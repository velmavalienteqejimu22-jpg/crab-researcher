"""
应用内任务调度器
使用 APScheduler 定时扫描并执行到期监测任务。
特性:
  - 单任务失败不影响其他任务
  - 失败任务自动重试（最多3次）
  - 完整的可观测性指标
  - 丰富的飞书卡片通知
"""

from typing import Optional
import logging
from collections import deque
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal
from app.models.task import MonitoringTask
from app.services.notification import NotificationService
from app.services.scraper import ScraperService

logger = logging.getLogger(__name__)

# 任务最大重试次数
MAX_TASK_RETRIES = 3


class MonitoringScheduler:
    """应用内监测任务调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._running = False

        # 运行态指标
        self.started_at: Optional[datetime] = None
        self.last_run_at: Optional[datetime] = None
        self.last_success_at: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.total_runs = 0
        self.total_failures = 0
        self.total_tasks_processed = 0
        self.total_alerts_sent = 0
        self.recent_runs: deque[dict] = deque(maxlen=20)

        # 任务失败计数器 {task_id: retry_count}
        self._task_retries: dict[int, int] = {}

    def start(self):
        if self._running:
            return

        self.scheduler.add_job(
            self.run_due_tasks,
            trigger="interval",
            minutes=1,
            id="monitoring-runner",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=30,
            replace_existing=True,
        )
        self.scheduler.start()
        self._running = True
        self.started_at = datetime.utcnow()
        logger.info("[Scheduler] 已启动（每分钟扫描到期任务）")

    def shutdown(self):
        if not self._running:
            return
        self.scheduler.shutdown(wait=False)
        self._running = False
        logger.info("[Scheduler] 已停止")

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "started_at": self._to_iso(self.started_at),
            "last_run_at": self._to_iso(self.last_run_at),
            "last_success_at": self._to_iso(self.last_success_at),
            "last_error": self.last_error,
            "counters": {
                "total_runs": self.total_runs,
                "total_failures": self.total_failures,
                "total_tasks_processed": self.total_tasks_processed,
                "total_alerts_sent": self.total_alerts_sent,
            },
            "recent_runs": list(self.recent_runs),
        }

    async def run_due_tasks(self):
        """扫描并执行到期任务"""
        now = datetime.utcnow()
        self.last_run_at = now
        self.total_runs += 1

        async with AsyncSessionLocal() as db:
            scraper = ScraperService(db)
            notifier = NotificationService()
            alerts = 0
            task_count = 0
            task_errors = []
            run_record = {
                "started_at": self._to_iso(now),
                "tasks": 0,
                "alerts": 0,
                "errors": 0,
                "status": "success",
                "details": [],
            }

            try:
                stmt = select(MonitoringTask).where(
                    MonitoringTask.status == "active",
                    or_(
                        MonitoringTask.next_run_at.is_(None),
                        MonitoringTask.next_run_at <= now,
                    ),
                )
                tasks = (await db.execute(stmt)).scalars().all()

                for task in tasks:
                    task_count += 1
                    task_detail = {
                        "task_id": task.id,
                        "brand": task.brand_name,
                        "type": task.task_type,
                        "status": "success",
                    }

                    try:
                        result = await self._run_task(task, scraper)
                        task.last_run_at = now
                        task.next_run_at = self._calc_next_run_at(task.frequency, now)

                        # 任务成功，重置重试计数
                        self._task_retries.pop(task.id, None)

                        if result and result.change_detected:
                            alerts += 1
                            await self._send_rich_notification(
                                notifier, task, result
                            )
                            task_detail["alert"] = True

                    except Exception as e:
                        # 单任务失败不影响其他任务
                        retry_count = self._task_retries.get(task.id, 0) + 1
                        self._task_retries[task.id] = retry_count

                        error_msg = f"task_id={task.id} brand={task.brand_name}: {str(e)[:200]}"
                        task_errors.append(error_msg)
                        task_detail["status"] = "failed"
                        task_detail["error"] = str(e)[:200]
                        task_detail["retry_count"] = retry_count

                        logger.error(
                            f"[Scheduler] 任务执行失败(第{retry_count}次): {error_msg}"
                        )

                        if retry_count >= MAX_TASK_RETRIES:
                            # 超过最大重试次数，暂停任务
                            task.status = "paused"
                            task_detail["auto_paused"] = True
                            logger.warning(
                                f"[Scheduler] 任务 {task.id} 连续失败{retry_count}次，已自动暂停"
                            )
                            # 通知用户
                            await notifier.send_alert(
                                title=f"任务自动暂停 - {task.brand_name}",
                                content=(
                                    f"任务 #{task.id} 连续失败 {retry_count} 次已被自动暂停。\n"
                                    f"错误: {str(e)[:200]}\n"
                                    f"请检查任务配置后手动恢复。"
                                ),
                                severity="critical",
                            )
                        else:
                            # 设置下次重试（短间隔）
                            task.next_run_at = now + timedelta(minutes=5 * retry_count)

                    run_record["details"].append(task_detail)

                await db.commit()
                self.last_success_at = datetime.utcnow()
                self.total_tasks_processed += task_count
                self.total_alerts_sent += alerts

                if task_errors:
                    self.last_error = f"{len(task_errors)}个任务失败"
                    self.total_failures += len(task_errors)
                    run_record["status"] = "partial"
                    run_record["errors"] = len(task_errors)
                else:
                    self.last_error = None

                run_record["tasks"] = task_count
                run_record["alerts"] = alerts
                self.recent_runs.append(run_record)

                if task_count > 0:
                    logger.info(
                        "[Scheduler] 本轮完成: tasks=%s alerts=%s errors=%s",
                        task_count, alerts, len(task_errors),
                    )

            except Exception as e:
                await db.rollback()
                self.total_failures += 1
                self.last_error = str(e)
                run_record["status"] = "failed"
                run_record["errors"] = str(e)[:200]
                self.recent_runs.append(run_record)
                logger.exception("[Scheduler] 本轮执行整体失败")
            finally:
                await scraper.close()
                await notifier.close()

    async def _run_task(self, task: MonitoringTask, scraper: ScraperService):
        """执行单个监测任务"""
        task_type = task.task_type.lower()

        if task_type == "price":
            return await scraper.scrape_price(task)
        if task_type == "sentiment":
            return await scraper.scrape_sentiment(task)
        if task_type == "new_product":
            return await scraper.scrape_new_product(task)
        if task_type == "promotion":
            return await scraper.scrape_price(task)

        logger.warning(
            "[Scheduler] 未知任务类型: task_id=%s type=%s，尝试作为价格监测执行",
            task.id, task.task_type,
        )
        return await scraper.scrape_price(task)

    async def _send_rich_notification(
        self, notifier: NotificationService, task: MonitoringTask, result
    ):
        """根据任务类型发送丰富的通知"""
        task_type = task.task_type.lower()
        data = result.data or {}

        try:
            if task_type == "sentiment":
                await notifier.send_feishu_sentiment_alert(
                    brand=task.brand_name,
                    platform=task.platform,
                    sentiment_score=data.get("sentiment_score", 0.5),
                    mention_count=sum(
                        m.get("count", 0) for m in data.get("mentions", [])
                    ),
                    hot_topics=data.get("hot_topics", []),
                    analysis=data.get("analysis", ""),
                )
            elif task_type == "new_product":
                new_products = data.get("new_products", [])
                if new_products:
                    await notifier.send_feishu_new_product_alert(
                        brand=task.brand_name,
                        platform=task.platform,
                        new_products=new_products,
                    )
            else:
                # price / promotion / 其他
                await notifier.send_alert(
                    title=f"{self._task_type_label(task.task_type)} - {task.brand_name}",
                    content=result.change_summary or "检测到变化",
                    severity=result.severity,
                )
        except Exception as e:
            # 通知发送失败不应影响任务执行
            logger.error(f"[Scheduler] 通知发送失败: {e}")

    @staticmethod
    def _calc_next_run_at(frequency: str, base_time: datetime) -> datetime:
        freq = frequency.lower()
        if freq == "hourly":
            return base_time + timedelta(hours=1)
        if freq == "weekly":
            return base_time + timedelta(days=7)
        # daily 或其他
        return base_time + timedelta(days=1)

    @staticmethod
    def _task_type_label(task_type: str) -> str:
        return {
            "price": "价格变动",
            "sentiment": "舆情预警",
            "new_product": "新品监测",
            "promotion": "促销监测",
        }.get(task_type.lower(), "监测告警")

    @staticmethod
    def _to_iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

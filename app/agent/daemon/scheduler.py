"""
CrabRes Daemon Scheduler — APScheduler 驱动的持久化调度

替代 asyncio.sleep 循环，解决：
1. 进程重启后 Daemon 自动恢复
2. 精确的 cron 调度（不是近似的 sleep 30min）
3. 午夜 Dream 用 cron 触发而非轮询检测
4. 任务执行有超时保护
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class DaemonScheduler:
    """
    APScheduler 封装层 — 管理 GrowthDaemon 的所有定时任务

    Jobs:
    - growth_tick:  每 30 分钟执行一次 _tick()
    - midnight_dream: 每天 00:00 执行 Growth Dream
    - health_check:  每 5 分钟检查 Daemon 健康状态
    """

    def __init__(self, daemon):
        self.daemon = daemon
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,          # 错过的执行合并为一次
                "max_instances": 1,         # 同一 job 不并发
                "misfire_grace_time": 300,  # 5 分钟内的错过仍执行
            },
        )
        self._started = False
        self._tick_count = 0
        self._last_tick_at: Optional[datetime] = None
        self._last_error: Optional[str] = None

    def start(self):
        """注册所有 job 并启动调度器"""
        if self._started:
            return

        # Job 1: 增长扫描 — 每 30 分钟
        self.scheduler.add_job(
            self._safe_tick,
            trigger=IntervalTrigger(minutes=30),
            id="growth_tick",
            name="Growth Tick (scan competitors, social, calendar)",
            replace_existing=True,
        )

        # Job 2: 午夜 Dream — 每天 00:00 UTC
        self.scheduler.add_job(
            self._safe_dream,
            trigger=CronTrigger(hour=0, minute=0),
            id="midnight_dream",
            name="Midnight Growth Dream (memory distillation)",
            replace_existing=True,
        )

        # Job 3: 健康检查 — 每 5 分钟
        self.scheduler.add_job(
            self._health_check,
            trigger=IntervalTrigger(minutes=5),
            id="health_check",
            name="Daemon Health Check",
            replace_existing=True,
        )

        self.scheduler.start()
        self._started = True
        logger.info("🦀 DaemonScheduler started: growth_tick(30min) + midnight_dream(00:00) + health_check(5min)")

    def shutdown(self):
        """优雅关闭"""
        if not self._started:
            return
        self.scheduler.shutdown(wait=False)
        self._started = False
        logger.info("🦀 DaemonScheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._started and self.scheduler.running

    def get_status(self) -> dict:
        """返回调度器状态（供 API 使用）"""
        jobs = []
        if self._started:
            for job in self.scheduler.get_jobs():
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                })

        return {
            "running": self.is_running,
            "tick_count": self._tick_count,
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_error": self._last_error,
            "jobs": jobs,
        }

    async def force_tick(self):
        """手动触发一次 tick（供 API 调用）"""
        await self._safe_tick()

    async def force_dream(self):
        """手动触发一次 Dream（供 API 调用）"""
        await self._safe_dream()

    async def _safe_tick(self):
        """带超时和错误保护的 tick"""
        try:
            self._tick_count += 1
            self._last_tick_at = datetime.utcnow()
            # 超时 5 分钟（防止 API 调用卡死）
            await asyncio.wait_for(self.daemon._tick(), timeout=300)
            self._last_error = None
            logger.info(f"🦀 Daemon tick #{self._tick_count} completed")
        except asyncio.TimeoutError:
            self._last_error = "Tick timed out (>5min)"
            logger.error("🦀 Daemon tick timed out after 5 minutes")
        except Exception as e:
            self._last_error = str(e)[:200]
            logger.error(f"🦀 Daemon tick failed: {e}", exc_info=True)

    async def _safe_dream(self):
        """带错误保护的 Dream"""
        try:
            await asyncio.wait_for(self.daemon._midnight_boundary(), timeout=600)
            logger.info("🦀 Midnight Dream completed")
        except asyncio.TimeoutError:
            logger.error("🦀 Midnight Dream timed out after 10 minutes")
        except Exception as e:
            logger.error(f"🦀 Midnight Dream failed: {e}", exc_info=True)

    async def _health_check(self):
        """健康检查 — 确认关键组件还活着"""
        issues = []

        # 检查 memory 是否可访问
        try:
            await self.daemon.memory.load("product")
        except Exception as e:
            issues.append(f"Memory inaccessible: {e}")

        # 检查 tools 是否注册
        if not self.daemon.tools.list_definitions():
            issues.append("No tools registered")

        if issues:
            logger.warning(f"🦀 Daemon health issues: {issues}")
        else:
            logger.debug("🦀 Daemon health: OK")

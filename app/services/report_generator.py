"""
报告生成服务
支持: 日报 / 周报 / 自定义专题
流程: 数据聚合 → RAG增强 → LLM生成 → Markdown输出
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import MonitoringResult, MonitoringTask, Report
from app.services.cost_controller import TaskTier
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class ReportGenerator:
    """报告生成器"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMService(db)
        self.rag = RAGService(db)

    async def generate(
        self,
        user_id: int,
        report_type: str,
        brands: Optional[list[str]] = None,
        title: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> Report:
        """
        生成报告主流程:
        1. 从数据库收集最近的监测数据
        2. RAG检索相关历史报告和SOP
        3. 智能选择模型
        4. LLM生成Markdown报告
        5. 保存到数据库
        """
        logger.info(f"[Report] 生成 {report_type} 报告, user={user_id}")

        # 1. 收集监测数据
        monitoring_data = await self._collect_data(user_id, report_type, brands)

        # 2. RAG检索增强
        rag_context = ""
        if monitoring_data:
            search_query = f"{report_type}报告 " + " ".join(brands or [])
            rag_context = await self.rag.search_and_augment(
                user_id, search_query, top_k=3, doc_type="report"
            )

        # 3. 构建 prompt
        prompt = self._build_prompt(report_type, monitoring_data, rag_context, custom_prompt)

        # 4. 调用 LLM (报告生成 = Tier 3 智能分析)
        tier = TaskTier.TIER_3_ANALYSIS
        if custom_prompt and len(custom_prompt) > 200:
            tier = TaskTier.TIER_4_DEEP  # 复杂的自定义分析用深度模型

        result = await self.llm.chat(
            user_id=user_id,
            tier=tier,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
            task_type="report",
            temperature=0.5,
            max_tokens=4096,
        )

        # 5. 保存报告
        final_title = title or self._auto_title(report_type, brands)
        report = Report(
            user_id=user_id,
            report_type=report_type,
            title=final_title,
            content=result["content"],
            model_used=result["model"],
            token_cost=result["cost_cny"],
        )
        self.db.add(report)
        await self.db.flush()

        logger.info(f"[Report] 报告生成完成: id={report.id}, 费用=¥{result['cost_cny']}")
        return report

    async def _collect_data(
        self, user_id: int, report_type: str, brands: Optional[list[str]]
    ) -> list[dict]:
        """收集时间段内的监测数据"""
        now = datetime.utcnow()

        if report_type == "daily":
            since = now - timedelta(days=1)
        elif report_type == "weekly":
            since = now - timedelta(days=7)
        else:
            since = now - timedelta(days=30)

        # 查询该用户的所有任务
        stmt = select(MonitoringTask).where(MonitoringTask.user_id == user_id)
        if brands:
            stmt = stmt.where(MonitoringTask.brand_name.in_(brands))

        tasks_result = await self.db.execute(stmt)
        tasks = tasks_result.scalars().all()
        task_ids = [t.id for t in tasks]

        if not task_ids:
            return []

        # 查询时间段内的结果
        results_stmt = (
            select(MonitoringResult)
            .where(
                MonitoringResult.task_id.in_(task_ids),
                MonitoringResult.created_at >= since,
            )
            .order_by(MonitoringResult.created_at.desc())
            .limit(100)
        )
        results = await self.db.execute(results_stmt)

        data = []
        for r in results.scalars().all():
            data.append({
                "task_id": r.task_id,
                "data": r.data,
                "change_detected": r.change_detected,
                "change_type": r.change_type,
                "change_summary": r.change_summary,
                "severity": r.severity,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })

        return data

    def _system_prompt(self) -> str:
        return """你是 CrabRes，一个 AI 增长策略 Agent。
你的任务是基于监测数据生成结构化的分析报告。

报告要求:
1. 使用Markdown格式
2. 包含摘要、重要发现、数据分析、建议
3. 语言简洁专业，数据驱动
4. 标注数据来源和时间
5. 如有参考资料，请在报告中引用"""

    def _build_prompt(
        self,
        report_type: str,
        data: list[dict],
        rag_context: str,
        custom_prompt: Optional[str],
    ) -> str:
        parts = []

        if report_type == "daily":
            parts.append("请生成一份【日报】，覆盖过去24小时的监测数据。")
        elif report_type == "weekly":
            parts.append("请生成一份【周报】，覆盖过去7天的监测数据和趋势分析。")
        else:
            parts.append("请生成一份【专题分析报告】。")

        if data:
            changes = [d for d in data if d["change_detected"]]
            parts.append(f"\n监测数据概览: 共{len(data)}条记录, 其中{len(changes)}条检测到变化。")

            if changes:
                parts.append("\n重要变化:")
                for c in changes[:10]:
                    parts.append(f"- [{c['severity']}] {c['change_summary']}")
        else:
            parts.append("\n暂无监测数据，请基于行业知识生成框架性报告。")

        if rag_context:
            parts.append(f"\n{rag_context}")

        if custom_prompt:
            parts.append(f"\n用户额外要求: {custom_prompt}")

        return "\n".join(parts)

    def _auto_title(self, report_type: str, brands: Optional[list[str]]) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%d")
        brand_str = "、".join(brands) if brands else "全品牌"
        type_map = {"daily": "日报", "weekly": "周报", "custom": "专题分析"}
        return f"{brand_str} {type_map.get(report_type, '报告')} ({now})"

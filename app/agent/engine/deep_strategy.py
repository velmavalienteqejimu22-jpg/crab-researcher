"""
CrabRes Deep Strategy — ULTRAPLAN

学习 Claude Code 的 ULTRAPLAN 设计：
将复杂策略任务卸载到后台，给 10-30 分钟深度思考时间。
用户不用盯着 loading 等，完成后通过通知推送结果。

触发词：
  - "deep strategy" / "重新想想整个增长策略"
  - "pivot" / "产品方向变了"
  - "从头来过" / "start over"
  - 或者 Agent 自动判断当前请求需要深度思考

流程：
  1. 用户发出复杂请求
  2. Coordinator 识别为 Deep Strategy 场景
  3. 创建后台任务（asyncio.create_task）
  4. 立即回复用户"后台策略会已启动"
  5. 后台：多轮搜索 → 全专家圆桌 → 生成完整 Playbook
  6. 完成后：保存结果 + 通知用户
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


class DeepStrategyStatus(str, Enum):
    QUEUED = "queued"
    RESEARCHING = "researching"
    CONSULTING = "consulting"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DeepStrategyJob:
    """一个深度策略任务"""
    id: str = field(default_factory=lambda: f"ds-{uuid.uuid4().hex[:8]}")
    user_id: str = ""
    session_id: str = ""
    request: str = ""
    status: DeepStrategyStatus = DeepStrategyStatus.QUEUED
    progress: float = 0.0  # 0-1
    progress_detail: str = ""
    result: Optional[str] = None
    expert_outputs: dict = field(default_factory=dict)
    research_data: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None


# 触发词检测
DEEP_STRATEGY_TRIGGERS = [
    "deep strategy", "深度策略", "重新想想整个增长策略",
    "pivot", "转型", "方向变了", "产品方向变了",
    "从头来过", "start over", "rethink everything",
    "重新制定", "全面重新", "completely rethink",
    "重做增长计划", "redo growth plan",
]


def should_trigger_deep_strategy(message: str) -> bool:
    """检测用户消息是否应该触发深度策略模式"""
    msg_lower = message.lower()
    return any(trigger in msg_lower for trigger in DEEP_STRATEGY_TRIGGERS)


class DeepStrategyEngine:
    """
    深度策略引擎
    
    管理后台策略任务的生命周期：创建 → 执行 → 完成/失败 → 通知
    """
    
    def __init__(self, base_dir: str = ".crabres/deep_strategy"):
        self._jobs: dict[str, DeepStrategyJob] = {}
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._running_tasks: dict[str, asyncio.Task] = {}
    
    async def create_job(
        self,
        user_id: str,
        session_id: str,
        request: str,
        llm_service,
        tool_registry,
        expert_pool,
        memory,
        notifier=None,
    ) -> DeepStrategyJob:
        """创建并启动一个深度策略任务"""
        job = DeepStrategyJob(
            user_id=user_id,
            session_id=session_id,
            request=request,
        )
        self._jobs[job.id] = job
        
        # 保存任务元数据
        await self._save_job(job)
        
        # 启动后台执行
        task = asyncio.create_task(
            self._execute_job(job, llm_service, tool_registry, expert_pool, memory, notifier)
        )
        self._running_tasks[job.id] = task
        
        logger.info(f"Deep Strategy job {job.id} created for user {user_id}")
        return job
    
    def get_job(self, job_id: str) -> Optional[DeepStrategyJob]:
        return self._jobs.get(job_id)
    
    def get_user_jobs(self, user_id: str) -> list[DeepStrategyJob]:
        return [j for j in self._jobs.values() if j.user_id == user_id]
    
    async def _execute_job(
        self,
        job: DeepStrategyJob,
        llm,
        tools,
        experts,
        memory,
        notifier,
    ):
        """后台执行深度策略分析"""
        from app.agent.engine.llm_adapter import TaskTier
        
        try:
            # Phase 1: 深度研究（30%）
            job.status = DeepStrategyStatus.RESEARCHING
            job.progress_detail = "Conducting deep market research..."
            await self._save_job(job)
            
            research_queries = await self._generate_research_queries(llm, job.request)
            
            for i, query in enumerate(research_queries):
                job.progress = 0.05 + (i / len(research_queries)) * 0.25
                job.progress_detail = f"Researching: {query[:50]}..."
                await self._save_job(job)
                
                tool = tools.get("web_search")
                if tool:
                    try:
                        result = await asyncio.wait_for(
                            tool.execute(query=query),
                            timeout=30.0,
                        )
                        job.research_data.append({
                            "query": query,
                            "result": json.dumps(result, ensure_ascii=False, default=str)[:2000],
                        })
                    except Exception as e:
                        logger.warning(f"Deep Strategy research failed for '{query}': {e}")
            
            # Phase 2: 专家圆桌（50%）
            job.status = DeepStrategyStatus.CONSULTING
            job.progress = 0.30
            job.progress_detail = "Assembling full expert roundtable..."
            await self._save_job(job)
            
            # 选择 6-8 个最相关的专家（比普通圆桌更多）
            expert_ids = [
                "market_researcher", "economist", "social_media",
                "psychologist", "content_strategist", "product_growth",
                "data_analyst", "copywriter",
            ]
            
            research_summary = "\n".join(
                f"- {r['query']}: {r['result'][:500]}" for r in job.research_data[:8]
            )
            
            for i, eid in enumerate(expert_ids):
                expert = experts.get(eid)
                if not expert:
                    continue
                    
                job.progress = 0.30 + (i / len(expert_ids)) * 0.40
                job.progress_detail = f"Consulting {expert.name}..."
                await self._save_job(job)
                
                try:
                    context = {
                        "user_message": job.request,
                        "tool_results": job.research_data,
                        "research_summary": research_summary,
                    }
                    output = await expert.analyze(
                        context,
                        f"Deep strategy analysis for: {job.request}\n\nResearch data:\n{research_summary[:3000]}"
                    )
                    job.expert_outputs[eid] = output[:2000]
                except Exception as e:
                    logger.warning(f"Deep Strategy expert {eid} failed: {e}")
                    job.expert_outputs[eid] = f"[Analysis unavailable: {str(e)[:100]}]"
            
            # Phase 3: CGO 综合（20%）
            job.status = DeepStrategyStatus.SYNTHESIZING
            job.progress = 0.70
            job.progress_detail = "CGO synthesizing final strategy..."
            await self._save_job(job)
            
            expert_summary = "\n\n".join(
                f"### {eid}\n{output[:1000]}" for eid, output in job.expert_outputs.items()
            )
            
            synthesis_prompt = f"""You are CrabRes's Chief Growth Officer. 

You just ran a DEEP STRATEGY SESSION — a full expert roundtable with 8 specialists.
This is not a quick answer. This is a comprehensive, fully-researched growth plan.

USER REQUEST: {job.request}

RESEARCH DATA:
{research_summary[:4000]}

EXPERT ANALYSES:
{expert_summary[:6000]}

Now synthesize everything into a COMPLETE growth strategy with:
1. Executive Summary (3 bullet points)
2. Market Analysis (key findings from research)
3. 3 Playbooks ranked by priority, each with:
   - Name and rationale
   - Phases (Prep → Execute → Track)
   - Specific steps with timeline and budget
   - Success metrics
4. Budget allocation across playbooks
5. 90-day milestone checkpoints
6. One Hard Truth the user needs to hear

This is the DEEP strategy — be thorough, specific, and data-driven.
Reference actual competitor names, actual numbers, actual subreddits."""

            response = await llm.generate(
                system_prompt=synthesis_prompt,
                messages=[{"role": "user", "content": job.request}],
                tier=TaskTier.CRITICAL,
                max_tokens=4096,
            )
            
            job.result = response.content
            job.status = DeepStrategyStatus.COMPLETED
            job.progress = 1.0
            job.progress_detail = "Strategy complete!"
            job.completed_at = time.time()
            await self._save_job(job)
            
            # 保存到 memory
            result_path = self._base_dir / f"{job.id}_result.md"
            result_path.write_text(
                f"# Deep Strategy: {job.request[:100]}\n\n"
                f"**Created**: {time.strftime('%Y-%m-%d %H:%M', time.localtime(job.created_at))}\n"
                f"**Completed**: {time.strftime('%Y-%m-%d %H:%M', time.localtime(job.completed_at))}\n"
                f"**Experts**: {', '.join(job.expert_outputs.keys())}\n\n"
                f"---\n\n{job.result}\n",
                encoding="utf-8",
            )
            
            # 通知用户
            if notifier:
                elapsed = int(job.completed_at - job.created_at)
                try:
                    await notifier.send(
                        title="🦀 Deep Strategy Complete",
                        body=f"Your growth strategy session finished in {elapsed}s. {len(job.expert_outputs)} experts consulted.",
                        urgency="high",
                    )
                except Exception as e:
                    logger.warning(f"Failed to notify user: {e}")
            
            logger.info(f"Deep Strategy {job.id} completed in {elapsed}s with {len(job.expert_outputs)} experts")
            
        except Exception as e:
            job.status = DeepStrategyStatus.FAILED
            job.error = str(e)[:500]
            job.completed_at = time.time()
            await self._save_job(job)
            logger.error(f"Deep Strategy {job.id} failed: {e}")
    
    async def _generate_research_queries(self, llm, request: str) -> list[str]:
        """让 LLM 生成一组深度研究查询"""
        from app.agent.engine.llm_adapter import TaskTier
        
        response = await llm.generate(
            system_prompt=(
                "Generate 5-8 specific web search queries to deeply research this growth strategy request. "
                "Include: competitor analysis queries, market size queries, channel-specific queries, "
                "pricing research queries, user persona queries. "
                "Return ONLY a JSON array of strings, nothing else."
            ),
            messages=[{"role": "user", "content": request}],
            tier=TaskTier.PARSING,
            max_tokens=500,
        )
        
        try:
            queries = json.loads(response.content)
            if isinstance(queries, list):
                return queries[:8]
        except json.JSONDecodeError:
            pass
        
        # Fallback: 手动拆分
        return [
            f"{request} competitors market analysis",
            f"{request} user acquisition channels",
            f"{request} pricing strategy SaaS",
            f"{request} Reddit community growth",
            f"{request} SEO content strategy",
        ]
    
    async def _save_job(self, job: DeepStrategyJob):
        """持久化任务状态"""
        path = self._base_dir / f"{job.id}.json"
        data = {
            "id": job.id,
            "user_id": job.user_id,
            "session_id": job.session_id,
            "request": job.request,
            "status": job.status.value,
            "progress": job.progress,
            "progress_detail": job.progress_detail,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "error": job.error,
            "expert_count": len(job.expert_outputs),
            "research_count": len(job.research_data),
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# 全局引擎实例
_engine: Optional[DeepStrategyEngine] = None

def get_deep_strategy_engine() -> DeepStrategyEngine:
    global _engine
    if _engine is None:
        _engine = DeepStrategyEngine()
    return _engine

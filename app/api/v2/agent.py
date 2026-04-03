"""
CrabRes Agent API — v2

核心端点：用户通过这个 API 和 CrabRes Agent 对话。
不是简单的 chat，是多轮增长研究对话。
"""

import uuid
import logging
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.security import get_current_user
from app.agent.engine.llm_adapter import AgentLLM
from app.agent.engine.loop import AgentLoop, LoopState
from app.agent.tools import ToolRegistry
from app.agent.tools.research import WebSearchTool, ScrapeWebsiteTool, SocialSearchTool, CompetitorAnalyzeTool, DeepScrapeTool
from app.agent.tools.actions import WritePostTool, WriteEmailTool, SubmitToDirectoryTool, SetActiveCampaignTool
from app.agent.tools.browser import BrowseWebsiteTool
from app.agent.experts import ExpertPool
from app.agent.experts.market_researcher import MarketResearcher
from app.agent.experts.economist import Economist
from app.agent.experts.content_strategist import ContentStrategist
from app.agent.experts.social_media import SocialMediaExpert
from app.agent.experts.paid_ads import PaidAdsExpert
from app.agent.experts.partnerships import PartnershipsExpert
from app.agent.experts.ai_distribution import AIDistributionExpert
from app.agent.experts.psychologist import ConsumerPsychologist
from app.agent.experts.product_growth import ProductGrowthExpert
from app.agent.experts.data_analyst import DataAnalyst
from app.agent.experts.copywriter import MasterCopywriter
from app.agent.experts.critic import StrategyCritic
from app.agent.experts.designer import DesignExpert
from app.agent.memory import GrowthMemory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])

# 全局会话存储（带 TTL 和用户隔离）
_sessions: dict[str, AgentLoop] = {}
_session_owners: dict[str, int] = {}  # session_id -> user_id
_session_last_active: dict[str, float] = {}  # session_id -> timestamp
_SESSION_TTL = 1800  # 30 分钟无活动过期


def _cleanup_expired_sessions():
    """清理过期会话（每次请求时触发）"""
    import time
    now = time.time()
    expired = [sid for sid, ts in _session_last_active.items() if now - ts > _SESSION_TTL]
    for sid in expired:
        _sessions.pop(sid, None)
        _session_owners.pop(sid, None)
        _session_last_active.pop(sid, None)
    if expired:
        logger.info(f"Cleaned up {len(expired)} expired sessions")


def _get_or_create_tools() -> ToolRegistry:
    """创建工具注册表"""
    registry = ToolRegistry()
    # 研究工具
    registry.register(WebSearchTool())
    registry.register(ScrapeWebsiteTool())
    registry.register(SocialSearchTool())
    registry.register(CompetitorAnalyzeTool())
    registry.register(DeepScrapeTool())
    registry.register(BrowseWebsiteTool())
    # 行动工具
    registry.register(WritePostTool())
    registry.register(WriteEmailTool())
    registry.register(SubmitToDirectoryTool())
    registry.register(SetActiveCampaignTool())
    return registry


def _get_or_create_experts() -> ExpertPool:
    """创建专家池 — 13 位专家"""
    pool = ExpertPool()
    pool.register(MarketResearcher())
    pool.register(Economist())
    pool.register(ContentStrategist())
    pool.register(SocialMediaExpert())
    pool.register(PaidAdsExpert())
    pool.register(PartnershipsExpert())
    pool.register(AIDistributionExpert())
    pool.register(ConsumerPsychologist())
    pool.register(ProductGrowthExpert())
    pool.register(DataAnalyst())
    pool.register(MasterCopywriter())
    pool.register(StrategyCritic())
    pool.register(DesignExpert())
    return pool


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: str = "en"  # "en" or "zh" — from frontend Settings


class ChatResponse(BaseModel):
    session_id: str
    type: str              # message / question / status / expert_thinking / error
    content: str
    expert_id: Optional[str] = None
    pending_tasks: list[dict] = []


@router.post("/chat", response_model=list[ChatResponse])
async def agent_chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """非流式：等待全部完成后一次性返回。兼容旧前端。"""
    session_id = req.session_id or str(uuid.uuid4())
    user_id = current_user.get('user_id', 0)

    _cleanup_expired_sessions()

    if session_id in _session_owners and _session_owners[session_id] != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to you")

    if session_id not in _sessions:
        llm = AgentLLM()
        tools = _get_or_create_tools()
        experts = _get_or_create_experts()
        experts.set_llm(llm)
        memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")
        loop = AgentLoop(
            session_id=session_id, llm_service=llm,
            tool_registry=tools, expert_pool=experts, memory=memory,
        )
        _sessions[session_id] = loop
        _session_owners[session_id] = user_id

    loop = _sessions[session_id]
    _session_last_active[session_id] = __import__('time').time()

    outputs: list[ChatResponse] = []
    async for event in loop.run(req.message, language=req.language):
        outputs.append(ChatResponse(
            session_id=session_id,
            type=event.get("type", "message"),
            content=event.get("content", ""),
            expert_id=event.get("expert_id"),
            pending_tasks=loop.state.pending_user_tasks,
        ))

    if not outputs:
        outputs.append(ChatResponse(
            session_id=session_id, type="message",
            content="I'm thinking... please try again.",
        ))

    return outputs


@router.post("/chat/stream")
async def agent_chat_stream(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    SSE 流式聊天 — 每个事件立即推送给前端
    
    前端用 EventSource 或 fetch + ReadableStream 接收。
    每行格式: data: {"type":"status","content":"Researching...","session_id":"xxx"}
    """
    session_id = req.session_id or str(uuid.uuid4())
    user_id = current_user.get('user_id', 0)

    _cleanup_expired_sessions()

    if session_id in _session_owners and _session_owners[session_id] != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to you")

    if session_id not in _sessions:
        llm = AgentLLM()
        tools = _get_or_create_tools()
        experts = _get_or_create_experts()
        experts.set_llm(llm)
        memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")
        loop = AgentLoop(
            session_id=session_id, llm_service=llm,
            tool_registry=tools, expert_pool=experts, memory=memory,
        )
        _sessions[session_id] = loop
        _session_owners[session_id] = user_id

    loop = _sessions[session_id]
    _session_last_active[session_id] = __import__('time').time()

    async def event_generator():
        try:
            async for event in loop.run(req.message, language=req.language):
                data = json.dumps({
                    "session_id": session_id,
                    "type": event.get("type", "message"),
                    "content": event.get("content", ""),
                    "expert_id": event.get("expert_id"),
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)[:200], 'session_id': session_id})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/session/{session_id}/status")
async def get_session_status(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取会话状态"""
    loop = _sessions.get(session_id)
    if not loop:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        "session_id": session_id,
        "phase": loop.state.phase.value,
        "turn_count": loop.state.turn_count,
        "tokens_used": loop.state.total_tokens_used,
        "is_waiting_for_user": loop.state.is_waiting_for_user,
        "pending_tasks": loop.state.pending_user_tasks,
        "experts_consulted": list(loop.state.expert_outputs.keys()),
    }


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
):
    """列出用户的所有会话 (包含内存和磁盘)"""
    user_id = current_user.get('user_id', 'default')
    # loop_state 默认保存在 product/ 目录下
    memory_path = Path(f".crabres/memory/{user_id}/product")
    
    # 1. 首先包含内存中的活跃会话
    user_sessions = {}
    for sid, loop in _sessions.items():
        user_sessions[sid] = {
            "session_id": sid,
            "phase": loop.state.phase.value,
            "turn_count": loop.state.turn_count,
            "is_waiting": loop.state.is_waiting_for_user,
            "created_at": loop.state.created_at,
            "last_active_at": loop.state.last_active_at,
            "is_active": True,
        }
    
    # 2. 扫描磁盘上的持久化会话
    if memory_path.exists():
        for state_file in memory_path.glob("loop_state_*.json"):
            try:
                sid = state_file.stem.replace("loop_state_", "")
                if sid not in user_sessions:
                    with open(state_file, "r") as f:
                        data = json.load(f)
                        user_sessions[sid] = {
                            "session_id": sid,
                            "phase": data.get("phase"),
                            "turn_count": data.get("turn_count"),
                            "is_waiting": data.get("is_waiting"),
                            "created_at": data.get("created_at", state_file.stat().st_ctime),
                            "last_active_at": data.get("last_active_at", state_file.stat().st_mtime),
                            "is_active": False,
                            "from_disk": True
                        }
            except Exception as e:
                logger.error(f"Error loading session metadata from disk: {e}")
                continue

    return {"sessions": list(user_sessions.values())}


@router.get("/session/{session_id}/cost")
async def get_session_cost(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取会话的 LLM 成本报告"""
    loop = _sessions.get(session_id)
    if not loop:
        raise HTTPException(status_code=404, detail="会话不存在")
    return loop.llm.get_cost_report()


@router.get("/discoveries")
async def get_discoveries(
    current_user: dict = Depends(get_current_user),
):
    """获取 Growth Daemon 的最新发现（前端轮询此接口）"""
    from app.main import app as fastapi_app
    daemon = getattr(fastapi_app.state, 'growth_daemon', None)
    if not daemon:
        return {"discoveries": [], "note": "Daemon not running"}
    return {"discoveries": daemon.get_pending_discoveries()}

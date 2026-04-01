"""
CrabRes Agent API — v2

核心端点：用户通过这个 API 和 CrabRes Agent 对话。
不是简单的 chat，是多轮增长研究对话。
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.security import get_current_user
from app.agent.engine.llm_adapter import AgentLLM
from app.agent.engine.loop import AgentLoop, LoopState
from app.agent.tools import ToolRegistry
from app.agent.tools.research import WebSearchTool, ScrapeWebsiteTool, SocialSearchTool, CompetitorAnalyzeTool
from app.agent.experts import ExpertPool
from app.agent.experts.market_researcher import MarketResearcher
from app.agent.experts.economist import Economist
from app.agent.memory import GrowthMemory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["Agent"])

# 全局会话存储（MVP 阶段用内存，后续改为持久化）
_sessions: dict[str, AgentLoop] = {}


def _get_or_create_tools() -> ToolRegistry:
    """创建工具注册表"""
    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(ScrapeWebsiteTool())
    registry.register(SocialSearchTool())
    registry.register(CompetitorAnalyzeTool())
    return registry


def _get_or_create_experts() -> ExpertPool:
    """创建专家池"""
    pool = ExpertPool()
    pool.register(MarketResearcher())
    pool.register(Economist())
    # TODO: 注册其余 10 位专家
    return pool


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


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
    """
    和 CrabRes Agent 对话
    
    第一次对话不需要 session_id，系统会创建新会话。
    后续对话带上 session_id 继续同一个增长研究。
    
    返回一个列表，因为 Agent 一次对话可能产出多条消息（状态更新 + 最终回复）。
    """
    session_id = req.session_id or str(uuid.uuid4())

    # 获取或创建 Agent Loop
    if session_id not in _sessions:
        llm = AgentLLM()
        tools = _get_or_create_tools()
        experts = _get_or_create_experts()
        experts.set_llm(llm)  # 专家共享 LLM 实例
        memory = GrowthMemory(base_dir=f".crabres/memory/{current_user.get('user_id', 'default')}")

        loop = AgentLoop(
            session_id=session_id,
            llm_service=llm,
            tool_registry=tools,
            expert_pool=experts,
            memory=memory,
        )
        _sessions[session_id] = loop

    loop = _sessions[session_id]

    # 运行 Agent Loop，收集所有输出
    outputs: list[ChatResponse] = []
    async for event in loop.run(req.message):
        outputs.append(ChatResponse(
            session_id=session_id,
            type=event.get("type", "message"),
            content=event.get("content", ""),
            expert_id=event.get("expert_id"),
            pending_tasks=loop.state.pending_user_tasks,
        ))

    if not outputs:
        outputs.append(ChatResponse(
            session_id=session_id,
            type="message",
            content="我正在思考你的增长策略，请稍等...",
        ))

    return outputs


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
    """列出用户的所有会话"""
    user_sessions = []
    for sid, loop in _sessions.items():
        user_sessions.append({
            "session_id": sid,
            "phase": loop.state.phase.value,
            "turn_count": loop.state.turn_count,
            "is_waiting": loop.state.is_waiting_for_user,
            "created_at": loop.state.created_at,
            "last_active_at": loop.state.last_active_at,
        })
    return {"sessions": user_sessions}


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

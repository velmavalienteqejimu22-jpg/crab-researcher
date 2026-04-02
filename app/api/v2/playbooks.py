"""
CrabRes Playbook API — 增长执行链管理

用户可以：
- 查看 Agent 生成的 Playbooks
- 激活某个 Playbook 开始执行
- 更新 step 状态（完成/跳过）
- 查看执行进度
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.agent.memory.playbooks import PlaybookStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/playbooks", tags=["Playbooks"])


def _get_store(user_id: int) -> PlaybookStore:
    return PlaybookStore(base_dir=f".crabres/memory/{user_id}")


@router.get("")
async def list_playbooks(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """列出所有 Playbooks"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    playbooks = await store.get_playbooks(status=status)
    return {"playbooks": playbooks}


@router.get("/{playbook_id}")
async def get_playbook(
    playbook_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取单个 Playbook 详情"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    pb = await store.get_playbook(playbook_id)
    if not pb:
        return {"error": "Playbook not found"}
    return {"playbook": pb}


@router.post("/{playbook_id}/activate")
async def activate_playbook(
    playbook_id: str,
    current_user: dict = Depends(get_current_user),
):
    """激活一个 Playbook（开始执行）"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    await store.activate_playbook(playbook_id)
    return {"status": "activated", "playbook_id": playbook_id}


class UpdateStepRequest(BaseModel):
    phase_idx: int = Field(..., description="Phase 索引 (0-based)")
    step_idx: int = Field(..., description="Step 索引 (0-based)")
    status: str = Field(..., description="pending / in_progress / done / skipped")
    notes: str = Field("", description="完成笔记")


@router.post("/{playbook_id}/step")
async def update_step(
    playbook_id: str,
    req: UpdateStepRequest,
    current_user: dict = Depends(get_current_user),
):
    """更新某个 step 的状态"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    await store.update_step_status(
        playbook_id=playbook_id,
        phase_idx=req.phase_idx,
        step_idx=req.step_idx,
        status=req.status,
        notes=req.notes,
    )
    return {"status": "updated", "playbook_id": playbook_id, "step_status": req.status}

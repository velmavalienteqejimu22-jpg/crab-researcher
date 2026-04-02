"""
CrabRes Growth Data API — 读写增长计划和任务数据

前端 Surface/Plan 页面从这里加载真实数据。
Agent 通过 memory 写入，这里只读。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.security import get_current_user
from app.agent.memory import GrowthMemory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/growth", tags=["Growth Data"])


def _get_memory(user_id: int) -> GrowthMemory:
    return GrowthMemory(base_dir=f".crabres/memory/{user_id}")


@router.get("/plan")
async def get_growth_plan(current_user: dict = Depends(get_current_user)):
    """获取当前增长计划"""
    memory = _get_memory(current_user.get("user_id", 0))
    plan = await memory.load("growth_plan", category="strategy")
    product = await memory.load("product")
    return {
        "plan": plan or {},
        "product": product or {},
    }


@router.get("/tasks")
async def get_daily_tasks(current_user: dict = Depends(get_current_user)):
    """获取今日任务"""
    memory = _get_memory(current_user.get("user_id", 0))
    tasks = await memory.load("daily_tasks", category="strategy")
    if not tasks:
        # 没有 Agent 生成的任务时返回引导任务
        return {"tasks": [
            {"id": "onboard", "type": "chat", "title": "Tell CrabRes about your product",
             "subtitle": "Start a conversation to begin research", "status": "pending"},
        ]}
    return {"tasks": tasks if isinstance(tasks, list) else [tasks]}


@router.get("/discoveries")
async def get_recent_discoveries(current_user: dict = Depends(get_current_user)):
    """获取最近的发现（从日志读取）"""
    memory = _get_memory(current_user.get("user_id", 0))
    # 也检查全局 daemon 的发现
    global_memory = GrowthMemory(base_dir=".crabres/memory/global")

    discoveries = []

    # 从用户记忆的 journal 读
    journal_dir = memory.base_dir / "journal"
    if journal_dir.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        journal_file = journal_dir / f"{today}.jsonl"
        if journal_file.exists():
            for line in journal_file.read_text().strip().split("\n")[-10:]:
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "daemon_discovery":
                            discoveries.append(entry.get("discovery", {}))
                    except json.JSONDecodeError:
                        pass

    # 从全局 daemon 日志也读
    global_journal = global_memory.base_dir / "journal"
    if global_journal.exists():
        today = datetime.now().strftime("%Y-%m-%d")
        gj_file = global_journal / f"{today}.jsonl"
        if gj_file.exists():
            for line in gj_file.read_text().strip().split("\n")[-5:]:
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "daemon_discovery":
                            discoveries.append(entry.get("discovery", {}))
                    except json.JSONDecodeError:
                        pass

    return {"discoveries": discoveries[-10:]}  # 最多 10 条


@router.get("/stats")
async def get_growth_stats(current_user: dict = Depends(get_current_user)):
    """获取增长统计"""
    memory = _get_memory(current_user.get("user_id", 0))
    product = await memory.load("product")
    execution = await memory.load("execution_stats", category="execution")

    return {
        "total_users": execution.get("total_users", 0) if execution else 0,
        "growth_rate": execution.get("growth_rate", 0) if execution else 0,
        "streak_days": execution.get("streak_days", 0) if execution else 0,
        "strategies_active": execution.get("strategies_active", 0) if execution else 0,
        "active_campaign_url": execution.get("active_campaign_url", "") if execution else "",
        "product_name": product.get("name", "") if product else "",
    }


class CampaignRequest(BaseModel):
    url: str
    name: Optional[str] = "Global Launch Post"


@router.post("/campaign")
async def update_active_campaign(
    req: CampaignRequest,
    current_user: dict = Depends(get_current_user)
):
    """更新当前活跃的增长战役链接"""
    memory = _get_memory(current_user.get("user_id", 0))
    execution = await memory.load("execution_stats", category="execution") or {}
    
    execution["active_campaign_url"] = req.url
    execution["active_campaign_name"] = req.name
    
    await memory.save("execution_stats", execution, category="execution")
    return {"status": "success", "url": req.url}


@router.get("/calendar")
async def get_content_calendar(current_user: dict = Depends(get_current_user)):
    """获取内容日历"""
    memory = _get_memory(current_user.get("user_id", 0))
    calendar = await memory.load("content_calendar", category="strategy")
    return {"calendar": calendar or []}

"""
CrabRes Real World API — 管理 Agent 的真实世界连接

端点：
- RSS feeds: 添加/删除/列出订阅源
- Competitors: 添加/删除监控的竞品 URL
- Actions: 查看/确认/完成 action
- Status: 查看真实世界连接状态
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/real-world", tags=["Real World"])


class FeedInput(BaseModel):
    url: str
    name: str = ""
    category: str = "general"


class CompetitorInput(BaseModel):
    url: str


class ActionConfirmInput(BaseModel):
    action_id: str
    result_url: str = ""


def _get_daemon(request: Request):
    return getattr(request.app.state, "growth_daemon", None)


@router.get("/status")
async def real_world_status(request: Request, current_user: dict = Depends(get_current_user)):
    """获取真实世界连接的完整状态"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}
    return {
        "daemon_running": daemon._running,
        "scheduler": daemon.scheduler_status,
        "real_world": daemon.real_world_status,
    }


# === RSS Feeds ===

@router.get("/feeds")
async def list_feeds(request: Request, current_user: dict = Depends(get_current_user)):
    """列出所有 RSS 订阅源"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}
    return {"feeds": daemon._real_world.rss.list_feeds()}


@router.post("/feeds")
async def add_feed(body: FeedInput, request: Request, current_user: dict = Depends(get_current_user)):
    """添加 RSS 订阅源"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    daemon._real_world.rss.add_feed(body.url, body.name, body.category)
    return {"status": "added", "url": body.url}


@router.delete("/feeds")
async def remove_feed(url: str, request: Request, current_user: dict = Depends(get_current_user)):
    """删除 RSS 订阅源"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    daemon._real_world.rss.remove_feed(url)
    return {"status": "removed", "url": url}


# === Competitors ===

@router.get("/competitors")
async def list_competitors(request: Request, current_user: dict = Depends(get_current_user)):
    """列出所有监控的竞品"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}
    return {"competitors": daemon._real_world._competitor_urls}


@router.post("/competitors")
async def add_competitor(body: CompetitorInput, request: Request, current_user: dict = Depends(get_current_user)):
    """添加竞品监控"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    daemon._real_world.add_competitor(body.url)
    return {"status": "added", "url": body.url}


@router.delete("/competitors")
async def remove_competitor(url: str, request: Request, current_user: dict = Depends(get_current_user)):
    """删除竞品监控"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    daemon._real_world.remove_competitor(url)
    return {"status": "removed", "url": url}


# === Actions ===

@router.get("/actions")
async def list_actions(
    request: Request,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """列出所有 action"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}
    
    from app.agent.engine.action_tracker import ActionStatus
    filter_status = ActionStatus(status) if status else None
    actions = daemon._real_world.tracker.get_all(status=filter_status)
    return {
        "actions": [a.to_dict() for a in actions],
        "stats": daemon._real_world.tracker.get_stats(),
    }


@router.post("/actions/confirm")
async def confirm_action(
    body: ActionConfirmInput,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """确认执行一个 action"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    
    record = daemon._real_world.tracker.confirm(body.action_id)
    if not record:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"status": "confirmed", "action": record.to_dict()}


@router.post("/actions/complete")
async def complete_action(
    body: ActionConfirmInput,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """标记 action 已完成（附带结果 URL）"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    
    record = daemon._real_world.tracker.complete(body.action_id, body.result_url)
    if not record:
        raise HTTPException(status_code=404, detail="Action not found")
    return {"status": "completed", "action": record.to_dict()}


# === Manual Crawl ===

@router.post("/crawl")
async def manual_crawl(
    url: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """手动触发一次页面抓取"""
    daemon = _get_daemon(request)
    if not daemon:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    
    result = await daemon._real_world.crawler.crawl(url)
    # 不返回 screenshot_path（安全考虑）
    result.pop("screenshot_path", None)
    return {"result": result}

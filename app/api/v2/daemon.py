"""
CrabRes Daemon API — Control and monitor the Growth Daemon

Endpoints:
- GET  /daemon/status   — Current daemon state + pending discoveries
- POST /daemon/start    — Start the daemon (if not running)
- POST /daemon/stop     — Stop the daemon
- POST /daemon/tick     — Force a tick (manual trigger for testing)
- POST /daemon/dream    — Force a Growth Dream (memory distillation)
- GET  /daemon/discoveries — Get recent discoveries
"""

import logging
from fastapi import APIRouter, Depends, Request
from app.core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/daemon", tags=["Growth Daemon"])


def _get_daemon(request: Request):
    """Get daemon from app state"""
    daemon = getattr(request.app.state, "growth_daemon", None)
    if not daemon:
        return None
    return daemon


@router.get("/status")
async def daemon_status(request: Request, current_user: dict = Depends(get_current_user)):
    """Get daemon status, scheduler details, and pending discoveries"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"running": False, "error": "Daemon not initialized"}

    return {
        "running": daemon._running,
        "tick_interval_seconds": daemon.TICK_INTERVAL,
        "pending_discoveries": len(daemon._discoveries),
        "scheduler": daemon.scheduler_status,
    }


@router.post("/start")
async def start_daemon(request: Request, current_user: dict = Depends(get_current_user)):
    """Start the Growth Daemon"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}

    if daemon._running:
        return {"status": "already_running"}

    await daemon.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_daemon(request: Request, current_user: dict = Depends(get_current_user)):
    """Stop the Growth Daemon"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}

    await daemon.stop()
    return {"status": "stopped"}


@router.post("/tick")
async def force_tick(request: Request, current_user: dict = Depends(get_current_user)):
    """Force a daemon tick (for testing)"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}

    await daemon._scheduler.force_tick()
    discoveries = daemon.get_pending_discoveries()
    return {
        "status": "ticked",
        "discoveries_found": len(discoveries),
        "discoveries": discoveries,
        "scheduler": daemon.scheduler_status,
    }


@router.post("/dream")
async def force_dream(request: Request, current_user: dict = Depends(get_current_user)):
    """Force a Growth Dream (memory distillation)"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"error": "Daemon not initialized"}

    await daemon._scheduler.force_dream()
    return {"status": "dream_completed", "scheduler": daemon.scheduler_status}


@router.get("/discoveries")
async def get_discoveries(request: Request, current_user: dict = Depends(get_current_user)):
    """Get and clear pending discoveries"""
    daemon = _get_daemon(request)
    if not daemon:
        return {"discoveries": []}

    discoveries = daemon.get_pending_discoveries()
    return {"discoveries": discoveries, "count": len(discoveries)}

"""
CrabRes Evaluation API — Agent quality metrics
"""

import logging
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.agent.eval import get_collector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/eval", tags=["Evaluation"])


@router.get("/summary")
async def get_eval_summary(
    days: int = 7,
    current_user: dict = Depends(get_current_user),
):
    """Get evaluation metrics summary for the last N days"""
    collector = get_collector()
    return collector.get_summary(days=days)


@router.get("/health")
async def get_agent_health():
    """Quick health check — no auth required, for monitoring"""
    collector = get_collector()
    summary = collector.get_summary(days=1)
    
    # Define health thresholds
    issues = []
    if summary["sessions"] > 0:
        if summary.get("avg_tcr", 1) < 0.9:
            issues.append(f"TCR below target: {summary['avg_tcr']}")
        if summary.get("avg_ear", 1) < 0.7:
            issues.append(f"EAR below target: {summary['avg_ear']}")
        if summary.get("avg_cpt", 0) > 0.10:
            issues.append(f"CPT above budget: ${summary['avg_cpt']}")
    
    return {
        "status": "healthy" if not issues else "degraded",
        "issues": issues,
        "sessions_24h": summary["sessions"],
        "summary": summary,
    }

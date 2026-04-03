"""
CrabRes Metrics API — 系统指标暴露

GET /api/metrics → 返回 Agent/工具/专家的调用统计
"""

from fastapi import APIRouter
from app.core.metrics import get_metrics

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("")
async def system_metrics():
    """系统运行指标"""
    return get_metrics().get_report()

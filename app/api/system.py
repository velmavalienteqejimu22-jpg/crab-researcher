"""
系统状态 API - 成本监控 / 健康检查 / Dashboard联调
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.task import MonitoringResult, MonitoringTask, Report, TokenUsageLog
from app.services.cost_controller import CostController

router = APIRouter(prefix="/system", tags=["系统"])


@router.get("/health", summary="健康检查")
async def health_check(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    scheduler_status = "unknown"
    scheduler = getattr(request.app.state, "monitoring_scheduler", None)
    if scheduler:
        scheduler_status = "ok" if scheduler.get_status().get("running") else "stopped"

    overall_ok = db_status == "ok" and scheduler_status in {"ok", "unknown"}

    return {
        "status": "ok" if overall_ok else "degraded",
        "database": db_status,
        "scheduler": scheduler_status,
        "version": get_settings().APP_VERSION,
    }


@router.get("/scheduler/status", summary="调度器运行状态")
async def scheduler_status(request: Request):
    scheduler = getattr(request.app.state, "monitoring_scheduler", None)
    if not scheduler:
        return {
            "running": False,
            "message": "调度器未初始化",
            "counters": {
                "total_runs": 0,
                "total_failures": 0,
                "total_tasks_processed": 0,
                "total_alerts_sent": 0,
            },
            "recent_runs": [],
        }

    return scheduler.get_status()


@router.get("/budget", summary="查看预算使用情况")
async def get_budget(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    controller = CostController(db)
    return await controller.check_budget(current_user["user_id"])


@router.get("/stats", summary="获取系统统计")
async def get_stats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = current_user["user_id"]

    task_count = (
        await db.execute(
            select(func.count()).select_from(MonitoringTask).where(MonitoringTask.user_id == uid)
        )
    ).scalar()

    active_tasks = (
        await db.execute(
            select(func.count()).select_from(MonitoringTask).where(
                MonitoringTask.user_id == uid, MonitoringTask.status == "active"
            )
        )
    ).scalar()

    result_count = (
        await db.execute(
            select(func.count())
            .select_from(MonitoringResult)
            .join(MonitoringTask)
            .where(MonitoringTask.user_id == uid)
        )
    ).scalar()

    alerts_count = (
        await db.execute(
            select(func.count())
            .select_from(MonitoringResult)
            .join(MonitoringTask)
            .where(
                MonitoringTask.user_id == uid,
                MonitoringResult.change_detected.is_(True),
            )
        )
    ).scalar()

    report_count = (
        await db.execute(select(func.count()).select_from(Report).where(Report.user_id == uid))
    ).scalar()

    total_cost = (
        await db.execute(
            select(func.coalesce(func.sum(TokenUsageLog.cost_cny), 0.0)).where(
                TokenUsageLog.user_id == uid
            )
        )
    ).scalar()

    return {
        "tasks": {"total": task_count, "active": active_tasks},
        "monitoring": {"total_results": result_count, "alerts": alerts_count},
        "reports": {"total": report_count},
        "cost": {"total_cny": round(float(total_cost), 2)},
    }


@router.get("/dashboard/alerts", summary="Dashboard 告警列表")
async def dashboard_alerts(
    limit: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None, pattern="^(info|warning|critical)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = current_user["user_id"]

    stmt = (
        select(MonitoringResult, MonitoringTask.brand_name, MonitoringTask.platform, MonitoringTask.task_type)
        .join(MonitoringTask, MonitoringResult.task_id == MonitoringTask.id)
        .where(
            MonitoringTask.user_id == uid,
            MonitoringResult.change_detected.is_(True),
        )
        .order_by(MonitoringResult.created_at.desc())
        .limit(limit)
    )

    if severity:
        stmt = stmt.where(MonitoringResult.severity == severity)

    rows = (await db.execute(stmt)).all()

    return [
        {
            "id": result.id,
            "task_id": result.task_id,
            "brand": brand_name,
            "platform": platform,
            "task_type": task_type,
            "severity": result.severity,
            "change_type": result.change_type,
            "change_summary": result.change_summary,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }
        for result, brand_name, platform, task_type in rows
    ]


@router.get("/dashboard/price-trends", summary="Dashboard 价格趋势")
async def dashboard_price_trends(
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    uid = current_user["user_id"]
    since = datetime.utcnow() - timedelta(days=days)

    stmt = (
        select(MonitoringResult, MonitoringTask.brand_name)
        .join(MonitoringTask, MonitoringResult.task_id == MonitoringTask.id)
        .where(
            MonitoringTask.user_id == uid,
            MonitoringTask.task_type == "price",
            MonitoringResult.created_at >= since,
        )
        .order_by(MonitoringResult.created_at.asc())
    )

    rows = (await db.execute(stmt)).all()

    bucket: dict[tuple[str, str], list[float]] = defaultdict(list)
    for result, brand_name in rows:
        price = _extract_first_price(result.data)
        if price is None:
            continue
        day = result.created_at.date().isoformat() if result.created_at else ""
        if day:
            bucket[(day, brand_name)].append(price)

    series = []
    for (day, brand), prices in sorted(bucket.items(), key=lambda x: (x[0][0], x[0][1])):
        avg_price = round(sum(prices) / len(prices), 2)
        series.append(
            {
                "date": day,
                "brand": brand,
                "avg_price": avg_price,
                "samples": len(prices),
            }
        )

    return {
        "days": days,
        "points": series,
    }


def _extract_first_price(data: Optional[dict]) -> Optional[float]:
    if not data:
        return None
    products = data.get("products") if isinstance(data, dict) else None
    if not products or not isinstance(products, list):
        return None
    first = products[0] if products else None
    if not isinstance(first, dict):
        return None

    price = first.get("price")
    if isinstance(price, (int, float)):
        return float(price)

    try:
        return float(price)
    except Exception:
        return None

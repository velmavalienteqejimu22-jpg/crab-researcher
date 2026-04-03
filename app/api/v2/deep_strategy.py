"""
CrabRes Deep Strategy API — ULTRAPLAN 端点
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.agent.engine.deep_strategy import get_deep_strategy_engine

router = APIRouter(prefix="/deep-strategy", tags=["Deep Strategy"])


@router.get("/jobs")
async def list_jobs(current_user: dict = Depends(get_current_user)):
    """列出当前用户的所有深度策略任务"""
    engine = get_deep_strategy_engine()
    user_id = str(current_user.get('user_id', 'default'))
    jobs = engine.get_user_jobs(user_id)
    return {
        "jobs": [
            {
                "id": j.id,
                "request": j.request[:200],
                "status": j.status.value,
                "progress": j.progress,
                "progress_detail": j.progress_detail,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
                "expert_count": len(j.expert_outputs),
            }
            for j in jobs
        ]
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, current_user: dict = Depends(get_current_user)):
    """获取深度策略任务详情（含结果）"""
    engine = get_deep_strategy_engine()
    job = engine.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": job.id,
        "request": job.request,
        "status": job.status.value,
        "progress": job.progress,
        "progress_detail": job.progress_detail,
        "result": job.result,
        "expert_outputs": {k: v[:500] for k, v in job.expert_outputs.items()},
        "research_count": len(job.research_data),
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error": job.error,
    }

"""
CrabRes - AI Growth Strategy Agent
(formerly 小蟹研究员)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth, tasks, monitoring, reports, rag, system, competitors
from app.api.v2 import agent as agent_v2
from app.api.v2 import growth_data as growth_data_v2
from app.api.v2 import oauth as oauth_v2
from app.api.v2 import share as share_v2
from app.api.v2 import mcp as mcp_v2
from app.services.scheduler import MonitoringScheduler
from app.agent.daemon import GrowthDaemon
from app.agent.notifications import NotificationHub
from app.agent.tools import ToolRegistry
from app.agent.tools.research import WebSearchTool, ScrapeWebsiteTool, SocialSearchTool
from app.agent.memory import GrowthMemory
from app.agent.engine.llm_adapter import AgentLLM

settings = get_settings()

# 日志配置
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    scheduler = MonitoringScheduler()
    scheduler.start()
    app.state.monitoring_scheduler = scheduler

    # Growth Daemon — 后台增长引擎
    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(ScrapeWebsiteTool())
    tools.register(SocialSearchTool())
    memory = GrowthMemory(base_dir=".crabres/memory/global")
    llm = AgentLLM(budget_limit_usd=0.1)  # Daemon 预算很低

    daemon = GrowthDaemon(memory=memory, tools=tools, llm=llm, notifier=NotificationHub())
    await daemon.start()
    app.state.growth_daemon = daemon

    logging.info("🦀 CrabRes Agent Engine started!")
    yield

    await daemon.stop()
    scheduler.shutdown()
    await engine.dispose()
    logging.info("🦀 CrabRes shut down")


app = FastAPI(
    title="🦀 CrabRes API",
    description="AI Growth Strategy Agent — helps any product find its path to growth",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v1 路由（保留兼容）
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(tasks.router, prefix=settings.API_PREFIX)
app.include_router(monitoring.router, prefix=settings.API_PREFIX)
app.include_router(reports.router, prefix=settings.API_PREFIX)
app.include_router(rag.router, prefix=settings.API_PREFIX)
app.include_router(system.router, prefix=settings.API_PREFIX)
app.include_router(competitors.router, prefix=settings.API_PREFIX)

# v2 路由（Agent Engine）
app.include_router(agent_v2.router, prefix=settings.API_PREFIX)
app.include_router(growth_data_v2.router, prefix=settings.API_PREFIX)
app.include_router(oauth_v2.router, prefix=settings.API_PREFIX)
app.include_router(share_v2.router, prefix=settings.API_PREFIX)
app.include_router(mcp_v2.router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "🦀 CrabRes",
        "tagline": "AI Growth Strategy Agent",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running",
    }

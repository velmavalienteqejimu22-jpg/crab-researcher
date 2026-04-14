"""
CrabRes - AI Growth Strategy Agent
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
from app.api.v2 import skills as skills_v2
from app.api.v2 import brand as brand_v2
from app.api.v2 import creature as creature_v2
from app.api.v2 import simulate as simulate_v2
from app.api.v2 import execute as execute_v2
from app.api.v2 import demo as demo_v2
from app.api.v2 import experiments as experiments_v2
from app.api.v2 import playbooks as playbooks_v2
from app.api.v2 import metrics as metrics_v2
from app.api.v2 import deep_strategy as deep_strategy_v2
from app.api.v2 import eval as eval_v2
from app.api.v2 import daemon as daemon_v2
from app.channels.feishu_bot import router as feishu_router
from app.channels.openclaw_skill import router as openclaw_router
from app.channels.discord_bot import router as discord_router
from app.channels.telegram_bot import router as telegram_router
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

    # Growth Daemon — APScheduler 驱动的持久化增长引擎
    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(ScrapeWebsiteTool())
    tools.register(SocialSearchTool())
    memory = GrowthMemory(base_dir=".crabres/memory/global")
    llm = AgentLLM(budget_limit_usd=0.1)  # Daemon 预算很低

    daemon = GrowthDaemon(memory=memory, tools=tools, llm=llm, notifier=NotificationHub())
    await daemon.start()
    app.state.growth_daemon = daemon

    # Telegram 长轮询模式（不依赖公网 Webhook，本地开发也能用）
    from app.channels.telegram_polling import TelegramPoller
    tg_poller = TelegramPoller()
    await tg_poller.start()
    app.state.telegram_poller = tg_poller

    # Playwright 浏览器预热（后台初始化，不阻塞启动）
    import asyncio
    asyncio.create_task(_warmup_playwright())

    logging.info("🦀 CrabRes Agent Engine started!")
    yield

    await tg_poller.stop()
    await daemon.stop()
    scheduler.shutdown()
    await engine.dispose()
    logging.info("🦀 CrabRes shut down")


async def _warmup_playwright():
    """后台预热 Playwright 浏览器（首次启动较慢）"""
    try:
        from app.agent.tools.browser import _get_browser
        browser = await _get_browser()
        if browser:
            logging.info("🌐 Playwright browser warmed up")
        else:
            logging.warning("🌐 Playwright not available (install: playwright install chromium)")
    except Exception as e:
        logging.warning(f"🌐 Playwright warmup failed: {e}")


app = FastAPI(
    title="🦀 CrabRes API",
    description="AI Growth Strategy Agent — helps any product find its path to growth",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — 限制为实际前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crab-researcher.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
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
app.include_router(skills_v2.router, prefix=settings.API_PREFIX)
app.include_router(brand_v2.router, prefix=settings.API_PREFIX)
app.include_router(creature_v2.router, prefix=settings.API_PREFIX)
app.include_router(simulate_v2.router, prefix=settings.API_PREFIX)
app.include_router(execute_v2.router, prefix=settings.API_PREFIX)
app.include_router(demo_v2.router, prefix=settings.API_PREFIX)
app.include_router(experiments_v2.router, prefix=settings.API_PREFIX)
app.include_router(playbooks_v2.router, prefix=settings.API_PREFIX)
app.include_router(metrics_v2.router, prefix=settings.API_PREFIX)
app.include_router(deep_strategy_v2.router, prefix=settings.API_PREFIX)
app.include_router(eval_v2.router, prefix=settings.API_PREFIX)
app.include_router(daemon_v2.router, prefix=settings.API_PREFIX)

# 渠道路由
app.include_router(feishu_router, prefix=settings.API_PREFIX)
app.include_router(openclaw_router, prefix=settings.API_PREFIX)
app.include_router(discord_router, prefix=settings.API_PREFIX)
app.include_router(telegram_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "🦀 CrabRes",
        "tagline": "AI Growth Strategy Agent",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running",
    }

"""
数据库连接管理
- 异步 SQLAlchemy 引擎
- Session 管理
"""

import ssl

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# SSL 配置（Neon / Supabase 等云数据库需要）
_connect_args = {}
if not _is_sqlite:
    if "neon.tech" in settings.DATABASE_URL or "supabase" in settings.DATABASE_URL:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        _connect_args["ssl"] = ssl_ctx

# 异步引擎 — SQLite 不支持 pool_size/max_overflow
_engine_kwargs: dict = {"echo": settings.DEBUG}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 5
    _engine_kwargs["connect_args"] = _connect_args

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

# Session 工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ORM 基类
class Base(DeclarativeBase):
    pass


# FastAPI 依赖注入
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

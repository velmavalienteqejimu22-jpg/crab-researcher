"""
CrabRes 配置管理
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    # ========== 应用基础 ==========
    APP_NAME: str = "CrabRes"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api"

    # ========== 数据库 ==========
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/crab_researcher"
    DATABASE_URL_SYNC: str = "postgresql://postgres:password@localhost:5432/crab_researcher"
    REDIS_URL: str = "redis://localhost:6379"

    # ========== OpenRouter (主力 LLM) ==========
    OPENROUTER_API_KEY: Optional[str] = None

    # ========== 备用 LLM API Keys ==========
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    MOONSHOT_API_KEY: Optional[str] = None

    # ========== 搜索 API ==========
    TAVILY_API_KEY: Optional[str] = None
    FIRECRAWL_API_KEY: Optional[str] = None

    # ========== 消息平台（国内）==========
    WECOM_WEBHOOK_URL: Optional[str] = None
    FEISHU_WEBHOOK_URL: Optional[str] = None
    FEISHU_WEBHOOK_SECRET: Optional[str] = None

    # ========== 消息平台（海外）==========
    DISCORD_WEBHOOK_URL: Optional[str] = None
    DISCORD_BOT_TOKEN: Optional[str] = None
    SLACK_WEBHOOK_URL: Optional[str] = None
    SLACK_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_ID: Optional[str] = None

    # ========== 安全 ==========
    JWT_SECRET: str = "change-me-in-production"
    API_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ========== OAuth ==========
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None

    # ========== 成本控制 ==========
    MONTHLY_BUDGET_PER_USER: float = 100.0
    TOKEN_USAGE_ALERT_THRESHOLD: float = 0.8

    # ========== 爬虫安全白名单 ==========
    ALLOWED_SCRAPE_DOMAINS: List[str] = [
        "taobao.com", "tmall.com", "jd.com", "pdd.com", "1688.com",
        "xiaohongshu.com", "douyin.com", "weibo.com",
    ]

    ALLOWED_ACTIONS: List[str] = [
        "fetch_data", "generate_report", "send_notification", "search_rag",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()

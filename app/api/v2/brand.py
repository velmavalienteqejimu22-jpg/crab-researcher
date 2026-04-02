"""
CrabRes 品牌记忆 API

让用户配置品牌调性、约束条件，所有专家共享。
学自 Claude Code 的 CLAUDE.md 宪法 + Averi 的品牌记忆。
"""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.core.security import get_current_user
from app.agent.memory import GrowthMemory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brand", tags=["Brand Config"])


class BrandConfig(BaseModel):
    """品牌配置——注入所有专家的上下文"""
    product_name: Optional[str] = None
    product_url: Optional[str] = None
    description: Optional[str] = None
    target_audience: Optional[str] = None
    brand_tone: Optional[str] = None          # "professional but friendly" / "casual and fun"
    languages: list[str] = ["en"]             # 支持的语言
    monthly_budget: Optional[float] = None
    time_per_day: Optional[str] = None        # "30 min" / "1 hour"
    do_not_mention: list[str] = []            # 不要提及的竞品/话题
    preferred_channels: list[str] = []         # 偏好渠道
    avoid_channels: list[str] = []             # 避免渠道
    custom_rules: list[str] = []               # 自定义规则


@router.get("/config")
async def get_brand_config(current_user: dict = Depends(get_current_user)):
    """获取品牌配置"""
    user_id = current_user.get("user_id", 0)
    memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")
    config = await memory.load("brand_config", category="product")
    return {"config": config or {}}


@router.post("/config")
async def save_brand_config(
    config: BrandConfig,
    current_user: dict = Depends(get_current_user),
):
    """保存品牌配置"""
    user_id = current_user.get("user_id", 0)
    memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")

    data = config.model_dump(exclude_none=True)
    await memory.save("brand_config", data, category="product")

    # 同时更新产品信息
    product = await memory.load("product") or {}
    if config.product_name:
        product["name"] = config.product_name
    if config.product_url:
        product["url"] = config.product_url
    if config.description:
        product["description"] = config.description
    await memory.save("product", product)

    logger.info(f"Brand config saved for user {user_id}")
    return {"status": "saved", "config": data}


def get_brand_context(brand_config: dict) -> str:
    """将品牌配置转为可注入 prompt 的文本"""
    if not brand_config:
        return ""

    parts = ["\n## Brand Context (applies to ALL outputs)\n"]

    if brand_config.get("product_name"):
        parts.append(f"Product: {brand_config['product_name']}")
    if brand_config.get("description"):
        parts.append(f"Description: {brand_config['description']}")
    if brand_config.get("target_audience"):
        parts.append(f"Target audience: {brand_config['target_audience']}")
    if brand_config.get("brand_tone"):
        parts.append(f"Brand tone: {brand_config['brand_tone']}")
    if brand_config.get("languages"):
        parts.append(f"Languages: {', '.join(brand_config['languages'])}")
    if brand_config.get("monthly_budget"):
        parts.append(f"Monthly budget: ${brand_config['monthly_budget']}")
    if brand_config.get("time_per_day"):
        parts.append(f"Time available per day: {brand_config['time_per_day']}")
    if brand_config.get("do_not_mention"):
        parts.append(f"DO NOT mention: {', '.join(brand_config['do_not_mention'])}")
    if brand_config.get("preferred_channels"):
        parts.append(f"Preferred channels: {', '.join(brand_config['preferred_channels'])}")
    if brand_config.get("avoid_channels"):
        parts.append(f"Avoid channels: {', '.join(brand_config['avoid_channels'])}")
    if brand_config.get("custom_rules"):
        parts.append("Custom rules:")
        for rule in brand_config["custom_rules"]:
            parts.append(f"  - {rule}")

    return "\n".join(parts)

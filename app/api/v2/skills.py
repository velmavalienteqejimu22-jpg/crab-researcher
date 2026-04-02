"""
CrabRes Skills Marketplace API

让用户浏览、安装、创建自定义 Skill 来扩展专家能力。
学习自 Accio Work 的技能插件 + Claude Code 的 Skills 生态。
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["Skills Marketplace"])

# 内置 Skills 目录
BUILTIN_SKILLS = [
    {
        "id": "competitor-analysis",
        "name": "Competitor Analysis",
        "description": "Deep competitive landscape analysis with feature matrix, pricing comparison, and SWOT.",
        "category": "research",
        "expert": "market_researcher",
        "installs": 2000,
        "builtin": True,
    },
    {
        "id": "reddit-marketing",
        "name": "Reddit Marketing",
        "description": "Reddit-native marketing strategy with subreddit selection, post templates, and engagement rules.",
        "category": "social",
        "expert": "social_media",
        "installs": 800,
        "builtin": True,
    },
    {
        "id": "cold-outreach",
        "name": "Cold Outreach",
        "description": "Personalized cold email/DM templates for influencers, partners, and potential users.",
        "category": "partnerships",
        "expert": "partnerships",
        "installs": 1500,
        "builtin": True,
    },
    {
        "id": "pricing-psychology",
        "name": "Pricing Psychology",
        "description": "70+ psychological principles for pricing, conversion, and persuasion.",
        "category": "psychology",
        "expert": "psychologist",
        "installs": 38300,
        "builtin": True,
    },
    {
        "id": "seo-audit",
        "name": "SEO Audit",
        "description": "38-point SEO + AI search optimization audit for any URL.",
        "category": "seo",
        "expert": "content_strategist",
        "installs": 4800,
        "builtin": True,
    },
    {
        "id": "product-hunt-launch",
        "name": "Product Hunt Launch",
        "description": "Complete PH launch playbook: timeline, gallery, tagline, first comment, community prep.",
        "category": "launch",
        "expert": "partnerships",
        "installs": 8100,
        "builtin": True,
    },
    {
        "id": "growth-playbook-2026",
        "name": "2026 Growth Playbook",
        "description": "10 advanced tactics: reverse trial, embedded triggers, cold DM, MCP distribution, and more.",
        "category": "strategy",
        "expert": "product_growth",
        "installs": 500,
        "builtin": True,
    },
    {
        "id": "copywriting-master",
        "name": "Copywriting Master",
        "description": "Complete copywriting framework: AIDA, PAS, headline formulas, CTA templates, page structures.",
        "category": "content",
        "expert": "copywriter",
        "installs": 52400,
        "builtin": True,
    },
]


@router.get("/list")
async def list_skills(current_user: dict = Depends(get_current_user)):
    """列出所有可用 Skills（内置 + 用户安装的）"""
    user_id = current_user.get("user_id", 0)
    user_skills = _load_user_skills(user_id)

    return {
        "builtin": BUILTIN_SKILLS,
        "installed": user_skills,
        "total": len(BUILTIN_SKILLS) + len(user_skills),
    }


@router.get("/categories")
async def list_categories():
    """列出 Skill 类别"""
    return {
        "categories": [
            {"id": "research", "name": "Research", "count": 2},
            {"id": "social", "name": "Social Media", "count": 1},
            {"id": "partnerships", "name": "Partnerships", "count": 2},
            {"id": "psychology", "name": "Psychology", "count": 1},
            {"id": "seo", "name": "SEO", "count": 1},
            {"id": "strategy", "name": "Strategy", "count": 1},
            {"id": "content", "name": "Content", "count": 1},
            {"id": "launch", "name": "Launch", "count": 1},
        ]
    }


class CustomSkill(BaseModel):
    name: str
    description: str
    expert_id: str
    prompt: str  # 自定义 Skill 的 prompt 内容


@router.post("/create")
async def create_custom_skill(
    skill: CustomSkill,
    current_user: dict = Depends(get_current_user),
):
    """创建自定义 Skill"""
    user_id = current_user.get("user_id", 0)
    skill_id = f"custom-{skill.name.lower().replace(' ', '-')}"

    skill_data = {
        "id": skill_id,
        "name": skill.name,
        "description": skill.description,
        "expert": skill.expert_id,
        "prompt": skill.prompt,
        "custom": True,
        "author": user_id,
    }

    _save_user_skill(user_id, skill_id, skill_data)

    return {"status": "created", "skill": skill_data}


def _load_user_skills(user_id: int) -> list[dict]:
    """加载用户安装的自定义 Skills"""
    skills_dir = Path(f".crabres/skills/{user_id}")
    if not skills_dir.exists():
        return []
    skills = []
    for f in skills_dir.glob("*.json"):
        try:
            skills.append(json.loads(f.read_text()))
        except Exception:
            pass
    return skills


def _save_user_skill(user_id: int, skill_id: str, data: dict):
    """保存用户自定义 Skill"""
    skills_dir = Path(f".crabres/skills/{user_id}")
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / f"{skill_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2)
    )

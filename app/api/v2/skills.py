"""
CrabRes Skills API — Marketplace + Auto-Evolved Skills

Two types of skills:
1. BUILTIN — Hardcoded expert skills (competitor-analysis, reddit-marketing, etc.)
2. LEARNED — Auto-evolved from successful growth actions (SkillStore)

The magic: when a user's Reddit post gets 100+ upvotes, the system
automatically extracts the pattern as a reusable Skill.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app.core.security import get_current_user
from app.agent.skills import SkillStore, SkillWriter, SkillDocument

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["Skills"])

# Builtin Skills (marketplace display)
BUILTIN_SKILLS = [
    {
        "id": "competitor-analysis", "name": "Competitor Analysis",
        "description": "Deep competitive landscape analysis with feature matrix, pricing comparison, and SWOT.",
        "category": "research", "expert": "market_researcher", "installs": 2000, "builtin": True,
    },
    {
        "id": "reddit-marketing", "name": "Reddit Marketing",
        "description": "Reddit-native marketing strategy with subreddit selection, post templates, and engagement rules.",
        "category": "social", "expert": "social_media", "installs": 800, "builtin": True,
    },
    {
        "id": "cold-outreach", "name": "Cold Outreach",
        "description": "Personalized cold email/DM templates for influencers, partners, and potential users.",
        "category": "partnerships", "expert": "partnerships", "installs": 1500, "builtin": True,
    },
    {
        "id": "pricing-psychology", "name": "Pricing Psychology",
        "description": "70+ psychological principles for pricing, conversion, and persuasion.",
        "category": "psychology", "expert": "psychologist", "installs": 38300, "builtin": True,
    },
    {
        "id": "seo-audit", "name": "SEO Audit",
        "description": "38-point SEO + AI search optimization audit for any URL.",
        "category": "seo", "expert": "content_strategist", "installs": 4800, "builtin": True,
    },
    {
        "id": "product-hunt-launch", "name": "Product Hunt Launch",
        "description": "Complete PH launch playbook: timeline, gallery, tagline, first comment, community prep.",
        "category": "launch", "expert": "partnerships", "installs": 8100, "builtin": True,
    },
    {
        "id": "growth-playbook-2026", "name": "2026 Growth Playbook",
        "description": "10 advanced tactics: reverse trial, embedded triggers, cold DM, MCP distribution, and more.",
        "category": "strategy", "expert": "product_growth", "installs": 500, "builtin": True,
    },
    {
        "id": "copywriting-master", "name": "Copywriting Master",
        "description": "Complete copywriting framework: AIDA, PAS, headline formulas, CTA templates, page structures.",
        "category": "content", "expert": "copywriter", "installs": 52400, "builtin": True,
    },
]


def _get_store(user_id: int) -> SkillStore:
    return SkillStore(base_dir=f".crabres/skills/{user_id}")


@router.get("/list")
async def list_skills(current_user: dict = Depends(get_current_user)):
    """List all skills: builtin + learned + custom"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)

    learned = await store.get_all_skills()

    return {
        "builtin": BUILTIN_SKILLS,
        "learned": learned,
        "total": len(BUILTIN_SKILLS) + len(learned),
    }


@router.get("/learned")
async def list_learned_skills(current_user: dict = Depends(get_current_user)):
    """List only auto-learned skills (from successful actions)"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    skills = await store.get_all_skills()
    return {"skills": skills, "count": len(skills)}


@router.get("/learned/{skill_id}")
async def get_learned_skill(skill_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific learned skill with full details"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    skill = await store.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    from dataclasses import asdict
    return asdict(skill)


@router.get("/search")
async def search_skills(
    q: str,
    platform: str = "",
    current_user: dict = Depends(get_current_user),
):
    """Search skills by query and optional platform"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)

    # Search learned skills
    learned = await store.search_skills(q, platform=platform, top_k=5)
    from dataclasses import asdict
    learned_results = [asdict(s) for s in learned]

    # Also filter builtins
    q_lower = q.lower()
    builtin_results = [
        s for s in BUILTIN_SKILLS
        if q_lower in s["name"].lower() or q_lower in s["description"].lower()
    ]

    return {
        "learned": learned_results,
        "builtin": builtin_results,
        "total": len(learned_results) + len(builtin_results),
    }


class RecordUsageRequest(BaseModel):
    skill_id: str
    succeeded: bool = True


@router.post("/learned/{skill_id}/usage")
async def record_skill_usage(
    skill_id: str,
    req: RecordUsageRequest,
    current_user: dict = Depends(get_current_user),
):
    """Record that a skill was used (updates confidence)"""
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)
    await store.record_usage(skill_id, req.succeeded)
    return {"status": "recorded"}


class TeachSkillRequest(BaseModel):
    message: str = Field(..., description="Describe the growth approach you want to save")
    product_context: str = Field("", description="Product context for better extraction")


@router.post("/teach")
async def teach_skill(
    req: TeachSkillRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    User explicitly teaches the agent a new skill.
    
    Example: "I found that posting at 9am PST on Reddit gets 3x more upvotes"
    """
    user_id = current_user.get("user_id", 0)
    store = _get_store(user_id)

    try:
        from app.agent.engine.llm_adapter import AgentLLM
        llm = AgentLLM(budget_limit_usd=0.05)
        writer = SkillWriter(store=store, llm=llm)
        skill = await writer.synthesize_from_user_input(req.message, req.product_context)

        if skill:
            from dataclasses import asdict
            return {"status": "learned", "skill": asdict(skill)}
        else:
            return {"status": "failed", "reason": "Could not extract a reusable skill from the input"}
    except Exception as e:
        logger.error(f"Teach skill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def list_categories():
    """List skill categories"""
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

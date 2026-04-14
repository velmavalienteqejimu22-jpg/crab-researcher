"""
CrabRes Skill Evolution System — Agent learns from success

Inspired by Hermes Agent's agentskills.io:
When an action produces great results, the agent automatically
distills the experience into a reusable Skill Document.

Skill lifecycle:
1. CAPTURE  — Growth Loop logs a "great" result
2. EXTRACT  — LLM extracts the reusable pattern
3. STORE    — Skill saved as structured Markdown in .crabres/skills/
4. INDEX    — Skill indexed for semantic retrieval
5. INJECT   — Next time a similar task comes up, the skill is auto-loaded
6. EVOLVE   — If the skill is used and produces another "great", confidence++
"""

import json
import time
import logging
import hashlib
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SkillDocument:
    """A learned growth skill — reusable knowledge extracted from real execution"""
    id: str = ""
    name: str = ""
    platform: str = ""          # reddit / x / linkedin / email / etc
    action_type: str = ""       # post / reply / dm / thread / outreach
    description: str = ""       # One sentence: what this skill does
    when_to_use: str = ""       # Trigger conditions
    steps: list[str] = field(default_factory=list)    # Concrete steps
    example: str = ""           # Real example from the action that worked
    metrics: dict = field(default_factory=dict)        # What results it produced
    confidence: float = 0.5     # 0.0-1.0, increases with repeated success
    times_used: int = 0
    times_succeeded: int = 0
    created_at: float = field(default_factory=time.time)
    last_used_at: float = 0.0
    source_action_id: str = ""  # The original action that spawned this skill
    tags: list[str] = field(default_factory=list)


class SkillStore:
    """Persistent storage and retrieval for learned skills"""

    def __init__(self, base_dir: str = ".crabres/skills"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_dir / "_index.json"

    def _load_index(self) -> list[dict]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text())
            except Exception:
                return []
        return []

    def _save_index(self, index: list[dict]):
        self._index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, default=str))

    async def save_skill(self, skill: SkillDocument) -> str:
        """Save a skill document and update the index"""
        if not skill.id:
            skill.id = f"skill-{hashlib.md5(f'{skill.platform}_{skill.name}_{time.time()}'.encode()).hexdigest()[:8]}"

        # Save as JSON
        path = self.base_dir / f"{skill.id}.json"
        path.write_text(json.dumps(asdict(skill), ensure_ascii=False, indent=2, default=str))

        # Also save as human-readable Markdown (for export/sharing)
        md_path = self.base_dir / f"{skill.id}.md"
        md_content = self._skill_to_markdown(skill)
        md_path.write_text(md_content)

        # Update index
        index = self._load_index()
        # Remove old entry if exists
        index = [s for s in index if s.get("id") != skill.id]
        index.append({
            "id": skill.id,
            "name": skill.name,
            "platform": skill.platform,
            "action_type": skill.action_type,
            "description": skill.description,
            "confidence": skill.confidence,
            "tags": skill.tags,
            "times_used": skill.times_used,
        })
        self._save_index(index)

        logger.info(f"Skill saved: {skill.id} — {skill.name} (confidence: {skill.confidence:.0%})")
        return skill.id

    async def get_skill(self, skill_id: str) -> Optional[SkillDocument]:
        """Load a specific skill by ID"""
        path = self.base_dir / f"{skill_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return SkillDocument(**{k: v for k, v in data.items() if k in SkillDocument.__dataclass_fields__})
        except Exception as e:
            logger.error(f"Failed to load skill {skill_id}: {e}")
            return None

    async def search_skills(self, query: str, platform: str = "", top_k: int = 5) -> list[SkillDocument]:
        """
        Search for relevant skills based on query and platform.
        
        Uses keyword matching on index (fast) + loads full skill docs for top matches.
        Future: replace with vector similarity search.
        """
        index = self._load_index()
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for entry in index:
            score = 0.0

            # Platform match bonus
            if platform and entry.get("platform", "") == platform:
                score += 2.0

            # Name/description keyword overlap
            name_words = set(entry.get("name", "").lower().split())
            desc_words = set(entry.get("description", "").lower().split())
            tag_words = set(t.lower() for t in entry.get("tags", []))

            overlap = query_words & (name_words | desc_words | tag_words)
            score += len(overlap) * 1.5

            # Confidence bonus
            score += entry.get("confidence", 0.5) * 0.5

            # Usage bonus (proven skills rank higher)
            score += min(entry.get("times_used", 0) * 0.1, 1.0)

            if score > 0:
                scored.append((entry["id"], score))

        # Sort by score, load top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for skill_id, _ in scored[:top_k]:
            skill = await self.get_skill(skill_id)
            if skill:
                results.append(skill)

        return results

    async def record_usage(self, skill_id: str, succeeded: bool):
        """Record that a skill was used (and whether it succeeded)"""
        skill = await self.get_skill(skill_id)
        if not skill:
            return

        skill.times_used += 1
        skill.last_used_at = time.time()
        if succeeded:
            skill.times_succeeded += 1
            # Increase confidence (max 0.95)
            skill.confidence = min(0.95, skill.confidence + 0.05)
        else:
            # Decrease confidence (min 0.1)
            skill.confidence = max(0.1, skill.confidence - 0.03)

        await self.save_skill(skill)
        logger.info(f"Skill {skill_id} used (success={succeeded}, confidence={skill.confidence:.0%})")

    async def get_all_skills(self) -> list[dict]:
        """Get all skills (index only, for listing)"""
        return self._load_index()

    async def get_skills_for_prompt(self, query: str, platform: str = "") -> str:
        """
        Format relevant skills as injectable prompt text.
        
        This is what gets added to expert system prompts.
        """
        skills = await self.search_skills(query, platform, top_k=3)
        if not skills:
            return ""

        lines = ["## LEARNED SKILLS (from real execution — high confidence)"]
        for s in skills:
            lines.append(f"\n### 🎯 {s.name} (confidence: {s.confidence:.0%})")
            lines.append(f"Platform: {s.platform} | Type: {s.action_type}")
            lines.append(f"When to use: {s.when_to_use}")
            if s.steps:
                lines.append("Steps:")
                for i, step in enumerate(s.steps, 1):
                    lines.append(f"  {i}. {step}")
            if s.example:
                lines.append(f"Real example: {s.example[:200]}")
            if s.metrics:
                lines.append(f"Results: {json.dumps(s.metrics)}")

        lines.append("\nPrioritize these proven patterns over generic advice.")
        return "\n".join(lines)

    def _skill_to_markdown(self, skill: SkillDocument) -> str:
        """Convert a skill to shareable Markdown format"""
        lines = [
            f"# {skill.name}",
            "",
            f"> {skill.description}",
            "",
            f"**Platform:** {skill.platform}",
            f"**Action Type:** {skill.action_type}",
            f"**Confidence:** {skill.confidence:.0%}",
            f"**Times Used:** {skill.times_used} ({skill.times_succeeded} succeeded)",
            "",
            "## When to Use",
            skill.when_to_use,
            "",
            "## Steps",
        ]
        for i, step in enumerate(skill.steps, 1):
            lines.append(f"{i}. {step}")
        
        if skill.example:
            lines.extend(["", "## Example", skill.example])
        
        if skill.metrics:
            lines.extend(["", "## Results", json.dumps(skill.metrics, indent=2)])
        
        if skill.tags:
            lines.extend(["", f"**Tags:** {', '.join(skill.tags)}"])

        return "\n".join(lines)


class SkillWriter:
    """
    Automatically synthesize new skills from successful growth actions.
    
    Triggered when:
    - Growth Loop result verdict == "great"
    - Daemon tracks an action with high engagement
    - User says "remember this" or "save this approach"
    """

    def __init__(self, store: SkillStore, llm=None):
        self.store = store
        self.llm = llm

    async def synthesize_from_action(
        self,
        action: dict,
        result: dict,
        product_context: str = "",
    ) -> Optional[SkillDocument]:
        """
        Extract a reusable skill from a successful action+result pair.
        
        Uses LLM to generalize the specific action into a transferable pattern.
        """
        if not self.llm:
            return await self._synthesize_rule_based(action, result)

        from app.agent.engine.llm_adapter import TaskTier

        prompt = f"""Analyze this successful growth action and extract a REUSABLE skill.

## Action
- Platform: {action.get('platform', '')}
- Type: {action.get('action_type', '')}
- Description: {action.get('description', '')}
- Content: {action.get('content_preview', '')[:300]}
- URL: {action.get('url', '')}

## Result
- Metrics: {json.dumps(result.get('metrics', {}))}
- Verdict: {result.get('verdict', 'great')}
- Score: {result.get('score', 0)}/100

## Product Context
{product_context[:200]}

## Task
Extract the GENERALIZABLE pattern. Remove product-specific details.
Focus on: timing, format, tone, structure, platform mechanics that made this work.

Return JSON:
{{
  "name": "Short skill name (5 words max)",
  "description": "One sentence describing the skill",
  "when_to_use": "When should an agent use this skill?",
  "steps": ["Step 1", "Step 2", "Step 3"],
  "example": "Anonymized example of what was done",
  "tags": ["tag1", "tag2"]
}}"""

        try:
            response = await self.llm.generate(
                system_prompt="You are a growth pattern extractor. Return ONLY valid JSON.",
                messages=[{"role": "user", "content": prompt}],
                tier=TaskTier.PARSING,
                max_tokens=500,
            )

            raw = response.content
            # Extract JSON from markdown code blocks if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            data = json.loads(raw.strip())

            skill = SkillDocument(
                name=data.get("name", "Unnamed Skill"),
                platform=action.get("platform", ""),
                action_type=action.get("action_type", ""),
                description=data.get("description", ""),
                when_to_use=data.get("when_to_use", ""),
                steps=data.get("steps", []),
                example=data.get("example", ""),
                metrics=result.get("metrics", {}),
                confidence=0.6,  # First success = 60% confidence
                times_used=1,
                times_succeeded=1,
                source_action_id=action.get("id", ""),
                tags=data.get("tags", []),
            )

            skill_id = await self.store.save_skill(skill)
            logger.info(f"Skill synthesized from action {action.get('id', '')}: {skill.name}")
            return skill

        except Exception as e:
            logger.error(f"Skill synthesis via LLM failed: {e}")
            return await self._synthesize_rule_based(action, result)

    async def _synthesize_rule_based(self, action: dict, result: dict) -> Optional[SkillDocument]:
        """Fallback: create a basic skill without LLM"""
        platform = action.get("platform", "unknown")
        action_type = action.get("action_type", "post")
        metrics = result.get("metrics", {})
        
        skill = SkillDocument(
            name=f"Successful {action_type} on {platform}",
            platform=platform,
            action_type=action_type,
            description=f"A {action_type} on {platform} that produced {sum(metrics.values())} engagement",
            when_to_use=f"When creating a {action_type} on {platform}",
            steps=[
                f"Create a {action_type} similar to: {action.get('description', '')[:100]}",
                "Post during the same time window",
                "Monitor for 24-48 hours",
            ],
            example=action.get("content_preview", "")[:200],
            metrics=metrics,
            confidence=0.4,  # Lower confidence without LLM analysis
            times_used=1,
            times_succeeded=1,
            source_action_id=action.get("id", ""),
            tags=[platform, action_type],
        )

        await self.store.save_skill(skill)
        return skill

    async def synthesize_from_user_input(self, user_message: str, product_context: str = "") -> Optional[SkillDocument]:
        """
        User explicitly says "remember this" or shares a successful approach.
        Extract and store as a skill.
        """
        if not self.llm:
            return None

        from app.agent.engine.llm_adapter import TaskTier

        try:
            response = await self.llm.generate(
                system_prompt="Extract a reusable growth skill from the user's message. Return ONLY valid JSON with: name, platform, action_type, description, when_to_use, steps[], example, tags[]",
                messages=[{"role": "user", "content": f"User shared: {user_message}\n\nProduct: {product_context[:200]}"}],
                tier=TaskTier.PARSING,
                max_tokens=400,
            )

            raw = response.content
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            data = json.loads(raw.strip())
            skill = SkillDocument(
                name=data.get("name", "User-shared Skill"),
                platform=data.get("platform", "general"),
                action_type=data.get("action_type", "strategy"),
                description=data.get("description", ""),
                when_to_use=data.get("when_to_use", ""),
                steps=data.get("steps", []),
                example=data.get("example", user_message[:200]),
                confidence=0.5,
                tags=data.get("tags", ["user-shared"]),
            )

            await self.store.save_skill(skill)
            logger.info(f"Skill from user input: {skill.name}")
            return skill

        except Exception as e:
            logger.error(f"Skill synthesis from user input failed: {e}")
            return None

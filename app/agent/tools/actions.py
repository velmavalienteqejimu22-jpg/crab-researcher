"""
行动类工具 — Agent 帮用户执行增长操作

支持两种模式：
1. 生成模式：返回可直接复制粘贴的文案（所有平台）
2. 发布模式：生成文案 + 通过 API 发布到平台（目前支持 X/Twitter）
"""

import logging
from typing import Any, Optional
from . import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)


class WritePostTool(BaseTool):
    """为指定平台撰写帖子"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_post",
            description="Write a ready-to-publish social media post for a specific platform. Adapts tone, format, and length to the platform's culture. Returns the complete post text.",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "Target platform: reddit, x, linkedin, hackernews, producthunt, xiaohongshu"},
                    "topic": {"type": "string", "description": "What the post should be about"},
                    "product_name": {"type": "string", "description": "Product name to naturally mention"},
                    "tone": {"type": "string", "description": "Tone: helpful, technical, casual, professional"},
                },
                "required": ["platform", "topic"],
            },
            concurrent_safe=True,
        )

    async def execute(self, platform: str, topic: str, product_name: str = "", tone: str = "helpful") -> Any:
        # 这个工具的"执行"是返回平台规范，让 LLM 基于此写出帖子
        platform_guides = {
            "reddit": {
                "format": "Title + body text. No emojis in title. Provide genuine value before mentioning product.",
                "max_length": "10,000 chars. Sweet spot: 200-500 words.",
                "rules": "Never sound like an ad. Always disclose it's your product. Engage with comments.",
                "best_subreddits_for_tools": "r/SideProject, r/startups, r/indiehackers, r/SaaS",
            },
            "x": {
                "format": "280 chars per tweet. Use threads for longer content. First tweet is the hook.",
                "max_length": "280 chars. Thread: 5-15 tweets.",
                "rules": "Short sentences. One idea per tweet. Use line breaks for readability.",
                "hashtags": "#buildinpublic #indiehacker are safe. Max 2-3 hashtags.",
            },
            "linkedin": {
                "format": "Long-form text post. Start with a hook line. Use line breaks liberally.",
                "max_length": "3,000 chars. Sweet spot: 800-1500 words.",
                "rules": "Professional but personal. Story-driven. End with a question or CTA.",
            },
            "hackernews": {
                "format": "Show HN: [Product] — [one-line description]. Keep it technical and honest.",
                "max_length": "Title: 80 chars. Comment: be thorough and transparent.",
                "rules": "No marketing language. Be technical. Explain what's novel. Respond to every comment.",
            },
            "producthunt": {
                "format": "Tagline (60 chars) + Description (260 chars) + First comment (the story).",
                "rules": "Tagline: benefit-focused. First comment: founder story, why you built this.",
            },
            "xiaohongshu": {
                "format": "标题不超过20字，正文不超过1000字。多用emoji和分段。",
                "rules": "种草文化，真实体验分享。配图很重要。",
            },
        }

        guide = platform_guides.get(platform, {"format": "Standard post", "rules": "Be authentic"})
        return {
            "platform": platform,
            "topic": topic,
            "product": product_name,
            "tone": tone,
            "guide": guide,
            "instruction": f"Write a {platform} post about '{topic}' for product '{product_name}'. Follow the platform guide strictly. Output the COMPLETE post text ready to copy-paste.",
        }


class PublishPostTool(BaseTool):
    """实际发布帖子到平台（目前支持 X/Twitter）"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="publish_post",
            description="Actually publish a post to a platform. Currently supports X/Twitter. Requires platform API credentials. Use write_post first to draft, then publish_post to send.",
            parameters={
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "enum": ["x"], "description": "Platform to publish to"},
                    "text": {"type": "string", "description": "The exact text to publish"},
                    "reply_to_id": {"type": "string", "description": "Optional: tweet ID to reply to"},
                },
                "required": ["platform", "text"],
            },
            concurrent_safe=False,
            requires_auth=True,
        )

    async def execute(self, platform: str, text: str, reply_to_id: Optional[str] = None, **kwargs) -> Any:
        if platform == "x":
            from app.agent.tools.twitter import TwitterPostTool
            poster = TwitterPostTool()
            result = await poster.execute(text=text, reply_to_id=reply_to_id)
            return result
        else:
            return {
                "status": "unsupported",
                "platform": platform,
                "text": text,
                "note": f"Publishing to {platform} is not yet supported. The draft is preserved above — copy-paste it manually.",
            }


class WriteEmailTool(BaseTool):
    """撰写外联邮件"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_email",
            description="Write a personalized outreach email (to influencers, partners, or potential users). Returns the complete email with subject line.",
            parameters={
                "type": "object",
                "properties": {
                    "recipient_type": {"type": "string", "description": "Who: influencer, partner, potential_user, press"},
                    "recipient_name": {"type": "string", "description": "Name of the recipient"},
                    "context": {"type": "string", "description": "Why reaching out (e.g., 'they posted a video about our category')"},
                    "product_name": {"type": "string", "description": "Your product name"},
                    "offer": {"type": "string", "description": "What you're offering (free access, commission, collaboration)"},
                },
                "required": ["recipient_type", "context"],
            },
            concurrent_safe=True,
        )

    async def execute(self, recipient_type: str, context: str, recipient_name: str = "", product_name: str = "", offer: str = "") -> Any:
        templates = {
            "influencer": {
                "subject_formula": "Loved your [specific content] + quick idea",
                "structure": "1. Reference their specific content (proves you actually watched/read it). 2. Brief intro of your product (one sentence). 3. Specific offer. 4. No pressure CTA.",
                "length": "Under 150 words. 3-4 short paragraphs.",
            },
            "partner": {
                "subject_formula": "Partnership idea: [mutual benefit]",
                "structure": "1. What you admire about their work. 2. How your audiences overlap. 3. Specific partnership proposal. 4. Make it easy to say yes.",
                "length": "Under 200 words.",
            },
            "potential_user": {
                "subject_formula": "Saw your [problem] — built something that might help",
                "structure": "1. Reference their specific problem (from Reddit/forum post). 2. How your product solves it. 3. Free access offer. 4. No strings attached.",
                "length": "Under 100 words. Short and helpful.",
            },
            "press": {
                "subject_formula": "[Newsworthy angle] — [Product Name]",
                "structure": "1. Newsworthy hook. 2. What makes it different. 3. Key numbers/traction. 4. Offer exclusive or interview.",
                "length": "Under 200 words.",
            },
        }

        template = templates.get(recipient_type, templates["potential_user"])
        return {
            "recipient_type": recipient_type,
            "recipient_name": recipient_name,
            "context": context,
            "product": product_name,
            "offer": offer,
            "template": template,
            "instruction": f"Write a personalized email to {recipient_name or 'the recipient'} ({recipient_type}). Context: {context}. Follow the template structure. Output: Subject line + complete email body.",
        }


class SaveCompetitorsTool(BaseTool):
    """保存发现的竞品到记忆系统，启用 Daemon 持续追踪"""

    def __init__(self, memory=None):
        self._memory = memory

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="save_competitors",
            description="Save discovered competitors to memory for continuous monitoring by Growth Daemon. Call this after researching competitors. The Daemon will automatically track their website changes, pricing updates, and social mentions every 30 minutes.",
            parameters={
                "type": "object",
                "properties": {
                    "competitors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Competitor name"},
                                "url": {"type": "string", "description": "Competitor website URL"},
                                "description": {"type": "string", "description": "Brief description of what they do"},
                                "pricing": {"type": "string", "description": "Pricing info if known"},
                            },
                            "required": ["name"],
                        },
                        "description": "List of competitors to track",
                    },
                },
                "required": ["competitors"],
            },
            concurrent_safe=True,
        )

    async def execute(self, competitors: list, **kwargs) -> Any:
        if not self._memory:
            return {"error": "Memory not available", "competitors": competitors}

        # Load existing competitors
        existing = await self._memory.load("competitors", category="research")
        if not isinstance(existing, list):
            existing = []

        # Merge: add new, update existing (by name)
        existing_names = {c.get("name", "").lower() for c in existing}
        added = []
        updated = []

        for comp in competitors:
            name = comp.get("name", "").strip()
            if not name:
                continue

            if name.lower() in existing_names:
                # Update existing
                for i, e in enumerate(existing):
                    if e.get("name", "").lower() == name.lower():
                        existing[i].update({k: v for k, v in comp.items() if v})
                        updated.append(name)
                        break
            else:
                comp["discovered_at"] = __import__("time").time()
                comp["status"] = "active"
                existing.append(comp)
                added.append(name)

        await self._memory.save("competitors", existing, category="research")

        return {
            "status": "saved",
            "total_tracked": len(existing),
            "added": added,
            "updated": updated,
            "note": f"Growth Daemon will now monitor {len(existing)} competitors every 30 minutes for website changes, pricing updates, and social mentions.",
        }


class SubmitToDirectoryTool(BaseTool):
    """提交到 AI/产品目录"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="submit_directory",
            description="Generate submission-ready copy for AI directories and product listing sites. Returns tagline, description, and category for each directory.",
            parameters={
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "product_description": {"type": "string"},
                    "product_url": {"type": "string"},
                },
                "required": ["product_name", "product_description"],
            },
            concurrent_safe=True,
        )

    async def execute(self, product_name: str, product_description: str, product_url: str = "") -> Any:
        directories = [
            {"name": "There's An AI For That", "url": "https://theresanaiforthat.com/submit/", "tagline_limit": 60, "desc_limit": 500},
            {"name": "Futurepedia", "url": "https://www.futurepedia.io/submit-tool", "tagline_limit": 80, "desc_limit": 300},
            {"name": "Product Hunt", "url": "https://www.producthunt.com/posts/new", "tagline_limit": 60, "desc_limit": 260},
            {"name": "AI Tools List", "url": "https://aitoolslist.io/submit/", "tagline_limit": 100, "desc_limit": 500},
            {"name": "ToolPilot", "url": "https://www.toolpilot.ai/submit", "tagline_limit": 80, "desc_limit": 400},
            {"name": "SaaS AI Tools", "url": "https://saasaitools.com/submit/", "tagline_limit": 80, "desc_limit": 500},
        ]

        return {
            "product": product_name,
            "description": product_description,
            "url": product_url,
            "directories": directories,
            "instruction": f"For each directory, write a tailored tagline (within char limit) and description. Make each one unique — don't just copy-paste the same text.",
        }


class SetActiveCampaignTool(BaseTool):
    """设置当前活跃的增长战役（如推文链接）"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="set_active_campaign",
            description="Set the current active growth campaign URL (e.g., a Tweet link, Reddit post, or Launch page). This will be pinned to the dashboard for live tracking.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the campaign (e.g., https://x.com/user/status/123)"},
                    "name": {"type": "string", "description": "Short name for the campaign", "default": "Global Launch Post"},
                },
                "required": ["url"],
            },
            concurrent_safe=True,
        )

    async def execute(self, url: str, name: str = "Global Launch Post") -> Any:
        # 这个工具在 Loop 中被调用时，状态由 loop.memory 管理
        # 我们返回指令让 Loop 逻辑去更新 memory
        return {
            "status": "pending_save",
            "url": url,
            "name": name,
            "instruction": f"Save this campaign to growth memory: {name} at {url}",
        }

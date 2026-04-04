"""
CrabRes Channel Playbook Engine — 知识驱动的具体建议

ChatGPT 说 "try Reddit" → CrabRes 说 "r/SaaS, 周二 9am, 数字标题, 这个模板"
不靠 LLM，代码直接基于产品类型输出具体 SOP。
"""


PRODUCT_CHANNEL_MAP = {
    "saas": ["reddit", "x_twitter", "product_hunt"],
    "tool": ["reddit", "x_twitter", "product_hunt"],
    "consumer_app": ["x_twitter", "xiaohongshu", "tiktok"],
    "ecommerce": ["xiaohongshu", "instagram", "tiktok"],
    "game": ["reddit", "x_twitter", "tiktok"],
    "lifestyle": ["xiaohongshu", "instagram", "x_twitter"],
    "education": ["x_twitter", "youtube", "reddit"],
    "content": ["x_twitter", "reddit", "youtube"],
    "default": ["reddit", "x_twitter", "product_hunt"],
}

CHANNEL_SOPS = {
    "reddit": {
        "name": "Reddit",
        "why": "Posts get indexed by Google for 6-24 months. One good post = passive leads for half a year.",
        "quick_start": [
            "Find 3-5 target subreddits (search: site:reddit.com + your keywords)",
            "Spend 1 week commenting helpfully — zero product mentions",
            "First post format: 'I [did X]. Here's what happened.' — experience share, not promo",
            "Titles with numbers get 3x more engagement (from real experiment data)",
            "Post during US East 9am-12pm. First 10 upvotes = weight of next 100",
            "Links in comments, never in main post",
        ],
        "template_title": "I spent [X weeks] building [product type]. Here's what I learned about [topic].",
        "template_body": "Share your real experience in 300-500 words. Last paragraph naturally mentions what you built. No hard sell.",
        "good_metrics": ">20 upvotes, >5 comments",
        "great_metrics": ">100 upvotes",
        "dont": ["New account posting product links", "Same link to multiple subreddits", "Engagement pods"],
    },
    "x_twitter": {
        "name": "X (Twitter)",
        "why": "Algorithm weights: Reply(+2x) > Quote(+1.5x) > Retweet(+1x) > Like(+1x). One quality reply = 2 likes.",
        "quick_start": [
            "Week 1: Reply Guy strategy — reply to 10-20 niche influencers within 30 min of their posts",
            "Replies must add value: data, personal experience, contrarian take (not 'great point!')",
            "Week 2: Start original content — 40% teaching, 25% behind-scenes, 20% engagement, 15% promo",
            "1 Thread/week: Hook tweet + 5-12 value tweets + CTA tweet",
            "Hook formula: 'I [achievement with number]. Here's [N] things that actually worked:'",
            "Put links in reply, not main tweet (algorithm penalizes external links)",
            "Space posts 2-4 hours apart (author diversity penalty)",
        ],
        "template_title": "I [specific achievement]. Here's what nobody tells you:",
        "template_body": "Thread format: 1 idea per tweet, short sentences, screenshots break up text. Last tweet: 'Follow for more [topic]. Building [product] — link in reply.'",
        "good_metrics": ">10 likes, >3 replies",
        "great_metrics": ">50 likes per tweet, >200 on thread",
        "dont": [">5 posts without spacing", ">2 hashtags", "Deleting tweets", "Getting blocked (-10x each)"],
    },
    "xiaohongshu": {
        "name": "Xiaohongshu (Red Note)",
        "why": "Search traffic is huge. One good post can get recommendations for over a year. Formula: 1 follow = 1 comment + 1 share.",
        "quick_start": [
            "Day 1-2: Don't post. Search industry keywords, browse 30min x3. Build account profile.",
            "Day 3: Check if Discover feed shows your niche (3/10 = success) → update profile → first post",
            "Day 4-7: Post 1-2 quality pieces daily. 10 posts in 7 days. NO marketing content.",
            "Cover: 3:4 vertical, text overlay = post essence. Cover decides 70% of click rate.",
            "Title: 20 chars with keywords. Formats: numbers / question / contrast / reverse",
            "Body: 600-800 chars. First 10 posts MUST be quality. Copy competitors' proven formats first.",
            "Title finding method: Search / Ride trends / Study / Copy (搜蹭学抄)",
        ],
        "template_title": "[Number] ways to [outcome] in [field], #[N] is incredible",
        "template_body": "3:4 cover with big text + clean background. 600-800 chars body. Personal tone.",
        "good_metrics": "Level 4: 2K-20K views",
        "great_metrics": "Level 5: 20K-100K views",
        "dont": ["Contact info anywhere", "Reposting others' images", "Marketing in first 7 days", "Keyword stuffing"],
    },
    "product_hunt": {
        "name": "Product Hunt",
        "why": "One-time launch event. Can bring 100-1000 initial users + long-term SEO value.",
        "quick_start": [
            "2 weeks before: Build 200+ supporter email list",
            "Prepare: 5 screenshots + 1 demo video (30-60s) + tagline (60 chars, benefit-focused)",
            "Find a Hunter (someone with 1000+ followers to submit for you)",
            "Launch Tuesday 12:01 AM PST (highest traffic day)",
            "First comment ready immediately: founder story + ask for feedback",
            "Reply to EVERY comment within 1 hour (PH algorithm = velocity-based)",
            "Simultaneous blast: X thread + LinkedIn + email + Discord/Slack",
        ],
        "template_title": "[Product] — [one-sentence benefit]",
        "template_body": "First comment: 'Hey! I'm [name], I built this because [personal story]. Would love your feedback — what's one thing you'd change?'",
        "good_metrics": "Top 10 of the day",
        "great_metrics": "Top 5, Product of the Day",
        "dont": ["Launching without supporter list", "Not replying to comments", "Launching on weekend"],
    },
}


def get_channels_for_product(product_type: str) -> list[str]:
    """获取产品类型推荐的渠道列表"""
    return PRODUCT_CHANNEL_MAP.get(product_type, PRODUCT_CHANNEL_MAP["default"])


def get_channel_sop(channel: str) -> dict:
    """获取某渠道的完整 SOP"""
    return CHANNEL_SOPS.get(channel, {})


def get_actionable_advice(product_type: str, budget: str = "") -> str:
    """
    基于产品类型生成具体的、可执行的渠道建议文本
    
    这段文本可以直接注入到 LLM 的 prompt 中，让它的输出更具体。
    也可以直接作为输出的一部分给用户。
    """
    channels = get_channels_for_product(product_type)
    no_budget = not budget or budget in ("0", "$0", "none", "no", "zero")

    parts = []
    for ch_key in channels[:3]:
        sop = CHANNEL_SOPS.get(ch_key)
        if not sop:
            continue

        lines = [f"### {sop['name']}"]
        lines.append(f"**Why**: {sop['why']}")
        lines.append("**This week:**")
        for task in sop["quick_start"][:4]:
            lines.append(f"  - {task}")
        lines.append(f"**Post template**: {sop['template_title']}")
        lines.append(f"**Good**: {sop['good_metrics']} | **Great**: {sop['great_metrics']}")
        if sop.get("dont"):
            lines.append(f"**Don't**: {', '.join(sop['dont'][:2])}")
        parts.append("\n".join(lines))

    header = "## Recommended channels" if not no_budget else "## Recommended channels ($0 budget — organic only)"
    return header + "\n\n" + "\n\n".join(parts)

"""
研究类工具 — Agent 的眼睛

Tavily 为主力搜索（专为 AI Agent 设计），httpx 做网页抓取。
"""

import logging
from typing import Any
import httpx
from app.core.config import get_settings
from . import BaseTool, ToolDefinition

settings = get_settings()
logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"


class WebSearchTool(BaseTool):
    """搜索互联网 — 用 Tavily API"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description="Search the internet for current information. Use for: finding competitors, market data, industry trends, user discussions, news. Returns structured results with titles, URLs and content snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query in English for best results"},
                    "num_results": {"type": "integer", "default": 5, "description": "Number of results (1-10)"},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic",
                                     "description": "basic=fast, advanced=deeper research"},
                },
                "required": ["query"],
            },
            concurrent_safe=True,
        )

    async def execute(self, query: str, num_results: int = 5, search_depth: str = "basic") -> Any:
        if not settings.TAVILY_API_KEY or settings.TAVILY_API_KEY.startswith('填'):
            # Fallback: 没有 Tavily key 时用简单 httpx 搜索
            return await self._fallback_search(query)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(TAVILY_URL, json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": min(num_results, 10),
                    "include_answer": True,
                    "include_raw_content": False,
                })
                resp.raise_for_status()
                data = resp.json()

                results = []
                for r in data.get("results", []):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500],
                        "score": r.get("score", 0),
                    })

                return {
                    "query": query,
                    "answer": data.get("answer", ""),
                    "results": results,
                    "count": len(results),
                }
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return await self._fallback_search(query)

    async def _fallback_search(self, query: str) -> dict:
        """无 Tavily key 时的降级方案"""
        return {
            "query": query,
            "answer": "",
            "results": [],
            "count": 0,
            "note": "Search API not configured. Set TAVILY_API_KEY in .env for real search results.",
        }


class ScrapeWebsiteTool(BaseTool):
    """抓取并分析网页内容"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="scrape_website",
            description="Fetch and extract content from a URL. Use for: analyzing competitor websites, reading product pages, extracting pricing info, checking landing pages.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to scrape"},
                    "extract": {"type": "string", "description": "What to extract (e.g., pricing, features, team size)"},
                },
                "required": ["url"],
            },
            concurrent_safe=True,
            result_budget=30_000,
        )

    async def execute(self, url: str, extract: str = "") -> Any:
        try:
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={"User-Agent": "CrabRes/2.0 (growth research agent)"}
            ) as client:
                resp = await client.get(url)

                # 提取文本内容（简单的 HTML→text）
                text = resp.text
                # 去掉 script/style 标签内容
                import re
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

                # 截断
                content = text[:self.definition.result_budget]

                return {
                    "url": url,
                    "status": resp.status_code,
                    "title": _extract_title(resp.text),
                    "content_length": len(text),
                    "content_preview": content[:3000],
                    "extract_hint": extract,
                }
        except Exception as e:
            return {"url": url, "error": str(e)}


class SocialSearchTool(BaseTool):
    """搜索社媒平台上的讨论 — 用 Tavily 限定域名"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="social_search",
            description="Search social media platforms for discussions about a topic. Searches Reddit, X/Twitter, HackerNews, ProductHunt. Use for: finding target users, understanding pain points, discovering communities.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic to search for"},
                    "platforms": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["reddit", "x", "hackernews", "producthunt", "linkedin"]},
                        "default": ["reddit", "hackernews"],
                        "description": "Which platforms to search",
                    },
                },
                "required": ["query"],
            },
            concurrent_safe=True,
        )

    async def execute(self, query: str, platforms: list[str] | None = None) -> Any:
        platforms = platforms or ["reddit", "hackernews"]

        domain_map = {
            "reddit": "reddit.com",
            "x": "x.com OR twitter.com",
            "hackernews": "news.ycombinator.com",
            "producthunt": "producthunt.com",
            "linkedin": "linkedin.com",
        }

        domains = " OR ".join(f"site:{domain_map[p]}" for p in platforms if p in domain_map)
        full_query = f"{query} {domains}"

        if not settings.TAVILY_API_KEY or settings.TAVILY_API_KEY.startswith('填'):
            return {"query": query, "platforms": platforms, "results": [],
                    "note": "Set TAVILY_API_KEY for real results"}

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(TAVILY_URL, json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": full_query,
                    "search_depth": "basic",
                    "max_results": 8,
                    "include_answer": True,
                })
                resp.raise_for_status()
                data = resp.json()

                results = []
                for r in data.get("results", []):
                    # 识别来源平台
                    source = "other"
                    url = r.get("url", "")
                    for p, domain in domain_map.items():
                        if any(d in url for d in domain.replace(" OR ", ",").split(",")):
                            source = p
                            break

                    results.append({
                        "title": r.get("title", ""),
                        "url": url,
                        "content": r.get("content", "")[:400],
                        "platform": source,
                    })

                return {
                    "query": query,
                    "platforms": platforms,
                    "answer": data.get("answer", ""),
                    "results": results,
                    "count": len(results),
                }
        except Exception as e:
            logger.error(f"Social search failed: {e}")
            return {"query": query, "platforms": platforms, "results": [], "error": str(e)}


class CompetitorAnalyzeTool(BaseTool):
    """深度分析一个竞品 — 抓取网站 + 搜索信息"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="competitor_analyze",
            description="Deep analysis of a competitor: product, pricing, features, traffic sources, social presence, reviews. Requires competitor URL. Combines web scraping and search.",
            parameters={
                "type": "object",
                "properties": {
                    "competitor_url": {"type": "string", "description": "Competitor website URL"},
                    "competitor_name": {"type": "string", "description": "Competitor name"},
                },
                "required": ["competitor_url"],
            },
            concurrent_safe=True,
            result_budget=30_000,
        )

    async def execute(self, competitor_url: str, competitor_name: str = "") -> Any:
        import asyncio

        scraper = ScrapeWebsiteTool()
        searcher = WebSearchTool()
        social = SocialSearchTool()

        name = competitor_name or competitor_url.split("//")[-1].split("/")[0]

        # 并行执行 3 个研究任务
        website_task = scraper.execute(url=competitor_url, extract="pricing, features, team, target audience")
        search_task = searcher.execute(query=f"{name} reviews pricing features competitors", num_results=5)
        social_task = social.execute(query=f"{name} review", platforms=["reddit", "hackernews"])

        website_data, search_data, social_data = await asyncio.gather(
            website_task, search_task, social_task,
            return_exceptions=True,
        )

        return {
            "competitor": name,
            "url": competitor_url,
            "website": website_data if not isinstance(website_data, Exception) else {"error": str(website_data)},
            "search_results": search_data if not isinstance(search_data, Exception) else {"error": str(search_data)},
            "social_mentions": social_data if not isinstance(social_data, Exception) else {"error": str(social_data)},
        }


def _extract_title(html: str) -> str:
    """从 HTML 提取 title"""
    import re
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""

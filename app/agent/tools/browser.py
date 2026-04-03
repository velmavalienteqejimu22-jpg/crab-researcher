"""
CrabRes Browser Tool — Agent 的眼睛升级

让 Agent 能"看到"网页：
- 截图（分析竞品落地页设计）
- JS 渲染后的内容提取（SPA/动态页面）
- 页面元数据（title, meta, OG tags）
- 移动端截图（检查响应式）

这是 Manus 的核心能力之一。
比 httpx 抓取强在：能处理 JS 渲染、能截图、能看到真实布局。
"""

import asyncio
import base64
import logging
from typing import Any, Optional
from pathlib import Path

from app.agent.tools import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)

# Playwright 延迟导入（不是所有环境都装了）
_playwright = None
_browser = None


async def _get_browser():
    """延迟初始化 Playwright browser（单例）"""
    global _playwright, _browser
    if _browser:
        return _browser

    try:
        from playwright.async_api import async_playwright
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        logger.info("Playwright browser initialized")
        return _browser
    except Exception as e:
        logger.warning(f"Playwright not available: {e}")
        return None


class BrowseWebsiteTool(BaseTool):
    """
    浏览网页——截图 + JS 渲染内容提取
    
    比 scrape_website（httpx）强在：
    - 能处理 SPA/JS 渲染页面
    - 能截图（Agent 能"看到"页面设计）
    - 能提取渲染后的完整 DOM
    """

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browse_website",
            description="Open a URL in a real browser, take a screenshot, and extract rendered content. Use for: analyzing competitor landing pages, checking product pages, seeing how websites look on mobile. More powerful than scrape_website — handles JavaScript-rendered pages.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to browse"},
                    "screenshot": {"type": "boolean", "description": "Take a screenshot", "default": True},
                    "mobile": {"type": "boolean", "description": "Emulate mobile device", "default": False},
                    "wait_seconds": {"type": "integer", "description": "Wait N seconds for page to load", "default": 3},
                },
                "required": ["url"],
            },
            concurrent_safe=False,  # 浏览器不并发
            result_budget=30_000,
        )

    async def execute(self, url: str, screenshot: bool = True, mobile: bool = False, wait_seconds: int = 3) -> Any:
        browser = await _get_browser()
        if not browser:
            # 降级到普通 scrape
            from app.agent.tools.research import ScrapeWebsiteTool
            logger.info("Playwright not available, falling back to httpx scrape")
            fallback = ScrapeWebsiteTool()
            result = await fallback.execute(url=url)
            result["note"] = "Rendered with httpx (Playwright not available). No screenshot."
            return result

        page = None
        try:
            context_options = {}
            if mobile:
                context_options = {
                    "viewport": {"width": 375, "height": 812},
                    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
                    "device_scale_factor": 3,
                    "is_mobile": True,
                }
            else:
                context_options = {
                    "viewport": {"width": 1280, "height": 800},
                }

            context = await browser.new_context(**context_options)
            page = await context.new_page()

            # 导航
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(wait_seconds * 1000)

            # 提取内容
            title = await page.title()
            
            # 提取元数据
            meta = await page.evaluate("""() => {
                const metas = {};
                document.querySelectorAll('meta').forEach(m => {
                    const name = m.getAttribute('name') || m.getAttribute('property') || '';
                    const content = m.getAttribute('content') || '';
                    if (name && content) metas[name] = content;
                });
                return metas;
            }""")

            # 提取可见文本（去掉 script/style）
            text_content = await page.evaluate("""() => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                return clone.innerText.substring(0, 15000);
            }""")

            # 提取链接
            links = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({text: a.innerText.trim().substring(0, 50), href: a.href}))
                    .filter(l => l.text && l.href.startsWith('http'))
                    .slice(0, 20);
            }""")

            result = {
                "url": url,
                "title": title,
                "meta": meta,
                "content_preview": text_content[:5000],
                "content_length": len(text_content),
                "links_count": len(links),
                "links": links[:10],
                "rendered": True,
                "mobile": mobile,
            }

            # 截图
            if screenshot:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")
                # 存到 workspace
                workspace = Path(".crabres/workspace/assets")
                workspace.mkdir(parents=True, exist_ok=True)
                import hashlib
                filename = f"screenshot_{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
                filepath = workspace / filename
                filepath.write_bytes(screenshot_bytes)
                result["screenshot_path"] = str(filepath)
                result["screenshot_size"] = len(screenshot_bytes)
                # Base64 缩略（给 Agent 看的描述）
                result["screenshot_note"] = f"Screenshot saved: {filepath} ({len(screenshot_bytes)//1024}KB)"

            await context.close()
            logger.info(f"Browse {url}: title='{title[:50]}', {len(text_content)} chars, screenshot={'yes' if screenshot else 'no'}")
            return result

        except Exception as e:
            if page:
                try:
                    await page.context.close()
                except Exception:
                    pass
            logger.error(f"Browse failed for {url}: {e}")
            # 降级
            from app.agent.tools.research import ScrapeWebsiteTool
            fallback = ScrapeWebsiteTool()
            result = await fallback.execute(url=url)
            result["browse_error"] = str(e)[:200]
            result["note"] = "Playwright failed, fell back to httpx scrape"
            return result

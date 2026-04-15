"""
CrabRes Browser Tool — Agent 的眼睛

三级降级策略（适应 Render 512MB 内存限制）：
1. Jina Reader API（免费、无需本地浏览器、支持 JS 渲染、返回 Markdown）
2. Playwright/Patchright（本地开发用，能截图）
3. httpx 直接抓取（最后兜底）

为什么不在 Render 上用 Chromium：
- Chromium 进程需要 200-300MB 内存
- Render 免费版只有 512MB
- Python + uvicorn + patchright 已占 150MB+
- 启动 Chromium 就 OOM 或极慢（45s+ 超时）
"""

import asyncio
import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx

from app.agent.tools import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)


class BrowseWebsiteTool(BaseTool):
    """
    浏览网页 — 三级降级策略
    
    Level 1: Jina Reader API（推荐，免费，支持 JS 渲染）
    Level 2: Playwright（本地开发，能截图）
    Level 3: httpx 直接抓取（兜底）
    """

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browse_website",
            description="Open a URL and extract rendered content. Handles JavaScript-rendered pages. "
                        "Use for: analyzing competitor landing pages, checking product pages, extracting page content. "
                        "Returns: page title, rendered text content, links, metadata.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to browse"},
                    "screenshot": {"type": "boolean", "description": "Take a screenshot (only works with local Playwright)", "default": False},
                    "mobile": {"type": "boolean", "description": "Emulate mobile device", "default": False},
                },
                "required": ["url"],
            },
            concurrent_safe=True,  # Jina Reader 是 HTTP API，可以并发
            result_budget=30_000,
        )

    async def execute(self, url: str, screenshot: bool = False, mobile: bool = False, **kwargs) -> Any:
        """三级降级执行"""
        # Level 1: Jina Reader API（免费、快速、支持 JS）
        result = await self._try_jina_reader(url)
        if result and not result.get("error"):
            result["engine"] = "jina_reader"
            logger.info(f"Browse {url}: Jina Reader success, {result.get('content_length', 0)} chars")
            return result

        # Level 2: 本地 Playwright（仅在有 PLAYWRIGHT_ENABLED=1 或本地开发时尝试）
        if os.environ.get("PLAYWRIGHT_ENABLED") == "1" or os.environ.get("LOCAL_DEV") == "1":
            result = await self._try_playwright(url, screenshot=screenshot, mobile=mobile)
            if result and not result.get("error"):
                result["engine"] = "playwright"
                logger.info(f"Browse {url}: Playwright success, {result.get('content_length', 0)} chars")
                return result

        # Level 3: httpx 直接抓取
        result = await self._try_httpx(url)
        if result and not result.get("error"):
            result["engine"] = "httpx"
            logger.info(f"Browse {url}: httpx fallback, {result.get('content_length', 0)} chars")
            return result

        return {"error": f"All browse methods failed for {url}", "url": url}

    async def _try_jina_reader(self, url: str) -> Optional[dict]:
        """
        Jina Reader API — 免费的 JS 渲染 + Markdown 提取
        
        文档: https://jina.ai/reader/
        - 免费层: 无需 API Key，有速率限制
        - 自动处理 JS 渲染
        - 返回 Markdown 格式的页面内容
        - 支持截图（通过 X-Return-Format: screenshot）
        """
        try:
            jina_url = f"https://r.jina.ai/{url}"
            headers = {
                "Accept": "application/json",
                "X-Return-Format": "markdown",
                "X-With-Links": "true",
            }
            
            # 如果有 Jina API Key，使用它（提高速率限制）
            jina_key = os.environ.get("JINA_API_KEY", "")
            if jina_key:
                headers["Authorization"] = f"Bearer {jina_key}"

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(jina_url, headers=headers)
                
                if resp.status_code != 200:
                    logger.debug(f"Jina Reader returned {resp.status_code} for {url}")
                    return None

                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
                
                if data and data.get("code") == 200:
                    content = data.get("data", {})
                    text = content.get("content", "")
                    title = content.get("title", "")
                    description = content.get("description", "")
                    
                    # 提取链接
                    links = []
                    for link in content.get("links", {}).items() if isinstance(content.get("links"), dict) else []:
                        links.append({"text": link[0][:50], "href": link[1]})
                    
                    # 保存到 workspace（作为文本文件，不需要截图）
                    workspace = self._get_workspace_path()
                    filename = f"browse_{hashlib.md5(url.encode()).hexdigest()[:8]}.md"
                    filepath = workspace / filename
                    filepath.write_text(f"# {title}\n\n{text[:10000]}", encoding="utf-8")
                    
                    return {
                        "url": url,
                        "title": title,
                        "description": description,
                        "content_preview": text[:5000],
                        "content_length": len(text),
                        "links": links[:15],
                        "links_count": len(links),
                        "rendered": True,
                        "browse_file": str(filepath),
                    }
                else:
                    # Jina 返回的不是 JSON，可能是纯文本 Markdown
                    text = resp.text
                    if text and len(text) > 50:
                        # 从 Markdown 中提取标题
                        title = ""
                        for line in text.split("\n"):
                            if line.startswith("# "):
                                title = line[2:].strip()
                                break
                        
                        workspace = self._get_workspace_path()
                        filename = f"browse_{hashlib.md5(url.encode()).hexdigest()[:8]}.md"
                        filepath = workspace / filename
                        filepath.write_text(f"# {title or url}\n\n{text[:10000]}", encoding="utf-8")
                        
                        return {
                            "url": url,
                            "title": title or url,
                            "content_preview": text[:5000],
                            "content_length": len(text),
                            "links": [],
                            "links_count": 0,
                            "rendered": True,
                            "browse_file": str(filepath),
                        }
                    return None

        except httpx.TimeoutException:
            logger.debug(f"Jina Reader timeout for {url}")
            return None
        except Exception as e:
            logger.debug(f"Jina Reader failed for {url}: {e}")
            return None

    async def _try_playwright(self, url: str, screenshot: bool = True, mobile: bool = False) -> Optional[dict]:
        """Playwright 浏览器 — 仅本地开发使用"""
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            return None

        pw = None
        browser = None
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                      '--single-process', '--no-zygote'],
            )

            context_opts = (
                {"viewport": {"width": 375, "height": 812}, "is_mobile": True}
                if mobile else {"viewport": {"width": 1280, "height": 800}}
            )
            context = await browser.new_context(**context_opts)
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            title = await page.title()
            text_content = await page.evaluate("""() => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
                return clone.innerText.substring(0, 15000);
            }""")
            meta = await page.evaluate("""() => {
                const metas = {};
                document.querySelectorAll('meta').forEach(m => {
                    const name = m.getAttribute('name') || m.getAttribute('property') || '';
                    const content = m.getAttribute('content') || '';
                    if (name && content) metas[name] = content;
                });
                return metas;
            }""")
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
                "links": links[:10],
                "links_count": len(links),
                "rendered": True,
                "mobile": mobile,
            }

            # 截图
            if screenshot:
                screenshot_bytes = await page.screenshot(full_page=False, type="png")
                workspace = self._get_workspace_path()
                filename = f"screenshot_{hashlib.md5(url.encode()).hexdigest()[:8]}.png"
                filepath = workspace / filename
                filepath.write_bytes(screenshot_bytes)
                result["screenshot_path"] = str(filepath)
                result["screenshot_base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")[:200] + "..."

            await context.close()
            return result

        except Exception as e:
            logger.debug(f"Playwright failed for {url}: {e}")
            return None
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    await pw.stop()
                except Exception:
                    pass

    async def _try_httpx(self, url: str) -> Optional[dict]:
        """httpx 直接抓取 — 最后兜底"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text

                # 简单提取
                import re
                title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else url

                # 去掉 script/style
                text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()

                # 提取 meta
                meta = {}
                for m in re.finditer(r'<meta\s+(?:name|property)=["\']([^"\']+)["\'].*?content=["\']([^"\']*)["\']', html, re.IGNORECASE):
                    meta[m.group(1)] = m.group(2)

                # 提取链接
                links = []
                for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
                    href = m.group(1)
                    link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                    if href.startswith("http") and link_text:
                        links.append({"text": link_text[:50], "href": href})

                return {
                    "url": url,
                    "title": title,
                    "meta": meta,
                    "content_preview": text[:5000],
                    "content_length": len(text),
                    "links": links[:10],
                    "links_count": len(links),
                    "rendered": False,  # httpx 不渲染 JS
                    "note": "Fetched with httpx (no JS rendering)",
                }

        except Exception as e:
            logger.debug(f"httpx failed for {url}: {e}")
            return None

    def _get_workspace_path(self) -> Path:
        """获取 workspace 路径（支持持久化）"""
        render_disk = os.environ.get("RENDER_DISK_PATH", "")
        if render_disk:
            workspace = Path(render_disk) / "workspace" / "assets"
        else:
            workspace = Path(".crabres/memory/workspace/assets")
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

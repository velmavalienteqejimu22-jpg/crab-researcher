"""
CrabRes Browser Crawler — Playwright 驱动的真实爬虫

解决的核心问题：
- 之前 BrowseWebsiteTool 只能 httpx 拉 HTML（JS 渲染的内容全丢）
- 现在用 Playwright 真实渲染页面，能看到 SPA、动态加载的内容

能力：
1. 抓取竞品首页 + 定价页 + 功能页
2. 截图存档（用于变化检测）
3. 提取结构化数据（标题、描述、定价、特性列表）
4. 检测页面变化（与上次抓取对比）
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 抓取结果存储目录
CRAWL_DIR = Path(".crabres/crawl")
CRAWL_DIR.mkdir(parents=True, exist_ok=True)


class BrowserCrawler:
    """
    真实浏览器爬虫 — Daemon 的"眼睛"

    用法：
        crawler = BrowserCrawler()
        result = await crawler.crawl("https://competitor.com")
        changes = await crawler.detect_changes("https://competitor.com")
    """

    def __init__(self):
        self._browser = None
        self._context = None

    async def _ensure_browser(self):
        """确保浏览器实例存在"""
        if self._browser and self._browser.is_connected():
            return

        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            self._browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            logger.info("🌐 BrowserCrawler: Playwright browser ready")
        except Exception as e:
            logger.error(f"🌐 BrowserCrawler: failed to start browser: {e}")
            raise

    async def crawl(self, url: str, screenshot: bool = True, timeout: int = 30) -> dict:
        """
        抓取单个页面

        返回：
        {
            "url": "https://...",
            "title": "...",
            "description": "...",
            "text_content": "...",  # 纯文本（去掉 HTML）
            "content_hash": "abc123",  # 用于变化检测
            "screenshot_path": ".crabres/crawl/...",
            "crawled_at": 1234567890,
            "features": [...],  # 提取的特性列表
            "pricing": {...},  # 提取的定价信息
        }
        """
        await self._ensure_browser()

        page = await self._context.new_page()
        result = {
            "url": url,
            "crawled_at": time.time(),
            "error": None,
        }

        try:
            # 导航到页面
            response = await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            result["status_code"] = response.status if response else None

            # 等待页面完全加载
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)  # 额外等待动态内容

            # 提取基础信息
            result["title"] = await page.title()
            result["description"] = await page.evaluate("""
                () => {
                    const meta = document.querySelector('meta[name="description"]');
                    return meta ? meta.content : '';
                }
            """)

            # 提取纯文本内容
            result["text_content"] = await page.evaluate("""
                () => {
                    // 移除脚本和样式
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(s => s.remove());
                    return document.body.innerText.trim().substring(0, 10000);
                }
            """)

            # 内容哈希（用于变化检测）
            result["content_hash"] = hashlib.md5(
                result["text_content"].encode()
            ).hexdigest()

            # 提取特性列表（常见的 feature list 模式）
            result["features"] = await page.evaluate("""
                () => {
                    const features = [];
                    // 常见的 feature 容器选择器
                    const selectors = [
                        '[class*="feature"] h3',
                        '[class*="feature"] h2',
                        '[class*="benefit"] h3',
                        '.features li',
                        '[data-testid*="feature"]',
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            const text = el.innerText.trim();
                            if (text && text.length < 200) features.push(text);
                        });
                        if (features.length > 0) break;
                    }
                    return features.slice(0, 20);
                }
            """)

            # 提取定价信息
            result["pricing"] = await page.evaluate("""
                () => {
                    const pricing = {};
                    // 查找价格元素
                    const priceElements = document.querySelectorAll(
                        '[class*="price"], [class*="pricing"], [data-testid*="price"]'
                    );
                    const prices = [];
                    priceElements.forEach(el => {
                        const text = el.innerText.trim();
                        const match = text.match(/\\$[\\d,.]+/);
                        if (match) prices.push(match[0]);
                    });
                    pricing.prices = [...new Set(prices)].slice(0, 5);

                    // 查找计划名称
                    const planElements = document.querySelectorAll(
                        '[class*="plan"] h2, [class*="plan"] h3, [class*="tier"] h2'
                    );
                    pricing.plans = [];
                    planElements.forEach(el => {
                        pricing.plans.push(el.innerText.trim());
                    });
                    pricing.plans = pricing.plans.slice(0, 5);

                    return pricing;
                }
            """)

            # 截图
            if screenshot:
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                screenshot_path = CRAWL_DIR / f"{url_hash}_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot_path), full_page=True)
                result["screenshot_path"] = str(screenshot_path)

        except Exception as e:
            result["error"] = str(e)[:500]
            logger.error(f"🌐 Crawl failed for {url}: {e}")
        finally:
            await page.close()

        # 保存抓取结果
        self._save_result(url, result)
        return result

    async def detect_changes(self, url: str) -> Optional[dict]:
        """
        检测页面变化（与上次抓取对比）

        返回：
        {
            "changed": True/False,
            "old_hash": "...",
            "new_hash": "...",
            "title_changed": True/False,
            "new_features": [...],
            "removed_features": [...],
        }
        """
        # 获取上次抓取结果
        old_result = self._load_latest_result(url)

        # 执行新抓取
        new_result = await self.crawl(url)

        if not old_result:
            return {"changed": False, "reason": "first_crawl", "result": new_result}

        changes = {
            "changed": False,
            "url": url,
            "old_hash": old_result.get("content_hash", ""),
            "new_hash": new_result.get("content_hash", ""),
            "detected_at": time.time(),
        }

        # 内容变化
        if changes["old_hash"] != changes["new_hash"]:
            changes["changed"] = True
            changes["content_changed"] = True

        # 标题变化
        if old_result.get("title") != new_result.get("title"):
            changes["changed"] = True
            changes["title_changed"] = True
            changes["old_title"] = old_result.get("title")
            changes["new_title"] = new_result.get("title")

        # 特性变化
        old_features = set(old_result.get("features", []))
        new_features = set(new_result.get("features", []))
        added = new_features - old_features
        removed = old_features - new_features
        if added or removed:
            changes["changed"] = True
            changes["new_features"] = list(added)
            changes["removed_features"] = list(removed)

        # 定价变化
        old_prices = set(old_result.get("pricing", {}).get("prices", []))
        new_prices = set(new_result.get("pricing", {}).get("prices", []))
        if old_prices != new_prices:
            changes["changed"] = True
            changes["pricing_changed"] = True
            changes["old_prices"] = list(old_prices)
            changes["new_prices"] = list(new_prices)

        return changes

    async def crawl_competitors(self, urls: list[str]) -> list[dict]:
        """批量抓取竞品页面"""
        results = []
        for url in urls:
            try:
                result = await self.crawl(url)
                results.append(result)
                # 礼貌间隔
                await asyncio.sleep(2)
            except Exception as e:
                results.append({"url": url, "error": str(e)})
        return results

    def _save_result(self, url: str, result: dict):
        """保存抓取结果到本地"""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        result_dir = CRAWL_DIR / url_hash
        result_dir.mkdir(exist_ok=True)

        # 保存最新结果
        latest_path = result_dir / "latest.json"
        with open(latest_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        # 保存历史（带时间戳）
        history_path = result_dir / f"{int(time.time())}.json"
        with open(history_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

    def _load_latest_result(self, url: str) -> Optional[dict]:
        """加载上次抓取结果"""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        latest_path = CRAWL_DIR / url_hash / "latest.json"

        if not latest_path.exists():
            return None

        try:
            with open(latest_path) as f:
                return json.load(f)
        except Exception:
            return None

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()

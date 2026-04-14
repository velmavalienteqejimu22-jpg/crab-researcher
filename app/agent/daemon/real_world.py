"""
CrabRes Real World Integration — Daemon 的真实世界连接层

把 BrowserCrawler、RSSWatcher、ActionTracker 整合到 Daemon tick 中，
让 Agent 每 30 分钟自动：
1. 检查 RSS 订阅的新内容
2. 抓取竞品页面检测变化
3. 追踪已完成 action 的结果
4. 从成功 action 中提取新 Skill
"""

import logging
import time

logger = logging.getLogger(__name__)


class RealWorldConnector:
    """
    真实世界连接器 — 在 Daemon tick 中调用

    职责：
    - 管理 RSS feeds
    - 管理竞品监控列表
    - 驱动 Action→Result→Skill 闭环
    """

    def __init__(self):
        from app.agent.tools.rss_watcher import RSSWatcher
        from app.agent.tools.browser_crawler import BrowserCrawler
        from app.agent.engine.action_tracker import ActionTracker

        self.rss = RSSWatcher()
        self.crawler = BrowserCrawler()
        self.tracker = ActionTracker()

        # 竞品监控列表（用户可通过 API 配置）
        self._competitor_urls: list[str] = []
        self._last_crawl_time: float = 0
        self._crawl_interval: int = 3600 * 6  # 每 6 小时爬一次竞品

        # 预置一些默认 RSS 源（AI/SaaS 行业）
        default_feeds = [
            ("https://news.ycombinator.com/rss", "Hacker News", "tech"),
            ("https://www.producthunt.com/feed", "Product Hunt", "launch"),
            ("https://blog.langchain.dev/rss/", "LangChain Blog", "ai"),
            ("https://openai.com/blog/rss.xml", "OpenAI Blog", "ai"),
        ]
        for url, name, cat in default_feeds:
            if not any(f["url"] == url for f in self.rss.list_feeds()):
                self.rss.add_feed(url, name, cat)

    async def tick(self) -> list[dict]:
        """
        每次 Daemon tick 时调用

        返回发现列表（供 EventBus 发布）
        """
        discoveries = []

        # 1. 检查 RSS 新内容
        try:
            new_items = await self.rss.check_feeds()
            for item in new_items:
                discoveries.append({
                    "type": "rss_new_item",
                    "source": item.get("feed_name", "unknown"),
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "description": item.get("description", "")[:200],
                    "discovered_at": time.time(),
                })
            if new_items:
                logger.info(f"🌍 RealWorld: {len(new_items)} new RSS items")
        except Exception as e:
            logger.error(f"🌍 RealWorld RSS check failed: {e}")

        # 2. 竞品页面变化检测（每 6 小时一次）
        if self._competitor_urls and (time.time() - self._last_crawl_time > self._crawl_interval):
            try:
                for url in self._competitor_urls:
                    changes = await self.crawler.detect_changes(url)
                    if changes and changes.get("changed"):
                        discoveries.append({
                            "type": "competitor_change",
                            "url": url,
                            "changes": changes,
                            "discovered_at": time.time(),
                        })
                self._last_crawl_time = time.time()
                logger.info(f"🌍 RealWorld: crawled {len(self._competitor_urls)} competitor pages")
            except Exception as e:
                logger.error(f"🌍 RealWorld crawl failed: {e}")

        # 3. 追踪已完成 action 的结果
        try:
            pending = self.tracker.get_pending_tracking()
            for action in pending:
                # 如果有 result_url，尝试用爬虫抓取结果
                result_url = action.details.get("result_url")
                if result_url:
                    try:
                        crawl_result = await self.crawler.crawl(result_url, screenshot=False)
                        # 简单的 engagement 提取（后续可以用 LLM 分析）
                        text = crawl_result.get("text_content", "")
                        result = {
                            "url": result_url,
                            "title": crawl_result.get("title", ""),
                            "text_preview": text[:500],
                            "crawled_at": time.time(),
                        }
                        self.tracker.record_result(action.action_id, result)
                        discoveries.append({
                            "type": "action_result_tracked",
                            "action_id": action.action_id,
                            "platform": action.platform,
                            "result": result,
                        })
                    except Exception as e:
                        logger.error(f"🌍 Failed to track action {action.action_id}: {e}")
        except Exception as e:
            logger.error(f"🌍 RealWorld action tracking failed: {e}")

        # 4. 从成功 action 中提取 Skill
        try:
            successful = self.tracker.get_successful_unextracted()
            for action in successful:
                # 触发 Skill 提取（需要 SkillWriter，这里只标记）
                discoveries.append({
                    "type": "skill_extraction_candidate",
                    "action_id": action.action_id,
                    "platform": action.platform,
                    "description": action.description,
                    "result": action.result,
                })
                logger.info(f"🌍 Skill extraction candidate: {action.action_id}")
        except Exception as e:
            logger.error(f"🌍 RealWorld skill extraction failed: {e}")

        return discoveries

    def add_competitor(self, url: str):
        """添加竞品监控 URL"""
        if url not in self._competitor_urls:
            self._competitor_urls.append(url)
            logger.info(f"🌍 Added competitor: {url}")

    def remove_competitor(self, url: str):
        if url in self._competitor_urls:
            self._competitor_urls.remove(url)

    def get_status(self) -> dict:
        """返回状态信息"""
        return {
            "rss_feeds": len(self.rss.list_feeds()),
            "competitors_monitored": len(self._competitor_urls),
            "actions_total": self.tracker.get_stats()["total"],
            "actions_stats": self.tracker.get_stats(),
            "last_crawl": self._last_crawl_time,
        }

    async def close(self):
        await self.crawler.close()

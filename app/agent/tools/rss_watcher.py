"""
CrabRes RSS Watcher — 被动接收外部世界的信息

解决的核心问题：
- Agent 之前只能主动搜索（用户不说话就不知道外面发生了什么）
- 现在 Agent 能订阅 RSS/Atom feed，自动接收竞品博客更新、行业新闻

工作方式：
1. 用户配置要监控的 feed URL 列表
2. Daemon 每次 tick 时调用 check_feeds()
3. 新文章自动发布到 EventBus → 前端实时通知
"""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

FEED_DIR = Path(".crabres/feeds")
FEED_DIR.mkdir(parents=True, exist_ok=True)


class RSSWatcher:
    """
    RSS/Atom 订阅监控器 — Agent 的"耳朵"

    用法：
        watcher = RSSWatcher()
        watcher.add_feed("https://blog.competitor.com/feed")
        new_items = await watcher.check_feeds()
    """

    def __init__(self):
        self._feeds: dict[str, dict] = {}
        self._seen_ids: set[str] = set()
        self._load_state()

    def add_feed(self, url: str, name: str = "", category: str = "general"):
        """添加一个 feed 源"""
        feed_id = hashlib.md5(url.encode()).hexdigest()[:8]
        self._feeds[feed_id] = {
            "url": url,
            "name": name or url,
            "category": category,
            "added_at": time.time(),
            "last_checked": 0,
            "item_count": 0,
        }
        self._save_state()
        logger.info(f"📡 RSS: added feed {name or url}")

    def remove_feed(self, url: str):
        """移除一个 feed 源"""
        feed_id = hashlib.md5(url.encode()).hexdigest()[:8]
        if feed_id in self._feeds:
            del self._feeds[feed_id]
            self._save_state()

    def list_feeds(self) -> list[dict]:
        """列出所有 feed 源"""
        return [{"id": k, **v} for k, v in self._feeds.items()]

    async def check_feeds(self) -> list[dict]:
        """
        检查所有 feed 的新内容

        返回新发现的条目列表
        """
        all_new_items = []

        for feed_id, feed in self._feeds.items():
            try:
                new_items = await self._check_single_feed(feed_id, feed)
                all_new_items.extend(new_items)
                feed["last_checked"] = time.time()
                feed["item_count"] += len(new_items)
            except Exception as e:
                logger.error(f"📡 RSS: failed to check {feed['name']}: {e}")

            # 礼貌间隔
            await asyncio.sleep(1)

        if all_new_items:
            logger.info(f"📡 RSS: found {len(all_new_items)} new items across {len(self._feeds)} feeds")

        self._save_state()
        return all_new_items

    async def _check_single_feed(self, feed_id: str, feed: dict) -> list[dict]:
        """检查单个 feed"""
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(feed["url"], headers={
                "User-Agent": "CrabRes/1.0 (Growth Agent RSS Reader)",
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            })
            resp.raise_for_status()

        # 解析 XML
        root = ET.fromstring(resp.text)
        items = self._parse_feed(root, feed)

        # 过滤已见过的
        new_items = []
        for item in items:
            item_id = item.get("id") or item.get("link") or item.get("title")
            if not item_id:
                continue
            id_hash = hashlib.md5(item_id.encode()).hexdigest()
            if id_hash not in self._seen_ids:
                self._seen_ids.add(id_hash)
                item["feed_name"] = feed["name"]
                item["feed_category"] = feed["category"]
                item["discovered_at"] = time.time()
                new_items.append(item)

        return new_items

    def _parse_feed(self, root: ET.Element, feed: dict) -> list[dict]:
        """解析 RSS 2.0 或 Atom feed"""
        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        for item in root.findall(".//item"):
            items.append({
                "title": self._get_text(item, "title"),
                "link": self._get_text(item, "link"),
                "description": self._get_text(item, "description", max_len=500),
                "published": self._get_text(item, "pubDate"),
                "id": self._get_text(item, "guid"),
                "format": "rss",
            })

        # Atom
        if not items:
            for entry in root.findall(".//atom:entry", ns):
                link_el = entry.find("atom:link", ns)
                items.append({
                    "title": self._get_text_ns(entry, "atom:title", ns),
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "description": self._get_text_ns(entry, "atom:summary", ns, max_len=500),
                    "published": self._get_text_ns(entry, "atom:published", ns) or self._get_text_ns(entry, "atom:updated", ns),
                    "id": self._get_text_ns(entry, "atom:id", ns),
                    "format": "atom",
                })

        return items[:20]  # 最多 20 条

    def _get_text(self, element: ET.Element, tag: str, max_len: int = 0) -> str:
        el = element.find(tag)
        if el is None or el.text is None:
            return ""
        text = el.text.strip()
        if max_len and len(text) > max_len:
            text = text[:max_len] + "..."
        return text

    def _get_text_ns(self, element: ET.Element, tag: str, ns: dict, max_len: int = 0) -> str:
        el = element.find(tag, ns)
        if el is None or el.text is None:
            return ""
        text = el.text.strip()
        if max_len and len(text) > max_len:
            text = text[:max_len] + "..."
        return text

    def _save_state(self):
        """持久化状态"""
        state = {
            "feeds": self._feeds,
            "seen_ids": list(self._seen_ids)[-1000:],  # 只保留最近 1000 个
        }
        with open(FEED_DIR / "state.json", "w") as f:
            json.dump(state, f, indent=2, default=str)

    def _load_state(self):
        """加载状态"""
        state_path = FEED_DIR / "state.json"
        if not state_path.exists():
            return
        try:
            with open(state_path) as f:
                state = json.load(f)
            self._feeds = state.get("feeds", {})
            self._seen_ids = set(state.get("seen_ids", []))
            logger.info(f"📡 RSS: loaded {len(self._feeds)} feeds, {len(self._seen_ids)} seen items")
        except Exception as e:
            logger.warning(f"📡 RSS: failed to load state: {e}")

"""
CrabRes Growth Daemon — 永远在线的增长引擎

学习自 Claude Code KAIROS，适配增长场景。
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GrowthDaemon:
    """
    后台增长引擎
    
    每 30 分钟 tick 一次，扫描：
    1. 竞品网站变化
    2. 社媒相关讨论
    3. 内容日历到期任务
    
    午夜触发 Growth Dream（记忆蒸馏）。
    """

    TICK_INTERVAL = 1800  # 30 分钟

    def __init__(self, memory, tools, llm=None):
        self.memory = memory
        self.tools = tools
        self.llm = llm
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._discoveries: list[dict] = []  # 待通知的发现

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("🦀 Growth Daemon started (tick every 30min)")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("🦀 Growth Daemon stopped")

    def get_pending_discoveries(self) -> list[dict]:
        """获取并清空待通知的发现（供 API 轮询）"""
        discoveries = self._discoveries.copy()
        self._discoveries.clear()
        return discoveries

    async def _run_loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Daemon tick error: {e}", exc_info=True)

            # 午夜边界
            now = datetime.now()
            if now.hour == 0 and 0 <= now.minute < 5:
                await self._midnight_boundary()

            await asyncio.sleep(self.TICK_INTERVAL)

    async def _tick(self):
        logger.debug("Growth Daemon tick")
        product = await self.memory.load("product")
        if not product:
            return  # 用户还没配置产品信息，不做任何事

        product_name = product.get("name", "")
        product_desc = product.get("description", "")
        keywords = product.get("keywords", [])

        tasks = []

        # 1. 扫描竞品变化
        tasks.append(self._scan_competitors(product))

        # 2. 扫描社媒提及
        if product_name or keywords:
            tasks.append(self._scan_social(product_name, keywords))

        # 3. 检查内容日历
        tasks.append(self._check_calendar())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                self._discoveries.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Daemon subtask failed: {result}")

        if self._discoveries:
            logger.info(f"Daemon found {len(self._discoveries)} discoveries")
            # 写入日志
            for d in self._discoveries:
                await self.memory.append_journal({
                    "type": "daemon_discovery",
                    "discovery": d,
                    "timestamp": time.time(),
                })

    async def _scan_competitors(self, product: dict) -> list[dict]:
        """扫描竞品网站变化"""
        discoveries = []
        competitors = await self.memory.load("competitors", category="research")
        if not competitors or not isinstance(competitors, list):
            return []

        scraper = self.tools.get("scrape_website")
        if not scraper:
            return []

        for comp in competitors[:3]:  # 最多扫 3 个竞品（节省资源）
            url = comp.get("url")
            if not url:
                continue
            try:
                result = await scraper.execute(url=url, extract="pricing, features")
                # 对比上次抓取的内容
                cache_key = f"comp_cache_{url.replace('/', '_').replace(':', '')}"
                last = await self.memory.load(cache_key, category="research")

                if last:
                    old_len = last.get("content_length", 0)
                    new_len = result.get("content_length", 0)
                    # 简单判断：内容长度变化超过 20% 视为有变化
                    if old_len > 0 and abs(new_len - old_len) / old_len > 0.2:
                        discoveries.append({
                            "type": "competitor_change",
                            "competitor": comp.get("name", url),
                            "url": url,
                            "change": f"Website content changed significantly ({old_len} → {new_len} chars)",
                        })

                # 更新缓存
                await self.memory.save(cache_key, {
                    "content_length": result.get("content_length", 0),
                    "title": result.get("title", ""),
                    "checked_at": time.time(),
                }, category="research")

            except Exception as e:
                logger.debug(f"Competitor scan failed for {url}: {e}")

        return discoveries

    async def _scan_social(self, product_name: str, keywords: list) -> list[dict]:
        """扫描社媒新讨论"""
        discoveries = []
        searcher = self.tools.get("social_search")
        if not searcher:
            return []

        query = product_name or " ".join(keywords[:3])
        if not query:
            return []

        try:
            result = await searcher.execute(query=query, platforms=["reddit", "hackernews"])
            if result.get("count", 0) > 0:
                # 只通知新的高价值讨论
                for r in result.get("results", [])[:2]:
                    discoveries.append({
                        "type": "social_mention",
                        "platform": r.get("platform", ""),
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "preview": r.get("content", "")[:200],
                    })
        except Exception as e:
            logger.debug(f"Social scan failed: {e}")

        return discoveries

    async def _check_calendar(self) -> list[dict]:
        """检查内容日历"""
        discoveries = []
        calendar = await self.memory.load("content_calendar", category="strategy")
        if not calendar or not isinstance(calendar, list):
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        for item in calendar:
            if item.get("date") == today and item.get("status") != "done":
                discoveries.append({
                    "type": "calendar_due",
                    "title": item.get("title", "Content task due"),
                    "channel": item.get("channel", ""),
                })

        return discoveries

    async def _midnight_boundary(self):
        """午夜边界：日报 + Growth Dream"""
        logger.info("Midnight boundary triggered")

        # 生成日报摘要
        today = datetime.now().strftime("%Y-%m-%d")
        journal_path = self.memory.base_dir / "journal" / f"{today}.jsonl"

        if journal_path.exists():
            entries = []
            for line in journal_path.read_text().strip().split("\n"):
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

            if entries:
                await self.memory.save(f"daily_summary_{today}", {
                    "date": today,
                    "entries_count": len(entries),
                    "types": list(set(e.get("type", "") for e in entries)),
                }, category="journal")

        # 触发 Growth Dream（如果条件满足）
        await self.growth_dream()

    async def growth_dream(self):
        """
        Growth Dream — 记忆蒸馏
        
        四阶段：Orient → Gather → Consolidate → Prune
        """
        logger.info("Growth Dream: starting...")

        # Phase 1: Orient — 扫描记忆状态
        categories = ["product", "research", "strategy", "execution", "feedback"]
        memory_status = {}
        for cat in categories:
            items = await self.memory.list_memories(cat)
            memory_status[cat] = len(items)
        logger.info(f"Dream Orient: {memory_status}")

        # Phase 2: Gather — 从最近日志提取关键信息
        journal_dir = self.memory.base_dir / "journal"
        recent_entries = []
        if journal_dir.exists():
            files = sorted(journal_dir.glob("*.jsonl"), reverse=True)[:3]  # 最近 3 天
            for f in files:
                for line in f.read_text().strip().split("\n"):
                    if line:
                        try:
                            recent_entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        logger.info(f"Dream Gather: {len(recent_entries)} recent entries")

        # Phase 3: Consolidate — 如果有 LLM，用它整理
        if self.llm and recent_entries:
            from app.agent.engine.llm_adapter import TaskTier
            try:
                summary_input = json.dumps(recent_entries[:20], ensure_ascii=False, default=str)[:3000]
                response = await self.llm.generate(
                    system_prompt="You are a memory consolidation agent. Summarize the following growth journal entries into key facts, decisions, and insights. Remove duplicates and contradictions. Output structured bullet points.",
                    messages=[{"role": "user", "content": summary_input}],
                    tier=TaskTier.PARSING,  # 用最便宜的模型
                    max_tokens=1024,
                )
                await self.memory.save("dream_summary", {
                    "consolidated_at": time.time(),
                    "entries_processed": len(recent_entries),
                    "summary": response.content,
                }, category="feedback")
                logger.info("Dream Consolidate: done with LLM summary")
            except Exception as e:
                logger.error(f"Dream Consolidate failed: {e}")

        # Phase 4: Prune — 清理过旧的日志（保留最近 30 天）
        if journal_dir.exists():
            cutoff = datetime.now().timestamp() - 30 * 86400
            for f in journal_dir.glob("*.jsonl"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    logger.info(f"Dream Prune: removed old journal {f.name}")

        logger.info("Growth Dream: completed")

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

from app.agent.daemon.scheduler import DaemonScheduler

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

    def __init__(self, memory, tools, llm=None, notifier=None):
        self.memory = memory
        self.tools = tools
        self.llm = llm
        self.notifier = notifier  # NotificationHub
        self._running = False
        self._scheduler = DaemonScheduler(self)
        self._discoveries: list[dict] = []  # 待通知的发现

    async def start(self):
        if self._running:
            return
        self._running = True
        self._scheduler.start()
        logger.info("🦀 Growth Daemon started (APScheduler: tick@30min, dream@midnight)")

    async def stop(self):
        self._running = False
        self._scheduler.shutdown()
        logger.info("🦀 Growth Daemon stopped")

    @property
    def scheduler_status(self) -> dict:
        """返回调度器详细状态"""
        return self._scheduler.get_status()

    def get_pending_discoveries(self) -> list[dict]:
        """获取并清空待通知的发现（供 API 轮询）"""
        discoveries = self._discoveries.copy()
        self._discoveries.clear()
        return discoveries

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

        # 4. 追踪已发布帖子的效果（action→result 闭环）
        tasks.append(self._scan_action_results())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                self._discoveries.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Daemon subtask failed: {result}")

        if self._discoveries:
            logger.info(f"Daemon found {len(self._discoveries)} discoveries")
            for i, d in enumerate(self._discoveries):
                # 用 LLM 分析发现并生成行动建议
                self._discoveries[i] = await self._enrich_discovery(d, product)
                await self.memory.append_journal({
                    "type": "daemon_discovery",
                    "discovery": self._discoveries[i],
                    "timestamp": time.time(),
                })
            # 通知用户
            if self.notifier:
                for d in self._discoveries:
                    try:
                        await self.notifier.send_discovery(d)
                    except Exception as e:
                        logger.error(f"Notification failed: {e}")

    async def _enrich_discovery(self, discovery: dict, product: dict) -> dict:
        """用 LLM 分析发现并生成行动建议"""
        if not self.llm:
            return discovery
        from app.agent.engine.llm_adapter import TaskTier
        product_name = product.get("name", product.get("raw_description", "")[:50])
        try:
            response = await self.llm.generate(
                system_prompt="You are a concise growth strategist. Analyze discoveries and give ONE specific action in 2 sentences.",
                messages=[{"role": "user", "content": f"Product: {product_name}\nDiscovery: {json.dumps(discovery, ensure_ascii=False, default=str)[:400]}\n\nWhat does this mean and what should we do RIGHT NOW?"}],
                tier=TaskTier.PARSING,
                max_tokens=150,
            )
            discovery["analysis"] = response.content
            discovery["has_action"] = True
        except Exception as e:
            logger.warning(f"Discovery enrichment failed: {e}")
        return discovery

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
        """扫描社媒新讨论（产品 + 竞品）"""
        discoveries = []
        searcher = self.tools.get("social_search")
        if not searcher:
            return []

        # 搜索产品自身
        query = product_name or " ".join(keywords[:3])
        if query:
            try:
                result = await searcher.execute(query=query, platforms=["reddit", "hackernews"])
                if result.get("count", 0) > 0:
                    for r in result.get("results", [])[:2]:
                        discoveries.append({
                            "type": "social_mention",
                            "platform": r.get("platform", ""),
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "preview": r.get("content", "")[:200],
                        })
            except Exception as e:
                logger.debug(f"Social scan (product) failed: {e}")

        # 搜索竞品动态
        competitors = await self.memory.load("competitors", category="research")
        if isinstance(competitors, list):
            for comp in competitors[:3]:  # 最多扫 3 个竞品
                comp_name = comp.get("name", "")
                if not comp_name:
                    continue
                try:
                    result = await searcher.execute(
                        query=f"{comp_name} launch update new feature",
                        platforms=["reddit", "hackernews", "x"],
                    )
                    if result.get("count", 0) > 0:
                        for r in result.get("results", [])[:1]:
                            discoveries.append({
                                "type": "competitor_social",
                                "competitor": comp_name,
                                "platform": r.get("platform", ""),
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "preview": r.get("content", "")[:200],
                            })
                except Exception as e:
                    logger.debug(f"Social scan (competitor {comp_name}) failed: {e}")

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

    async def _scan_action_results(self) -> list[dict]:
        """
        追踪已发布帖子的效果 — action→result 闭环的核心
        
        扫描所有 status="posted" 的 action，抓取 metrics（likes/upvotes/comments）。
        """
        discoveries = []

        try:
            from app.agent.memory.experiments import ExperimentTracker
            tracker = ExperimentTracker(base_dir=str(self.memory.base_dir))
            trackable = await tracker.get_trackable_actions()

            if not trackable:
                return []

            scraper = self.tools.get("scrape_website")
            if not scraper:
                return []

            for action in trackable[:5]:  # 每次最多追踪 5 个
                url = action.get("url", "")
                platform = action.get("platform", "")
                action_id = action.get("id", "")

                if not url:
                    continue

                try:
                    result = await scraper.execute(url=url)
                    content = result.get("content_preview", "")
                    metrics = self._extract_metrics(content, platform)

                    if metrics:
                        await tracker.record_result(
                            action_id=action_id,
                            metrics=metrics,
                            raw_data={"scraped_length": result.get("content_length", 0)},
                        )

                        total_engagement = sum(metrics.values())
                        if total_engagement > 50:
                            discoveries.append({
                                "type": "action_result",
                                "title": f"Your {platform} post got {total_engagement} engagement!",
                                "url": url,
                                "metrics": metrics,
                            })

                        logger.info(f"Tracked action {action_id}: {metrics}")

                        # 🔥 Auto-evolve: if result is "great", synthesize a Skill
                        if total_engagement > 100:
                            try:
                                from app.agent.skills import SkillStore, SkillWriter
                                user_id = str(self.memory.base_dir).split("/")[-1]
                                store = SkillStore(base_dir=f".crabres/skills/{user_id}")
                                writer = SkillWriter(store=store, llm=self.llm)
                                
                                product = await self.memory.load("product")
                                product_ctx = json.dumps(product or {}, ensure_ascii=False, default=str)[:300]
                                
                                skill = await writer.synthesize_from_action(
                                    action=action,
                                    result={"metrics": metrics, "verdict": "great", "score": min(100, total_engagement)},
                                    product_context=product_ctx,
                                )
                                if skill:
                                    discoveries.append({
                                        "type": "skill_learned",
                                        "title": f"New skill learned: {skill.name}",
                                        "skill_id": skill.id,
                                        "confidence": skill.confidence,
                                    })
                                    logger.info(f"Auto-evolved skill from action {action_id}: {skill.name}")
                            except Exception as skill_err:
                                logger.debug(f"Skill auto-evolution failed: {skill_err}")

                except Exception as e:
                    logger.debug(f"Failed to track action {action_id}: {e}")

        except Exception as e:
            logger.error(f"Action result scanning failed: {e}")

        return discoveries

    def _extract_metrics(self, content: str, platform: str) -> dict:
        """从抓取的页面内容中启发式提取 metrics"""
        import re
        metrics = {}
        if not content:
            return metrics
        content_lower = content.lower()

        if platform == "reddit":
            pts = re.search(r'(\d+)\s*(?:points?|upvotes?|score)', content_lower)
            cmts = re.search(r'(\d+)\s*comments?', content_lower)
            if pts: metrics["upvotes"] = int(pts.group(1))
            if cmts: metrics["comments"] = int(cmts.group(1))
        elif platform == "x":
            lk = re.search(r'(\d+)\s*(?:likes?)', content_lower)
            rt = re.search(r'(\d+)\s*(?:retweets?|reposts?)', content_lower)
            rp = re.search(r'(\d+)\s*(?:replies?)', content_lower)
            if lk: metrics["likes"] = int(lk.group(1))
            if rt: metrics["retweets"] = int(rt.group(1))
            if rp: metrics["replies"] = int(rp.group(1))
        elif platform in ("linkedin", "hackernews"):
            pts = re.search(r'(\d+)\s*(?:reactions?|likes?|points?)', content_lower)
            cmts = re.search(r'(\d+)\s*comments?', content_lower)
            if pts: metrics["likes" if platform == "linkedin" else "upvotes"] = int(pts.group(1))
            if cmts: metrics["comments"] = int(cmts.group(1))

        return metrics

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

        # 触发 GrowthDream 对活跃 session 进行深层记忆蒸馏
        if self.llm:
            try:
                from app.agent.engine.dream import GrowthDream
                dream = GrowthDream(memory=self.memory, llm=self.llm)
                # 扫描所有持久化的 session state
                product_dir = self.memory.base_dir / "product"
                if product_dir.exists():
                    for state_file in product_dir.glob("loop_state_*.json"):
                        sid = state_file.stem.replace("loop_state_", "")
                        try:
                            await dream.distill(sid)
                        except Exception as e:
                            logger.warning(f"Dream distill failed for {sid}: {e}")
            except Exception as e:
                logger.error(f"GrowthDream integration failed: {e}")

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

        # Phase 3: Consolidate + 效果复盘
        if self.llm and recent_entries:
            from app.agent.engine.llm_adapter import TaskTier
            try:
                summary_input = json.dumps(recent_entries[:20], ensure_ascii=False, default=str)[:3000]
                response = await self.llm.generate(
                    system_prompt="""You are a growth analytics agent. Analyze the journal entries and produce:

1. WHAT WORKED: Which actions drove results? (specific posts, emails, channels)
2. WHAT DIDN'T: Which actions had no effect or negative effect?
3. PATTERNS: What growth patterns are emerging? (best times, best channels, best content types)
4. NEXT WEEK RULES: Based on the above, what 3 specific rules should guide next week's strategy?

Be specific. Use data from the entries. Output as structured bullet points.""",
                    messages=[{"role": "user", "content": summary_input}],
                    tier=TaskTier.PARSING,
                    max_tokens=1024,
                )
                await self.memory.save("dream_summary", {
                    "consolidated_at": time.time(),
                    "entries_processed": len(recent_entries),
                    "summary": response.content,
                }, category="feedback")
                # 也保存为"增长规律"供 Coordinator 下次使用
                await self.memory.save("growth_patterns", {
                    "patterns": response.content,
                    "updated_at": time.time(),
                }, category="strategy")
                logger.info("Dream Consolidate: done with effect review")
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

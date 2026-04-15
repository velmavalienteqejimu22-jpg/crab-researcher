"""
CrabRes Orchestrator — 确定性阶段编排器

解决的核心问题：
- 之前 run() 是一个 flat while loop，LLM 每次迭代都要决定"下一步是什么"
- 模型能力不足时，决策质量差：搜了 8 次还在搜、跳过圆桌、不用浏览器
- 现在：阶段间的转换由代码控制（确定性），阶段内的操作由 LLM 决策

架构对比：
  Before: while(running) { decision = LLM(); execute(decision); }  ← LLM 控制一切
  After:  for stage in [UNDERSTAND, RESEARCH, EXPERT, SYNTHESIZE, DELIVER]:
              stage.run(LLM)  ← 代码控制流程，LLM 控制细节

学习自：
- Claude Code: Orchestrator + Agent 分层
- Manus: 确定性的 Plan → Execute → Verify 流程
- Devin: 每个阶段有独立的 Agent 和工具集
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)


class Stage(str, Enum):
    """编排器阶段 — 严格按顺序执行"""
    UNDERSTAND = "understand"    # 理解用户意图 + 产品信息
    RESEARCH = "research"        # 搜索竞品 / 市场 / 用户讨论
    EXPERT = "expert"            # 圆桌专家分析
    SYNTHESIZE = "synthesize"    # CGO 综合输出
    DELIVER = "deliver"          # 生成交付物（文档 + Playbook）


@dataclass
class StageResult:
    """每个阶段的输出"""
    stage: Stage
    data: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)   # yield 给前端的事件
    should_skip_remaining: bool = False                 # 提前终止（如纯闲聊）
    duration_ms: int = 0


@dataclass
class OrchestratorContext:
    """编排器上下文 — 跨阶段共享"""
    user_message: str
    language: str = "en"
    
    # UNDERSTAND 阶段输出
    intent: str = ""                    # "greeting" | "product_intro" | "growth_request" | "tool_request" | "followup" | "chitchat"
    has_product_info: bool = False
    product_info: dict = field(default_factory=dict)
    is_self_awareness: bool = False     # 用户问"你是什么"
    direct_reply: str = ""              # 不需要走完整流程的直接回复
    
    # RESEARCH 阶段输出
    search_results: list[dict] = field(default_factory=list)
    scraped_pages: list[dict] = field(default_factory=list)
    browse_results: list[dict] = field(default_factory=list)
    tool_call_count: int = 0
    
    # EXPERT 阶段输出
    expert_outputs: dict[str, str] = field(default_factory=dict)
    expert_ids_used: list[str] = field(default_factory=list)
    
    # SYNTHESIZE 阶段输出
    synthesis: str = ""
    
    # DELIVER 阶段输出
    deliverables: list[dict] = field(default_factory=list)
    
    # 累计事件（所有阶段的 yield events）
    all_events: list[dict] = field(default_factory=list)


class Orchestrator:
    """
    确定性阶段编排器
    
    控制流程：
    1. UNDERSTAND: 意图分类 + 产品信息提取（确定性规则 + 轻量 LLM）
    2. RESEARCH: 最多 N 次工具调用（代码控制上限，LLM 选择查什么）
    3. EXPERT: 根据产品类型选专家 + 圆桌（代码选人，专家各自分析）
    4. SYNTHESIZE: CGO 综合所有数据（LLM）
    5. DELIVER: 生成文档 + Playbook（LLM 生成内容，代码控制格式）
    
    每个阶段有明确的：
    - 入口条件（什么时候执行）
    - 退出条件（什么时候结束）
    - 最大时间/调用次数限制
    - 输出格式
    """

    # ===== 阶段配置 =====
    MAX_RESEARCH_TOOL_CALLS = 4     # RESEARCH 阶段最多调用 4 次工具
    MAX_RESEARCH_TIME_SEC = 45      # RESEARCH 阶段最多 45 秒
    MAX_EXPERTS = 4                 # EXPERT 阶段最多 4 个专家
    EXPERT_TIMEOUT_SEC = 90         # 单个专家最多 90 秒
    MIN_RESEARCH_FOR_EXPERT = 1     # 至少 1 条搜索结果才启动圆桌
    MIN_RESEARCH_FOR_DELIVER = 2    # 至少 2 条搜索结果才生成交付物

    def __init__(self, loop: 'AgentLoop'):
        """
        Args:
            loop: AgentLoop 实例，提供 LLM / 工具 / 专家 / 记忆
        """
        self.loop = loop
        self.llm = loop.llm
        self.tools = loop.tools
        self.experts = loop.experts
        self.memory = loop.memory

    async def run(self, user_message: str, language: str = "en") -> AsyncIterator[dict]:
        """
        主编排流程 — yield 事件给前端
        
        每个阶段是一个独立的 async generator，编排器按顺序调用。
        阶段间的数据通过 OrchestratorContext 传递。
        """
        ctx = OrchestratorContext(user_message=user_message, language=language)
        
        # 加载已有的产品信息（包括 onboarding 时设置的 budget/target）
        product_in_memory = await self.memory.load("product")
        if product_in_memory and product_in_memory.get("raw_description"):
            ctx.product_info = product_in_memory
            ctx.has_product_info = True
        
        # 从 onboarding 消息中提取结构化信息（budget、target users 等）
        # Onboarding 前端发送格式: "My product is called X. ... Goal: 100 users ... Monthly budget: $0."
        self._extract_onboarding_context(ctx)

        stages = [
            (Stage.UNDERSTAND, self._stage_understand),
            (Stage.RESEARCH, self._stage_research),
            (Stage.EXPERT, self._stage_expert),
            (Stage.SYNTHESIZE, self._stage_synthesize),
            (Stage.DELIVER, self._stage_deliver),
        ]

        for stage_enum, stage_fn in stages:
            t0 = time.time()
            try:
                result = StageResult(stage=stage_enum)
                async for event in stage_fn(ctx):
                    result.events.append(event)
                    yield event
                
                result.duration_ms = int((time.time() - t0) * 1000)
                logger.info(f"Stage {stage_enum.value} completed in {result.duration_ms}ms")
                
                # 检查是否需要提前终止
                if ctx.direct_reply:
                    # UNDERSTAND 阶段决定直接回复（闲聊/自我介绍）
                    yield {"type": "message", "content": ctx.direct_reply}
                    return
                    
            except Exception as e:
                logger.error(f"Stage {stage_enum.value} failed: {e}", exc_info=True)
                # 阶段失败不崩溃，跳到下一个阶段或给兜底回复
                if stage_enum in (Stage.UNDERSTAND, Stage.SYNTHESIZE):
                    # 关键阶段失败 → 兜底
                    yield {
                        "type": "message",
                        "content": self._fallback_reply(ctx, str(e)),
                    }
                    return
                # 非关键阶段失败 → 跳过继续
                continue

    # ===== Stage 1: UNDERSTAND =====
    async def _stage_understand(self, ctx: OrchestratorContext) -> AsyncIterator[dict]:
        """
        理解用户意图 — 确定性规则优先，LLM 兜底
        
        输出：ctx.intent, ctx.has_product_info, ctx.is_self_awareness, ctx.direct_reply
        不 yield 任何可见事件（这个阶段对用户透明）
        
        注意：必须包含至少一个 yield 语句（即使不执行到），
        否则 Python 会把这个方法当作 coroutine 而非 async generator，
        导致 run() 中的 async for 报 TypeError。
        """
        # 占位 yield — 使本方法成为 async generator（Python 语言要求）
        # 这行永远不会执行到，但它的存在让 Python 正确识别方法类型
        if False:
            yield {}  # pragma: no cover

        msg = ctx.user_message
        msg_lower = msg.lower().strip()
        lang = ctx.language

        # === 规则 1: 自我认知 ===
        self_triggers = [
            "what are you", "who are you", "你是什么", "你是谁",
            "what do you do", "你做什么", "介绍一下你", "introduce yourself",
        ]
        if any(t in msg_lower for t in self_triggers):
            ctx.is_self_awareness = True
            ctx.intent = "self_awareness"
            from app.agent.engine.llm_adapter import TaskTier
            resp = await self.llm.generate(
                system_prompt=self._self_awareness_prompt(lang),
                messages=[{"role": "user", "content": msg}],
                tier=TaskTier.THINKING,
                max_tokens=200,
            )
            ctx.direct_reply = resp.content
            return

        # === 规则 2: 纯问候 ===
        greetings = ['hi', 'hello', 'hey', '你好', '嗨', 'yo', 'sup', '在吗', '在不在']
        if msg_lower.strip() in greetings:
            ctx.intent = "greeting"
            lang_name = "Chinese" if lang == "zh" else "English"
            from app.agent.engine.llm_adapter import TaskTier
            resp = await self.llm.generate(
                system_prompt=f"You are CrabRes, an AI growth agent. Greet the user warmly in {lang_name}. 1-2 sentences max. Ask what they're building. Be casual, not formal.",
                messages=[{"role": "user", "content": msg}],
                tier=TaskTier.PARSING,
                max_tokens=100,
            )
            ctx.direct_reply = resp.content
            return

        # === 规则 3: 产品信息检测 ===
        # 强信号：直接提到 crabres
        if "crabres" in msg_lower or "crab-researcher" in msg_lower or "crab res" in msg_lower:
            ctx.has_product_info = True
            ctx.intent = "growth_request"
            # 注入自我认知
            ctx.product_info = {
                "name": "CrabRes",
                "raw_description": "CrabRes is an AI growth strategy agent for indie developers. It has 13 AI expert advisors, can browse the web, search social media, analyze competitors, and execute growth actions.",
                "type": "saas",
                "is_self": True,
                "url": "https://crab-researcher.vercel.app",
            }
            # 🔥 解析用户指定的目标平台
            ctx.product_info["target_platforms"] = self._detect_target_platforms(msg)
            return

        # 弱信号：其他产品描述
        if self._detect_product_info(msg):
            ctx.has_product_info = True
            ctx.intent = "growth_request"
            # 自动保存产品信息
            existing = ctx.product_info or {}
            existing["raw_description"] = msg
            existing["updated_at"] = time.time()
            existing["target_platforms"] = self._detect_target_platforms(msg)
            ctx.product_info = existing
            await self.memory.save("product", existing)
            return

        # === 规则 4: 工具请求（"用浏览器看看"、"搜一下"） ===
        tool_triggers = [
            "浏览器", "browser", "搜一下", "搜索", "search",
            "看看", "打开", "访问", "open", "visit", "browse",
            "分析", "analyze", "体验", "试试",
        ]
        url_in_msg = "http" in msg_lower or ".com" in msg_lower or ".io" in msg_lower or ".app" in msg_lower
        if any(t in msg_lower for t in tool_triggers) or url_in_msg:
            ctx.intent = "tool_request"
            # 如果记忆中有产品信息，标记为有
            if ctx.product_info:
                ctx.has_product_info = True
            return

        # === 规则 5: 有记忆中的产品信息 + 非闲聊 ===
        if ctx.has_product_info and len(msg) > 5:
            ctx.intent = "followup"
            return

        # === 兜底: 当作产品描述（用户来 CrabRes 就是为了谈产品） ===
        if len(msg) > 15:
            ctx.has_product_info = True
            ctx.intent = "growth_request"
            existing = ctx.product_info or {}
            existing["raw_description"] = msg
            ctx.product_info = existing
            await self.memory.save("product", existing)
            return

        # 真的什么都没有 → 追问
        ctx.intent = "chitchat"
        lang_name = "Chinese" if lang == "zh" else "English"
        from app.agent.engine.llm_adapter import TaskTier
        resp = await self.llm.generate(
            system_prompt=f"You are CrabRes, an AI growth agent. The user sent a short message. Respond warmly in {lang_name}, 1-2 sentences. Gently ask what product they're working on.",
            messages=[{"role": "user", "content": msg}],
            tier=TaskTier.PARSING,
            max_tokens=100,
        )
        ctx.direct_reply = resp.content

    # ===== Stage 2: RESEARCH =====
    async def _stage_research(self, ctx: OrchestratorContext) -> AsyncIterator[dict]:
        """
        研究阶段 — 代码控制调用次数上限，LLM 决定搜什么
        
        策略：
        1. 先做 1-2 次确定性搜索（基于产品名/描述）
        2. 如果有 URL，自动 browse
        3. 剩余配额让 LLM 决定补充搜索什么
        4. 最多 MAX_RESEARCH_TOOL_CALLS 次，最多 MAX_RESEARCH_TIME_SEC 秒
        """
        if not ctx.has_product_info and ctx.intent not in ("tool_request", "followup"):
            # 没有产品信息，跳过研究
            return

        yield {"type": "status", "content": "Researching your product market..."}
        
        t0 = time.time()
        product_desc = ctx.product_info.get("raw_description", ctx.user_message)
        product_name = ctx.product_info.get("name", "")
        product_url = ctx.product_info.get("url", "")
        target_platforms = ctx.product_info.get("target_platforms", [])

        # --- 浏览器优先：如果有 URL，先用浏览器打开获取第一手数据 ---
        import re
        urls_in_msg = re.findall(r'https?://\S+', ctx.user_message)
        if not urls_in_msg and product_url:
            urls_in_msg = [product_url]
        
        for url in urls_in_msg[:1]:
            if ctx.tool_call_count >= self.MAX_RESEARCH_TOOL_CALLS:
                break
            yield {"type": "status", "content": f"Browsing {url[:60]}..."}
            yield {"type": "browser_event", "action": "navigating", "url": url}
            browse_result = await self._safe_tool_call("browse_website", {"url": url}, timeout=90.0)
            if browse_result and not browse_result.get("error"):
                ctx.browse_results.append({"url": url, "result": browse_result})
                ctx.tool_call_count += 1
                yield {
                    "type": "browser_event", "action": "loaded", "url": url,
                    "title": browse_result.get("title", ""),
                    "screenshot_path": browse_result.get("screenshot_path", ""),
                    "content_preview": browse_result.get("content_preview", "")[:200],
                }
            else:
                yield {"type": "browser_event", "action": "failed", "url": url,
                       "error": str(browse_result.get("error", "unknown"))[:100]}

        # --- LLM 自主决定所有搜索查询 ---
        # 给模型充分的自主权：它决定搜什么、用什么工具
        # 代码只控制上限（MAX_RESEARCH_TOOL_CALLS 次，MAX_RESEARCH_TIME_SEC 秒）
        remaining_calls = self.MAX_RESEARCH_TOOL_CALLS - ctx.tool_call_count
        if remaining_calls > 0:
            search_plan = await self._llm_plan_research(ctx, remaining_calls)
            
            for step in search_plan:
                if ctx.tool_call_count >= self.MAX_RESEARCH_TOOL_CALLS:
                    break
                if time.time() - t0 > self.MAX_RESEARCH_TIME_SEC:
                    break
                
                tool_name = step.get("tool", "web_search")
                query = step.get("query", "")
                if not query:
                    continue
                
                yield {"type": "status", "content": f"Searching: {query[:60]}..."}
                
                if tool_name == "social_search":
                    r = await self._safe_tool_call("social_search", {
                        "query": query, "platforms": ["reddit", "x", "hackernews"],
                    })
                else:
                    r = await self._safe_tool_call("web_search", {"query": query, "num_results": 5})
                
                if r and not r.get("error"):
                    ctx.search_results.append({"tool": tool_name, "query": query, "result": r})
                    ctx.tool_call_count += 1

        # 自动保存竞品到记忆
        await self._auto_save_competitors(ctx)

        logger.info(f"RESEARCH stage: {ctx.tool_call_count} tool calls, {len(ctx.search_results)} search results, {len(ctx.browse_results)} pages browsed, {int(time.time()-t0)}s")

    # ===== Stage 3: EXPERT =====
    async def _stage_expert(self, ctx: OrchestratorContext) -> AsyncIterator[dict]:
        """
        专家圆桌 — 代码选人，专家各自分析，支持分批执行
        
        入口条件：至少有 MIN_RESEARCH_FOR_EXPERT 条搜索结果
        """
        useful_results = [
            r for r in ctx.search_results
            if isinstance(r.get("result"), dict) and not r["result"].get("error")
        ]
        
        if len(useful_results) < self.MIN_RESEARCH_FOR_EXPERT:
            logger.info(f"EXPERT stage skipped: only {len(useful_results)} useful results (need {self.MIN_RESEARCH_FOR_EXPERT})")
            return

        yield {"type": "status", "content": "Assembling expert roundtable..."}

        # 代码控制：根据产品类型选专家
        from app.agent.engine.context_engine import select_roundtable_experts, get_expert_execution_order
        product_type = ctx.product_info.get("type", "default")
        expert_ids = select_roundtable_experts(product_type, ctx.user_message, max_experts=self.MAX_EXPERTS)
        ctx.expert_ids_used = expert_ids

        # 构建研究数据摘要（给专家看）
        research_summary = self._build_research_summary(ctx)

        # 构建专家任务
        lang = "Chinese" if ctx.language == "zh" else "English"
        target_platforms = ctx.product_info.get("target_platforms", [])
        platform_instruction = ""
        if target_platforms:
            platform_instruction = (
                f"\n\n## TARGET PLATFORMS (user specified): {', '.join(target_platforms)}\n"
                f"Focus your analysis on these platforms ONLY. Do not suggest other platforms.\n"
                f"CRITICAL: 'X' or 'x' = X/Twitter (formerly Twitter), NOT 小红书.\n"
                f"Write content templates in the platform's native language:\n"
                f"- Reddit/X/Twitter/ProductHunt/HackerNews → English\n"
                f"- 小红书/微博/知乎 → Chinese\n"
            )
        
        task = (
            f"Analyze this product and create a growth strategy based on the research data. "
            f"Respond in {lang} for explanations, but write any content drafts/templates "
            f"in the language of the target platform (e.g., English for Reddit/X, Chinese for 小红书).\n\n"
            f"Product: {json.dumps(ctx.product_info, ensure_ascii=False, default=str)[:500]}\n\n"
            f"Research data:\n{research_summary}\n\n"
            f"User request: {ctx.user_message}"
            f"{platform_instruction}"
        )

        # 分批执行（依赖关系）
        batches = get_expert_execution_order(expert_ids)
        
        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                yield {"type": "status", "content": f"Round {batch_idx + 1}: {len(batch)} experts analyzing with prior insights..."}

            # 并行执行同一批的专家
            async def _consult_one(eid: str) -> tuple[str, str]:
                expert = self.experts.get(eid)
                if not expert:
                    return eid, f"Expert {eid} not available"
                try:
                    # 注入前批专家的观点
                    enriched_task = task
                    if ctx.expert_outputs:
                        enriched_task += "\n\n## Other experts' views (challenge or build on these):\n"
                        for ok, ov in ctx.expert_outputs.items():
                            if ok != eid:
                                enriched_task += f"- {ok}: {ov[:300]}\n"
                    
                    # 构建专家上下文
                    from app.agent.engine.context_engine import build_expert_context
                    expert_context = build_expert_context(eid, {
                        "product": ctx.product_info,
                        "tool_results": [{"tool": r["tool"], "result": r["result"]} for r in ctx.search_results],
                        "expert_outputs": ctx.expert_outputs,
                        "user_message": ctx.user_message,
                    }, enriched_task)
                    
                    result = await asyncio.wait_for(
                        expert.analyze(expert_context, enriched_task),
                        timeout=self.EXPERT_TIMEOUT_SEC,
                    )
                    return eid, result
                except asyncio.TimeoutError:
                    return eid, f"[{eid}] Analysis timed out"
                except Exception as e:
                    return eid, f"[{eid}] Error: {str(e)[:100]}"

            tasks = [_consult_one(eid) for eid in batch]
            for coro in asyncio.as_completed(tasks):
                eid, result = await coro
                ctx.expert_outputs[eid] = result
                
                expert = self.experts.get(eid)
                expert_name = expert.name if expert else eid
                yield {"type": "expert_thinking", "expert_id": eid, "content": result}

        logger.info(f"EXPERT stage: {len(ctx.expert_outputs)} experts consulted: {list(ctx.expert_outputs.keys())}")

    # ===== Stage 4: SYNTHESIZE =====
    async def _stage_synthesize(self, ctx: OrchestratorContext) -> AsyncIterator[dict]:
        """
        CGO 综合 — 将所有数据合成最终策略
        
        如果没有专家输出（研究数据不足），直接基于搜索结果给基础建议
        """
        yield {"type": "status", "content": "CGO synthesizing growth strategy..."}

        from app.agent.engine.llm_adapter import TaskTier
        lang = "Chinese (中文)" if ctx.language == "zh" else "English"
        
        research_summary = self._build_research_summary(ctx)
        
        if ctx.expert_outputs:
            # 有专家输出 → 完整综合
            expert_summary = ""
            for eid, output in ctx.expert_outputs.items():
                expert = self.experts.get(eid)
                name = expert.name if expert else eid
                expert_summary += f"\n### {name} ({eid}):\n{output[:1500]}\n"

            synthesis_prompt = self._build_synthesis_prompt(ctx, lang, expert_summary, research_summary)
            
            response = await self.llm.generate(
                system_prompt=synthesis_prompt,
                messages=[{"role": "user", "content": ctx.user_message}],
                tier=TaskTier.CRITICAL,
                max_tokens=4096,
            )
            ctx.synthesis = response.content
        else:
            # 没有专家输出 → 基于搜索结果的轻量回复
            light_prompt = f"""You are CrabRes, an AI growth agent. Respond in {lang}.

You searched for information about the user's product but didn't have enough data for a full expert analysis.
Based on what you found, give 3-4 specific, actionable suggestions.

Research data:
{research_summary[:2000]}

Product info:
{json.dumps(ctx.product_info, ensure_ascii=False, default=str)[:500]}

RULES:
- Be specific: name actual platforms, subreddits, competitor names found in research
- Be concise: 200-400 words max
- End with ONE specific question to help you do deeper research next time
- Language: Respond in {lang} for explanations, but write content templates in the target platform's language
"""
            response = await self.llm.generate(
                system_prompt=light_prompt,
                messages=[{"role": "user", "content": ctx.user_message}],
                tier=TaskTier.THINKING,
                max_tokens=1500,
            )
            ctx.synthesis = response.content

        # 输出综合结果
        yield {"type": "message", "content": ctx.synthesis}

        # 保存到记忆
        await self.memory.save(f"growth_plan_{self.loop.state.session_id}", {
            "content": ctx.synthesis,
            "updated_at": time.time(),
        }, category="strategy")

    # ===== Stage 5: DELIVER =====
    async def _stage_deliver(self, ctx: OrchestratorContext) -> AsyncIterator[dict]:
        """
        生成交付物 — 竞品报告 / 内容草稿 / 30天计划 / Playbook
        
        入口条件：有综合输出 + 至少 MIN_RESEARCH_FOR_DELIVER 条有效搜索结果
        """
        useful_results = [
            r for r in ctx.search_results
            if isinstance(r.get("result"), dict) and not r["result"].get("error")
        ]
        
        if not ctx.synthesis or len(useful_results) < self.MIN_RESEARCH_FOR_DELIVER:
            logger.info("DELIVER stage skipped: insufficient data")
            return

        # 产品信息质量门控
        product_name = ctx.product_info.get("name", "")
        product_desc = ctx.product_info.get("description", ctx.product_info.get("raw_description", ""))
        if not product_name and len(str(product_desc)) < 20:
            logger.info("DELIVER stage skipped: product info too vague")
            return

        yield {"type": "status", "content": "Preparing deliverables..."}

        try:
            # 确保 workspace 目录在持久化路径上
            # Render Disk 挂载到 /data 时，文件不会在部署后丢失
            import os
            persistent_base = os.environ.get("RENDER_DISK_PATH", "")
            if persistent_base:
                workspace_path = Path(persistent_base) / "workspace"
                workspace_path.mkdir(parents=True, exist_ok=True)
                # 同步到持久化路径
                import shutil
                src_workspace = Path(".crabres/memory/workspace")
                if src_workspace.exists():
                    for f in src_workspace.rglob("*"):
                        if f.is_file():
                            dest = workspace_path / f.relative_to(src_workspace)
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, dest)
            
            deliverables = await self.loop._generate_deliverables(
                context={
                    "product": ctx.product_info,
                    "tool_results": [{"tool": r["tool"], "result": r["result"]} for r in ctx.search_results],
                    "user_message": ctx.user_message,
                },
                strategy_response=ctx.synthesis,
                expert_results=ctx.expert_outputs,
            )
            
            if deliverables:
                ctx.deliverables = deliverables
                files_msg_parts = []
                for d in deliverables:
                    files_msg_parts.append(f"**{d['name']}**: {d['desc']}")
                    # 推送文件创建事件 → 前端自动刷新文件树
                    yield {
                        "type": "file_created",
                        "path": d.get("path", ""),
                        "name": d.get("name", ""),
                    }
                
                files_msg = "\n".join(f"- {p}" for p in files_msg_parts)
                yield {
                    "type": "message",
                    "content": f"I've prepared these for you:\n\n{files_msg}\n\nYou can find them in your workspace.",
                }
        except Exception as e:
            logger.warning(f"DELIVER stage failed (non-fatal): {e}")

    # ===== 辅助方法 =====

    async def _safe_tool_call(self, tool_name: str, args: dict, timeout: float = 30.0) -> Optional[dict]:
        """安全的工具调用 — 带超时和错误处理"""
        tool = self.tools.get(tool_name)
        if not tool:
            logger.warning(f"Tool {tool_name} not found")
            return None
        try:
            result = await asyncio.wait_for(
                tool.execute(**args),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Tool {tool_name} timed out ({timeout}s)")
            return {"error": f"timeout after {timeout}s"}
        except Exception as e:
            logger.warning(f"Tool {tool_name} failed: {e}")
            return {"error": str(e)[:200]}

    async def _llm_plan_research(self, ctx: OrchestratorContext, max_steps: int) -> list[dict]:
        """让 LLM 规划整个搜索策略 — 模型决定搜什么、用什么工具
        
        返回: [{"tool": "web_search"|"social_search", "query": "..."}, ...]
        """
        from app.agent.engine.llm_adapter import TaskTier
        
        target_platforms = ctx.product_info.get("target_platforms", [])
        budget = ctx.product_info.get("monthly_budget", ctx.product_info.get("budget", ""))
        goal = ctx.product_info.get("growth_target", ctx.product_info.get("goal", ""))
        
        # 已有的搜索结果摘要
        existing = ""
        if ctx.search_results:
            existing = "\nAlready searched:\n" + "\n".join(
                f"- [{r.get('tool','')}] {r.get('query','')}" for r in ctx.search_results
            )
        if ctx.browse_results:
            existing += "\nAlready browsed:\n" + "\n".join(
                f"- {br.get('url','')} → {br.get('result',{}).get('title','')}" for br in ctx.browse_results
            )
        
        prompt = f"""You are a growth research planner. Plan up to {max_steps} search queries for this product.

Product: {ctx.product_info.get('name', '')} — {ctx.product_info.get('raw_description', ctx.user_message)[:300]}
User request: {ctx.user_message}
Target platforms: {', '.join(target_platforms) if target_platforms else 'not specified'}
Budget: {budget or 'not specified'}
Growth goal: {goal or 'not specified'}
{existing}

Available tools:
- web_search: General web search (Google). Good for competitors, market data, articles.
- social_search: Search Reddit, X/Twitter, HackerNews. Good for user discussions, community insights.

Return a JSON array of search steps. Each step: {{"tool": "web_search"|"social_search", "query": "concise search query"}}
Be specific: use competitor names, platform names, concrete terms. Don't repeat what's already searched.
Return ONLY the JSON array, no explanation."""

        try:
            response = await self.llm.generate(
                system_prompt="You are a research planner. Return only a JSON array.",
                messages=[{"role": "user", "content": prompt}],
                tier=TaskTier.PARSING,
                max_tokens=300,
            )
            raw = response.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
                if raw.startswith("json"):
                    raw = raw[4:]
            steps = json.loads(raw)
            if isinstance(steps, list):
                return steps[:max_steps]
        except Exception as e:
            logger.debug(f"LLM plan research failed: {e}, falling back to default queries")
        
        # 降级：如果 LLM 规划失败，用确定性查询
        fallback = []
        product_name = ctx.product_info.get("name", "")
        if product_name:
            fallback.append({"tool": "web_search", "query": f"{product_name} competitors alternatives 2024"})
        if target_platforms:
            fallback.append({"tool": "social_search", "query": f"{product_name or 'SaaS'} growth {' '.join(target_platforms[:2])}"})
        else:
            fallback.append({"tool": "social_search", "query": f"{product_name or ctx.user_message[:40]} indie developer growth"})
        return fallback[:max_steps]

    async def _auto_save_competitors(self, ctx: OrchestratorContext):
        """从搜索结果中自动提取竞品"""
        # 复用 loop 的方法
        fake_context = {
            "tool_results": [{"tool": r["tool"], "result": r["result"]} for r in ctx.search_results],
        }
        await self.loop._auto_save_competitors_from_results(fake_context)

    def _build_research_summary(self, ctx: OrchestratorContext) -> str:
        """构建研究数据摘要（给专家和 CGO 看）"""
        parts = []
        
        for i, sr in enumerate(ctx.search_results[:5]):
            result = sr.get("result", {})
            if isinstance(result, dict) and not result.get("error"):
                # 提取搜索结果的关键信息
                results_list = result.get("results", [])
                if results_list:
                    items = []
                    for r in results_list[:3]:
                        title = r.get("title", "")
                        url = r.get("url", "")
                        content = r.get("content", "")[:200]
                        items.append(f"  - {title} ({url}): {content}")
                    parts.append(f"Search [{sr.get('tool','')}]: \"{sr.get('query','')}\"\n" + "\n".join(items))
                
                # 社媒搜索的特殊处理
                answer = result.get("answer", "")
                if answer:
                    parts.append(f"Social insight: {answer[:300]}")
        
        for br in ctx.browse_results[:2]:
            result = br.get("result", {})
            if isinstance(result, dict):
                title = result.get("title", "")
                content = result.get("content_preview", "")[:500]
                analysis = result.get("visual_analysis", "")[:300]
                parts.append(f"Browsed {br['url']}: {title}\n{content}\n{analysis}")
        
        return "\n\n".join(parts) if parts else "No research data available."

    def _extract_onboarding_context(self, ctx: OrchestratorContext):
        """从 product_info 或历史消息中提取 onboarding 结构化信息"""
        pi = ctx.product_info
        if not pi:
            return
        
        raw = pi.get("raw_description", "")
        
        # 提取 budget（如果还没有）
        if not pi.get("monthly_budget"):
            import re
            budget_match = re.search(r'(?:budget|预算)[:\s]*\$?(\d+)', raw, re.IGNORECASE)
            if budget_match:
                pi["monthly_budget"] = budget_match.group(1)
        
        # 提取 target users（如果还没有）
        if not pi.get("growth_target"):
            import re
            goal_match = re.search(r'(?:goal|目标)[:\s]*(\d+)\s*(?:users|用户)', raw, re.IGNORECASE)
            if goal_match:
                pi["growth_target"] = goal_match.group(1)
        
        # 提取 product type（如果还没有）
        if not pi.get("type") or pi["type"] == "default":
            import re
            type_match = re.search(r'(?:product type|类型)[:\s]*(\w+)', raw, re.IGNORECASE)
            if type_match:
                pi["type"] = type_match.group(1).lower()
        
        ctx.product_info = pi

    def _detect_target_platforms(self, message: str) -> list[str]:
        """从用户消息中提取目标平台"""
        msg_lower = message.lower()
        platforms = []
        
        # 平台名称映射（用户可能用的各种说法）
        platform_map = {
            # X/Twitter
            "twitter": "X/Twitter",
            "x平台": "X/Twitter",
            "推特": "X/Twitter",
            # 注意：单独的 "x" 需要上下文判断
            
            # Reddit
            "reddit": "Reddit",
            
            # 小红书
            "小红书": "小红书",
            "xiaohongshu": "小红书",
            "xhs": "小红书",
            "red note": "小红书",
            "rednote": "小红书",
            
            # Product Hunt
            "product hunt": "Product Hunt",
            "producthunt": "Product Hunt",
            "ph": "Product Hunt",
            
            # Hacker News
            "hacker news": "Hacker News",
            "hackernews": "Hacker News",
            "hn": "Hacker News",
            
            # LinkedIn
            "linkedin": "LinkedIn",
            "领英": "LinkedIn",
            
            # 微博
            "微博": "微博",
            "weibo": "微博",
            
            # 知乎
            "知乎": "知乎",
            "zhihu": "知乎",
            
            # YouTube
            "youtube": "YouTube",
            "油管": "YouTube",
            
            # 抖音/TikTok
            "抖音": "抖音/TikTok",
            "tiktok": "抖音/TikTok",
            "douyin": "抖音/TikTok",
        }
        
        for keyword, platform in platform_map.items():
            if keyword in msg_lower and platform not in platforms:
                platforms.append(platform)
        
        # 特殊处理：单独的 "x" 在增长/策略上下文中 = X/Twitter
        # "针对x的增长策略" / "在x上推广" / "x platform"
        import re
        x_patterns = [
            r"针对\s*x\s*的", r"在\s*x\s*上", r"x\s*platform",
            r"x\s*增长", r"x\s*策略", r"x\s*推广",
            r"for\s+x", r"on\s+x", r"x\s+growth",
        ]
        if "X/Twitter" not in platforms:
            for pattern in x_patterns:
                if re.search(pattern, msg_lower):
                    platforms.append("X/Twitter")
                    break
        
        return platforms

    def _detect_product_info(self, message: str) -> bool:
        """检测消息是否包含产品信息（复用 loop 的逻辑）"""
        return self.loop._detect_product_info(message)

    def _self_awareness_prompt(self, lang: str) -> str:
        lang_name = "Chinese (中文)" if lang == "zh" else "English"
        return f"""You are CrabRes, an AI growth strategy agent AND a product yourself. Respond in {lang_name}.

About yourself:
- You are a SaaS product (crab-researcher.vercel.app) that helps indie developers and small teams grow their products
- You have 13 AI expert advisors covering market research, content strategy, social media, paid ads, partnerships, etc.
- You can browse the web, search social media, analyze competitors, and execute growth actions
- You were built by an indie developer — you understand the struggle

Answer naturally and warmly. 2-3 sentences max. Then ask what they're building."""

    def _build_synthesis_prompt(self, ctx: OrchestratorContext, lang: str, expert_summary: str, research_summary: str) -> str:
        """构建 CGO 综合 prompt"""
        return f"""You are CrabRes's Chief Growth Officer. You just held a roundtable with {len(ctx.expert_outputs)} experts.

## LANGUAGE STRATEGY
- **UI/conversation language**: Respond to the user in {lang}.
- **Content drafts language**: Match the TARGET PLATFORM's primary language:
  - Reddit / X (Twitter) / Product Hunt / Hacker News → English
  - 小红书 / 微博 / 知乎 / 微信公众号 → Chinese
  - LinkedIn → English (or match user's market)
- When presenting playbooks, use {lang} for explanations but write content templates in the platform's native language.
- Example: If user speaks Chinese but targets Reddit, explain strategy in Chinese, but write the Reddit post template in English.

## ROUNDTABLE THREE-PHASE STRUCTURE

### Phase 1: Market Intelligence (数据先行)
- Open with 2-3 SPECIFIC data points from the research (competitor names, traffic numbers, pricing).
- Cite which expert found what.

### Phase 2: Expert Debate (专家争论)
- Highlight the KEY DISAGREEMENT between experts.
- Explain YOUR decision as CGO and why.

### Phase 3: Execution Playbooks (可执行计划)
- Present 2-3 Playbooks ranked by priority.
- Each Playbook MUST have: Name, Why this channel (with data), Phase 1-3 (Prep/Execute/Track), Budget, Expected outcome, Ready-to-use template.

## MANDATORY ELEMENTS
1. **Hard Truth**: One uncomfortable truth. Label: ⚠️ **Hard truth:**
2. **Quick Win**: One thing they can do TODAY.
3. **CGO Verdict**: Your #1 priority and why.

## ANTI-PATTERNS (violation = failure)
❌ Generic advice that could apply to any product
❌ Listing 10 channels instead of going deep on 2-3
❌ Saying "based on my analysis" without showing data
❌ Skipping the Hard Truth

## Research Data
{research_summary[:3000]}

## Expert Outputs
{expert_summary}

## User Request
{ctx.user_message}

## Target Platforms (user specified)
{', '.join(ctx.product_info.get('target_platforms', [])) or 'Not specified — suggest based on product type'}

## Product Info
{json.dumps(ctx.product_info, ensure_ascii=False, default=str)[:500]}

## PLATFORM-SPECIFIC RULES
- If user specified target platforms, focus ALL playbooks on those platforms
- "X" or "x" means X/Twitter (formerly Twitter), NOT 小红书
- Reddit: English-only community, posts MUST be in English
- X/Twitter: English for global audience, Chinese only if targeting Chinese market
- 小红书: Chinese-only platform, posts MUST be in Chinese with 小红书 style (emoji-heavy, 种草风格)
- Product Hunt: English-only
- Hacker News: English-only, technical audience"""

    def _fallback_reply(self, ctx: OrchestratorContext, error: str) -> str:
        """兜底回复"""
        lang = ctx.language
        if lang == "zh":
            return (
                "抱歉，处理过程中遇到了问题。"
                "能告诉我你的产品具体是做什么的吗？一句话就够，我立刻开始研究。"
            )
        return (
            "Sorry, I ran into an issue during processing. "
            "Could you tell me what your product does? Even one sentence — I'll start researching immediately."
        )

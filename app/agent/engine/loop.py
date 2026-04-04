"""
CrabRes Agent Loop — ReAct 核心循环

学习自 Claude Code 源码泄露的设计：
- while(true) 状态机，永不崩溃
- think → act → observe 循环
- 流式工具执行（工具收到就执行，不等完整响应）
- 并发安全工具可并行运行
- 写前日志（进程被杀也能恢复）
- Token 预算管理（动态分配给不同专家）
- 3 级恢复路径（压缩→折叠→升级）
"""

import asyncio
import logging
import time
import json
from typing import Any, Optional, AsyncIterator
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LoopPhase(str, Enum):
    """Agent 所处阶段"""
    INTAKE = "intake"                # 信息收集：了解用户产品
    VALIDATION = "validation"        # 验证：产品方向是否可行
    RESEARCH = "research"            # 研究：竞品/用户/渠道
    ANALYSIS = "analysis"            # 分析：汇总研究结果
    CONFIRM = "confirm"              # 确认：与用户确认方向
    STRATEGY = "strategy"            # 策略：制定增长计划
    EXECUTION = "execution"          # 执行：生成物料
    REVIEW = "review"                # 复盘：追踪效果并迭代


class ActionType(str, Enum):
    THINK = "think"          # 内部推理
    TOOL_CALL = "tool_call"  # 调用工具
    EXPERT = "expert"        # 调度单个专家
    ROUNDTABLE = "roundtable"  # 圆桌：并行调度多个专家 + Coordinator 综合
    ASK_USER = "ask_user"    # 向用户提问
    OUTPUT = "output"        # 输出给用户
    WAIT = "wait"            # 等待用户输入/外部事件


@dataclass
class AgentAction:
    """Agent 的一次行动"""
    type: ActionType
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    expert_id: Optional[str] = None
    expert_ids: list[str] = field(default_factory=list)  # 圆桌模式：多个专家 ID
    metadata: dict = field(default_factory=dict)
    parallel_tools: list = field(default_factory=list)  # 并发执行的额外工具


@dataclass 
class LoopState:
    """Agent Loop 的运行状态"""
    session_id: str
    phase: LoopPhase = LoopPhase.INTAKE
    turn_count: int = 0
    total_tokens_used: int = 0
    token_budget: int = 100_000
    actions_history: list[AgentAction] = field(default_factory=list)
    pending_user_tasks: list[dict] = field(default_factory=list)
    expert_outputs: dict[str, Any] = field(default_factory=dict)
    is_waiting_for_user: bool = False
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)


class AgentLoop:
    """
    CrabRes 核心 Agent 循环
    """

    def __init__(self, session_id: str, llm_service, tool_registry, expert_pool, memory):
        self.state = LoopState(session_id=session_id)
        self.llm = llm_service
        self.tools = tool_registry
        self.experts = expert_pool
        self.memory = memory
        self._running = False
        self._max_consecutive_errors = 3
        self._error_count = 0
        self._max_loop_iterations = 10
        self._message_history: list[dict] = []

        # Agent workspace 沙箱 — Agent 的"工作区"
        from pathlib import Path
        workspace_base = Path(str(memory.base_dir)).parent / "workspace"
        for subdir in ["drafts", "assets", "outreach", "reports", "experiments"]:
            (workspace_base / subdir).mkdir(parents=True, exist_ok=True)
        self.workspace = workspace_base

        # Trust Levels — 渐进自主权
        from app.agent.trust import TrustManager
        self.trust = TrustManager(memory)

        # Mood Sensing — 情绪感知
        from app.agent.engine.mood_sensing import MoodSensor
        self.mood_sensor = MoodSensor()

        # Deep Strategy — ULTRAPLAN 异步深度策略
        from app.agent.engine.deep_strategy import get_deep_strategy_engine
        self.deep_strategy = get_deep_strategy_engine()

        # Prompt Cache — 上下文复用缓存
        from app.agent.engine.prompt_cache import PromptCache
        self.prompt_cache = PromptCache()

    async def run(self, user_message: str, language: str = "en"):
        """
        处理一条用户消息，yield 流式输出
        
        Args:
            user_message: 用户消息
            language: 用户选择的语言 ("en" 或 "zh")，从前端 Settings 传入
        """
        self._running = True
        self._language = language  # 存储供后续方法使用
        self.state.turn_count += 1
        self.state.last_active_at = time.time()
        self.state.is_waiting_for_user = False

        # 检测 @expert_id 私聊模式
        import re
        at_match = re.match(r'^@(\w+)\s+(.+)', user_message.strip(), re.DOTALL)
        if at_match:
            expert_id = at_match.group(1).lower()
            expert_task = at_match.group(2).strip()
            expert = self.experts.get(expert_id)
            if expert:
                # 直接和专家对话，跳过 Coordinator
                yield {"type": "status", "content": f"Connecting you directly with {expert.name}..."}
                yield {"type": "expert_thinking", "expert_id": expert_id, "content": f"{expert.name} is analyzing your question..."}

                # 写前日志
                await self._write_ahead_log(user_message)
                self._message_history.append({"role": "user", "content": user_message})

                # 构建上下文
                context = await self._build_context(user_message)

                # 直接调度专家
                try:
                    expert_output = await expert.analyze(context, expert_task)
                    self._message_history.append({"role": "assistant", "content": f"[Expert: {expert_id}] {expert_output[:1500]}"})
                    self.state.expert_outputs[expert_id] = expert_output
                    yield {"type": "expert_thinking", "expert_id": expert_id, "content": expert_output}
                except Exception as e:
                    yield {"type": "error", "content": f"Expert {expert_id} encountered an error: {str(e)[:200]}"}

                await self._persist_state()
                return

        # 记录 Trust Level session
        await self.trust.record_session()
        trust_permissions = await self.trust.get_permissions()

        # 🧠 Deep Strategy 触发检测（ULTRAPLAN）
        from app.agent.engine.deep_strategy import should_trigger_deep_strategy
        if should_trigger_deep_strategy(user_message):
            yield {"type": "status", "content": "Initiating Deep Strategy session (background)..."}
            try:
                job = await self.deep_strategy.create_job(
                    user_id=str(self.memory.base_dir).split("/")[-1],
                    session_id=self.state.session_id,
                    request=user_message,
                    llm_service=self.llm,
                    tool_registry=self.tools,
                    expert_pool=self.experts,
                    memory=self.memory,
                )
                yield {
                    "type": "message",
                    "content": (
                        f"🔬 **Deep Strategy Session launched** (ID: `{job.id}`)\n\n"
                        f"This is a complex request that requires thorough research. "
                        f"I'm running a full expert roundtable in the background with 8 specialists.\n\n"
                        f"**What's happening:**\n"
                        f"1. Deep market research (5-8 search queries)\n"
                        f"2. Full expert roundtable (8 experts analyzing in parallel)\n"
                        f"3. CGO synthesizing final comprehensive strategy\n\n"
                        f"This will take 2-5 minutes. I'll notify you when it's ready.\n"
                        f"In the meantime, feel free to ask me anything else!"
                    ),
                }
                self._message_history.append({"role": "user", "content": user_message})
                self._message_history.append({"role": "assistant", "content": f"[Deep Strategy launched: {job.id}]"})
                await self._persist_state()
                return
            except Exception as e:
                logger.error(f"Deep Strategy failed to launch: {e}")
                yield {"type": "status", "content": "Deep strategy unavailable, proceeding normally..."}

        # 🎭 Mood Sensing — 情绪感知
        mood_signal = self.mood_sensor.detect(user_message)
        mood_injection = ""
        if mood_signal:
            mood_injection = self.mood_sensor.get_prompt_injection(mood_signal)
            logger.info(f"Mood sensing: {mood_signal.mood.value} (confidence={mood_signal.confidence:.2f})")

        # ========== 硬编码保底层（不依赖 LLM 遵循指令）==========
        
        # 1. 自我认知注入：如果用户问"你是什么"或提到 crabres，直接回答不走 LLM 决策
        msg_lower = user_message.lower().strip()
        self_awareness_triggers = [
            "what are you", "who are you", "你是什么", "你是谁",
            "what do you do", "你做什么", "介绍一下你", "introduce yourself",
        ]
        if any(t in msg_lower for t in self_awareness_triggers):
            self._message_history.append({"role": "user", "content": user_message})
            lang = self._language
            if lang == "zh":
                reply = "我是 CrabRes，一个 AI 增长策略 Agent。我帮独立开发者和小团队研究市场、分析竞品、制定可执行的增长计划。告诉我你在做什么产品，我就开始工作。"
            else:
                reply = "I'm CrabRes — an AI growth agent. I research your market, analyze competitors, and create actionable growth plans. Tell me what you're building and I'll get to work."
            self._message_history.append({"role": "assistant", "content": reply})
            yield {"type": "message", "content": reply}
            await self._persist_state()
            return

        # 2. 产品信息检测：用户消息包含足够产品信息 → 直接进入 research，不让 LLM 决定"要不要先问"
        import re
        has_product_info = self._detect_product_info(user_message)
        product_in_memory = await self.memory.load("product")
        has_product_in_memory = bool(product_in_memory and product_in_memory.get("raw_description"))
        
        # 3. ask_user 计数器：连续 ask 不超过 1 次
        self._ask_count = getattr(self, '_ask_count', 0)
        
        # 4. 已 scrape 的 URL 去重集合
        if not hasattr(self, '_scraped_urls'):
            self._scraped_urls = set()

        # ========== 保底层结束 ==========

        # 如果是新启动的会话（或进程重启），尝试从磁盘加载历史
        if not self._message_history:
            await self._load_state()

        # 写前日志（学 Claude Code）
        await self._write_ahead_log(user_message)

        # 自动提取和存储产品信息（如果用户消息包含产品描述）
        await self._maybe_save_product_info(user_message)

        # 自动检测用户贴回的社媒链接并开始追踪
        await self._maybe_track_posted_url(user_message)

        # 加载记忆上下文
        context = await self._build_context(user_message)
        context["trust"] = trust_permissions
        context["mood_injection"] = mood_injection  # 情绪感知注入

        iteration = 0
        tool_call_count = 0  # 追踪工具调用次数

        # ========== 主动搜索层（不等 LLM 决定）==========
        # 如果检测到产品信息，直接启动搜索，不让 Coordinator 有机会选择 ask_user
        if has_product_info and not context.get("tool_results"):
            yield {"type": "status", "content": "Researching your product market..."}

            # 构建搜索查询
            search_query = user_message[:120]
            # 如果用户提到了竞品，搜索竞品
            competitor_keywords = ['竞品', '竞争', 'competitor', 'competing', 'rival', 'alternative', 'vs']
            is_competitor_mention = any(kw in msg_lower for kw in competitor_keywords)

            if is_competitor_mention:
                # 提取竞品名（取掉竞品关键词后的实体词）
                import re as _re
                # 去掉常见修饰词，剩下的就是竞品名
                competitor_name = _re.sub(
                    r'(是|竞品|竞争对手|对手|competitor|is a|is my|the)', '',
                    user_message, flags=_re.IGNORECASE
                ).strip()
                if competitor_name:
                    search_query = f"{competitor_name} product features pricing reviews"

            # 执行预搜索
            pre_search_action = AgentAction(
                type=ActionType.TOOL_CALL,
                content="Pre-research: searching product market",
                tool_name="web_search",
                tool_args={"query": search_query, "num_results": 5},
            )
            pre_result = await self._execute_tool(pre_search_action)
            context = await self._incorporate_result(context, pre_search_action, pre_result)
            result_summary = json.dumps(pre_result, ensure_ascii=False, default=str)[:2000]
            self._message_history.append({
                "role": "assistant",
                "content": f"[Tool: web_search] Result: {result_summary}",
            })
            tool_call_count += 1
            self.state.actions_history.append(pre_search_action)

            # 如果是竞品查询且找到了URL，自动 scrape 竞品网站
            if is_competitor_mention and pre_result and isinstance(pre_result, dict):
                results = pre_result.get("results", [])
                if results and results[0].get("url"):
                    competitor_url = results[0]["url"]
                    yield {"type": "status", "content": f"Analyzing competitor: {competitor_url[:60]}..."}
                    scrape_action = AgentAction(
                        type=ActionType.TOOL_CALL,
                        content="Scraping competitor website",
                        tool_name="scrape_website",
                        tool_args={"url": competitor_url},
                    )
                    scrape_result = await self._execute_tool(scrape_action)
                    context = await self._incorporate_result(context, scrape_action, scrape_result)
                    scrape_summary = json.dumps(scrape_result, ensure_ascii=False, default=str)[:2000]
                    self._message_history.append({
                        "role": "assistant",
                        "content": f"[Tool: scrape_website] Result: {scrape_summary}",
                    })
                    tool_call_count += 1
                    self.state.actions_history.append(scrape_action)
                    if competitor_url:
                        self._scraped_urls.add(competitor_url)

            # 自动提取并保存竞品到记忆（不依赖 LLM，从搜索结果中提取）
            await self._auto_save_competitors_from_results(context)

            logger.info(f"Proactive search completed: {tool_call_count} tool calls before Coordinator")
        # ========== 主动搜索层结束 ==========

        while self._running and iteration < self._max_loop_iterations:
            iteration += 1
            try:
                # 🔥 强制停止搜索：如果已经做了 3+ 轮工具调用，注入强制指令
                if tool_call_count >= 3:
                    tool_results = context.get("tool_results", [])
                    num_results = len(tool_results)
                    force_msg = {
                        "role": "user",
                        "content": (
                            f"[SYSTEM OVERRIDE] You have completed {tool_call_count} research rounds "
                            f"and collected {num_results} data points. STOP SEARCHING. "
                            f"You MUST now either: (1) call consult_roundtable with 3-4 experts to analyze the data, "
                            f"or (2) call output with your final strategy. "
                            f"Do NOT call any more search tools. Research phase is OVER."
                        ),
                    }
                    # 注入到 context messages 的末尾
                    msgs = context.get("messages", [])
                    if not any("[SYSTEM OVERRIDE]" in m.get("content", "") for m in msgs):
                        msgs.append(force_msg)
                        context["messages"] = msgs
                        logger.info(f"Injected SYSTEM OVERRIDE: {tool_call_count} tool calls done, forcing output")

                # 1. THINK: 让 Coordinator（首席增长官）决定下一步
                yield {"type": "status", "content": "Coordinator deciding next tactical move..."}
                decision = await self._think(context)

                # ========== 硬编码决策拦截层 ==========
                
                # 拦截 1: ask_user — 如果有产品信息，第一次就拦截，不允许任何 ask
                if decision.type == ActionType.ASK_USER:
                    self._ask_count += 1
                    if has_product_info or has_product_in_memory:
                        # 有产品信息就不该问 — 立刻强制搜索
                        logger.info(f"OVERRIDE: ask blocked (has product info), forcing web_search")
                        product_desc = user_message if has_product_info else product_in_memory.get("raw_description", "")
                        decision = AgentAction(
                            type=ActionType.TOOL_CALL,
                            content="Researching your product market",
                            tool_name="web_search",
                            tool_args={"query": f"{product_desc[:100]} competitors market analysis"},
                        )
                    elif self._ask_count > 1:
                        # 没有产品信息，但已经问过一次了 — 不再问，给兜底回复
                        logger.info("OVERRIDE: ask_count > 1 without product info → giving helpful output")
                        lang = getattr(self, '_language', 'en')
                        msg = ("告诉我你在做什么产品就行，一句话就够。比如'帮独立开发者增长的AI工具'，我立刻开始研究。"
                               if lang == "zh" else
                               "Just tell me what you're building — even one sentence like 'AI resume tool for job seekers'. I'll start researching immediately.")
                        decision = AgentAction(type=ActionType.OUTPUT, content=msg)
                else:
                    self._ask_count = 0  # 不是 ask → 重置计数
                
                # 拦截 2: 工具去重 — 同一 URL 不重复 scrape
                if decision.type == ActionType.TOOL_CALL and decision.tool_name in ("scrape_website", "browse_website", "deep_scrape"):
                    url = (decision.tool_args or {}).get("url", "")
                    if url and url in self._scraped_urls:
                        logger.info(f"OVERRIDE: URL already scraped, skipping: {url[:60]}")
                        # 跳过重复的 scrape，换成 web_search
                        product_desc = (await self.memory.load("product") or {}).get("raw_description", user_message)
                        decision = AgentAction(
                            type=ActionType.TOOL_CALL,
                            content="Searching for market data",
                            tool_name="web_search",
                            tool_args={"query": f"{product_desc[:80]} market size competitors pricing"},
                        )
                    elif url:
                        self._scraped_urls.add(url)
                
                # 拦截 3: 同一个 web_search query 不重复搜索
                if decision.type == ActionType.TOOL_CALL and decision.tool_name == "web_search":
                    query = (decision.tool_args or {}).get("query", "")
                    if not hasattr(self, '_searched_queries'):
                        self._searched_queries = set()
                    if query and query in self._searched_queries:
                        logger.info(f"OVERRIDE: query already searched, skipping: {query[:60]}")
                        continue  # 跳过这次迭代
                    elif query:
                        self._searched_queries.add(query)

                # ========== 拦截层结束 ==========

                if decision.type == ActionType.OUTPUT:
                    content = decision.content

                    # 🔥 强制圆桌检查：如果做了研究但跳过了专家讨论，强制触发一轮圆桌
                    tool_results = context.get("tool_results", [])
                    has_research = len(tool_results) >= 2
                    has_experts = len(self.state.expert_outputs) > 0
                    if has_research and not has_experts and iteration < self._max_loop_iterations - 2:
                        logger.info("Forcing roundtable: research done but no experts consulted")
                        yield {"type": "status", "content": "Assembling expert roundtable for analysis..."}
                        # 🔥 Harness：根据产品类型智能选择专家
                        from app.agent.engine.context_engine import select_roundtable_experts
                        product_type = context.get("product", {}).get("type", "default")
                        expert_ids = select_roundtable_experts(product_type, context.get("user_message", ""))
                        task = f"Analyze this product and create a growth strategy based on the research data. Product: {context.get('user_message', '')}. Research results available in context."
                        async for evt in self._run_roundtable(expert_ids, task, context):
                            if evt.get("type") == "expert_thinking":
                                eid = evt.get("expert_id", "")
                                self.state.expert_outputs[eid] = evt.get("content", "")
                                context.setdefault("expert_outputs", {})[eid] = evt.get("content", "")
                            yield evt
                        # 圆桌会输出自己的 message，不需要再输出 Coordinator 的
                        break

                    # 自动 Critic 审核（如果输出足够长且是策略内容）
                    if len(content) > 500 and self.state.turn_count >= 2:
                        critic = self.experts.get("critic")
                        if critic:
                            yield {"type": "status", "content": "Strategy Critic reviewing..."}
                            try:
                                review = await critic.analyze(context, f"Review this growth strategy for quality, feasibility, and specificity:\n\n{content[:2000]}")
                                if review and "❌" in review:
                                    # Critic 发现严重问题，加到输出里
                                    content += f"\n\n---\n⚖️ **Critic Review:**\n{review}"
                                    yield {"type": "expert_thinking", "expert_id": "critic", "content": review}
                            except Exception as e:
                                logger.warning(f"Critic review failed: {e}")

                    self._message_history.append({"role": "assistant", "content": content})
                    await self._save_output_to_memory(content)
                    yield {"type": "message", "content": content}
                    break

                elif decision.type == ActionType.ASK_USER:
                    # 需要用户提供信息
                    self._message_history.append({"role": "assistant", "content": decision.content})
                    yield {"type": "question", "content": decision.content}
                    self.state.is_waiting_for_user = True
                    break

                elif decision.type == ActionType.TOOL_CALL:
                    # 2. ACT: 执行工具（支持并发）
                    yield {"type": "status", "content": f"Researching: {decision.content}..."}

                    # 检查是否有多个工具调用需要并发
                    if hasattr(decision, 'parallel_tools') and decision.parallel_tools:
                        # 并发执行所有工具
                        tasks = [self._execute_tool(d) for d in [decision] + decision.parallel_tools]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for j, (d, r) in enumerate(zip([decision] + decision.parallel_tools, results)):
                            if isinstance(r, Exception):
                                r = {"error": str(r)}
                            context = await self._incorporate_result(context, d, r)
                            result_summary = json.dumps(r, ensure_ascii=False, default=str)[:1500]
                            self._message_history.append({
                                "role": "assistant",
                                "content": f"[Tool: {d.tool_name}] Result: {result_summary}",
                            })
                    else:
                        result = await self._execute_tool(decision)
                        context = await self._incorporate_result(context, decision, result)
                        result_summary = json.dumps(result, ensure_ascii=False, default=str)[:2000]
                        self._message_history.append({
                            "role": "assistant",
                            "content": f"[Tool: {decision.tool_name}] Result: {result_summary}",
                        })
                    
                    tool_call_count += 1

                elif decision.type == ActionType.EXPERT:
                    # 调度专家 — 增加模拟"思考片段"让前端可视化更真实
                    expert = self.experts.get(decision.expert_id)
                    expert_name = expert.name if expert else decision.expert_id
                    
                    yield {"type": "status", "content": f"Consulting {expert_name}..."}
                    yield {"type": "expert_thinking", "expert_id": decision.expert_id, "content": f"{expert_name} is analyzing context..."}
                    
                    # 真正的专家分析
                    expert_output = await self._consult_expert(decision, context)
                    context = self._incorporate_expert(context, decision, expert_output)
                    # 把专家输出加入消息历史
                    self._message_history.append({
                        "role": "assistant",
                        "content": f"[Expert: {decision.expert_id}] {expert_output[:1500]}",
                    })
                    yield {
                        "type": "expert_thinking",
                        "expert_id": decision.expert_id,
                        "content": expert_output,
                    }

                elif decision.type == ActionType.ROUNDTABLE:
                    # 圆桌模式：并行调度多个专家 → 收集输出 → Coordinator 综合
                    expert_ids = decision.expert_ids or []
                    if not expert_ids:
                        expert_ids = ["market_researcher", "economist"]

                    yield {"type": "status", "content": f"Assembling roundtable: {len(expert_ids)} experts..."}

                    # 并行调度所有选中的专家
                    async for event in self._run_roundtable(expert_ids, decision.content, context):
                        if event.get("type") == "expert_thinking":
                            # 将专家输出合并到上下文
                            eid = event.get("expert_id", "")
                            content_text = event.get("content", "")
                            self.state.expert_outputs[eid] = content_text
                            context.setdefault("expert_outputs", {})[eid] = content_text
                            self._message_history.append({
                                "role": "assistant",
                                "content": f"[Expert: {eid}] {content_text[:1500]}",
                            })
                        yield event

                elif decision.type == ActionType.THINK:
                    # 内部推理，不输出给用户，但加入历史让 Coordinator 记住
                    context = self._incorporate_thinking(context, decision)
                    self._message_history.append({
                        "role": "assistant",
                        "content": f"[Internal reasoning] {decision.content[:500]}",
                    })

                # 记录行动
                self.state.actions_history.append(decision)
                self._error_count = 0  # 重置错误计数

                # Token 预算检查
                if self.state.total_tokens_used >= self.state.token_budget * 0.9:
                    yield {"type": "warning", "content": "接近 Token 预算上限，正在收敛思考"}
                    self._running = False

            except Exception as e:
                self._error_count += 1
                logger.error(f"Agent loop error (#{self._error_count}): {e}")

                if self._error_count >= self._max_consecutive_errors:
                    yield {
                        "type": "error",
                        "content": f"遇到连续错误，暂停处理。错误信息：{str(e)[:200]}"
                    }
                    break

                # 尝试恢复（学 Claude Code 的 3 级恢复）
                context = await self._try_recover(context, e)

        # 🔥 Fallback: 如果循环用完了但有搜索数据，强制输出
        tool_results = context.get("tool_results", [])
        has_output = any(
            a.type == ActionType.OUTPUT for a in self.state.actions_history
        ) or any(
            a.type == ActionType.ROUNDTABLE for a in self.state.actions_history
        )
        
        if not has_output and len(tool_results) >= 1:
            # 🔥 搜索结果质量门控：过滤掉错误和无效的结果
            useful_results = [
                r for r in tool_results
                if isinstance(r.get("result"), dict)
                and not r["result"].get("error")
                and len(json.dumps(r["result"], default=str)) > 200
            ]
            
            if len(useful_results) >= 2:
                # 有效数据足够 → 正常圆桌
                logger.info(f"Fallback: {len(useful_results)} useful results → launching roundtable")
                yield {"type": "status", "content": "Finalizing analysis with expert roundtable..."}
                
                from app.agent.engine.context_engine import select_roundtable_experts
                product_type = context.get("product", {}).get("type", "default")
                expert_ids = select_roundtable_experts(product_type, context.get("user_message", ""))
                user_msg = context.get("user_message", "")
                task = (
                    f"Analyze this product and create a growth strategy. "
                    f"Product: {user_msg}. "
                    f"We have collected {len(useful_results)} research data points. "
                    f"Synthesize the research into actionable Playbooks."
                )
                
                try:
                    async for evt in self._run_roundtable(expert_ids, task, context):
                        if evt.get("type") == "expert_thinking":
                            eid = evt.get("expert_id", "")
                            self.state.expert_outputs[eid] = evt.get("content", "")
                        yield evt
                except Exception as e:
                    logger.error(f"Fallback roundtable failed: {e}")
                    yield {
                        "type": "message",
                        "content": "I ran into an issue assembling the expert analysis. Could you try again?",
                    }
            else:
                # 搜索结果质量太差 → 不浪费 token 开圆桌，直接用知识库给基础建议
                logger.info(f"Fallback: only {len(useful_results)} useful results → knowledge-based output")
                product_data = context.get("product", {})
                product_desc = product_data.get("raw_description", context.get("user_message", ""))
                
                lang = getattr(self, '_language', 'en')
                if lang == "zh":
                    yield {
                        "type": "message",
                        "content": (
                            f"我搜索了一些市场数据，但结果不够充分来做完整分析。"
                            f"基于你的产品描述，我建议先从以下方向入手：\n\n"
                            f"1. **找到你的用户在哪**：搜索 Reddit/小红书上讨论类似问题的帖子\n"
                            f"2. **看看竞品怎么做的**：找 3 个直接竞品，分析他们的流量来源\n"
                            f"3. **写第一篇内容**：在用户最活跃的社区发一篇真实的分享\n\n"
                            f"能告诉我你的产品具体解决什么问题吗？我可以做更精准的研究。"
                        ),
                    }
                else:
                    yield {
                        "type": "message",
                        "content": (
                            f"I searched for market data but didn't find enough for a full analysis. "
                            f"Based on what I know, here's where to start:\n\n"
                            f"1. **Find where your users are** — search Reddit, X, or Hacker News for discussions about the problem you solve\n"
                            f"2. **Study 3 competitors** — look at their traffic sources, pricing, and what users say about them\n"
                            f"3. **Write your first post** — share something genuine in the community where your users hang out\n\n"
                            f"Can you tell me more about what specific problem your product solves? I'll do a more targeted search."
                        ),
                    }

        # 持久化状态
        await self._persist_state()

    async def _think(self, context: dict) -> AgentAction:
        """
        Coordinator（首席增长官）的思考
        
        使用 Tier CRITICAL：这是核心决策，质量最重要。
        """
        from app.agent.engine.llm_adapter import TaskTier

        coordinator_prompt = self._build_coordinator_prompt(context)
        
        response = await self.llm.generate(
            system_prompt=coordinator_prompt,
            messages=context.get("messages", []),
            tier=TaskTier.CRITICAL,  # Coordinator 用最好的模型
            tools=self._get_available_actions(),
        )

        # 同步 token 使用量
        self.state.total_tokens_used = self.llm.usage.total_tokens

        return self._parse_decision(response)

    def _build_coordinator_prompt(self, context: dict) -> str:
        """
        首席增长官的 System Prompt
        
        这是整个系统最重要的 prompt。
        所有的"不要套路化"、"要个性化"的要求都在这里体现。
        """
        product_context = context.get("product", {})
        phase = self.state.phase.value
        expert_outputs = self.state.expert_outputs
        trust = context.get("trust", {})
        trust_level_name = trust.get("level_name", "Cautious")
        auto_research = trust.get("auto_research", False)
        auto_post = trust.get("auto_post", False)

        lang = getattr(self, '_language', 'en')
        lang_rule = "English" if lang == "en" else "Chinese (中文)"

        return f"""You are CrabRes — an AI growth strategy agent that helps indie developers and small teams find users and grow their products.

## WHO YOU ARE (self-awareness — you MUST know this)
- You ARE CrabRes. You are the product itself. If someone asks "what are you" or "what do you do", you answer about yourself.
- Your job: research a user's product market, analyze competitors, and create actionable growth plans.
- You have 13 specialized AI experts (market researcher, economist, psychologist, etc.) that you coordinate.
- You are NOT a generic chatbot. You are a growth strategist with real research tools.

## CRITICAL LANGUAGE RULE
**You MUST respond ONLY in {lang_rule}.** No exceptions. No mixing languages.

## RULE #1: RESEARCH FIRST, ASK NEVER (THIS IS THE MOST IMPORTANT RULE)

**If the user gives you ANY information about their product — even a single sentence — you MUST call web_search or social_search IMMEDIATELY.** Do NOT ask follow-up questions first. Do NOT say "Could you tell me more about...". Do NOT list questions for the user to answer.

Examples of messages where you MUST search immediately (not ask):
- "帮助vibecoder增长的营销产品" → search "vibecoder growth marketing tools competitors"
- "accio是竞品" → search "accio AI product" + scrape accio's website
- "AI resume tool, $9.99/mo" → search "AI resume tool competitors market size"
- "我做了一个帮独立开发者的工具" → search "indie developer tools market competitors"

The ONLY time you may use ask_user: the message is a pure greeting with ZERO product context (just "hi" or "hello").

**Anti-patterns (instant failure — if you do any of these, you have failed):**
- ❌ Asking "Could you provide more details about X?" when you could search instead
- ❌ Listing 3-5 questions for the user to answer
- ❌ Saying "I need more information" when the user already gave you a product description
- ❌ Repeating back what the user said instead of researching it
- ❌ Outputting strategy without first using search tools

## CONVERSATION STYLE
**Be like a coworker, not a consultant. Be warm, concise, direct.**

- Greeting with no product context → 1-2 sentences. "Hey! What are you building?" Done.
- User gives ANY product info → Start researching. Show results. Then ask follow-ups if needed.
- NEVER ask more than ONE question per turn.
- NEVER repeat what the user already told you.
- It's ALWAYS better to search with incomplete info than to ask for more info.

## TRUST LEVEL: {trust_level_name}
{"- You CAN auto-execute research without asking." if auto_research else "- Ask user before executing any strategy."}
{"- You CAN auto-post content on behalf of user." if auto_post else "- Always show content to user for approval before posting."}

## YOUR PERSONALITY
- Warm and direct. Not formal, not stiff.
- Data-driven — always cite numbers.
- Honest — if something won't work, say so.

You lead a team of 13 specialized experts. Your job is NOT just to give advice. Your job is to BUILD A MACHINE that makes this specific product grow.

## HOW YOU THINK (Roundtable Coordinator Rules)
- **NO REPEATING**: If an expert suggests A, the next expert MUST challenge, supplement, or debunk A from a different dimension.
- **ENCOURAGE CONFLICT**: Generate intense debates on "CAC vs UX", "Short-term Traffic vs Long-term Brand", "Free vs Premium".
- **RESEARCH FIRST**: Before any recommendation, you MUST use tools to research.
- **THINK LIKE A DETECTIVE**: Use specific links and data, not generic consultant talk.

Step 1: RESEARCH IMMEDIATELY (mandatory — use at least 2 tools before anything else)
  - Search competitors: web_search("{product} competitors market analysis")
  - If user named a competitor: scrape_website or competitor_analyze on that competitor
  - Find target users: social_search("{product} discussions", platforms=["reddit", "x", "hackernews"])
  - You MUST do this step even if user gave minimal info. Search with what you have.
Step 2: ROUNDTABLE (use consult_roundtable, NOT consult_expert)
  - Pick 2-4 relevant experts based on the research findings
  - Example: for a SaaS product → market_researcher + economist + social_media + psychologist
  - The experts will analyze in parallel and debate each other
  - You will then synthesize their outputs into a unified strategy
Step 3: Output the final plan with ALL content written
Step 4: ONLY if you truly lack ALL context (user said just "hi") → ask ONE question: "What are you building?"

## CRITICAL RULE: USE ROUNDTABLE

When you have research data and need expert analysis:
→ Use consult_roundtable with 2-4 experts. NEVER use consult_expert for strategic decisions.
→ consult_expert is ONLY for quick single-expert follow-up questions.

## CURRENT STATE

Phase: {phase}
Product info: {json.dumps(product_context, ensure_ascii=False, default=str)}
Experts consulted: {json.dumps(list(expert_outputs.keys()), ensure_ascii=False)}
Turn: {self.state.turn_count}

## YOUR 13 EXPERTS

- market_researcher: Competitive intelligence, user discovery, market sizing
- economist: Budget allocation, CAC/LTV, pricing strategy, flywheel economics  
- content_strategist: SEO/AEO, topic clusters, programmatic SEO
- social_media: Platform-native strategies (Reddit/X/LinkedIn/YouTube/TikTok/XHS/etc)
- paid_ads: Google/Meta/LinkedIn/TikTok/Reddit ads, ROAS optimization
- partnerships: KOL outreach, cold email, PH launch, affiliate, offline events
- ai_distribution: MCP servers, GPT Store, AEO, AI directories
- psychologist: CRO, pricing psychology, persuasion, behavioral triggers
- product_growth: PLG, viral loops, activation, retention, onboarding
- data_analyst: KPIs, funnels, cohort analysis, experiment design
- copywriter: All written content (posts, emails, ads, landing pages)
- critic: Feasibility check, budget validation, risk assessment
- designer: Ad creatives, social graphics, brand visual, design specs

## TOOLS (use via call_tool)

- web_search: Search the internet (competitors, market data, trends)
- scrape_website: Fetch and analyze a webpage
- social_search: Search Reddit/HN/X/PH/LinkedIn for discussions
- competitor_analyze: Deep parallel analysis (scrape + search + social)
- deep_scrape: JS-rendered pages (Instagram, SPAs, anti-bot sites)

{self._get_playbook_context()}

## CRITICAL RULES

### Rule 1: CONVERSATION STYLE (like a coworker, not a consultant)
- **Be concise.** Match the length of your response to the complexity of the question.
- If the user says "hi" or a short greeting → respond in 1-2 sentences max. Be warm, be brief.
- Only write long responses when you have real research data to present.
- NEVER dump a wall of text on a user who hasn't given you product information yet.

### Rule 2: ALWAYS SEARCH BEFORE ASKING (reinforcement of Rule #1)
- If user mentions ANY product, tool, competitor, or market → SEARCH IMMEDIATELY. Do NOT ask first.
- You can ask follow-up questions AFTER showing research results — never before.
- NEVER ask about pricing, target audience, budget separately — search with what you have.

### Rule 3: COMPETITOR TRACKING (CRITICAL)
- When you discover competitors through research, ALWAYS call save_competitors to persist them.
- The Growth Daemon will then automatically monitor these competitors every 30 minutes.
- Include name, url, description, and pricing (if known) for each competitor.
- This is how CrabRes becomes a real agent — continuous monitoring, not one-time research.

### Rule 4: EXPERT USAGE
- Do NOT call experts or roundtable until you have product info AND research data.
- If someone @mentions an expert without context, the expert should ask what product they're working on — not generate a generic analysis.

## OUTPUT FORMAT RULES (MANDATORY — violation = failure)

1. **DATA FIRST**: Every output MUST begin with 2-3 specific, verifiable data points before any opinion.
   GOOD: "Your top competitor Teal.com gets 4.8M monthly visits, 72% from SEO. Their #1 keyword 'resume builder free' has 135K monthly searches."
   BAD: "The resume market is competitive. I suggest focusing on content marketing."
   
2. **NAME NAMES**: Always use specific competitor names, specific subreddit names (with subscriber counts if found), specific pricing, specific URLs. NEVER say "some competitors" or "a few platforms."

3. **ONE UNCOMFORTABLE TRUTH**: Every final output MUST include one thing the user probably doesn't want to hear but needs to hear. Label it clearly:
   ⚠️ **Hard truth:** "There are 37 direct competitors in this space and your product has no clear differentiator yet." 
   ⚠️ **Hard truth:** "Nobody on Reddit is discussing this problem — which means demand is unproven."
   ⚠️ **Hard truth:** "Your pricing is 3x higher than the market leader with fewer features."
   
   If you can't find anything uncomfortable, you haven't researched deeply enough.

4. **SPECIFICITY TEST**: Before outputting, ask yourself: "Could I swap this product's name with any other product and the advice would still make sense?" If yes → too generic → rewrite with specifics.

5. **CITE RESEARCH RESULTS**: You MUST reference specific findings from your tool calls in your output.
   BAD: "Based on my research, the market is competitive."
   GOOD: "Search results show 3 direct competitors: Rezi ($29/mo, 890K monthly visits), Kickresume (freemium, 2.1M visits), Zety ($24.99/mo, 4.8M visits). Reddit r/resumes (850K members) has 12 recent threads asking for AI resume tools."
   
   If you used web_search or social_search, their results MUST appear in your output. Don't just say "I researched" — show the data.

5. **PLAYBOOK FORMAT**: When presenting a growth strategy, structure it as executable Playbooks:
   - Each growth path = 1 Playbook (e.g., "小红书达人种草", "Reddit Community Growth", "X Build in Public")
   - Each Playbook has Phases (准备期 → 执行期 → 追踪期)
   - Each Phase has numbered Steps with: title, specific actions, tools to use, budget, timeline, success criteria
   - Present 2-3 Playbooks ranked by priority
   - Let the user choose which to activate first
   - This is NOT a suggestion list. This is an execution manual.

6. **CHANNEL DEPTH**: For X/Twitter, 小红书, and Reddit — give Playbook-level SOPs with platform-specific knowledge (algorithm rules, content formats, timing, anti-ban). For other channels — give directional advice + "whether it fits" judgment + first step.

{context.get('mood_injection', '')}

The user came here because they're tired of generic advice. Show them what real research looks like."""

    async def _execute_tool(self, action: AgentAction) -> Any:
        """执行工具，带超时、重试和结果验证"""
        tool = self.tools.get(action.tool_name)
        if not tool:
            return {"error": f"Tool {action.tool_name} not found"}

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    tool.execute(**action.tool_args or {}),
                    timeout=60.0,
                )
                
                # 结果验证：检查是否为有效结果
                if isinstance(result, dict):
                    if result.get("error"):
                        last_error = result["error"]
                        if attempt < max_retries - 1:
                            logger.warning(f"Tool {action.tool_name} returned error (attempt {attempt+1}): {last_error}")
                            await asyncio.sleep(1)  # 短暂等待后重试
                            continue
                        return result
                    # 验证搜索结果不为空
                    if action.tool_name in ("web_search", "social_search"):
                        if result.get("count", 0) == 0 and not result.get("answer"):
                            logger.info(f"Tool {action.tool_name} returned empty results, attempt {attempt+1}")
                            if attempt < max_retries - 1:
                                await asyncio.sleep(1)
                                continue
                
                return result
                
            except asyncio.TimeoutError:
                last_error = f"Tool {action.tool_name} timed out"
                logger.warning(f"{last_error} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    continue
                return {"error": last_error}
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Tool {action.tool_name} failed (attempt {attempt+1}): {last_error}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {"error": last_error}

        return {"error": last_error or "Unknown error after retries"}

    async def _consult_expert(self, action: AgentAction, context: dict) -> str:
        """调度专家 Agent"""
        expert = self.experts.get(action.expert_id)
        if not expert:
            return f"Expert {action.expert_id} not found"

        return await expert.analyze(context, action.content)

    async def _run_roundtable(self, expert_ids: list[str], task: str, context: dict):
        """
        圆桌模式：按依赖关系分批调度专家 → 后批能看到前批结果 → CGO 综合
        
        升级：使用 Harness 的 EXPERT_DEPENDENCIES 做分批执行
        - 第一批：无依赖的专家并行
        - 第二批：依赖第一批的专家并行（能看到第一批结果）
        - 最后：CGO 综合所有输出
        """
        from app.agent.engine.llm_adapter import TaskTier
        from app.agent.engine.context_engine import get_expert_execution_order

        # 1. 计算分批执行顺序
        batches = get_expert_execution_order(expert_ids)
        logger.info(f"Roundtable execution order: {batches}")

        expert_results: dict[str, str] = {}

        # 2. 为每个专家创建分析任务
        async def _consult_one(eid: str) -> tuple[str, str]:
            expert = self.experts.get(eid)
            if not expert:
                return eid, f"Expert {eid} not available"
            try:
                # 注入已有其他专家的观点（前批结果），鼓励冲突
                other_views = {k: v[:300] for k, v in self.state.expert_outputs.items() if k != eid}
                enriched_task = task
                if other_views:
                    enriched_task += f"\n\n## Other experts' views (challenge or build on these):\n"
                    for ok, ov in other_views.items():
                        enriched_task += f"- {ok}: {ov}\n"
                
                result = await asyncio.wait_for(
                    expert.analyze(context, enriched_task),
                    timeout=90.0,
                )
                return eid, result
            except asyncio.TimeoutError:
                return eid, f"[{expert.name}] Analysis timed out"
            except Exception as e:
                return eid, f"[{expert.name if expert else eid}] Error: {str(e)[:100]}"

        # 3. 按批次执行：同批并行，批间串行（后批能看到前批结果）
        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                yield {"type": "status", "content": f"Round {batch_idx + 1}: {len(batch)} experts analyzing with prior insights..."}

            tasks_list = [_consult_one(eid) for eid in batch]
            
            for coro in asyncio.as_completed(tasks_list):
                eid, result = await coro
                expert_results[eid] = result
                # 写入 state 让下一批专家能看到
                self.state.expert_outputs[eid] = result
                context.setdefault("expert_outputs", {})[eid] = result

                expert = self.experts.get(eid)
                expert_name = expert.name if expert else eid
                yield {"type": "expert_thinking", "expert_id": eid, "content": f"{expert_name} is analyzing..."}
                yield {"type": "expert_thinking", "expert_id": eid, "content": result}

        # 4. 所有专家完成后，Coordinator 综合
        yield {"type": "status", "content": "CGO synthesizing expert insights..."}
        synthesis = await self._coordinator_synthesize(task, expert_results, context)
        
        # 综合结果作为消息返回
        self._message_history.append({"role": "assistant", "content": synthesis})
        await self._save_output_to_memory(synthesis)
        yield {"type": "message", "content": synthesis}

    async def _coordinator_synthesize(self, task: str, expert_results: dict[str, str], context: dict) -> str:
        """
        Coordinator（CGO）综合所有专家观点，产出最终回复
        
        关键：指出专家间的分歧，解释为什么选择某个方向
        """
        from app.agent.engine.llm_adapter import TaskTier

        expert_summary = ""
        for eid, output in expert_results.items():
            expert = self.experts.get(eid)
            name = expert.name if expert else eid
            expert_summary += f"\n### {name} ({eid}):\n{output[:1500]}\n"

        lang = getattr(self, '_language', 'en')
        lang_rule = "English" if lang == "en" else "Chinese (中文)"

        synthesis_prompt = f"""You are CrabRes's Chief Growth Officer. You just held a roundtable with {len(expert_results)} experts.

## CRITICAL LANGUAGE RULE
**You MUST respond ONLY in {lang_rule}.** No exceptions.

## ROUNDTABLE THREE-PHASE STRUCTURE (follow this order)

### Phase 1: Market Intelligence (数据先行)
- Open with 2-3 SPECIFIC data points from the research (competitor names, traffic numbers, pricing).
- Cite which expert found what. Example: "Our Market Researcher found Teal.com gets 4.8M monthly visits..."

### Phase 2: Expert Debate (专家争论)
- Highlight the KEY DISAGREEMENT between experts. There's always one.
- Example: "Our Economist argues for organic-only at this budget, but our Social Media Expert insists $50/mo on Reddit ads has 8x ROI."
- Explain YOUR decision as CGO and why.

### Phase 3: Execution Playbooks (可执行计划)
- Present 2-3 Playbooks ranked by priority.
- Each Playbook MUST have:
  - **Name** (e.g., "Reddit Community Growth")
  - **Why this channel** (1 sentence with data)
  - **Phase 1: Prep** (specific setup steps, timeline: X days)
  - **Phase 2: Execute** (specific actions, frequency, templates)
  - **Phase 3: Track** (what metrics to watch, what "good" looks like)
  - **Budget**: exact $ allocation
  - **Expected outcome**: realistic numbers
- End each playbook with a ready-to-use template (post title, email subject, etc.)

## MANDATORY ELEMENTS
1. **Hard Truth**: One uncomfortable truth the user needs to hear. Label it: ⚠️ **Hard truth:**
2. **Quick Win**: One thing they can do TODAY that will show results THIS WEEK.
3. **CGO Verdict**: Your personal judgment on the #1 priority and why.

## ANTI-PATTERNS (violation = failure)
❌ Don't say "based on my analysis" without showing the analysis.
❌ Don't give a strategy that could apply to any product. Be specific to THIS product.
❌ Don't list 10 channels. Pick 2-3 and go DEEP.
❌ Don't skip the Hard Truth. If you can't find one, you haven't thought deeply enough.

## Expert Outputs
{expert_summary}

## Original Question
{task}
"""

        response = await self.llm.generate(
            system_prompt=synthesis_prompt,
            messages=context.get("messages", [])[-5:],
            tier=TaskTier.CRITICAL,
            max_tokens=4096,
        )
        self.state.total_tokens_used = self.llm.usage.total_tokens
        return response.content

    async def _incorporate_result(self, context: dict, action: AgentAction, result: Any) -> dict:
        """将工具结果合并到上下文"""
        context.setdefault("tool_results", []).append({
            "tool": action.tool_name,
            "args": action.tool_args,
            "result": result,
        })

        # 特殊处理：设置活跃战役
        if action.tool_name == "set_active_campaign" and isinstance(result, dict) and result.get("status") == "pending_save":
            url = result.get("url")
            name = result.get("name")
            if url:
                execution = await self.memory.load("execution_stats", category="execution") or {}
                execution["active_campaign_url"] = url
                execution["active_campaign_name"] = name
                await self.memory.save("execution_stats", execution, category="execution")
                logger.info(f"Pinned active campaign to dashboard: {url}")

        return context

    def _incorporate_expert(self, context: dict, action: AgentAction, output: str) -> dict:
        """将专家输出合并到上下文和状态"""
        self.state.expert_outputs[action.expert_id] = output
        context.setdefault("expert_outputs", {})[action.expert_id] = output
        return context

    def _incorporate_thinking(self, context: dict, action: AgentAction) -> dict:
        """将内部思考合并到上下文（不输出给用户）"""
        context.setdefault("thinking", []).append(action.content)
        return context

    async def _build_context(self, user_message: str) -> dict:
        """构建当前上下文"""
        # 加载记忆
        product = await self.memory.load("product")
        competitors = await self.memory.load("competitors")
        strategy = await self.memory.load("strategy")
        results = await self.memory.load("results")
        brand_config = await self.memory.load("brand_config", category="product")
        growth_patterns = await self.memory.load("growth_patterns", category="strategy")

        # 把用户消息加入消息历史
        if user_message:
            self._message_history.append({"role": "user", "content": user_message})

        # 构建上下文摘要注入到消息中（使用 Prompt Cache 避免重复）
        context_summary_parts = []
        # 品牌配置优先（最重要的上下文）
        if brand_config:
            from app.api.v2.brand import get_brand_context
            brand_text = get_brand_context(brand_config)
            if brand_text:
                cached_brand, was_cached = self.prompt_cache.check_and_cache(
                    "brand_config", brand_text, "[Brand config: unchanged]"
                )
                context_summary_parts.append(cached_brand)
        if product:
            product_str = f"[Product info]: {json.dumps(product, ensure_ascii=False, default=str)}"
            cached_product, _ = self.prompt_cache.check_and_cache(
                "product_info", product_str, "[Product info: unchanged since last turn]"
            )
            context_summary_parts.append(cached_product)
        if competitors:
            context_summary_parts.append(f"[Competitor data]: {json.dumps(competitors, ensure_ascii=False, default=str)[:500]}")
        if strategy:
            strategy_str = f"[Current strategy]: {json.dumps(strategy, ensure_ascii=False, default=str)[:500]}"
            cached_strategy, _ = self.prompt_cache.check_and_cache(
                "strategy", strategy_str, "[Strategy: unchanged since last turn]"
            )
            context_summary_parts.append(cached_strategy)
        if results:
            context_summary_parts.append(f"[Execution results]: {json.dumps(results, ensure_ascii=False, default=str)[:300]}")
        if growth_patterns:
            patterns_text = growth_patterns.get("patterns", "")
            if patterns_text:
                context_summary_parts.append(f"[Growth patterns learned from past actions]:\n{patterns_text[:500]}")

        # 注入实验追踪数据和增长规律（action→result 闭环）
        try:
            from app.agent.memory.experiments import ExperimentTracker
            tracker = ExperimentTracker(base_dir=str(self.memory.base_dir))
            exp_summary = await tracker.get_summary()
            if exp_summary.get("total_actions", 0) > 0:
                context_summary_parts.append(
                    f"[Experiment tracker]: {exp_summary['total_actions']} actions recorded, "
                    f"{exp_summary['tracked_actions']} tracked, "
                    f"{exp_summary['total_engagement']} total engagement, "
                    f"{exp_summary['learnings_count']} learnings extracted"
                )
            learnings_text = await tracker.get_learnings_text()
            if learnings_text:
                context_summary_parts.append(learnings_text)
        except Exception:
            pass

        # 注入 Growth State（渠道权重 + 历史表现 + 增长信号）
        try:
            from app.agent.memory.growth_log import GrowthLog
            growth_log = GrowthLog(base_dir=str(self.memory.base_dir))
            state_text = await growth_log.get_state_prompt()
            if state_text:
                context_summary_parts.append(state_text)
        except Exception:
            pass

        # 消息列表：如果有上下文摘要，作为第一条 system reminder 注入
        messages = []
        if context_summary_parts:
            messages.append({
                "role": "user",
                "content": "[SYSTEM CONTEXT — not from user]\n" + "\n".join(context_summary_parts),
            })
            messages.append({
                "role": "assistant",
                "content": "Understood, I have the context loaded.",
            })

        # 智能消息历史构建（不再无脑塞 20 条）
        # 1. 过滤掉 status 消息（"Researching..."对 LLM 无用，浪费 token）
        # 2. 截断工具结果（[Tool: xxx] 只保留前 500 字符）
        # 3. 旧对话压缩（超过最近 8 轮的部分只保留 user/assistant 核心内容）
        
        filtered_history = []
        for msg in self._message_history:
            content = msg.get("content", "")
            role = msg.get("role", "")
            
            # 跳过空消息
            if not content.strip():
                continue
            
            # 跳过 status 类消息（[Internal reasoning] 等对 Coordinator 有用但要截断）
            if content.startswith("[Tool:"):
                # 工具结果截断到 500 字符
                filtered_history.append({**msg, "content": content[:500]})
            elif content.startswith("[Internal reasoning]"):
                # 内部推理截断到 200 字符
                filtered_history.append({**msg, "content": content[:200]})
            elif content.startswith("[Expert:"):
                # 专家输出截断到 800 字符
                filtered_history.append({**msg, "content": content[:800]})
            else:
                filtered_history.append(msg)
        
        # 保留最近 12 条完整消息（约 6 轮对话）
        # 更早的消息只保留 user 和 assistant 的核心消息（跳过工具/专家）
        if len(filtered_history) > 12:
            old_msgs = filtered_history[:-12]
            recent_msgs = filtered_history[-12:]
            
            # 旧消息只保留 user 和最终 assistant 回复
            compressed_old = []
            for m in old_msgs:
                r = m.get("role", "")
                c = m.get("content", "")
                if r == "user":
                    compressed_old.append({"role": "user", "content": c[:300]})
                elif r == "assistant" and not c.startswith("["):
                    compressed_old.append({"role": "assistant", "content": c[:500]})
            
            # 如果压缩后的旧消息太多，进一步截取
            compressed_old = compressed_old[-6:]
            
            messages.extend(compressed_old)
            messages.extend(recent_msgs)
        else:
            messages.extend(filtered_history)

        # 在最后追加语言指令（使用用户设置的语言，不再猜测）
        if user_message:
            lang = getattr(self, '_language', 'en')
            lang_name = "Chinese (中文)" if lang == "zh" else "English"
            messages.append({
                "role": "user",
                "content": f"[SYSTEM] Respond in {lang_name} only. Do NOT use any other language.",
            })

        return {
            "user_message": user_message,
            "product": product or {},
            "competitors": competitors or {},
            "strategy": strategy or {},
            "results": results or {},
            "messages": messages,
            "phase": self.state.phase.value,
        }

    async def _write_ahead_log(self, user_message: str):
        """写前日志 — 进程被杀也能恢复"""
        await self.memory.append_journal({
            "type": "user_message",
            "content": user_message,
            "session_id": self.state.session_id,
            "turn": self.state.turn_count,
            "timestamp": time.time(),
        })

    async def _try_recover(self, context: dict, error: Exception) -> dict:
        """3 级恢复（学 Claude Code）"""
        if self._error_count == 1:
            logger.info("Recovery L1: compacting context")
            context = self._compact_context(context)
        elif self._error_count == 2:
            logger.info("Recovery L2: collapsing history")
            context = self._collapse_history(context)
        else:
            logger.info("Recovery L3: resetting to safe state")
            context = await self._build_context("")
        return context

    async def _save_output_to_memory(self, content: str):
        """把 Agent 输出自动存入记忆，让 Plan/Surface 能读取"""
        # 检测是否包含策略/计划内容
        plan_keywords = ['strategy', 'plan', 'step', 'phase', 'month', 'week',
                        '策略', '计划', '步骤', '阶段']
        is_plan = any(kw in content.lower() for kw in plan_keywords)

        if is_plan and len(content) > 200:
            await self.memory.save(f"growth_plan_{self.state.session_id}", {
                "content": content,
                "turn": self.state.turn_count,
                "updated_at": time.time(),
            }, category="strategy")

            # 也生成简化的每日任务
            tasks = []
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line and (line.startswith('- ') or line.startswith('1.') or line.startswith('2.') or line.startswith('3.')):
                    clean = line.lstrip('-123456789. ').strip()
                    if clean and len(clean) > 10 and len(clean) < 200:
                        tasks.append({
                            "id": f"task-{len(tasks)}",
                            "type": "action",
                            "title": clean[:80],
                            "subtitle": "From growth plan",
                            "status": "pending",
                        })
                        if len(tasks) >= 5:
                            break

            if tasks:
                self.state.pending_user_tasks = tasks
                await self.memory.save(f"daily_tasks_{self.state.session_id}", tasks, category="strategy")

            logger.info(f"Saved growth plan to memory ({len(content)} chars, {len(tasks)} tasks)")

        # 保存专家输出
        for expert_id, output in self.state.expert_outputs.items():
            await self.memory.save(f"expert_output_{self.state.session_id}_{expert_id}", output, category="research")

        # 记录到日志
        await self.memory.append_journal({
            "type": "agent_output",
            "content_preview": content[:300],
            "turn": self.state.turn_count,
            "timestamp": time.time(),
        })

    async def _auto_save_competitors_from_results(self, context: dict):
        """
        从搜索结果中自动提取竞品并保存到记忆。

        不用 LLM — 直接从搜索结果的 title/url 中提取。
        Daemon 会用这些数据做持续监控。
        """
        tool_results = context.get("tool_results", [])
        if not tool_results:
            return

        competitors = []
        seen_domains = set()

        for tr in tool_results:
            result = tr.get("result", {})
            if not isinstance(result, dict):
                continue
            # 从 web_search / social_search 结果中提取
            for r in result.get("results", []):
                url = r.get("url", "")
                title = r.get("title", "")
                content = r.get("content", "")
                if not url:
                    continue

                # 提取域名
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    continue

                # 跳过搜索引擎、社交平台、通用网站
                skip_domains = {
                    "google.com", "bing.com", "reddit.com", "twitter.com", "x.com",
                    "youtube.com", "linkedin.com", "facebook.com", "instagram.com",
                    "github.com", "medium.com", "quora.com", "wikipedia.org",
                    "news.ycombinator.com", "producthunt.com", "crunchbase.com",
                    "techcrunch.com", "forbes.com", "bloomberg.com",
                    "futurepedia.io", "alternativeto.net", "g2.com", "capterra.com",
                }
                if any(skip in domain for skip in skip_domains):
                    continue

                if domain in seen_domains:
                    continue
                seen_domains.add(domain)

                # 从 title 中提取产品名（取第一个 - 或 | 之前的部分）
                name = title.split(" - ")[0].split(" | ")[0].split(" — ")[0].strip()
                if len(name) > 50:
                    name = name[:50]

                competitors.append({
                    "name": name,
                    "url": f"https://{domain}",
                    "description": content[:200] if content else title,
                })

        if competitors:
            # 保存到记忆
            existing = await self.memory.load("competitors", category="research")
            if not isinstance(existing, list):
                existing = []

            existing_urls = {c.get("url", "").lower() for c in existing}
            new_comps = []
            for c in competitors[:5]:  # 最多自动添加 5 个
                if c["url"].lower() not in existing_urls:
                    c["discovered_at"] = time.time()
                    c["status"] = "active"
                    c["source"] = "auto_discovery"
                    new_comps.append(c)

            if new_comps:
                existing.extend(new_comps)
                await self.memory.save("competitors", existing, category="research")
                logger.info(f"Auto-discovered {len(new_comps)} competitors: {[c['name'] for c in new_comps]}")

    def _detect_product_info(self, message: str) -> bool:
        """
        硬编码检测：用户消息是否包含足够的产品信息可以开始研究

        不靠 LLM 判断，用关键词启发式。
        只要检测到产品描述就返回 True，Agent 应该立即 research。
        宁可误判为 True（多搜一次），也不要误判为 False（多问一次）。
        """
        msg = message.lower()

        # 纯问候过滤（只过滤极短的纯问候）
        greetings = ['hi', 'hello', 'hey', '你好', '嗨', 'yo', 'sup']
        if msg.strip() in greetings:
            return False

        # 竞品/对手信号（短消息也算 — "accio是竞品" 只有 6 个字但信息充分）
        competitor_signals = [
            '竞品', '竞争对手', '对手', '竞争者', '类似的产品', '类似产品',
            'competitor', 'competing', 'rival', 'alternative', 'vs ', ' vs',
            '比较', '对比',
        ]
        if any(kw in msg for kw in competitor_signals):
            return True

        # 产品描述关键词（任一命中，无最小长度要求）
        product_signals = [
            'my product', 'i built', 'i made', "i'm building", 'i have a',
            "it's a", 'it is a', 'we built', 'our product', 'we made',
            'i run', 'i created', 'working on', 'building a', 'launched',
            '我的产品', '我做了', '我们做了', '我在做', '我开发了',
            '我做的', '正在做', '在开发', '做了一个', '上线了',
        ]
        if any(kw in msg for kw in product_signals):
            return True

        # 产品类型信号（需要 >10 chars 避免误判）
        if len(msg) > 10:
            type_signals = [
                'saas', 'app', 'tool', 'platform', 'service', 'marketplace',
                'plugin', 'extension', 'bot', 'agent', 'api',
                'helps', 'for users', 'for developers', 'for teams',
                '$', '/mo', '/month', 'pricing', 'free', 'freemium',
                'users', 'customers', 'target', 'audience',
                'growth', 'marketing', 'launch', 'mvp',
                '帮助', '用户', '增长', '营销', '独立开发', '产品',
                'vibecoder', 'indie', 'hacker', 'startup', 'founder',
                'crabres', 'ai growth agent',
            ]
            if any(kw in msg for kw in type_signals):
                return True

        # URL 检测
        if 'http' in msg or '.com' in msg or '.io' in msg or '.app' in msg or '.ai' in msg:
            return True

        # 如果消息超过 20 字且不是纯问句，倾向于当作产品描述
        # （用户来 CrabRes 就是为了谈产品，不是闲聊）
        if len(msg) > 20 and not msg.endswith('?') and not msg.endswith('？'):
            return True

        return False

    async def _maybe_save_product_info(self, user_message: str):
        """如果用户消息包含产品信息，自动存入记忆"""
        msg = user_message.lower()
        # 简单启发式：第一条消息通常包含产品描述
        product_keywords = ['my product', 'i built', 'i made', 'i\'m building', 'i have a',
                          'it\'s a', 'it is a', 'we built', 'our product',
                          '我的产品', '我做了', '我们做了']

        if any(kw in msg for kw in product_keywords) or self.state.turn_count <= 2:
            # 存储原始消息作为产品信息
            existing = await self.memory.load("product") or {}
            existing["raw_description"] = user_message
            existing["updated_at"] = time.time()

            # 提取 URL
            import re
            urls = re.findall(r'https?://\S+', user_message)
            if urls:
                existing["url"] = urls[0]

            await self.memory.save("product", existing)
            logger.info(f"Product info saved to memory (turn {self.state.turn_count})")

    async def _maybe_track_posted_url(self, user_message: str):
        """
        如果用户消息包含社媒平台链接，自动创建 GrowthAction 记录并开始追踪。
        
        这是闭环的关键入口：用户发了帖子 → 贴回链接 → CrabRes 开始追踪效果。
        """
        import re
        urls = re.findall(r'https?://\S+', user_message)
        if not urls:
            return

        from app.agent.memory.experiments import ExperimentTracker
        tracker = ExperimentTracker(base_dir=str(self.memory.base_dir))

        for url in urls:
            url_lower = url.lower().rstrip('.,;:!?)')
            platform = ""
            action_type = "post"

            if "reddit.com" in url_lower:
                platform = "reddit"
                if "/comment/" in url_lower or "/comments/" in url_lower:
                    action_type = "reply" if "/comment/" in url_lower else "post"
            elif "x.com" in url_lower or "twitter.com" in url_lower:
                platform = "x"
            elif "linkedin.com" in url_lower:
                platform = "linkedin"
                if "/messaging/" in url_lower:
                    action_type = "dm"
            elif "news.ycombinator.com" in url_lower:
                platform = "hackernews"
            elif "producthunt.com" in url_lower:
                platform = "producthunt"

            if platform:
                await tracker.record_action(
                    platform=platform,
                    action_type=action_type,
                    url=url_lower,
                    content_preview=user_message[:200],
                )
                logger.info(f"Auto-tracked posted URL: {platform}/{action_type} → {url_lower[:60]}")

    def _get_playbook_context(self) -> str:
        """获取 Playbook 模板和活跃 Playbook 状态，注入 Coordinator prompt"""
        parts = []
        try:
            from app.agent.knowledge.playbook_templates import get_playbook_templates_prompt
            parts.append(get_playbook_templates_prompt())
        except Exception:
            pass

        try:
            from app.agent.memory.playbooks import PlaybookStore
            import asyncio
            store = PlaybookStore(base_dir=str(self.memory.base_dir))
            # 同步调用（在 prompt 构建时无法 await）
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已运行的 event loop 中，使用线程安全方式
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    summary = pool.submit(
                        lambda: asyncio.run(store.get_active_playbook_summary())
                    ).result(timeout=2)
            else:
                summary = asyncio.run(store.get_active_playbook_summary())
            if summary:
                parts.append(summary)
        except Exception:
            pass

        return "\n".join(parts) if parts else ""

    def _compact_context(self, context: dict) -> dict:
        """压缩上下文：截断旧的工具结果"""
        if "tool_results" in context and len(context["tool_results"]) > 5:
            context["tool_results"] = context["tool_results"][-5:]
        return context

    def _collapse_history(self, context: dict) -> dict:
        """折叠历史：只保留最近的专家输出"""
        if "expert_outputs" in context:
            # 只保留最近 3 个专家的输出
            keys = list(context["expert_outputs"].keys())[-3:]
            context["expert_outputs"] = {k: context["expert_outputs"][k] for k in keys}
        return context

    async def _persist_state(self):
        """
        完整会话检查点 — 进程重启无损恢复
        
        保存所有状态，包括：
        - Loop 基本状态（phase, turn, tokens）
        - 消息历史（完整）
        - 专家输出缓存（完整内容，不只是 key）
        - 待办任务
        - 时间戳（用于判断检查点新鲜度）
        """
        # 专家输出完整保存（不只是 key 列表）
        expert_outputs_full = {}
        for eid, output in self.state.expert_outputs.items():
            expert_outputs_full[eid] = output[:3000] if isinstance(output, str) else str(output)[:3000]

        checkpoint = {
            "session_id": self.state.session_id,
            "phase": self.state.phase.value,
            "turn_count": self.state.turn_count,
            "tokens_used": self.state.total_tokens_used,
            "token_budget": self.state.token_budget,
            "pending_tasks": self.state.pending_user_tasks,
            "expert_outputs": expert_outputs_full,
            "expert_outputs_keys": list(self.state.expert_outputs.keys()),
            "is_waiting": self.state.is_waiting_for_user,
            "message_history": self._message_history[-50:],  # 最多保存 50 条
            "created_at": self.state.created_at,
            "last_active_at": self.state.last_active_at,
            "checkpoint_version": 2,  # 版本号，用于未来迁移
        }

        await self.memory.save(f"loop_state_{self.state.session_id}", checkpoint)

    async def _load_state(self):
        """从检查点恢复完整状态"""
        data = await self.memory.load(f"loop_state_{self.state.session_id}")
        if not data:
            return

        logger.info(f"Restoring session checkpoint for {self.state.session_id} (v{data.get('checkpoint_version', 1)})")
        self.state.phase = LoopPhase(data.get("phase", LoopPhase.INTAKE))
        self.state.turn_count = data.get("turn_count", 0)
        self.state.total_tokens_used = data.get("tokens_used", 0)
        self.state.token_budget = data.get("token_budget", 100_000)
        self.state.pending_user_tasks = data.get("pending_tasks", [])
        self.state.is_waiting_for_user = data.get("is_waiting", False)
        self._message_history = data.get("message_history", [])
        self.state.created_at = data.get("created_at", time.time())
        self.state.last_active_at = data.get("last_active_at", time.time())
        
        # v2 检查点：直接恢复专家输出内容
        if data.get("checkpoint_version", 1) >= 2:
            expert_outputs = data.get("expert_outputs", {})
            if isinstance(expert_outputs, dict):
                self.state.expert_outputs = expert_outputs
                logger.info(f"Restored {len(expert_outputs)} expert outputs from checkpoint")
        else:
            # v1 兼容：只有 key 列表，需要从文件加载
            for expert_id in data.get("expert_outputs_keys", []):
                output = await self.memory.load(
                    f"expert_output_{self.state.session_id}_{expert_id}", category="research"
                )
                if output:
                    self.state.expert_outputs[expert_id] = output

    def _get_available_actions(self) -> list[dict]:
        """返回当前可用的 action schema"""
        return [
            {
                "name": "think",
                "description": "Internal reasoning, not shown to user",
                "parameters": {"type": "object", "properties": {"reasoning": {"type": "string"}}}
            },
            # 直接暴露研究工具（LLM 可以直接调用）
            {
                "name": "web_search",
                "description": "YOUR DEFAULT ACTION. Search the internet for competitors, market data, trends, product info. Use this BEFORE asking the user any questions. If user mentions any product or competitor name, search it immediately.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results (1-10)"},
                    },
                    "required": ["query"],
                }
            },
            {
                "name": "social_search",
                "description": "Search social media for user discussions and mentions. Use alongside web_search for comprehensive research. Platforms: reddit, x, hackernews, producthunt, linkedin, xiaohongshu, jike, bilibili, zhihu.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Topic to search"},
                        "platforms": {"type": "array", "items": {"type": "string"}, "description": "Platforms to search"},
                    },
                    "required": ["query"],
                }
            },
            {
                "name": "scrape_website",
                "description": "Fetch and extract content from a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to scrape"},
                    },
                    "required": ["url"],
                }
            },
            {
                "name": "competitor_analyze",
                "description": "Deep analysis of a competitor (parallel: scrape site + search reviews + social mentions).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "competitor_url": {"type": "string", "description": "Competitor website URL"},
                        "competitor_name": {"type": "string", "description": "Competitor name"},
                    },
                    "required": ["competitor_url"],
                }
            },
            {
                "name": "deep_scrape",
                "description": "Deep scrape a URL using Firecrawl (handles JavaScript rendering). Use for Instagram, SPA apps, or when regular scrape fails.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to deep scrape"},
                    },
                    "required": ["url"],
                }
            },
            {
                "name": "browse_website",
                "description": "Open URL in real browser, take screenshot, extract JS-rendered content. Use for: analyzing competitor landing pages visually, checking how a website looks, pages that require JavaScript. Returns screenshot + full rendered text + metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to browse"},
                        "mobile": {"type": "boolean", "description": "Emulate mobile view", "default": False},
                    },
                    "required": ["url"],
                }
            },
            # 行动工具
            {
                "name": "write_post",
                "description": "Write a ready-to-publish social media post for a specific platform (reddit, x, linkedin, etc).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "platform": {"type": "string", "description": "Platform: reddit, x, linkedin, hackernews, producthunt, xiaohongshu"},
                        "topic": {"type": "string", "description": "Post topic"},
                        "product_name": {"type": "string", "description": "Product to mention"},
                    },
                    "required": ["platform", "topic"],
                }
            },
            {
                "name": "publish_post",
                "description": "Actually publish a post to X/Twitter. Use after write_post to send the content live. Requires Twitter API credentials.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "platform": {"type": "string", "enum": ["x"], "description": "Platform to publish to"},
                        "text": {"type": "string", "description": "Exact text to publish (max 280 chars for X)"},
                    },
                    "required": ["platform", "text"],
                }
            },
            {
                "name": "twitter_read",
                "description": "Read real-time data from X/Twitter: search tweets about a topic, get user profile info, or get a user's recent tweets with engagement metrics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["search_tweets", "user_info", "user_tweets"], "description": "What to do"},
                        "query": {"type": "string", "description": "Search query or @username"},
                        "max_results": {"type": "integer", "description": "Max results (10-100)"},
                    },
                    "required": ["action", "query"],
                }
            },
            {
                "name": "write_email",
                "description": "Write a personalized outreach email to influencers, partners, or potential users.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipient_type": {"type": "string", "description": "Who: influencer, partner, potential_user, press"},
                        "context": {"type": "string", "description": "Why reaching out"},
                        "recipient_name": {"type": "string", "description": "Name"},
                    },
                    "required": ["recipient_type", "context"],
                }
            },
            {
                "name": "consult_expert",
                "description": "Consult a specialized expert for deep analysis.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expert_id": {"type": "string", "enum": [
                            "market_researcher", "economist", "content_strategist",
                            "social_media", "paid_ads", "partnerships",
                            "ai_distribution", "psychologist", "product_growth",
                            "data_analyst", "copywriter", "critic", "designer"
                        ]},
                        "task": {"type": "string", "description": "What to analyze"},
                    },
                    "required": ["expert_id", "task"],
                }
            },
            {
                "name": "consult_roundtable",
                "description": "PREFERRED over consult_expert. Assemble 2-4 experts for a roundtable discussion. Each expert analyzes independently, then you synthesize. Use this for any strategic question that benefits from multiple perspectives. Experts will see each other's views and challenge them.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expert_ids": {
                            "type": "array",
                            "items": {"type": "string", "enum": [
                                "market_researcher", "economist", "content_strategist",
                                "social_media", "paid_ads", "partnerships",
                                "ai_distribution", "psychologist", "product_growth",
                                "data_analyst", "copywriter", "critic", "designer"
                            ]},
                            "description": "Pick 2-4 most relevant experts for this question",
                        },
                        "task": {"type": "string", "description": "The question or analysis task for the roundtable"},
                    },
                    "required": ["expert_ids", "task"],
                }
            },
            {
                "name": "save_competitors",
                "description": "Save discovered competitors for continuous monitoring. After researching competitors, call this to enable Growth Daemon to track them automatically (website changes, pricing, social mentions every 30 min). ALWAYS call this after discovering competitors.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "competitors": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "url": {"type": "string"},
                                    "description": {"type": "string"},
                                    "pricing": {"type": "string"},
                                },
                                "required": ["name"],
                            },
                        },
                    },
                    "required": ["competitors"],
                }
            },
            {
                "name": "set_active_campaign",
                "description": "Set the current active growth campaign URL (e.g., a Tweet link, Reddit post, or Launch page). This will be pinned to the dashboard for live tracking.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL of the campaign (e.g., https://x.com/user/status/123)"},
                        "name": {"type": "string", "description": "Short name for the campaign", "default": "Global Launch Post"},
                    },
                    "required": ["url"],
                }
            },
            {
                "name": "ask_user",
                "description": "LAST RESORT ONLY. Ask the user a question. Use ONLY when the user's message is a pure greeting with zero product context (e.g., just 'hi'). If the user has mentioned ANY product, competitor, or market — use web_search instead of asking. Never ask more than one question.",
                "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}
            },
            {
                "name": "output",
                "description": "Send the final response to the user. Use ONLY when you have enough research to give specific, actionable advice.",
                "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
            },
        ]

    def _parse_decision(self, response) -> AgentAction:
        """解析 LLM 的决策输出为 AgentAction"""
        from app.agent.engine.llm_adapter import LLMResponse

        if not isinstance(response, LLMResponse):
            return AgentAction(type=ActionType.OUTPUT, content=str(response))

        logger.debug(f"Parse decision: content={response.content[:100] if response.content else 'empty'}, tool_calls={len(response.tool_calls)}")

        # 如果有 tool calls，解析第一个
        if response.tool_calls:
            tc = response.tool_calls[0]
            name = tc.get("name", "")
            args = tc.get("args", {})
            logger.info(f"Tool call detected: {name}, args keys: {list(args.keys())}")

            if name == "think":
                return AgentAction(
                    type=ActionType.THINK,
                    content=args.get("reasoning", ""),
                )
            elif name == "call_tool":
                return AgentAction(
                    type=ActionType.TOOL_CALL,
                    content=args.get("reason", "调用工具"),
                    tool_name=args.get("tool_name"),
                    tool_args=args.get("tool_args", {}),
                )
            elif name in ("web_search", "social_search", "scrape_website", "competitor_analyze", "deep_scrape", "browse_website", "write_post", "write_email", "submit_directory", "set_active_campaign"):
                # LLM 直接调用工具名
                action = AgentAction(
                    type=ActionType.TOOL_CALL,
                    content=f"Using {name}",
                    tool_name=name,
                    tool_args=args,
                )
                # 如果有额外的 tool_calls，收集为并行任务
                if len(response.tool_calls) > 1:
                    parallel = []
                    for extra_tc in response.tool_calls[1:]:
                        extra_name = extra_tc.get("name", "")
                        extra_args = extra_tc.get("args", {})
                        if extra_name in ("web_search", "social_search", "scrape_website", "competitor_analyze", "deep_scrape", "browse_website"):
                            parallel.append(AgentAction(
                                type=ActionType.TOOL_CALL,
                                content=f"Using {extra_name}",
                                tool_name=extra_name,
                                tool_args=extra_args,
                            ))
                    if parallel:
                        action.parallel_tools = parallel
                        action.content = f"Running {1 + len(parallel)} tools in parallel"
                        logger.info(f"Parallel execution: {name} + {[p.tool_name for p in parallel]}")
                return action
            elif name == "consult_expert":
                expert_id = args.get("expert_id", "")
                return AgentAction(
                    type=ActionType.EXPERT,
                    content=args.get("task", f"咨询{expert_id}"),
                    expert_id=expert_id,
                )
            elif name == "consult_roundtable":
                expert_ids = args.get("expert_ids", [])
                return AgentAction(
                    type=ActionType.ROUNDTABLE,
                    content=args.get("task", "圆桌讨论"),
                    expert_ids=expert_ids,
                )
            elif name == "ask_user":
                return AgentAction(
                    type=ActionType.ASK_USER,
                    content=args.get("question", ""),
                )
            elif name == "output":
                return AgentAction(
                    type=ActionType.OUTPUT,
                    content=args.get("message", ""),
                )

        # 没有 tool calls，直接用 content 作为输出
        if response.content:
            return AgentAction(
                type=ActionType.OUTPUT,
                content=response.content,
            )

        return AgentAction(
            type=ActionType.OUTPUT,
            content="我需要更多信息来帮你制定增长策略。能告诉我你的产品是什么吗？",
        )

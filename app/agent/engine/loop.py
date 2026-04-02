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
from collections.abc import AsyncIterator as AsyncIteratorABC
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
    EXPERT = "expert"        # 调度专家
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
        self._max_loop_iterations = 15  # 允许更多轮次做深度研究
        self._message_history: list[dict] = []  # 跨轮次消息历史

    async def run(self, user_message: str):
        """
        处理一条用户消息，yield 流式输出
        
        这是整个系统的心跳。
        while(not_done): think → act → observe
        """
        self._running = True
        self.state.turn_count += 1
        self.state.last_active_at = time.time()
        self.state.is_waiting_for_user = False

        # 如果是新启动的会话（或进程重启），尝试从磁盘加载历史
        if not self._message_history:
            await self._load_state()

        # 写前日志（学 Claude Code）
        await self._write_ahead_log(user_message)

        # 自动提取和存储产品信息（如果用户消息包含产品描述）
        await self._maybe_save_product_info(user_message)

        # 加载记忆上下文
        context = await self._build_context(user_message)

        iteration = 0
        while self._running and iteration < self._max_loop_iterations:
            iteration += 1
            try:
                # 1. THINK: 让 Coordinator（首席增长官）决定下一步
                decision = await self._think(context)

                if decision.type == ActionType.OUTPUT:
                    content = decision.content
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

                elif decision.type == ActionType.EXPERT:
                    # 调度专家
                    yield {"type": "status", "content": f"Consulting {decision.content}..."}
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

        return f"""You are CrabRes's Chief Growth Officer — a world-class growth strategist.

You lead a team of 13 specialized experts. Your job is NOT to give advice. Your job is to BUILD A MACHINE that makes this specific product grow.

## HOW YOU THINK (This is what separates you from ChatGPT)

**1. ALWAYS RESEARCH FIRST, NEVER GUESS**
Before giving any recommendation, you MUST use tools to research:
- Use web_search to find the product's actual competitors (by name, with real pricing)
- Use social_search to find where target users are RIGHT NOW complaining about related problems
- Use competitor_analyze to understand what competitors are doing for growth
- If the user gave a URL, use scrape_website to analyze their actual product

If you haven't researched yet, your FIRST action must be a tool call, not an output.
Do NOT skip research and jump to generic advice. That's what ChatGPT does.

**2. THINK LIKE A DETECTIVE, NOT A CONSULTANT**
Bad: "You should try Reddit marketing"
Good: "I found 3 Reddit threads from this week where people are asking for exactly what your product does. Here are the threads: [links]. Here's a reply I wrote for each one that naturally mentions your product without being spammy."

Bad: "Consider reaching out to influencers"  
Good: "I found @JeffSu (180K YouTube subscribers) just posted a 'best tools' video in your category but didn't include you. Here's a personalized email to him — I referenced his specific video and offered free lifetime access in exchange for a review."

**3. USE THE 2026 PLAYBOOK, NOT THE 2020 PLAYBOOK**
You know these advanced tactics and use them when appropriate:
- Reverse trial: Give full premium access first, downgrade later (loss aversion)
- Embedded growth triggers: Product exports carry brand watermark + free credit link
- Cold DM with value: Find people with the EXACT problem on social media, DM them a solution (not a pitch)
- MCP server distribution: Publish to Smithery so AI assistants recommend the product
- Behavioral email triggers: Only email when user does/doesn't do specific in-app actions
- Micro-community ownership: Build a private Discord/Slack with 50 power users instead of chasing 5000 Twitter followers
- Service-first validation: Offer the service manually to 5 people before building features
- Synthetic persona testing: Use AI to simulate user reactions before launching campaigns
- API-first growth: Let other developers build on your platform (ecosystem play)
- Browser extension as growth channel: Keep the product in users' daily workflow

**4. GLOBAL & MULTI-LANGUAGE GROWTH MINDSET**
You are a global growth expert. You do not limit yourself to the English-speaking world.
- **Domestic (China):** You use social_search on platforms like Xiaohongshu, Jike, Bilibili, and Zhihu to find "Vibe Coders" and developers. You understand their unique pain points (e.g., global payment, traffic acquisition, cross-border compliance).
- **International:** You search X, Reddit, HN, and ProductHunt for global trends.
- **Multi-lingual:** You can research in Chinese and output in English, or vice versa, to help the product bridge the gap between markets. 

**5. NEVER GIVE THE SAME ADVICE TWICE**
Every product is different. A SaaS tool for developers grows COMPLETELY differently from an e-commerce store for pet owners.
- Cameron Trew hit $62K MRR in 3 months through trusted network distribution (no PH, no Reddit)
- Senja hit $50K MRR through Twitter content + cold DMs to people using screenshots as testimonials
- One founder runs 30 small apps making $22K/month total (portfolio strategy)
- Another revived a 17-year-old project for $26K/month (old idea + new execution)

Match the strategy to the product, the founder's strengths, and the market reality.

**5. DEMAND SPECIFICITY FROM YOURSELF**
When you output a strategy, it must pass this test:
"Can the founder copy-paste this and execute it in the next 30 minutes?"

If the answer is no, you're being too vague. Rewrite.

Every post must be fully written. Every email must be fully written.
Every DM must be personalized to a real person (found via research).
Every timeline must have specific dates and numbers.

## YOUR WORKFLOW

Step 1: If you don't know the product well → ask_user for key details
Step 2: RESEARCH (mandatory — use at least 2 tools before any strategy)
  - Search competitors: web_search
  - Find target users: social_search
  - Analyze competitor sites: competitor_analyze or scrape_website
Step 3: Consult relevant experts (not all 13 — pick the 3-4 most relevant)
Step 4: Synthesize into a specific, executable plan
Step 5: Have the critic review it
Step 6: Output the final plan with ALL content written

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

## CRITICAL RULE

If this is the user's first message about their product:
→ Your FIRST action must be a tool call (web_search or social_search)
→ NOT an output. NOT an ask_user. RESEARCH FIRST.

The user came here because they're tired of generic advice. Show them what real research looks like."""

    async def _execute_tool(self, action: AgentAction) -> Any:
        """执行工具，带超时和错误处理"""
        tool = self.tools.get(action.tool_name)
        if not tool:
            return {"error": f"Tool {action.tool_name} not found"}

        try:
            result = await asyncio.wait_for(
                tool.execute(**action.tool_args or {}),
                timeout=60.0,
            )
            return result
        except asyncio.TimeoutError:
            return {"error": f"Tool {action.tool_name} timed out"}
        except Exception as e:
            return {"error": str(e)}

    async def _consult_expert(self, action: AgentAction, context: dict) -> str:
        """调度专家 Agent"""
        expert = self.experts.get(action.expert_id)
        if not expert:
            return f"Expert {action.expert_id} not found"

        return await expert.analyze(context, action.content)

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

        # 构建上下文摘要注入到消息中
        context_summary_parts = []
        # 品牌配置优先（最重要的上下文）
        if brand_config:
            from app.api.v2.brand import get_brand_context
            brand_text = get_brand_context(brand_config)
            if brand_text:
                context_summary_parts.append(brand_text)
        if product:
            context_summary_parts.append(f"[Product info]: {json.dumps(product, ensure_ascii=False, default=str)}")
        if competitors:
            context_summary_parts.append(f"[Competitor data]: {json.dumps(competitors, ensure_ascii=False, default=str)[:500]}")
        if strategy:
            context_summary_parts.append(f"[Current strategy]: {json.dumps(strategy, ensure_ascii=False, default=str)[:500]}")
        if results:
            context_summary_parts.append(f"[Execution results]: {json.dumps(results, ensure_ascii=False, default=str)[:300]}")
        if growth_patterns:
            patterns_text = growth_patterns.get("patterns", "")
            if patterns_text:
                context_summary_parts.append(f"[Growth patterns learned from past actions]:\n{patterns_text[:500]}")

        # 消息列表：如果有上下文摘要，作为第一条 system reminder 注入
        messages = []
        if context_summary_parts:
            messages.append({
                "role": "user",
                "content": "[系统注入的背景信息，不是用户说的]\n" + "\n".join(context_summary_parts),
            })
            messages.append({
                "role": "assistant",
                "content": "收到，我已了解背景信息。",
            })

        # 加入消息历史（截取最近 20 条，避免超 token）
        recent_history = self._message_history[-20:]
        messages.extend(recent_history)

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
        """持久化 Loop 状态"""
        await self.memory.save(f"loop_state_{self.state.session_id}", {
            "session_id": self.state.session_id,
            "phase": self.state.phase.value,
            "turn_count": self.state.turn_count,
            "tokens_used": self.state.total_tokens_used,
            "pending_tasks": self.state.pending_user_tasks,
            "expert_outputs_keys": list(self.state.expert_outputs.keys()),
            "is_waiting": self.state.is_waiting_for_user,
            "message_history": self._message_history,
        })

    async def _load_state(self):
        """从磁盘加载 Loop 状态"""
        data = await self.memory.load(f"loop_state_{self.state.session_id}")
        if not data:
            return

        logger.info(f"Loading session state for {self.state.session_id}")
        self.state.phase = LoopPhase(data.get("phase", LoopPhase.INTAKE))
        self.state.turn_count = data.get("turn_count", 0)
        self.state.total_tokens_used = data.get("tokens_used", 0)
        self.state.pending_user_tasks = data.get("pending_tasks", [])
        self.state.is_waiting_for_user = data.get("is_waiting", False)
        self._message_history = data.get("message_history", [])
        
        # 加载已有的专家输出到内存
        for expert_id in data.get("expert_outputs_keys", []):
            output = await self.memory.load(f"expert_output_{self.state.session_id}_{expert_id}", category="research")
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
                "description": "Search the internet for global and domestic (China) info. Supports multi-language.",
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
                "description": "Search social media for discussions. Platforms: reddit, x, hackernews, producthunt, linkedin, xiaohongshu, jike, bilibili, zhihu.",
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
                "description": "Ask the user a question to get information you need.",
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
            elif name in ("web_search", "social_search", "scrape_website", "competitor_analyze", "deep_scrape", "write_post", "write_email", "submit_directory", "set_active_campaign"):
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
                        if extra_name in ("web_search", "social_search", "scrape_website", "competitor_analyze", "deep_scrape"):
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

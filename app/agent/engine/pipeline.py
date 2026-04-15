"""
CrabRes Pipeline Runner — 代码流水线 + LLM 自由发挥 + 防护栏审核

设计原则（来自调研）：
1. 代码控制"什么时候该做什么"（顺序），LLM 控制"该怎么做"（内容）
2. 防护栏是地板不是天花板——弱模型触发拦截，好模型永远碰不到
3. 13 专家圆桌保留——但只在代码判断"数据足够"时才触发
4. 每步只给该步需要的 context（上下文隔离）

流水线：
  Step 1: UNDERSTAND — 理解用户要什么
  Step 2: RESEARCH  — 搜索真实市场数据
  Step 3: ANALYZE   — 调专家圆桌分析（或单 LLM 分析）
  Step 4: RESPOND   — 综合输出给用户
  
对话式路径（不走流水线的场景）：
  - 打招呼 → 直接回复
  - 问"你是什么" → 硬编码回复
  - 简单追问 → LLM 直接回答（不调工具不调专家）
"""

import asyncio
import json
import logging
import time
import re
from typing import Any, Optional, AsyncIterator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    """流水线状态"""
    session_id: str
    turn_count: int = 0
    product_info: dict = field(default_factory=dict)
    research_data: list = field(default_factory=list)
    expert_outputs: dict = field(default_factory=dict)
    message_history: list = field(default_factory=list)
    scraped_urls: set = field(default_factory=set)
    searched_queries: set = field(default_factory=set)
    ask_count: int = 0
    created_at: float = field(default_factory=time.time)


class PipelineRunner:
    """
    CrabRes 流水线 Agent
    
    和 AgentLoop 的区别：
    - AgentLoop: LLM 决定每一步做什么（Coordinator 模式）
    - PipelineRunner: 代码决定流程，LLM 在每步内自由发挥
    
    好模型接入后：
    - 防护栏对好模型透明（它不会触发任何拦截）
    - 好模型可以自由决定是否需要更多搜索、更多专家
    - 代码只做执行和最低限度的安全检查
    """

    def __init__(self, session_id: str, llm_service, tool_registry, expert_pool, memory):
        self.state = PipelineState(session_id=session_id)
        self.llm = llm_service
        self.tools = tool_registry
        self.experts = expert_pool
        self.memory = memory
        self._language = "en"

        # Mood Sensing
        from app.agent.engine.mood_sensing import MoodSensor
        self.mood_sensor = MoodSensor()

        # Deep Strategy
        from app.agent.engine.deep_strategy import get_deep_strategy_engine
        self.deep_strategy = get_deep_strategy_engine()

        from pathlib import Path
        workspace_base = Path(str(memory.base_dir)).parent / "workspace"
        workspace_base.mkdir(parents=True, exist_ok=True)

    async def run(self, user_message: str, language: str = "en") -> AsyncIterator[dict]:
        """处理用户消息，yield 流式事件"""
        self._language = language
        self.state.turn_count += 1
        self.state.message_history.append({"role": "user", "content": user_message})

        msg = user_message.strip()
        msg_lower = msg.lower()

        # ========== Deep Strategy 检测 ==========
        from app.agent.engine.deep_strategy import should_trigger_deep_strategy
        if should_trigger_deep_strategy(msg):
            yield {"type": "status", "content": "Launching deep strategy session..."}
            try:
                job = await self.deep_strategy.create_job(
                    user_id=str(self.memory.base_dir).split("/")[-1],
                    session_id=self.state.session_id,
                    request=msg,
                    llm_service=self.llm,
                    tool_registry=self.tools,
                    expert_pool=self.experts,
                    memory=self.memory,
                )
                reply = f"Deep Strategy session launched (ID: {job.id}). I'm running a full 8-expert roundtable in the background. This takes 2-5 minutes — I'll notify you when it's ready."
                yield {"type": "message", "content": reply}
                self.state.message_history.append({"role": "assistant", "content": reply})
                return
            except Exception as e:
                logger.warning(f"Deep Strategy failed: {e}")

        # ========== Mood Sensing ==========
        mood_signal = self.mood_sensor.detect(msg)
        self._mood_injection = ""
        if mood_signal:
            self._mood_injection = self.mood_sensor.get_prompt_injection(mood_signal)
            logger.info(f"Mood: {mood_signal.mood.value} ({mood_signal.confidence:.2f})")

        # ========== 快速路径 ==========

        # 1. 纯打招呼（精确匹配，0 token）
        if self._is_greeting(msg_lower):
            reply = await self._quick_reply(msg, "The user is greeting you. Reply warmly in 1-2 sentences and ask what they're building or how you can help.")
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            return

        # 2. 短消息智能路由（用 LLM 判断意图，不再用 len < 50 硬判断）
        # 🔥 如果已经有产品上下文（之前聊过 crabres 或有 product_info），跳过短消息路由直接进流水线
        has_existing_product = bool(self.state.product_info.get("name")) or any(
            self._is_self_referencing(m.get("content", ""))
            for m in self.state.message_history[-6:]
            if m.get("role") == "user"
        )
        if len(msg) < 80 and not self._has_product_signals(msg_lower) and not has_existing_product:
            intent = await self._classify_intent(msg)
            logger.info(f"Intent classification: {intent}")

            if intent == "self_awareness":
                # 区分"问你是谁"和"给你自己做增长策略"
                # 前者直接回复，后者进流水线
                action_triggers = [
                    "增长", "策略", "计划", "growth", "strategy", "plan",
                    "做", "制定", "执行", "帮", "给", "make", "create", "build",
                    "市场", "竞品", "分析", "market", "competitor", "analyze",
                ]
                wants_action = any(t in msg_lower for t in action_triggers)
                if wants_action:
                    # 用户要 CrabRes 为自己做事 → 注入自我认知后进完整流水线
                    pass  # 继续往下走，进入流水线
                else:
                    # 纯粹问"你是谁" → 简短回复
                    reply = await self._self_aware_reply(msg)
                    yield {"type": "message", "content": reply}
                    self.state.message_history.append({"role": "assistant", "content": reply})
                    return
            elif intent == "greeting":
                reply = await self._quick_reply(msg, "The user is greeting you. Reply warmly in 1-2 sentences and ask what they're building.")
                yield {"type": "message", "content": reply}
                self.state.message_history.append({"role": "assistant", "content": reply})
                return
            elif intent == "chitchat":
                # 闲聊但不是产品相关 → 友好回复并引导
                reply = await self._quick_reply(msg, "The user is chatting casually. Reply naturally based on conversation history, then gently steer toward how you can help with growth strategy. Don't repeat the same question if you already asked it.")
                yield {"type": "message", "content": reply}
                self.state.message_history.append({"role": "assistant", "content": reply})
                return
            # intent == "product" or "followup" → 继续进流水线

        # ========== 流水线路径 ==========
        # 注意：ask_count 不在这里重置，它在 PipelineState 中初始化为 0
        # 只有当用户提供了足够信息后才重置（见 _step_understand 之后的逻辑）

        # 🔥 最后防线：如果消息太短（< 20 字符）且没有产品信号且没有历史研究数据
        # → 这几乎不可能是一个有效的产品描述，走 chitchat 路径
        if len(msg) < 20 and not self._has_product_signals(msg_lower) and not self.state.research_data:
            reply = await self._quick_reply(msg, f"The user said something short and vague: \"{msg}\". This is NOT a product description. Reply naturally based on conversation history. If you don't know what they're referring to, ask what product they'd like help with. Be warm and casual.")
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            return

        # 🔥 记忆注入：加载历史产品信息和增长模式，让 Agent 有"记忆感"
        prior_product = await self.memory.load("product")
        if prior_product and isinstance(prior_product, dict) and not self.state.product_info:
            self.state.product_info.update({k: v for k, v in prior_product.items() if not k.startswith("_")})
        
        # 加载增长模式（Growth Dream 蒸馏的结果）
        growth_patterns = await self.memory.load("growth_patterns", category="strategy")
        if growth_patterns and isinstance(growth_patterns, dict):
            self._growth_patterns = growth_patterns.get("patterns", "")
        else:
            self._growth_patterns = ""

        # 🔥 语义记忆搜索：用当前消息搜索相关历史记忆
        try:
            self._memory_context = await self.memory.search_for_prompt(msg)
        except Exception:
            self._memory_context = ""

        # 🔥 反思注入：加载自我改进笔记
        try:
            from app.agent.engine.reflection import ReflectionEngine
            reflection_engine = ReflectionEngine(self.memory, self.llm)
            self._reflection_context = reflection_engine.get_improvement_prompt()
            # 检测用户负面反馈并记录
            await reflection_engine.feedback_reflection(msg)
        except Exception:
            self._reflection_context = ""

        # 🔥 目标注入：加载当前增长目标
        try:
            from app.agent.engine.goal_tracker import GoalTracker
            goal_tracker = GoalTracker(self.memory)
            self._goal_context = goal_tracker.get_goal_prompt()
        except Exception:
            self._goal_context = ""

        # 🔥 Skill 加载：搜索与当前任务相关的已学技能
        try:
            from app.agent.skills import SkillStore
            user_id = str(self.memory.base_dir).split("/")[-1]
            skill_store = SkillStore(base_dir=f".crabres/skills/{user_id}")
            self._skill_context = await skill_store.get_skills_for_prompt(msg)
        except Exception:
            self._skill_context = ""

        # 🔥 追问检测：如果上一轮已经搜过+有专家输出，新消息是追问/补充信息
        has_prior_research = len(self.state.research_data) > 0
        has_prior_experts = len(self.state.expert_outputs) > 0
        is_followup = has_prior_research and len(msg) < 200

        if is_followup and (has_prior_research or has_prior_experts):
            # 🔥 检测是否是工具请求（用户要求 Agent 执行某个动作）
            tool_triggers = [
                "browser", "浏览器", "browse", "打开", "看看", "访问", "scrape",
                "搜索", "search", "找", "查", "分析", "analyze",
                "发帖", "post", "发布", "publish", "执行", "execute",
                "写", "write", "draft", "起草",
            ]
            needs_tool = any(t in msg_lower for t in tool_triggers)

            if needs_tool:
                # 用户要求执行动作 → 调用工具而不是纯文本回答
                yield {"type": "status", "content": "Executing your request..."}
                reply = await self._tool_followup(msg)
                yield {"type": "message", "content": reply}
                self.state.message_history.append({"role": "assistant", "content": reply})
                await self._persist()
                return

            # 普通追问：用已有数据 + 新信息直接回答
            yield {"type": "status", "content": "Updating analysis with your input..."}
            reply = await self._followup_reply(msg)
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            await self._persist()
            return

        # Step 1: UNDERSTAND
        yield {"type": "status", "content": "Understanding your product..."}
        product_info = await self._step_understand(msg)
        self.state.product_info.update(product_info)
        await self.memory.save("product", self.state.product_info)

        # 🔥 信息充分度检测：如果产品信息太模糊，先追问而不是生成垃圾 Playbook
        has_name = bool(product_info.get("name") and product_info["name"] not in ("product", "unknown", ""))
        has_desc = bool(product_info.get("description") and len(product_info.get("description", "")) > 30)
        has_type = bool(product_info.get("type"))
        is_self = product_info.get("is_self", False)
        # 额外检测：原始消息是否太短（< 30 字符的消息不太可能是完整的产品描述）
        raw_too_short = len(product_info.get("raw_description", "")) < 30
        info_score = sum([has_name, has_desc, has_type, is_self])
        # 如果原始消息太短，即使 LLM 提取出了一些字段，也要降分
        if raw_too_short and not is_self:
            info_score = min(info_score, 1)

        # 🔥 额外检查：如果历史对话中已经提到过 CrabRes 或有产品信息，不追问
        has_prior_product_context = any(
            self._is_self_referencing(m.get("content", ""))
            for m in self.state.message_history[-6:]
            if m.get("role") == "user"
        ) or bool(self.state.product_info.get("name"))
        
        if info_score < 2 and not is_self and not has_prior_product_context and self.state.ask_count < 2:
            # 信息不够，用 LLM 生成一个自然的追问（不是硬编码）
            self.state.ask_count += 1
            lang = "Chinese" if self._language == "zh" else "English"
            from app.agent.engine.llm_adapter import TaskTier
            clarify = await self.llm.generate(
                system_prompt=f"""You are CrabRes. The user gave you a product description but it's too vague to create a useful growth plan. 
Ask ONE specific question to get the most critical missing info. Respond in {lang}.
Be warm and casual, not robotic. Don't list multiple questions — just ONE.
Examples of good questions:
- "Cool! What does [product] actually do? Like, what's the one-sentence pitch?"
- "Got it — who's the target user? Developers? Designers? Small business owners?"
- "Interesting! What's the main problem it solves?"
Do NOT say "Could you provide more details" — be specific about what you need.""",
                messages=self.state.message_history[-4:],
                tier=TaskTier.PARSING,
                max_tokens=150,
            )
            reply = clarify.content
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            await self._persist()
            return

        # Step 2: RESEARCH
        yield {"type": "status", "content": "Researching your market..."}
        research_results = await self._step_research(self.state.product_info)
        self.state.research_data.extend(research_results)

        # 质量门控：有效结果够不够
        useful = [r for r in research_results if r.get("useful")]
        
        if len(useful) >= 2:
            # Step 3: ANALYZE（有数据 → 开圆桌）
            yield {"type": "status", "content": "Assembling expert roundtable..."}
            analysis, expert_events = await self._step_analyze(self.state.product_info, useful)
            for evt in expert_events:
                yield evt

            # Step 4: RESPOND（综合输出）
            yield {"type": "status", "content": "Synthesizing growth strategy..."}
            response = await self._step_respond(self.state.product_info, useful, analysis)
        else:
            # 数据不够 → 单 LLM 基于已知信息回答（不浪费 token 开圆桌）
            yield {"type": "status", "content": "Analyzing available data..."}
            response = await self._step_respond_light(self.state.product_info, research_results)

        yield {"type": "message", "content": response}
        self.state.message_history.append({"role": "assistant", "content": response})

        # Step 5: DELIVER — 生成可交付物，保存到 workspace
        if len(useful if 'useful' in dir() else []) >= 2 or len(self.state.research_data) > 0:
            yield {"type": "status", "content": "Preparing deliverables..."}
            deliverables = await self._step_deliver(self.state.product_info, self.state.research_data, response)
            if deliverables:
                # 告诉用户生成了什么
                files_msg = "\n".join(f"- {d['name']}: {d['desc']}" for d in deliverables)
                yield {"type": "message", "content": f"I've prepared these for you:\n\n{files_msg}\n\nYou can find them in your workspace."}

        # 持久化
        await self._persist()

    # ========== 流水线步骤 ==========

    # CrabRes 自身的产品信息（硬编码，用于自我认知场景）
    CRABRES_PRODUCT_INFO = {
        "name": "CrabRes",
        "description": "AI growth strategy agent that helps indie developers and small teams research markets, analyze competitors, and execute actionable growth plans",
        "type": "saas",
        "audience": "indie developers, solo founders, small SaaS teams (1-5 people)",
        "goal": "acquire first 1000 users through organic channels",
        "budget": "$0",
        "url": "https://crab-researcher.vercel.app",
        "features": [
            "13 AI expert advisors (market researcher, content strategist, social media, etc.)",
            "Real-time web research and competitor analysis",
            "Automated content drafting (Reddit, Twitter/X, email)",
            "Structured Growth Playbooks with step-by-step execution",
            "Browser automation for deep scraping",
            "Execution engine that actually posts/sends (not just suggests)",
        ],
        "competitors": [
            {"name": "GrowthBook", "focus": "A/B testing and feature flags"},
            {"name": "Jasper", "focus": "AI copywriting"},
            {"name": "Copy.ai", "focus": "AI marketing copy"},
            {"name": "Writesonic", "focus": "AI content generation"},
        ],
        "differentiator": "Not just AI copywriting — full research + strategy + execution pipeline. CrabRes is an employee, not a tool.",
        "search_keywords": ["AI growth agent", "SaaS marketing automation", "indie developer growth tool", "AI competitor analysis", "automated growth strategy"],
    }

    def _is_self_referencing(self, msg: str) -> bool:
        """检测用户是否在说 CrabRes 自身"""
        msg_lower = msg.lower()
        triggers = [
            "crabres", "crab-res", "crab res", "你自己", "你本身",
            "你是一个产品", "你是产品", "给你自己", "为你自己",
            "for yourself", "about yourself", "your own", "you are a product",
            "my project is you", "the product is you",
        ]
        return any(t in msg_lower for t in triggers)

    async def _step_understand(self, user_message: str) -> dict:
        """Step 1: 从用户消息提取产品信息"""
        from app.agent.engine.llm_adapter import TaskTier

        # 🔥 自我认知：检查当前消息 OR 最近历史中是否提到 CrabRes
        is_self_ref = self._is_self_referencing(user_message)
        if not is_self_ref:
            # 检查最近 6 条用户消息是否提到过 CrabRes
            for m in self.state.message_history[-6:]:
                if m.get("role") == "user" and self._is_self_referencing(m.get("content", "")):
                    is_self_ref = True
                    break
        
        if is_self_ref:
            info = dict(self.CRABRES_PRODUCT_INFO)
            info["raw_description"] = user_message
            info["is_self"] = True
            logger.info("Self-referencing detected: injecting CrabRes product info")
            return info

        # 如果消息够长且包含产品信号，让 LLM 提取结构化信息
        if len(user_message) > 30 and self._has_product_signals(user_message.lower()):
            response = await self.llm.generate(
                system_prompt="Extract product information from the user's message. Return a JSON object with: name, description (what the product does in one sentence), type (saas/tool/consumer_app/ecommerce/etc), audience (who uses it), goal, budget, search_keywords (3-5 keywords for searching competitors and market, DO NOT use the product name, use descriptive terms like 'AI resume optimizer' not 'ResumeAI'). Return ONLY valid JSON.",
                messages=[{"role": "user", "content": user_message}],
                tier=TaskTier.PARSING,
                max_tokens=300,
            )
            try:
                info = json.loads(response.content)
                if isinstance(info, dict):
                    info["raw_description"] = user_message
                    return info
            except (json.JSONDecodeError, TypeError):
                pass

        return {"raw_description": user_message}

    async def _step_research(self, product_info: dict) -> list:
        """Step 2: 并行搜索市场数据"""
        results = []
        search_tool = self.tools.get("web_search")
        social_tool = self.tools.get("social_search")

        if not search_tool:
            return results

        # 🔥 关键：用产品描述/类型/受众搜索，不用产品名！
        desc = product_info.get("description", "")
        audience = product_info.get("audience", "")
        ptype = product_info.get("type", "")
        raw = product_info.get("raw_description", "")
        keywords = product_info.get("search_keywords", [])
        
        # 优先用 LLM 提取的 search_keywords
        if keywords and isinstance(keywords, list) and len(keywords) >= 2:
            search_base = " ".join(keywords[:4])
        elif desc and len(desc) > 10:
            search_base = desc[:100]
        elif raw:
            search_base = raw[:150]
        else:
            search_base = "software product"
        
        if audience and audience.lower() not in search_base.lower():
            search_base = f"{search_base} for {audience}"

        # 构建 3 个不同角度的搜索
        queries = [
            f"{search_base} competitors pricing comparison 2026",
            f"{search_base} user acquisition channels best practices",
        ]
        if social_tool:
            # 社交搜索用更自然的语言
            social_query = f"{audience or 'developers'} {desc[:50] or search_base[:50]} recommendation"
            queries.append(social_query)

        # 去重
        queries = [q for q in queries if q not in self.state.searched_queries]
        for q in queries:
            self.state.searched_queries.add(q)

        # 并行执行
        tasks = []
        for q in queries[:3]:
            if "reddit" in q and social_tool:
                tasks.append(self._exec_tool(social_tool, query=q, platforms=["reddit", "hackernews"]))
            else:
                tasks.append(self._exec_tool(search_tool, query=q))

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                results.append({"query": queries[i] if i < len(queries) else "", "result": {}, "useful": False})
            elif isinstance(r, dict):
                content_len = len(json.dumps(r, default=str))
                results.append({
                    "query": queries[i] if i < len(queries) else "",
                    "result": r,
                    "useful": content_len > 200 and not r.get("error"),
                })
            else:
                results.append({"query": queries[i] if i < len(queries) else "", "result": {}, "useful": False})

        return results

    async def _step_analyze(self, product_info: dict, useful_results: list) -> tuple[dict, list]:
        """Step 3: 专家圆桌分析（只在有足够数据时调用）"""
        from app.agent.engine.context_engine import select_roundtable_experts, get_expert_execution_order

        product_type = product_info.get("type", "default")
        expert_ids = select_roundtable_experts(product_type, product_info.get("raw_description", ""))
        batches = get_expert_execution_order(expert_ids)

        # 构建研究摘要
        research_summary = "\n".join(
            f"- {r['query']}: {json.dumps(r['result'], ensure_ascii=False, default=str)[:500]}"
            for r in useful_results[:5]
        )

        # Load relevant learned skills for experts
        skill_injection = getattr(self, '_skill_context', '')
        memory_injection = getattr(self, '_memory_context', '')

        task = (
            f"Analyze this product and create a growth strategy.\n\n"
            f"Product: {json.dumps(product_info, ensure_ascii=False, default=str)[:800]}\n\n"
            f"Research data:\n{research_summary}"
        )
        if skill_injection:
            task += f"\n\n{skill_injection}"
        if memory_injection:
            task += f"\n\n{memory_injection}"

        context = {
            "product": product_info,
            "tool_results": useful_results,
            "user_message": product_info.get("raw_description", ""),
            "expert_outputs": {},
            "language": self._language,  # 🔥 Pass language to experts for consistency
        }

        expert_results = {}
        events = []

        for batch in batches:
            batch_tasks = []
            for eid in batch:
                expert = self.experts.get(eid)
                if not expert:
                    continue
                # 注入前批结果
                enriched_task = task
                if expert_results:
                    enriched_task += "\n\nOther experts' views:\n"
                    for k, v in expert_results.items():
                        enriched_task += f"- {k}: {v[:300]}\n"

                batch_tasks.append(self._run_expert(expert, context, enriched_task))

            results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for j, r in enumerate(results):
                eid = batch[j] if j < len(batch) else "unknown"
                expert = self.experts.get(eid)
                if isinstance(r, Exception):
                    output = f"[Analysis unavailable: {str(r)[:100]}]"
                elif isinstance(r, str):
                    output = r
                else:
                    output = str(r)

                expert_results[eid] = output
                self.state.expert_outputs[eid] = output
                context["expert_outputs"][eid] = output

                events.append({"type": "expert_thinking", "expert_id": eid, "content": f"{expert.name if expert else eid} is analyzing..."})
                events.append({"type": "expert_thinking", "expert_id": eid, "content": output})

        return expert_results, events

    async def _step_respond(self, product_info: dict, useful_results: list, expert_analysis: dict) -> str:
        """Step 4: 综合输出（有专家数据 + 知识驱动的渠道建议）"""
        from app.agent.engine.llm_adapter import TaskTier
        from app.agent.knowledge.channel_playbooks import get_actionable_advice

        lang = "Chinese" if self._language == "zh" else "English"
        research_summary = "\n".join(
            f"- {r['query']}: {json.dumps(r['result'], ensure_ascii=False, default=str)[:400]}"
            for r in useful_results[:5]
        )
        expert_summary = "\n\n".join(
            f"### {eid}\n{output[:1000]}"
            for eid, output in expert_analysis.items()
        )
        
        # 🔥 知识注入：基于产品类型的具体渠道建议
        product_type = product_info.get("type", "default")
        budget = product_info.get("budget", "")
        channel_advice = get_actionable_advice(product_type, budget)

        # 🔥 自我认知注入
        self_note = ""
        if product_info.get("is_self"):
            self_note = """
IMPORTANT: You ARE CrabRes. The user asked you to create a growth strategy for YOURSELF.
Be self-aware and enthusiastic — you're analyzing your own market and competitors.
Reference your own features, your own differentiators, your own target audience.
Don't say "your product" — say "we" or "CrabRes" or "our tool".
"""

        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth agent. Respond ONLY in {lang}.
{self_note}
You have research data and expert opinions. Write a response like you're talking to a friend who asked for help.

STRICT FORMAT RULES:
- Do NOT use ### headers or numbered sections like "1. Strategy A", "2. Strategy B"
- Do NOT use phrases like "Actionable Growth Strategy" or "Key Findings" or "Conclusion"
- Write in natural paragraphs, like Claude or a smart friend would
- Use **bold** only for competitor names and key numbers, not for section titles
- Start with the most important insight, not a summary header
- Include ONE hard truth — something uncomfortable but true
- End with 2-3 specific things to do THIS WEEK (not a numbered list of 10)
- Total length: 3-5 paragraphs. Not more.

SPECIFICITY RULES (CRITICAL — violation = generic garbage):
- NEVER say "找到3-5个subreddit" — say exactly WHICH subreddits (e.g., r/SideProject has 120K members, r/indiehackers has 95K)
- NEVER say "回复相关领域的影响者" — say exactly WHO to reply to (e.g., "@levelsio, @marc_louvion, @danshipper")
- NEVER say "准备200+支持者邮件列表" without saying HOW (e.g., "use your existing Twitter followers + add a waitlist on your landing page")
- EVERY tactic must include: specific platform + specific community/person + specific format + specific timing
- If you mention a competitor, include at least ONE specific data point (pricing, traffic, feature)
- The user should be able to execute your advice in the next 2 hours without googling anything

{getattr(self, '_mood_injection', '')}

{f"MEMORY — what you know about this user from past sessions:{chr(10)}" + getattr(self, '_growth_patterns', '') if getattr(self, '_growth_patterns', '') else ''}

{getattr(self, '_reflection_context', '')}
{getattr(self, '_goal_context', '')}""",
            messages=[{
                "role": "user",
                "content": f"Product: {json.dumps(product_info, ensure_ascii=False, default=str)[:600]}\n\nResearch:\n{research_summary}\n\nExpert analysis:\n{expert_summary}\n\nChannel-specific playbooks (use these specific tactics, don't generalize):\n{channel_advice}\n\nSynthesize into a natural, conversational growth strategy. Reference the specific channel tactics above.",
            }],
            tier=TaskTier.CRITICAL,
            max_tokens=4096,
        )
        return response.content

    async def _step_respond_light(self, product_info: dict, research_results: list) -> str:
        """Step 4 (light): 搜索数据不够时的基础回答"""
        from app.agent.engine.llm_adapter import TaskTier

        lang = "Chinese" if self._language == "zh" else "English"
        available_data = "\n".join(
            f"- {r['query']}: {json.dumps(r.get('result', {}), ensure_ascii=False, default=str)[:300]}"
            for r in research_results[:3]
        )

        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth agent. Respond ONLY in {lang}.

You searched for market data but results were limited. Be honest about this.
Give helpful directional advice based on what you know, and suggest what the user can provide to help you do a better search (competitor names, website URLs, etc).

Be brief and natural. 3-5 paragraphs max.""",
            messages=[{
                "role": "user",
                "content": f"Product: {json.dumps(product_info, ensure_ascii=False, default=str)[:600]}\n\nSearch results (limited):\n{available_data}\n\nGive initial advice and ask for more info to do better research.",
            }],
            tier=TaskTier.THINKING,
            max_tokens=1500,
        )
        return response.content

    async def _step_deliver(self, product_info: dict, research_data: list, strategy_response: str) -> list:
        """
        Step 5: DELIVER — 生成可交付物并保存到 workspace
        
        这是"做事"和"说话"的区别。
        不只是告诉用户"去 Reddit 发帖"，而是直接写好帖子。
        """
        from app.agent.engine.llm_adapter import TaskTier
        from pathlib import Path

        # 🔥 质量门控：如果产品信息太模糊，不生成交付物（垃圾进 = 垃圾出）
        product_name = product_info.get("name", "product")
        product_desc_raw = product_info.get("raw_description", "")
        has_real_name = product_name not in ("product", "unknown", "")
        has_real_desc = bool(product_info.get("description") and len(product_info.get("description", "")) > 20)
        if not has_real_name and not has_real_desc and len(product_desc_raw) < 30:
            logger.warning(f"Skipping deliverables: product info too vague (name={product_name}, desc_len={len(product_desc_raw)})")
            return []

        workspace = Path(str(self.memory.base_dir)).parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        for sub in ["drafts", "reports", "plans"]:
            (workspace / sub).mkdir(exist_ok=True)

        deliverables = []
        lang = "Chinese" if self._language == "zh" else "English"
        product_desc = json.dumps(product_info, ensure_ascii=False, default=str)[:500]

        # 1. 竞品分析报告
        research_text = "\n".join(
            f"- {r.get('query','')}: {json.dumps(r.get('result',{}), ensure_ascii=False, default=str)[:600]}"
            for r in research_data[:5] if r.get("useful")
        )
        if research_text:
            try:
                report = await self.llm.generate(
                    system_prompt=f"""Generate a competitor analysis report in {lang}. Be specific — use real names, numbers, URLs from the research data. Format as clean markdown. Include: competitor names, their pricing, traffic estimates, strengths, weaknesses, and gaps we can exploit. 500-800 words.""",
                    messages=[{"role": "user", "content": f"Product: {product_desc}\n\nResearch data:\n{research_text}"}],
                    tier=TaskTier.THINKING,
                    max_tokens=1500,
                )
                path = workspace / "reports" / f"competitor_analysis_{product_name.lower().replace(' ','_')}.md"
                file_content = f"# Competitor Analysis: {product_name}\n\n{report.content}"
                path.write_text(file_content, encoding="utf-8")
                await self._backup_file_to_memory(f"reports/{path.name}", file_content)
                deliverables.append({"name": f"Competitor Analysis", "desc": f"reports/{path.name}", "path": str(path)})
            except Exception as e:
                logger.warning(f"Failed to generate competitor report: {e}")

        # 2. 第一篇 Reddit/X 帖子草稿
        try:
            draft = await self.llm.generate(
                system_prompt=f"""Write a ready-to-post social media draft in {lang}. 

Write TWO versions:
1. A Reddit post for a relevant subreddit (title + body, genuine tone, NOT promotional)
2. A Twitter/X thread (hook tweet + 3-5 follow-up tweets)

Use the product info and strategy to make it specific. Include the actual product name. The Reddit post should sound like a real person sharing their experience, NOT an ad.""",
                messages=[{"role": "user", "content": f"Product: {product_desc}\n\nStrategy context: {strategy_response[:800]}"}],
                tier=TaskTier.WRITING,
                max_tokens=1200,
            )
            path = workspace / "drafts" / f"first_posts_{product_name.lower().replace(' ','_')}.md"
            file_content = f"# Content Drafts: {product_name}\n\n{draft.content}"
            path.write_text(file_content, encoding="utf-8")
            await self._backup_file_to_memory(f"drafts/{path.name}", file_content)
            deliverables.append({"name": "Content Drafts (Reddit + X)", "desc": f"drafts/{path.name}", "path": str(path)})
        except Exception as e:
            logger.warning(f"Failed to generate content drafts: {e}")

        # 3. 30 天增长计划
        try:
            plan = await self.llm.generate(
                system_prompt=f"""Create a 30-day growth plan in {lang}. 

Format: Week 1 / Week 2 / Week 3 / Week 4, each with 3-4 specific daily/weekly tasks.
Be very specific: which platform, what type of content, what time to post, what metrics to track.
Base it on the strategy and research data provided.""",
                messages=[{"role": "user", "content": f"Product: {product_desc}\n\nStrategy: {strategy_response[:800]}"}],
                tier=TaskTier.THINKING,
                max_tokens=1500,
            )
            path = workspace / "plans" / f"30day_growth_{product_name.lower().replace(' ','_')}.md"
            file_content = f"# 30-Day Growth Plan: {product_name}\n\n{plan.content}"
            path.write_text(file_content, encoding="utf-8")
            await self._backup_file_to_memory(f"plans/{path.name}", file_content)
            deliverables.append({"name": "30-Day Growth Plan", "desc": f"plans/{path.name}", "path": str(path)})
        except Exception as e:
            logger.warning(f"Failed to generate growth plan: {e}")

        # 4. 生成结构化 Playbook（供 Plan 页面展示）
        try:
            from app.agent.engine.llm_adapter import TaskTier as _TaskTier
            from app.agent.memory.playbooks import PlaybookStore, parse_playbook_from_llm
            from app.agent.knowledge.channel_playbooks import get_channels_for_product, get_channel_sop
            from app.agent.knowledge.playbook_templates import COMMUNITY_GROWTH_TEMPLATE

            # 🔥 注入产品类型对应的渠道 SOP（具体到 subreddit、发帖时间、模板）
            p_type = product_info.get("type", "saas")
            channels = get_channels_for_product(p_type)
            channel_sops = ""
            for ch_key in channels[:3]:
                sop = get_channel_sop(ch_key)
                if sop:
                    channel_sops += f"\n### {sop.get('name', ch_key)}\n"
                    channel_sops += f"Why: {sop.get('why', '')}\n"
                    channel_sops += "Quick start:\n"
                    for task in sop.get('quick_start', [])[:4]:
                        channel_sops += f"  - {task}\n"
                    channel_sops += f"Post template title: {sop.get('template_title', '')}\n"
                    channel_sops += f"Post template body: {sop.get('template_body', '')}\n"
                    channel_sops += f"Good metrics: {sop.get('good_metrics', '')}\n"
                    channel_sops += f"Don't: {', '.join(sop.get('dont', [])[:3])}\n"

            # 🔥 注入模板结构作为 few-shot（用 Community Growth 模板做示例）
            import json as _json
            example_step = COMMUNITY_GROWTH_TEMPLATE["phases"][0]["steps"][0]
            few_shot_example = _json.dumps(example_step, ensure_ascii=False, indent=2)

            # 🔥 自我认知注入
            self_aware_note = ""
            if product_info.get("is_self"):
                self_aware_note = """
IMPORTANT: The product is CrabRes ITSELF — an AI growth agent (crab-researcher.vercel.app).
You ARE the product. Create a growth plan for yourself. Be specific:
- Competitors: GrowthBook (A/B testing), Jasper (AI copywriting), Copy.ai (AI marketing), Writesonic
- Target: indie developers, solo founders on Reddit (r/SideProject, r/indiehackers, r/SaaS), X (#buildinpublic, #indiehackers), Hacker News (Show HN)
- Differentiator: Not just AI copywriting — full research + strategy + execution pipeline
- Budget: $0 (organic only)
- Key angle: 'I built an AI that doesn\'t just give advice — it actually executes growth strategies for you'"""

            playbook_json = await self.llm.generate(
                system_prompt=f"""Generate a structured growth playbook in JSON format. Language: {lang}.
{self_aware_note}

CRITICAL RULES — VIOLATION = FAILURE:
1. This is for a solo developer or tiny team (1-3 people) with $0 total budget
2. Every step budget MUST be $0. If a step costs money, remove it or find a free alternative
3. Every step duration MUST be under 4 hours. "2 hours" is good. "5 days" is WRONG
4. Steps MUST name SPECIFIC platforms with SPECIFIC details:
   - Reddit: exact subreddit names (r/SideProject, r/indiehackers), exact post title format, body template
   - Twitter/X: exact hashtags (#buildinpublic, #indiehackers), thread format, hook formula
   - HN: "Show HN: [product] — [one-line benefit]" format
   - Email: subject line template, 3-paragraph body structure
5. NO generic steps like "Create brand identity", "Develop marketing strategy", "Secure funding", "Draft business plan"
6. NO steps requiring paid tools (no Adobe, no paid software, no ad spend)
7. Every step MUST produce a concrete deliverable: a written post, a published thread, a sent email
8. Use the CHANNEL SOPs below as source material — copy their specific tactics into steps

## CHANNEL SOPs (use these specific tactics in your steps)
{channel_sops}

## EXAMPLE OF A GOOD STEP (follow this level of specificity)
{few_shot_example}

Return ONLY valid JSON with this exact structure:
{{
  "name": "Playbook name (specific, e.g. 'Reddit + Show HN Launch Sprint')",
  "description": "One sentence",
  "suitable_for": "Solo developer / tiny team with $0 budget",
  "total_budget": "$0",
  "expected_timeline": "4 weeks",
  "expected_results": "Specific expected outcome with numbers (e.g. '50-200 signups, 3 viral posts')",
  "risk_factors": ["risk1", "risk2"],
  "priority": 1,
  "phases": [
    {{
      "name": "Phase name",
      "duration": "Day 1-3",
      "steps": [
        {{
          "order": 1,
          "title": "Step title (action verb + specific target, e.g. 'Post experience share in r/SideProject')",
          "detail": "3-5 sentences: WHAT to do, WHERE exactly, WHAT FORMAT, WHAT TEMPLATE to use. Include the actual post title format and body structure.",
          "tools": ["free tool only"],
          "budget": "$0",
          "duration": "2 hours",
          "output": "Concrete deliverable (e.g. '1 published Reddit post')",
          "success_criteria": "Measurable outcome (e.g. '>20 upvotes within 24h')",
          "common_mistakes": ["specific mistake with explanation"]
        }}
      ]
    }}
  ]
}}
Create 3 phases: Phase 1: Setup & First Post (Day 1-3, 4 steps), Phase 2: Distribution Blitz (Day 4-14, 5-6 steps), Phase 3: Iterate & Double Down (Day 15-30, 4-5 steps).
12-15 steps total.""",
                messages=[{"role": "user", "content": f"Product: {product_desc}\n\nStrategy: {strategy_response[:1000]}"}],
                tier=_TaskTier.CRITICAL,
                max_tokens=4000,
            )
            
            # Parse and save
            raw = playbook_json.content
            # Extract JSON from potential markdown code blocks
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            
            playbook = parse_playbook_from_llm(raw.strip())
            if playbook:
                store = PlaybookStore(base_dir=str(self.memory.base_dir))
                await store.save_playbook(playbook)
                deliverables.append({
                    "name": f"Growth Playbook: {playbook.name}",
                    "desc": f"Structured playbook with {playbook.total_steps} actionable steps — check the Plan tab!",
                    "path": "playbook",
                })
                logger.info(f"Playbook generated: {playbook.name} ({playbook.total_steps} steps)")
        except Exception as e:
            logger.warning(f"Failed to generate playbook: {e}")

        # ===== Step 5b: EXECUTE — 真正执行操作（不只是生成文件）=====
        # 这是"顾问"和"员工"的分水岭
        try:
            from app.agent.engine.execution import ExecutionEngine, ExecutionRequest
            from app.agent.engine.autonomous import AutonomousEngine
            from app.agent.engine.action_tracker import ActionTracker

            exec_engine = ExecutionEngine(
                tools=self.tools,
                memory=self.memory,
                autonomous=AutonomousEngine(self.memory),
                tracker=ActionTracker(),
            )

            # 用 LLM 从策略中提取可立即执行的操作
            exec_prompt = (
                "From the growth strategy, extract IMMEDIATE executable actions.\n"
                "Return ONLY valid JSON array. Each item:\n"
                '{"action_type": "reddit_post|twitter_post|send_email|reddit_comment",\n'
                ' "platform": "reddit|x|email",\n'
                ' "description": "what this does",\n'
                ' "params": {...action-specific params...}}\n\n'
                'For reddit_post: {"subreddit": "...", "title": "...", "text": "..."}\n'
                'For twitter_post: {"text": "..."}\n'
                'For send_email: {"to": "...", "subject": "...", "body": "..."}\n\n'
                "ONLY include actions that can be executed RIGHT NOW with the draft content.\n"
                "If no immediate actions, return empty array [].\n"
                "Max 3 actions per session."
            )
            exec_plan = await self.llm.generate(
                system_prompt=exec_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Strategy: {strategy_response[:1500]}\n\nProduct: {product_desc}",
                }],
                tier=TaskTier.PARSING,
                max_tokens=800,
            )

            # 解析执行计划
            raw_plan = exec_plan.content.strip()
            if "```" in raw_plan:
                raw_plan = raw_plan.split("```")[1].split("```")[0]
                if raw_plan.startswith("json"):
                    raw_plan = raw_plan[4:]

            actions = json.loads(raw_plan)
            if isinstance(actions, list):
                execution_results = []
                for act in actions[:3]:
                    req = ExecutionRequest(
                        action_type=act.get("action_type", ""),
                        platform=act.get("platform", ""),
                        description=act.get("description", ""),
                        params=act.get("params", {}),
                        source="pipeline",
                    )
                    result = await exec_engine.execute(req)
                    execution_results.append({
                        "action": act.get("action_type"),
                        "platform": act.get("platform"),
                        "status": result.status,
                        "success": result.success,
                        "url": result.url,
                    })

                if execution_results:
                    exec_summary = ", ".join(
                        f"{r['platform']}({r['status']})" for r in execution_results
                    )
                    deliverables.append({
                        "name": "Executed Actions",
                        "desc": f"{len(execution_results)} actions executed: {exec_summary}",
                        "path": "execution_log",
                        "execution_results": execution_results,
                    })
                    logger.info(f"Executed {len(execution_results)} actions from pipeline")

        except json.JSONDecodeError:
            logger.debug("No executable actions extracted from strategy")
        except Exception as e:
            logger.warning(f"Execution step failed (non-fatal): {e}")

        if deliverables:
            logger.info(f"Delivered {{len(deliverables)}} items (files + executions) to workspace")

        return deliverables

    # ========== 工具与专家执行 ==========

    async def _exec_tool(self, tool, **kwargs) -> Any:
        """执行工具，带超时"""
        try:
            return await asyncio.wait_for(tool.execute(**kwargs), timeout=30.0)
        except asyncio.TimeoutError:
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)[:200]}

    async def _run_expert(self, expert, context: dict, task: str) -> str:
        """执行单个专家分析"""
        try:
            return await asyncio.wait_for(expert.analyze(context, task), timeout=60.0)
        except asyncio.TimeoutError:
            return f"[{expert.name}] Analysis timed out"
        except Exception as e:
            return f"[{expert.name}] Error: {str(e)[:100]}"

    # ========== 快速回复 ==========

    async def _followup_reply(self, user_message: str) -> str:
        """基于已有研究数据回答追问（不重走搜索）"""
        from app.agent.engine.llm_adapter import TaskTier

        lang = "Chinese" if self._language == "zh" else "English"
        
        # 构建已有数据的摘要
        research_brief = ""
        for r in self.state.research_data[-5:]:
            if r.get("useful"):
                research_brief += f"- {json.dumps(r.get('result', {}), ensure_ascii=False, default=str)[:300]}\n"
        
        expert_brief = ""
        for eid, output in self.state.expert_outputs.items():
            expert_brief += f"- {eid}: {output[:200]}\n"

        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth agent. Respond in {lang}.

The user is following up on a previous analysis. Use the existing data to answer.

Rules:
- Be concise and conversational, like a smart friend
- If they gave a constraint (like "no budget"), adjust advice — don't repeat everything
- No headers, no numbered lists of 10 items
- 2-3 focused paragraphs max

IMPORTANT: You have real tools available:
- Web search (search the internet for competitors, market data)
- Browser (open and analyze competitor websites with screenshots)
- Social search (search Reddit, HN, Twitter for discussions)
- Content writing (draft Reddit posts, tweets, emails)
- Execution (actually post to Reddit, send emails)
If the user asks you to DO something (browse, search, post, write), acknowledge that you CAN do it and describe what you found/did. NEVER say "I cannot use a browser" or "I'm a text-based AI" — you are an AGENT with real tools.""",
            messages=[
                {"role": "user", "content": f"Previous research data:\n{research_brief[:1500]}\n\nPrevious expert analysis:\n{expert_brief[:1500]}"},
                {"role": "assistant", "content": "I have the context from our previous analysis."},
            ] + self.state.message_history[-4:],
            tier=TaskTier.THINKING,
            max_tokens=1500,
        )
        return response.content

    async def _tool_followup(self, user_message: str) -> str:
        """用户在追问中要求执行动作（浏览器、搜索、发帖等）→ 调用工具"""
        from app.agent.engine.llm_adapter import TaskTier
        import asyncio

        lang = "Chinese" if self._language == "zh" else "English"
        msg_lower = user_message.lower()

        # 检测具体要做什么
        browse_triggers = ["browser", "浏览器", "browse", "打开", "访问", "看看竞品", "看一下"]
        search_triggers = ["搜索", "search", "找", "查"]
        product_info = self.state.product_info

        result_text = ""

        # 1. 浏览器请求：找一个竞品网站并真正打开
        if any(t in msg_lower for t in browse_triggers):
            # 从已有研究数据中提取竞品 URL
            competitor_url = None
            competitor_name = None

            # 先从产品信息中的竞品列表找
            competitors = product_info.get("competitors", [])
            if competitors and isinstance(competitors, list):
                comp = competitors[0]
                if isinstance(comp, dict):
                    competitor_name = comp.get("name", "")
                    # 搜索竞品 URL
                    search_tool = self.tools.get("web_search")
                    if search_tool and competitor_name:
                        try:
                            sr = await asyncio.wait_for(
                                search_tool.execute(query=f"{competitor_name} official website"),
                                timeout=15.0
                            )
                            if isinstance(sr, dict):
                                for r in sr.get("results", []):
                                    url = r.get("url", "")
                                    if url and "google" not in url and "bing" not in url:
                                        competitor_url = url
                                        break
                        except Exception:
                            pass

            # 如果找到了 URL，用浏览器打开
            if competitor_url:
                browse_tool = self.tools.get("browse_website")
                scrape_tool = self.tools.get("scrape_website")
                tool = browse_tool or scrape_tool

                if tool:
                    try:
                        browse_result = await asyncio.wait_for(
                            tool.execute(url=competitor_url),
                            timeout=30.0
                        )
                        if isinstance(browse_result, dict):
                            title = browse_result.get("title", "")
                            text = browse_result.get("text", browse_result.get("content", ""))[:1500]
                            result_text = f"I browsed {competitor_name} ({competitor_url}):\n\nTitle: {title}\nContent preview:\n{text}"
                        else:
                            result_text = f"Browsed {competitor_url} but got limited data."
                    except Exception as e:
                        result_text = f"Tried to browse {competitor_url} but encountered an error: {str(e)[:100]}"
                else:
                    result_text = f"Found competitor {competitor_name} but browser tool is not available in this environment."
            else:
                # 没有竞品信息，搜索一下
                search_tool = self.tools.get("web_search")
                desc = product_info.get("description", product_info.get("raw_description", ""))
                if search_tool and desc:
                    try:
                        sr = await asyncio.wait_for(
                            search_tool.execute(query=f"{desc[:80]} competitors"),
                            timeout=15.0
                        )
                        if isinstance(sr, dict):
                            results = sr.get("results", [])[:3]
                            result_text = "Searched for competitors:\n" + "\n".join(
                                f"- {r.get('title', '')}: {r.get('url', '')} — {r.get('content', '')[:100]}"
                                for r in results
                            )
                    except Exception:
                        result_text = "Search failed, please try again."

        # 2. 搜索请求
        elif any(t in msg_lower for t in search_triggers):
            search_tool = self.tools.get("web_search")
            if search_tool:
                try:
                    sr = await asyncio.wait_for(
                        search_tool.execute(query=user_message[:120]),
                        timeout=15.0
                    )
                    if isinstance(sr, dict):
                        results = sr.get("results", [])[:5]
                        result_text = "Search results:\n" + "\n".join(
                            f"- {r.get('title', '')}: {r.get('url', '')}\n  {r.get('content', '')[:150]}"
                            for r in results
                        )
                except Exception as e:
                    result_text = f"Search failed: {str(e)[:100]}"

        # 用 LLM 基于工具结果生成自然回复
        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth agent. Respond in {lang}.
You just executed a tool action based on the user's request. Present the results naturally.
If you browsed a competitor's website, analyze what you found: their positioning, pricing, features, and what the user can learn from it.
If you searched, highlight the most relevant findings.
Be specific and data-driven. 2-4 paragraphs.""",
            messages=self.state.message_history[-6:] + [
                {{"role": "user", "content": f"Tool execution result:\n{result_text}\n\nUser's original request: {user_message}"}}
            ],
            tier=TaskTier.THINKING,
            max_tokens=1500,
        )
        return response.content

    async def _quick_reply(self, user_message: str, instruction: str) -> str:
        """LLM 简短回复（不调工具，不调专家，但带完整上下文）"""
        from app.agent.engine.llm_adapter import TaskTier

        lang = "Chinese" if self._language == "zh" else "English"
        
        # 构建产品上下文（如果有的话）
        product_ctx = ""
        if self.state.product_info:
            product_ctx = f"\nYou already know about the user's product: {json.dumps(self.state.product_info, ensure_ascii=False, default=str)[:300]}"

        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth strategy agent. You are ALSO a product yourself — a SaaS tool that helps indie developers grow their products.

Key facts about yourself:
- You are CrabRes, built to research markets, analyze competitors, and create actionable growth plans
- You have 13 AI expert advisors (market researcher, content strategist, social media expert, etc.)
- You can browse the web, search Reddit/Twitter, and execute growth actions
- You are a product that needs growth too — you understand the struggle firsthand

Respond in {lang}. {instruction}{product_ctx}""",
            messages=self.state.message_history[-10:],
            tier=TaskTier.THINKING,  # 用更好的模型，保证对话质量
            max_tokens=300,
        )
        return response.content

    # ========== 检测器 ==========

    def _is_greeting(self, msg: str) -> bool:
        """精确匹配纯打招呼（0 token）"""
        greetings = ["hi", "hey", "hello", "sup", "yo", "嗨", "你好", "哈喽", "在吗", "hi!", "hello!", "hey!"]
        return msg.strip().rstrip("!！.。，,") in greetings

    def _has_product_signals(self, msg: str) -> bool:
        """检测消息是否包含产品信息（纯代码，0 token）"""
        if len(msg) < 15:
            return False
        signals = [
            "my product", "i built", "i made", "i'm building", "we built",
            "it's a", "it is a", "helps", "for users", "for developers",
            "saas", "app", "tool", "platform", "$", "/mo", "pricing",
            "users", "customers", "growth", "marketing", "launch",
            "我的产品", "我做了", "我在做", "帮助", "用户", "增长",
            "crabres", "ai growth", "http", ".com", ".io", ".app",
        ]
        return any(s in msg for s in signals)

    async def _classify_intent(self, msg: str) -> str:
        """用 LLM 对短消息进行意图分类（代替硬编码规则）"""
        from app.agent.engine.llm_adapter import TaskTier

        # 先用关键词快速过滤明显的自我认知问题
        self_triggers = [
            "what are you", "who are you", "what do you do", "introduce yourself",
            "你是什么", "你是谁", "你做什么", "介绍一下",
            "你自己", "你本身", "你是一个产品", "你是产品", "crabres是",
            "about yourself", "about you", "tell me about crabres",
        ]
        if any(t in msg.lower() for t in self_triggers):
            return "self_awareness"

        # 构建对话历史摘要给 LLM 做判断
        recent_history = ""
        for m in self.state.message_history[-6:]:
            role = "User" if m["role"] == "user" else "CrabRes"
            recent_history += f"{role}: {m['content'][:100]}\n"

        response = await self.llm.generate(
            system_prompt="""Classify the user's intent into exactly ONE of these categories:
- self_awareness: User is asking about CrabRes itself (what it is, its capabilities, asking it to do something for itself)
- greeting: Pure greeting with no substance
- product: User is describing a product, giving product context, OR asking for growth/marketing/strategy help
- followup: User is providing additional info that continues the conversation (answering a question, adding constraints, giving instructions like "制定计划"/"执行"/"开始")
- chitchat: General chat, casual remarks, or anything unrelated to product growth

CRITICAL RULES:
- If the user mentions a PRODUCT NAME (even just "crabres") → "self_awareness" or "product", NOT "chitchat"
- If the user is giving INSTRUCTIONS or TASKS (like "制定增长计划", "帮我分析", "开始执行") → "followup" or "product", NOT "chitchat"
- If CrabRes just asked a question and the user is responding with any info → "followup"
- "chitchat" is ONLY for truly unrelated messages (like "天气怎么样", "你好吗", random remarks)
- If the message contains growth/strategy/marketing keywords → NEVER classify as "chitchat"
- When in doubt, prefer "followup" over "chitchat" — it's better to act than to idle

Reply with ONLY the category name, nothing else.""",
            messages=[{
                "role": "user",
                "content": f"Conversation so far:\n{recent_history}\nLatest message: {msg}\n\nClassify the intent:"
            }],
            tier=TaskTier.PARSING,
            max_tokens=20,
        )
        intent = response.content.strip().lower().replace('"', '').replace("'", "")
        # 容错：如果 LLM 返回了意外内容，默认当 followup 处理（进流水线）
        valid = {"self_awareness", "greeting", "product", "followup", "chitchat"}
        return intent if intent in valid else "followup"

    async def _self_aware_reply(self, msg: str) -> str:
        """回答关于 CrabRes 自身的问题（带上下文的 LLM 回复）"""
        from app.agent.engine.llm_adapter import TaskTier

        lang = "Chinese" if self._language == "zh" else "English"
        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth strategy agent AND a product yourself. Respond in {lang}.

About yourself:
- You are a SaaS product (crab-researcher.vercel.app) that helps indie developers and small teams grow their products
- You have 13 AI expert advisors covering market research, content strategy, social media, paid ads, partnerships, etc.
- You can browse the web, search social media, analyze competitors, and execute growth actions (post to Reddit, send emails, etc.)
- You were built by an indie developer — you understand the struggle of building and growing a product from zero
- You ARE a product that needs growth strategies too. If someone asks you to create a growth plan for yourself, DO IT — analyze your own market, competitors (like GrowthBook, Jasper, Copy.ai), and suggest real strategies.

Answer the user's question about yourself naturally and honestly. If they're asking you to do something for yourself (like create your own growth strategy), engage with it enthusiastically — you're both the tool and the subject.""",
            messages=self.state.message_history[-8:],
            tier=TaskTier.THINKING,
            max_tokens=500,
        )
        return response.content

    async def _backup_file_to_memory(self, rel_path: str, content: str):
        """备份 workspace 文件到 memory（部署重建后可恢复）"""
        try:
            backup_key = f"workspace_file_{rel_path.replace('/', '_')}"
            await self.memory.save(backup_key, {
                "rel_path": rel_path,
                "content": content,
                "backed_up_at": __import__('time').time(),
            }, category="workspace_backup")
        except Exception as e:
            logger.debug(f"Failed to backup workspace file: {e}")

    # ========== 持久化 ==========

    async def _persist(self):
        """保存状态 + 记录评估指标"""
        checkpoint = {
            "session_id": self.state.session_id,
            "turn_count": self.state.turn_count,
            "product_info": self.state.product_info,
            "expert_outputs": {k: v[:2000] for k, v in self.state.expert_outputs.items()},
            "message_history": self.state.message_history[-50:],
            "created_at": self.state.created_at,
        }
        await self.memory.save(f"pipeline_state_{self.state.session_id}", checkpoint)

        # 🔥 记录评估指标
        try:
            from app.agent.eval import get_collector
            collector = get_collector()
            
            total_research = len(self.state.research_data)
            useful_research = len([r for r in self.state.research_data if r.get("useful")])
            total_experts = len(self.state.expert_outputs)
            valid_experts = len([v for v in self.state.expert_outputs.values() 
                               if isinstance(v, str) and not v.startswith("[")])
            
            collector.record_session(self.state.session_id, {
                "turn_count": self.state.turn_count,
                "tcr": 1 if any(m["role"] == "assistant" for m in self.state.message_history) else 0,
                "rdr": round(useful_research / max(total_research, 1), 2),
                "ear": round(valid_experts / max(total_experts, 1), 2),
                "tpt": self.llm.usage.total_tokens,
                "cpt": self.llm.usage.total_cost_usd,
                "ttc": round(time.time() - self.state.created_at, 1),
                "dgr": 1 if hasattr(self, '_last_deliverables_count') and self._last_deliverables_count > 0 else 0,
                "pgr": 1 if hasattr(self, '_last_playbook_generated') and self._last_playbook_generated else 0,
                "experts_activated": list(self.state.expert_outputs.keys()),
                "language": self._language,
            })
        except Exception as e:
            logger.debug(f"Eval metrics recording failed: {e}")

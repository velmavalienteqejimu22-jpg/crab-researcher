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

        # 1. 自我认知——硬编码，0 token
        if self._is_self_awareness_question(msg_lower):
            reply = self._self_awareness_reply()
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            return

        # 2. 纯打招呼——LLM 简短回复，不调工具
        if self._is_greeting(msg_lower):
            reply = await self._quick_reply(msg, "The user is greeting you. Reply warmly in 1-2 sentences and ask what they're building.")
            yield {"type": "message", "content": reply}
            self.state.message_history.append({"role": "assistant", "content": reply})
            return

        # 3. 简短追问/闲聊——LLM 直接回答
        if len(msg) < 50 and not self._has_product_signals(msg_lower):
            # 先检查是否已有产品信息
            if self.state.product_info:
                # 有产品信息的追问 → 可能需要进流水线
                pass
            else:
                # 没产品信息的短消息 → 引导
                self.state.ask_count += 1
                if self.state.ask_count <= 1:
                    reply = await self._quick_reply(msg, "The user said something short without product info. Ask ONE friendly question about what they're building. Keep it to 1-2 sentences.")
                    yield {"type": "message", "content": reply}
                    self.state.message_history.append({"role": "assistant", "content": reply})
                    return
                else:
                    # 问过了还没给产品信息 → 给兜底
                    reply = self._fallback_reply()
                    yield {"type": "message", "content": reply}
                    self.state.message_history.append({"role": "assistant", "content": reply})
                    return

        # ========== 流水线路径 ==========
        self.state.ask_count = 0

        # 🔥 追问检测：如果上一轮已经搜过+有专家输出，新消息是追问/补充信息
        # → 不重走搜索，直接基于已有数据回答
        has_prior_research = len(self.state.research_data) > 0
        has_prior_experts = len(self.state.expert_outputs) > 0
        is_followup = has_prior_research and len(msg) < 200

        if is_followup and (has_prior_research or has_prior_experts):
            # 追问路径：用已有数据 + 新信息直接回答
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

    async def _step_understand(self, user_message: str) -> dict:
        """Step 1: 从用户消息提取产品信息"""
        from app.agent.engine.llm_adapter import TaskTier

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

        task = (
            f"Analyze this product and create a growth strategy.\n\n"
            f"Product: {json.dumps(product_info, ensure_ascii=False, default=str)[:800]}\n\n"
            f"Research data:\n{research_summary}"
        )

        context = {
            "product": product_info,
            "tool_results": useful_results,
            "user_message": product_info.get("raw_description", ""),
            "expert_outputs": {},
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

        response = await self.llm.generate(
            system_prompt=f"""You are CrabRes, an AI growth agent. Respond ONLY in {lang}.

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

{getattr(self, '_mood_injection', '')}""",
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

        workspace = Path(str(self.memory.base_dir)).parent / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        for sub in ["drafts", "reports", "plans"]:
            (workspace / sub).mkdir(exist_ok=True)

        deliverables = []
        lang = "Chinese" if self._language == "zh" else "English"
        product_name = product_info.get("name", "product")
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
                path.write_text(f"# Competitor Analysis: {product_name}\n\n{report.content}", encoding="utf-8")
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
            path.write_text(f"# Content Drafts: {product_name}\n\n{draft.content}", encoding="utf-8")
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
            path.write_text(f"# 30-Day Growth Plan: {product_name}\n\n{plan.content}", encoding="utf-8")
            deliverables.append({"name": "30-Day Growth Plan", "desc": f"plans/{path.name}", "path": str(path)})
        except Exception as e:
            logger.warning(f"Failed to generate growth plan: {e}")

        if deliverables:
            logger.info(f"Delivered {len(deliverables)} files to workspace")

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
- 2-3 focused paragraphs max""",
            messages=[
                {"role": "user", "content": f"Previous research data:\n{research_brief[:1500]}\n\nPrevious expert analysis:\n{expert_brief[:1500]}"},
                {"role": "assistant", "content": "I have the context from our previous analysis."},
            ] + self.state.message_history[-4:],
            tier=TaskTier.THINKING,
            max_tokens=1500,
        )
        return response.content

    async def _quick_reply(self, user_message: str, instruction: str) -> str:
        """LLM 简短回复（不调工具，不调专家）"""
        from app.agent.engine.llm_adapter import TaskTier

        lang = "Chinese" if self._language == "zh" else "English"
        response = await self.llm.generate(
            system_prompt=f"You are CrabRes, an AI growth agent that helps developers grow their products. Respond in {lang}. {instruction}",
            messages=self.state.message_history[-6:],
            tier=TaskTier.PARSING,  # 最便宜的 tier
            max_tokens=200,
        )
        return response.content

    # ========== 检测器（纯代码，0 token）==========

    def _is_self_awareness_question(self, msg: str) -> bool:
        triggers = ["what are you", "who are you", "what do you do",
                     "introduce yourself", "你是什么", "你是谁", "你做什么", "介绍一下"]
        return any(t in msg for t in triggers)

    def _self_awareness_reply(self) -> str:
        if self._language == "zh":
            return "我是 CrabRes，一个 AI 增长策略 Agent。我帮开发者和小团队研究市场、分析竞品、制定可执行的增长计划。告诉我你在做什么产品，我就开始工作。"
        return "I'm CrabRes — an AI growth agent. I research your market, analyze competitors, and create actionable growth plans for indie developers and small teams. Tell me what you're building and I'll get to work."

    def _is_greeting(self, msg: str) -> bool:
        greetings = ["hi", "hey", "hello", "sup", "yo", "嗨", "你好", "哈喽", "在吗"]
        return msg.strip().rstrip("!！.。") in greetings

    def _has_product_signals(self, msg: str) -> bool:
        """检测消息是否包含产品信息（纯代码，0 token）"""
        if len(msg) < 20:
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

    def _fallback_reply(self) -> str:
        if self._language == "zh":
            return "我需要知道你在做什么才能帮你。给我一句话就行——比如 'AI 简历优化工具，$9.99/月'，我就能立刻开始研究。"
        return "I need to know what you're building to help. Just a one-liner works — like 'AI resume optimizer at $9.99/mo' — and I'll start researching immediately."

    # ========== 持久化 ==========

    async def _persist(self):
        """保存状态"""
        checkpoint = {
            "session_id": self.state.session_id,
            "turn_count": self.state.turn_count,
            "product_info": self.state.product_info,
            "expert_outputs": {k: v[:2000] for k, v in self.state.expert_outputs.items()},
            "message_history": self.state.message_history[-50:],
            "created_at": self.state.created_at,
        }
        await self.memory.save(f"pipeline_state_{self.state.session_id}", checkpoint)

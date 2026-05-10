"""
CrabRes Agent Engine — 统一图编排器 (GraphBuilder)

替代 loop.py / pipeline.py / orchestrator.py 三套引擎的统一入口。
基于 Router 决定执行模式，复用共享节点，实现 Pipeline + ReAct 混合架构。

架构：
  UserMessage → Router → [Pipeline Mode | ReAct Mode | Quick Mode]
                              ↓
                    共享节点池
                        ├── node_understand()
                        ├── node_research()
                        ├── node_expert()
                        └── node_deliver()

使用方式（向后兼容）：
  - 新代码: GraphBuilder(session_id, llm, tools, experts, memory).run(message)
  - 旧代码: AgentLoop / PipelineRunner 保持可用，内部委托给 GraphBuilder
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncIterator

from app.agent.engine.state import AgentState, ExecutionMode, Phase
from app.agent.engine.errors import (
    CrabResError, ToolError, ExpertError, StageError,
)
from app.agent.engine.router import route, maybe_refine_route, RouteDecision
from app.agent.engine.nodes import (
    NodeDeps,
    node_understand,
    node_research,
    node_expert,
    node_deliver,
)

logger = logging.getLogger(__name__)


class GraphBuilder:
    """
    统一图编排器 — CrabRes Agent 的唯一执行入口。
    
    合并了:
      - AgentLoop (loop.py) 的 ReAct 循环能力
      - PipelineRunner (pipeline.py) 的确定性流水线
      - Orchestrator (orchestrator.py) 的阶段控制
    
    关键设计原则：
      1. Router 零 token 决定模式
      2. 共享节点消除代码重复
      3. 异常分类处理（不再静默吞异常）
      4. 向后兼容：AgentLoop.run() 内部委托到此类的 run()
    """
    
    # ===== 阶段配置（从 orchestrator 迁移）=====
    MAX_RESEARCH_TOOL_CALLS = 4
    MAX_RESEARCH_TIME_SEC = 45
    MAX_EXPERTS = 4
    
    def __init__(self, session_id: str, llm_service, tool_registry, expert_pool, memory):
        self.state = AgentState(session_id=session_id)
        self.llm = llm_service
        self.tools = tool_registry
        self.experts = expert_pool
        self.memory = memory
        
        # 构建依赖注入容器
        self.deps = NodeDeps(
            llm=llm_service,
            tools=tool_registry,
            experts=expert_pool,
            memory=memory,
        )
        
        # 可选服务（延迟导入避免循环依赖）
        self._trust = None
        self._mood_sensor = None
        self._deep_strategy = None
        self._prompt_cache = None
        
        # Workspace 初始化
        from pathlib import Path
        workspace_base = Path(str(memory.base_dir)).parent / "workspace"
        for subdir in ["drafts", "assets", "outreach", "reports", "experiments"]:
            (workspace_base / subdir).mkdir(parents=True, exist_ok=True)
        self.workspace = workspace_base

    async def run(self, user_message: str, language: str = "en") -> AsyncIterator[dict]:
        """
        主入口：处理用户消息，yield 流式事件。
        
        这是唯一需要调用的方法。内部自动处理：
          1. 路由决策（Quick/Pipeline/ReAct）
          2. 模式执行
          3. 状态持久化
          4. 事件转发
        """
        self.state.language = language
        self.state.turn_count += 1
        self.state.last_active_at = time.time()
        
        # 加载历史状态
        if not self.state.message_history:
            await self._load_state()
        
        # 写前日志
        await self._write_ahead_log(user_message)
        
        # 自动提取产品信息
        await self._maybe_save_product_info(user_message)
        
        # 自动追踪社媒链接
        await self._maybe_track_posted_url(user_message)
        
        self.state.add_message("user", user_message)
        
        # ===== 路由决策 =====
        decision = route(user_message, self.state)
        # 低置信度时用 LLM 兜底分类（只对短消息且没有强规则命中的情况触发）
        decision = await maybe_refine_route(decision, user_message, self.llm)
        logger.info(f"Route decision: {decision.mode.value} ({decision.reason}, conf={decision.confidence:.2f})")
        
        try:
            # --- Quick 模式 ---
            if decision.mode == ExecutionMode.QUICK:
                async for event in self._run_quick(user_message, decision):
                    yield event
            
            # --- Pipeline 模式（默认）---
            elif decision.mode == ExecutionMode.PIPELINE:
                async for event in self._run_pipeline(user_message):
                    yield event
            
            # --- ReAct 模式（高信任用户）---
            elif decision.mode == ExecutionMode.REACT:
                async for event in self._run_react(user_message):
                    yield event
        
        except CrabResError as e:
            logger.error(f"Agent error [{type(e).__name__}]: {e}", exc_info=True)
            if e.user_message:
                yield {"type": "error", "content": e.user_message}
            else:
                yield {
                    "type": "message",
                    "content": f"Sorry, I ran into an issue: {str(e)[:200]}. Let me try a different approach.",
                }
        except Exception as e:
            logger.exception(f"Unexpected agent error: {e}")
            yield {
                "type": "message",
                "content": "Something went wrong on my end. Could you rephrase that? I'll try again.",
            }
        
        # 持久化状态
        await self._persist_state()

    async def _run_quick(self, user_message: str, decision: RouteDecision) -> AsyncIterator[dict]:
        """快速路径：打招呼、闲聊、自我介绍、专家私聊、Deep Strategy"""
        msg = user_message.strip()
        msg_lower = msg.lower()
        lang = self.state.language
        
        # 专家私聊
        if decision.reason == "expert_chat" and decision.expert_id:
            expert = self.experts.get(decision.expert_id)
            if expert:
                yield {"type": "status", "content": f"Connecting you directly with {expert.name}..."}
                yield {"type": "expert_thinking", "expert_id": decision.expert_id, "content": f"{expert.name} is analyzing..."}
                try:
                    context = await self._build_context("")
                    output = await expert.analyze(context, decision.expert_task)
                    self.state.add_message("assistant", f"[Expert: {decision.expert_id}] {output[:1500]}")
                    self.state.expert_outputs[decision.expert_id] = output
                    yield {"type": "expert_thinking", "expert_id": decision.expert_id, "content": output}
                    yield {"type": "message", "content": f"**{expert.name}** (@{decision.expert_id}):\n\n{output}"}
                except Exception as e:
                    yield {"type": "error", "content": f"Expert {decision.expert_id} error: {str(e)[:200]}"}
                return
        
        # Deep Strategy 后台任务
        if decision.reason == "deep_strategy_background":
            try:
                from app.agent.engine.deep_strategy import get_deep_strategy_engine
                ds = get_deep_strategy_engine()
                job = await ds.create_job(
                    user_id=str(self.memory.base_dir).split("/")[-1],
                    session_id=self.state.session_id,
                    request=msg,
                    llm_service=self.llm,
                    tool_registry=self.tools,
                    expert_pool=self.experts,
                    memory=self.memory,
                )
                yield {
                    "type": "message",
                    "content": (
                        f"\U0001f52c **Deep Strategy Session launched** (ID: `{job.id}`)\n\n"
                        f"This complex request requires thorough research. "
                        f"I'm running a full expert roundtable in the background.\n\n"
                        f"This will take 2-5 minutes. I'll notify you when it's ready."
                    ),
                }
                self.state.add_message("assistant", f"[Deep Strategy launched: {job.id}]")
            except Exception as e:
                logger.error(f"Deep Strategy failed: {e}")
                yield {"type": "status", "content": "Deep strategy unavailable."}
            return
        
        # 自我认知
        if decision.reason == "self_awareness":
            reply = await self._quick_llm_reply(
                msg,
                f"You are CrabRes, an AI growth strategy agent AND a product yourself. Respond in {'Chinese' if lang == 'zh' else 'English'}."
                f"About yourself: SaaS product for indie developers with 13 AI experts, web research, and execution capabilities."
                f"Answer naturally. 2-3 sentences max.",
            )
            yield {"type": "message", "content": reply}
            self.state.add_message("assistant", reply)
            return
        
        # 打招呼
        if decision.reason == "greeting":
            reply = await self._quick_llm_reply(
                msg,
                f"You are CrabRes, AI growth agent. Greet warmly in {'Chinese' if lang == 'zh' else 'English'}. 1-2 sentences. Ask what they're building.",
            )
            yield {"type": "message", "content": reply}
            self.state.add_message("assistant", reply)
            return

    async def _run_pipeline(self, user_message: str) -> AsyncIterator[dict]:
        """
        Pipeline 模式：确定性阶段流水线。

        UNDERSTAND → RESEARCH → EXPERT → DELIVER
        每个阶段有明确的入口/退出条件。

        Guardrail: 总步骤数硬上限 (max_pipeline_steps)，防止异常路径无限循环。
        """
        # 重置步数计数（每次请求独立预算）
        self.state.pipeline_step_count = 0

        def _check_budget(stage: str) -> bool:
            """检查步数预算。超额返回 False 让调用方退出。"""
            self.state.pipeline_step_count += 1
            if self.state.pipeline_step_count > self.state.max_pipeline_steps:
                logger.error(
                    f"Pipeline step budget exceeded at {stage}: "
                    f"{self.state.pipeline_step_count}/{self.state.max_pipeline_steps}"
                )
                return False
            return True

        # Step 1: UNDERSTAND
        if not _check_budget("understand"):
            yield {"type": "error", "content": "Request too complex, aborted to prevent runaway."}
            return
        state = await node_understand(self.state, self.deps, user_message)
        
        # 快速路径检测
        if state.intent == "greeting":
            reply = await self._quick_llm_reply(user_message, "Greet warmly as CrabRes growth agent. Ask what they're building.")
            yield {"type": "message", "content": reply}
            self.state.add_message("assistant", reply)
            return
        
        if state.intent == "self_awareness":
            reply = await self._quick_llm_reply(user_message, "You ARE CrabRes. Answer about yourself enthusiastically.")
            yield {"type": "message", "content": reply}
            self.state.add_message("assistant", reply)
            return
        
        if state.intent == "chitchat":
            reply = await self._quick_llm_reply(user_message, "Casual friendly reply as CrabRes. Steer toward growth help.")
            yield {"type": "message", "content": reply}
            self.state.add_message("assistant", reply)
            return
        
        if state.direct_reply:
            yield {"type": "message", "content": state.direct_reply}
            return
        
        # 更新 state（node_understand 可能修改了 product_info 等）
        self.state.product_info.update(state.product_info)
        self.state.has_product_info = state.has_product_info
        self.state.intent = state.intent
        self.state.is_self_awareness = state.is_self_awareness
        self.state.target_platforms = state.target_platforms
        
        # 保存产品信息到记忆
        if self.state.product_info:
            existing = await self.memory.load("product") or {}
            existing.update(self.state.product_info)
            await self.memory.save("product", existing)
        
        # Step 2: RESEARCH
        if not _check_budget("research"):
            return
        async for event in node_research(self.state, self.deps):
            yield event

        # Step 3: EXPERT + SYNTHESIZE（合并为一步）
        if not _check_budget("expert"):
            return
        useful_results = [r for r in self.state.search_results if r.get("useful")]
        if len(useful_results) >= 1:
            async for event in node_expert(self.state, self.deps):
                yield event
        else:
            # 数据不足时的轻量回复
            if self.state.search_results:
                light_reply = await self._synthesize_light()
                self.state.synthesis = light_reply
                yield {"type": "message", "content": light_reply}
                self.state.add_message("assistant", light_reply)

        # Step 4: DELIVER
        if not _check_budget("deliver"):
            return
        async for event in node_deliver(self.state, self.deps):
            yield event

    async def _run_react(self, user_message: str) -> AsyncIterator[dict]:
        """
        ReAct 模式：LLM 自主决策循环（带守卫的有限循环）。
        
        think → act → observe 循环，但有以下安全限制：
        - 最大迭代次数: max_loop_iterations (默认 10)
        - Token 预算: token_budget
        - 连续错误阈值: max_consecutive_errors (默认 3)
        - 强制退出条件: 连续无新信息产出
        
        与纯 ReAct 的区别：
        - 使用 Function Calling（tool_choice）而非自由文本解析
        - 共享 Pipeline 的节点作为 fallback
        - Trust Level 控制自主权范围
        """
        max_iterations = self.state.max_loop_iterations
        iteration = 0
        consecutive_no_new_info = 0
        last_output_hash = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"ReAct iteration {iteration}/{max_iterations}")
            
            # 1. THINK: LLM 决定下一步动作
            try:
                action = await self._react_think(user_message)
            except Exception as e:
                logger.error(f"ReAct think failed (iter {iteration}): {e}")
                self.state.consecutive_errors += 1
                if self.state.consecutive_errors >= 3:
                    # 降级到 Pipeline
                    logger.warning(f"ReAct degraded to Pipeline after {self.state.consecutive_errors} errors")
                    async for evt in self._run_pipeline(user_message):
                        yield evt
                    return
                continue
            
            # 2. ACT: 执行动作
            if action.type == "output":
                # LLM 决定输出 → 结束循环
                content = action.content
                self.state.add_message("assistant", content)
                
                # 保存策略到记忆
                if len(content) > 200:
                    await self._save_output_to_memory(content)
                
                yield {"type": "message", "content": content}
                
                # 如果有足够的研究数据，触发专家圆桌和交付物
                if self.state.search_results and not self.state.expert_outputs:
                    async for evt in node_expert(self.state, self.deps):
                        yield evt
                    async for evt in node_deliver(self.state, self.deps):
                        yield evt
                break
            
            elif action.type == "tool_call":
                # 工具调用
                result = await self._react_execute_tool(action)
                self.state.tool_call_count += 1
                
                # 检查是否有新信息
                result_str = json.dumps(result, default=str)[:200] if isinstance(result, dict) else str(result)[:200]
                if result_str == last_output_hash:
                    consecutive_no_new_info += 1
                else:
                    consecutive_no_new_info = 0
                    last_output_hash = result_str
                
                if consecutive_no_new_info >= 3:
                    logger.info(f"ReAct: no new info after 3 iterations, synthesizing")
                    synthesis = await self._synthesize_light()
                    self.state.synthesis = synthesis
                    yield {"type": "message", "content": synthesis}
                    break
            
            elif action.type == "roundtable":
                # 圆桌专家
                async for evt in node_expert(self.state, self.deps):
                    yield evt
                break
            
            elif action.type == "ask_user":
                # 向用户提问
                yield {"type": "message", "content": action.content}
                self.state.is_waiting_for_user = True
                break
            
            elif action.type == "think":
                # 内部思考，继续循环
                continue
            
            else:
                # 未知动作类型 → 当作输出
                yield {"type": "message", "content": action.content or "I've processed your request."}
                break
        
        if iteration >= max_iterations:
            logger.info(f"ReAct reached max iterations ({max_iterations}), falling back to pipeline")
            async for evt in self._run_pipeline(user_message):
                yield evt

    # ===== ReAct 专用方法 =====

    async def _react_think(self, user_message: str):
        """ReAct 思考步骤：让 LLM 决定下一步动作"""
        from app.agent.engine.llm_adapter import TaskTier
        
        context = await self._build_context(user_message)
        coordinator_prompt = self._build_coordinator_prompt(context)
        
        response = await self.llm.generate(
            system_prompt=coordinator_prompt,
            messages=context.get("messages", []),
            tier=TaskTier.CRITICAL,
            tools=self._get_available_actions(),
        )
        
        self.state.total_tokens_used = self.llm.usage.total_tokens
        return self._parse_decision(response)

    async def _react_execute_tool(self, action):
        """ReAct 工具执行：带重试和超时"""
        tool = self.tools.get(action.tool_name)
        if not tool:
            raise ToolError(action.tool_name, "not found")
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = await asyncio.wait_for(
                    tool.execute(**(action.tool_args or {})),
                    timeout=60.0,
                )
                if isinstance(result, dict) and result.get("error"):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                return result
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {"error": f"{action.tool_name} timed out"}
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return {"error": str(e)[:200]}
        return {"error": "max retries exceeded"}

    def _parse_decision(self, response):
        """解析 LLM 输出为结构化动作（复用 loop.py 的逻辑）"""
        from app.agent.engine.llm_adapter import LLMResponse
        from app.agent.engine.loop import ActionType, AgentAction
        
        if not isinstance(response, LLMResponse):
            from dataclasses import dataclass
            @dataclass
            class FakeAction:
                type: str; content: str
            return FakeAction("output", str(response))
        
        if response.tool_calls:
            tc = response.tool_calls[0]
            name = tc.get("name", "")
            args = tc.get("args", {})
            
            direct_tool_names = [
                "web_search", "social_search", "scrape_website", "competitor_analyze",
                "deep_scrape", "browse_website", "write_post", "publish_post",
                "twitter_read", "write_email", "consult_expert", "consult_roundtable",
                "save_competitors", "set_active_campaign", "ask_user", "output",
            ]
            
            if name in direct_tool_names:
                return AgentAction(type=name if name in ("output", "ask_user") else "tool_call", content=f"Using {name}", tool_name=name, tool_args=args)
        
        if response.content:
            return AgentAction(type="output", content=response.content)
        
        return AgentAction(type="output", content="")

    # ===== 辅助方法（从 loop.py 迁移）=====

    async def _build_context(self, user_message: str) -> dict:
        """构建上下文（复用 loop.py._build_context）"""
        product = await self.memory.load("product")
        competitors = await self.memory.load("competitors")
        strategy = await self.memory.load("strategy")
        results = await self.memory.load("results")
        
        if user_message:
            self.state.add_message("user", user_message)
        
        context_parts = []
        if product:
            context_parts.append(f"[Product]: {json.dumps(product, ensure_ascii=False, default=str)[:500]}")
        if competitors:
            context_parts.append(f"[Competitors]: {json.dumps(competitors, ensure_ascii=False, default=str)[:500]}")
        if strategy:
            context_parts.append(f"[Strategy]: {json.dumps(strategy, ensure_ascii=False, default=str)[:500]}")
        if results:
            context_parts.append(f"[Results]: {json.dumps(results, ensure_ascii=False, default=str)[:300]}")
        
        messages = []
        if context_parts:
            messages.append({"role": "user", "content": "[SYSTEM CONTEXT]\n" + "\n".join(context_parts)})
            messages.append({"role": "assistant", "content": "Understood."})
        
        messages.extend(self.state.recent_messages(12))
        
        return {
            "user_message": user_message,
            "product": product or {},
            "messages": messages,
            "phase": self.state.phase.value,
        }

    async def _quick_llm_reply(self, user_msg: str, system_instruction: str) -> str:
        """快速 LLM 回复（用于 quick 路径）"""
        from app.agent.engine.llm_adapter import TaskTier
        lang = "Chinese" if self.state.language == "zh" else "English"
        
        response = await self.llm.generate(
            system_prompt=system_instruction,
            messages=self.state.recent_messages(10),
            tier=TaskTier.THINKING,
            max_tokens=300,
        )
        return response.content

    async def _synthesize_light(self) -> str:
        """轻量综合（数据不足时使用）"""
        from app.agent.engine.llm_adapter import TaskTier
        lang = "Chinese" if self.state.language == "zh" else "English"
        
        research_brief = "\n".join(
            f"- {r.get('query','')}: {json.dumps(r.get('result',{}), ensure_ascii=False, default=str)[:300]}"
            for r in self.state.search_results[:3] if r.get("useful")
        )
        
        return await self.llm.generate(
            system_prompt=f"You are CrabRes AI growth agent. Respond in {lang}. Give helpful directional advice based on research data. Be concise 200-400 words.",
            messages=[{"role": "user", "content": f"Research:\n{research_brief[:2000]}\nProduct: {json.dumps(self.state.product_info, ensure_ascii=False, default=str)[:500]}"}],
            tier=TaskTier.THINKING,
            max_tokens=1500,
        ).content

    async def _save_output_to_memory(self, content: str):
        """保存输出到记忆"""
        plan_keywords = ['strategy', 'plan', 'step', 'phase', 'month', 'week', '策略', '计划', '步骤', '阶段']
        is_plan = any(kw in content.lower() for kw in plan_keywords)
        
        if is_plan and len(content) > 200:
            await self.memory.save(f"growth_plan_{self.state.session_id}", {
                "content": content, "turn": self.state.turn_count, "updated_at": time.time(),
            }, category="strategy")

    async def _write_ahead_log(self, user_message: str):
        """写前日志"""
        await self.memory.append_journal({
            "type": "user_message", "content": user_message,
            "session_id": self.state.session_id,
            "turn": self.state.turn_count,
            "timestamp": time.time(),
        })

    async def _maybe_save_product_info(self, user_message: str):
        """自动提取产品信息"""
        product_keywords = ['my product', 'i built', 'i made', "i'm building", 'i have a',
                          "it's a", 'it is a', 'we built', 'our product',
                          '我的产品', '我做了', '我们做了']
        msg_lower = user_message.lower()
        if any(kw in msg_lower for kw in product_keywords) or self.state.turn_count <= 2:
            existing = await self.memory.load("product") or {}
            existing["raw_description"] = user_message
            existing["updated_at"] = time.time()
            urls = re.findall(r'https?://\S+', user_message)
            if urls:
                existing["url"] = urls[0]
            await self.memory.save("product", existing)

    async def _maybe_track_posted_url(self, user_message: str):
        """自动追踪社媒链接"""
        urls = re.findall(r'https?://\S+', user_message)
        if not urls:
            return
        
        try:
            from app.agent.memory.experiments import ExperimentTracker
            tracker = ExperimentTracker(base_dir=str(self.memory.base_dir))
            for url in urls:
                url_lower = url.lower().rstrip('.,;:!?)')
                platform = ""
                if "reddit.com" in url_lower:
                    platform = "reddit"
                elif "x.com" in url_lower or "twitter.com" in url_lower:
                    platform = "x"
                elif "linkedin.com" in url_lower:
                    platform = "linkedin"
                elif "news.ycombinator.com" in url_lower:
                    platform = "hackernews"
                elif "producthunt.com" in url_lower:
                    platform = "producthunt"
                
                if platform:
                    await tracker.record_action(platform=platform, action_type="post", url=url_lower, content_preview=user_message[:200])
        except Exception:
            pass

    async def _persist_state(self):
        """持久化状态检查点"""
        checkpoint = self.state.to_checkpoint()
        await self.memory.save(f"loop_state_{self.state.session_id}", checkpoint)

    async def _load_state(self):
        """从检查点恢复状态"""
        data = await self.memory.load(f"loop_state_{self.state.session_id}")
        if not data:
            return
        
        version = data.get("checkpoint_version", 1)
        self.state.turn_count = data.get("turn_count", 0)
        self.state.total_tokens_used = data.get("tokens_used", 0)
        self.state.token_budget = data.get("token_budget", 100_000)
        self.state.target_platforms = data.get("target_platforms", [])
        
        history = data.get("message_history", [])
        if history:
            for msg in history:
                self.state._message_history.append(msg)
        
        # v2+: 直接恢复专家输出
        if version >= 2:
            eo = data.get("expert_outputs", {})
            if isinstance(eo, dict):
                self.state.expert_outputs = eo

    def _build_coordinator_prompt(self, context: dict) -> str:
        """构建 Coordinator prompt（复用 loop.py 的 prompt，保持行为一致）"""
        # 复用 loop.py 中已有的完整 coordinator prompt
        # 这里引用它以避免重复维护两份 prompt
        from app.agent.engine.loop import AgentLoop
        temp_loop = object.__new__(AgentLoop)
        temp_loop.state = self.state
        temp_loop._language = getattr(self, '_language', 'en')
        return temp_loop._build_coordinator_prompt(context)

    def _get_available_actions(self) -> list[dict]:
        """返回可用的 action schema（复用 loop.py）"""
        from app.agent.engine.loop import AgentLoop
        temp_loop = object.__new__(AgentLoop)
        return temp_loop._get_available_actions(self)

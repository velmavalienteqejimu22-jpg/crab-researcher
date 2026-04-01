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
        self._max_loop_iterations = 8  # 单次用户消息最多循环 8 次
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

        # 写前日志（学 Claude Code）
        await self._write_ahead_log(user_message)

        # 加载记忆上下文
        context = await self._build_context(user_message)

        iteration = 0
        while self._running and iteration < self._max_loop_iterations:
            iteration += 1
            try:
                # 1. THINK: 让 Coordinator（首席增长官）决定下一步
                decision = await self._think(context)

                if decision.type == ActionType.OUTPUT:
                    # 最终输出给用户
                    self._message_history.append({"role": "assistant", "content": decision.content})
                    yield {"type": "message", "content": decision.content}
                    break

                elif decision.type == ActionType.ASK_USER:
                    # 需要用户提供信息
                    self._message_history.append({"role": "assistant", "content": decision.content})
                    yield {"type": "question", "content": decision.content}
                    self.state.is_waiting_for_user = True
                    break

                elif decision.type == ActionType.TOOL_CALL:
                    # 2. ACT: 执行工具
                    yield {"type": "status", "content": f"正在{decision.content}..."}
                    result = await self._execute_tool(decision)
                    # 3. OBSERVE: 将结果加入上下文
                    context = self._incorporate_result(context, decision, result)

                elif decision.type == ActionType.EXPERT:
                    # 调度专家
                    yield {"type": "status", "content": f"咨询{decision.content}..."}
                    expert_output = await self._consult_expert(decision, context)
                    context = self._incorporate_expert(context, decision, expert_output)
                    # 可选：让用户看到专家思考过程
                    yield {
                        "type": "expert_thinking",
                        "expert_id": decision.expert_id,
                        "content": expert_output,
                    }

                elif decision.type == ActionType.THINK:
                    # 内部推理，不输出给用户
                    context = self._incorporate_thinking(context, decision)

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

        return f"""你是 CrabRes 的首席增长官（Chief Growth Officer）。

你管理一个由 12 位增长专家组成的团队，帮助用户的产品找到增长之路。

## 你的核心原则

1. **绝不给出套路化建议**
   - 禁止默认推荐"做 Reddit + SEO + 社媒"这种万能公式
   - 每个产品的增长路径都是独特的
   - 有些产品适合地推，有些适合冷邮件，有些适合 AI 分发
   - 你必须基于研究结果来判断，而不是基于"常见做法"

2. **先验证再行动**
   - 在推荐任何增长策略之前，先判断产品方向是否可行
   - 如果研究发现市场需求不足，必须诚实告知用户
   - 不要在错误的方向上帮用户"更努力地营销"

3. **事无巨细**
   - 给出的策略必须精确到可以直接执行
   - 不说"可以考虑做内容营销"，要说具体在哪做、做什么、怎么做、文案是什么
   - 所有文案使用用户产品的真实信息，不用占位符

4. **考虑全局**
   - 预算怎么分配才能形成飞轮
   - 短期获客和长期品牌怎么平衡
   - 哪些投入有复利效应、哪些是一次性消耗
   - 用户的时间和精力也是稀缺资源

5. **敢于创新**
   - 不局限于线上渠道。线下活动、合作伙伴、社群渗透、冷启动hack 都可以
   - 根据产品特点推荐最不寻常但最有效的策略
   - 如果一个策略没有竞品在用但你认为有效，大胆推荐并说明理由

## 当前状态

阶段: {phase}
产品信息: {json.dumps(product_context, ensure_ascii=False, default=str)}
已有专家输出: {json.dumps(list(expert_outputs.keys()), ensure_ascii=False)}
对话轮次: {self.state.turn_count}

## 你的 13 位专家

你可以调度以下专家（按需唤醒，不是每次都用所有人）：
- market_researcher: 市场研究专家（竞品分析、用户发现、行业扫描）
- economist: 经济学顾问（预算分配、CAC/LTV、定价、飞轮经济学）
- content_strategist: 内容营销专家（SEO/AEO、博客、程序化内容）
- social_media: 社媒运营专家（各平台策略、帖子撰写、互动策略）
- paid_ads: 付费广告专家（各广告平台、ROAS 优化、创意测试）
- partnerships: 合作关系专家（博主外联、商务拓展、联盟营销、地推）
- ai_distribution: AI 分发专家（MCP、GPT Store、AEO）
- psychologist: 消费心理学专家（转化优化、定价心理、说服力）
- product_growth: 产品增长专家（PLG、病毒循环、留存）
- data_analyst: 数据分析师（KPI、漏斗分析、实验设计）
- copywriter: 文案大师（所有文字输出的最终润色）
- critic: 策略审核专家（验证策略一致性、预算合理性、可行性）
- designer: 设计大佬（广告海报、社媒配图、品牌视觉、落地页设计）

## 决策指令

根据当前阶段和上下文，决定下一步行动：
- 如果需要更多信息 → ask_user
- 如果需要研究 → 调用工具或专家
- 如果分析充分 → 输出建议或计划
- 如果需要深度思考 → think

永远记住：你的目标不是输出一份报告，而是帮这个具体的产品找到真正有效的增长方式。"""

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

    def _incorporate_result(self, context: dict, action: AgentAction, result: Any) -> dict:
        """将工具结果合并到上下文"""
        context.setdefault("tool_results", []).append({
            "tool": action.tool_name,
            "args": action.tool_args,
            "result": result,
        })
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

        # 把用户消息加入消息历史
        if user_message:
            self._message_history.append({"role": "user", "content": user_message})

        # 构建上下文摘要注入到消息中
        context_summary_parts = []
        if product:
            context_summary_parts.append(f"[已知产品信息]: {json.dumps(product, ensure_ascii=False, default=str)}")
        if competitors:
            context_summary_parts.append(f"[已知竞品数据]: {json.dumps(competitors, ensure_ascii=False, default=str)[:500]}")
        if strategy:
            context_summary_parts.append(f"[当前策略]: {json.dumps(strategy, ensure_ascii=False, default=str)[:500]}")
        if results:
            context_summary_parts.append(f"[执行效果]: {json.dumps(results, ensure_ascii=False, default=str)[:300]}")

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
            # Level 1: 压缩上下文
            logger.info("Recovery L1: compacting context")
            context = self._compact_context(context)
        elif self._error_count == 2:
            # Level 2: 折叠历史
            logger.info("Recovery L2: collapsing history")
            context = self._collapse_history(context)
        else:
            # Level 3: 重置到安全状态
            logger.info("Recovery L3: resetting to safe state")
            context = await self._build_context("")
        return context

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
        await self.memory.save("loop_state", {
            "session_id": self.state.session_id,
            "phase": self.state.phase.value,
            "turn_count": self.state.turn_count,
            "tokens_used": self.state.total_tokens_used,
            "pending_tasks": self.state.pending_user_tasks,
            "expert_outputs_keys": list(self.state.expert_outputs.keys()),
            "is_waiting": self.state.is_waiting_for_user,
        })

    def _get_available_actions(self) -> list[dict]:
        """返回当前可用的 action schema（给 LLM 做 tool_use）"""
        return [
            {
                "name": "think",
                "description": "内部推理，不输出给用户",
                "parameters": {"type": "object", "properties": {"reasoning": {"type": "string"}}}
            },
            {
                "name": "call_tool",
                "description": "调用研究/分析工具",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "tool_args": {"type": "object"},
                        "reason": {"type": "string"},
                    }
                }
            },
            {
                "name": "consult_expert",
                "description": "调度专家 Agent 进行深度分析",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expert_id": {"type": "string", "enum": [
                            "market_researcher", "economist", "content_strategist",
                            "social_media", "paid_ads", "partnerships",
                            "ai_distribution", "psychologist", "product_growth",
                            "data_analyst", "copywriter", "critic", "designer"
                        ]},
                        "task": {"type": "string"},
                    }
                }
            },
            {
                "name": "ask_user",
                "description": "向用户提问以获取必要信息",
                "parameters": {"type": "object", "properties": {"question": {"type": "string"}}}
            },
            {
                "name": "output",
                "description": "向用户输出最终结果/建议",
                "parameters": {"type": "object", "properties": {"message": {"type": "string"}}}
            },
        ]

    def _parse_decision(self, response) -> AgentAction:
        """解析 LLM 的决策输出为 AgentAction"""
        from app.agent.engine.llm_adapter import LLMResponse

        if not isinstance(response, LLMResponse):
            return AgentAction(type=ActionType.OUTPUT, content=str(response))

        # 如果有 tool calls，解析第一个
        if response.tool_calls:
            tc = response.tool_calls[0]
            name = tc.get("name", "")
            args = tc.get("args", {})

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

"""
CrabRes Agent Engine — 路由层（Router）

根据用户消息特征，决定使用哪种执行模式：
  - QUICK: 打招呼、闲聊、自我介绍 → 直接回复
  - PIPELINE: 默认模式 → 确定性阶段流水线
  - REACT: 高信任用户 → LLM 自主决策循环

路由规则是确定性的（不依赖 LLM），保证零 token 消耗的快速路径。
"""

import logging
import re
from typing import Optional

from app.agent.engine.state import AgentState, ExecutionMode

logger = logging.getLogger(__name__)


class RouteDecision:
    """路由决策结果"""
    def __init__(
        self,
        mode: ExecutionMode,
        *,
        reason: str = "",
        expert_id: str = None,
        expert_task: str = None,
        confidence: float = 1.0,
    ):
        self.mode = mode
        self.reason = reason
        self.expert_id = expert_id       # 仅用于 expert_chat 模式
        self.expert_task = expert_task   # 仅用于 expert_chat 模式
        # confidence: 决策置信度（1.0 = 强规则命中；< 0.5 = 兜底/低置信度）
        # 低置信度的决策会触发 LLM 兜底分类（详见 maybe_refine_route）
        self.confidence = confidence


def route(user_message: str, state: AgentState) -> RouteDecision:
    """
    确定性路由：根据消息特征决定执行模式。
    
    不消耗任何 token，纯代码规则匹配。
    优先级从高到低：
      1. @expert 私聊 → expert_chat (特殊处理)
      2. 纯打招呼 → quick
      3. 自我认知问题 → quick（带 self_aware 标记）
      4. 有产品上下文 + 追问/工具请求 → pipeline 或 react
      5. 新产品描述 → pipeline（默认）
      6. 闲聊/模糊 → quick
    
    ReAct 模式的触发条件（需同时满足）：
      - trust_level >= "Trusted"（高信任）
      - 消息包含明确的行动指令
      - 已有足够的产品和研究上下文
    """
    msg = user_message.strip()
    msg_lower = msg.lower()
    
    # === 1: @expert 私聊 ===
    at_match = re.match(r'^@(\w+)\s+(.+)', msg, re.DOTALL)
    if at_match:
        return RouteDecision(
            mode=ExecutionMode.QUICK,
            reason="expert_chat",
            expert_id=at_match.group(1).lower(),
            expert_task=at_match.group(2).strip(),
        )
    
    # === 2: 纯打招呼（精确匹配，0 token）===
    greetings = ["hi", "hello", "hey", "你好", "嗨", "yo", "sup"]
    if msg_lower.rstrip("!！.。，,") in greetings:
        return RouteDecision(ExecutionMode.QUICK, reason="greeting")
    
    # === 3: 自我认知 ===
    self_triggers = [
        "what are you", "who are you", "你是什么", "你是谁",
        "what do you do", "你做什么", "介绍一下你", "introduce yourself",
    ]
    if any(t in msg_lower for t in self_triggers):
        return RouteDecision(ExecutionMode.QUICK, reason="self_awareness")
    
    # === 4: Deep Strategy 触发（异步后台任务）===
    try:
        from app.agent.engine.deep_strategy import should_trigger_deep_strategy
        if should_trigger_deep_strategy(msg):
            return RouteDecision(ExecutionMode.QUICK, reason="deep_strategy_background")
    except Exception:
        pass
    
    # === 5: 工具请求（有产品上下文时）===
    tool_triggers = [
        "browser", "浏览器", "browse", "搜索", "search",
        "发帖", "post", "发布", "publish", "分析", "analyze",
    ]
    has_product_context = bool(state.product_info.get("name")) or state.has_product_info
    is_tool_request = any(t in msg_lower for t in tool_triggers)
    url_in_msg = "http" in msg_lower or ".com" in msg_lower or ".io" in msg_lower or ".app" in msg_lower
    
    if (is_tool_request or url_in_msg) and has_product_context:
        # 有产品上下文的工具请求 → 根据信任级别决定模式
        trust_level = getattr(state, '_trust_level', 'Cautious')
        if trust_level in ("Trusted", "Autonomous"):
            return RouteDecision(ExecutionMode.REACT, reason=f"tool_request_trusted_{trust_level}")
        return RouteDecision(ExecutionMode.PIPELINE, reason="tool_request_safe_mode")
    
    # === 6: 追问（有历史研究数据）===
    has_prior_research = len(state.search_results) > 0
    has_prior_experts = len(state.expert_outputs) > 0
    is_followup = has_prior_research and len(msg) < 200
    
    if is_followup and (has_prior_research or has_prior_experts):
        trust_level = getattr(state, '_trust_level', 'Cautious')
        if trust_level in ("Trusted", "Autonomous") and is_tool_request:
            return RouteDecision(ExecutionMode.REACT, reason=f"followup_trusted_{trust_level}")
        return RouteDecision(ExecutionMode.PIPELINE, reason="followup_safe_mode")
    
    # === 7: 有明确产品信息的新请求 ===
    if has_product_context or _has_strong_product_signal(msg):
        trust_level = getattr(state, '_trust_level', 'Cautious')
        
        # ReAct 条件：高信任 + 消息较长 + 非首次对话
        if trust_level in ("Trusted", "Autonomous") and len(msg) > 50 and state.turn_count > 2:
            return RouteDecision(ExecutionMode.REACT, reason=f"product_request_trusted_{trust_level}_turn{state.turn_count}")
        
        return RouteDecision(ExecutionMode.PIPELINE, reason="product_request_default")
    
    # === 8: 兜底 → Pipeline（默认模式，最安全）===
    # confidence=0.3: 没有任何规则强命中，建议触发 LLM 兜底分类
    return RouteDecision(ExecutionMode.PIPELINE, reason="default_pipeline", confidence=0.3)


async def maybe_refine_route(
    decision: "RouteDecision",
    user_message: str,
    llm_service,
) -> "RouteDecision":
    """
    Router LLM 兜底：当代码规则置信度不高时，用一次 PARSING tier 的小模型分类。

    设计理念（hybrid: code as fast path, LLM as fallback）：
    - 强规则命中（greeting/expert_chat/self_awareness 等）→ 直接返回，零 token
    - 兜底 default_pipeline + 短消息 → 调用一次 nano 模型分类，覆盖正则漏召回

    单次成本约 $0.0001 (PARSING tier)，比维护一份不断膨胀的关键词列表更经济。
    """
    # 强规则已命中，无需兜底
    if decision.confidence >= 0.7:
        return decision
    # 长消息基本是 growth_request，Pipeline 处理足够
    if len(user_message) > 200:
        return decision
    # 没有 LLM 可用 → 退化成原决策
    if llm_service is None or not hasattr(llm_service, "generate"):
        return decision

    try:
        from app.agent.engine.llm_adapter import TaskTier

        prompt = (
            "Classify the user message into ONE label, return ONLY the label:\n"
            "- greeting (pure hello/hi/嗨/早上好/在吗/yo, no real request)\n"
            "- self_awareness (asking what/who you are)\n"
            "- chitchat (small talk, no growth task)\n"
            "- growth_request (any product/marketing/competitor/strategy task)\n"
            "Default to growth_request when unsure."
        )
        resp = await llm_service.generate(
            system_prompt=prompt,
            messages=[{"role": "user", "content": user_message[:300]}],
            tier=TaskTier.PARSING,
            max_tokens=10,
        )
        label = (getattr(resp, "content", "") or "").strip().lower()
        logger.info(f"Router LLM fallback classified: {label!r}")

        if "greeting" in label:
            return RouteDecision(ExecutionMode.QUICK, reason="greeting", confidence=0.85)
        if "self_aware" in label:
            return RouteDecision(ExecutionMode.QUICK, reason="self_awareness", confidence=0.85)
        # chitchat / growth_request / 其他 → 留给 Pipeline 内部的 node_understand 继续判断
    except Exception as e:
        logger.debug(f"Router LLM fallback skipped: {e}")

    return decision


def _has_strong_product_signal(msg: str) -> bool:
    """检测强产品信号"""
    msg_lower = msg.lower()
    strong_signals = ["crabres", "crab-res", "crab res", "ai growth"]
    if any(s in msg_lower for s in strong_signals):
        return True
    
    if len(msg) < 15:
        return False
    
    signals = [
        "my product", "i built", "i made", "i'm building", "we built",
        "it's a", "it is a", "helps", "for users", "for developers",
        "saas", "app", "tool", "platform", "$", "/mo", "pricing",
        "我的产品", "我做了", "我在做", "帮助", "用户", "增长",
        "http", ".com", ".io", ".app",
    ]
    return any(s in msg_lower for s in signals)

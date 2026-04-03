"""
CrabRes LLM 适配器 — Moonshot 为主力，OpenRouter 为备选

=== 模型分级策略 ===

当前主力：Moonshot V1 128K（直连，不经 OpenRouter）
备选：OpenRouter（Claude/DeepSeek/Gemini），需充值后使用

Tier 1: CRITICAL — 首席增长官的核心决策
  主力: moonshot-v1-128k (直连 Moonshot API)
  备选: claude-sonnet-4 via OpenRouter → deepseek-v3 via OpenRouter

Tier 2: THINKING — 深度研究和策略制定
  主力: moonshot-v1-128k
  备选: deepseek-v3 via OpenRouter → gemini-flash via OpenRouter

Tier 3: WRITING — 文案创作
  主力: moonshot-v1-128k
  备选: deepseek-v3 via OpenRouter

Tier 4: PARSING — 工具结果解析、格式化
  主力: moonshot-v1-128k
  备选: gemini-flash via OpenRouter → deepseek-v3 via OpenRouter

=== 降级策略 ===
每个 Tier 的降级链：Moonshot → OpenRouter 模型
Moonshot 走直连 API，不受 OpenRouter 余额限制。
"""

import json
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class TaskTier(str, Enum):
    """任务分级"""
    CRITICAL = "critical"    # Coordinator 核心决策
    THINKING = "thinking"    # 深度研究和分析
    WRITING = "writing"      # 文案创作
    PARSING = "parsing"      # 解析和格式化
    EMBEDDING = "embedding"  # 向量化


@dataclass
class ModelSpec:
    """模型规格"""
    id: str                          # OpenRouter model ID
    display_name: str                # 显示名
    input_cost_per_m: float          # $/M input tokens
    output_cost_per_m: float         # $/M output tokens
    max_tokens: int = 4096           # 默认 max_tokens
    supports_tools: bool = True      # 是否支持 function calling
    provider: str = "openrouter"     # openrouter / moonshot


# ===== 模型注册表 =====
MODELS: dict[str, ModelSpec] = {
    # 主力: Moonshot（直连，不经 OpenRouter）
    "moonshot": ModelSpec(
        id="moonshot-v1-128k",
        display_name="Moonshot V1 128K",
        input_cost_per_m=0.8,  # 约 ¥0.012/千tokens
        output_cost_per_m=0.8,
        max_tokens=4096,
        provider="moonshot",
    ),
    # 备选: Claude via OpenRouter
    "claude-sonnet-4": ModelSpec(
        id="anthropic/claude-sonnet-4",
        display_name="Claude Sonnet 4",
        input_cost_per_m=3.0,
        output_cost_per_m=15.0,
        max_tokens=8192,
    ),
    # 备选: DeepSeek via OpenRouter
    "deepseek-v3": ModelSpec(
        id="deepseek/deepseek-chat-v3-0324",
        display_name="DeepSeek V3",
        input_cost_per_m=0.27,
        output_cost_per_m=1.10,
        max_tokens=4096,
    ),
    # 备选: Gemini via OpenRouter
    "gemini-flash": ModelSpec(
        id="google/gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        input_cost_per_m=0.15,
        output_cost_per_m=0.60,
        max_tokens=4096,
    ),
}

# ===== Tier → 模型降级链 =====
# Moonshot 在所有 Tier 中都是第一选择，OpenRouter 模型作为降级备选
TIER_CHAIN: dict[TaskTier, list[str]] = {
    TaskTier.CRITICAL: ["moonshot", "claude-sonnet-4", "deepseek-v3"],
    TaskTier.THINKING: ["moonshot", "deepseek-v3", "gemini-flash"],
    TaskTier.WRITING:  ["moonshot", "deepseek-v3"],
    TaskTier.PARSING:  ["moonshot", "gemini-flash", "deepseek-v3"],
}


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    model_display: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0


@dataclass
class UsageTracker:
    """成本追踪"""
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    calls_by_tier: dict = field(default_factory=lambda: {t.value: 0 for t in TaskTier})
    tokens_by_tier: dict = field(default_factory=lambda: {t.value: 0 for t in TaskTier})
    cost_by_tier: dict = field(default_factory=lambda: {t.value: 0.0 for t in TaskTier})


class AgentLLM:
    """
    CrabRes Agent LLM 接口
    
    主力走 OpenRouter（一个 key 访问所有模型）。
    Moonshot 作为最后降级。
    
    使用规则：
    1. Coordinator（首席增长官）的决策用 Tier CRITICAL
    2. 专家的深度分析用 Tier THINKING
    3. 文案生成用 Tier WRITING
    4. 工具结果解析用 Tier PARSING
    5. 每个 Tier 有降级链，首选挂了自动切下一个
    6. 成本实时追踪，接近预算时自动降级到更便宜的模型
    """

    def __init__(self, budget_limit_usd: float = 1.0):
        """
        Args:
            budget_limit_usd: 单次会话的美元预算上限（默认 $1）
        """
        self._openrouter_client: Optional[AsyncOpenAI] = None
        self._moonshot_client: Optional[AsyncOpenAI] = None
        self.usage = UsageTracker()
        self.budget_limit = budget_limit_usd

    @property
    def openrouter(self) -> AsyncOpenAI:
        if self._openrouter_client is None:
            self._openrouter_client = AsyncOpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://crabres.com",
                    "X-Title": "CrabRes",
                },
            )
        return self._openrouter_client

    @property
    def moonshot(self) -> AsyncOpenAI:
        if self._moonshot_client is None:
            self._moonshot_client = AsyncOpenAI(
                api_key=settings.MOONSHOT_API_KEY,
                base_url="https://api.moonshot.cn/v1",
            )
        return self._moonshot_client

    def _get_client(self, spec: ModelSpec) -> AsyncOpenAI:
        if spec.provider == "moonshot":
            return self.moonshot
        return self.openrouter

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        tier: TaskTier = TaskTier.THINKING,
        tools: Optional[list] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        生成响应，自动按 Tier 选模型
        
        Args:
            system_prompt: 系统提示
            messages: 对话历史
            tier: 任务分级（决定用哪个模型）
            tools: 可用工具（function calling 格式）
            temperature: 温度
            max_tokens: 覆盖默认 max_tokens
        """
        # 预算检查：如果接近上限，强制降级
        effective_tier = self._maybe_downgrade_tier(tier)
        chain = TIER_CHAIN.get(effective_tier, TIER_CHAIN[TaskTier.PARSING])

        for model_key in chain:
            spec = MODELS[model_key]
            try:
                result = await self._call(
                    spec=spec,
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens or spec.max_tokens,
                )
                # 记录成本
                self._track_usage(tier, spec, result)
                return result

            except Exception as e:
                error_str = str(e)
                # 402: 余额不足 → 降低 max_tokens 重试同一个模型
                if "402" in error_str and "credits" in error_str.lower():
                    reduced_tokens = min(2000, (max_tokens or spec.max_tokens) // 2)
                    logger.info(f"[LLM] {spec.display_name} 402 insufficient credits, retrying with max_tokens={reduced_tokens}")
                    try:
                        result = await self._call(
                            spec=spec, system_prompt=system_prompt, messages=messages,
                            tools=tools, temperature=temperature, max_tokens=reduced_tokens,
                        )
                        self._track_usage(tier, spec, result)
                        return result
                    except Exception:
                        pass
                
                logger.warning(f"[LLM] {spec.display_name} failed: {error_str[:100]}, trying next...")
                continue

        # 全部失败
        return LLMResponse(
            content="[系统] 所有模型调用失败，请检查 API Key 或网络。",
            model="error",
        )

    async def _call(
        self,
        spec: ModelSpec,
        system_prompt: str,
        messages: list[dict],
        tools: Optional[list],
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """执行单次 LLM 调用"""
        client = self._get_client(spec)
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        kwargs: dict[str, Any] = {
            "model": spec.id,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools and spec.supports_tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)
        return self._parse(response, spec)

    def _parse(self, response, spec: ModelSpec) -> LLMResponse:
        """解析响应"""
        choice = response.choices[0]
        usage = response.usage
        tokens = usage.total_tokens if usage else 0

        # 估算成本
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0
        cost = (input_tokens * spec.input_cost_per_m + output_tokens * spec.output_cost_per_m) / 1_000_000

        result = LLMResponse(
            content=choice.message.content or "",
            model=spec.id,
            model_display=spec.display_name,
            tokens_used=tokens,
            cost_usd=cost,
        )

        # 解析 tool calls
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                result.tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "args": args,
                })

        return result

    def _track_usage(self, tier: TaskTier, spec: ModelSpec, result: LLMResponse):
        """追踪成本"""
        self.usage.total_tokens += result.tokens_used
        self.usage.total_cost_usd += result.cost_usd
        self.usage.calls_by_tier[tier.value] = self.usage.calls_by_tier.get(tier.value, 0) + 1
        self.usage.tokens_by_tier[tier.value] = self.usage.tokens_by_tier.get(tier.value, 0) + result.tokens_used
        self.usage.cost_by_tier[tier.value] = self.usage.cost_by_tier.get(tier.value, 0) + result.cost_usd

        logger.info(
            f"[LLM] {spec.display_name} | tier={tier.value} | "
            f"tokens={result.tokens_used} | cost=${result.cost_usd:.4f} | "
            f"session_total=${self.usage.total_cost_usd:.4f}"
        )

    def _maybe_downgrade_tier(self, tier: TaskTier) -> TaskTier:
        """如果接近预算上限，自动降级"""
        ratio = self.usage.total_cost_usd / self.budget_limit if self.budget_limit > 0 else 0

        if ratio >= 0.9:
            # 超过 90% 预算，所有任务降到最便宜
            logger.warning(f"[LLM] Budget {ratio*100:.0f}% used, forcing PARSING tier")
            return TaskTier.PARSING
        elif ratio >= 0.7:
            # 超过 70%，CRITICAL 降为 THINKING
            if tier == TaskTier.CRITICAL:
                logger.info(f"[LLM] Budget {ratio*100:.0f}% used, downgrading CRITICAL → THINKING")
                return TaskTier.THINKING
        return tier

    def get_cost_report(self) -> dict:
        """获取当前会话的成本报告"""
        return {
            "total_tokens": self.usage.total_tokens,
            "total_cost_usd": round(self.usage.total_cost_usd, 4),
            "budget_limit_usd": self.budget_limit,
            "budget_used_pct": round(self.usage.total_cost_usd / self.budget_limit * 100, 1) if self.budget_limit > 0 else 0,
            "by_tier": {
                tier: {
                    "calls": self.usage.calls_by_tier.get(tier, 0),
                    "tokens": self.usage.tokens_by_tier.get(tier, 0),
                    "cost_usd": round(self.usage.cost_by_tier.get(tier, 0), 4),
                }
                for tier in [t.value for t in TaskTier]
            },
        }

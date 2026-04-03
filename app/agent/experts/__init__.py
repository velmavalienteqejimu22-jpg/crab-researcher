"""
CrabRes 专家 Agent 系统
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseExpert(ABC):
    """专家基类"""

    _llm = None  # 共享 LLM 实例，由 ExpertPool 设置

    @property
    @abstractmethod
    def expert_id(self) -> str:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        ...

    async def analyze(self, context: dict, task: str) -> str:
        """
        执行分析任务，调用 LLM
        
        升级：
        1. 选择性知识注入（不全量 580 行，只注入任务相关的渠道知识）
        2. 上下文隔离（每个专家只看到自己需要的 context 片段）
        3. Prompt Cache（同 session 内相同知识不重复发送）
        """
        if not self._llm:
            return f"[{self.name}] LLM 未初始化"

        from app.agent.engine.llm_adapter import TaskTier
        from app.agent.engine.context_engine import get_selective_knowledge, build_expert_context
        import json

        # 🔥 选择性知识注入（根据任务内容只注入相关渠道知识）
        user_message = context.get("user_message", "")
        knowledge = get_selective_knowledge(self.expert_id, task, user_message)

        # 构建增强版 system prompt = 专家基础 prompt + 选择性知识 + 输出质量规则
        enhanced_prompt = self.system_prompt
        if knowledge:
            enhanced_prompt += "\n" + knowledge

        # 所有专家共享的输出质量规则
        enhanced_prompt += """

## OUTPUT QUALITY RULES (MANDATORY)

1. **SPECIFIC DATA POINTS**: Every claim must include at least one specific number, name, or link.
   BAD: "There are several competitors in this space"
   GOOD: "Top 3 competitors: Teal (4.8M visits/mo), Jobscan (2.1M), Kickresume (890K)"

2. **NO CONSULTANT SPEAK**: Banned phrases: "consider", "might want to", "could potentially", "it's important to", "there are opportunities". 
   Instead: direct imperatives with specifics. "Post in r/cscareerquestions (1.2M members) every Tuesday 9am EST."

3. **CITE YOUR REASONING**: Don't just state conclusions. Show the logic chain:
   "Reddit r/resumes has 850K members → 42% of Teal's traffic comes from Reddit → your first priority should be r/resumes because [specific reason]."

4. **ONE CONTRARIAN TAKE**: Include one thing that goes against conventional wisdom or challenges the other experts' views. You are not here to agree — you are here to sharpen the strategy through debate."""

        # 🔥 上下文隔离：专家只看到自己需要的 context
        isolated_ctx = build_expert_context(self.expert_id, context, task)
        product_info = isolated_ctx.get("product", {})
        expert_outputs = isolated_ctx.get("expert_outputs", {})

        # 注入相关的工具搜索结果摘要（如果有）
        tool_results_text = ""
        for r in isolated_ctx.get("tool_results", [])[:3]:
            result_str = json.dumps(r.get("result", {}), ensure_ascii=False, default=str)[:400]
            tool_results_text += f"- [{r.get('tool', '')}]: {result_str}\n"

        user_content = f"""## Task
{task}

## Product Info
{json.dumps(product_info, ensure_ascii=False, default=str) if product_info else "Not yet provided"}

## Research Data Available
{tool_results_text if tool_results_text else "No research data yet"}

## Other Experts' Views (challenge or build on these)
{json.dumps(expert_outputs, ensure_ascii=False, default=str)[:1000] if expert_outputs else "None yet"}
"""
        response = await self._llm.generate(
            system_prompt=enhanced_prompt,
            messages=[{"role": "user", "content": user_content}],
            tier=TaskTier.THINKING,
            max_tokens=2048,
        )
        return response.content


class ExpertPool:
    """专家池"""

    def __init__(self, llm=None):
        self._experts: dict[str, BaseExpert] = {}
        self._llm = llm

    def set_llm(self, llm):
        """设置共享的 LLM 实例"""
        self._llm = llm
        for expert in self._experts.values():
            expert._llm = llm

    def register(self, expert: BaseExpert):
        if self._llm:
            expert._llm = self._llm
        self._experts[expert.expert_id] = expert

    def get(self, expert_id: str) -> Optional[BaseExpert]:
        return self._experts.get(expert_id)

    def list_all(self) -> list[dict]:
        return [{"id": e.expert_id, "name": e.name} for e in self._experts.values()]

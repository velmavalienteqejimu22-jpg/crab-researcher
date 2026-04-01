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
        """执行分析任务，调用 LLM"""
        if not self._llm:
            return f"[{self.name}] LLM 未初始化"

        from app.agent.engine.llm_adapter import TaskTier
        import json

        # 构建专家专用的消息
        product_info = context.get("product", {})
        expert_outputs = context.get("expert_outputs", {})

        user_content = f"""## 任务
{task}

## 产品信息
{json.dumps(product_info, ensure_ascii=False, default=str) if product_info else "暂无，需要向用户询问"}

## 其他专家已有的分析
{json.dumps(expert_outputs, ensure_ascii=False, default=str)[:1000] if expert_outputs else "暂无"}
"""
        response = await self._llm.generate(
            system_prompt=self.system_prompt,
            messages=[{"role": "user", "content": user_content}],
            tier=TaskTier.THINKING,  # 专家分析用 THINKING tier
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

    def get(self, expert_id: str) -> BaseExpert | None:
        return self._experts.get(expert_id)

    def list_all(self) -> list[dict]:
        return [{"id": e.expert_id, "name": e.name} for e in self._experts.values()]

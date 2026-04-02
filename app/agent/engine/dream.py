"""
CrabRes Growth Dream — 记忆蒸馏和整理
学习自 Claude Code 的 AutoDream 机制。

职责：
- 定期或手动触发，将零散的日志（journal/）和对话历史蒸馏为结构化记忆。
- 消除矛盾，合并重复信息。
- 将模糊的观察转化为确定的事实。
"""

import logging
import json
import time
from typing import Any, Optional
from app.agent.memory import GrowthMemory
from app.agent.engine.llm_adapter import AgentLLM, TaskTier

logger = logging.getLogger(__name__)

class GrowthDream:
    """记忆蒸馏引擎"""

    def __init__(self, memory: GrowthMemory, llm: AgentLLM):
        self.memory = memory
        self.llm = llm

    async def distill(self, session_id: str):
        """
        对指定会话进行记忆蒸馏
        
        Phase 1: Gather (收集日志和当前状态)
        Phase 2: Consolidate (合并和消除矛盾)
        Phase 3: Write (写回结构化记忆)
        """
        logger.info(f"Starting Growth Dream for session {session_id}")
        
        # 1. Gather
        # 读取会话状态
        state = await self.memory.load(f"loop_state_{session_id}")
        if not state:
            logger.warning(f"No state found for session {session_id}, skipping dream.")
            return

        # 读取产品 DNA
        product_dna = await self.memory.load("product") or {}
        
        # 读取专家输出
        expert_outputs_keys = state.get("expert_outputs_keys", [])
        expert_data = {}
        for eid in expert_outputs_keys:
            output = await self.memory.load(f"expert_output_{session_id}_{eid}", category="research")
            if output:
                expert_data[eid] = output

        # 2. Consolidate via LLM
        prompt = f"""你是 CrabRes 的记忆蒸馏引擎（Growth Dream）。
你的任务是将一个增长研究会话的原始输出蒸馏为结构化的事实，并存入长期记忆。

## 当前已知产品信息
{json.dumps(product_dna, ensure_ascii=False)}

## 专家研究发现
{json.dumps(expert_data, ensure_ascii=False)[:5000]}

## 任务
1. 提取关于产品的新事实（功能、定价、技术栈）。
2. 提取关于竞品的新发现（特别是流量来源、优势、弱点）。
3. 提取关于目标用户的新洞察（痛点、活跃社区）。
4. 提取已确定的策略和任务。

## 输出格式
请输出一个 JSON，包含以下字段：
- product_updates: dict
- competitors_found: list[dict]
- audience_insights: list[str]
- confirmed_strategy: str
"""

        response = await self.llm.generate(
            system_prompt="你是一个精准的知识提取引擎。",
            messages=[{"role": "user", "content": prompt}],
            tier=TaskTier.THINKING,
        )

        try:
            distilled = json.loads(response.content)
            await self._update_long_term_memory(distilled)
            logger.info(f"Growth Dream completed for session {session_id}")
            return distilled
        except Exception as e:
            logger.error(f"Failed to parse distilled memory: {e}")
            return None

    async def _update_long_term_memory(self, distilled: dict):
        """将蒸馏后的数据写回 memdir/"""
        # 更新产品信息
        if distilled.get("product_updates"):
            current = await self.memory.load("product") or {}
            current.update(distilled["product_updates"])
            await self.memory.save("product", current)

        # 更新竞品
        for comp in distilled.get("competitors_found", []):
            name = comp.get("name")
            if name:
                await self.memory.save(name.lower(), comp, category="research")

        # 更新策略
        if distilled.get("confirmed_strategy"):
            await self.memory.save("latest_strategy", {
                "content": distilled["confirmed_strategy"],
                "updated_at": time.time()
            }, category="strategy")

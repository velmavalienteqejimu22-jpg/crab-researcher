"""
CrabRes Channel Gateway — Unified agent invocation for all platforms

All channels (Telegram, Discord, Feishu, Web) share this single entry point.
No more duplicated agent initialization in every channel file.
"""

import asyncio
import logging
import time
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# Singleton cache for agent components (avoid re-init per message)
_agent_cache: dict = {}


class ChannelGateway:
    """
    Unified gateway for all channels to invoke CrabRes Agent.
    
    Responsibilities:
    - Initialize agent components once, reuse across messages
    - Route messages to PipelineRunner (default) or AgentLoop
    - Handle language detection from channel context
    - Record trust events (session count, confirmations)
    - Format output for different channel constraints
    """

    MAX_BUDGET_PER_SESSION = 1.0  # USD

    def __init__(self, channel: str, user_id: str, language: str = "en"):
        self.channel = channel
        self.user_id = user_id
        self.language = language
        self._session_id = f"{channel}-{user_id}"

    async def process(self, message: str) -> str:
        """
        Process a user message and return the agent's response.
        
        This is the main entry point for all channels.
        Returns plain text (channels handle their own formatting).
        """
        start_time = time.time()

        try:
            llm, tools, experts, memory = await self._get_or_create_components()

            # Record session for trust level tracking
            from app.agent.trust import TrustManager
            trust = TrustManager(memory)
            await trust.record_session()

            # Use PipelineRunner (deterministic, research-first)
            from app.agent.engine.pipeline import PipelineRunner
            runner = PipelineRunner(
                session_id=self._session_id,
                llm=llm,
                tools=tools,
                experts=experts,
                memory=memory,
                language=self.language,
            )

            result = await runner.run(message)

            elapsed = round(time.time() - start_time, 1)
            logger.info(
                f"[Gateway] {self.channel}/{self.user_id} processed in {elapsed}s "
                f"(tokens: {llm.usage.total_tokens}, cost: ${llm.usage.total_cost_usd:.4f})"
            )

            return result if result else "I'm still thinking about this. Could you provide more details about your product?"

        except Exception as e:
            logger.error(f"[Gateway] {self.channel}/{self.user_id} failed: {e}", exc_info=True)
            return f"Something went wrong. Please try again. (Error: {str(e)[:100]})"

    async def process_stream(self, message: str) -> AsyncGenerator[dict, None]:
        """
        Process a message with streaming events (for SSE-capable channels like Web).
        """
        try:
            llm, tools, experts, memory = await self._get_or_create_components()

            from app.agent.trust import TrustManager
            trust = TrustManager(memory)
            await trust.record_session()

            from app.agent.engine.loop import AgentLoop
            loop = AgentLoop(
                session_id=self._session_id,
                llm_service=llm,
                tool_registry=tools,
                expert_pool=experts,
                memory=memory,
            )

            async for event in loop.run(message):
                yield event

        except Exception as e:
            logger.error(f"[Gateway] stream failed: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)[:200]}

    async def _get_or_create_components(self):
        """Get or create agent components (cached per user)"""
        cache_key = self._session_id

        if cache_key in _agent_cache:
            cached = _agent_cache[cache_key]
            # Expire cache after 30 minutes
            if time.time() - cached["created_at"] < 1800:
                return cached["llm"], cached["tools"], cached["experts"], cached["memory"]
            else:
                del _agent_cache[cache_key]

        from app.agent.engine.llm_adapter import AgentLLM
        from app.agent.tools import ToolRegistry
        from app.agent.tools.research import WebSearchTool, ScrapeWebsiteTool, SocialSearchTool
        from app.agent.experts import ExpertPool
        from app.agent.experts.market_researcher import MarketResearcher
        from app.agent.experts.economist import Economist
        from app.agent.experts.psychologist import ConsumerPsychologist
        from app.agent.experts.social_media import SocialMediaExpert
        from app.agent.experts.content_strategist import ContentStrategist
        from app.agent.experts.copywriter import MasterCopywriter
        from app.agent.experts.critic import StrategyCritic
        from app.agent.experts.data_analyst import DataAnalyst
        from app.agent.experts.product_growth import ProductGrowthExpert
        from app.agent.experts.paid_ads import PaidAdsExpert
        from app.agent.experts.partnerships import PartnershipExpert
        from app.agent.experts.designer import GrowthDesigner
        from app.agent.experts.ai_distribution import AIDistributionExpert
        from app.agent.memory import GrowthMemory

        llm = AgentLLM(budget_limit_usd=self.MAX_BUDGET_PER_SESSION)
        
        tools = ToolRegistry()
        tools.register(WebSearchTool())
        tools.register(ScrapeWebsiteTool())
        tools.register(SocialSearchTool())

        experts = ExpertPool()
        for expert_cls in [
            MarketResearcher, Economist, ConsumerPsychologist,
            SocialMediaExpert, ContentStrategist, MasterCopywriter,
            StrategyCritic, DataAnalyst, ProductGrowthExpert,
            PaidAdsExpert, PartnershipExpert, GrowthDesigner,
            AIDistributionExpert,
        ]:
            experts.register(expert_cls())
        experts.set_llm(llm)

        memory = GrowthMemory(base_dir=f".crabres/memory/{self.channel}_{self.user_id}")

        _agent_cache[cache_key] = {
            "llm": llm, "tools": tools, "experts": experts, "memory": memory,
            "created_at": time.time(),
        }

        return llm, tools, experts, memory

    @staticmethod
    def format_for_channel(text: str, channel: str, max_length: int = 4000) -> list[str]:
        """
        Split and format text for channel-specific constraints.
        
        Returns a list of message chunks.
        """
        if not text:
            return [""]

        if channel == "telegram":
            # Telegram: 4096 char limit, supports Markdown
            return [text[i:i+max_length] for i in range(0, len(text), max_length)]
        elif channel == "discord":
            # Discord: 2000 char limit, supports Markdown
            return [text[i:i+1900] for i in range(0, len(text), 1900)]
        elif channel == "feishu":
            # Feishu: supports interactive cards, no hard limit
            return [text]
        else:
            return [text]

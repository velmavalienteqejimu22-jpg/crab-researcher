import asyncio
import logging
import uuid
import json
from pathlib import Path
from app.agent.engine.loop import AgentLoop
from app.agent.engine.llm_adapter import AgentLLM
from app.agent.tools import ToolRegistry
from app.agent.tools.research import WebSearchTool, ScrapeWebsiteTool, SocialSearchTool, CompetitorAnalyzeTool, DeepScrapeTool
from app.agent.experts import ExpertPool
from app.agent.experts.market_researcher import MarketResearcher
from app.agent.experts.economist import Economist
from app.agent.experts.psychologist import ConsumerPsychologist
from app.agent.memory import GrowthMemory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    session_id = str(uuid.uuid4())
    user_id = "test_user"
    
    # 1. Setup components
    llm = AgentLLM(budget_limit_usd=0.05)
    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(ScrapeWebsiteTool())
    tools.register(SocialSearchTool())
    tools.register(CompetitorAnalyzeTool())
    tools.register(DeepScrapeTool())
    
    experts = ExpertPool(llm=llm)
    experts.register(MarketResearcher())
    experts.register(Economist())
    experts.register(ConsumerPsychologist())
    
    memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")
    
    # 2. Initialize loop
    loop = AgentLoop(
        session_id=session_id,
        llm_service=llm,
        tool_registry=tools,
        expert_pool=experts,
        memory=memory
    )
    
    # 3. Run a scenario
    user_input = "我正在开发一个为开发者设计的屏幕录制工具，支持一键生成漂亮的 GIF 并自动上传到 GitHub/Cloudinary。我的竞争对手有 Loom, CleanShot X。帮我分析一下增长点。"
    
    print(f"\n🚀 Starting Growth Research for session: {session_id}")
    print(f"User: {user_input}\n")
    
    async for event in loop.run(user_input):
        etype = event.get("type")
        content = event.get("content", "")
        
        if etype == "status":
            print(f"⏳ [Status] {content}")
        elif etype == "expert_thinking":
            eid = event.get("expert_id")
            print(f"🧠 [Expert: {eid}] Thinking...")
            # print(f"{content[:200]}...")
        elif etype == "message":
            print(f"\n✅ [Final Response]\n{content}")
        elif etype == "question":
            print(f"\n❓ [Question] {content}")
        elif etype == "error":
            print(f"❌ [Error] {content}")

    # 4. Check persistence
    print(f"\n💾 Verifying persistence...")
    state_file = Path(f".crabres/memory/{user_id}/product/loop_state_{session_id}.json")
    if state_file.exists():
        print(f"✅ State persisted to {state_file}")
    else:
        print(f"❌ State NOT found at {state_file}")

if __name__ == "__main__":
    async def run_test():
        try:
            await main()
        except Exception as e:
            logger.error(f"Test failed: {e}", exc_info=True)
            
    asyncio.run(run_test())

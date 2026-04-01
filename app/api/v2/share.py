"""
CrabRes 分享卡片 API

生成可分享的 HTML 卡片图片（生物体 + 增长数据 + 品牌水印）。
用户一键分享到 X/LinkedIn，自带品牌曝光。
"""

import logging
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from app.core.security import get_current_user
from app.agent.memory import GrowthMemory
from app.components.creature.types import SPECIES_CONFIG

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/share", tags=["Share"])


@router.get("/card/{user_id}", response_class=HTMLResponse)
async def generate_share_card(user_id: int):
    """
    生成分享卡片 HTML（可截图或用 puppeteer 转图片）
    
    公开端点——不需要认证，因为分享链接会被转发。
    """
    memory = GrowthMemory(base_dir=f".crabres/memory/{user_id}")
    product = await memory.load("product") or {}
    stats = await memory.load("execution_stats", category="execution") or {}

    product_name = product.get("name", "My Product")
    total_users = stats.get("total_users", 0)
    growth_rate = stats.get("growth_rate", 0)
    streak = stats.get("streak_days", 0)
    species = stats.get("species", "crab")
    spec = SPECIES_CONFIG.get(species, SPECIES_CONFIG["crab"])

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta property="og:title" content="{product_name} — Growing with CrabRes">
<meta property="og:description" content="+{growth_rate}% growth · {total_users} users · {streak}d streak">
<meta property="og:image" content="https://crab-researcher.vercel.app/og-card.png">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=DM+Sans:wght@400;500&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ 
    width: 600px; height: 315px; 
    background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
    font-family: 'DM Sans', sans-serif;
    color: #E2E8F0;
    display: flex;
    align-items: center;
    padding: 40px;
    position: relative;
    overflow: hidden;
  }}
  .glow {{
    position: absolute;
    width: 200px; height: 200px;
    border-radius: 50%;
    background: {spec["baseColor"]}20;
    filter: blur(60px);
    top: 50%; left: 30%;
    transform: translate(-50%, -50%);
  }}
  .content {{ position: relative; z-index: 1; width: 100%; }}
  .header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }}
  .creature {{
    width: 64px; height: 64px;
    background: {spec["baseColor"]}25;
    border-radius: 16px;
    display: flex; align-items: center; justify-content: center;
    font-size: 32px;
    border: 2px solid {spec["baseColor"]}40;
  }}
  .name {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 24px; font-weight: 700;
    color: #F8FAFC;
  }}
  .species {{
    font-size: 13px; color: {spec["baseColor"]};
    font-weight: 500;
  }}
  .metrics {{
    display: flex; gap: 32px; margin-bottom: 24px;
  }}
  .metric-value {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 28px; font-weight: 700;
    color: #F8FAFC;
  }}
  .metric-label {{
    font-size: 12px; color: #94A3B8;
    margin-top: 2px;
  }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
  }}
  .brand {{
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px; color: #64748B;
    display: flex; align-items: center; gap: 6px;
  }}
  .brand span {{ color: #0EA5E9; }}
  .streak {{
    background: linear-gradient(135deg, #F97316, #EAB308);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 14px; font-weight: 700;
  }}
  .grid {{
    position: absolute; inset: 0;
    background-image: 
      linear-gradient(rgba(14,165,233,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(14,165,233,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
  }}
</style>
</head>
<body>
  <div class="grid"></div>
  <div class="glow"></div>
  <div class="content">
    <div class="header">
      <div class="creature">🦀</div>
      <div>
        <div class="name">{product_name}</div>
        <div class="species">{spec["displayName"]}</div>
      </div>
    </div>
    <div class="metrics">
      <div>
        <div class="metric-value">+{growth_rate}%</div>
        <div class="metric-label">growth</div>
      </div>
      <div>
        <div class="metric-value">{total_users}</div>
        <div class="metric-label">users</div>
      </div>
      <div>
        <div class="metric-value">{streak}d</div>
        <div class="metric-label">streak</div>
      </div>
    </div>
    <div class="footer">
      <div class="brand">🦀 <span>CrabRes</span> · crabres.com</div>
      {"<div class='streak'>🔥 " + str(streak) + "-day streak</div>" if streak >= 7 else ""}
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/card-url")
async def get_share_url(current_user: dict = Depends(get_current_user)):
    """获取当前用户的分享卡片 URL"""
    uid = current_user.get("user_id", 0)
    base = "https://crab-researcher.onrender.com/api"
    return {
        "card_url": f"{base}/share/card/{uid}",
        "twitter_share": f"https://twitter.com/intent/tweet?text=Growing%20with%20CrabRes%20🦀&url={base}/share/card/{uid}",
        "linkedin_share": f"https://www.linkedin.com/sharing/share-offsite/?url={base}/share/card/{uid}",
    }

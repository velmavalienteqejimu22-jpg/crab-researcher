"""
飞书 Bot 双向对话 — 不只是通知，是对话

用户在飞书群里 @CrabRes → CrabRes 回复增长建议
支持文本消息和交互式卡片（带按钮）

接入方式：
1. 在飞书开放平台创建应用，获取 App ID + App Secret
2. 开启机器人能力
3. 配置事件订阅 URL: https://your-server/api/feishu/event
4. 订阅事件: im.message.receive_v1
"""

import hashlib
import hmac
import json
import logging
import time
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feishu", tags=["Feishu Bot"])

# 飞书 API
FEISHU_API = "https://open.feishu.cn/open-apis"
_tenant_token = None
_token_expires = 0


async def _get_tenant_token() -> str:
    """获取飞书 tenant_access_token"""
    global _tenant_token, _token_expires

    if _tenant_token and time.time() < _token_expires:
        return _tenant_token

    app_id = getattr(settings, 'FEISHU_APP_ID', None)
    app_secret = getattr(settings, 'FEISHU_APP_SECRET', None)
    if not app_id or not app_secret:
        raise ValueError("FEISHU_APP_ID and FEISHU_APP_SECRET not configured")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{FEISHU_API}/auth/v3/tenant_access_token/internal", json={
            "app_id": app_id,
            "app_secret": app_secret,
        })
        data = resp.json()
        _tenant_token = data.get("tenant_access_token")
        _token_expires = time.time() + data.get("expire", 7200) - 300
        return _tenant_token


async def _send_message(chat_id: str, content: str, msg_type: str = "text"):
    """发送消息到飞书会话"""
    token = await _get_tenant_token()
    async with httpx.AsyncClient(timeout=15) as client:
        if msg_type == "text":
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": content}),
            }
        elif msg_type == "interactive":
            body = {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": content,  # 已经是 JSON 字符串
            }
        else:
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": content}),
            }

        await client.post(
            f"{FEISHU_API}/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )


def _build_card(title: str, content: str, actions: list[dict] = None) -> str:
    """构建飞书交互式消息卡片"""
    elements = [
        {"tag": "markdown", "content": content},
    ]
    if actions:
        buttons = []
        for a in actions:
            buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": a["text"]},
                "type": a.get("type", "default"),
                "value": {"action": a["action"]},
            })
        elements.append({"tag": "action", "actions": buttons})

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "🦀 Powered by CrabRes"}],
    })

    card = {
        "header": {
            "title": {"tag": "plain_text", "content": f"🦀 {title}"},
            "template": "blue",
        },
        "elements": elements,
    }
    return json.dumps(card)


@router.post("/event")
async def feishu_event(request: Request):
    """
    飞书事件订阅回调
    
    处理：
    1. URL 验证（飞书配置时的 challenge）
    2. 消息接收（用户 @机器人 的消息）
    """
    body = await request.json()

    # URL 验证
    if "challenge" in body:
        return JSONResponse({"challenge": body["challenge"]})

    # 事件处理
    event = body.get("event", {})
    event_type = body.get("header", {}).get("event_type", "")

    if event_type == "im.message.receive_v1":
        await _handle_message(event)

    return JSONResponse({"code": 0})


async def _handle_message(event: dict):
    """处理收到的消息"""
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    msg_type = message.get("message_type", "")
    content_str = message.get("content", "{}")

    if msg_type != "text":
        await _send_message(chat_id, "目前只支持文字消息哦 🦀")
        return

    try:
        content = json.loads(content_str)
        text = content.get("text", "").strip()
    except json.JSONDecodeError:
        text = content_str

    # 去掉 @机器人 的标记
    text = text.replace("@_all", "").replace("@CrabRes", "").strip()
    if not text:
        await _send_message(chat_id, "你好！我是 CrabRes 🦀 发送你的产品描述，我帮你做增长分析。")
        return

    # 调用 Agent (via ChannelGateway — shared initialization)
    logger.info(f"Feishu message from {chat_id}: {text[:50]}")
    await _send_message(chat_id, "🔍 正在研究中...")

    try:
        from app.channels import ChannelGateway

        gateway = ChannelGateway(channel="feishu", user_id=chat_id, language="zh")
        response_text = await gateway.process(text)

        if response_text:
            # 如果回复较长，用卡片
            if len(response_text) > 500:
                card = _build_card(
                    "Growth Analysis",
                    response_text[:2000],
                    actions=[
                        {"text": "查看完整计划", "action": "view_plan", "type": "primary"},
                        {"text": "继续对话", "action": "continue", "type": "default"},
                    ],
                )
                await _send_message(chat_id, card, msg_type="interactive")
            else:
                await _send_message(chat_id, f"🦀 {response_text}")
        else:
            await _send_message(chat_id, "🦀 分析完成但结果为空，请再描述一下你的产品？")

    except Exception as e:
        logger.error(f"Feishu agent error: {e}", exc_info=True)
        await _send_message(chat_id, f"❌ 出错了：{str(e)[:200]}\n请稍后再试或换一种方式描述你的产品。")

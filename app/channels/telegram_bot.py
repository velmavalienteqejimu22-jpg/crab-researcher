"""
Telegram Bot — CrabRes Growth Agent on Telegram

Setup:
1. Search @BotFather on Telegram → /newbot → follow prompts
2. Copy Token → set TELEGRAM_BOT_TOKEN in .env
3. Set Webhook:
   curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
     -d "url=https://crab-researcher.onrender.com/api/telegram/webhook"
4. Done! Users can DM the bot or @mention it in groups.
"""

import asyncio
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.channels import ChannelGateway

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["Telegram Bot"])

TELEGRAM_API = "https://api.telegram.org"
BOT_USERNAMES = ["@CrabRes_bot", "@crabres_bot", "@CrabResBot", "@crabresbot"]


async def _send_telegram_message(chat_id: str, text: str, reply_to: int = None):
    """Send a Telegram message (auto-chunks if > 4096 chars)"""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    chunks = ChannelGateway.format_for_channel(text, "telegram")
    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            payload = {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "Markdown",
            }
            if reply_to:
                payload["reply_to_message_id"] = reply_to
            try:
                await client.post(
                    f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json=payload,
                )
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")


async def _send_typing(chat_id: str):
    """Send 'typing...' status indicator"""
    if not settings.TELEGRAM_BOT_TOKEN:
        return
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
        )


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Telegram Webhook endpoint — receives all messages from Telegram"""
    body = await request.json()

    message = body.get("message") or body.get("edited_message")
    if not message:
        return JSONResponse({"ok": True})

    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))
    user_id = str(message.get("from", {}).get("id", ""))
    message_id = message.get("message_id")
    chat_type = message.get("chat", {}).get("type", "private")
    user_lang = message.get("from", {}).get("language_code", "en")

    if not text or not chat_id:
        return JSONResponse({"ok": True})

    # Group chat: only respond when @bot is mentioned
    if chat_type in ("group", "supergroup"):
        mentioned = any(username.lower() in text.lower() for username in BOT_USERNAMES)
        if not mentioned:
            return JSONResponse({"ok": True})
        # Strip @bot_name from message
        for username in BOT_USERNAMES:
            text = text.replace(username, "").replace(username.lower(), "")
        text = text.strip()

    # /start command
    if text == "/start":
        await _send_telegram_message(
            chat_id,
            "🦀 *CrabRes — Your AI Growth Agent*\n\n"
            "Tell me about your product and I'll research your market, "
            "find competitors, and create a growth plan.\n\n"
            "Example: _I built an AI resume optimizer for job seekers_\n\n"
            "Just type your product description to get started!",
        )
        return JSONResponse({"ok": True})

    # /help command
    if text == "/help":
        await _send_telegram_message(
            chat_id,
            "🦀 *CrabRes Commands*\n\n"
            "Just describe your product to start a growth research.\n\n"
            "Tips:\n"
            "• Include your product URL for deeper analysis\n"
            "• Mention your budget for budget-appropriate strategies\n"
            "• Ask follow-up questions to dive deeper\n\n"
            "13 growth experts are ready to help.",
        )
        return JSONResponse({"ok": True})

    # Send typing indicator
    await _send_typing(chat_id)

    # Process asynchronously (avoid Telegram's 60s timeout)
    asyncio.create_task(_handle_message(chat_id, text, user_id, message_id, user_lang))
    return JSONResponse({"ok": True})


async def _handle_message(chat_id: str, text: str, user_id: str, reply_to: int, lang: str):
    """Async message handler — uses ChannelGateway"""
    try:
        # Detect language: zh for Chinese users, en otherwise
        language = "zh" if lang in ("zh", "zh-hans", "zh-hant") else "en"
        gateway = ChannelGateway(channel="telegram", user_id=user_id, language=language)
        result = await gateway.process(text)
        await _send_telegram_message(chat_id, result, reply_to=reply_to)
    except Exception as e:
        logger.error(f"Telegram handler failed: {e}", exc_info=True)
        await _send_telegram_message(chat_id, f"⚠️ Error: {str(e)[:200]}")


@router.get("/health")
async def telegram_health():
    return {
        "status": "ok",
        "bot_configured": bool(settings.TELEGRAM_BOT_TOKEN),
    }


@router.post("/set-webhook")
async def set_webhook():
    """One-click webhook setup for deployment"""
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not configured"}

    webhook_url = "https://crab-researcher.onrender.com/api/telegram/webhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook",
            json={"url": webhook_url},
        )
        return resp.json()

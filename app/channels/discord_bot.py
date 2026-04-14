"""
Discord Bot — CrabRes Growth Agent on Discord

Setup:
1. https://discord.com/developers/applications → New Application
2. Bot → Add Bot → Copy Token → set DISCORD_BOT_TOKEN in .env
3. Enable MESSAGE CONTENT INTENT on Bot page
4. OAuth2 → URL Generator → select bot + applications.commands
5. Bot Permissions: Send Messages, Read Message History, Embed Links, View Channels
6. Invite Bot to your Server with the generated URL
7. Deploy and the bot goes live automatically

Usage: @CrabRes in a channel or DM the bot
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
router = APIRouter(prefix="/discord", tags=["Discord Bot"])

DISCORD_API = "https://discord.com/api/v10"


async def _send_discord_message(channel_id: str, content: str):
    """Send a message to a Discord channel (auto-chunks at 2000 chars)"""
    if not settings.DISCORD_BOT_TOKEN:
        return
    chunks = ChannelGateway.format_for_channel(content, "discord")
    async with httpx.AsyncClient() as client:
        for chunk in chunks:
            await client.post(
                f"{DISCORD_API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
                json={"content": chunk},
            )


@router.post("/webhook")
async def discord_webhook(request: Request):
    """Discord Interactions Endpoint"""
    body = await request.json()

    # Discord verification ping
    if body.get("type") == 1:
        return JSONResponse({"type": 1})

    # Handle slash command interaction
    if body.get("type") == 2:  # APPLICATION_COMMAND
        data = body.get("data", {})
        options = data.get("options", [])
        message = options[0].get("value", "") if options else ""
        user = body.get("member", {}).get("user", {}) or body.get("user", {})
        user_id = user.get("id", "unknown")
        locale = user.get("locale", "en-US")

        if not message:
            return JSONResponse({
                "type": 4,
                "data": {"content": "Please provide a message. Example: `/crabres I built an AI resume tool`"}
            })

        # Respond with DEFERRED to avoid 3s timeout, then process async
        asyncio.create_task(_handle_interaction(body, message, user_id, locale))
        return JSONResponse({"type": 5})

    return JSONResponse({"status": "ok"})


async def _handle_interaction(body: dict, message: str, user_id: str, locale: str):
    """Async interaction handler — uses ChannelGateway"""
    token = body.get("token", "")
    app_id = body.get("application_id", "")

    language = "zh" if locale.startswith("zh") else "en"
    gateway = ChannelGateway(channel="discord", user_id=user_id, language=language)
    result = await gateway.process(message)

    chunks = ChannelGateway.format_for_channel(result, "discord")
    async with httpx.AsyncClient() as client:
        # Edit the deferred response
        await client.patch(
            f"{DISCORD_API}/webhooks/{app_id}/{token}/messages/@original",
            json={"content": chunks[0] if chunks else "No response generated."},
        )
        # Follow-up messages for remaining chunks
        for chunk in chunks[1:]:
            await client.post(
                f"{DISCORD_API}/webhooks/{app_id}/{token}",
                json={"content": chunk},
            )


@router.get("/health")
async def discord_health():
    return {
        "status": "ok",
        "bot_configured": bool(settings.DISCORD_BOT_TOKEN),
    }


@router.post("/register-commands")
async def register_slash_commands():
    """Register the /crabres slash command with Discord API"""
    if not settings.DISCORD_BOT_TOKEN:
        return {"error": "DISCORD_BOT_TOKEN not configured"}

    # Extract application ID from token
    import base64
    try:
        app_id = base64.b64decode(settings.DISCORD_BOT_TOKEN.split(".")[0] + "==").decode()
    except Exception:
        return {"error": "Could not extract app ID from token. Set DISCORD_APP_ID in .env"}

    command = {
        "name": "crabres",
        "description": "Ask CrabRes to research your market and create a growth plan",
        "options": [
            {
                "name": "message",
                "description": "Describe your product or ask a growth question",
                "type": 3,  # STRING
                "required": True,
            }
        ],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DISCORD_API}/applications/{app_id}/commands",
            headers={"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"},
            json=command,
        )
        return resp.json()

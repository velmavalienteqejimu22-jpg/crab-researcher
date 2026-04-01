"""
CrabRes 多触点通知系统

支持：Discord · Slack · Telegram · WhatsApp · 飞书 · 邮件
每个用户可配置多个渠道，通知会同时发到所有已配置的渠道。
"""

import logging
import httpx
from typing import Optional
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class NotificationHub:
    """
    统一通知中心
    
    所有渠道共享同一个接口：send(title, body, urgency)
    内部自动发到所有已配置的渠道。
    """

    def __init__(self):
        self._channels: list[NotificationChannel] = []
        self._setup_channels()

    def _setup_channels(self):
        """根据环境变量自动配置可用渠道"""
        if settings.DISCORD_WEBHOOK_URL:
            self._channels.append(DiscordChannel(settings.DISCORD_WEBHOOK_URL))
        if settings.SLACK_WEBHOOK_URL:
            self._channels.append(SlackChannel(settings.SLACK_WEBHOOK_URL))
        if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
            self._channels.append(TelegramChannel(settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID))
        if settings.FEISHU_WEBHOOK_URL:
            self._channels.append(FeishuChannel(settings.FEISHU_WEBHOOK_URL))

        logger.info(f"NotificationHub: {len(self._channels)} channels configured "
                     f"({', '.join(c.name for c in self._channels) or 'none'})")

    @property
    def has_channels(self) -> bool:
        return len(self._channels) > 0

    async def send(self, title: str, body: str, urgency: str = "normal"):
        """
        发送通知到所有已配置渠道
        
        urgency: "low" | "normal" | "high" | "critical"
        """
        if not self._channels:
            logger.debug(f"No notification channels configured. Skipping: {title}")
            return

        for channel in self._channels:
            try:
                await channel.send(title, body, urgency)
            except Exception as e:
                logger.error(f"Notification failed on {channel.name}: {e}")

    async def send_discovery(self, discovery: dict):
        """发送 Daemon 发现的通知"""
        dtype = discovery.get("type", "")
        if dtype == "competitor_change":
            await self.send(
                title=f"🔍 Competitor Update: {discovery.get('competitor', '')}",
                body=discovery.get("change", ""),
                urgency="normal",
            )
        elif dtype == "social_mention":
            await self.send(
                title=f"💬 New discussion on {discovery.get('platform', '')}",
                body=f"{discovery.get('title', '')}\n{discovery.get('url', '')}",
                urgency="low",
            )
        elif dtype == "calendar_due":
            await self.send(
                title=f"📅 Content due today",
                body=f"{discovery.get('title', '')} on {discovery.get('channel', '')}",
                urgency="high",
            )
        else:
            await self.send(
                title="🦀 CrabRes Discovery",
                body=str(discovery),
                urgency="normal",
            )


class NotificationChannel:
    """通知渠道基类"""
    name: str = "unknown"

    async def send(self, title: str, body: str, urgency: str = "normal"):
        raise NotImplementedError


class DiscordChannel(NotificationChannel):
    name = "Discord"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, title: str, body: str, urgency: str = "normal"):
        color = {"low": 0x94A3B8, "normal": 0x0EA5E9, "high": 0xF59E0B, "critical": 0xEF4444}.get(urgency, 0x0EA5E9)
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(self.webhook_url, json={
                "embeds": [{
                    "title": title,
                    "description": body[:2000],
                    "color": color,
                    "footer": {"text": "CrabRes Growth Agent"},
                }]
            })


class SlackChannel(NotificationChannel):
    name = "Slack"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, title: str, body: str, urgency: str = "normal"):
        emoji = {"low": "ℹ️", "normal": "🦀", "high": "⚠️", "critical": "🚨"}.get(urgency, "🦀")
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(self.webhook_url, json={
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} {title}"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": body[:2000]}},
                    {"type": "context", "elements": [{"type": "mrkdwn", "text": "via CrabRes"}]},
                ]
            })


class TelegramChannel(NotificationChannel):
    name = "Telegram"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, title: str, body: str, urgency: str = "normal"):
        text = f"*{title}*\n\n{body}"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text[:4000], "parse_mode": "Markdown"},
            )


class FeishuChannel(NotificationChannel):
    name = "Feishu"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, title: str, body: str, urgency: str = "normal"):
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(self.webhook_url, json={
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"🦀 {title}"},
                        "template": {"low": "grey", "normal": "blue", "high": "yellow", "critical": "red"}.get(urgency, "blue"),
                    },
                    "elements": [
                        {"tag": "markdown", "content": body[:2000]},
                        {"tag": "note", "elements": [{"tag": "plain_text", "content": "CrabRes Growth Agent"}]},
                    ],
                },
            })

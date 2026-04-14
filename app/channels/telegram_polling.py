"""
Telegram Long Polling — 不依赖公网 Webhook 的 Bot 运行模式

解决的核心问题：
- Webhook 模式需要公网 HTTPS URL（本地开发/内网部署用不了）
- Long Polling 主动拉取消息，任何环境都能跑

用法：
1. 在 .env 设置 TELEGRAM_BOT_TOKEN
2. 启动服务，TelegramPoller 自动开始拉取消息
3. 用户在 Telegram 发消息 → Bot 实时响应
"""

import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import get_settings
from app.channels import ChannelGateway

settings = get_settings()
logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
BOT_USERNAMES = ["@CrabRes_bot", "@crabres_bot", "@CrabResBot", "@crabresbot"]


class TelegramPoller:
    """
    Telegram Long Polling 客户端

    比 Webhook 的优势：
    - 不需要公网 IP / HTTPS
    - 本地开发、内网部署都能用
    - 自动重连，不怕网络波动
    """

    POLL_TIMEOUT = 30  # 长轮询超时（秒）
    ERROR_BACKOFF = 5  # 出错后等待（秒）

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._offset = 0  # Telegram update offset
        self._message_count = 0

    async def start(self):
        """启动长轮询"""
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.info("📱 Telegram Bot: no token configured, skipping polling")
            return

        if self._running:
            return

        self._running = True

        # 先删除可能存在的 Webhook（Webhook 和 Polling 互斥）
        await self._delete_webhook()

        # 获取 Bot 信息
        bot_info = await self._get_me()
        if bot_info:
            logger.info(f"📱 Telegram Bot: @{bot_info.get('username', '?')} ({bot_info.get('first_name', '')})")

        self._task = asyncio.create_task(self._poll_loop())
        logger.info("📱 Telegram Long Polling started")

    async def stop(self):
        """停止长轮询"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"📱 Telegram Polling stopped (processed {self._message_count} messages)")

    async def _poll_loop(self):
        """主轮询循环"""
        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    # 更新 offset（确认已处理）
                    self._offset = update.get("update_id", 0) + 1
                    # 异步处理消息（不阻塞轮询）
                    asyncio.create_task(self._handle_update(update))
            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                # 长轮询超时是正常的（没有新消息）
                continue
            except Exception as e:
                logger.error(f"📱 Telegram polling error: {e}")
                await asyncio.sleep(self.ERROR_BACKOFF)

    async def _get_updates(self) -> list:
        """拉取新消息（长轮询）"""
        async with httpx.AsyncClient(timeout=self.POLL_TIMEOUT + 10) as client:
            resp = await client.get(
                f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": self.POLL_TIMEOUT,
                    "allowed_updates": '["message", "callback_query"]',
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", [])

    async def _handle_update(self, update: dict):
        """处理单条 update"""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))
        user_id = str(message.get("from", {}).get("id", ""))
        message_id = message.get("message_id")
        chat_type = message.get("chat", {}).get("type", "private")
        user_lang = message.get("from", {}).get("language_code", "en")
        user_name = message.get("from", {}).get("first_name", "")

        if not text or not chat_id:
            return

        # 群聊：只响应 @bot
        if chat_type in ("group", "supergroup"):
            mentioned = any(username.lower() in text.lower() for username in BOT_USERNAMES)
            if not mentioned:
                return
            for username in BOT_USERNAMES:
                text = text.replace(username, "").replace(username.lower(), "")
            text = text.strip()

        self._message_count += 1
        logger.info(f"📱 Telegram [{user_name}]: {text[:80]}...")

        # /start 命令
        if text == "/start":
            await self._send(
                chat_id,
                "🦀 *CrabRes — Your AI Growth Agent*\n\n"
                "Tell me about your product and I'll research your market, "
                "find competitors, and create a growth plan.\n\n"
                "Example: _I built an AI resume optimizer for job seekers_\n\n"
                "Just type your product description to get started!",
            )
            return

        # /help 命令
        if text == "/help":
            await self._send(
                chat_id,
                "🦀 *CrabRes Commands*\n\n"
                "/start — Begin a new session\n"
                "/help — Show this message\n"
                "/status — Check agent status\n\n"
                "Just describe your product to start a growth research.\n"
                "13 growth experts are ready to help.",
            )
            return

        # /status 命令
        if text == "/status":
            await self._send(
                chat_id,
                f"🦀 *CrabRes Status*\n\n"
                f"• Messages processed: {self._message_count}\n"
                f"• Mode: Long Polling\n"
                f"• Status: Running ✅",
            )
            return

        # 发送 typing 状态
        await self._send_typing(chat_id)

        # 调用 Agent
        try:
            language = "zh" if user_lang in ("zh", "zh-hans", "zh-hant") else "en"
            gateway = ChannelGateway(channel="telegram", user_id=user_id, language=language)
            result = await gateway.process(text)
            await self._send(chat_id, result, reply_to=message_id)
        except Exception as e:
            logger.error(f"📱 Telegram handler failed: {e}", exc_info=True)
            await self._send(chat_id, f"⚠️ Error: {str(e)[:200]}")

    async def _send(self, chat_id: str, text: str, reply_to: int = None):
        """发送消息（自动分片）"""
        chunks = ChannelGateway.format_for_channel(text, "telegram")
        async with httpx.AsyncClient(timeout=15) as client:
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
                    # Markdown 解析失败时降级为纯文本
                    payload.pop("parse_mode", None)
                    try:
                        await client.post(
                            f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                            json=payload,
                        )
                    except Exception as e2:
                        logger.error(f"📱 Telegram send failed: {e2}")

    async def _send_typing(self, chat_id: str):
        """发送 typing 状态"""
        async with httpx.AsyncClient(timeout=5) as client:
            try:
                await client.post(
                    f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                )
            except Exception:
                pass

    async def _delete_webhook(self):
        """删除已有 Webhook（Webhook 和 Polling 互斥）"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook",
                    json={"drop_pending_updates": False},
                )
                data = resp.json()
                if data.get("result"):
                    logger.info("📱 Telegram: existing webhook deleted (switching to polling)")
        except Exception as e:
            logger.warning(f"📱 Telegram: failed to delete webhook: {e}")

    async def _get_me(self) -> Optional[dict]:
        """获取 Bot 信息"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{TELEGRAM_API}/bot{settings.TELEGRAM_BOT_TOKEN}/getMe",
                )
                resp.raise_for_status()
                return resp.json().get("result")
        except Exception as e:
            logger.error(f"📱 Telegram getMe failed: {e}")
            return None

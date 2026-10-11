from __future__ import annotations

import logging
from telegram.ext import Application
from telegram.request import HTTPXRequest
from bot.bybit_client import BybitClient
from bot.config import AppConfig
from bot.trader import Trader

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self, config: AppConfig, client: BybitClient, trader: Trader) -> None:
        self.config = config
        self.client = client
        self.trader = trader

        tg = config.telegram
        builder = Application.builder().token(tg.bot_token)

        # Настройка прокси (исправлено с proxy_url на proxy)
        if tg.proxy_host and tg.proxy_port:
            if tg.proxy_username and tg.proxy_password:
                proxy_url = f"http://{tg.proxy_username}:{tg.proxy_password}@{tg.proxy_host}:{tg.proxy_port}"
            else:
                proxy_url = f"http://{tg.proxy_host}:{tg.proxy_port}"
            request = HTTPXRequest(proxy=proxy_url)  # <- Исправлено здесь
            builder.request(request)

        self.app = builder.build()

    async def send_startup_notification(self) -> None:
        chat_id = self.config.telegram.allowed_user_id
        if not chat_id:
            return
        text = self.trader.format_startup_message()
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            logger.info("Startup configuration sent to Telegram.")
        except Exception as e:
            logger.error(f"Failed to send startup message to Telegram: {e}")

    async def send_message(self, text: str) -> None:
        chat_id = self.config.telegram.allowed_user_id
        if not chat_id or not text:
            return
        try:
            await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send message to Telegram: {e}")

    async def run_polling(self) -> None:
        await self.app.initialize()
        await self.app.start()
        await self.send_startup_notification()
        await self.app.updater.start_polling()
        logger.info("Telegram bot polling started.")
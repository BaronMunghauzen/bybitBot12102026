from __future__ import annotations

import logging
from telegram.ext import Application, ApplicationBuilder
from bot.config import AppConfig

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(
        self,
        token: str,
        allowed_user_id: int,
        proxy_host: str = "",
        proxy_port: int = 0,
        proxy_username: str = "",
        proxy_password: str = "",
    ) -> None:
        self.token = token
        self.allowed_user_id = allowed_user_id
        
        builder = ApplicationBuilder().token(self.token)
        
        if proxy_host and proxy_port:
            proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}" if proxy_username else f"http://{proxy_host}:{proxy_port}"
            builder.proxy(proxy_url).get_updates_proxy(proxy_url)
            
        self.application: Application = builder.build()

    @classmethod
    def from_app_config(cls, config: AppConfig) -> TelegramService:
        t = config.telegram
        return cls(
            token=t.bot_token,
            allowed_user_id=t.allowed_user_id,
            proxy_host=t.proxy_host,
            proxy_port=t.proxy_port,
            proxy_username=t.proxy_username,
            proxy_password=t.proxy_password,
        )

    async def initialize(self) -> None:
        await self.application.initialize()
        await self.application.start()

    async def send_message(self, text: str) -> None:
        try:
            await self.application.bot.send_message(
                chat_id=self.allowed_user_id,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def shutdown(self) -> None:
        try:
            await self.application.stop()
            await self.application.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down Telegram service: {e}")
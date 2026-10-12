from __future__ import annotations

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.config import AppConfig
from bot.telegram_bot import TelegramService
from bot.trader import Trader

logger = logging.getLogger(__name__)

class DailyScheduler:
    def __init__(self, config: AppConfig, trader: Trader, telegram: TelegramService) -> None:
        self.config = config
        self.trader = trader
        self.telegram = telegram
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        # Запуск каждый день в 23:59:30 UTC (за 30 секунд до закрытия дневной свечи в 00:00 UTC)
        self.scheduler.add_job(
            self._job_daily_close,
            "cron",
            hour=23,
            minute=59,
            second=30,
            id="daily_close_trading_job",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Scheduler started. Daily job set at 23:59:30 UTC.")

    async def _job_daily_close(self) -> None:
        logger.info("Running daily candle close algorithm...")
        try:
            messages = await asyncio.to_thread(self.trader.process_trading_logic, None)
            for msg in messages:
                await self.telegram.send_message(msg)
        except Exception as e:
            err_msg = f"❌ **Ошибка в ежедневном алгоритме:**\n`{type(e).__name__}: {e}`"
            logger.exception("Error in daily job")
            await self.telegram.send_message(err_msg)

    def shutdown(self) -> None:
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown.")
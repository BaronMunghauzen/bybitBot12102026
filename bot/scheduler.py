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
        t_conf = self.config.trading
        
        # 1. Часовой алгоритм (пункты 4-5)
        self.scheduler.add_job(
            self._job_hourly,
            "cron",
            minute=t_conf.schedule_minute,
            second=t_conf.schedule_second,
            id="hourly_trading_job",
            replace_existing=True,
        )

        # 2. Минутный мониторинг (пункт 6 и далее)
        self.scheduler.add_job(
            self._job_minute,
            "cron",
            second=0,
            id="minute_monitoring_job",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            f"Scheduler started. Hourly job set at :59:30. Minute job set every minute."
        )

    async def _job_hourly(self) -> None:
        logger.info("Running hourly trading check...")
        try:
            messages = await asyncio.to_thread(self.trader.run_hourly_check)
            for msg in messages:
                await self.telegram.send_message(msg)
        except Exception as e:
            err_msg = f"❌ **Ошибка в часовом алгоритме:**\n`{type(e).__name__}: {e}`"
            logger.exception("Error in hourly job")
            await self.telegram.send_message(err_msg)

    async def _job_minute(self) -> None:
        logger.info("Running minute monitoring check...")
        try:
            messages = await asyncio.to_thread(self.trader.run_minute_check)
            for msg in messages:
                await self.telegram.send_message(msg)
        except Exception as e:
            err_msg = f"❌ **Ошибка в минутном мониторинге:**\n`{type(e).__name__}: {e}`"
            logger.exception("Error in minute job")
            await self.telegram.send_message(err_msg)

    def shutdown(self) -> None:
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown.")
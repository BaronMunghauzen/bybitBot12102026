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
        s_conf = self.config.scheduler
        
        # 1. Суточный алгоритм
        self.scheduler.add_job(
            self._job_daily_close,
            "cron",
            hour=s_conf.hour,
            minute=s_conf.minute,
            second=s_conf.second,
            timezone=s_conf.timezone,
            id="daily_close_trading_job",
            replace_existing=True,
        )

        # 2. Часовой алгоритм
        self.scheduler.add_job(
            self._job_hourly_close,
            "cron",
            minute=s_conf.hourly_minute,
            second=s_conf.hourly_second,
            timezone=s_conf.timezone,
            id="hourly_trading_job",
            replace_existing=True,
        )

        # 3. Ежеминутный мониторинг висящих лимитных ордеров
        self.scheduler.add_job(
            self._job_minute_check,
            "cron",
            second=0,
            timezone=s_conf.timezone,
            id="minute_monitoring_job",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(
            f"Scheduler started. Daily job set at {s_conf.hour:02d}:{s_conf.minute:02d}:{s_conf.second:02d} ({s_conf.timezone}). "
            f"Hourly job set at minute {s_conf.hourly_minute}, second {s_conf.hourly_second} ({s_conf.timezone}). "
            f"Minute monitoring enabled."
        )

    async def _job_daily_close(self) -> None:
        logger.info("Running daily candle close algorithm...")
        try:
            messages = await asyncio.to_thread(self.trader.process_trading_logic, None)
            for msg in messages:
                await self.telegram.send_message(msg)
        except Exception as e:
            err_msg = f"❌ **Ошибка в суточном алгоритме:**\n`{type(e).__name__}: {e}`"
            logger.exception("Error in daily job")
            await self.telegram.send_message(err_msg)

    async def _job_hourly_close(self) -> None:
        logger.info("Running hourly candle close algorithm...")
        try:
            messages = await asyncio.to_thread(self.trader.process_hourly_trading_logic)
            for msg in messages:
                await self.telegram.send_message(msg)
        except Exception as e:
            err_msg = f"❌ **Ошибка в часовом алгоритме:**\n`{type(e).__name__}: {e}`"
            logger.exception("Error in hourly job")
            await self.telegram.send_message(err_msg)

    async def _job_minute_check(self) -> None:
        try:
            await asyncio.to_thread(self.trader.process_minute_monitoring)
        except Exception as e:
            logger.exception("Error in minute monitoring job")

    def shutdown(self) -> None:
        self.scheduler.shutdown()
        logger.info("Scheduler shutdown.")
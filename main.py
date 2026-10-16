from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from bot.config import load_config, setup_logging
from bot.bybit_client import BybitClient
from bot.telegram_bot import TelegramService
from bot.trader import Trader
from bot.scheduler import DailyScheduler

logger = logging.getLogger(__name__)

async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Bybit Trading Bot")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"), help="Path to config file")
    parser.add_argument("--test-signal", type=str, choices=["long", "short"], help="Test signal for daily strategy")
    parser.add_argument("--test-hourly-signal", type=str, choices=["long", "short"], help="Test signal for hourly strategy")
    args = parser.parse_args()

    config = load_config(args.config)
    setup_logging(config.logging.level)

    client = BybitClient.from_app_config(config)
    trader = Trader(config, client)

    # Тесты выполняются сразу, не дожидаясь инициализации Telegram
    if args.test_hourly_signal:
        logger.info(f"Running test hourly signal: {args.test_hourly_signal.upper()}")
        messages = await asyncio.to_thread(trader.process_hourly_trading_logic, args.test_hourly_signal)
        for msg in messages:
            logger.info(msg)
            print(msg)
        return

    if args.test_signal:
        logger.info(f"Running test daily signal: {args.test_signal.upper()}")
        messages = await asyncio.to_thread(trader.process_trading_logic, args.test_signal)
        for msg in messages:
            logger.info(msg)
            print(msg)
        return

    # Штатный запуск бота с Telegram и шедулером
    telegram = TelegramService.from_app_config(config)
    await telegram.initialize()
    startup_msg = trader.format_startup_message()
    await telegram.send_message(startup_msg)

    scheduler = DailyScheduler(config, trader, telegram)
    scheduler.start()

    logger.info("Telegram bot polling started successfully.")
    
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        scheduler.shutdown()
        await telegram.shutdown()

def main() -> None:
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")

if __name__ == "__main__":
    main()
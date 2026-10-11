#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from bot.bybit_client import BybitClient
from bot.config import DEFAULT_CONFIG_PATH, load_config, setup_logging
from bot.scheduler import DailyScheduler
from bot.telegram_bot import TelegramService
from bot.trader import Trader

logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bybit futures trading bot")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml",
    )
    return parser.parse_args()

def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

async def main_async() -> None:
    args = parse_args()
    config = load_config(args.config)
    setup_logging(config.logging.level)

    client = BybitClient.from_app_config(config)
    trader = Trader(config, client)
    telegram = TelegramService(config, client, trader)
    scheduler = DailyScheduler(config, trader, telegram)

    # Запускаем шедулер задач
    scheduler.start()

    try:
        # Инициализируем и запускаем Telegram приложение и пуллет
        await telegram.app.initialize()
        await telegram.app.start()
        await telegram.send_startup_notification()
        await telegram.app.updater.start_polling()
        logger.info("Telegram bot polling started successfully.")

        # Удерживаем приложение работающим бесконечно
        while True:
            await asyncio.sleep(3600)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down gracefully...")
    finally:
        scheduler.shutdown()
        await telegram.app.updater.stop()
        await telegram.app.stop()
        await telegram.app.shutdown()
        logger.info("Bot stopped.")

def main() -> None:
    _configure_stdout()
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)

if __name__ == "__main__":
    main()
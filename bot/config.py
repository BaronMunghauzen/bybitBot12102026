from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")

@dataclass
class BybitConfig:
    api_key: str
    api_secret: str
    mode: str = "demo"

@dataclass
class TradingConfig:
    category: str = "linear"
    settle_coin: str = "USDT"
    leverage: int = 50
    symbols: List[str] = field(default_factory=lambda: ["TAOUSDT"])
    initial_size_mult: float = 10.0
    take_profit_pct: float = 0.8
    max_add_orders: int = 1
    hourly_enabled: bool = True
    hourly_take_profit_pct: float = 0.5
    hourly_stop_loss_pct: float = 1.0

@dataclass
class SchedulerConfig:
    hour: int = 23
    minute: int = 59
    second: int = 30
    timezone: str = "UTC"
    hourly_minute: int = 59
    hourly_second: int = 30

@dataclass
class TelegramConfig:
    bot_token: str
    allowed_user_id: int
    proxy_host: str = ""
    proxy_port: int = 0
    proxy_username: str = ""
    proxy_password: str = ""

@dataclass
class LoggingConfig:
    level: str = "INFO"

@dataclass
class AppConfig:
    bybit: BybitConfig
    trading: TradingConfig
    scheduler: SchedulerConfig
    telegram: TelegramConfig
    logging: LoggingConfig

def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    bybit_raw = raw.get("bybit", {})
    trading_raw = raw.get("trading", {})
    scheduler_raw = raw.get("scheduler", {})
    telegram_raw = raw.get("telegram", {})
    logging_raw = raw.get("logging", {})

    return AppConfig(
        bybit=BybitConfig(
            api_key=bybit_raw.get("api_key", ""),
            api_secret=bybit_raw.get("api_secret", ""),
            mode=bybit_raw.get("mode", "demo"),
        ),
        trading=TradingConfig(
            category=trading_raw.get("category", "linear"),
            settle_coin=trading_raw.get("settle_coin", "USDT"),
            leverage=int(trading_raw.get("leverage", 50)),
            symbols=trading_raw.get("symbols", ["TAOUSDT"]),
            initial_size_mult=float(trading_raw.get("initial_size_mult", 10.0)),
            take_profit_pct=float(trading_raw.get("take_profit_pct", 0.8)),
            max_add_orders=int(trading_raw.get("max_add_orders", 1)),
            hourly_enabled=bool(trading_raw.get("hourly_enabled", True)),
            hourly_take_profit_pct=float(trading_raw.get("hourly_take_profit_pct", 0.5)),
            hourly_stop_loss_pct=float(trading_raw.get("hourly_stop_loss_pct", 1.0)),
        ),
        scheduler=SchedulerConfig(
            hour=int(scheduler_raw.get("hour", 23)),
            minute=int(scheduler_raw.get("minute", 59)),
            second=int(scheduler_raw.get("second", 30)),
            timezone=str(scheduler_raw.get("timezone", "UTC")),
            hourly_minute=int(scheduler_raw.get("hourly_minute", 59)),
            hourly_second=int(scheduler_raw.get("hourly_second", 30)),
        ),
        telegram=TelegramConfig(
            bot_token=telegram_raw.get("bot_token", ""),
            allowed_user_id=int(telegram_raw.get("allowed_user_id", 0)),
            proxy_host=telegram_raw.get("proxy_host", ""),
            proxy_port=int(telegram_raw.get("proxy_port", 0)),
            proxy_username=telegram_raw.get("proxy_username", ""),
            proxy_password=telegram_raw.get("proxy_password", ""),
        ),
        logging=LoggingConfig(
            level=logging_raw.get("level", "INFO"),
        ),
    )

def setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
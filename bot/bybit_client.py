from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pybit.unified_trading import HTTP
from bot.config import AppConfig

logger = logging.getLogger(__name__)

class BybitClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, demo: bool = False) -> None:
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            demo=demo,
        )

    @classmethod
    def from_app_config(cls, config: AppConfig) -> BybitClient:
        mode = config.bybit.mode.lower()
        testnet = mode == "testnet"
        demo = mode == "demo"
        return cls(
            api_key=config.bybit.api_key,
            api_secret=config.bybit.api_secret,
            testnet=testnet,
            demo=demo,
        )

    def get_wallet_balance(self, coin: str = "USDT") -> float:
        resp = self.session.get_wallet_balance(
            accountType="UNIFIED",
            coin=coin,
        )
        result = resp.get("result", {})
        list_acc = result.get("list", [])
        if not list_acc:
            return 0.0
        coins = list_acc[0].get("coin", [])
        for c in coins:
            if c.get("coin") == coin:
                return float(c.get("equity", 0.0) or 0.0)
        return 0.0

    def get_ticker_price(self, symbol: str) -> float:
        resp = self.session.get_tickers(
            category="linear",
            symbol=symbol,
        )
        list_t = resp.get("result", {}).get("list", [])
        if list_t:
            return float(list_t[0].get("lastPrice", 0.0))
        return 0.0

    def get_klines(self, symbol: str, interval: str = "60", limit: int = 600) -> List[Dict[str, Any]]:
        resp = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        list_k = resp.get("result", {}).get("list", [])
        list_k.reverse() # Chronological order
        return list_k

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
            return True
        except Exception as e:
            if "110043" in str(e): # Already set
                return True
            raise

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        resp = self.session.get_positions(
            category="linear",
            symbol=symbol,
        )
        list_p = resp.get("result", {}).get("list", [])
        for p in list_p:
            if float(p.get("size", 0.0) or 0.0) > 0:
                return p
        return None

    def get_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        resp = self.session.get_open_orders(
            category="linear",
            symbol=symbol,
        )
        return resp.get("result", {}).get("list", [])

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None,
        stop_loss: Optional[str] = None,
        reduce_only: bool = False,
    ) -> Optional[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "reduceOnly": reduce_only,
        }
        if order_type == "Limit" and price:
            kwargs["price"] = str(price)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)

        resp = self.session.place_order(**kwargs)
        return resp.get("result")

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        self.session.cancel_order(
            category="linear",
            symbol=symbol,
            orderId=order_id,
        )
        return True

    def cancel_all_orders(self, symbol: str) -> bool:
        self.session.cancel_all_orders(
            category="linear",
            symbol=symbol,
        )
        return True

    def amend_order_trading_stop(
        self,
        symbol: str,
        stop_loss: Optional[str] = None,
        trailing_stop: Optional[str] = None,
        active_price: Optional[str] = None,
    ) -> bool:
        kwargs: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
        }
        if stop_loss is not None:
            kwargs["stopLoss"] = str(stop_loss)
        if trailing_stop is not None:
            kwargs["trailingStop"] = str(trailing_stop)
        if active_price is not None:
            kwargs["activePrice"] = str(active_price)

        self.session.set_trading_stop(**kwargs)
        return True
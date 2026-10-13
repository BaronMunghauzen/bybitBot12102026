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
                return float(c.get("walletBalance", 0.0) or c.get("equity", 0.0) or 0.0)
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

    def get_klines(self, symbol: str, interval: str = "D", limit: int = 5) -> List[Dict[str, Any]]:
        resp = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        list_k = resp.get("result", {}).get("list", [])
        list_k.reverse()
        return list_k

    def get_qty_step_and_precision(self, symbol: str) -> tuple[int, float]:
        try:
            resp = self.session.get_instruments_info(
                category="linear",
                symbol=symbol,
            )
            list_i = resp.get("result", {}).get("list", [])
            if list_i:
                lot_filter = list_i[0].get("lotSizeFilter", {})
                step_str = lot_filter.get("qtyStep", "0.01")
                qty_step = float(step_str)
                if "." in step_str:
                    decimals = len(step_str.rstrip("0").split(".")[1])
                else:
                    decimals = 0
                return decimals, qty_step
        except Exception as e:
            logger.warning(f"Failed to fetch instrument info for {symbol}: {e}")
        return 2, 0.01

    def set_margin_mode_and_leverage(self, symbol: str, leverage: int) -> None:
        try:
            self.session.switch_margin_mode(
                category="linear",
                symbol=symbol,
                tradeMode=1,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
        except Exception as e:
            if any(err in str(e) for err in ["110026", "10032", "already", "not supported"]):
                pass
            else:
                logger.warning(f"Margin mode switch notice for {symbol}: {e}")

        try:
            self.session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=str(leverage),
                sellLeverage=str(leverage),
            )
        except Exception as e:
            if "110043" not in str(e):
                logger.warning(f"Leverage set notice for {symbol}: {e}")

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

    def has_add_been_executed(self, symbol: str, pos_side: str, pos_created_time: int) -> bool:
        try:
            resp = self.session.get_order_history(
                category="linear",
                symbol=symbol,
                limit=15,
            )
            orders = resp.get("result", {}).get("list", [])
            filled_entries = 0
            for o in orders:
                if o.get("orderStatus") == "Filled" and o.get("side") == pos_side:
                    reduce_only = o.get("reduceOnly", False)
                    is_reduce = (reduce_only.lower() == "true") if isinstance(reduce_only, str) else bool(reduce_only)
                    
                    if not is_reduce:
                        order_time = int(o.get("createdTime", 0))
                        if order_time >= pos_created_time - 5000:
                            filled_entries += 1
            return filled_entries >= 2
        except Exception as e:
            logger.warning(f"Failed to check order history for add status on {symbol}: {e}")
            return False

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None,
        take_profit: Optional[str] = None,
        stop_loss: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kwargs: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
        }
        if order_type == "Limit":
            if price:
                kwargs["price"] = str(price)
            kwargs["timeInForce"] = "GTC"
        elif order_type == "Market":
            kwargs["timeInForce"] = "IOC"

        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)

        resp = self.session.place_order(**kwargs)
        return resp.get("result")

    def amend_order_trading_stop(
        self,
        symbol: str,
        take_profit: Optional[str] = None,
    ) -> bool:
        kwargs: Dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
        }
        if take_profit is not None:
            kwargs["takeProfit"] = str(take_profit)

        self.session.set_trading_stop(**kwargs)
        return True
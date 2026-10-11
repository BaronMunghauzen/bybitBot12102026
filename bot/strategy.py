from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from bot.indicators import calculate_sma

logger = logging.getLogger(__name__)

class Strategy:
    def __init__(self, config) -> None:
        self.config = config.trading

    def calculate_mas(self, closes: List[float], current_price: float) -> Tuple[float, float, float, float]:
        fast_period = self.config.ma_fast
        slow_period = self.config.ma_slow

        if len(closes) < slow_period:
            raise ValueError(f"Not enough klines: need at least {slow_period}, got {len(closes)}")

        closes_curr = closes[:-1] + [current_price]
        fast_curr = calculate_sma(closes_curr, fast_period)
        slow_curr = calculate_sma(closes_curr, slow_period)

        fast_prev = calculate_sma(closes, fast_period)
        slow_prev = calculate_sma(closes, slow_period)

        return fast_curr, slow_curr, fast_prev, slow_prev

    def check_signal(self, fast_curr: float, slow_curr: float, fast_prev: float, slow_prev: float) -> Optional[str]:
        if fast_prev <= slow_prev and fast_curr > slow_curr:
            return "Buy"
        elif fast_prev >= slow_prev and fast_curr < slow_curr:
            return "Sell"
        return None

    def calculate_initial_stop_loss(
        self, side: str, entry_price: float, short_ma: float
    ) -> float:
        pct = self.config.initial_stop_loss_pct / 100.0
        if side == "Buy":
            sl_pct_price = entry_price * (1.0 - pct)
            sl_ma_price = short_ma * (1.0 - 0.001)
            return max(sl_pct_price, sl_ma_price)
        else:
            sl_pct_price = entry_price * (1.0 + pct)
            sl_ma_price = short_ma * (1.0 + 0.001)
            return min(sl_pct_price, sl_ma_price)

    def calculate_add_orders_prices(
        self, side: str, entry_price: float, initial_sl: float, max_adds: int
    ) -> List[float]:
        sl_distance = abs(entry_price - initial_sl)
        prices = []
        for i in range(1, max_adds + 1):
            mult = 1 + i # 1st add: 2*sl, 2nd: 3*sl, etc.
            if side == "Buy":
                p = entry_price + (mult * sl_distance)
            else:
                p = entry_price - (mult * sl_distance)
            prices.append(round(p, 4))
        return prices

    def calculate_updated_stop_loss(
        self, side: str, avg_entry_price: float, filled_adds_count: int
    ) -> Optional[float]:
        if filled_adds_count <= 0:
            return None
        pct = (filled_adds_count * 0.3) / 100.0
        if side == "Buy":
            return avg_entry_price * (1.0 + pct)
        else:
            return avg_entry_price * (1.0 - pct)
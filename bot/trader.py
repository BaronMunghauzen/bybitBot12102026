from __future__ import annotations

import logging
from typing import List, Optional
from bot.bybit_client import BybitClient

logger = logging.getLogger(__name__)

class Trader:
    def __init__(self, config, client: BybitClient) -> None:
        self.config = config
        self.client = client

    def format_startup_message(self) -> str:
        t = self.config.trading
        return (
            "🤖 **Торговый бот запущен (Свеча + MA фильтры + Усреднение + Очистка лимиток)**\n\n"
            "⚙️ **Параметры:**\n"
            f"• Плечо: {t.leverage}x (Изолированная маржа)\n"
            f"• Список активов: {', '.join(t.symbols)}\n"
            f"• Часовой ТП: {t.hourly_take_profit_pct}% | Стоп-лосс: {t.hourly_stop_loss_pct}%\n"
            f"• Просадка для лимитного докупа: {t.hourly_add_order_drop_pct}%\n"
            f"• MA фильтры: Быстрая MA={t.ma_fast}, Длинная MA={t.ma_slow}\n"
        )

    def _calculate_sma(self, closes: List[float], period: int) -> float:
        if len(closes) < period:
            return sum(closes) / len(closes) if closes else 0.0
        return sum(closes[-period:]) / period

    def process_trading_logic(self, test_signal: Optional[str] = None) -> List[str]:
        """Суточный алгоритм"""
        messages = []
        t_conf = self.config.trading
        equity = self.client.get_wallet_balance(t_conf.settle_coin)
        if equity <= 0:
            equity = 100.0

        for symbol in t_conf.symbols:
            self.client.set_margin_mode_and_leverage(symbol, t_conf.leverage)
            pos = self.client.get_position(symbol)
            last_price = self.client.get_ticker_price(symbol)
            if last_price <= 0:
                continue

            decimals, qty_step = self.client.get_qty_step_and_precision(symbol)
            is_bullish, is_bearish = False, False

            if test_signal:
                if test_signal.lower() == "long":
                    is_bullish = True
                elif test_signal.lower() == "short":
                    is_bearish = True
            else:
                klines = self.client.get_klines(symbol, interval="D", limit=2)
                if not klines:
                    continue
                candle = klines[-1]
                is_bullish = float(candle[4]) > float(candle[1])
                is_bearish = float(candle[4]) < float(candle[1])

            notional = equity * t_conf.initial_size_mult
            qty_raw = notional / last_price
            qty_val = round(round(qty_raw / qty_step) * qty_step, decimals) if qty_step > 0 else round(qty_raw, decimals)
            qty = str(int(qty_val)) if decimals == 0 else f"{qty_val:.{decimals}f}"

            if pos is None:
                if is_bullish:
                    tp_price = last_price * (1.0 + t_conf.take_profit_pct / 100.0)
                    if self.client.place_order(symbol=symbol, side="Buy", order_type="Market", qty=qty, take_profit=str(round(tp_price, 4))):
                        messages.append(f"🟢 **[Суточный] Лонг ({symbol})** | ТП: {round(tp_price, 4)}")
                elif is_bearish:
                    tp_price = last_price * (1.0 - t_conf.take_profit_pct / 100.0)
                    if self.client.place_order(symbol=symbol, side="Sell", order_type="Market", qty=qty, take_profit=str(round(tp_price, 4))):
                        messages.append(f"🔴 **[Суточный] Шорт ({symbol})** | ТП: {round(tp_price, 4)}")
            else:
                pos_side = pos.get("side")
                already_added = self.client.has_add_been_executed(symbol, pos_side, int(pos.get("createdTime", 0)))
                if pos_side == "Buy" and is_bullish and not already_added:
                    if self.client.place_order(symbol=symbol, side="Buy", order_type="Market", qty=qty):
                        new_tp = float(pos.get("avgPrice", last_price)) * (1.0 + t_conf.take_profit_pct / 100.0)
                        self.client.amend_order_trading_stop(symbol=symbol, take_profit=str(round(new_tp, 4)))
                        messages.append(f"📈 **[Суточный] Докуп Лонг ({symbol})**")
                elif pos_side == "Sell" and is_bearish and not already_added:
                    if self.client.place_order(symbol=symbol, side="Sell", order_type="Market", qty=qty):
                        new_tp = float(pos.get("avgPrice", last_price)) * (1.0 - t_conf.take_profit_pct / 100.0)
                        self.client.amend_order_trading_stop(symbol=symbol, take_profit=str(round(new_tp, 4)))
                        messages.append(f"📉 **[Суточный] Докуп Шорт ({symbol})**")

        return messages

    def process_hourly_trading_logic(self, test_signal: Optional[str] = None) -> List[str]:
        """Часовой алгоритм: цвет свечи (бычья/медвежья) + MA фильтры"""
        messages = []
        t_conf = self.config.trading
        if not t_conf.hourly_enabled and not test_signal:
            return messages

        equity = self.client.get_wallet_balance(t_conf.settle_coin)
        if equity <= 0:
            equity = 100.0

        for symbol in t_conf.symbols:
            self.client.set_margin_mode_and_leverage(symbol, t_conf.leverage)
            pos = self.client.get_position(symbol)
            
            if pos is not None and not test_signal:
                continue

            last_price = self.client.get_ticker_price(symbol)
            if last_price <= 0:
                continue

            decimals, qty_step = self.client.get_qty_step_and_precision(symbol)

            is_bullish = False
            is_bearish = False

            if test_signal:
                if test_signal.lower() == "long":
                    is_bullish = True
                elif test_signal.lower() == "short":
                    is_bearish = True
            else:
                limit_candles = max(t_conf.ma_slow + 5, 60)
                klines = self.client.get_klines(symbol, interval="60", limit=limit_candles)
                if not klines or len(klines) < t_conf.ma_slow + 2:
                    logger.warning(f"Not enough klines for MA calculation on {symbol}")
                    continue

                candle = klines[-2]
                open_p = float(candle[1])
                close_p = float(candle[4])
                
                # 1. Проверяем, какая свеча (бычья или медвежья)
                candle_is_bullish = close_p > open_p
                candle_is_bearish = close_p < open_p

                closes = [float(k[4]) for k in klines]
                closes_prev = closes[:-1]
                ma9_curr = self._calculate_sma(closes, t_conf.ma_fast)
                ma9_prev = self._calculate_sma(closes_prev, t_conf.ma_fast)
                ma50_curr = self._calculate_sma(closes, t_conf.ma_slow)

                # 2. Дополнительные условия MA поверх направления свечи:
                # Лонг: свеча бычья AND цена ниже MA50 AND текущая MA9 > предыдущей MA9
                is_bullish = candle_is_bullish and (last_price < ma50_curr) and (ma9_curr > ma9_prev)
                
                # Шорт: свеча медвежья AND цена выше MA50 AND текущая MA9 < предыдущей MA9
                is_bearish = candle_is_bearish and (last_price > ma50_curr) and (ma9_curr < ma9_prev)

            notional = equity * t_conf.initial_size_mult
            qty_raw = notional / last_price
            qty_val = round(round(qty_raw / qty_step) * qty_step, decimals) if qty_step > 0 else round(qty_raw, decimals)
            qty = str(int(qty_val)) if decimals == 0 else f"{qty_val:.{decimals}f}"

            if is_bullish:
                tp_price = last_price * (1.0 + t_conf.hourly_take_profit_pct / 100.0)
                sl_price = last_price * (1.0 - t_conf.hourly_stop_loss_pct / 100.0) if t_conf.hourly_stop_loss_pct > 0 else None
                
                order_kwargs = {
                    "symbol": symbol,
                    "side": "Buy",
                    "order_type": "Market",
                    "qty": qty,
                    "take_profit": str(round(tp_price, 4))
                }
                if sl_price:
                    order_kwargs["stop_loss"] = str(round(sl_price, 4))

                res = self.client.place_order(**order_kwargs)
                if res:
                    if t_conf.hourly_stop_loss_pct <= 0 and t_conf.hourly_add_order_drop_pct > 0:
                        add_price = last_price * (1.0 - t_conf.hourly_add_order_drop_pct / 100.0)
                        self.client.place_order(
                            symbol=symbol,
                            side="Buy",
                            order_type="Limit",
                            qty=qty,
                            price=str(round(add_price, 4))
                        )

                    prefix = "[ТЕСТ / Часовой Лонг]" if test_signal else "[Часовой Лонг]"
                    sl_text = f" | СЛ: {round(sl_price, 4)}" if sl_price else " | Лимитка усреднения выставлена"
                    msg = f"⏱🟢 **{prefix} ({symbol})** | ТП: {round(tp_price, 4)}{sl_text}"
                    messages.append(msg)
                    logger.info(msg)

            elif is_bearish:
                tp_price = last_price * (1.0 - t_conf.hourly_take_profit_pct / 100.0)
                sl_price = last_price * (1.0 + t_conf.hourly_stop_loss_pct / 100.0) if t_conf.hourly_stop_loss_pct > 0 else None
                
                order_kwargs = {
                    "symbol": symbol,
                    "side": "Sell",
                    "order_type": "Market",
                    "qty": qty,
                    "take_profit": str(round(tp_price, 4))
                }
                if sl_price:
                    order_kwargs["stop_loss"] = str(round(sl_price, 4))

                res = self.client.place_order(**order_kwargs)
                if res:
                    if t_conf.hourly_stop_loss_pct <= 0 and t_conf.hourly_add_order_drop_pct > 0:
                        add_price = last_price * (1.0 + t_conf.hourly_add_order_drop_pct / 100.0)
                        self.client.place_order(
                            symbol=symbol,
                            side="Sell",
                            order_type="Limit",
                            qty=qty,
                            price=str(round(add_price, 4))
                        )

                    prefix = "[ТЕСТ / Часовой Шорт]" if test_signal else "[Часовой Шорт]"
                    sl_text = f" | СЛ: {round(sl_price, 4)}" if sl_price else " | Лимитка усреднения выставлена"
                    msg = f"⏱🔴 **{prefix} ({symbol})** | ТП: {round(tp_price, 4)}{sl_text}"
                    messages.append(msg)
                    logger.info(msg)

        return messages

    def process_minute_monitoring(self) -> None:
        """Ежеминутная проверка висящих лимитных ордеров"""
        t_conf = self.config.trading
        for symbol in t_conf.symbols:
            pos = self.client.get_position(symbol)
            if pos is None:
                open_orders = self.client.get_open_orders(symbol)
                if open_orders:
                    logger.info(f"Position for {symbol} is closed, but open orders found. Cancelling remaining orders.")
                    self.client.cancel_all_orders(symbol)
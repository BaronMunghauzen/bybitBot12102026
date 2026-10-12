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
            "🤖 **Торговый бот запущен (Анализ состояния по API Bybit)**\n\n"
            "⚙️ **Параметры:**\n"
            f"• Плечо: {t.leverage}x (Изолированная маржа)\n"
            f"• Список активов: {', '.join(t.symbols)}\n"
            f"• Коэффициент первого входа: {t.initial_size_mult}x\n"
            f"• Тейк-профит: {t.take_profit_pct}%\n"
            f"• Максимум докупов: {t.max_add_orders}\n"
            "• Время срабатывания: за 30 секунд до закрытия дневной свечи (23:59:30 UTC)\n"
        )

    def process_trading_logic(self, test_signal: Optional[str] = None) -> List[str]:
        messages = []
        t_conf = self.config.trading
        equity = self.client.get_wallet_balance(t_conf.settle_coin)
        if equity <= 0:
            logger.warning("Wallet balance is 0 or unable to fetch. Using fallback for tests.")
            equity = 100.0

        for symbol in t_conf.symbols:
            self.client.set_margin_mode_and_leverage(symbol, t_conf.leverage)
            pos = self.client.get_position(symbol)
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
                klines = self.client.get_klines(symbol, interval="D", limit=2)
                if not klines:
                    logger.warning(f"No klines for {symbol}")
                    continue
                candle = klines[-1]
                open_p = float(candle[1])
                close_p = float(candle[4])
                is_bullish = close_p > open_p
                is_bearish = close_p < open_p

            notional = equity * t_conf.initial_size_mult
            qty_raw = notional / last_price

            if qty_step > 0:
                qty_val = round(round(qty_raw / qty_step) * qty_step, decimals)
            else:
                qty_val = round(qty_raw, decimals)

            if decimals == 0:
                qty = str(int(qty_val))
            else:
                qty = f"{qty_val:.{decimals}f}"

            # Если позиция ОТСУТСТВУЕТ
            if pos is None:
                if is_bullish:
                    side = "Buy"
                    tp_price = last_price * (1.0 + t_conf.take_profit_pct / 100.0)
                    order_res = self.client.place_order(
                        symbol=symbol,
                        side=side,
                        order_type="Market",
                        qty=qty,
                        take_profit=str(round(tp_price, 4)),
                    )
                    if order_res:
                        msg = (
                            f"🟢 **Открыта Лонг сделка по рынку ({symbol})** [Сигнал: Бычья свеча]\n"
                            f"• Объем: {qty} (Коэфф: {t_conf.initial_size_mult}x, Плечо: {t_conf.leverage}x)\n"
                            f"• Тейк-профит: {round(tp_price, 4)} (+{t_conf.take_profit_pct}%)"
                        )
                        messages.append(msg)
                        logger.info(msg)

                elif is_bearish:
                    side = "Sell"
                    tp_price = last_price * (1.0 - t_conf.take_profit_pct / 100.0)
                    order_res = self.client.place_order(
                        symbol=symbol,
                        side=side,
                        order_type="Market",
                        qty=qty,
                        take_profit=str(round(tp_price, 4)),
                    )
                    if order_res:
                        msg = (
                            f"🔴 **Открыта Шорт сделка по рынку ({symbol})** [Сигнал: Медвежья свеча]\n"
                            f"• Объем: {qty} (Коэфф: {t_conf.initial_size_mult}x, Плечо: {t_conf.leverage}x)\n"
                            f"• Тейк-профит: {round(tp_price, 4)} (-{t_conf.take_profit_pct}%)"
                        )
                        messages.append(msg)
                        logger.info(msg)

            # Если позиция УЖЕ СУЩЕСТВУЕТ — проверяем статус докупа прямо по данным Bybit
            else:
                pos_side = pos.get("side")
                pos_created_time = int(pos.get("createdTime", 0))
                
                # Запрашиваем у Bybit, был ли уже докуп для этой активной позиции
                already_added = self.client.has_add_been_executed(symbol, pos_side, pos_created_time)

                if pos_side == "Buy" and is_bullish and not already_added:
                    order_res = self.client.place_order(
                        symbol=symbol,
                        side="Buy",
                        order_type="Market",
                        qty=qty,
                    )
                    if order_res:
                        avg_price = float(pos.get("avgPrice", last_price))
                        new_tp = avg_price * (1.0 + t_conf.take_profit_pct / 100.0)
                        self.client.amend_order_trading_stop(symbol=symbol, take_profit=str(round(new_tp, 4)))

                        msg = (
                            f"📈 **Докуп Лонг позиции по рынку выполнен ({symbol})**\n"
                            f"• Объем докупа: {qty}\n"
                            f"• Новый Тейк-профит: {round(new_tp, 4)} (+{t_conf.take_profit_pct}% от средней)"
                        )
                        messages.append(msg)
                        logger.info(msg)

                elif pos_side == "Sell" and is_bearish and not already_added:
                    order_res = self.client.place_order(
                        symbol=symbol,
                        side="Sell",
                        order_type="Market",
                        qty=qty,
                    )
                    if order_res:
                        avg_price = float(pos.get("avgPrice", last_price))
                        new_tp = avg_price * (1.0 - t_conf.take_profit_pct / 100.0)
                        self.client.amend_order_trading_stop(symbol=symbol, take_profit=str(round(new_tp, 4)))

                        msg = (
                            f"📉 **Докуп Шорт позиции по рынку выполнен ({symbol})**\n"
                            f"• Объем докупа: {qty}\n"
                            f"• Новый Тейк-профит: {round(new_tp, 4)} (-{t_conf.take_profit_pct}% от средней)"
                        )
                        messages.append(msg)
                        logger.info(msg)

        return messages
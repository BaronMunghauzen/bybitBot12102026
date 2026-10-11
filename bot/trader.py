from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from bot.bybit_client import BybitClient
from bot.strategy import Strategy

logger = logging.getLogger(__name__)

class Trader:
    def __init__(self, config, client: BybitClient) -> None:
        self.config = config
        self.client = client
        self.strategy = Strategy(config)
        # Keep track of previous SL update states per symbol to avoid spamming
        self.last_filled_adds: Dict[str, int] = {}
        self.trailing_activated: Dict[str, bool] = {}

    def format_startup_message(self) -> str:
        t = self.config.trading
        return (
            "🤖 **Торговый бот запущен и настроен**\n\n"
            "⚙️ **Параметры стратегии:**\n"
            "• Риск на сделку: не используется\n"
            f"• Размер плеча: {t.leverage}x\n"
            f"• Список активов: {', '.join(t.symbols)}\n"
            f"• Объем первого входа (коэфф.): {t.initial_size_mult}\n"
            f"• Короткая МА: {t.ma_fast}\n"
            f"• Длинная МА: {t.ma_slow}\n"
            f"• Максимальное число докупов: {t.max_add_orders}\n"
            f"• Первоначальный стоп-лосс: {t.initial_stop_loss_pct}%\n"
            f"• Скользящий стоп-лосс: {t.trailing_stop_pct}%\n"
            f"• Время срабатывания: каждый час в {t.schedule_minute} мин {t.schedule_second} сек\n"
        )

    def run_hourly_check(self) -> List[str]:
        messages = []
        t_conf = self.config.trading
        equity = self.client.get_wallet_balance(t_conf.settle_coin)
        if equity <= 0:
            logger.warning("Wallet equity is 0 or unable to fetch.")
            return messages

        for symbol in t_conf.symbols:
            self.client.set_leverage(symbol, t_conf.leverage)
            pos = self.client.get_position(symbol)
            
            # Fetch klines (hourly)
            klines = self.client.get_klines(symbol, interval="60", limit=t_conf.ma_slow + 50)
            if not klines or len(klines) < t_conf.ma_slow:
                logger.warning(f"Not enough klines for {symbol}")
                continue

            closes = [float(k[4]) for k in klines[:-1]] # previous closed candles
            last_price = self.client.get_ticker_price(symbol)
            if last_price <= 0:
                continue

            try:
                fast_curr, slow_curr, fast_prev, slow_prev = self.strategy.calculate_mas(closes, last_price)
            except Exception as e:
                logger.error(f"MA calculation error for {symbol}: {e}")
                continue

            # If no active trades/positions, check signal
            if pos is None:
                signal = self.strategy.check_signal(fast_curr, slow_curr, fast_prev, slow_prev)
                if signal:
                    side = "Buy" if signal == "Buy" else "Sell"
                    # Volume calculation: (Equity * initial_size_mult) / price
                    notional = equity * t_conf.initial_size_mult
                    qty_raw = notional / last_price
                    # Format qty based on precision or simple round
                    qty = f"{qty_raw:.2f}"

                    short_ma = fast_curr
                    initial_sl = self.strategy.calculate_initial_stop_loss(side, last_price, short_ma)

                    # Execute order
                    order_res = self.client.place_order(
                        symbol=symbol,
                        side=side,
                        order_type="Limit",
                        qty=qty,
                        price=str(last_price),
                        stop_loss=str(round(initial_sl, 4)),
                    )

                    if order_res:
                        msg = (
                            f"🚨 **Сделка открыта ({symbol})**\n"
                            f"• Направление: {side}\n"
                            f"• Цена входа: {last_price}\n"
                            f"• Объем: {qty} (Коэфф: {t_conf.initial_size_mult}x)\n"
                            f"• Стоп-лосс: {round(initial_sl, 4)}\n"
                            f"• Fast MA: {fast_curr:.2f} | Slow MA: {slow_curr:.2f}"
                        )
                        messages.append(msg)
                        logger.info(msg)

                        # Reset state tracking
                        self.last_filled_adds[symbol] = 0
                        self.trailing_activated[symbol] = False

                        # Place pyramid add orders
                        add_prices = self.strategy.calculate_add_orders_prices(
                            side, last_price, initial_sl, t_conf.max_add_orders
                        )
                        add_side = "Buy" if side == "Buy" else "Sell"
                        add_msgs = [f"📈 **Выставлены лимитные ордера докупки (Пирамидинг):**"]
                        for idx, p in enumerate(add_prices, 1):
                            add_res = self.client.place_order(
                                symbol=symbol,
                                side=add_side,
                                order_type="Limit",
                                qty=qty,
                                price=str(p),
                            )
                            add_msgs.append(f"  {idx}. Цена: {p}, Объем: {qty}")
                        messages.append("\n".join(add_msgs))

        return messages

    def run_minute_check(self) -> List[str]:
        messages = []
        t_conf = self.config.trading

        for symbol in t_conf.symbols:
            pos = self.client.get_position(symbol)
            open_orders = self.client.get_open_orders(symbol)

            # Check if position was closed (e.g. stopped out)
            if pos is None:
                # If there were open limit/add orders, cancel them
                if open_orders:
                    self.client.cancel_all_orders(symbol)
                    if symbol in self.last_filled_adds and self.last_filled_adds[symbol] > 0:
                        msg = f"❌ **Позиция по {symbol} закрыта (сработал стоп-лосс). Все активные лимитные ордера отменены.**"
                        messages.append(msg)
                        logger.info(msg)
                    self.last_filled_adds[symbol] = 0
                    self.trailing_activated[symbol] = False
                continue

            # Position is active
            side = pos.get("side") # "Buy" or "Sell"
            avg_entry = float(pos.get("avgPrice", 0.0) or 0.0)
            
            # Count filled add orders by checking how many open add orders remain vs max_add_orders
            # Or count active add orders in open_orders
            add_prices_orders = [o for o in open_orders if o.get("orderType") == "Limit" and not o.get("reduceOnly")]
            filled_adds = t_conf.max_add_orders - len(add_prices_orders)
            if filled_adds < 0:
                filled_adds = 0
            if filled_adds > t_conf.max_add_orders:
                filled_adds = t_conf.max_add_orders

            prev_filled = self.last_filled_adds.get(symbol, 0)

            # If all add orders are filled and trailing not activated yet
            if filled_adds >= t_conf.max_add_orders and not self.trailing_activated.get(symbol, False):
                # Switch to trailing stop
                success = self.client.amend_order_trading_stop(
                    symbol=symbol,
                    stop_loss="0", # remove fixed stop loss
                    trailing_stop=str(t_conf.trailing_stop_pct),
                )
                if success:
                    self.trailing_activated[symbol] = True
                    msg = (
                        f"🔄 **Все лимитные ордера докупки ({t_conf.max_add_orders}) исполнены! ({symbol})**\n"
                        f"Установлен скользящий стоп-лосс (Trailing Stop): {t_conf.trailing_stop_pct}%."
                    )
                    messages.append(msg)
                    logger.info(msg)
            elif filled_adds > prev_filled and not self.trailing_activated.get(symbol, False):
                # Update stop loss based on step (+0.3% per add)
                new_sl = self.strategy.calculate_updated_stop_loss(side, avg_entry, filled_adds)
                if new_sl:
                    success = self.client.amend_order_trading_stop(
                        symbol=symbol,
                        stop_loss=str(round(new_sl, 4)),
                    )
                    if success:
                        self.last_filled_adds[symbol] = filled_adds
                        profit_pct = filled_adds * 0.3
                        msg = (
                            f"🛡 **Стоп-лосс перемещен ({symbol})**\n"
                            f"• Исполнено докупов: {filled_adds}/{t_conf.max_add_orders}\n"
                            f"• Новая цена стопа: {round(new_sl, 4)} (Безубыток/Прибыль +{profit_pct:.1f}%)"
                        )
                        messages.append(msg)
                        logger.info(msg)

        return messages
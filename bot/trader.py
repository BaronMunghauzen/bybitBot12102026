def process_hourly_trading_logic(self, test_signal: Optional[str] = None) -> List[str]:
        """Часовой алгоритм: цвет текущей свечи (бычья/медвежья) + MA фильтры"""
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

                # ИЗМЕНЕНИЕ: Берем klines[-1] — текущую свечу, которая закрывается прямо сейчас в 59 минут 30 секунд
                candle = klines[-1]
                open_p = float(candle[1])
                close_p = float(candle[4])
                
                # 1. Проверяем цвет текущей свечи
                candle_is_bullish = close_p > open_p
                candle_is_bearish = close_p < open_p

                closes = [float(k[4]) for k in klines]
                closes_prev = closes[:-1]
                ma9_curr = self._calculate_sma(closes, t_conf.ma_fast)
                ma9_prev = self._calculate_sma(closes_prev, t_conf.ma_fast)
                ma50_curr = self._calculate_sma(closes, t_conf.ma_slow)

                # 2. Дополнительные условия MA поверх направления текущей свечи
                is_bullish = candle_is_bullish and (last_price < ma50_curr) and (ma9_curr > ma9_prev)
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
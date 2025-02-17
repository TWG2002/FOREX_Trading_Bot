import asyncio
from datetime import datetime, timezone
import pandas as pd

from config import (
    OANDA_API_KEY,
    OANDA_ACCOUNT_ID,
    INSTRUMENTS,
    TIMEFRAME,
    RISK_PER_TRADE,
    MAX_TRADES_PER_DAY,
    DAILY_DRAWDOWN_LIMIT_PCT,
    RSI_PERIOD,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
    ATR_PERIOD,
    TRAILING_STOP_PIPS
)
from utils import (
    logger,
    get_oanda_client,
    fetch_ohlc_data,
    get_account_balance,
    calculate_dynamic_position_size,
    place_order,
    send_email_alert,
    close_all_trades,
    notify_trade
)
from strategy import generate_combined_signal, apply_indicators, get_higher_timeframe_trend
from indicators import detect_candlestick_patterns

def compute_unrealized_pnl(trade: dict, current_price: float, pip_value: float = 0.0001) -> float:
    if trade["side"].upper() == "BUY":
        return (current_price - trade["entry_price"]) * trade["units"] * pip_value
    else:
        return (trade["entry_price"] - current_price) * trade["units"] * pip_value

async def fetch_all_instruments(client, instruments, timeframe, count=200):
    tasks = [asyncio.to_thread(fetch_ohlc_data, client, instrument, timeframe, count) for instrument in instruments]
    results = await asyncio.gather(*tasks)
    return dict(zip(instruments, results))

async def main_async():
    client = get_oanda_client()
    daily_trade_count = 0
    consecutive_losses = 0
    MAX_CONSECUTIVE_LOSSES = 3  # Stop trading after 3 losses in a row
    start_of_day_equity = None
    last_date = None

    # List to track open trades
    open_trades = []

    logger.info("Starting live day-trading bot with Asynchronous Data Fetching...")

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_day = now.date()
            current_hour = now.hour

            # --- Mitigate Costs: Only trade during optimal trading hours (e.g., 6 to 18 UTC) ---
            if current_hour < 6 or current_hour > 18:
                logger.info("Outside optimal trading hours. Pausing new trades.")
                await asyncio.sleep(300)  # Sleep for 5 minutes
                continue

            # Only trade on weekdays
            if now.weekday() >= 5:
                logger.info("It's the weekend. The bot will not trade today.")
                await asyncio.sleep(3600)
                continue

            # Daily reset: new day resets trade count and loss counter
            if current_day != last_date:
                last_date = current_day
                daily_trade_count = 0
                consecutive_losses = 0
                start_of_day_equity = get_account_balance(client, OANDA_ACCOUNT_ID)
                logger.info(f"New trading day: {current_day}, equity = {start_of_day_equity:.2f}")

            current_balance = get_account_balance(client, OANDA_ACCOUNT_ID)
            if start_of_day_equity is None:
                start_of_day_equity = current_balance
            dd_pct = ((current_balance - start_of_day_equity) / start_of_day_equity) * 100

            if dd_pct <= -DAILY_DRAWDOWN_LIMIT_PCT:
                logger.warning(f"Daily drawdown {dd_pct:.2f}% exceeds limit. Halting new trades.")
                send_email_alert("Daily Drawdown Alert", f"Daily drawdown {dd_pct:.2f}% exceeds limit. Halting new trades.")
                await asyncio.sleep(60)
                continue

            # --- Fetch Data ---
            instrument_data = await fetch_all_instruments(client, INSTRUMENTS, TIMEFRAME, count=200)
            latest_prices = {}

            for instrument, df in instrument_data.items():
                if df.empty or len(df) < 50:
                    logger.warning(f"No sufficient data for {instrument}.")
                    continue

                df = apply_indicators(df, RSI_PERIOD, MACD_FAST, MACD_SLOW, MACD_SIGNAL, ATR_PERIOD)
                df.dropna(inplace=True)
                df = detect_candlestick_patterns(df)
                latest_price = df["close"].iloc[-1]
                latest_prices[instrument] = latest_price

                # --- Adapt to Market Regime: Skip trade if market is flat (ADX < 30) ---
                adx = df["ADX"].iloc[-1]
                logger.info(f"{instrument}: Current ADX is {adx:.2f}.")
                if adx < 25:
                    logger.info(f"{instrument}: ADX ({adx:.2f}) indicates a flat market. Skipping trade.")
                    continue


                # --- Step 2: Retrieve M15 and M5 Trends ---
                trend_M15 = get_higher_timeframe_trend(client, instrument, higher_tf="M15", count=50)
                trend_M5  = get_higher_timeframe_trend(client, instrument, higher_tf="M5", count=50)
                logger.info(f"{instrument} trends => M15: {trend_M15}, M5: {trend_M5}")

                # --- Generate Signal from M1 Data ---
                signal = generate_combined_signal(df, htf_trend=None)
                logger.info(f"{instrument} M1 signal: {signal}")

                # --- Step 3: Use Trend Confirmation ---
                confirmed_signal = "FLAT"
                if signal == "BUY" and trend_M15 == "up" and trend_M5 == "up":
                    confirmed_signal = "BUY"
                elif signal == "SELL" and trend_M15 == "down" and trend_M5 == "down":
                    confirmed_signal = "SELL"
                else:
                    logger.info(f"{instrument} signal not confirmed by M5/M15 trends; skipping trade.")

                # Only proceed if confirmed_signal is BUY or SELL
                if confirmed_signal in ["BUY", "SELL"]:
                    # --- Tighten Risk Management: Check trade limits ---
                    if daily_trade_count >= MAX_TRADES_PER_DAY or consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                        logger.info("Trade cap reached for today. Skipping new trade signals.")
                        continue

                    balance = get_account_balance(client, OANDA_ACCOUNT_ID)
                    atr_value = df["ATR"].iloc[-1]
                    current_price = latest_price

                    # Calculate dynamic position size
                    position_size = calculate_dynamic_position_size(balance, RISK_PER_TRADE, atr_value, current_price)

                    # --- Improve Stop/Target Placement: ATR-based SL and TP ---
                    atr_in_pips = atr_value * 10000
                    stop_loss_multiplier = 1.5  # Adjust multiplier as needed
                    reward_factor = 2.0         # Aim for at least a 2:1 reward-to-risk ratio

                    stop_loss_pips = atr_in_pips * stop_loss_multiplier

                    if confirmed_signal.upper() == "BUY":
                        stop_loss_price = current_price - (stop_loss_pips * 0.0001)
                        take_profit_price = current_price + (stop_loss_pips * 0.0001 * reward_factor)
                    else:  # SELL signal
                        stop_loss_price = current_price + (stop_loss_pips * 0.0001)
                        take_profit_price = current_price - (stop_loss_pips * 0.0001 * reward_factor)

                    order_id = place_order(client, instrument, confirmed_signal, position_size, stop_loss_price, take_profit_price)
                    if order_id is not None:
                        daily_trade_count += 1
                        open_trade = {
                            "instrument": instrument,
                            "side": confirmed_signal,
                            "entry_price": current_price,
                            "units": position_size,
                            "order_id": order_id,
                            "max_price": current_price if confirmed_signal.upper() == "BUY" else None,
                            "min_price": current_price if confirmed_signal.upper() == "SELL" else None,
                            "take_profit_price": take_profit_price
                        }
                        open_trades.append(open_trade)
                        notify_trade(open_trade)

            # --- Trailing Stop Loss Logic ---
            for trade in open_trades.copy():
                inst = trade["instrument"]
                current_price = latest_prices.get(inst)
                if current_price is None:
                    df_temp = await asyncio.to_thread(fetch_ohlc_data, client, inst, TIMEFRAME, 1)
                    if df_temp.empty:
                        continue
                    current_price = df_temp["close"].iloc[-1]

                # Activate trailing stop only after the trade is in profit by at least 30% of the target gain
                if trade["side"].upper() == "BUY":
                    if current_price > trade["max_price"]:
                        trade["max_price"] = current_price
                    profit_threshold = (trade["take_profit_price"] - trade["entry_price"]) * 0.35
                    if (current_price - trade["entry_price"]) > profit_threshold:
                        trailing_stop_level = trade["max_price"] - (TRAILING_STOP_PIPS * 0.0001)
                        logger.info(f"{inst} BUY trade: current price {current_price:.5f}, trailing stop level {trailing_stop_level:.5f}")
                        if current_price < trailing_stop_level:
                            logger.warning(f"Trailing stop hit for {inst} BUY trade. Closing trade.")
                            send_email_alert("Trailing Stop Alert", f"Trailing stop hit for {inst} BUY trade. Trade closed.")
                            if close_all_trades(client, [trade]) == []:
                                open_trades.remove(trade)
                                profit = compute_unrealized_pnl(trade, current_price)
                                if profit < 0:
                                    consecutive_losses += 1
                                else:
                                    consecutive_losses = 0
                    else:
                        logger.info(f"{inst} BUY trade not yet eligible for trailing stop adjustment.")
                elif trade["side"].upper() == "SELL":
                    if current_price < trade["min_price"]:
                        trade["min_price"] = current_price
                    profit_threshold = (trade["entry_price"] - trade["take_profit_price"]) * 0.5
                    if (trade["entry_price"] - current_price) > profit_threshold:
                        trailing_stop_level = trade["min_price"] + (TRAILING_STOP_PIPS * 0.0001)
                        logger.info(f"{inst} SELL trade: current price {current_price:.5f}, trailing stop level {trailing_stop_level:.5f}")
                        if current_price > trailing_stop_level:
                            logger.warning(f"Trailing stop hit for {inst} SELL trade. Closing trade.")
                            send_email_alert("Trailing Stop Alert", f"Trailing stop hit for {inst} SELL trade. Trade closed.")
                            if close_all_trades(client, [trade]) == []:
                                open_trades.remove(trade)
                                profit = compute_unrealized_pnl(trade, current_price)
                                if profit < 0:
                                    consecutive_losses += 1
                                else:
                                    consecutive_losses = 0
                    else:
                        logger.info(f"{inst} SELL trade not yet eligible for trailing stop adjustment.")

            # --- Risk Management: Total Unrealized Loss ---
            total_unrealized_loss = 0.0
            for trade in open_trades:
                inst = trade["instrument"]
                current_price = latest_prices.get(inst)
                if current_price is None:
                    df_temp = await asyncio.to_thread(fetch_ohlc_data, client, inst, TIMEFRAME, 1)
                    if df_temp.empty:
                        continue
                    current_price = df_temp["close"].iloc[-1]
                pnl = compute_unrealized_pnl(trade, current_price)
                if pnl < 0:
                    total_unrealized_loss += pnl

            daily_loss_limit = start_of_day_equity * (DAILY_DRAWDOWN_LIMIT_PCT / 100.0)
            if abs(total_unrealized_loss) >= daily_loss_limit:
                logger.warning(f"Total unrealized loss ({abs(total_unrealized_loss):.2f}) reached daily limit ({daily_loss_limit:.2f}). Closing trades.")
                send_email_alert("Daily Loss Limit Exceeded", f"Total unrealized loss of {abs(total_unrealized_loss):.2f} reached/exceeded daily limit of {daily_loss_limit:.2f}. Closing trades.")
                open_trades = close_all_trades(client, open_trades)

            await asyncio.sleep(60)

        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            send_email_alert("Trading Bot Error", f"Unexpected error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_async())

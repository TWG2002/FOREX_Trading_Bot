"""
Indicator calculations (RSI, MACD, ATR, etc.) for use in both live trading and backtesting.
"""

import pandas as pd
import numpy as np

def compute_rsi(data: pd.DataFrame, period: int) -> pd.Series:
    """
    Calculate RSI on 'close' prices over a specified period.
    """
    delta = data["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)  # prevent division by zero
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(data: pd.DataFrame, fast: int, slow: int, signal: int):
    """
    MACD line, signal line, histogram on 'close' prices.
    """
    ema_fast = data["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = data["close"].ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def compute_atr(data: pd.DataFrame, period: int) -> pd.Series:
    """
    Average True Range (ATR) for volatility-based stop sizing.
    """
    df = data.copy()
    df["H-L"] = df["high"] - df["low"]
    df["H-C"] = (df["high"] - df["close"].shift(1)).abs()
    df["L-C"] = (df["low"] - df["close"].shift(1)).abs()
    df["TR"] = df[["H-L", "H-C", "L-C"]].max(axis=1)
    atr = df["TR"].rolling(window=period).mean()
    return atr

def compute_bollinger_bands(data: pd.DataFrame, period: int = 20, num_std: float = 2.0):
    """
    Compute Bollinger Bands (upper, mid, lower) on the 'close' price.
    period: moving average period
    num_std: number of standard deviations for upper/lower bands
    """
    df = data.copy()
    # Simple Moving Average
    df["BB_mid"] = df["close"].rolling(window=period).mean()
    # Standard Deviation
    df["BB_std"] = df["close"].rolling(window=period).std()
    
    df["BB_upper"] = df["BB_mid"] + (num_std * df["BB_std"])
    df["BB_lower"] = df["BB_mid"] - (num_std * df["BB_std"])
    
    return df["BB_upper"], df["BB_mid"], df["BB_lower"]


def compute_adx(data: pd.DataFrame, period: int = 14):
    """
    Compute the Average Directional Index (ADX) using Wilder's smoothing method.
    ADX measures trend strength; typically:
      - ADX < 20 => weak trend
      - ADX > 25-30 => strong trend.
    """
    df = data.copy()
    
    # 1) Calculate price movement components
    df["diff_high"] = df["high"].diff()
    df["diff_low"] = df["low"].diff()
    
    # 2) Calculate +DM and -DM (both as positive values)
    df["+DM"] = np.where((df["diff_high"] > df["diff_low"]) & (df["diff_high"] > 0), df["diff_high"], 0.0)
    df["-DM"] = np.where((df["diff_low"] > df["diff_high"]) & (df["diff_low"] > 0), df["diff_low"], 0.0)
    
    # 3) True Range (TR)
    df["TR_method1"] = df["high"] - df["low"]
    df["TR_method2"] = (df["high"] - df["close"].shift(1)).abs()
    df["TR_method3"] = (df["low"] - df["close"].shift(1)).abs()
    df["TR"] = df[["TR_method1", "TR_method2", "TR_method3"]].max(axis=1)
    
    # 4) Apply Wilder's smoothing using ewm with alpha=1/period
    df["+DM_smooth"] = df["+DM"].ewm(alpha=1/period, adjust=False).mean()
    df["-DM_smooth"] = df["-DM"].ewm(alpha=1/period, adjust=False).mean()
    df["TR_smooth"] = df["TR"].ewm(alpha=1/period, adjust=False).mean()
    
    # 5) Calculate +DI and -DI
    df["+DI"] = 100 * (df["+DM_smooth"] / df["TR_smooth"])
    df["-DI"] = 100 * (df["-DM_smooth"] / df["TR_smooth"])
    
    # 6) Calculate DX
    df["DX"] = ( (df["+DI"] - df["-DI"]).abs() / (df["+DI"] + df["-DI"]) ) * 100
    
    # 7) Finally, compute ADX using Wilder's smoothing on DX
    df["ADX"] = df["DX"].ewm(alpha=1/period, adjust=False).mean()
    
    return df["ADX"]



# indicators.py

def detect_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Basic custom-coded detection for:
      - Bullish Engulfing
      - Hammer
    We'll keep it simple for demonstration.
    """
    df["BullishEngulfing"] = 0
    df["Hammer"] = 0
    
    for i in range(1, len(df)):
        prev_open = df["open"].iloc[i - 1]
        prev_close = df["close"].iloc[i - 1]

        curr_open = df["open"].iloc[i]
        curr_close = df["close"].iloc[i]
        curr_high = df["high"].iloc[i]
        curr_low = df["low"].iloc[i]
        
        # 1) Bullish Engulfing:
        #   - Previous bar is bearish (close < open)
        #   - Current bar is bullish (close > open)
        #   - Current bar's body fully engulfs the previous bar's body
        if (prev_close < prev_open) and (curr_close > curr_open) and \
           (curr_close > prev_open) and (curr_open < prev_close):
            df.at[df.index[i], "BullishEngulfing"] = 1
        
        # 2) Hammer:
        #   - Hammer typically has a small real body near the top of the range
        #   - Long lower shadow, short or no upper shadow
        body = abs(curr_close - curr_open)
        upper_shadow = curr_high - max(curr_close, curr_open)
        lower_shadow = min(curr_close, curr_open) - curr_low

        # Simplistic ratio approach
        if body <= (0.3 * (curr_high - curr_low)) and lower_shadow >= (2 * body):
            # That’s a naive "hammer" detection
            df.at[df.index[i], "Hammer"] = 1

    return df


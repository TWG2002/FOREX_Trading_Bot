import pandas as pd
import datetime
from dateutil.parser import isoparse
from oandapyV20 import API
from oandapyV20.endpoints import instruments
from oandapyV20.exceptions import V20Error
from config import OANDA_API_KEY, OANDA_ENV

def fetch_data_for_period(
    client: API,
    instrument: str,
    start: str,
    end: str,
    granularity: str = "M1"   # default is M1; can be changed to M15, H1, etc.
) -> pd.DataFrame:
    """
    Fetch historical data (OHLC) from OANDA for a given instrument and timeframe.
    
    :param client:    OANDA API client (oandapyV20.API).
    :param instrument: e.g. "EUR_USD".
    :param start:     Start time (str or datetime). Example: "2023-01-01T00:00:00Z".
    :param end:       End time (str or datetime). Example: "2023-01-05T00:00:00Z".
    :param granularity: Timeframe to fetch (e.g., "M1", "M15", "H1"). Default is "M1".
    :return:          pd.DataFrame with columns [open, high, low, close], indexed by time.
    """
    # Convert inputs to datetime if they are strings
    if isinstance(start, str):
        start_dt = isoparse(start)
    else:
        start_dt = start
    
    if isinstance(end, str):
        end_dt = isoparse(end)
    else:
        end_dt = end

    # Use the provided granularity in the request
    price_type = "M"  # mid prices
    
    all_candles = []
    current_start = start_dt

    while True:
        # Set an upper bound for this request (~5000 candles)
        chunk_end = current_start + datetime.timedelta(minutes=5000)
        
        if chunk_end > end_dt:
            chunk_end = end_dt
        
        params = {
            "from": current_start.isoformat(),
            "to": chunk_end.isoformat(),
            "granularity": granularity,
            "price": price_type
        }

        req = instruments.InstrumentsCandles(instrument=instrument, params=params)
        try:
            client.request(req)
        except V20Error as e:
            print(f"Error fetching data for {instrument}: {e}")
            break  # stop on error

        candles = req.response.get("candles", [])
        if not candles:
            break

        # Convert candles to DataFrame rows
        chunk_df = pd.DataFrame([
            {
                "time": c["time"],
                "open": float(c["mid"]["o"]),
                "high": float(c["mid"]["h"]),
                "low": float(c["mid"]["l"]),
                "close": float(c["mid"]["c"])
            }
            for c in candles if c.get("complete", False)
        ])

        if not chunk_df.empty:
            chunk_df["time"] = pd.to_datetime(chunk_df["time"])
            chunk_df.set_index("time", inplace=True)
            all_candles.append(chunk_df)

        if chunk_end >= end_dt:
            break
        else:
            # Continue from chunk_end, adding a small offset to avoid overlap
            current_start = chunk_end + datetime.timedelta(seconds=1)

    if all_candles:
        final_df = pd.concat(all_candles)
        final_df = final_df[~final_df.index.duplicated(keep="first")]
        final_df.sort_index(inplace=True)
        return final_df
    else:
        return pd.DataFrame()


def fetch_multiple_pairs(
    client: API,
    instruments_list: list,
    start: str,
    end: str,
    granularity: str = "M1"   # default is M1; can be set to another timeframe
) -> dict:
    """
    Convenience function: fetch historical data for multiple currency pairs
    for a given time period and timeframe.
    
    :param client:           OANDA API client.
    :param instruments_list: List of instruments, e.g. ["EUR_USD", "GBP_USD", "AUD_USD", ...]
    :param start:            Start datetime (str or datetime).
    :param end:              End datetime (str or datetime).
    :param granularity:      Timeframe to fetch (e.g., "M1", "M15", "H1"). Default is "M1".
    :return:                 dict {instrument -> DataFrame}
    """
    data_dict = {}
    for instr in instruments_list:
        print(f"Fetching {granularity} data for {instr} from {start} to {end}...")
        df = fetch_data_for_period(client, instr, start, end, granularity)
        data_dict[instr] = df
        print(f"{instr}: fetched {len(df)} rows.")
    return data_dict

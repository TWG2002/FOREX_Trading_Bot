import os
from pathlib import Path
from dotenv import load_dotenv

# Determine the directory where config.py resides
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Retrieve environment variables
OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
OANDA_ENV = os.getenv("OANDA_ENV")

# For debugging, log these values (masking sensitive parts)
print("DEBUG: Loaded OANDA_API_KEY:", OANDA_API_KEY)
print("DEBUG: Loaded OANDA_ACCOUNT_ID:", OANDA_ACCOUNT_ID)
print("DEBUG: Loaded OANDA_ENV:", OANDA_ENV)

# =====================================
# OANDA API Settings
# =====================================
# (The values above will be used by your bot)

# =====================================
# Bot Parameters
# =====================================
RISK_PER_TRADE = 0.01             # 1% risk per trade
MAX_TRADES_PER_DAY = 5            # No more than 5 trades per day
DAILY_DRAWDOWN_LIMIT_PCT = 7.5    # Kill-switch if daily drawdown > 5%
TIMEFRAME = "M1"                  # Default timeframe for data
INSTRUMENTS = ["EUR_USD", "GBP_USD", "AUD_USD", "USD_CHF", "NZD_USD", "USD_CAD"]
MAX_POSITION_PERCENT = 0.01  
# New: Trailing stop parameter in pips (e.g., 10 pips)
TRAILING_STOP_PIPS = 17

RSI_PERIOD = 14                   # Period for RSI calculation
MACD_FAST = 12                    # Fast period for MACD
MACD_SLOW = 26                    # Slow period for MACD
MACD_SIGNAL = 9                   # Signal period for MACD
ATR_PERIOD = 14 

# =====================================
# Dynamic Position Sizing Parameters
# =====================================
BASELINE_ATR = 0.0010           # Baseline ATR value; adjust based on typical volatility
MIN_RISK_MULTIPLIER = 0.5       # Minimum risk multiplier
MAX_RISK_MULTIPLIER = 1.5       # Maximum risk multiplier

# =====================================
# Logging Settings
# =====================================
LOG_TO_FILE = True
LOG_LEVEL = "INFO"

# =====================================
# Email Alert Settings
# =====================================
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_USER = "thomaswgrierson@gmail.com"       # Replace with your email address
EMAIL_PASSWORD = "cymr vaoe lobu ahdn"        # Replace with your email or app-specific password

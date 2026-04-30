import os
from dotenv import load_dotenv

load_dotenv()

# ─── API ──────────────────────────────────────────────────────────────────────
API_KEY = os.getenv("COINSWITCH_API_KEY", "")
SECRET_KEY = os.getenv("COINSWITCH_SECRET_KEY", "")

BASE_URL = "https://coinswitch.co"

# ─── Mode ─────────────────────────────────────────────────────────────────────
TRADING_MODE = os.getenv("TRADING_MODE", "paper")   # "paper" or "live"
IS_PAPER = TRADING_MODE.lower() == "paper"

# ─── Trading Universe ─────────────────────────────────────────────────────────
# Ultra-cheap meme/micro coins — all verified on CoinSwitch EXCHANGE_2 + Binance futures.
# Sorted by 24h Binance futures volume (highest first = most liquid).
TRADING_PAIRS = [
    "1000PEPEUSDT",   # $0.004  — $303M/day volume
    "FIGHTUSDT",      # $0.004  — $43M/day
    "GALAUSDT",       # $0.003  — $42M/day
    "XANUSDT",        # $0.008  — $41M/day
    "1000BONKUSDT",   # $0.006  — $31M/day
    "BLESSUSDT",      # $0.006  — $18M/day
    "JCTUSDT",        # $0.002  — $12M/day
    "TRUUSDT",        # $0.004  — $12M/day
    "PENGUUSDT",      # $0.008  — $77M/day
    "BOMEUSDT",       # $0.0006 — $37M/day
    "MEMEUSDT",       # $0.0006 — $6M/day
    "GPSUSDT",        # $0.009  — $28M/day
]

FUTURES_EXCHANGE = "EXCHANGE_2"
BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USDT")

# ─── Risk Parameters ──────────────────────────────────────────────────────────
MAX_PORTFOLIO_RISK_PCT = float(os.getenv("MAX_PORTFOLIO_RISK", "5.0"))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE", "1.5"))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
MAX_DRAWDOWN_PCT = float(os.getenv("MAX_DRAWDOWN_PCT", "10.0"))
MAX_CONCURRENT_TRADES = 4       # allow up to 4 open trades across 12 pairs
MAX_CONSECUTIVE_LOSSES = 3      # stop trading after this many in a row

# ─── Leverage ─────────────────────────────────────────────────────────────────
DEFAULT_LEVERAGE = int(os.getenv("DEFAULT_LEVERAGE", "10"))
MAX_LEVERAGE = int(os.getenv("MAX_LEVERAGE", "15"))

# ─── Strategy Config ──────────────────────────────────────────────────────────
STRATEGY_EMA_RSI = os.getenv("STRATEGY_EMA_RSI", "true").lower() == "true"
STRATEGY_BREAKOUT = os.getenv("STRATEGY_BREAKOUT", "true").lower() == "true"
STRATEGY_MTF_TREND = os.getenv("STRATEGY_MTF_TREND", "true").lower() == "true"
STRATEGY_SR_BOUNCE = os.getenv("STRATEGY_SR_BOUNCE", "true").lower() == "true"
# ─── Selectivity profile ──────────────────────────────────────────────────────
# WIN_RATE_MODE = trade fewer, higher-quality setups. Pre-sets the gates below.
#   true  → favor win-rate (2-vote confluence, trend-aligned SR, partial @ 1R)
#   false → favor trade volume (looser, lets the agent learn faster)
WIN_RATE_MODE = os.getenv("WIN_RATE_MODE", "true").lower() == "true"

MIN_CONFLUENCE_SIGNALS = int(os.getenv("STRATEGY_MIN_CONFLUENCE", "2"))
# Average confidence of agreeing strategies must meet this (reduces weak 2-vote setups).
MIN_CONFLUENCE_AVG_CONFIDENCE = float(
    os.getenv("MIN_CONFLUENCE_AVG_CONFIDENCE", "0.60" if WIN_RATE_MODE else "0.52")
)
# Solo SR path: stricter bar so range trades are fewer but higher quality.
SOLO_SR_MIN_CONFIDENCE = float(
    os.getenv("SOLO_SR_MIN_CONFIDENCE", "0.65" if WIN_RATE_MODE else "0.58")
)
SOLO_SR_MIN_VOL_RATIO = float(os.getenv("SOLO_SR_MIN_VOL_RATIO", "1.05"))
# In WIN_RATE_MODE, only take SR_BOUNCE when the higher-TF trend isn't fighting
# us (i.e. don't short resistance during a 4H uptrend; don't buy support during
# a 4H downtrend). Trend-aligned SR has ~20-30 pp higher historical win rate.
SR_REQUIRE_TREND_ALIGNED = os.getenv(
    "SR_REQUIRE_TREND_ALIGNED", "true" if WIN_RATE_MODE else "false"
).lower() == "true"

# Solo trend path. Off by default in win-rate mode (trend solos have weaker edge
# than 2-vote confluence). Turn on if you want more trade flow for agent learning.
ALLOW_SOLO_TREND = os.getenv(
    "ALLOW_SOLO_TREND", "false" if WIN_RATE_MODE else "true"
).lower() == "true"
SOLO_TREND_MIN_CONFIDENCE = float(
    os.getenv("SOLO_TREND_MIN_CONFIDENCE", "0.70" if WIN_RATE_MODE else "0.62")
)

# ─── Win-rate trade management ────────────────────────────────────────────────
# Take partial profit when price reaches 1R and immediately move SL to entry.
# Every trade that touches 1R becomes win-or-scratch (never a loss). Single
# biggest structural boost to win rate, at the cost of slightly lower avg R.
PARTIAL_TP_AT_1R       = os.getenv("PARTIAL_TP_AT_1R",       "true" if WIN_RATE_MODE else "false").lower() == "true"
MOVE_SL_TO_BE_AT_1R    = os.getenv("MOVE_SL_TO_BE_AT_1R",    "true" if WIN_RATE_MODE else "false").lower() == "true"
PARTIAL_TP_AT_1R_RATIO = float(os.getenv("PARTIAL_TP_AT_1R_RATIO", "0.5"))   # 50% off at 1R

# ─── Confluence quality (DMI + regime) ────────────────────────────────────────
REQUIRE_DI_ALIGNMENT = os.getenv("REQUIRE_DI_ALIGNMENT", "true").lower() == "true"
# Skip entries in tight BB compression unless an SR_BOUNCE vote is present (chop filter).
USE_CHOP_FILTER = os.getenv("USE_CHOP_FILTER", "true").lower() == "true"
CHOP_BB_WIDTH_VS_MA_RATIO = float(os.getenv("CHOP_BB_WIDTH_VS_MA_RATIO", "0.72"))
# "weighted" = confidence-weighted TP (better R multiple on wins); "conservative" = old min/max merge.
CONFLUENCE_TP_MERGE_MODE = os.getenv("CONFLUENCE_TP_MERGE_MODE", "weighted").lower()
CONFLUENCE_MIN_RR = float(os.getenv("CONFLUENCE_MIN_RR", "1.5"))
CONFLUENCE_MAX_RR = float(os.getenv("CONFLUENCE_MAX_RR", "4.5"))

# ─── Hype / Momentum Filter ───────────────────────────────────────────────────
# Meme coins are driven by hype. Only take signals when at least one hype
# dimension is green, and bail when funding is at stretched extremes.
USE_HYPE_FILTER = True
HYPE_VOL_RATIO_MIN   = 1.0   # at/above average volume
FUNDING_EXTREME_POS  = 0.0008   # +0.08% per 8h → crowd leveraged long; fade longs
FUNDING_EXTREME_NEG  = -0.0008  # −0.08% per 8h → crowd leveraged short; fade shorts
OI_DELTA_MIN_PCT     = 0.5   # open interest moving >= 0.5% over last 4 bars
# UTC dead-zone (Asia close → EU open). Skip brand-new trades in this window.
DEADZONE_UTC_START   = 2     # 02:00 UTC
DEADZONE_UTC_END     = 6     # 06:00 UTC

# ─── Support / Resistance ─────────────────────────────────────────────────────
SR_LOOKBACK           = 80     # bars to scan for swing highs/lows
SR_PROXIMITY_PCT      = 0.010  # 1.0% — "near" a level (meme coins are volatile)
SR_SL_BUFFER_PCT      = 0.005  # 0.5% beyond the level for SL

# ─── Timeframes ───────────────────────────────────────────────────────────────
PRIMARY_TF = "15m"       # main trading timeframe
CONFIRM_TF = "1h"        # confirmation timeframe
TREND_TF = "4h"          # trend definition timeframe
EXECUTION_TF = "5m"      # entry precision timeframe

CANDLE_LIMIT = 200       # candles to fetch per timeframe

# ─── Indicator Settings ───────────────────────────────────────────────────────
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
EMA_TREND = 200

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
RSI_BULL_THRESHOLD = 55
RSI_BEAR_THRESHOLD = 45

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5    # stop loss = entry ± (ATR × multiplier)
ATR_TP_MULTIPLIER = 3.0    # take profit = entry ± (ATR × multiplier)

ADX_PERIOD = 14
# 18 is the textbook number for liquid majors; on low-vol meme perps ADX
# rarely climbs above 20 even during clean runs. 16 keeps the filter useful
# (still rejects pure chop) without nuking borderline-trending tape.
ADX_TREND_THRESHOLD = int(os.getenv("ADX_TREND_THRESHOLD", "16"))

BB_PERIOD = 20
BB_STD = 2.0

VOLUME_MA_PERIOD = 20
VOLUME_BREAKOUT_MULT = 1.5  # volume must be 1.5x avg for breakout confirm

# ─── Order Settings ───────────────────────────────────────────────────────────
LIMIT_ORDER_SLIPPAGE = 0.001   # 0.1% slippage tolerance for limit orders
PARTIAL_TP_RATIO = 0.5         # close 50% at TP1, let 50% ride
MIN_ORDER_SIZE_USDT = 2.0      # minimum order value in USDT (small-account friendly)

# ─── Fees & Tax (CoinSwitch Futures, India) ───────────────────────────────────
# All percentages here are in **percent units** (0.05 means 0.05%, NOT 5%).
# Override every one of these from .env to match your actual statement.
TAKER_FEE_PCT  = float(os.getenv("TAKER_FEE_PCT",  "0.05"))   # platform fee/side
MAKER_FEE_PCT  = float(os.getenv("MAKER_FEE_PCT",  "0.05"))
GST_PCT        = float(os.getenv("GST_PCT",        "18.0"))   # GST on the fee
TDS_PCT        = float(os.getenv("TDS_PCT",        "1.0"))    # India VDA TDS
# How TDS is billed by CoinSwitch:
#   sell_only — TDS on the sell leg only (default; matches typical billing)
#   both      — TDS on both legs (worst-case)
#   off       — no TDS (non-India / broker absorbs it)
TDS_MODE       = os.getenv("TDS_MODE", "sell_only").lower()
# Most market entries cross the spread → taker. Set false if you use limit-makers.
ASSUME_TAKER   = os.getenv("ASSUME_TAKER", "true").lower() == "true"

# Wire fees into the rest of the bot.
INCLUDE_FEES_IN_SIZING = os.getenv("INCLUDE_FEES_IN_SIZING", "true").lower() == "true"
INCLUDE_FEES_IN_RR     = os.getenv("INCLUDE_FEES_IN_RR",     "true").lower() == "true"
# Backtester realism — apply costs to each simulated trade's PnL.
BACKTEST_APPLY_FEES    = os.getenv("BACKTEST_APPLY_FEES",    "true").lower() == "true"

# ─── Logging / Monitoring ─────────────────────────────────────────────────────
LOG_DIR = "logs"
DATA_DIR = "data"
LOG_LEVEL = "INFO"

# ─── Polling Intervals ────────────────────────────────────────────────────────
SIGNAL_CHECK_INTERVAL = 60     # seconds between signal scans
POSITION_CHECK_INTERVAL = 30   # seconds between position checks
MARKET_DATA_INTERVAL = 10      # seconds between price updates

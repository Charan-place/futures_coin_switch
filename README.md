# Futures Coin Switch

An autonomous cryptocurrency futures trading bot for CoinSwitch Futures. Targets high-volume meme coins and micro-cap tokens using a multi-strategy confluence engine with an online learning agent that improves trade selection over time.

## Features

- **4 Strategies**: EMA+RSI crossover, volume breakout, multi-timeframe trend, support/resistance bounce
- **Confluence Engine**: Requires ≥2 strategies to agree; hype filter, chop filter, trend alignment
- **Online Learning**: Contextual bandit agent tracks per-(strategy, symbol) win rate and R-multiple; adjusts confidence ±40%
- **Risk Management**: Per-trade sizing, portfolio risk cap, daily loss limit, drawdown protection, consecutive-loss circuit breaker
- **Fee-Aware**: Accounts for taker fees, GST (18%), and India TDS (1% on notional) in sizing and take-profit targets
- **Paper & Live Modes**: Same logic and risk management in both
- **Backtester**: Replay historical candles through the full pipeline with honest fee-adjusted P&L
- **Rich Terminal Dashboard**: Portfolio, open trades, signal log, bot log — all live

## Tech Stack

- **Language**: Python 3.11+
- **Indicators**: TA-Lib, pandas, numpy
- **API**: CoinSwitch Futures REST (EXCHANGE_2)
- **UI**: Rich terminal dashboard
- **Learning**: Custom EWMA contextual bandit

## Default Trading Pairs

`1000PEPEUSDT`, `FIGHTUSDT`, `GALAUSDT`, `XANUSDT`, `1000BONKUSDT`, `BLESSUSDT`, `JCTUSDT`, `TRUUSDT`, `PENGUUSDT`, `BOMEUSDT`, `MEMEUSDT`, `GPSUSDT`

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
COINSWITCH_API_KEY=your_key
COINSWITCH_SECRET_KEY=your_secret
TRADING_MODE=paper            # paper | live
MAX_PORTFOLIO_RISK=5.0        # max % of account at risk
RISK_PER_TRADE=1.5            # % risked per trade
DEFAULT_LEVERAGE=10
```

## Run

```bash
# Paper trading (simulated, safe to start)
python main.py --paper

# Paper with custom balance
python main.py --paper --balance 5000

# Live trading (real money — shows 5s warning)
python main.py --live

# Backtest a symbol
python main.py --backtest --symbol PENGUUSDT --tf 15m

# Backtest from CSV
python main.py --backtest --symbol PENGUUSDT --tf 15m --csv candles.csv
```

## Key Configuration

All settings in `config/settings.py`, overridable via `.env`:

| Setting | Default | Description |
|---|---|---|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `RISK_PER_TRADE` | 1.5% | % risked per trade |
| `MAX_PORTFOLIO_RISK` | 5.0% | Max simultaneous account exposure |
| `DEFAULT_LEVERAGE` | 10x | Starting leverage (max 15x) |
| `STRATEGY_MIN_CONFLUENCE` | 2 | Min strategies that must agree |
| `WIN_RATE_MODE` | true | Favor fewer, higher-conviction trades |
| `PARTIAL_TP_AT_1R` | true | Close 50% at 1R, move SL to entry |
| `CONFLUENCE_MIN_RR` | 1.5 | Minimum gross risk:reward ratio |
| `TDS_PCT` | 1.0% | India TDS on notional |

## Fee Reality Check

With India TDS (1%) + GST (18% on 0.05% taker fee), round-trip cost is ~**1.1% of notional**. Verify before going live:

```bash
python -c "from core.fees import from_settings; fm = from_settings(); print(round(fm.round_trip_cost_pct('LONG')*100, 3), '%')"
```

## Agent Learning

The bot learns which (strategy, symbol) pairs have an edge. State persists across restarts in `data/agent_state.json`. Inspect it to see win rates and R-multiples per arm. Cold-start multiplier is 1.0 until 5+ trades on an arm.

## Risk Warning

Futures trading with leverage can result in losses exceeding your initial deposit. Always start in paper mode. This is not financial advice.

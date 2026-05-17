# Quick Start — Meme Coin Scalp Bot

## Setup (one-time)

```bash
cd /Users/nsatyasaicharan/Desktop/personal/auto_coin_switch
source venv/bin/activate
cp .env.example .env
# Edit .env: add COINSWITCH_API_KEY and COINSWITCH_SECRET_KEY (for live only)
```

---

## Run modes

### Paper (test without real money)

```bash
# Default: $1000 balance
python main.py --paper

# Custom balance
python main.py --paper --balance 5000
```

Scalp + Pump strategies run automatically on 5m candles. Swing strategies run on 15m.

### Live (real money — WARNING)

```bash
# Shows 5-second countdown before executing real trades
python main.py --live --balance 5000

# Or set TRADING_MODE=live in .env, then:
python main.py
```

**Before going live:**
- Test paper mode for at least 2-3 days (50+ trades)
- Verify `.env` API keys work (bot logs "Fees discovered" on startup if keys OK)
- Understand the fee breakdown:
  ```bash
  python -c "from core.fees import from_settings; \
  fm = from_settings(); \
  print('Round-trip cost:', round(fm.round_trip_cost_pct('LONG')*100, 2), '% of notional')"
  ```
- Know your min viable move: ~1.3% (breakeven after fees)

---

## Key configs (.env)

| Setting | Default | Purpose |
|---------|---------|---------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `STRATEGY_SCALP` | `true` | 5m scalp momentum (VWAP+Supertrend) |
| `STRATEGY_PUMP` | `true` | 5m pump detector (volume spike) |
| `USE_TRAILING_STOP` | `true` | Trail 1 ATR once 2R is hit |
| `RISK_PER_TRADE_PCT` | `1.5` | Max risk per trade |
| `MAX_CONCURRENT_TRADES` | `4` | Max open trades |
| `DEFAULT_LEVERAGE` | `10` | Leverage (be careful!) |

---

## What to watch

**Bot Log** (live panel when running):
- Shows every signal, why trades are rejected, fees on each trade
- Format: `[SYMBOL] strategy_name → LONG/SHORT conf=X | reason`

**Portfolio** (live panel):
- Total balance, daily P&L, win rate, max drawdown
- Current open trades + unrealized P&L

**Hype Filter** (live panel):
- Volume ratio, funding rate, open interest delta
- If funding is extreme, longs/shorts get vetoed

---

## Troubleshooting

### No signals for hours
Check:
- `ADX < 16` (no trend) — scalp/pump need trend or volume spike
- `vol_ratio < 1.8` (quiet market) — scalp gate is 1.8x average
- Hype filter vetoed (check bot log for "hype BLOCK — ...")

### Losing trades
Meme coins are volatile. Expected on this strategy:
- ~40-50% win rate (typical for directional trading)
- 2:1 R:R on winners, -1R on losers → breakeven at 33% win rate
- Trailing stop should help ride big wins

### API errors
- Verify keys in `.env` are correct (copy-paste exactly)
- Check CoinSwitch account has open-orders permission on API key
- If live, ensure account has funds

---

## Commands cheat sheet

```bash
# Paper (simple)
python main.py --paper

# Paper (custom balance)
python main.py --paper --balance 5000

# Live (real money!)
python main.py --live

# Live with custom balance
python main.py --live --balance 5000

# Backtest on historical data
python main.py --backtest --symbol PENGUUSDT --tf 15m

# Backtest with your CSV
python main.py --backtest --symbol PENGUUSDT --tf 15m --csv data.csv

# Disable scalp, run swing only
STRATEGY_SCALP=false STRATEGY_PUMP=false python main.py --paper

# Verify fees
python -c "from core.fees import from_settings; fm=from_settings(); print('RT cost:', round(fm.round_trip_cost_pct('LONG')*100, 2), '%')"

# Check agent learning (see what strategies are winning)
cat data/agent_state.json | head -50
```

---

## What the strategies do

### SCALP_MOMENTUM (5m)
**When:** Supertrend bullish + price above VWAP + StochK rising from low + volume >1.8x

**Why:** Clean directional setup with volume confirmation. Enter when momentum is just starting to accelerate.

**Exit:** 2 ATR TP or trailing stop (whichever hits first). SL at 0.6 ATR (tight).

### PUMP_DETECTOR (5m)
**When:** Volume >3x avg + price moved ±0.8% in 3 bars + RSI not extended + VWAP reclaim

**Why:** Early pump detection. Volume spike = institutional involvement or retail frenzy.

**Exit:** 4 ATR TP (ride the wave) or trailing stop. SL at bar low (very tight on pump entry).

### Swing strategies (15m)
EMA crosses, breakouts, multi-timeframe trend, S/R bounces. Same as before, still run every 60s.

---

## Fee reality (India)

Each round-trip trade costs ~**1.1-1.3% of notional**:
- Platform fee: 0.05% × 2 sides = 0.10%
- GST 18% on fee = +0.018%
- TDS 1% on sell notional = 1.0%
- **Total ≈ 1.118% of notional**

**At 10x leverage:** 1.12% × 10 = **11.2% of your capital per trade**

**Minimum profitable move:** ~1.3% (to cover costs)

**Why 10x?** With meme coins at $0.001–$0.01, you need leverage to get meaningful position size. Just be aware of the cost burden.

Bot accounts for this automatically:
- Sizes positions so SL loss = RISK_PER_TRADE_PCT after costs
- Stretches TPs so net R:R hits CONFLUENCE_MIN_RR (1.5) after fees
- Skips trades where TP barely covers costs

---

## Next steps

1. **Paper test:** `python main.py --paper --balance 5000` for 1-2 weeks
2. **Review backtest:** `python main.py --backtest` to see historical equity curve
3. **Check agent stats:** `cat data/agent_state.json` to see which strategies are winning
4. **Go live:** `python main.py --live --balance 5000` (start small!)

Good luck! 🚀

# How to run the bot

From the project root (`auto_coin_switch/`):

```bash
cd /path/to/auto_coin_switch
source venv/bin/activate   # or: ./venv/bin/python ...
```

Ensure `.env` exists (copy from `.env.example` and fill in API keys). The bot reads `TRADING_MODE` from `.env` when you do **not** pass `--paper` or `--live`.

---

## Paper mode (simulated trades)

**Option A — force paper (ignores `TRADING_MODE` in `.env`):**

```bash
python main.py --paper
```

**Option B — use `.env`:** set `TRADING_MODE=paper`, then:

```bash
python main.py
```

**Optional:** starting paper balance (default `1000`):

```bash
python main.py --paper --balance 1000
```

---

## Live mode (real orders — use only when ready)

1. Confirm `.env` has valid `COINSWITCH_API_KEY` and `COINSWITCH_SECRET_KEY`.
2. Prefer setting `TRADING_MODE=live` in `.env` **or** use the flag below (flag overrides the default branch but you should still keep keys correct).

**Force live (shows a 5-second warning, then connects for real):**

```bash
python main.py --live
```

**Optional:** explicit starting balance reference for risk sizing in paper-like accounting where applicable:

```bash
python main.py --live --balance 1000
```

Stop the bot with **Ctrl+C**.

---

## Backtest (historical / fetched candles — not live trading)

```bash
python main.py --backtest --symbol PENGUUSDT --tf 15m
```

With a CSV (columns like `open,high,low,close,volume`; index = time):

```bash
python main.py --backtest --symbol PENGUUSDT --tf 15m --csv path/to/candles.csv
```

---

## Quick reference

| Goal              | Command                          |
|-------------------|----------------------------------|
| Paper (explicit)  | `python main.py --paper`         |
| Paper (from .env) | `TRADING_MODE=paper` → `python main.py` |
| Live              | `python main.py --live`          |
| Backtest          | `python main.py --backtest --symbol <PAIR> --tf 15m` |

Use a symbol from `config/settings.py` (`TRADING_PAIRS`) in the form your exchange expects (e.g. `PENGUUSDT`).

---

## Fees & Tax (CoinSwitch Futures, India)

Every trade on CoinSwitch incurs three deductions that the bot now factors in
before placing an order:

| Component | Default | Where in `.env` |
|-----------|---------|------------------|
| Platform fee (taker) | `0.05%` per side | `TAKER_FEE_PCT` |
| Platform fee (maker) | `0.05%` per side | `MAKER_FEE_PCT` |
| GST on the fee       | `18%`            | `GST_PCT`       |
| TDS on VDA           | `1%`             | `TDS_PCT` + `TDS_MODE` |

**Critical insight:** TDS is charged on **notional**, not on profit. With 10×
leverage, a "1% risk" trade can easily eat **2–3% of your balance** in costs
alone if TDS is ignored. The bot now:

1. **Sizes positions** (`risk_manager.calculate_position_size`) so the
   stop-loss really only loses ~`RISK_PER_TRADE_PCT` after costs, not before.
2. **Stretches take-profits** (`confluence_engine._weighted_take_profit`) so
   the **net** R:R after fees + GST + TDS hits `CONFLUENCE_MIN_RR`.
3. **Refuses** any trade whose TP barely covers fees + TDS (executor logs
   `TP barely covers fees+TDS`).
4. **Backtests with fees applied** when `BACKTEST_APPLY_FEES=true` so
   simulated PnL matches what you'd actually see.

### Verifying the numbers

Run this once after editing `.env` to see the actual round-trip cost:

```bash
./venv/bin/python -c "from core.fees import from_settings; \
fm = from_settings(); \
print('round-trip cost % of notional:', round(fm.round_trip_cost_pct('LONG')*100, 3), '%')"
```

If the figure looks high vs. your real CoinSwitch invoice, override
`TAKER_FEE_PCT` / `TDS_MODE` / `TDS_PCT` in `.env` to match reality.

### Knobs

```bash
TAKER_FEE_PCT=0.05            # platform fee/side; check your CoinSwitch tier
MAKER_FEE_PCT=0.05
GST_PCT=18.0                  # India GST on the fee, 18%
TDS_PCT=1.0                   # India 1% TDS on VDA
TDS_MODE=sell_only            # sell_only | both | off
ASSUME_TAKER=true             # market orders → taker

INCLUDE_FEES_IN_SIZING=true   # SL loss = risk budget *after* costs
INCLUDE_FEES_IN_RR=true       # TP stretched to hit min RR after costs
BACKTEST_APPLY_FEES=true      # honest backtest PnL
```

### What you should see in the logs

For each trade attempt, the executor now prints:

```
Executing LONG PENGUUSDT | qty=… entry=… SL=… TP=…
  Costs SL: fee=$… GST=$… TDS=$… (1.14% of notional)
  Net @ SL: -$10.00 (1.00% of bal) | Net @ TP: +$15.00 | Net R:R=1.50
```

If `Net @ TP` is close to zero the trade is **skipped** automatically — the
strategy must find moves big enough to clear costs.

### Practical implication

With ~1% TDS on notional, **strategies that win on small moves are unlikely
to be profitable on Indian crypto futures**. To improve net P&L:

1. Lower leverage (smaller notional → smaller absolute fees/TDS).
2. Wider stops (so price-risk is large vs. cost-risk).
3. Higher confluence (let only the best setups through — see
   `MIN_CONFLUENCE_AVG_CONFIDENCE`, `STRATEGY_MIN_CONFLUENCE`).
4. If you ever take futures on a non-Indian exchange, set `TDS_MODE=off`.

### Live fee discovery

You don't have to hard-code the percentages. On startup the bot calls
CoinSwitch and tries to learn the real schedule:

1. `client.get_fee_schedule(symbol)` — reads `taker_commission` /
   `maker_commission` from `instrument_info`.
2. `client.parse_fees_from_transactions(symbol)` — back-out the *actual*
   effective cost % from your last few real fills (`fee + tds + gst`
   ÷ `notional`). This is ground truth and overrides anything else.

What was learned shows up in the Bot Log on startup:

```
INFO main: Discovering live fees from CoinSwitch API…
INFO main: Fees discovered: FeeModel(transactions:PENGUUSDT(3)): … round-trip ≈ 1.094%
```

If discovery fails (no key, market not yet traded, endpoint shape change),
the env values remain as the fallback — no crash.

---

## Step-by-step logs (Bot Log panel)

The dashboard now contains a live "Bot Log (step-by-step)" panel that
captures every decision the bot makes — fetch, indicator readings, each
strategy's vote, confluence verdict, hype filter, and execution costs.

You'll see lines like:

```
[1000PEPEUSDT] fetching candles 15m/1h/4h
[1000PEPEUSDT] enriched [15m,1h,4h] price=0.0042 ADX=22.7 RSI=58.1 vol=1.31x
[1000PEPEUSDT] EMA_RSI → LONG conf=0.65 | EMA9 crossed above EMA21 …
[1000PEPEUSDT] votes: EMA_RSI=LONG(0.65) BREAKOUT=∅ MTF_TREND=LONG(0.70) SR_BOUNCE=∅
[1000PEPEUSDT] hype OK — vol=1.31x oi_Δ=+0.42% fund=-0.001% bias=neutral
[1000PEPEUSDT] SIGNAL FIRED: LONG conf=0.78 R:R=2.10
  Costs SL: fee=$0.42 GST=$0.07 TDS=$2.10 (1.10% of notional)
  Net @ SL: -$10.00 (1.00% of bal) | Net @ TP: +$15.40 | Net R:R=1.54
```

If a symbol is silent ("no qualifying setup"), you'll see the precise
reason it was rejected — `reject — ADX=14.2<18, no SR vote`,
`reject — DMI not aligned with LONG`, etc. No more guessing.

---

## Agent (online learner)

After every closed trade the bot updates a per-(strategy, symbol)
performance arm:

* EWMA win-rate
* EWMA R-multiple (cost-aware — uses **net** PnL ÷ risk-amount)
* Trial / win / loss counts

The next time that strategy fires on that symbol, its raw confidence
gets multiplied by:

```
1 + tanh(0.7·ewma_R + 0.3·(2·ewma_winrate − 1)) · 0.4
```

(within `[0.6, 1.4]`). Below 5 closed trades on an arm, multiplier is
exactly `1.0` — no opinion until there's data.

State is persisted to `data/agent_state.json` after every update, so
learning survives restarts. Inspect or reset it any time:

```bash
cat data/agent_state.json | head -40

rm data/agent_state.json   # reset learning
```

The dashboard shows a one-line agent summary in the Portfolio panel
(`trades_seen / arms_total / arms_learned / global_pnl`).

### Why bandit, not deep RL?

Deep RL (DQN/PPO) needs ~10⁴+ episodes to converge and overfits hard
on 12 noisy meme coins. The contextual-bandit + EWMA approach used
here is the standard for "online decision under delayed reward with
limited samples" (ad-ranking, slot-tuning, order-routing). It is
fully transparent (read `agent_state.json`) and degrades gracefully
when data is sparse.

# Meme Coin Trading Hours (CoinSwitch Futures)

## When memes move

| Hour UTC | Activity | Volume | Notes |
|----------|----------|--------|-------|
| **00:00–08:00** | Slow | Low | Asia sleeping, US closed. Dead time. |
| **08:00–10:00** | Waking up | Medium | US opens. Crypto momentum building. |
| **10:00–14:00** | **PRIME TIME** | **High** | **US morning peak. Best pump action.** |
| **14:00–16:00** | Afternoon | Medium | US afternoon. Still decent. |
| **16:00–22:00** | Evening | Low | US market fatigue, Asia sleep. |
| **22:00–00:00** | Dead | Very low | End of day, next morning prep. |

## What this means for the bot

**Volume gates require actual trading activity:**
- SCALP_MOMENTUM: vol_ratio ≥ 1.8x (needs avg 500k → spike to 900k on 5m)
- PUMP_DETECTOR: vol_ratio ≥ 3.0x (needs avg 500k → spike to 1.5M on 5m)

**Outside prime hours (10:00–14:00 UTC):**
- Vol spikes won't happen → strategies won't fire
- That's **intentional** — don't trade dead markets
- Fees eat you alive in quiet tape (1.13% round-trip)

## Your testing schedule

**If testing paper now:**
- ✅ **Do:** run live to see rejection reasons in logs
- ✅ **Do:** test backtest mode on historical data
- ❌ **Don't:** expect trades during dead hours

**To test live with real signals:**
1. Start bot at **08:00 UTC** (2am ET)
2. Run until **16:00 UTC** (11am ET)
3. Then stop (volume dies off)

## Quick backtest

```bash
python main.py --backtest --symbol PENGUUSDT --tf 5m
```

This runs the last 500 5m candles (≈1.7 days) through the bot using historical data. You'll see signal fired / closed trades / P&L.

## Fee reality (why quiet markets lose money)

If avg volume on a pair is 300k/5m:
- Scalp gate: needs 300k × 1.8 = 540k ← rare outside prime hours
- Pump gate: needs 300k × 3.0 = 900k ← almost never

And even when vol is OK, your position cost is **1.13% round-trip**. A move needs to be ≥1.3% to profit. Meme coins during US hours do that. During Asia hours? No.

---

## Summary

**Bot is not broken. Market is just slow right now (19:46 UTC).**

Run it during these windows:
- **Best:** 10:00–14:00 UTC (US morning)
- **OK:** 08:00–16:00 UTC (US day)
- **Bad:** 16:00–08:00 UTC (Asia / US closed)

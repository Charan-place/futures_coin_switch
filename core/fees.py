"""
Fee + Tax model for CoinSwitch Futures (India)
───────────────────────────────────────────────
Every round-trip trade has these costs that the bot must factor into:
  • position sizing (so a stop-loss really only loses ~RISK_PER_TRADE_PCT)
  • take-profit placement (so a "winner" is actually positive after costs)
  • backtest PnL (so historical results aren't optimistic)

Cost components (configurable in .env, since CoinSwitch fee tiers + Indian
tax treatment can change):
  • Trading fee   — taker/maker % of NOTIONAL on each side (entry + exit)
  • GST           — 18% on the trading fee (not the notional)
  • TDS           — 1% on the SELL-side notional (India). Configurable so
                    you can model: applied both sides / sell only / disabled.

NOTE — none of these numbers are universal truth. CoinSwitch publishes their
fee schedule per market and TDS treatment for futures has changed over time.
The defaults are conservative; verify against your own CoinSwitch invoice
and override via .env. See `RUN.md` → "Fees & Tax" section.
"""
from dataclasses import dataclass


@dataclass
class TradeCosts:
    entry_fee: float           # platform fee on entry (USDT/INR)
    exit_fee: float            # platform fee on exit
    gst: float                 # 18% × (entry_fee + exit_fee)
    tds: float                 # TDS as configured
    total: float               # sum of the above
    pct_of_notional: float     # total / entry_notional × 100

    def as_dict(self) -> dict:
        return {
            "entry_fee":  round(self.entry_fee, 4),
            "exit_fee":   round(self.exit_fee, 4),
            "gst":        round(self.gst, 4),
            "tds":        round(self.tds, 4),
            "total":      round(self.total, 4),
            "pct_notional": round(self.pct_of_notional, 4),
        }


class FeeModel:
    """
    All percentages are in **percent units** (0.05 means 0.05%, NOT 5%).

    `tds_mode` options:
      • "sell_only" — TDS on sell-side notional only (default; matches
                       how Indian VDA TDS is typically billed)
      • "both"      — TDS on both legs (worst-case)
      • "off"       — TDS disabled (e.g. broker absorbs it, or you're
                       modelling a non-Indian setup)
    """

    def __init__(
        self,
        taker_fee_pct: float = 0.05,
        maker_fee_pct: float = 0.05,
        gst_pct: float = 18.0,
        tds_pct: float = 1.0,
        tds_mode: str = "sell_only",
        assume_taker: bool = True,
    ):
        self.taker_fee_pct = taker_fee_pct
        self.maker_fee_pct = maker_fee_pct
        self.gst_pct = gst_pct
        self.tds_pct = tds_pct
        self.tds_mode = tds_mode.lower()
        self.assume_taker = assume_taker
        self.source = "config"           # config | instrument_info | transactions
        self.last_discovery_at: float = 0.0

    # ── live discovery ──────────────────────────────────────────────────────

    def discover_from_api(self, client, symbols=None) -> bool:
        """
        Pull live fee data from CoinSwitch. Tries two paths:
          1) instrument_info — published taker/maker percentages
          2) transactions    — back out the *effective* cost % from real fills,
                                which is ground truth (includes TDS+GST)

        `client` is a CoinSwitchClient. `symbols` is a list of futures
        symbols to probe; the first that returns usable data wins.
        Returns True if anything was learned.
        """
        import time as _time
        if symbols is None:
            try:
                from config.settings import TRADING_PAIRS
                symbols = TRADING_PAIRS[:3]
            except Exception:
                symbols = []

        for sym in symbols:
            try:
                fees = client.get_fee_schedule(sym)
            except Exception:
                fees = None
            if fees:
                if "taker_pct" in fees:
                    self.taker_fee_pct = fees["taker_pct"]
                if "maker_pct" in fees:
                    self.maker_fee_pct = fees["maker_pct"]
                self.source = f"instrument_info:{sym}"
                self.last_discovery_at = _time.time()
                return True

        for sym in symbols:
            try:
                eff = client.parse_fees_from_transactions(sym)
            except Exception:
                eff = None
            if eff and eff.get("samples", 0) > 0:
                # Effective % already includes fee+gst+tds — fold it in by
                # treating it as a "synthetic taker fee" with TDS off.
                self.taker_fee_pct = eff["effective_cost_pct"] / 2.0
                self.maker_fee_pct = eff["effective_cost_pct"] / 2.0
                self.gst_pct = 0.0
                self.tds_mode = "off"
                self.source = f"transactions:{sym}({eff['samples']})"
                self.last_discovery_at = _time.time()
                return True

        return False

    def describe(self) -> str:
        return (
            f"FeeModel({self.source}): taker={self.taker_fee_pct}% "
            f"maker={self.maker_fee_pct}% gst={self.gst_pct}% "
            f"tds={self.tds_pct}% mode={self.tds_mode} "
            f"→ round-trip ≈ {self.round_trip_cost_pct('LONG')*100:.3f}%"
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def per_side_fee_pct(self) -> float:
        """Effective platform fee per side as a fraction (0.0005 = 0.05%)."""
        pct = self.taker_fee_pct if self.assume_taker else self.maker_fee_pct
        return pct / 100.0

    @property
    def gst_multiplier(self) -> float:
        """GST as fraction of the fee. 18% → 0.18."""
        return self.gst_pct / 100.0

    @property
    def tds_fraction(self) -> float:
        """TDS as fraction of notional, 0 if disabled."""
        if self.tds_mode == "off":
            return 0.0
        return self.tds_pct / 100.0

    # ── core math ────────────────────────────────────────────────────────────

    def round_trip_cost(
        self,
        entry_price: float,
        exit_price: float,
        quantity: float,
        side: str,
    ) -> TradeCosts:
        """
        Compute total round-trip cost for a closed trade.
        side: "LONG" or "SHORT" (only matters for which leg is the sell).
        """
        side = side.upper()
        entry_notional = entry_price * quantity
        exit_notional  = exit_price  * quantity

        fee_pct = self.per_side_fee_pct
        entry_fee = entry_notional * fee_pct
        exit_fee  = exit_notional  * fee_pct

        gst = (entry_fee + exit_fee) * self.gst_multiplier

        # TDS: applied to sell-side notional in India.
        # LONG  → sell happens at exit
        # SHORT → sell happens at entry (you sell-to-open)
        tds = 0.0
        tds_frac = self.tds_fraction
        if tds_frac > 0:
            if self.tds_mode == "both":
                tds = (entry_notional + exit_notional) * tds_frac
            else:  # sell_only
                if side == "LONG":
                    tds = exit_notional * tds_frac
                else:
                    tds = entry_notional * tds_frac

        total = entry_fee + exit_fee + gst + tds
        pct = (total / entry_notional * 100.0) if entry_notional > 0 else 0.0
        return TradeCosts(entry_fee, exit_fee, gst, tds, total, pct)

    # ── what the strategy layer needs ────────────────────────────────────────

    def round_trip_cost_pct(self, side: str) -> float:
        """
        Estimated round-trip cost as a **fraction of notional**, assuming
        entry_price ≈ exit_price (a small approximation around break-even).
        Used by the engine to push TP outward and inflate sizing risk.
        """
        side = side.upper()
        fee = 2 * self.per_side_fee_pct                       # entry + exit fees
        gst = fee * self.gst_multiplier                       # GST on those fees
        tds_frac = self.tds_fraction
        if self.tds_mode == "both":
            tds = 2 * tds_frac
        elif self.tds_mode == "sell_only":
            tds = tds_frac
        else:
            tds = 0.0
        return fee + gst + tds

    def stop_loss_cost_per_unit(
        self, entry_price: float, stop_loss: float, side: str
    ) -> float:
        """
        Estimated cost charged per unit of `quantity` if the trade is stopped
        out at `stop_loss`. Used by the risk manager to pre-budget costs into
        position sizing.
        """
        side = side.upper()
        fee_pct = self.per_side_fee_pct
        gst_m   = self.gst_multiplier
        tds_frac = self.tds_fraction

        entry_fee_per_unit = entry_price * fee_pct
        exit_fee_per_unit  = stop_loss   * fee_pct
        gst_per_unit       = (entry_fee_per_unit + exit_fee_per_unit) * gst_m

        tds_per_unit = 0.0
        if self.tds_mode == "both":
            tds_per_unit = (entry_price + stop_loss) * tds_frac
        elif self.tds_mode == "sell_only" and tds_frac > 0:
            tds_per_unit = (stop_loss if side == "LONG" else entry_price) * tds_frac

        return entry_fee_per_unit + exit_fee_per_unit + gst_per_unit + tds_per_unit


# ── module-level singleton bound to settings ────────────────────────────────-

def from_settings():
    """Build a FeeModel from `config/settings.py` values."""
    from config.settings import (
        TAKER_FEE_PCT, MAKER_FEE_PCT, GST_PCT, TDS_PCT, TDS_MODE, ASSUME_TAKER,
    )
    return FeeModel(
        taker_fee_pct=TAKER_FEE_PCT,
        maker_fee_pct=MAKER_FEE_PCT,
        gst_pct=GST_PCT,
        tds_pct=TDS_PCT,
        tds_mode=TDS_MODE,
        assume_taker=ASSUME_TAKER,
    )

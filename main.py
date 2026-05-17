"""
CoinSwitch Futures Autonomous Trading Bot
─────────────────────────────────────────
Runs a continuous loop:
  1. Fetch multi-timeframe OHLCV for all trading pairs
  2. Enrich with indicators
  3. Run confluence engine — all 3 strategies must agree
  4. Size and execute trades with SL + TP
  5. Monitor open positions for SL/TP (paper) or rely on exchange (live)
  6. Display live dashboard

Usage:
  python main.py            → run bot (mode from .env)
  python main.py --backtest → run backtest on BTC/USDT
  python main.py --paper    → force paper mode
"""
import time
import signal as os_signal
import argparse
import sys
from typing import Dict, List
from datetime import datetime

from config.settings import (
    TRADING_PAIRS, TRADING_MODE, IS_PAPER,
    SIGNAL_CHECK_INTERVAL, SCALP_CHECK_INTERVAL, POSITION_CHECK_INTERVAL,
    PRIMARY_TF, CONFIRM_TF, TREND_TF, SCALP_TF,
    STRATEGY_SCALP, STRATEGY_PUMP,
)
from core.api_client import CoinSwitchClient
from core.data_fetcher import DataFetcher, PaperDataFetcher
from indicators.technical import enrich
from strategies.confluence_engine import ConfluenceEngine
from risk.risk_manager import RiskManager
from execution.trade_executor import TradeExecutor
from monitoring.dashboard_simple import render_dashboard_simple
from monitoring.logger import get_logger
from monitoring.log_buffer import install_buffered_handler, silence_stdout_logging

install_buffered_handler()
logger = get_logger("main")


class TradingBot:
    def __init__(self, mode: str = TRADING_MODE, initial_balance: float = 1000.0):
        self.mode = mode
        self.running = False
        self.signal_log: List[str] = []

        logger.info(f"Initializing bot in {mode.upper()} mode (balance=${initial_balance:,.2f})")

        self.client = CoinSwitchClient()

        if mode == "paper":
            self.fetcher = PaperDataFetcher(self.client, initial_balance)
        else:
            self.fetcher = DataFetcher(self.client)

        self.risk_mgr   = RiskManager(initial_balance)
        self.executor   = TradeExecutor(self.client, self.risk_mgr)
        self.confluence = ConfluenceEngine()

        # Try to discover real fees from the exchange itself. Failure is
        # non-fatal — env values remain as the fallback.
        if self.client._private_key is not None:
            logger.info("Discovering live fees from CoinSwitch API…")
            ok = self.risk_mgr.fee_model.discover_from_api(self.client)
            if ok:
                logger.info(f"Fees discovered: {self.risk_mgr.fee_model.describe()}")
                self.confluence.fee_model = self.risk_mgr.fee_model
            else:
                logger.info(f"Fee discovery: no usable response → using {self.risk_mgr.fee_model.describe()}")
        else:
            logger.info(f"No API key — using config fees: {self.risk_mgr.fee_model.describe()}")

        self._last_signal_scan = 0
        self._last_scalp_scan  = 0
        self._last_position_check = 0
        self._signal_cooldown: Dict[str, float] = {}        # symbol → last swing signal ts
        self._scalp_cooldown:  Dict[str, float] = {}        # symbol → last scalp signal ts
        self._signal_cooldown_secs = 300                    # 5 min cooldown (swing)
        self._scalp_cooldown_secs  = 90                     # 90 sec cooldown (scalp/pump)

    # ─── Main Loop ────────────────────────────────────────────────────────────

    def run(self):
        logger.info("Bot started. Press Ctrl+C to stop.")
        self.running = True

        # Once the dashboard owns stdout, silence the console StreamHandlers so
        # log lines don't tear the rich frame. Disk + Bot-Log panel still capture
        # everything.
        silence_stdout_logging()

        os_signal.signal(os_signal.SIGINT, self._shutdown)
        os_signal.signal(os_signal.SIGTERM, self._shutdown)

        while self.running:
            now = time.time()

            try:
                # ── Update balance ────────────────────────────────────────────
                self._update_balance()

                # ── Scan for signals ──────────────────────────────────────────
                if now - self._last_signal_scan >= SIGNAL_CHECK_INTERVAL:
                    self._scan_signals()
                    self._last_signal_scan = now

                # ── Fast scalp/pump scan (5m candles, every 20s) ──────────────
                if (STRATEGY_SCALP or STRATEGY_PUMP) and \
                        now - self._last_scalp_scan >= SCALP_CHECK_INTERVAL:
                    self._scan_scalp_signals()
                    self._last_scalp_scan = now

                # ── Check positions (paper only) ──────────────────────────────
                if now - self._last_position_check >= POSITION_CHECK_INTERVAL:
                    self._check_positions()
                    self._last_position_check = now

                # ── Render dashboard ──────────────────────────────────────────
                current_prices = self._get_current_prices()
                render_dashboard_simple(
                    self.risk_mgr,
                    self.executor.open_trades,
                    current_prices,
                    self.mode,
                )

            except Exception as e:
                logger.error(f"Bot loop error: {e}", exc_info=True)

            time.sleep(5)

    # ─── Signal Scanning ──────────────────────────────────────────────────────

    def _scan_signals(self):
        now = time.time()

        for symbol in TRADING_PAIRS:
            already_open = any(t.symbol == symbol
                               for t in self.executor.open_trades.values())
            if already_open:
                continue

            last_sig_ts = self._signal_cooldown.get(symbol, 0)
            if now - last_sig_ts < self._signal_cooldown_secs:
                continue

            try:
                data = self._fetch_enriched(symbol)
                if not data:
                    continue

                signal = self.confluence.evaluate(symbol, data)

                if signal:
                    self._signal_cooldown[symbol] = time.time()
                    trade = self.executor.execute_signal(signal)
                    if trade:
                        logger.warning(
                            f"TRADE: {trade.trade_id} {trade.side} {symbol} "
                            f"@ {trade.entry_price:.6g} | SL={trade.stop_loss:.6g} TP={trade.take_profit:.6g} "
                            f"| {signal.strategy_name}"
                        )

            except Exception as e:
                logger.error(f"[{symbol}] scan error: {e}")

    # ─── Scalp / Pump Signal Scanning ────────────────────────────────────────

    def _scan_scalp_signals(self):
        """Fast scan using 5m candles for SCALP_MOMENTUM and PUMP_DETECTOR."""
        now = time.time()
        for symbol in TRADING_PAIRS:
            already_open = any(t.symbol == symbol
                               for t in self.executor.open_trades.values())
            if already_open:
                continue

            last_scalp_ts = self._scalp_cooldown.get(symbol, 0)
            if now - last_scalp_ts < self._scalp_cooldown_secs:
                continue

            try:
                df_5m = self.fetcher.get_ohlcv(symbol, SCALP_TF)
                if df_5m is None or len(df_5m) < 50:
                    continue

                df_5m = enrich(df_5m)
                signal = self.confluence.evaluate_fast(symbol, df_5m)

                if signal:
                    self._scalp_cooldown[symbol] = time.time()
                    trade = self.executor.execute_signal(signal)
                    if trade:
                        logger.warning(
                            f"FAST TRADE: {trade.trade_id} {trade.side} {symbol} "
                            f"@ {trade.entry_price:.6g} | SL={trade.stop_loss:.6g} TP={trade.take_profit:.6g} "
                            f"| {signal.strategy_name}"
                        )

            except Exception as e:
                logger.error(f"[{symbol}] scalp scan error: {e}")

    # ─── Position Monitoring ──────────────────────────────────────────────────

    def _check_positions(self):
        if not self.executor.open_trades:
            return
        current_prices = self._get_current_prices()
        self.executor.check_and_close_positions(current_prices)

    # ─── Data Helpers ─────────────────────────────────────────────────────────

    def _fetch_enriched(self, symbol: str) -> Dict:
        """Fetch and enrich data for all required timeframes."""
        data = {}
        for tf in [PRIMARY_TF, CONFIRM_TF, TREND_TF]:
            df = self.fetcher.get_ohlcv(symbol, tf)
            if df is not None and len(df) >= 50:
                data[tf] = enrich(df)
        return data

    def _get_current_prices(self) -> Dict[str, float]:
        prices = {}
        for symbol in TRADING_PAIRS:
            p = self.fetcher.get_current_price(symbol)
            if p:
                prices[symbol] = p
            # Also fill from open trades entry prices as fallback
            for trade in self.executor.open_trades.values():
                if trade.symbol == symbol and symbol not in prices:
                    prices[symbol] = trade.entry_price
        return prices

    def _update_balance(self):
        try:
            if self.mode == "paper":
                return
            portfolio = self.fetcher.get_portfolio_value()
            bal = portfolio.get("available", 0)
            if bal:
                self.risk_mgr.update_balance(float(bal))
        except Exception:
            pass

    def _shutdown(self, *_):
        logger.info("Shutting down bot...")
        self.running = False
        stats = self.risk_mgr.get_stats()
        logger.info(f"Final stats: {stats}")
        sys.exit(0)


# ─── Backtest Mode ────────────────────────────────────────────────────────────

def run_backtest(symbol: str = "BTC/USDT", tf: str = "15m",
                 candle_file: str = None):
    from backtester.backtest import Backtester
    import pandas as pd

    logger.info(f"Running backtest on {symbol} ({tf})")

    if candle_file:
        df = pd.read_csv(candle_file, index_col=0, parse_dates=True)
        df.columns = [c.lower() for c in df.columns]
    else:
        # Fetch live data for backtest
        client = CoinSwitchClient()
        fetcher = DataFetcher(client)
        df = fetcher.get_ohlcv(symbol, tf, limit=500, use_cache=False)
        if df is None:
            logger.error("Could not fetch data for backtest")
            return

    bt = Backtester(initial_balance=1000.0)
    result = bt.run(df, symbol, tf)

    print("\n" + "="*50)
    print("BACKTEST RESULTS")
    print("="*50)
    for k, v in result.summary().items():
        print(f"  {k:20s}: {v}")
    print("="*50 + "\n")

    # Print trade-by-trade
    if result.trades:
        print(f"Last 10 trades:")
        for t in result.trades[-10:]:
            emoji = "✅" if t.pnl > 0 else "❌"
            print(f"  {emoji} {t.signal:5s} entry={t.entry_price:.4f} "
                  f"exit={t.exit_price:.4f} PnL=${t.pnl:+.2f} ({t.pnl_pct:+.1f}%) "
                  f"[{t.exit_reason}] {t.strategy}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CoinSwitch Futures Bot")
    parser.add_argument("--backtest",  action="store_true", help="Run backtest")
    parser.add_argument("--paper",     action="store_true", help="Force paper mode")
    parser.add_argument("--live",      action="store_true", help="Force live mode")
    parser.add_argument("--symbol",    default="BTC/USDT",  help="Symbol for backtest")
    parser.add_argument("--tf",        default="15m",       help="Timeframe for backtest")
    parser.add_argument("--balance",   default=1000.0, type=float, help="Starting balance")
    parser.add_argument("--csv",       default=None,        help="CSV file for backtest")
    args = parser.parse_args()

    if args.backtest:
        run_backtest(args.symbol, args.tf, args.csv)
    else:
        mode = "paper"
        if args.live:
            mode = "live"
            print("\n⚠️  LIVE MODE — real money at risk. Ctrl+C to abort in 5s...")
            time.sleep(5)
        elif args.paper:
            mode = "paper"
        else:
            mode = TRADING_MODE

        bot = TradingBot(mode=mode, initial_balance=args.balance)
        bot.run()

"""
Rich terminal dashboard — live P&L, open positions, signal feed, risk stats.
"""
import os
from typing import Dict, List, Optional
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from execution.trade_executor import OpenTrade
from risk.risk_manager import RiskManager
from monitoring.log_buffer import BotLog

console = Console() if RICH_AVAILABLE else None


_LEVEL_COLOR = {
    "DEBUG":   "dim",
    "INFO":    "white",
    "WARNING": "yellow",
    "ERROR":   "red",
    "CRITICAL":"bold red",
}


def _color_pnl(val: float) -> str:
    if val > 0:
        return f"[green]+{val:.2f}[/green]"
    if val < 0:
        return f"[red]{val:.2f}[/red]"
    return f"{val:.2f}"


def _fmt_price(p: float) -> str:
    """Auto-select decimal places based on price magnitude."""
    if p == 0:
        return "0.00"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.01:
        return f"{p:.6f}"
    if p >= 0.0001:
        return f"{p:.8f}"
    return f"{p:.10f}"


def render_dashboard(
    risk_mgr: RiskManager,
    open_trades: Dict[str, OpenTrade],
    current_prices: Dict[str, float],
    last_signals: List[str],
    mode: str = "paper",
):
    if not RICH_AVAILABLE:
        _plain_dashboard(risk_mgr, open_trades, current_prices, mode)
        return

    stats = risk_mgr.get_stats()
    layout = Layout()

    # ── Header ────────────────────────────────────────────────────────────────
    mode_color = "yellow" if mode == "paper" else "bold red"
    header = Panel(
        f"[{mode_color}]CoinSwitch Futures Bot — {mode.upper()} MODE[/{mode_color}]  "
        f"  [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC]",
        box=box.DOUBLE_EDGE,
    )

    # ── Stats ─────────────────────────────────────────────────────────────────
    halt_str = f"[red]HALTED: {stats['halt_reason']}[/red]" if stats["trading_halted"] else "[green]ACTIVE[/green]"
    stats_text = (
        f"Balance: [bold]${stats['balance']:,.2f}[/bold]   "
        f"Peak: ${stats['peak_balance']:,.2f}   "
        f"Daily PnL: {_color_pnl(stats['daily_pnl'])}   "
        f"Drawdown: [{'red' if stats['drawdown_pct'] > 5 else 'white'}]{stats['drawdown_pct']:.1f}%[/{'red' if stats['drawdown_pct'] > 5 else 'white'}]   "
        f"Trades: {stats['total_trades']}   "
        f"Win Rate: {stats['win_rate']:.1f}%   "
        f"Status: {halt_str}"
    )
    agent_line = ""
    try:
        from agent.strategy_agent import get_agent
        a = get_agent().summary()
        agent_line = (
            f"\n[cyan]Agent[/cyan]: trades_seen={a['global_trades']}  "
            f"arms_total={a['arms_total']}  arms_learned={a['arms_learned']}  "
            f"global_pnl=${a['global_pnl']:+.2f}"
        )
    except Exception:
        pass
    stats_panel = Panel(stats_text + agent_line, title="Portfolio + Agent", box=box.ROUNDED)

    # ── Open Positions ────────────────────────────────────────────────────────
    pos_table = Table(title="Open Positions", box=box.SIMPLE, expand=True)
    pos_table.add_column("ID",       style="cyan",   no_wrap=True)
    pos_table.add_column("Symbol",   style="white")
    pos_table.add_column("Side",     style="bold")
    pos_table.add_column("Qty",      justify="right")
    pos_table.add_column("Entry",    justify="right")
    pos_table.add_column("Current",  justify="right")
    pos_table.add_column("SL",       justify="right", style="red")
    pos_table.add_column("TP",       justify="right", style="green")
    pos_table.add_column("PnL",      justify="right")
    pos_table.add_column("Strategy", style="dim")

    for tid, trade in open_trades.items():
        cur = current_prices.get(trade.symbol, trade.entry_price)
        pnl = trade.pnl(cur)
        side_color = "green" if trade.is_long else "red"
        pos_table.add_row(
            tid[-8:],
            trade.symbol,
            f"[{side_color}]{trade.side}[/{side_color}]",
            f"{trade.quantity:.2f}",
            _fmt_price(trade.entry_price),
            _fmt_price(cur),
            _fmt_price(trade.stop_loss),
            _fmt_price(trade.take_profit),
            _color_pnl(pnl),
            trade.strategy[:15],
        )

    # ── Recent Signals ────────────────────────────────────────────────────────
    sig_table = Table(title="Recent Signals", box=box.SIMPLE, expand=True)
    sig_table.add_column("Time")
    sig_table.add_column("Message")
    for line in last_signals[-8:]:
        sig_table.add_row("", line)

    # ── Bot Log (live, persists across redraws) ──────────────────────────────
    log_table = Table(title="Bot Log (step-by-step)", box=box.SIMPLE, expand=True)
    log_table.add_column("Time", no_wrap=True, style="cyan")
    log_table.add_column("Level", no_wrap=True)
    log_table.add_column("Source", no_wrap=True, style="dim")
    log_table.add_column("Message", overflow="fold")
    for ts, level, name, msg in BotLog.get().tail(18):
        color = _LEVEL_COLOR.get(level, "white")
        log_table.add_row(ts, f"[{color}]{level}[/{color}]", name.split(".")[-1], msg)

    console.clear()
    console.print(header)
    console.print(stats_panel)
    console.print(pos_table)
    console.print(sig_table)
    console.print(log_table)


def _plain_dashboard(risk_mgr, open_trades, current_prices, mode):
    stats = risk_mgr.get_stats()
    os.system("clear")
    print(f"\n=== CoinSwitch Bot [{mode.upper()}] {datetime.utcnow().strftime('%H:%M:%S')} ===")
    print(f"Balance: ${stats['balance']:,.2f} | Daily PnL: {stats['daily_pnl']:+.2f} | "
          f"Win Rate: {stats['win_rate']:.1f}% | Trades: {stats['total_trades']}")
    print(f"Open Positions: {stats['open_positions']} | Drawdown: {stats['drawdown_pct']:.1f}%")
    if stats["trading_halted"]:
        print(f"*** HALTED: {stats['halt_reason']} ***")
    print(f"\nOpen Trades: {len(open_trades)}")
    for tid, t in open_trades.items():
        cur = current_prices.get(t.symbol, t.entry_price)
        print(f"  {tid}: {t.symbol} {t.side} qty={t.quantity:.4f} "
              f"entry={t.entry_price:.4f} cur={cur:.4f} pnl=${t.pnl(cur):+.2f}")

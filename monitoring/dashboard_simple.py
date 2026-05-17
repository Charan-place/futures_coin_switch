"""
Minimal dashboard — only open trades + closed trades today.
No strategy spam, no signal feed, no logs.
"""
from typing import Dict, List
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from execution.trade_executor import OpenTrade
from risk.risk_manager import RiskManager

console = Console() if RICH_AVAILABLE else None


def _fmt_price(p: float) -> str:
    if p == 0:
        return "0.00"
    if p >= 1:
        return f"{p:.4f}"
    if p >= 0.01:
        return f"{p:.6f}"
    if p >= 0.0001:
        return f"{p:.8f}"
    return f"{p:.10f}"


def _color_pnl(val: float) -> str:
    if val > 0:
        return f"[green]+{val:.2f}[/green]"
    if val < 0:
        return f"[red]{val:.2f}[/red]"
    return f"{val:.2f}"


def render_dashboard_simple(
    risk_mgr: RiskManager,
    open_trades: Dict[str, OpenTrade],
    current_prices: Dict[str, float],
    mode: str = "paper",
):
    """Minimal dashboard: header + open trades + today's closed trades."""
    if not RICH_AVAILABLE:
        return

    stats = risk_mgr.get_stats()

    # Header
    mode_color = "yellow" if mode == "paper" else "bold red"
    console.print(
        f"\n[{mode_color}]{'█' * 80}[/{mode_color}]"
    )
    console.print(
        f"[{mode_color}]CoinSwitch Bot — {mode.upper()} MODE[/{mode_color}] | "
        f"Balance: [bold]${stats['balance']:,.2f}[/bold] | "
        f"Daily PnL: {_color_pnl(stats['daily_pnl'])} | "
        f"Win Rate: {stats['win_rate']:.0f}% | "
        f"Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}"
    )
    console.print(
        f"[{mode_color}]{'█' * 80}[/{mode_color}]\n"
    )

    # Open Positions
    open_tbl = Table(title="OPEN POSITIONS", box=box.SIMPLE, expand=False)
    open_tbl.add_column("ID", style="cyan")
    open_tbl.add_column("Symbol", style="white")
    open_tbl.add_column("Side", style="bold")
    open_tbl.add_column("Qty", justify="right")
    open_tbl.add_column("Entry", justify="right")
    open_tbl.add_column("Current", justify="right")
    open_tbl.add_column("SL", justify="right", style="red")
    open_tbl.add_column("TP", justify="right", style="green")
    open_tbl.add_column("PnL", justify="right")
    open_tbl.add_column("Strategy", style="dim")

    if open_trades:
        for tid, trade in open_trades.items():
            cur = current_prices.get(trade.symbol, trade.entry_price)
            pnl = trade.pnl(cur)
            pnl_pct = trade.pnl_pct(cur)
            pnl_str = f"{_color_pnl(pnl)} ({pnl_pct:+.1f}%)"
            side_style = "green" if trade.is_long else "red"
            open_tbl.add_row(
                tid,
                trade.symbol,
                f"[{side_style}]{trade.side}[/{side_style}]",
                f"{trade.quantity:.0f}",
                _fmt_price(trade.entry_price),
                _fmt_price(cur),
                _fmt_price(trade.stop_loss),
                _fmt_price(trade.take_profit),
                pnl_str,
                trade.strategy[:15],
            )
    else:
        open_tbl.add_row("[dim]— no open trades —[/dim]", "", "", "", "", "", "", "", "", "")

    console.print(open_tbl)

    # Closed Trades Today
    closed_tbl = Table(title="CLOSED TRADES TODAY", box=box.SIMPLE, expand=False)
    closed_tbl.add_column("Symbol", style="white")
    closed_tbl.add_column("Side")
    closed_tbl.add_column("Entry", justify="right")
    closed_tbl.add_column("Exit", justify="right")
    closed_tbl.add_column("PnL", justify="right")
    closed_tbl.add_column("%", justify="right")
    closed_tbl.add_column("Strategy", style="dim")
    closed_tbl.add_column("Time", justify="right", style="dim")

    today = datetime.utcnow().date()
    closed_today = [t for t in risk_mgr.trade_history
                    if t.timestamp.date() == today]

    if closed_today:
        for t in closed_today[-20:]:  # last 20 trades
            side_style = "green" if t.side == "LONG" else "red"
            pnl_str = f"{_color_pnl(t.pnl)}"
            closed_tbl.add_row(
                t.symbol,
                f"[{side_style}]{t.side}[/{side_style}]",
                _fmt_price(t.entry_price),
                _fmt_price(t.exit_price),
                pnl_str,
                f"{t.pnl_pct:+.1f}%",
                t.strategy[:15],
                t.timestamp.strftime("%H:%M"),
            )
    else:
        closed_tbl.add_row("[dim]— no closed trades yet —[/dim]", "", "", "", "", "", "", "")

    console.print(closed_tbl)
    console.print()

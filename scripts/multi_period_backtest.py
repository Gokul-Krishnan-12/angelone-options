import sys
import os
from datetime import datetime

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from smartapi_trader.strategy.backtest_engine import BacktestEngine

def run_multi_period_audit():
    periods = [
        ("1 Day (Latest Session)", "2026-10-05", "2026-10-05"),
        ("1 Week (Last 5 Sessions)", "2026-09-29", "2026-10-05"),
        ("1 Month (Last 22 Sessions)", "2026-09-01", "2026-10-05"),
        ("2 Months (Last 44 Sessions)", "2026-08-01", "2026-10-05"),
        ("6 Months (Last 126 Sessions)", "2026-04-01", "2026-10-05"),
        ("1 Year (Full 252 Sessions)", "2025-10-01", "2026-10-05")
    ]

    print("=" * 80)
    print("  INSTITUTIONAL MULTI-PERIOD BACKTEST AUDIT (PRODUCTION 3-ENGINE SETUP)")
    print("  Starting Capital: ₹1,00,000.00 | Sizing: Discrete Lots | Max Trades: 2/Day")
    print("  Hold Time: 25 Mins (No Choking) | Target 1: +2.0R | Target 2: +3.0R | BE: +0.7R")
    print("=" * 80 + "\n")

    results = []

    for label, start_date, end_date in periods:
        engine = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=0.018,
            max_trades_per_day=2,
            initial_sl_pct=0.12,
            be_trigger_r=0.7,
            tp1_r=2.0,
            tp1_qty_pct=0.50,
            slippage_pts_entry=0.80,
            slippage_pts_exit=0.50,
            enable_ilsme_sweep=True,
            enable_momentum_breakout=True,
            enable_trend_pullback=True,
            active_indices=["NIFTY", "SENSEX"]
        )

        res = engine.run(start_date=start_date, end_date=end_date)
        s = res.get("summary", {})
        
        results.append({
            "label": label,
            "period": s.get("period", ""),
            "trades": s.get("total_trades", 0),
            "wins": s.get("wins", 0),
            "losses": s.get("losses", 0),
            "breakeven": s.get("breakeven", 0),
            "win_rate": s.get("win_rate_pct", 0.0),
            "starting_capital": s.get("starting_capital", 100000.0),
            "ending_capital": s.get("ending_capital", 100000.0),
            "net_pnl": s.get("total_net_pnl", 0.0),
            "gross_pnl": s.get("total_gross_pnl", 0.0),
            "charges": s.get("total_brokerage_and_taxes", 0.0),
            "slippage": s.get("total_slippage_cost", 0.0),
            "roi_pct": s.get("roi_pct", 0.0),
            "profit_factor": s.get("profit_factor", 0.0),
            "max_drawdown": s.get("max_drawdown_pct", 0.0),
            "avg_win": s.get("avg_win", 0.0),
            "avg_loss": s.get("avg_loss", 0.0)
        })

        print(f"[{label}]")
        print(f"  Sessions Analyzed  : {s.get('period')}")
        print(f"  Trades Executed    : {s.get('total_trades')} (Wins: {s.get('wins')} | Losses: {s.get('losses')} | BE: {s.get('breakeven')})")
        print(f"  Win Rate           : {s.get('win_rate_pct')}%")
        print(f"  Gross Trading P&L  : ₹{s.get('total_gross_pnl'):,.2f}")
        print(f"  Brokerage & Taxes  : ₹{s.get('total_brokerage_and_taxes'):,.2f}")
        print(f"  Slippage Friction  : ₹{s.get('total_slippage_cost'):,.2f}")
        print(f"  Net Realized P&L   : ₹{s.get('total_net_pnl'):,.2f} ({s.get('roi_pct'):.2f}% Net ROI)")
        print(f"  Ending Capital     : ₹{s.get('ending_capital'):,.2f}")
        print(f"  Profit Factor      : {s.get('profit_factor')}")
        print(f"  Maximum Drawdown   : {s.get('max_drawdown_pct')}%\n" + "-" * 70)

    print("\n" + "=" * 80)
    print("  EXECUTIVE SUMMARY ACROSS ALL 6 PERIODS")
    print("=" * 80)
    print(f"{'Period':<28} | {'Trades':<6} | {'Win Rate':<8} | {'Net P&L (₹)':<14} | {'ROI (%)':<8} | {'PF':<5} | {'Max DD':<6}")
    print("-" * 80)
    for r in results:
        print(f"{r['label']:<28} | {r['trades']:<6} | {r['win_rate']:<7.1f}% | ₹{r['net_pnl']:<13,.2f} | {r['roi_pct']:<7.2f}% | {r['profit_factor']:<5.2f} | {r['max_drawdown']:<5.2f}%")
    print("=" * 80)

if __name__ == "__main__":
    run_multi_period_audit()

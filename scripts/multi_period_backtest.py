import sys
import os
from datetime import datetime

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from smartapi_trader.strategy.backtest_engine import BacktestEngine

def run_multi_period_audit():
    periods = [
        ("Today (2026-10-28)", "2026-10-28", "2026-10-28"),
        ("1 Week (Last 5 Sessions)", "2026-09-29", "2026-10-28"),
        ("1 Month (September – October 2026)", "2026-09-01", "2026-10-28"),
        ("2 Months (August – October 2026)", "2026-08-01", "2026-10-28"),
        ("6 Months (April – October 2026)", "2026-04-01", "2026-10-28"),
        ("1 Year (Full 253 Sessions)", "2025-10-01", "2026-10-28")
    ]

    print("=" * 95)
    print("  INSTITUTIONAL QUANTITATIVE AUDIT: NAKED OPTIONS vs DEBIT SPREADS")
    print("  Starting Capital: ₹1,00,000.00 | Sizing: 1.5% Risk Discrete Lots | Max Trades: 2/Day")
    print("  Execution Architectures: 1) NAKED (ATM) | 2) DEBIT SPREAD (Buy ATM + Sell OTM)")
    print("=" * 95 + "\n")

    comparative_results = []

    for label, start_date, end_date in periods:
        print(f"\n>>> AUDITING PERIOD: {label}")
        print("-" * 95)

        # 1. Run NAKED backtest
        naked_engine = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=0.015,
            max_trades_per_day=2,
            initial_sl_pct=0.12,
            be_trigger_r=1.5,
            tp1_r=2.5,
            tp1_qty_pct=0.50,
            slippage_pts_entry=0.80,
            slippage_pts_exit=0.50,
            enable_ilsme_sweep=True,
            enable_momentum_breakout=False,
            enable_trend_pullback=True,
            active_indices=["NIFTY", "SENSEX"],
            execution_structure="NAKED"
        )
        res_naked = naked_engine.run(start_date=start_date, end_date=end_date)
        s_naked = res_naked.get("summary", {})

        # 2. Run DEBIT SPREAD backtest
        spread_engine = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=0.015,
            max_trades_per_day=2,
            initial_sl_pct=0.12,
            be_trigger_r=1.5,
            tp1_r=2.5,
            tp1_qty_pct=0.50,
            slippage_pts_entry=0.80,
            slippage_pts_exit=0.50,
            enable_ilsme_sweep=True,
            enable_momentum_breakout=False,
            enable_trend_pullback=True,
            active_indices=["NIFTY", "SENSEX"],
            execution_structure="DEBIT_SPREAD",
            debit_spread_take_profit_pct=0.50,
            debit_spread_stop_loss_pct=0.40
        )
        res_spread = spread_engine.run(start_date=start_date, end_date=end_date)
        s_spread = res_spread.get("summary", {})

        comparative_results.append({
            "label": label,
            "naked": {
                "trades": s_naked.get("total_trades", 0),
                "wins": s_naked.get("wins", 0),
                "losses": s_naked.get("losses", 0),
                "be": s_naked.get("breakeven", 0),
                "win_rate": s_naked.get("win_rate_pct", 0.0),
                "gross_pnl": s_naked.get("total_gross_pnl", 0.0),
                "charges": s_naked.get("total_brokerage_and_taxes", 0.0),
                "slippage": s_naked.get("total_slippage_cost", 0.0),
                "net_pnl": s_naked.get("total_net_pnl", 0.0),
                "roi_pct": s_naked.get("roi_pct", 0.0),
                "pf": s_naked.get("profit_factor", 0.0),
                "max_dd": s_naked.get("max_drawdown_pct", 0.0),
                "end_capital": s_naked.get("ending_capital", 100000.0)
            },
            "spread": {
                "trades": s_spread.get("total_trades", 0),
                "wins": s_spread.get("wins", 0),
                "losses": s_spread.get("losses", 0),
                "be": s_spread.get("breakeven", 0),
                "win_rate": s_spread.get("win_rate_pct", 0.0),
                "gross_pnl": s_spread.get("total_gross_pnl", 0.0),
                "charges": s_spread.get("total_brokerage_and_taxes", 0.0),
                "slippage": s_spread.get("total_slippage_cost", 0.0),
                "net_pnl": s_spread.get("total_net_pnl", 0.0),
                "roi_pct": s_spread.get("roi_pct", 0.0),
                "pf": s_spread.get("profit_factor", 0.0),
                "max_dd": s_spread.get("max_drawdown_pct", 0.0),
                "end_capital": s_spread.get("ending_capital", 100000.0)
            }
        })

        print(f"  ● NAKED OPTIONS BUYING:")
        print(f"    Trades: {s_naked.get('total_trades')} | Win Rate: {s_naked.get('win_rate_pct')}% | Net P&L: ₹{s_naked.get('total_net_pnl'):,.2f} ({s_naked.get('roi_pct'):.2f}%) | Max DD: {s_naked.get('max_drawdown_pct')}% | PF: {s_naked.get('profit_factor')}")
        print(f"  🛡️ DEBIT SPREAD (BUY ATM + SELL OTM):")
        print(f"    Trades: {s_spread.get('total_trades')} | Win Rate: {s_spread.get('win_rate_pct')}% | Net P&L: ₹{s_spread.get('total_net_pnl'):,.2f} ({s_spread.get('roi_pct'):.2f}%) | Max DD: {s_spread.get('max_drawdown_pct')}% | PF: {s_spread.get('profit_factor')}")

    print("\n" + "=" * 105)
    print("  EXECUTIVE COMPARISON MATRIX: NAKED OPTIONS vs DEBIT SPREADS")
    print("=" * 105)
    print(f"{'Time Horizon':<25} | {'Naked Net P&L':<15} | {'Naked ROI':<10} | {'Naked DD':<9} | {'Spread Net P&L':<15} | {'Spread ROI':<10} | {'Spread DD':<9} | {'Winner'}")
    print("-" * 105)
    for r in comparative_results:
        n = r["naked"]
        s = r["spread"]
        winner = "NAKED" if n["net_pnl"] > s["net_pnl"] else "DEBIT SPREAD"
        print(f"{r['label']:<25} | ₹{n['net_pnl']:<14,.2f} | {n['roi_pct']:<9.2f}% | {n['max_dd']:<8.2f}% | ₹{s['net_pnl']:<14,.2f} | {s['roi_pct']:<9.2f}% | {s['max_dd']:<8.2f}% | {winner}")
    print("=" * 105)

if __name__ == "__main__":
    run_multi_period_audit()

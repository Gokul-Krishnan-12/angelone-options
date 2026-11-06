import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartapi_trader.strategy.backtest_engine import BacktestEngine

def run_comprehensive_report():
    print("=" * 105)
    print("  INSTITUTIONAL QUANTITATIVE AUDIT & BACKTEST REPORT (NIFTY & SENSEX)")
    print("  Capital: ₹1,00,000.00 | Discrete Integer Lots | Realistic Bid-Ask Slippage Modeling")
    print("  Statutory Deductions: STT 0.15% (Sell), GST 18%, Exchange Turnover, SEBI, Stamp Duty")
    print("=" * 105)

    # 1. Multi-Period Benchmark
    periods = [
        ("1 Week (Oct 21 - Oct 28)", "2026-10-21", "2026-10-28"),
        ("1 Month (Sep 01 - Oct 28)", "2026-09-01", "2026-10-28"),
        ("2 Months (Aug 01 - Oct 28)", "2026-08-01", "2026-10-28"),
        ("6 Months (Apr 01 - Oct 28)", "2026-04-01", "2026-10-28"),
        ("1 Year (Full 253 Sessions)", "2025-10-01", "2026-10-28")
    ]

    header = f"{'Horizon':<27} | {'Trades':<7} | {'Win Rate':<9} | {'Net P&L':<15} | {'ROI':<9} | {'Profit Factor':<13} | {'Max DD':<8}"
    print("\n📊 MULTI-PERIOD PERFORMANCE BENCHMARK:")
    print("-" * 105)
    print(header)
    print("-" * 105)

    full_year_res = None

    for label, s_dt, e_dt in periods:
        eng = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=0.015,
            max_trades_per_day=2,
            initial_sl_pct=0.12,
            be_trigger_r=0.85,
            tp1_r=2.5,
            enable_ilsme_sweep=True,
            enable_momentum_breakout=False,
            enable_trend_pullback=True,
            active_indices=["NIFTY", "SENSEX"]
        )
        res = eng.run(start_date=s_dt, end_date=e_dt)
        s = res["summary"]
        if "1 Year" in label:
            full_year_res = res
        print(f"{label:<27} | {s['total_trades']:<7d} | {s['win_rate_pct']:<8.1f}% | ₹{s['total_net_pnl']:<14,.2f} | {s['roi_pct']:<8.1f}% | {s['profit_factor']:<13.2f} | {s['max_drawdown_pct']:<7.1f}%")

    print("=" * 105)

    # 2. Asset Allocation Breakdown (NIFTY vs SENSEX) over 1 Year
    print("\n🎯 ASSET ATTRIBUTION (1-YEAR BREAKDOWN: NIFTY vs SENSEX):")
    print("-" * 105)
    for idx in ["NIFTY", "SENSEX"]:
        eng_idx = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=0.015,
            max_trades_per_day=2,
            initial_sl_pct=0.12,
            be_trigger_r=0.85,
            tp1_r=2.5,
            enable_ilsme_sweep=True,
            enable_momentum_breakout=False,
            enable_trend_pullback=True,
            active_indices=[idx]
        )
        s_idx = eng_idx.run(start_date="2025-10-01", end_date="2026-10-28")["summary"]
        print(f"  • {idx:<10}: {s_idx['total_trades']} trades | Win Rate: {s_idx['win_rate_pct']:.1f}% | Net P&L: ₹{s_idx['total_net_pnl']:+,.2f} ({s_idx['roi_pct']:+.1f}% ROI) | Profit Factor: {s_idx['profit_factor']:.2f} | Max DD: {s_idx['max_drawdown_pct']:.1f}%")

    # 3. Monthly Breakdown (1-Year Full Run)
    if full_year_res:
        trades = full_year_res["trades"]
        months = {}
        for t in trades:
            m = t["date"][:7]
            if m not in months:
                months[m] = {"trades": 0, "wins": 0, "losses": 0, "be": 0, "gross": 0.0, "net": 0.0, "charges": 0.0}
            months[m]["trades"] += 1
            if t["result"] == "WIN":
                months[m]["wins"] += 1
            elif t["result"] == "LOSS":
                months[m]["losses"] += 1
            else:
                months[m]["be"] += 1
            months[m]["gross"] += t.get("gross_pnl", 0.0)
            months[m]["charges"] += t.get("total_charges", 0.0)
            months[m]["net"] += t.get("net_pnl", 0.0)

        print("\n📅 MONTH-BY-MONTH RETURN PROFILE (2025 - 2026):")
        print("-" * 105)
        print(f"{'Month':<10} | {'Trades':<7} | {'Wins':<5} | {'Losses':<6} | {'Breakeven':<9} | {'Win Rate':<9} | {'Gross P&L':<15} | {'Taxes & Brokerage':<18} | {'Net Realized P&L'}")
        print("-" * 105)
        for m, d in sorted(months.items()):
            wr = (d["wins"] / d["trades"] * 100.0) if d["trades"] > 0 else 0
            print(f"{m:<10} | {d['trades']:<7d} | {d['wins']:<5d} | {d['losses']:<6d} | {d['be']:<9d} | {wr:<8.1f}% | ₹{d['gross']:<14,.2f} | -₹{d['charges']:<16,.2f} | ₹{d['net']:+,.2f}")
        print("=" * 105)

    # 4. Summary Cost Friction
    s_full = full_year_res["summary"]
    print("\n💰 STATUTORY COST & SLIPPAGE FRICTION AUDIT (1 YEAR):")
    print("-" * 105)
    print(f"  • Gross P&L Generated      : ₹{s_full['total_gross_pnl']:+,.2f}")
    print(f"  • Brokerage & STT Deducted : -₹{s_full['total_brokerage_and_taxes']:,.2f}")
    print(f"  • Bid-Ask Slippage Absorbed: -₹{s_full['total_slippage_cost']:,.2f}")
    print(f"  • Final Net Realized P&L   : ₹{s_full['total_net_pnl']:+,.2f}")
    print(f"  • Total Cost Friction Ratio: {((s_full['total_brokerage_and_taxes'] + s_full['total_slippage_cost']) / max(1.0, abs(s_full['total_gross_pnl']))) * 100:.1f}% of gross gains")
    print("=" * 105)

if __name__ == "__main__":
    run_comprehensive_report()

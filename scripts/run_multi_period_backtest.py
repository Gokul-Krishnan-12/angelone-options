import json
from smartapi_trader.strategy.backtest_engine import BacktestEngine

def run_test(name, start, end, cap=100000.0, risk=0.018):
    engine = BacktestEngine(
        starting_capital=cap,
        risk_per_trade_pct=risk,
        max_trades_per_day=2,
        initial_sl_pct=0.12,
        be_trigger_r=1.5,
        tp1_r=3.0,
        enable_ilsme_sweep=True,
        enable_momentum_breakout=True,
        active_indices=["NIFTY", "SENSEX"],
        slippage_pts_entry=1.0,
        slippage_pts_exit=0.8,
        start_date=start,
        end_date=end
    )
    res = engine.run(start_date=start, end_date=end)
    s = res["summary"]
    trades = res["trades"]
    print(f"==================================================")
    print(f"📊 {name} ({s['period']})")
    print(f"==================================================")
    print(f"Starting Capital: ₹{s['starting_capital']:,.2f}")
    print(f"Ending Capital: ₹{s['ending_capital']:,.2f}")
    print(f"Total Trades: {s['total_trades']} | Win Rate: {s['win_rate_pct']}% | Non-Losing Rate: {s['non_losing_rate_pct']}%")
    print(f"Profit Factor: {s['profit_factor']}")
    print(f"Gross P&L: ₹{s['total_gross_pnl']:+,.2f}")
    print(f"Brokerage, STT & Taxes: -₹{s['total_brokerage_and_taxes']:,.2f}")
    print(f"Spread Slippage Absorbed: -₹{s['total_slippage_cost']:,.2f}")
    print(f"Net Realized P&L: ₹{s['total_net_pnl']:+,.2f}")
    print(f"Return on Capital (ROI): {s['roi_pct']:+,.2f}%")
    print(f"Max Peak Drawdown: {s['max_drawdown_pct']:.2f}%")
    print(f"Wins: {s['wins']} | Losses: {s['losses']} | Breakeven Shifts: {s['breakeven']}")
    print(f"Avg Win: ₹{s['avg_win']:,.2f} | Avg Loss: ₹{s['avg_loss']:,.2f}")
    
    # Monthly breakdown if multiple months
    months = {}
    for t in trades:
        m = t["date"][:7]
        if m not in months:
            months[m] = {"trades": 0, "wins": 0, "net_pnl": 0.0}
        months[m]["trades"] += 1
        if t["result"] == "WIN":
            months[m]["wins"] += 1
        months[m]["net_pnl"] += t["net_pnl"]
    
    if len(months) > 1:
        print("\n📅 Monthly Breakdown:")
        for m, d in sorted(months.items()):
            wr = (d["wins"] / d["trades"] * 100.0) if d["trades"] > 0 else 0
            print(f"  • {m}: Net P&L ₹{d['net_pnl']:+,.2f} ({d['trades']} trades | Win Rate: {wr:.1f}%)")
    print()

if __name__ == "__main__":
    # 1 Month: Sep 2026
    run_test("1-MONTH BACKTEST (September 2026)", "2026-09-01", "2026-09-30")

    # 2 Months: Aug 2026 - Sep 2026
    run_test("2-MONTH BACKTEST (August – September 2026)", "2026-08-01", "2026-09-30")

    # 1 Year: Oct 2025 - Sep 2026
    run_test("1-YEAR FULL BACKTEST (October 2025 – September 2026)", "2025-10-01", "2026-09-30")

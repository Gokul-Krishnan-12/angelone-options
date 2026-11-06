import yaml
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smartapi_trader.strategy.backtest_engine import BacktestEngine

def run_fresh_audit():
    with open("smartapi_trader/config/settings.yaml") as f:
        cfg = yaml.safe_load(f)

    risk_cfg = cfg["risk"]
    strat_cfg = cfg["strategy"]

    periods = [
        ("1 Day (Latest Session: Nov 03)", "2026-11-03", "2026-11-03"),
        ("1 Week (Oct 28 - Nov 03)", "2026-10-28", "2026-11-03"),
        ("1 Month (Oct 01 - Nov 03)", "2026-10-01", "2026-11-03"),
        ("3 Months (Aug 01 - Nov 03)", "2026-08-01", "2026-11-03"),
        ("6 Months (May 01 - Nov 03)", "2026-05-01", "2026-11-03"),
        ("1 Year (Full History to Nov 03)", "2025-10-01", "2026-11-03")
    ]

    print("=" * 110)
    print("  FRESH PRODUCTION WORKFLOW BACKTEST AUDIT (INDEX & EXECUTION ENGINE)")
    print(f"  Risk Per Trade: {risk_cfg['risk_per_trade_pct']*100:.1f}% | BE Trigger: {risk_cfg['breakeven_trigger_r']}R | Initial SL: {risk_cfg['initial_sl_percent']*100:.0f}% | TP1: {risk_cfg['partial_exit_r']}R")
    print(f"  Active Strategies: ILSME Sweep ({strat_cfg['enable_ilsme_sweep']}) + Donchian Trend Pullback ({strat_cfg['enable_trend_pullback']}, 15b, OR Break: {strat_cfg['donchian_require_or_break']})")
    print("=" * 110)

    print("\n📊 1. MULTI-PERIOD PERFORMANCE BENCHMARK (NAKED BUYING):")
    print("-" * 110)
    print(f"{'Horizon':<28} | {'Trades':<7} | {'Win Rate':<9} | {'Net Realized P&L':<18} | {'ROI':<8} | {'Profit Factor':<13} | {'Max DD':<7}")
    print("-" * 110)

    full_res = None
    for label, s_dt, e_dt in periods:
        eng = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=risk_cfg["risk_per_trade_pct"],
            max_trades_per_day=risk_cfg["max_trades_per_day"],
            initial_sl_pct=risk_cfg["initial_sl_percent"],
            be_trigger_r=risk_cfg["breakeven_trigger_r"],
            tp1_r=risk_cfg["partial_exit_r"],
            donchian_bars=strat_cfg["donchian_lookback_bars"],
            donchian_require_or_break=strat_cfg["donchian_require_or_break"],
            trade_cooldown_bars=5,
            max_vwap_distance_nifty=strat_cfg["max_vwap_distance_nifty"],
            max_vwap_distance_sensex=strat_cfg["max_vwap_distance_sensex"],
            max_consecutive_trend_bars=strat_cfg["max_consecutive_trend_bars"],
            enable_ilsme_sweep=strat_cfg["enable_ilsme_sweep"],
            enable_momentum_breakout=strat_cfg["enable_momentum_breakout"],
            enable_trend_pullback=strat_cfg["enable_trend_pullback"],
            active_indices=strat_cfg["active_indices"],
            execution_structure="NAKED"
        )
        res = eng.run(start_date=s_dt, end_date=e_dt)
        s = res["summary"]
        if "1 Year" in label:
            full_res = res
        print(f"{label:<28} | {s['total_trades']:<7} | {s['win_rate_pct']:<8.1f}% | ₹{s['total_net_pnl']:<17,.2f} | {s['roi_pct']:<7.1f}% | {s['profit_factor']:<13.2f} | {s['max_drawdown_pct']:<6.1f}%")

    print("=" * 110)

    # 2. Asset Attribution (NIFTY vs SENSEX)
    print("\n🎯 2. ASSET ATTRIBUTION (1-YEAR BREAKDOWN: NIFTY vs SENSEX):")
    print("-" * 110)
    for idx in ["NIFTY", "SENSEX"]:
        eng_idx = BacktestEngine(
            starting_capital=100000.0,
            risk_per_trade_pct=risk_cfg["risk_per_trade_pct"],
            max_trades_per_day=risk_cfg["max_trades_per_day"],
            initial_sl_pct=risk_cfg["initial_sl_percent"],
            be_trigger_r=risk_cfg["breakeven_trigger_r"],
            tp1_r=risk_cfg["partial_exit_r"],
            donchian_bars=strat_cfg["donchian_lookback_bars"],
            donchian_require_or_break=strat_cfg["donchian_require_or_break"],
            trade_cooldown_bars=5,
            max_vwap_distance_nifty=strat_cfg["max_vwap_distance_nifty"],
            max_vwap_distance_sensex=strat_cfg["max_vwap_distance_sensex"],
            max_consecutive_trend_bars=strat_cfg["max_consecutive_trend_bars"],
            enable_ilsme_sweep=strat_cfg["enable_ilsme_sweep"],
            enable_momentum_breakout=strat_cfg["enable_momentum_breakout"],
            enable_trend_pullback=strat_cfg["enable_trend_pullback"],
            active_indices=[idx],
            execution_structure="NAKED"
        )
        s_idx = eng_idx.run(start_date="2025-10-01", end_date="2026-11-03")["summary"]
        print(f"  • {idx:<8}: {s_idx['total_trades']} trades | Win Rate: {s_idx['win_rate_pct']:.1f}% | Net P&L: ₹{s_idx['total_net_pnl']:+,.2f} ({s_idx['roi_pct']:+.1f}% ROI) | Profit Factor: {s_idx['profit_factor']:.2f} | Max DD: {s_idx['max_drawdown_pct']:.1f}%")

    # 3. Monthly Breakdown
    if full_res:
        trades = full_res["trades"]
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

        print("\n📅 3. MONTH-BY-MONTH RETURN PROFILE (2025 - 2026):")
        print("-" * 110)
        print(f"{'Month':<10} | {'Trades':<7} | {'Wins':<5} | {'Losses':<6} | {'BE':<4} | {'Win Rate':<9} | {'Gross P&L':<15} | {'Taxes & Brokerage':<18} | {'Net Realized P&L'}")
        print("-" * 110)
        for m, d in sorted(months.items()):
            wr = (d["wins"] / d["trades"] * 100.0) if d["trades"] > 0 else 0
            print(f"{m:<10} | {d['trades']:<7d} | {d['wins']:<5d} | {d['losses']:<6d} | {d['be']:<4d} | {wr:<8.1f}% | ₹{d['gross']:<14,.2f} | -₹{d['charges']:<16,.2f} | ₹{d['net']:+,.2f}")
        print("=" * 110)

        # 4. Friction Audit
        s_full = full_res["summary"]
        tot_fric = s_full["total_brokerage_and_taxes"] + s_full["total_slippage_cost"]
        fric_ratio = (tot_fric / s_full["total_gross_pnl"]) * 100.0 if s_full["total_gross_pnl"] > 0 else 0.0
        print("\n💰 4. EXECUTION FRICTION & STATUTORY COST AUDIT (1 YEAR):")
        print("-" * 110)
        print(f"  • Gross P&L Generated       : ₹{s_full['total_gross_pnl']:+,.2f}")
        print(f"  • Brokerage & STT Deducted  : -₹{s_full['total_brokerage_and_taxes']:,.2f}")
        print(f"  • Spread Slippage Absorbed  : -₹{s_full['total_slippage_cost']:,.2f}")
        print(f"  • Final Net Realized P&L    : ₹{s_full['total_net_pnl']:+,.2f}")
        print(f"  • Total Drag Ratio          : {fric_ratio:.1f}% of gross gains absorbed by costs")
        print("=" * 110)

if __name__ == "__main__":
    run_fresh_audit()


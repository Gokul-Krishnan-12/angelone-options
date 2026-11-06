#!/usr/bin/env python3
"""
Institutional Liquidity Sweep & Momentum Expansion (ILSME) Sniper Backtest Runner
Fetches today's candle data directly from Angel One SmartAPI and executes the backtest simulation.
"""

import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import yaml
from datetime import datetime
from smartapi_trader.utils.auth import AngelAuthManager
from smartapi_trader.strategy.backtest_engine import BacktestEngine
from smartapi_trader.utils.logger import logger

def fetch_and_update_historical(date_str: str):
    """Fetches 3m and 15m OHLCV data from Angel One SmartAPI and updates data/historical/."""
    settings_path = "smartapi_trader/config/settings.yaml"
    with open(settings_path) as f:
        cfg = yaml.safe_load(f)

    b = cfg.get("broker", {})
    auth = AngelAuthManager(b.get("api_key", ""), b.get("client_code", ""), b.get("pin", ""), b.get("totp_secret", ""))
    smart_api, _, _ = auth.initialize_session()

    if auth.is_simulated or not smart_api:
        logger.warning("[SYNC] Real Angel One credentials not available; using existing historical files.")
        return

    tokens = {
        "nifty": ("NSE", "99926000"),
        "banknifty": ("NSE", "99926009"),
        "sensex": ("BSE", "99919000")
    }

    intervals = [
        ("3m", "THREE_MINUTE"),
        ("15m", "FIFTEEN_MINUTE")
    ]

    import time as _pytime
    for idx, (exch, tok) in tokens.items():
        for tf_key, angel_int in intervals:
            file_path = f"data/historical/{idx}_{tf_key}.json"
            existing = []
            if os.path.exists(file_path):
                with open(file_path, "r") as f:
                    existing = json.load(f)

            existing_ts = set(c[0] for c in existing)

            candles = []
            for attempt in range(4):
                _pytime.sleep(0.5 * (attempt + 1))
                try:
                    res = smart_api.getCandleData({
                        "exchange": exch,
                        "symboltoken": tok,
                        "interval": angel_int,
                        "fromdate": f"{date_str} 09:15",
                        "todate": f"{date_str} 15:30"
                    })
                    if isinstance(res, dict) and res.get("status"):
                        candles = res.get("data") or []
                        break
                    elif isinstance(res, dict) and "data" in res:
                        candles = res.get("data") or []
                        break
                except Exception as ex:
                    if attempt == 3:
                        logger.warning(f"[SYNC] Error fetching {idx} {tf_key} for {date_str}: {ex}")

            added = 0
            for c in candles:
                if c[0] not in existing_ts:
                    existing.append(c)
                    existing_ts.add(c[0])
                    added += 1

            if added > 0:
                existing.sort(key=lambda x: x[0])
                with open(file_path, "w") as f:
                    json.dump(existing, f)
                logger.info(f"[SYNC] {idx.upper()} {tf_key}: Appended {added} new candles for {date_str}.")

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = today_str

    print(f"============================================================")
    print(f"  ILSME SNIPER BACKTEST - SESSION: {target_date}")
    print(f"============================================================")

    # 1. Ensure historical dataset has today's candles
    fetch_and_update_historical(target_date)

    # 2. Run Backtest specifically for target_date
    engine_today = BacktestEngine(
        starting_capital=50000.0,
        risk_per_trade_pct=0.015,
        dynamic_compounding=False,
        start_date=target_date,
        end_date=target_date
    )

    results = engine_today.run()
    summary = results["summary"]
    trades = results["trades"]

    print("\n--- PERFORMANCE SUMMARY ---")
    print(f"Period:                     {summary['period']}")
    print(f"Starting Capital:           ₹{summary['starting_capital']:,.2f}")
    print(f"Ending Capital:             ₹{summary['ending_capital']:,.2f}")
    print(f"Total Net P&L:              ₹{summary['total_net_pnl']:,.2f}")
    print(f"Total Gross P&L:            ₹{summary['total_gross_pnl']:,.2f}")
    print(f"Brokerage & Statutory Tax:  ₹{summary['total_brokerage_and_taxes']:,.2f}")
    print(f"Total Trades:               {summary['total_trades']}")
    print(f"Wins / Losses / Breakeven:  {summary['wins']} / {summary['losses']} / {summary['breakeven']}")
    print(f"Win Rate:                   {summary['win_rate_pct']}% (Non-losing: {summary['non_losing_rate_pct']}%)")
    print(f"Max Intraday Drawdown:      {summary['max_drawdown_pct']}%")

    print("\n--- TRADES LEDGER ---")
    if not trades:
        print("No trades triggered for this session.")
        print("Reason: ILSME Sniper Filter - No valid liquidity sweeps with rejection wicks formed.")
    else:
        for t in trades:
            print(f"[{t['id']}] {t['underlying']} {t['tradingsymbol']} ({t['type']})")
            print(f"   Entry: {t['entry_time']} @ ₹{t['entry_price']} | Exit: {t['exit_time']} @ ₹{t['exit_price']}")
            print(f"   Lots: {t['lots']} (Qty: {t['quantity']}) | Capital Used: ₹{t['capital_used']:,.2f}")
            print(f"   Gross PnL: ₹{t['gross_pnl']:,.2f} | Net PnL: ₹{t['net_pnl']:,.2f} ({t['result']})")
            print(f"   Reason: {t['exit_reason']}")

    # Save today's output
    with open("data/backtest_today.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Comparative Backtest Analysis:
Baseline ILSME Reversal Sniper vs. Dual-Engine (ILSME Reversal + Momentum Trend / ORB Breakout).
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartapi_trader.utils.charges import calculate_option_charges

def run_dual_strategy_backtest(
    starting_capital: float = 50000.0,
    risk_per_trade_pct: float = 0.015,
    max_trades_per_day: int = 2,
    enable_momentum_breakout: bool = True,
    quick_fee_lock: bool = False,
    dynamic_compounding: bool = False
) -> Dict[str, Any]:
    
    indices_data = {}
    for idx in ["nifty", "banknifty", "sensex"]:
        path_15m = f"data/historical/{idx}_15m.json"
        path_3m = f"data/historical/{idx}_3m.json"
        if os.path.exists(path_15m) and os.path.exists(path_3m):
            with open(path_15m) as f1, open(path_3m) as f2:
                m15 = json.load(f1)
                m3 = json.load(f2)
                
                # 50-period EMA on 15m
                k = 2.0 / (50.0 + 1.0)
                cur_ema = m15[0][4]
                ema_map = {}
                for b in m15:
                    cur_ema = (b[4] * k) + (cur_ema * (1.0 - k))
                    ema_map[b[0][:16]] = cur_ema

                indices_data[idx.upper()] = {
                    "15m": m15,
                    "3m": m3,
                    "ema": ema_map,
                    "lot_size": 65 if idx == "nifty" else (30 if idx == "banknifty" else 20),
                    "base_premium": 180.0 if idx == "nifty" else (350.0 if idx == "banknifty" else 220.0),
                    "fvg_min": 2.0 if idx == "nifty" else 5.0
                }

    all_dates = sorted(list(set(c[0][:10] for c in indices_data["NIFTY"]["3m"])))
    
    capital = starting_capital
    peak_capital = capital
    max_drawdown_pct = 0.0
    trades: List[Dict[str, Any]] = []
    prev_levels = {}

    initial_sl_pct = 0.10
    be_trigger_r = 0.60
    tp1_r = 2.2
    tp1_qty_pct = 0.50

    for date_str in all_dates:
        day_trades_count = 0
        day_consecutive_losses = 0
        active_trade_direction = None

        today_3m_by_idx = {
            u: [c for c in d["3m"] if c[0].startswith(date_str)]
            for u, d in indices_data.items()
        }

        session_state = {}
        for underlying in indices_data:
            session_state[underlying] = {
                "cum_pv": 0.0,
                "cum_vol": 0.0,
                "high": -1.0,
                "low": 999999.0,
                "or_high": -1.0,
                "or_low": 999999.0,
                "or_settled": False,
                "sweep_status": "NONE",
                "sweep_price": 0.0,
                "armed_signal": None,
                "in_trade": False
            }

        # Initialize reference levels if first day
        for underlying, d in indices_data.items():
            if underlying not in prev_levels:
                first_bars = d["3m"][:20]
                prev_levels[underlying] = {
                    "pdh": max(b[2] for b in first_bars) + (50 if underlying == "NIFTY" else 150),
                    "pdl": min(b[3] for b in first_bars) - (50 if underlying == "NIFTY" else 150)
                }

        num_intervals = len(today_3m_by_idx.get("NIFTY", []))

        for bar_i in range(num_intervals):
            for underlying, d in indices_data.items():
                bars = today_3m_by_idx.get(underlying, [])
                if bar_i >= len(bars):
                    continue

                bar = bars[bar_i]
                ts, o, h, l, c, v = bar[0], float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4]), float(bar[5])
                st = session_state[underlying]

                st["high"] = max(st["high"], h)
                st["low"] = min(st["low"], l)

                # Track 15-minute Opening Range (first 5 bars: 09:15 to 09:30)
                if bar_i < 5:
                    st["or_high"] = max(st["or_high"], h)
                    st["or_low"] = min(st["or_low"], l)
                elif bar_i == 5:
                    st["or_settled"] = True

                # Intraday VWAP
                typical_price = (h + l + c) / 3.0
                vol_weight = v if v > 0 else 1000.0
                st["cum_pv"] += typical_price * vol_weight
                st["cum_vol"] += vol_weight
                vwap = st["cum_pv"] / st["cum_vol"]
                time_part = ts[11:16]

                ema_val = d["ema"].get(ts[:16], c)

                # ========================================================
                # 1. ILSME REVERSAL SWEEP SCANNER
                # ========================================================
                if bar_i >= 4 and bar_i % 5 == 0:
                    sub = bars[bar_i-4 : bar_i+1]
                    o15, h15, l15, c15 = sub[0][1], max(b[2] for b in sub), min(b[3] for b in sub), sub[-1][4]
                    rng = max(0.01, h15 - l15)
                    lower_wick = (min(o15, c15) - l15) / rng
                    upper_wick = (h15 - max(o15, c15)) / rng

                    pdl = prev_levels[underlying]["pdl"]
                    pdh = prev_levels[underlying]["pdh"]

                    if l15 < pdl and c15 > pdl:
                        if (c15 >= ema_val and lower_wick >= 0.28) or (lower_wick >= 0.35):
                            st["sweep_status"] = "BULLISH_SWEEP"
                            st["sweep_price"] = l15

                    elif h15 > pdh and c15 < pdh:
                        if (c15 <= ema_val and upper_wick >= 0.28) or (upper_wick >= 0.35):
                            st["sweep_status"] = "BEARISH_SWEEP"
                            st["sweep_price"] = h15

                # 3m Micro Shift & FVG for ILSME
                min_gap = d["fvg_min"]
                if st["sweep_status"] != "NONE" and bar_i >= 2 and not st.get("armed_signal"):
                    if not ("11:15" <= time_part <= "13:30" or time_part >= "14:50"):
                        c1 = bars[bar_i - 2]
                        c2 = bars[bar_i - 1]
                        c3 = bars[bar_i]

                        if st["sweep_status"] == "BULLISH_SWEEP":
                            if c2[4] > c1[2] and c2[4] > vwap and (c3[3] - c1[2]) >= min_gap:
                                st["armed_signal"] = {
                                    "source": "ILSME_REVERSAL",
                                    "type": "BUY_CE",
                                    "top": c3[3],
                                    "bottom": c1[2],
                                    "swing_inval": c2[2]
                                }

                        elif st["sweep_status"] == "BEARISH_SWEEP":
                            if c2[4] < c1[3] and c2[4] < vwap and (c1[3] - c3[2]) >= min_gap:
                                st["armed_signal"] = {
                                    "source": "ILSME_REVERSAL",
                                    "type": "BUY_PE",
                                    "top": c1[3],
                                    "bottom": c3[2],
                                    "swing_inval": c2[3]
                                }

                # ========================================================
                # 2. MOMENTUM TREND / OPENING RANGE BREAKOUT (ORB) ENGINE
                # ========================================================
                if enable_momentum_breakout and st.get("or_settled") and not st.get("armed_signal") and not st.get("in_trade"):
                    # ORB Window: 09:30 to 11:15 IST and 13:30 to 14:30 IST
                    if ("09:30" <= time_part <= "11:15" or "13:30" <= time_part <= "14:30") and bar_i >= 5:
                        or_h = st["or_high"]
                        or_l = st["or_low"]
                        or_rng = or_h - or_l

                        # Bullish Breakout: 3m Close > OR High + Close > VWAP + Close > 50-EMA
                        if c > or_h and c > vwap and c > ema_val and (c - or_h) <= (or_rng * 0.40):
                            st["armed_signal"] = {
                                "source": "MOMENTUM_ORB",
                                "type": "BUY_CE",
                                "top": h,
                                "bottom": max(or_h, l),
                                "swing_inval": or_h
                            }

                        # Bearish Breakout: 3m Close < OR Low + Close < VWAP + Close < 50-EMA
                        elif c < or_l and c < vwap and c < ema_val and (or_l - c) <= (or_rng * 0.40):
                            st["armed_signal"] = {
                                "source": "MOMENTUM_ORB",
                                "type": "BUY_PE",
                                "top": min(or_l, h),
                                "bottom": l,
                                "swing_inval": or_l
                            }

                # ========================================================
                # 3. ORDER EXECUTION & MULTI-STAGE POSITION TRACKING
                # ========================================================
                if st.get("armed_signal") and not st.get("in_trade"):
                    if day_trades_count >= max_trades_per_day or day_consecutive_losses >= 2:
                        st["armed_signal"] = None
                        continue

                    if "11:15" <= time_part <= "13:30" and st["armed_signal"]["source"] == "ILSME_REVERSAL":
                        st["armed_signal"] = None
                        continue

                    if time_part >= "15:00":
                        st["armed_signal"] = None
                        continue

                    sig = st["armed_signal"]
                    if active_trade_direction == sig["type"]:
                        continue

                    is_fill = (sig["type"] == "BUY_CE" and l <= sig["top"]) or \
                              (sig["type"] == "BUY_PE" and h >= sig["bottom"])

                    if is_fill:
                        st["armed_signal"] = None
                        st["sweep_status"] = "NONE"
                        st["in_trade"] = True
                        active_trade_direction = sig["type"]
                        day_trades_count += 1

                        lot_size = d["lot_size"]
                        dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        w_day = dt_obj.weekday()
                        exp_wday = 3 if underlying == "SENSEX" else 1
                        dte = (exp_wday - w_day) % 7
                        if dte == 0:
                            dte = 7

                        if underlying == "NIFTY":
                            entry_opt = round(120.0 + (dte * 8.0), 2)
                        elif underlying == "BANKNIFTY":
                            entry_opt = round(260.0 + (dte * 16.0), 2)
                        else:
                            entry_opt = round(170.0 + (dte * 12.0), 2)

                        sl_opt = round(entry_opt * (1.0 - initial_sl_pct), 2)
                        unit_risk = entry_opt - sl_opt

                        if dynamic_compounding:
                            profit_cushion = max(0.0, capital - starting_capital)
                            capital_at_risk = (capital * risk_per_trade_pct) + (profit_cushion * 0.07)
                        else:
                            capital_at_risk = capital * risk_per_trade_pct

                        lots = max(1, math.floor(capital_at_risk / (unit_risk * lot_size)))
                        max_lots_margin = max(1, math.floor((capital * 0.75) / (entry_opt * lot_size)))
                        lots = min(lots, max_lots_margin)
                        qty = lots * lot_size

                        cap_before = round(capital, 2)
                        cap_used = round(entry_opt * qty, 2)
                        entry_time = ts
                        entry_spot = c
                        trade_type = sig["type"]
                        source_engine = sig["source"]

                        step = 50 if underlying == "NIFTY" else 100
                        strike_price = int(round(entry_spot / step) * step)
                        opt_label = "CE" if trade_type == "BUY_CE" else "PE"
                        tradingsymbol = f"{underlying} {strike_price} {opt_label}"

                        target_be = unit_risk * be_trigger_r
                        target_tp1 = unit_risk * tp1_r
                        target_tp1_price = entry_opt + target_tp1

                        be_moved = False
                        partial_sold = False
                        realized_gross = 0.0
                        remaining_qty = qty
                        exit_price = entry_opt
                        exit_time = ts
                        exit_reason = "15:12 EOD Square-Off"

                        for fwd_i in range(bar_i + 1, len(bars)):
                            fb = bars[fwd_i]
                            f_ts, f_h, f_l, f_c = fb[0], fb[2], fb[3], fb[4]
                            f_time = f_ts[11:16]
                            delta = 0.52

                            if trade_type == "BUY_CE":
                                spot_move = f_c - entry_spot
                                high_move = f_h - entry_spot
                                low_move = f_l - entry_spot
                            else:
                                spot_move = entry_spot - f_c
                                high_move = entry_spot - f_l
                                low_move = entry_spot - f_h

                            curr_opt_high = entry_opt + (high_move * delta)
                            curr_opt_low = entry_opt + (low_move * delta)
                            curr_opt_close = entry_opt + (spot_move * delta)

                            # Quick Fee Lock (if enabled): book 25% at +1.2R
                            if quick_fee_lock and not partial_sold and (curr_opt_high - entry_opt) >= (unit_risk * 1.2):
                                quick_qty = max(lot_size, int(qty * 0.25 // lot_size) * lot_size)
                                realized_gross += (unit_risk * 1.2) * quick_qty
                                remaining_qty -= quick_qty
                                be_moved = True

                            # Hard SL Invalidation
                            if not be_moved and curr_opt_low <= sl_opt:
                                exit_price = sl_opt
                                exit_time = f_ts
                                exit_reason = "Hard Stop-Loss (-10%)"
                                break

                            # Breakeven Stop Invalidation
                            elif be_moved and curr_opt_low <= entry_opt:
                                exit_price = entry_opt
                                exit_time = f_ts
                                exit_reason = "Breakeven / Scratch Stop (+0.0R)"
                                break

                            # Breakeven Trigger at +0.6R to +0.8R
                            if not be_moved and (curr_opt_high - entry_opt) >= target_be:
                                be_moved = True

                            # Target 1 (+2.2R) Lock
                            if not partial_sold and curr_opt_high >= target_tp1_price:
                                partial_sold = True
                                partial_qty = max(lot_size, int(qty * tp1_qty_pct // lot_size) * lot_size)
                                realized_gross += (target_tp1_price - entry_opt) * partial_qty
                                remaining_qty -= partial_qty

                            # EOD Mandatory Close (15:12)
                            if f_time >= "15:12":
                                exit_price = curr_opt_close
                                exit_time = f_ts
                                exit_reason = "15:12 EOD Square-Off"
                                break

                        # Compute final gross & net PnL
                        gross_pnl = realized_gross + ((exit_price - entry_opt) * remaining_qty)
                        charges = calculate_option_charges(entry_opt, exit_price, qty, "NFO")
                        net_pnl = round(gross_pnl - charges["total_charges"], 2)

                        capital += net_pnl
                        if capital > peak_capital:
                            peak_capital = capital
                        cur_dd = (peak_capital - capital) / peak_capital * 100.0 if peak_capital > 0 else 0.0
                        if cur_dd > max_drawdown_pct:
                            max_drawdown_pct = cur_dd

                        res_label = "WIN" if gross_pnl > 50 else ("BREAKEVEN" if abs(gross_pnl) <= 50 else "LOSS")
                        if res_label == "LOSS":
                            day_consecutive_losses += 1
                        else:
                            day_consecutive_losses = 0

                        trades.append({
                            "id": f"TR_{date_str}_{len(trades)+1:03d}",
                            "date": date_str,
                            "source_engine": source_engine,
                            "underlying": underlying,
                            "tradingsymbol": tradingsymbol,
                            "type": trade_type,
                            "lots": lots,
                            "quantity": qty,
                            "capital_used": cap_used,
                            "entry_price": entry_opt,
                            "exit_price": round(exit_price, 2),
                            "gross_pnl": round(gross_pnl, 2),
                            "total_charges": charges["total_charges"],
                            "net_pnl": net_pnl,
                            "exit_reason": exit_reason,
                            "result": res_label
                        })

                        st["in_trade"] = False
                        active_trade_direction = None

        # Update PDH/PDL for next session
        for underlying, d in indices_data.items():
            today_bars = today_3m_by_idx.get(underlying, [])
            if today_bars:
                prev_levels[underlying] = {
                    "pdh": max(b[2] for b in today_bars),
                    "pdl": min(b[3] for b in today_bars)
                }

    # Summary Statistics
    total_trades = len(trades)
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    be = [t for t in trades if t["result"] == "BREAKEVEN"]

    total_gross = sum(t["gross_pnl"] for t in trades)
    total_charges = sum(t["total_charges"] for t in trades)
    total_net = sum(t["net_pnl"] for t in trades)

    win_rate = (len(wins) / total_trades * 100.0) if total_trades else 0.0
    non_loss_rate = ((len(wins) + len(be)) / total_trades * 100.0) if total_trades else 0.0

    gross_profit = sum(t["gross_pnl"] for t in wins)
    gross_loss = abs(sum(t["gross_pnl"] for t in losses))
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.9

    avg_win = round(sum(t["net_pnl"] for t in wins) / len(wins), 2) if wins else 0.0
    avg_loss = round(sum(t["net_pnl"] for t in losses) / len(losses), 2) if losses else 0.0

    return {
        "summary": {
            "period": f"{all_dates[0]} to {all_dates[-1]} ({len(all_dates)} Sessions)",
            "starting_capital": starting_capital,
            "ending_capital": round(capital, 2),
            "total_net_pnl": round(total_net, 2),
            "total_gross_pnl": round(total_gross, 2),
            "total_brokerage_and_taxes": round(total_charges, 2),
            "roi_pct": round((total_net / starting_capital) * 100.0, 2),
            "win_rate_pct": round(win_rate, 1),
            "non_losing_rate_pct": round(non_loss_rate, 1),
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "breakeven": len(be),
            "profit_factor": pf,
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "trades_by_engine": {
                "ILSME_REVERSAL": len([t for t in trades if t.get("source_engine") == "ILSME_REVERSAL"]),
                "MOMENTUM_ORB": len([t for t in trades if t.get("source_engine") == "MOMENTUM_ORB"])
            }
        },
        "trades": trades
    }

if __name__ == "__main__":
    print("=" * 75)
    print("🚀 QUANTITATIVE STRATEGY COMPARISON: BASELINE vs DUAL-ENGINE")
    print("=" * 75)

    # 1. Baseline ILSME (Reversal Only)
    res_baseline = run_dual_strategy_backtest(
        starting_capital=50000.0,
        risk_per_trade_pct=0.015,
        enable_momentum_breakout=False,
        quick_fee_lock=False,
        dynamic_compounding=False
    )

    # 2. Dual Engine (ILSME Reversal + Momentum Trend ORB)
    res_dual = run_dual_strategy_backtest(
        starting_capital=50000.0,
        risk_per_trade_pct=0.015,
        enable_momentum_breakout=True,
        quick_fee_lock=False,
        dynamic_compounding=False
    )

    # 3. Optimized Dual Engine (Dual Engine + Quick Fee Lock to eliminate BE friction)
    res_dual_opt = run_dual_strategy_backtest(
        starting_capital=50000.0,
        risk_per_trade_pct=0.015,
        enable_momentum_breakout=True,
        quick_fee_lock=True,
        dynamic_compounding=False
    )

    print("\n1. BASELINE: Pure ILSME Reversal Sniper")
    print(json.dumps(res_baseline["summary"], indent=2))

    print("\n2. DUAL-ENGINE: ILSME Reversal + Momentum Trend ORB Breakout")
    print(json.dumps(res_dual["summary"], indent=2))

    print("\n3. OPTIMIZED DUAL-ENGINE: Dual-Engine + Quick Fee Buffer Lock (+1.2R)")
    print(json.dumps(res_dual_opt["summary"], indent=2))

    with open("data/backtest_comparison.json", "w") as f:
        json.dump({
            "baseline": res_baseline["summary"],
            "dual_engine": res_dual["summary"],
            "optimized_dual_engine": res_dual_opt["summary"]
        }, f, indent=2)

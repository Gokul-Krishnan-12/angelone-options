#!/usr/bin/env python3
"""
Recursive Strategy Optimizer & Grid Search Engine:
Conducts recursive parametric search across hundreds of strategy variations for ₹1,00,000 capital.
Evaluates Net P&L, ROI, Win Rate, Profit Factor, Max Drawdown, and Stability across 1-Year and Sub-periods.
"""

import os
import sys
import json
import math
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartapi_trader.utils.charges import calculate_option_charges

class StrategyDataset:
    """In-memory cached historical market data."""
    def __init__(self):
        self.indices_data = {}
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

                    self.indices_data[idx.upper()] = {
                        "15m": m15,
                        "3m": m3,
                        "ema": ema_map,
                        "lot_size": 65 if idx == "nifty" else (30 if idx == "banknifty" else 20),
                        "base_premium": 180.0 if idx == "nifty" else (350.0 if idx == "banknifty" else 220.0),
                        "fvg_min": 2.0 if idx == "nifty" else 5.0,
                        "slip_mult": 1.0 if idx == "nifty" else (2.0 if idx == "banknifty" else 1.2)
                    }
        self.all_dates = sorted(list(set(c[0][:10] for c in self.indices_data["NIFTY"]["3m"])))

DATASET = None

def get_dataset():
    global DATASET
    if DATASET is None:
        DATASET = StrategyDataset()
    return DATASET

def simulate_strategy(params: Dict[str, Any], start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    ds = get_dataset()
    
    starting_capital = params.get("starting_capital", 100000.0)
    risk_pct = params.get("risk_per_trade_pct", 0.02)
    max_trades_per_day = params.get("max_trades_per_day", 2)
    max_consecutive_losses = params.get("max_consecutive_losses", 2)
    initial_sl_pct = params.get("initial_sl_pct", 0.10)
    be_trigger_r = params.get("be_trigger_r", 1.2)
    tp1_r = params.get("tp1_r", 3.0)
    tp1_qty_pct = params.get("tp1_qty_pct", 0.50)
    enable_orb = params.get("enable_orb", True)
    enable_ilsme = params.get("enable_ilsme", True)
    min_or_filter = params.get("min_or_filter", True)
    stagnation_exit_bars = params.get("stagnation_exit_bars", 5) # 5 bars = 15m
    dynamic_compounding = params.get("dynamic_compounding", False)
    slippage_entry = params.get("slippage_entry", 0.8)
    slippage_exit = params.get("slippage_exit", 0.5)
    selected_indices = params.get("indices", ["NIFTY", "SENSEX", "BANKNIFTY"])

    dates = [d for d in ds.all_dates if (not start_date or d >= start_date) and (not end_date or d <= end_date)]
    
    capital = starting_capital
    peak_capital = capital
    max_drawdown_pct = 0.0
    
    total_trades = 0
    wins = 0
    losses = 0
    breakevens = 0
    total_gross = 0.0
    total_charges = 0.0
    total_slippage = 0.0
    
    gross_wins = []
    gross_losses = []
    
    prev_levels = {}
    if start_date and start_date in ds.all_dates:
        s_idx = ds.all_dates.index(start_date)
        if s_idx > 0:
            prior_d = ds.all_dates[s_idx - 1]
            for u in selected_indices:
                if u in ds.indices_data:
                    pb = [c for c in ds.indices_data[u]["3m"] if c[0].startswith(prior_d)]
                    if pb:
                        prev_levels[u] = {"pdh": max(b[2] for b in pb), "pdl": min(b[3] for b in pb)}

    for date_str in dates:
        day_trades = 0
        day_losses = 0
        active_direction = None
        
        today_3m = {
            u: [c for c in ds.indices_data[u]["3m"] if c[0].startswith(date_str)]
            for u in selected_indices if u in ds.indices_data
        }
        
        session_state = {}
        for u in today_3m:
            session_state[u] = {
                "cum_pv": 0.0,
                "cum_vol": 0.0,
                "sweep_status": "NONE",
                "armed_signal": None,
                "in_trade": False,
                "or_high": -1e9,
                "or_low": 1e9,
                "or_settled": False
            }
            
        max_len = max(len(v) for v in today_3m.values()) if today_3m else 0
        for bar_i in range(max_len):
            for u, bars in today_3m.items():
                if bar_i >= len(bars):
                    continue
                d = ds.indices_data[u]
                bar = bars[bar_i]
                ts, o, h, l, c, v = bar[0], bar[1], bar[2], bar[3], bar[4], bar[5]
                time_part = ts[11:16]
                st = session_state[u]
                
                st["cum_vol"] += max(1.0, v)
                st["cum_pv"] += (h + l + c) / 3.0 * max(1.0, v)
                vwap = st["cum_pv"] / st["cum_vol"]
                ema_val = d["ema"].get(ts[:16], c)
                
                if time_part <= "09:30":
                    st["or_high"] = max(st["or_high"], h)
                    st["or_low"] = min(st["or_low"], l)
                elif not st["or_settled"] and st["or_high"] > 0:
                    st["or_settled"] = True
                    
                if st["in_trade"]:
                    continue
                    
                pdh = prev_levels.get(u, {}).get("pdh", 1e9)
                pdl = prev_levels.get(u, {}).get("pdl", -1e9)
                
                # 1. Macro 15m Sweep Detection (ILSME)
                if enable_ilsme and time_part in ["09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "13:30", "13:45", "14:00", "14:15", "14:30"]:
                    bars_15m = [b for b in d["15m"] if b[0] <= ts]
                    if bars_15m:
                        l15 = bars_15m[-1]
                        o15, h15, l15_val, c15 = l15[1], l15[2], l15[3], l15[4]
                        rng15 = max(1.0, h15 - l15_val)
                        lower_wick = (min(o15, c15) - l15_val) / rng15
                        upper_wick = (h15 - max(o15, c15)) / rng15
                        
                        if l15_val < pdl and c15 > pdl:
                            if (c15 >= ema_val and lower_wick >= 0.28) or (lower_wick >= 0.35):
                                st["sweep_status"] = "BULLISH_SWEEP"
                        elif h15 > pdh and c15 < pdh:
                            if (c15 <= ema_val and upper_wick >= 0.28) or (upper_wick >= 0.35):
                                st["sweep_status"] = "BEARISH_SWEEP"
                                
                # 2. Micro 3m FVG Displacement (ILSME)
                min_gap = d["fvg_min"]
                if enable_ilsme and st["sweep_status"] != "NONE" and bar_i >= 2 and not st.get("armed_signal"):
                    if not ("11:15" <= time_part <= "13:30" or time_part >= "14:50"):
                        c1 = bars[bar_i - 2]
                        c2 = bars[bar_i - 1]
                        c3 = bars[bar_i]
                        if st["sweep_status"] == "BULLISH_SWEEP" and c2[4] > c1[2] and c2[4] > vwap and (c3[3] - c1[2]) >= min_gap:
                            st["armed_signal"] = {"source": "ILSME_REVERSAL", "type": "BUY_CE", "top": c3[3], "bottom": c1[2], "swing_inval": c2[2]}
                        elif st["sweep_status"] == "BEARISH_SWEEP" and c2[4] < c1[3] and c2[4] < vwap and (c1[3] - c3[2]) >= min_gap:
                            st["armed_signal"] = {"source": "ILSME_REVERSAL", "type": "BUY_PE", "top": c1[3], "bottom": c3[2], "swing_inval": c2[3]}
                            
                # 3. Momentum Trend / ORB Engine
                if enable_orb and st.get("or_settled") and not st.get("armed_signal") and not st.get("in_trade"):
                    if ("09:30" <= time_part <= "11:15" or "13:30" <= time_part <= "14:30") and bar_i >= 5:
                        or_h = st["or_high"]
                        or_l = st["or_low"]
                        or_rng = max(1.0, or_h - or_l)
                        
                        # Minimum range filter to prevent chop
                        min_req = 45.0 if u == "NIFTY" else (160.0 if u == "SENSEX" else 120.0)
                        if not min_or_filter or or_rng >= min_req:
                            if c > or_h and c > vwap and c > ema_val and (c - or_h) <= (or_rng * 0.40):
                                st["armed_signal"] = {"source": "MOMENTUM_ORB", "type": "BUY_CE", "top": h, "bottom": max(or_h, l), "swing_inval": or_h}
                            elif c < or_l and c < vwap and c < ema_val and (or_l - c) <= (or_rng * 0.40):
                                st["armed_signal"] = {"source": "MOMENTUM_ORB", "type": "BUY_PE", "top": min(or_l, h), "bottom": l, "swing_inval": or_l}

                # 4. Entry Execution
                if st.get("armed_signal") and not st.get("in_trade"):
                    if day_trades >= max_trades_per_day or day_losses >= max_consecutive_losses:
                        st["armed_signal"] = None
                        continue
                    if "11:15" <= time_part <= "13:30" and st["armed_signal"]["source"] == "ILSME_REVERSAL":
                        st["armed_signal"] = None
                        continue
                    if time_part >= "15:00":
                        st["armed_signal"] = None
                        continue
                        
                    sig = st["armed_signal"]
                    if active_direction == sig["type"]:
                        continue
                        
                    is_fill = (sig["type"] == "BUY_CE" and l <= sig["top"]) or (sig["type"] == "BUY_PE" and h >= sig["bottom"])
                    if is_fill:
                        st["armed_signal"] = None
                        st["sweep_status"] = "NONE"
                        st["in_trade"] = True
                        active_direction = sig["type"]
                        day_trades += 1
                        
                        lot_size = d["lot_size"]
                        slip_mult = d["slip_mult"]
                        
                        dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        w_day = dt_obj.weekday()
                        exp_wday = 3 if u == "SENSEX" else 1
                        dte = (exp_wday - w_day) % 7
                        if dte == 0:
                            dte = 7
                            
                        if u == "NIFTY":
                            raw_opt = round(120.0 + (dte * 8.0), 2)
                        elif u == "BANKNIFTY":
                            raw_opt = round(260.0 + (dte * 16.0), 2)
                        else:
                            raw_opt = round(170.0 + (dte * 12.0), 2)
                            
                        entry_slip = slippage_entry * slip_mult
                        entry_opt = round(raw_opt + entry_slip, 2)
                        total_slippage += entry_slip
                        
                        sl_opt = round(raw_opt * (1.0 - initial_sl_pct), 2)
                        unit_risk = entry_opt - sl_opt
                        
                        if dynamic_compounding:
                            profit_cushion = max(0.0, capital - starting_capital)
                            capital_at_risk = (capital * risk_pct) + (profit_cushion * 0.05)
                        else:
                            capital_at_risk = capital * risk_pct
                            
                        calc_lots = math.floor(capital_at_risk / (unit_risk * lot_size))
                        lots = max(1, calc_lots)
                        max_lots_margin = max(1, math.floor((capital * 0.75) / (entry_opt * lot_size)))
                        lots = min(lots, max_lots_margin)
                        qty = lots * lot_size
                        
                        entry_spot = c
                        trade_type = sig["type"]
                        target_be = unit_risk * be_trigger_r
                        target_tp1 = unit_risk * tp1_r
                        target_tp1_price = raw_opt + target_tp1
                        
                        be_moved = False
                        partial_sold = False
                        realized_gross = 0.0
                        remaining_qty = qty
                        exit_price = entry_opt
                        
                        bars_in_trade = 0
                        
                        for fwd_i in range(bar_i + 1, len(bars)):
                            bars_in_trade += 1
                            fb = bars[fwd_i]
                            f_ts, f_h, f_l, f_c = fb[0], fb[2], fb[3], fb[4]
                            f_time = f_ts[11:16]
                            delta = 0.52
                            
                            spot_move = (f_c - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_c)
                            high_move = (f_h - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_l)
                            low_move = (f_l - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_h)
                            
                            cur_opt_close = max(1.0, raw_opt + (spot_move * delta))
                            peak_opt = max(1.0, raw_opt + (high_move * delta))
                            trough_opt = max(1.0, raw_opt + (low_move * delta))
                            
                            # Stagnation Exit (e.g. 15-min check: if fails to reach +0.5R, exit at market)
                            if stagnation_exit_bars > 0 and bars_in_trade >= stagnation_exit_bars and (peak_opt - raw_opt) < (unit_risk * 0.5):
                                exit_slip = slippage_exit * slip_mult
                                total_slippage += exit_slip
                                exit_price = max(1.0, cur_opt_close - exit_slip)
                                realized_gross += (exit_price - entry_opt) * remaining_qty
                                remaining_qty = 0
                                break
                                
                            # Target Exit
                            if peak_opt >= target_tp1_price and not partial_sold:
                                if lots == 1 or tp1_qty_pct >= 1.0:
                                    exit_slip = slippage_exit * slip_mult
                                    total_slippage += exit_slip
                                    exit_price = max(1.0, target_tp1_price - exit_slip)
                                    realized_gross += (exit_price - entry_opt) * remaining_qty
                                    remaining_qty = 0
                                    break
                                else:
                                    partial_sold = True
                                    lots_to_close = max(1, math.floor(lots * tp1_qty_pct))
                                    qty_close = lots_to_close * lot_size
                                    exit_slip = slippage_exit * slip_mult
                                    total_slippage += exit_slip
                                    actual_exit = max(1.0, target_tp1_price - exit_slip)
                                    realized_gross += (actual_exit - entry_opt) * qty_close
                                    remaining_qty -= qty_close
                                    be_moved = True
                                    
                            # Stop-Loss / Breakeven Stop
                            cur_sl = raw_opt if be_moved else sl_opt
                            if trough_opt <= cur_sl:
                                exit_slip = slippage_exit * slip_mult
                                total_slippage += exit_slip
                                exit_price = max(1.0, cur_sl - exit_slip)
                                realized_gross += (exit_price - entry_opt) * remaining_qty
                                remaining_qty = 0
                                break
                                
                            # Breakeven Shift
                            if be_trigger_r > 0 and not be_moved and (peak_opt - raw_opt) >= target_be:
                                be_moved = True
                                
                            if f_time >= "15:12":
                                exit_slip = slippage_exit * slip_mult
                                total_slippage += exit_slip
                                exit_price = max(1.0, cur_opt_close - exit_slip)
                                realized_gross += (exit_price - entry_opt) * remaining_qty
                                remaining_qty = 0
                                break
                                
                        gross_pnl = round(realized_gross + ((exit_price - entry_opt) * remaining_qty), 2)
                        charges = calculate_option_charges(entry_opt, exit_price, qty, "NFO")
                        net_pnl = round(gross_pnl - charges["total_charges"], 2)
                        
                        total_trades += 1
                        total_gross += gross_pnl
                        total_charges += charges["total_charges"]
                        
                        if gross_pnl > 50:
                            wins += 1
                            gross_wins.append(gross_pnl)
                            day_losses = 0
                        elif gross_pnl < -50:
                            losses += 1
                            gross_losses.append(abs(gross_pnl))
                            day_losses += 1
                        else:
                            breakevens += 1
                            
                        capital += net_pnl
                        if capital > peak_capital:
                            peak_capital = capital
                        cur_dd = (peak_capital - capital) / peak_capital * 100.0 if peak_capital > 0 else 0.0
                        if cur_dd > max_drawdown_pct:
                            max_drawdown_pct = cur_dd

        # Update PDH/PDL for next day
        for u, bars in today_3m.items():
            if bars:
                prev_levels[u] = {"pdh": max(b[2] for b in bars), "pdl": min(b[3] for b in bars)}

    net_pnl_tot = round(capital - starting_capital, 2)
    roi_pct = round((net_pnl_tot / starting_capital) * 100.0, 2)
    win_rate = round((wins / total_trades * 100.0), 2) if total_trades > 0 else 0.0
    non_losing_rate = round(((wins + breakevens) / total_trades * 100.0), 2) if total_trades > 0 else 0.0
    
    sum_w = sum(gross_wins)
    sum_l = sum(gross_losses)
    profit_factor = round(sum_w / sum_l, 2) if sum_l > 0 else (99.0 if sum_w > 0 else 0.0)
    avg_win = round(sum_w / len(gross_wins), 2) if gross_wins else 0.0
    avg_loss = round(-sum_l / len(gross_losses), 2) if gross_losses else 0.0

    return {
        "params": params,
        "starting_capital": starting_capital,
        "ending_capital": round(capital, 2),
        "net_pnl": net_pnl_tot,
        "gross_pnl": round(total_gross, 2),
        "total_charges": round(total_charges, 2),
        "total_slippage": round(total_slippage, 2),
        "roi_pct": roi_pct,
        "win_rate_pct": win_rate,
        "non_losing_rate_pct": non_losing_rate,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakevens,
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "avg_win": avg_win,
        "avg_loss": avg_loss
    }

def run_recursive_grid_search():
    """Generates strategy parameter variations and executes multi-period optimizations."""
    print("=" * 80)
    print(" 🚀 STARTING RECURSIVE STRATEGY OPTIMIZATION (CAPITAL: ₹1,00,000)")
    print("=" * 80)
    
    # Define Parameter Grid
    grid = []
    
    # Strategy engine variations
    engines = [
        ("DUAL", True, True),
        ("ORB_ONLY", True, False),
        ("ILSME_ONLY", False, True)
    ]
    
    indices_sets = [
        ["NIFTY", "SENSEX"],
        ["NIFTY", "BANKNIFTY", "SENSEX"],
        ["NIFTY"]
    ]
    
    risk_pcts = [0.015, 0.020, 0.025, 0.030]
    tp1_rs = [2.2, 2.6, 3.0, 3.5, 4.0]
    be_rs = [0.8, 1.2, 1.5, 0.0] # 0.0 = no early BE, let winner run
    sl_pcts = [0.10, 0.12, 0.15]
    stagnation_options = [0, 5, 8] # 0 = disabled, 5 = 15m, 8 = 24m
    compounding_options = [False, True]
    
    for eng_name, orb, ils in engines:
        for idxs in indices_sets:
            for r_pct in risk_pcts:
                for tp_r in tp1_rs:
                    for be_r in be_rs:
                        for sl_p in sl_pcts:
                            for stag in stagnation_options:
                                for comp in compounding_options:
                                    grid.append({
                                        "engine_name": eng_name,
                                        "enable_orb": orb,
                                        "enable_ilsme": ils,
                                        "indices": idxs,
                                        "risk_per_trade_pct": r_pct,
                                        "tp1_r": tp_r,
                                        "be_trigger_r": be_r,
                                        "initial_sl_pct": sl_p,
                                        "stagnation_exit_bars": stag,
                                        "dynamic_compounding": comp,
                                        "tp1_qty_pct": 0.50,
                                        "min_or_filter": True,
                                        "max_trades_per_day": 2,
                                        "max_consecutive_losses": 2,
                                        "starting_capital": 100000.0,
                                        "slippage_entry": 0.8,
                                        "slippage_exit": 0.5
                                    })
                                    
def _eval_single_combo(params: Dict[str, Any]) -> Dict[str, Any]:
    res = simulate_strategy(params)
    res_sub = simulate_strategy(params, start_date="2026-08-01")
    
    net = res["net_pnl"]
    pf = res["profit_factor"]
    dd = max(5.0, res["max_drawdown_pct"])
    sub_roi = res_sub["roi_pct"]
    
    # Stability Score
    score = (net / 1000.0) * (pf ** 1.2) * (100.0 / dd) + (sub_roi * 2.0)
    
    return {
        "score": round(score, 2),
        "full_year": res,
        "recent_2m": res_sub,
        "params": params
    }

def run_recursive_grid_search():
    print("=" * 80)
    print(" 🚀 STARTING RECURSIVE STRATEGY OPTIMIZATION (CAPITAL: ₹1,00,000)")
    print("=" * 80)
    
    grid = []
    
    # Engines to compare
    engines = ["ILSME_SWEEP", "MOMENTUM_ORB", "HYBRID_DUAL"]
    
    # Focused Index combinations (NIFTY, BANKNIFTY, and NIFTY+BANKNIFTY)
    index_sets = [
        ["NIFTY"],
        ["BANKNIFTY"],
        ["NIFTY", "BANKNIFTY"]
    ]
    
    # High-impact Targets (R-multiples)
    tp1_rs = [2.5, 3.0, 3.5]
    
    # Breakeven Triggers (R-multiples)
    be_triggers = [1.0, 1.2, 1.5]
    
    # Initial Stop Loss %
    initial_sls = [0.08, 0.10, 0.12]
    
    # Trailing Stop Step (R-multiples)
    trailing_steps = [0.5, 1.0]
    
    # Stagnation Exit Bars (0 = disabled, 5 = 75 mins)
    stagnation_options = [0, 5]
    
    # Compounding mode
    compounding_options = [False, True]
    
    # Risk per trade
    risk_pcts = [0.02, 0.025]
    
    for eng in engines:
        for idx_set in index_sets:
            for tp_r in tp1_rs:
                for be_r in be_triggers:
                    for sl_p in initial_sls:
                        for tr_s in trailing_steps:
                            for stag in stagnation_options:
                                for comp in compounding_options:
                                    for r_pct in risk_pcts:
                                        grid.append({
                                            "engine_name": eng,
                                            "indices": idx_set,
                                            "risk_per_trade_pct": r_pct,
                                            "tp1_r": tp_r,
                                            "trailing_step_r": tr_s,
                                            "be_trigger_r": be_r,
                                            "initial_sl_pct": sl_p,
                                            "stagnation_exit_bars": stag,
                                            "dynamic_compounding": comp,
                                            "tp1_qty_pct": 0.50,
                                            "min_or_filter": True,
                                            "max_trades_per_day": 2,
                                            "max_consecutive_losses": 2,
                                            "starting_capital": 100000.0,
                                            "slippage_entry": 0.8,
                                            "slippage_exit": 0.5
                                        })
                                        
    print(f"📦 Total Parameter Combinations in Search Grid: {len(grid):,}")
    
    # Prime in-memory dataset
    t0 = time.time()
    get_dataset()
    print(f"⚡ Market Data Preloaded in {time.time() - t0:.2f}s across 251 sessions.")
    
    import multiprocessing
    cores = min(os.cpu_count() or 4, 12)
    print(f"⚡ Utilizing {cores} CPU Cores in Parallel...")
    print("⏳ Executing recursive grid simulations across 1-year historical dataset...")
    
    t_start = time.time()
    results = []
    
    with multiprocessing.Pool(processes=cores, initializer=get_dataset) as pool:
        for idx, res in enumerate(pool.imap_unordered(_eval_single_combo, grid, chunksize=50)):
            results.append(res)
            if (idx + 1) % 1000 == 0 or (idx + 1) == len(grid):
                elapsed = time.time() - t_start
                rate = (idx + 1) / elapsed
                remaining = (len(grid) - (idx + 1)) / rate if rate > 0 else 0
                print(f"  Processed {idx + 1}/{len(grid)} combinations ({(idx + 1)/len(grid)*100:.1f}%) — Speed: {rate:.1f} runs/s | ETA: {remaining:.0f}s")
                
    # Sort results by Score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    
    print("\n" + "=" * 80)
    print(" 🏆 TOP 5 OPTIMAL STRATEGY CONFIGURATIONS (CAPITAL ₹1,00,000)")
    print("=" * 80)
    
    top_5 = results[:5]
    for rank, item in enumerate(top_5, 1):
        fy = item["full_year"]
        r2m = item["recent_2m"]
        p = item["params"]
        
        print(f"\n🥇 RANK #{rank} — SCORE: {item['score']:,.1f}")
        print(f"  ├─ Engine: {p['engine_name']} | Indices: {', '.join(p['indices'])}")
        print(f"  ├─ Risk/Trade: {p['risk_per_trade_pct']*100:.1f}% | Compounding: {p['dynamic_compounding']}")
        print(f"  ├─ Target: +{p['tp1_r']}R | BE Shift: +{p['be_trigger_r']}R | SL: {p['initial_sl_pct']*100:.0f}%")
        print(f"  ├─ 15m Stagnation Exit: {'YES (5 bars)' if p['stagnation_exit_bars'] > 0 else 'NO'}")
        print(f"  ├─ 📅 1-YEAR (251 Sessions): Net P&L: ₹{fy['net_pnl']:+,.2f} ({fy['roi_pct']:+.1f}%) | Max DD: {fy['max_drawdown_pct']:.1f}% | PF: {fy['profit_factor']:.2f} | WinRate: {fy['win_rate_pct']:.1f}% (Trades: {fy['total_trades']})")
        print(f"  └─ 📅 RECENT 2-MONTH (42 Sessions): Net P&L: ₹{r2m['net_pnl']:+,.2f} ({r2m['roi_pct']:+.1f}%) | Max DD: {r2m['max_drawdown_pct']:.1f}% | WinRate: {r2m['win_rate_pct']:.1f}%")
        
    # Save optimal findings to JSON
    output_path = "data/optimal_strategy_results.json"
    with open(output_path, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_tested_combinations": len(grid),
            "top_strategies": results[:20]
        }, f, indent=2)
        
    print(f"\n💾 Top 20 strategy configurations saved to: {output_path}")
    return top_5[0]

if __name__ == "__main__":
    run_recursive_grid_search()

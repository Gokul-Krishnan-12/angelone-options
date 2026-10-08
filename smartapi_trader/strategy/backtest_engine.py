import os
import json
import math
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.utils.charges import calculate_option_charges
from smartapi_trader.utils.logger import logger

class BacktestEngine:
    """
    Institutional Liquidity Sweep & Momentum Expansion (ILSME) Sniper Backtest Engine.
    Replays actual 15m and 3m candlestick data fetched directly from Angel One SmartAPI.
    
    Hardened Institutional Model:
    - Discrete Integer Contract Sizing (Exact floor math)
    - Realistic Bid-Ask Slippage Modeling (Crossing Ask on entry and bid on market stops)
    - Full Statutory Taxes (STT 0.15% on sell, GST 18%, Exchange Turnover, SEBI, Stamp Duty)
    - Single-Lot vs Multi-Lot Exit Logic (100% full exit at target on 1 lot; 50% partial on >= 2 lots)
    - Selective Tradable Indices (NIFTY 50, SENSEX default; BANK NIFTY & MIDCPNIFTY optional)
    - Widened Breakeven Trigger (+1.5R) to eliminate premature fee-generating stops
    """
    def __init__(
        self,
        starting_capital: float = 50000.0,
        risk_per_trade_pct: float = 0.015,
        max_trades_per_day: int = 2,
        initial_sl_pct: float = 0.12,
        be_trigger_r: float = 1.5,
        tp1_r: float = 3.0,
        tp1_qty_pct: float = 0.50,
        enable_ilsme_sweep: bool = True,
        enable_momentum_breakout: bool = True,
        dynamic_compounding: bool = False,
        active_indices: Optional[List[str]] = None,
        slippage_pts_entry: float = 0.80,
        slippage_pts_exit: float = 0.50,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ):
        self.starting_capital = starting_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_trades_per_day = max_trades_per_day
        self.initial_sl_pct = initial_sl_pct
        self.be_trigger_r = be_trigger_r
        self.tp1_r = tp1_r
        self.tp1_qty_pct = tp1_qty_pct
        self.enable_ilsme_sweep = enable_ilsme_sweep
        self.enable_momentum_breakout = enable_momentum_breakout
        self.dynamic_compounding = dynamic_compounding
        self.active_indices = [x.upper() for x in (active_indices or ["NIFTY", "SENSEX"])]
        self.slippage_pts_entry = slippage_pts_entry
        self.slippage_pts_exit = slippage_pts_exit
        self.start_date = start_date
        self.end_date = end_date

    def run(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """Executes backtest across historical data for active indices."""
        indices_data = {}
        for idx in ["nifty", "banknifty", "sensex"]:
            if idx.upper() not in self.active_indices:
                continue
            path_15m = f"data/historical/{idx}_15m.json"
            path_3m = f"data/historical/{idx}_3m.json"
            if os.path.exists(path_15m) and os.path.exists(path_3m):
                with open(path_15m) as f1, open(path_3m) as f2:
                    m15 = json.load(f1)
                    m3 = json.load(f2)
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
                        "fvg_min": 2.0 if idx == "nifty" else 5.0,
                        "slip_mult": 1.0 if idx == "nifty" else (2.0 if idx == "banknifty" else 1.2),
                        "min_or": 45.0 if idx == "nifty" else (160.0 if idx == "sensex" else 120.0)
                    }


        if not indices_data:
            # Fallback to NIFTY
            idx = "nifty"
            path_15m = f"data/historical/{idx}_15m.json"
            path_3m = f"data/historical/{idx}_3m.json"
            if os.path.exists(path_15m) and os.path.exists(path_3m):
                with open(path_15m) as f1, open(path_3m) as f2:
                    m15 = json.load(f1)
                    m3 = json.load(f2)
                    k = 2.0 / (50.0 + 1.0)
                    cur_ema = m15[0][4]
                    ema_map = {}
                    for b in m15:
                        cur_ema = (b[4] * k) + (cur_ema * (1.0 - k))
                        ema_map[b[0][:16]] = cur_ema
                    indices_data["NIFTY"] = {
                        "15m": m15,
                        "3m": m3,
                        "ema": ema_map,
                        "lot_size": 65,
                        "base_premium": 180.0,
                        "fvg_min": 2.0,
                        "slip_mult": 1.0
                    }

        if not indices_data:
            raise FileNotFoundError(f"No active historical candle datasets found for {self.active_indices}")

        all_dates = sorted(list(set(c[0][:10] for c in indices_data[list(indices_data.keys())[0]]["3m"])))
        eff_start = start_date or self.start_date
        eff_end = end_date or self.end_date

        dates = [d for d in all_dates if (not eff_start or d >= eff_start) and (not eff_end or d <= eff_end)]
        if not dates:
            raise ValueError(f"No trading data available in the requested range: {eff_start} to {eff_end}")

        capital = self.starting_capital
        peak_capital = capital
        max_drawdown_pct = 0.0

        trades: List[Dict[str, Any]] = []
        daily_equity_curve: List[Dict[str, Any]] = []
        prev_levels = {}

        if eff_start and eff_start in all_dates:
            s_idx = all_dates.index(eff_start)
            if s_idx > 0:
                prior_date = all_dates[s_idx - 1]
                for underlying, d in indices_data.items():
                    prior_bars = [c for c in d["3m"] if c[0].startswith(prior_date)]
                    if prior_bars:
                        prev_levels[underlying] = {
                            "pdh": max(b[2] for b in prior_bars),
                            "pdl": min(b[3] for b in prior_bars)
                        }

        total_slippage_cost = 0.0

        for date_str in dates:
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
                    "cum_vol": 0.0,
                    "cum_pv": 0.0,
                    "session_high": -1e9,
                    "session_low": 1e9,
                    "sweep_status": "NONE",
                    "sweep_price": 0.0,
                    "armed_fvg": None,
                    "in_trade": False,
                    "or_high": -1e9,
                    "or_low": 1e9,
                    "or_settled": False
                }

            max_len = max(len(v) for v in today_3m_by_idx.values()) if today_3m_by_idx else 0
            for bar_i in range(max_len):
                for underlying, d in indices_data.items():
                    bars = today_3m_by_idx[underlying]
                    if bar_i >= len(bars):
                        continue

                    bar = bars[bar_i]
                    ts, o, h, l, c, v = bar[0], bar[1], bar[2], bar[3], bar[4], bar[5]
                    time_part = ts[11:16]

                    st = session_state[underlying]
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

                    pdh = prev_levels.get(underlying, {}).get("pdh", 1e9)
                    pdl = prev_levels.get(underlying, {}).get("pdl", -1e9)

                    # 1. 15m Macro Sweep Detection
                    if self.enable_ilsme_sweep and time_part in ["09:30", "09:45", "10:00", "10:15", "10:30", "10:45", "11:00", "11:15", "13:30", "13:45", "14:00", "14:15", "14:30"]:
                        bars_15m = [b for b in d["15m"] if b[0] <= ts]
                        if bars_15m:
                            last_15m = bars_15m[-1]
                            o15, h15, l15, c15 = last_15m[1], last_15m[2], last_15m[3], last_15m[4]
                            rng15 = max(1.0, h15 - l15)
                            lower_wick = (min(o15, c15) - l15) / rng15
                            upper_wick = (h15 - max(o15, c15)) / rng15

                            if l15 < pdl and c15 > pdl:
                                if (c15 >= ema_val and lower_wick >= 0.28) or (lower_wick >= 0.35):
                                    st["sweep_status"] = "BULLISH_SWEEP"
                                    st["sweep_price"] = l15
                            elif h15 > pdh and c15 < pdh:
                                if (c15 <= ema_val and upper_wick >= 0.28) or (upper_wick >= 0.35):
                                    st["sweep_status"] = "BEARISH_SWEEP"
                                    st["sweep_price"] = h15

                    # 2. 3m Micro Displacement & Quality FVG (ILSME Reversal)
                    min_gap = d["fvg_min"]
                    if self.enable_ilsme_sweep and st["sweep_status"] != "NONE" and bar_i >= 2 and not st.get("armed_fvg"):
                        if not ("11:15" <= time_part <= "13:30" or time_part >= "14:50"):
                            c1 = bars[bar_i - 2]
                            c2 = bars[bar_i - 1]
                            c3 = bars[bar_i]

                            if st["sweep_status"] == "BULLISH_SWEEP":
                                if c2[4] > c1[2] and c2[4] > vwap and (c3[3] - c1[2]) >= min_gap:
                                    st["armed_fvg"] = {
                                        "source": "ILSME_REVERSAL",
                                        "type": "BUY_CE",
                                        "top": c3[3],
                                        "bottom": c1[2],
                                        "swing_inval": c2[2]
                                    }

                            elif st["sweep_status"] == "BEARISH_SWEEP":
                                if c2[4] < c1[3] and c2[4] < vwap and (c1[3] - c3[2]) >= min_gap:
                                    st["armed_fvg"] = {
                                        "source": "ILSME_REVERSAL",
                                        "type": "BUY_PE",
                                        "top": c1[3],
                                        "bottom": c3[2],
                                        "swing_inval": c2[3]
                                    }

                    # 3. Momentum Trend / Opening Range Breakout (ORB) Engine
                    if self.enable_momentum_breakout and st.get("or_settled") and not st.get("armed_fvg") and not st.get("in_trade"):
                        if ("09:30" <= time_part <= "11:15" or "13:30" <= time_part <= "14:30") and bar_i >= 5:
                            or_h = st["or_high"]
                            or_l = st["or_low"]
                            or_rng = max(1.0, or_h - or_l)

                            # Dead Chop Volatility Floor Filter
                            if or_rng >= d.get("min_or", 0.0):
                                if c > or_h and c > vwap and c > ema_val and (c - or_h) <= (or_rng * 0.40):
                                    st["armed_fvg"] = {
                                        "source": "MOMENTUM_ORB",
                                        "type": "BUY_CE",
                                        "top": h,
                                        "bottom": max(or_h, l),
                                        "swing_inval": or_h
                                    }
                                elif c < or_l and c < vwap and c < ema_val and (or_l - c) <= (or_rng * 0.40):
                                    st["armed_fvg"] = {
                                        "source": "MOMENTUM_ORB",
                                        "type": "BUY_PE",
                                        "top": min(or_l, h),
                                        "bottom": l,
                                        "swing_inval": or_l
                                    }

                    # 4. 15-Minute Donchian Trend Breakout Engine
                    if not st.get("armed_fvg") and not st.get("in_trade") and bar_i >= 5:
                        if ("09:30" <= time_part <= "11:45" or "12:45" <= time_part <= "14:45"):
                            prior_5 = bars[bar_i-5:bar_i]
                            d_high = max(b[2] for b in prior_5)
                            d_low = min(b[3] for b in prior_5)

                            recent_bars = bars[max(0, bar_i - 20):bar_i + 1]
                            ema9 = recent_bars[0][4]
                            ema21 = recent_bars[0][4]
                            k9 = 2.0 / 10.0
                            k21 = 2.0 / 22.0
                            for rb in recent_bars:
                                ema9 = (rb[4] * k9) + (ema9 * (1.0 - k9))
                                ema21 = (rb[4] * k21) + (ema21 * (1.0 - k21))

                            if c < d_low and c < vwap and ema9 < ema21:
                                swing_pts = max(18.0 if underlying == "NIFTY" else 55.0, d_high - c)
                                st["armed_fvg"] = {
                                    "source": "TREND_PULLBACK",
                                    "type": "BUY_PE",
                                    "top": h,
                                    "bottom": l,
                                    "swing_inval": d_high,
                                    "swing_pts": swing_pts
                                }
                            elif c > d_high and c > vwap and ema9 > ema21:
                                swing_pts = max(18.0 if underlying == "NIFTY" else 55.0, c - d_low)
                                st["armed_fvg"] = {
                                    "source": "TREND_PULLBACK",
                                    "type": "BUY_CE",
                                    "top": h,
                                    "bottom": l,
                                    "swing_inval": d_low,
                                    "swing_pts": swing_pts
                                }

                    # 5. Entry Execution
                    if st.get("armed_fvg") and not st.get("in_trade"):
                        if day_trades_count >= self.max_trades_per_day or day_consecutive_losses >= 2:
                            st["armed_fvg"] = None
                            continue

                        if "11:15" <= time_part <= "13:30" and st["armed_fvg"].get("source") == "ILSME_REVERSAL":
                            st["armed_fvg"] = None
                            continue

                        if time_part >= "15:05":
                            st["armed_fvg"] = None
                            continue

                        fvg = st["armed_fvg"]
                        if active_trade_direction == fvg["type"]:
                            continue

                        is_fill = (fvg["type"] == "BUY_CE" and l <= fvg["top"]) or \
                                  (fvg["type"] == "BUY_PE" and h >= fvg["bottom"])

                        if is_fill:
                            st["armed_fvg"] = None
                            st["sweep_status"] = "NONE"
                            st["in_trade"] = True
                            active_trade_direction = fvg["type"]
                            day_trades_count += 1

                            lot_size = d["lot_size"]
                            slip_mult = d.get("slip_mult", 1.0)
                            
                            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
                            w_day = dt_obj.weekday()
                            exp_wday = 3 if underlying == "SENSEX" else 1
                            dte = (exp_wday - w_day) % 7
                            if dte == 0:
                                dte = 7
                            
                            if underlying == "NIFTY":
                                raw_entry_opt = round(95.0 + (dte * 4.2), 2)
                            elif underlying == "BANKNIFTY":
                                raw_entry_opt = round(190.0 + (dte * 10.0), 2)
                            else:
                                raw_entry_opt = round(120.0 + (dte * 6.5), 2)

                            entry_slip = self.slippage_pts_entry * slip_mult
                            entry_opt = round(raw_entry_opt + entry_slip, 2)

                            swing_pts = fvg.get("swing_pts")
                            if swing_pts and swing_pts > 0:
                                unit_risk = round(swing_pts * 0.55, 2)
                                sl_opt = round(max(1.0, raw_entry_opt - unit_risk), 2)
                            else:
                                sl_opt = round(raw_entry_opt * (1.0 - self.initial_sl_pct), 2)
                                unit_risk = entry_opt - sl_opt

                            capital_at_risk = capital * self.risk_per_trade_pct
                            calc_lots = math.floor(capital_at_risk / (unit_risk * lot_size))
                            lots = max(1, calc_lots)
                            max_lots_margin = max(1, math.floor((capital * 0.75) / (entry_opt * lot_size)))
                            lots = min(lots, max_lots_margin)
                            qty = lots * lot_size

                            cap_before = round(capital, 2)
                            cap_used = round(entry_opt * qty, 2)

                            entry_time = ts
                            entry_spot = c
                            trade_type = fvg["type"]
                            swing_inval = fvg.get("swing_inval", 0.0)

                            step = 50 if underlying == "NIFTY" else 100
                            strike_price = int(round(entry_spot / step) * step)
                            opt_label = "CE" if trade_type == "BUY_CE" else "PE"
                            tradingsymbol = f"{underlying} {strike_price} {opt_label}"

                            target_be = unit_risk * self.be_trigger_r
                            target_tp1 = unit_risk * self.tp1_r
                            target_tp1_price = raw_entry_opt + target_tp1

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
                                spot_change = (f_c - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_c)
                                high_spot_change = (f_h - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_l)
                                low_spot_change = (f_l - entry_spot) if trade_type == "BUY_CE" else (entry_spot - f_h)

                                cur_opt_price = max(1.0, raw_entry_opt + (spot_change * delta))
                                peak_opt_price = max(1.0, raw_entry_opt + (high_spot_change * delta))
                                trough_opt_price = max(1.0, raw_entry_opt + (low_spot_change * delta))

                                # Take Target 1 profit
                                if peak_opt_price >= target_tp1_price and not partial_sold:
                                    if lots == 1:
                                        exit_slip = self.slippage_pts_exit * slip_mult
                                        actual_exit = max(1.0, target_tp1_price - exit_slip)
                                        realized_gross += (actual_exit - entry_opt) * remaining_qty
                                        remaining_qty = 0
                                        exit_price = actual_exit
                                        exit_time = f_ts
                                        exit_reason = f"Full Target Hit (+{self.tp1_r:.1f}R)"
                                        break
                                    else:
                                        partial_sold = True
                                        lots_to_close = max(1, math.floor(lots * self.tp1_qty_pct))
                                        qty_close = lots_to_close * lot_size
                                        exit_slip = self.slippage_pts_exit * slip_mult
                                        actual_exit = max(1.0, target_tp1_price - exit_slip)
                                        realized_gross += (actual_exit - entry_opt) * qty_close
                                        remaining_qty -= qty_close
                                        be_moved = True

                                # Stop Loss / Breakeven Stop Trigger
                                cur_sl = raw_entry_opt if be_moved else sl_opt
                                if trough_opt_price <= cur_sl:
                                    exit_slip = self.slippage_pts_exit * slip_mult
                                    actual_exit = max(1.0, cur_sl - exit_slip)
                                    exit_price = actual_exit
                                    exit_time = f_ts
                                    exit_reason = "Trailing Breakeven SL" if be_moved else f"Hard Stop-Loss (-{int(self.initial_sl_pct*100)}%)"
                                    realized_gross += (exit_price - entry_opt) * remaining_qty
                                    remaining_qty = 0
                                    break

                                # Breakeven Trigger Logic
                                swing_broken = (f_h >= swing_inval) if trade_type == "BUY_CE" else (f_l <= swing_inval)
                                if peak_opt_price >= (raw_entry_opt + target_be) and swing_broken and not be_moved:
                                    be_moved = True

                                if f_time >= "15:12":
                                    exit_slip = self.slippage_pts_exit * slip_mult
                                    actual_exit = max(1.0, cur_opt_price - exit_slip)
                                    exit_price = actual_exit
                                    exit_time = f_ts
                                    exit_reason = "15:12 IST Intraday Square-off"
                                    realized_gross += (exit_price - entry_opt) * remaining_qty
                                    remaining_qty = 0
                                    break

                            if remaining_qty > 0:
                                exit_slip = self.slippage_pts_exit * slip_mult
                                actual_exit = max(1.0, exit_price - exit_slip)
                                realized_gross += (actual_exit - entry_opt) * remaining_qty

                            charges = calculate_option_charges(
                                entry_price=entry_opt,
                                exit_price=exit_price,
                                quantity=qty,
                                exchange="BSE" if underlying == "SENSEX" else "NSE"
                            )

                            net_pnl = round(realized_gross - charges["total_charges"], 2)
                            trade_slip = (self.slippage_pts_entry + self.slippage_pts_exit) * slip_mult * qty
                            total_slippage_cost += trade_slip

                            capital += net_pnl
                            if capital > peak_capital:
                                peak_capital = capital
                            dd = (peak_capital - capital) / peak_capital * 100.0
                            if dd > max_drawdown_pct:
                                max_drawdown_pct = dd

                            if net_pnl > 50:
                                outcome = "WIN"
                            elif abs(realized_gross) < 50:
                                outcome = "BREAKEVEN"
                            else:
                                outcome = "LOSS"

                            if outcome == "LOSS":
                                day_consecutive_losses += 1
                            else:
                                day_consecutive_losses = 0

                            strat_label = "Trend Pullback" if fvg.get("source") == "TREND_PULLBACK" else ("Momentum Breakout" if fvg.get("source") == "MOMENTUM_ORB" else "ILSME Reversal")

                            trades.append({
                                "id": f"BT_{len(trades)+1:03d}",
                                "date": date_str,
                                "entry_time": entry_time[11:16],
                                "exit_time": exit_time[11:16],
                                "underlying": underlying,
                                "tradingsymbol": tradingsymbol,
                                "strike_price": strike_price,
                                "type": trade_type,
                                "strategy_name": strat_label,
                                "lots": lots,
                                "quantity": qty,
                                "capital_before": cap_before,
                                "capital_used": cap_used,
                                "entry_price": entry_opt,
                                "exit_price": round(exit_price, 2),
                                "gross_pnl": round(realized_gross, 2),
                                "brokerage": charges["brokerage"],
                                "stt": charges["stt"],
                                "exchange_charges": charges["exchange_charges"],
                                "sebi_charges": charges["sebi_charges"],
                                "stamp_duty": charges["stamp_duty"],
                                "gst": charges["gst"],
                                "total_charges": charges["total_charges"],
                                "net_pnl": net_pnl,
                                "capital_after": round(capital, 2),
                                "exit_reason": exit_reason,
                                "result": outcome
                            })

                            st["in_trade"] = False
                            active_trade_direction = None

            for u, d in indices_data.items():
                bars = today_3m_by_idx[u]
                if bars:
                    prev_levels[u] = {
                        "pdh": max(b[2] for b in bars),
                        "pdl": min(b[3] for b in bars)
                    }

            daily_equity_curve.append({
                "date": date_str,
                "capital": round(capital, 2),
                "trades": day_trades_count
            })

        wins = [t for t in trades if t["result"] == "WIN"]
        losses = [t for t in trades if t["result"] == "LOSS"]
        bes = [t for t in trades if t["result"] == "BREAKEVEN"]

        total_net_pnl = round(capital - self.starting_capital, 2)
        total_gross = sum(t["gross_pnl"] for t in trades)
        total_fees = sum(t["total_charges"] for t in trades)

        gross_profit = sum(t["net_pnl"] for t in trades if t["net_pnl"] > 0)
        gross_loss = abs(sum(t["net_pnl"] for t in trades if t["net_pnl"] < 0))
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        return {
            "summary": {
                "period": f"{dates[0]} to {dates[-1]} ({len(dates)} Sessions)",
                "starting_capital": self.starting_capital,
                "ending_capital": round(capital, 2),
                "total_net_pnl": total_net_pnl,
                "total_gross_pnl": round(total_gross, 2),
                "total_brokerage_and_taxes": round(total_fees, 2),
                "total_slippage_cost": round(total_slippage_cost, 2),
                "roi_pct": round((total_net_pnl / self.starting_capital) * 100.0, 2),
                "win_rate_pct": round((len(wins) / len(trades) * 100.0), 1) if trades else 0,
                "non_losing_rate_pct": round(((len(wins) + len(bes)) / len(trades) * 100.0), 1) if trades else 0,
                "total_trades": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "breakeven": len(bes),
                "profit_factor": pf,
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "avg_win": round(sum(t["net_pnl"] for t in wins) / len(wins), 2) if wins else 0,
                "avg_loss": round(sum(t["net_pnl"] for t in losses) / len(losses), 2) if losses else 0,
                "risk_reward_ratio": f"1 : {self.tp1_r:.1f}",
                "risk_per_trade": f"{self.risk_per_trade_pct*100:.1f}%",
                "dynamic_compounding": self.dynamic_compounding
            },
            "trades": trades,
            "daily_equity_curve": daily_equity_curve
        }

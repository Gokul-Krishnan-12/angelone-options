import math
from datetime import datetime, time
from typing import Dict, List, Optional, Any
from smartapi_trader.core.events import BarEvent, TickEvent, SignalEvent, EventType
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.data.instrument_loader import InstrumentLoader
from smartapi_trader.strategy.base_strategy import BaseStrategy
from smartapi_trader.utils.logger import logger
from smartapi_trader.utils.tz import ist_time, now_ist

class SniperILSMEStrategy(BaseStrategy):
    """
    Institutional Liquidity Sweep & Momentum Expansion (ILSME) Sniper Framework.
    
    1. 15m Macro Timeframe: Detects structural liquidity sweeps at PDH/PDL or Session Extremes
       confirmed by prominent wick rejections (wick >= 30% of candle range).
    2. 3m Micro Timeframe: Confirms Market Structure Shift (MSS) through VWAP and Fair Value Gap (FVG).
    3. Strike Selection: Dynamically targets ATM or immediate ITM contracts (Delta ~0.50-0.55).
    4. Regime Filter: Ignores entries during midday chop (11:15 - 13:30 IST).
    5. Expiry Protection: Rolls 0-DTE contracts to next expiry prior to 13:00 IST on expiry day.
    """
    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        instrument_loader: InstrumentLoader,
        config: Dict[str, Any],
        symbols_config: Dict[str, Any],
        auth_manager: Optional[Any] = None
    ):
        super().__init__("ILSME_Sniper", event_bus)
        self.state_mgr = state_manager
        self.loader = instrument_loader
        self.auth_mgr = auth_manager
        self.cfg = config.get("strategy", {})
        self.risk_cfg = config.get("risk", {})
        self.symbols_cfg = symbols_config.get("indices", {})
        
        # State tracking per underlying: "NIFTY", "BANKNIFTY", "SENSEX"
        self.active_indices = self.cfg.get("active_indices", ["NIFTY", "BANKNIFTY", "SENSEX"])
        self.trade_cooldown_mins = float(self.cfg.get("trade_cooldown_minutes", 15.0))
        self.max_consecutive_trend_bars = int(self.cfg.get("max_consecutive_trend_bars", 4))
        self.max_vwap_atr_mult = float(self.cfg.get("max_vwap_atr_multiplier", 1.6))
        self.donchian_lookback_bars = int(self.cfg.get("donchian_lookback_bars", 15))
        self.donchian_require_or_break = bool(self.cfg.get("donchian_require_or_break", True))
        self.consecutive_loss_limit = int(self.risk_cfg.get("consecutive_loss_limit", 2))
        self.state: Dict[str, Dict[str, Any]] = {}
        for idx in self.active_indices:
            self._init_index_state(idx)

        # Buffer of bars: token -> timeframe -> List[BarEvent]
        self.bars: Dict[str, Dict[str, List[BarEvent]]] = {}
        self.option_volume_history: Dict[str, List[int]] = {}

        # Wire position updates to keep in_trade state in sync
        self.bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)
        self.bus.subscribe(EventType.RISK_ALERT, self._on_risk_alert)

    async def _on_position_update(self, event: Any):
        """Syncs in_trade state when positions open or close."""
        underlying = getattr(event, "underlying", "")
        if underlying in self.state:
            is_open = getattr(event, "is_open", False)
            was_open = self.state[underlying].get("in_trade", False)
            if was_open and not is_open:
                self.state[underlying]["last_exit_time"] = now_ist()
                logger.info(f"[STRATEGY] Position closed for {underlying}. Cooldown active for {self.trade_cooldown_mins} minutes.")
            self.state[underlying]["in_trade"] = is_open
            if not is_open:
                self.state_mgr.set_strategy_status("Scanning for Liquidity Sweep & Momentum Breakouts")

    async def _on_risk_alert(self, event: Any):
        """Immediately clears in_trade lock if an order was rejected by Risk Manager."""
        action = getattr(event, "action_taken", "")
        if action == "REJECT":
            for underlying, st in self.state.items():
                if not any(getattr(p, "underlying", "") == underlying and getattr(p, "is_open", False) for p in self.state_mgr.positions.values()):
                    st["in_trade"] = False
                    st["last_signal_time"] = None
            self.state_mgr.set_strategy_status("Scanning for Liquidity Sweep & Momentum Breakouts")

    def _is_in_trade(self, underlying: str) -> bool:
        """Determines if there is an active open position for this underlying."""
        if any(getattr(p, "underlying", "") == underlying and getattr(p, "is_open", False) for p in self.state_mgr.positions.values()):
            return True
        st = self.state.get(underlying, {})
        last_sig_t = st.get("last_signal_time")
        if last_sig_t:
            cur_sec = ist_time().hour * 3600 + ist_time().minute * 60 + ist_time().second
            sig_sec = last_sig_t.hour * 3600 + last_sig_t.minute * 60 + last_sig_t.second
            elapsed_sec = cur_sec - sig_sec
            if 0 <= elapsed_sec < 30 and st.get("in_trade"):
                return True
            elif elapsed_sec >= 30 and not any(getattr(p, "underlying", "") == underlying and getattr(p, "is_open", False) for p in self.state_mgr.positions.values()):
                st["in_trade"] = False
        return bool(st.get("in_trade", False))

    def _init_index_state(self, underlying: str):
        # Dynamically load true Previous Day High (PDH) and Low (PDL)
        pdh, pdl, ref_spot = self._fetch_dynamic_pdh_pdl(underlying)
        
        # Check if booting after 09:30 IST today; if so, attempt to backfill genuine 09:15-09:30 Opening Range
        or_h, or_l, or_settled = self._backfill_opening_range(underlying, ref_spot)

        # Detect if breakout already occurred before boot or if cutoff already passed
        or_already_broken = False
        if or_settled and ref_spot > 0:
            orb_cutoff_str = str(self.risk_cfg.get("orb_cutoff_time", self.cfg.get("orb_cutoff_time", "11:00")))
            try:
                ch, cm = map(int, orb_cutoff_str.split(":"))
                cutoff_t = time(ch, cm)
            except Exception:
                cutoff_t = time(11, 0)
            if ref_spot > or_h or ref_spot < or_l or ist_time() >= cutoff_t:
                or_already_broken = True

        self.state[underlying] = {
            "pdh": pdh,
            "pdl": pdl,
            "session_high": max(pdh, or_h) if or_h > 0 else pdh,
            "session_low": min(pdl, or_l) if or_l < 999999.0 else pdl,
            "vwap": ref_spot,
            "last_spot": ref_spot,
            "or_high": or_h,
            "or_low": or_l,
            "or_settled": or_settled,
            "or_triggered_today": or_already_broken,
            "sweep_status": "NONE",       # "NONE", "BULLISH_SWEEP", "BEARISH_SWEEP"
            "sweep_price": 0.0,
            "sweep_time": None,
            "armed_fvg": None,           # Holds pending FVG or Breakout zone dict
            "last_exit_time": None,      # Post-trade cooldown timestamp
            "in_trade": False
        }
        logger.info(
            f"[STRATEGY] Initialized {underlying} Reference Levels -> PDH: {pdh:.2f} | PDL: {pdl:.2f} | "
            f"OR High: {or_h:.2f} | OR Low: {or_l:.2f} (Settled: {or_settled}, PreBroken/Triggered: {or_already_broken})"
        )

    def _backfill_opening_range(self, underlying: str, ref_spot: float) -> tuple[float, float, bool]:
        """
        Recovers the genuine 09:15-09:30 Opening Range high/low if the engine is booted or restarted after 09:30 IST.
        """
        now_t = ist_time()
        if now_t < time(9, 30):
            return -1.0, 999999.0, False

        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Try SmartAPI getCandleData for today's 09:15 15m bar
        import time as _pytime
        smart_api = getattr(self.auth_mgr, "smart_api", None)
        if self.auth_mgr and not self.auth_mgr.is_simulated and smart_api:
            sym_info = self.symbols_cfg.get(underlying, {})
            tok = sym_info.get("spot_token")
            exch = sym_info.get("exchange", "NSE")
            if tok:
                for attempt in range(3):
                    try:
                        _pytime.sleep(0.4 * (attempt + 1))  # Prevent Angel One SmartAPI 3 req/sec rate limit
                        res = smart_api.getCandleData({
                            "exchange": exch,
                            "symboltoken": str(tok),
                            "interval": "FIFTEEN_MINUTE",
                            "fromdate": f"{today_str} 09:15",
                            "todate": f"{today_str} 09:30"
                        })
                        if isinstance(res, dict) and res.get("status"):
                            data = res.get("data") or []
                            today_bars = [b for b in data if b[0].startswith(today_str)]
                            if today_bars:
                                or_bar = today_bars[0]
                                or_high = float(or_bar[2])
                                or_low = float(or_bar[3])
                                logger.info(f"[STRATEGY] 🔄 Successfully backfilled {underlying} 09:15-09:30 Opening Range: High ₹{or_high:.2f}, Low ₹{or_low:.2f}")
                                return or_high, or_low, True
                    except Exception as e:
                        if attempt == 2:
                            logger.warning(f"[STRATEGY] Could not fetch live 15m candle for {underlying} OR backfill: {e}")

        # 2. Try local historical 15m store if present
        import os
        import json
        path = f"data/historical/{underlying.lower()}_15m.json"
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    bars = json.load(f)
                today_bars = [b for b in bars if b[0].startswith(today_str)]
                if today_bars:
                    or_high = float(today_bars[0][2])
                    or_low = float(today_bars[0][3])
                    logger.info(f"[STRATEGY] 🔄 Backfilled {underlying} Opening Range from local dataset: High ₹{or_high:.2f}, Low ₹{or_low:.2f}")
                    return or_high, or_low, True
            except Exception:
                pass

        # 3. Fallback: If after 09:30 and no historical candle, initialize from current spot levels
        if ref_spot > 0:
            logger.info(f"[STRATEGY] ℹ️ Using current spot reference (₹{ref_spot:.2f}) to seed Opening Range for {underlying}")
            return ref_spot, ref_spot, False

        return -1.0, 999999.0, False

    def _fetch_dynamic_pdh_pdl(self, underlying: str) -> tuple[float, float, float]:
        """Dynamically resolves true Previous Day High / Low from historical datasets or Angel One API."""
        import os
        import json
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        idx_key = underlying.lower()
        
        # 1. Try local historical 3m / 15m candle store (only if fresh within 4 calendar days)
        for tf in ["3m", "15m"]:
            path = f"data/historical/{idx_key}_{tf}.json"
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        bars = json.load(f)
                    dates = sorted(list(set(c[0][:10] for c in bars if c[0][:10] < today_str)))
                    if dates:
                        prev_date = dates[-1]
                        prev_dt = datetime.strptime(prev_date, "%Y-%m-%d").date()
                        days_diff = (datetime.now().date() - prev_dt).days
                        if days_diff <= 4:
                            prev_bars = [c for c in bars if c[0].startswith(prev_date)]
                            if prev_bars:
                                pdh = max(b[2] for b in prev_bars)
                                pdl = min(b[3] for b in prev_bars)
                                close = prev_bars[-1][4]
                                logger.info(f"[STRATEGY] Loaded fresh PDH/PDL for {underlying} from {path} (Date: {prev_date}) -> PDH: {pdh:.2f}, PDL: {pdl:.2f}")
                                return pdh, pdl, close
                        else:
                            logger.warning(f"[STRATEGY] Local historical data in {path} is stale ({prev_date}, {days_diff} days old). Skipping to live SmartAPI.")
                except Exception as e:
                    logger.warning(f"[STRATEGY] Error reading {path} for PDH/PDL: {e}")

        # 2. Try Angel One SmartAPI live historical fetch if authenticated
        smart_api = getattr(self.auth_mgr, "smart_api", None)
        if self.auth_mgr and not self.auth_mgr.is_simulated and smart_api:
            try:
                import time as _pytime
                _pytime.sleep(0.4)  # Prevent Angel One SmartAPI 3 req/sec rate limit violation
                sym_info = self.symbols_cfg.get(underlying, {})
                tok = sym_info.get("spot_token")
                exch = sym_info.get("exchange", "NSE")
                if tok:
                    from datetime import timedelta
                    from_d = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
                    to_d = datetime.now().strftime("%Y-%m-%d")
                    res = smart_api.getCandleData({
                        "exchange": exch,
                        "symboltoken": str(tok),
                        "interval": "ONE_DAY",
                        "fromdate": f"{from_d} 09:15",
                        "todate": f"{to_d} 15:30"
                    })
                    data = res.get("data") or []
                    valid = [d for d in data if d[0][:10] < today_str]
                    if valid:
                        last_day = valid[-1]
                        pdh, pdl, close = float(last_day[2]), float(last_day[3]), float(last_day[4])
                        logger.info(f"[STRATEGY] Loaded live broker PDH/PDL for {underlying} (Date: {last_day[0][:10]}) -> PDH: {pdh:.2f}, PDL: {pdl:.2f}, Prev Close: {close:.2f}")
                        return pdh, pdl, close
            except Exception as api_err:
                logger.warning(f"[STRATEGY] SmartAPI daily candle fetch for {underlying} failed: {api_err}")

        # 3. Fallback to reasonable index defaults
        default_levels = {
            "NIFTY": {"pdh": 22800.0, "pdl": 22500.0, "spot": 22700.0},
            "BANKNIFTY": {"pdh": 54500.0, "pdl": 53800.0, "spot": 54200.0},
            "SENSEX": {"pdh": 72800.0, "pdl": 72000.0, "spot": 72500.0}
        }
        ref = default_levels.get(underlying, {"pdh": 22800.0, "pdl": 22500.0, "spot": 22700.0})
        return ref["pdh"], ref["pdl"], ref["spot"]

    def reset_daily_state(self):
        for idx in self.active_indices:
            self._init_index_state(idx)
        self.state_mgr.set_strategy_status("Scanning for Liquidity Sweep & Momentum Breakouts")
        logger.info("[STRATEGY] Daily state reset completed with fresh reference levels.")

    def _is_midday_chop(self) -> bool:
        """Checks if current time falls in midday consolidation based on risk settings (e.g. 11:45 - 13:00 or 11:15 - 13:30)."""
        now = ist_time()
        start_str = str(self.risk_cfg.get("midday_chop_filter_start", "11:15"))
        end_str = str(self.risk_cfg.get("midday_chop_filter_end", "13:30"))
        try:
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start = time(sh, sm)
            end = time(eh, em)
        except Exception:
            start = time(11, 15)
            end = time(13, 30)
        return start <= now <= end

    def _is_market_hours(self) -> bool:
        """Trading entry window: 09:15 to last_entry_time (default 14:30 IST). No new setups or signals after cutoff."""
        now = ist_time()
        start = time(9, 15)
        last_entry_str = str(self.risk_cfg.get("last_entry_time", "14:30"))
        try:
            eh, em = map(int, last_entry_str.split(":"))
            end = time(eh, em)
        except Exception:
            end = time(14, 30)
        return start <= now <= end

    async def on_tick(self, event: TickEvent):
        # Check if tick belongs to underlying index spot
        for sym_name, sym_info in self.symbols_cfg.items():
            if str(event.token) == str(sym_info.get("spot_token")):
                # Guard: Strict active indices enforcement - ignore ticks for disabled indices
                if sym_name not in self.active_indices:
                    return

                if sym_name not in self.state:
                    self._init_index_state(sym_name)
                st = self.state[sym_name]
                st["last_spot"] = event.ltp
                cur_high = max(event.high if event.high > 0 else event.ltp, event.ltp)
                cur_low = min(event.low if event.low > 0 else event.ltp, event.ltp)
                st["session_high"] = max(st["session_high"], cur_high)
                st["session_low"] = min(st["session_low"], cur_low) if st["session_low"] > 0 else cur_low
                
                # Opening Range Tracker (09:15 to 09:30)
                now_t = ist_time()
                if time(9, 15) <= now_t <= time(9, 30):
                    st["or_high"] = max(st["or_high"], cur_high)
                    st["or_low"] = min(st["or_low"], cur_low) if st["or_low"] > 0 else cur_low
                elif now_t > time(9, 30) and not st["or_settled"]:
                    st["or_settled"] = True
                    logger.info(f"[STRATEGY] {sym_name} 15m Opening Range SETTLED -> High: {st['or_high']:.2f} | Low: {st['or_low']:.2f}")

                self.state_mgr.update_spot_telemetry(
                    sym_name, event.ltp, st["vwap"], st["pdh"], st["pdl"], st["session_high"], st["session_low"]
                )
                
                # Check for limit retracement fill if FVG/Breakout is armed
                if st.get("armed_fvg"):
                    await self._evaluate_fvg_retest(sym_name, event.ltp)

    async def on_bar(self, event: BarEvent):
        """Processes closed 15m and 3m bars."""
        token = event.token
        tf = event.timeframe
        
        if token not in self.bars:
            self.bars[token] = {"3m": [], "15m": []}

        # Identify which underlying this token belongs to
        target_underlying = None
        for sym_name, sym_info in self.symbols_cfg.items():
            if str(token) == str(sym_info.get("spot_token")):
                target_underlying = sym_name
                break

        if not target_underlying or target_underlying not in self.active_indices:
            return

        if event.is_closed:
            # Defensive guard: Discard pre-market bars that started before 09:15 IST
            if getattr(event, "bar_start_time", None):
                try:
                    b_iso = event.bar_start_time.replace("Z", "+00:00")
                    b_dt = datetime.fromisoformat(b_iso)
                    if b_dt.time() < time(9, 15):
                        return
                except Exception:
                    pass

            self.bars[token][tf].append(event)
            if len(self.bars[token][tf]) > 50:
                self.bars[token][tf].pop(0)

            # Update VWAP from bar
            self.state[target_underlying]["vwap"] = event.vwap

            if tf == "15m":
                await self._evaluate_15m_macro_sweep(target_underlying, event)
            elif tf == "3m":
                await self._evaluate_3m_micro_displacement(target_underlying, event)

    async def _evaluate_15m_macro_sweep(self, underlying: str, bar: BarEvent):
        """
        15-minute Macro Timeframe Logic:
        Evaluates structural sweeps of PDH / PDL or Session Extremes with wick rejection.
        """
        # Strictly discard any 15m bar closing before 09:30 IST (such as 09:00-09:15 premarket auction bars)
        if ist_time() < time(9, 30) or not self._is_market_hours() or self._is_midday_chop():
            return

        if not self.cfg.get("enable_ilsme_sweep", True):
            return

        st = self.state[underlying]
        rng = max(0.01, bar.high - bar.low)

        # Outlier spike filter: reject candles whose range exceeds max_spike_candle_pct of spot/open
        max_spike_pct = float(self.cfg.get("max_spike_candle_pct", 1.2))
        ref_price = bar.open if bar.open > 0 else (st.get("last_spot") or 1.0)
        spike_pct = (rng / ref_price) * 100.0
        if spike_pct > max_spike_pct:
            logger.warning(
                f"[STRATEGY] ⚠️ Rejected anomalous spike candle for {underlying}: "
                f"Range={rng:.2f} pts ({spike_pct:.2f}% > {max_spike_pct:.1f}% limit). Ignored for sweep evaluation."
            )
            return

        lower_wick = (min(bar.open, bar.close) - bar.low) / rng
        upper_wick = (bar.high - max(bar.open, bar.close)) / rng

        # Bullish Sweep: Pierces PDL / Session Low but closes above with lower wick >= 30%
        if bar.low < st["pdl"] and bar.close > st["pdl"] and lower_wick >= self.cfg.get("min_wick_ratio", 0.30):
            st["sweep_status"] = "BULLISH_SWEEP"
            st["sweep_price"] = bar.low
            st["sweep_time"] = now_ist()
            status_msg = f"Sweep Detected ({underlying} Bullish): Waiting for 3m Displacement"
            self.state_mgr.set_strategy_status(status_msg)
            logger.info(f"[STRATEGY] {underlying} 15m BULLISH LIQUIDITY SWEEP at {bar.low:.2f} (Wick: {lower_wick:.1%})")

        # Bearish Sweep: Pierces PDH / Session High but closes below with upper wick >= 30%
        elif bar.high > st["pdh"] and bar.close < st["pdh"] and upper_wick >= self.cfg.get("min_wick_ratio", 0.30):
            st["sweep_status"] = "BEARISH_SWEEP"
            st["sweep_price"] = bar.high
            st["sweep_time"] = now_ist()
            status_msg = f"Sweep Detected ({underlying} Bearish): Waiting for 3m Displacement"
            self.state_mgr.set_strategy_status(status_msg)
            logger.info(f"[STRATEGY] {underlying} 15m BEARISH LIQUIDITY SWEEP at {bar.high:.2f} (Wick: {upper_wick:.1%})")

    def _calculate_atr(self, token: str, period: int = 14) -> float:
        """Calculates rolling ATR from closed 3m bars."""
        closed = self.bars.get(token, {}).get("3m", [])
        if len(closed) < 2:
            return 0.0
        trs = []
        for i in range(1, len(closed)):
            h = closed[i].high
            l = closed[i].low
            prev_c = closed[i - 1].close
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
        sample = trs[-period:]
        return sum(sample) / len(sample) if sample else 0.0

    def _check_macro_liquidity_clearance(
        self,
        underlying: str,
        direction: str,
        bar_close: float,
        bar_high: float,
        bar_low: float,
        min_penetration: float,
        or_bound: float
    ) -> tuple[bool, str]:
        """
        Universal Macro Liquidity Clearance Guard:
        Ensures an intraday breakout does not drive directly into an un-cleared
        macro liquidity wall (Previous Day High or Low) where institutional reversals cluster.
        """
        st = self.state.get(underlying, {})
        pdh = float(st.get("pdh", 0.0))
        pdl = float(st.get("pdl", 0.0))
        macro_clearance = float(self.cfg.get(
            f"orb_macro_clearance_{underlying.lower()}",
            30.0 if underlying == "NIFTY" else (100.0 if underlying == "SENSEX" else 80.0)
        ))

        if direction == "BULLISH":
            if pdh > 0:
                # Active sweep guard: candle tested PDH but failed to close above with buffer
                if bar_high >= pdh and bar_close < (pdh + min_penetration):
                    return False, f"Bar tested PDH (₹{pdh:.2f}) but failed to clear buffer (Close: ₹{bar_close:.2f}). Liquidity sweep risk."
                # Restricted clearance: OR High is below PDH and distance to PDH is choked
                if or_bound > 0 and or_bound < pdh and (pdh - or_bound) < macro_clearance:
                    if bar_close < (pdh + min_penetration):
                        return False, f"Room between OR High (₹{or_bound:.2f}) and PDH (₹{pdh:.2f}) is choked ({pdh - or_bound:.1f} pts < {macro_clearance:.1f} pts). Awaiting breakout above PDH."
        elif direction == "BEARISH":
            if pdl > 0:
                # Active sweep guard: candle tested PDL but failed to close below with buffer
                if bar_low <= pdl and bar_close > (pdl - min_penetration):
                    return False, f"Bar tested PDL (₹{pdl:.2f}) but failed to clear buffer (Close: ₹{bar_close:.2f}). Liquidity sweep risk."
                # Restricted clearance: OR Low is above PDL and distance to PDL is choked
                if or_bound < 999999.0 and or_bound > pdl and (or_bound - pdl) < macro_clearance:
                    if bar_close > (pdl - min_penetration):
                        return False, f"Room between OR Low (₹{or_bound:.2f}) and PDL (₹{pdl:.2f}) is choked ({or_bound - pdl:.1f} pts < {macro_clearance:.1f} pts). Awaiting breakdown below PDL."

        return True, "OK"

    async def _evaluate_3m_micro_displacement(self, underlying: str, bar: BarEvent):
        """
        3-minute Micro Timeframe Logic:
        1. ILSME Reversal Model: Market Structure Shift (MSS) through VWAP and Fair Value Gap (FVG).
        2. Momentum Trend Model: Opening Range Breakout (ORB) with VWAP and EMA confirmation.
        """
        if not self._is_market_hours():
            return

        st = self.state[underlying]

        # Check 3m bar for anomalous spike
        max_spike_pct = float(self.cfg.get("max_spike_candle_pct", 1.2))
        ref_price = bar.open if bar.open > 0 else (st.get("last_spot") or 1.0)
        if ((bar.high - bar.low) / ref_price) * 100.0 > max_spike_pct:
            return

        # Sweep TTL (Time-To-Live) Expiry Check: Invalidate stale sweeps if elapsed time exceeds sweep_ttl_minutes
        if st.get("sweep_status") != "NONE" and st.get("sweep_time"):
            elapsed_minutes = (now_ist() - st["sweep_time"]).total_seconds() / 60.0
            sweep_ttl = float(self.cfg.get("sweep_ttl_minutes", 20.0))
            if elapsed_minutes > sweep_ttl:
                logger.info(
                    f"[STRATEGY] Expiring stale {st['sweep_status']} for {underlying}: "
                    f"{elapsed_minutes:.1f}m elapsed (TTL: {sweep_ttl:.1f}m)"
                )
                st["sweep_status"] = "NONE"
                st["sweep_time"] = None
                st["sweep_price"] = 0.0
                st["armed_fvg"] = None

        vwap = bar.vwap or st["vwap"]
        token = bar.token
        closed_3m = self.bars.get(token, {}).get("3m", [])
        if len(closed_3m) < 3:
            return

        c1 = closed_3m[-3]
        c2 = closed_3m[-2] # Displacement bar
        c3 = closed_3m[-1]

        # =====================================================================
        # MODEL 1: ILSME REVERSAL SWEEP ENGINE
        # =====================================================================
        if self.cfg.get("enable_ilsme_sweep", True) and st["sweep_status"] != "NONE" and not self._is_midday_chop():
            # 1. Bullish Setup (Call buying)
            if st["sweep_status"] == "BULLISH_SWEEP":
                has_displacement = c2.close > c1.high and c2.close > vwap
                has_fvg = (c3.low - c1.high) >= self.cfg.get("fvg_min_points", 2.0)

                if has_displacement and has_fvg:
                    fvg_top = c3.low
                    fvg_bottom = c1.high
                    st["armed_fvg"] = {
                        "source": "ILSME_REVERSAL",
                        "type": "BUY_CE",
                        "top": fvg_top,
                        "bottom": fvg_bottom,
                        "displacement_low": c2.low,
                        "displacement_high": c2.high,
                        "underlying": underlying,
                        "armed_time": now_ist()
                    }
                    status_msg = f"FVG Formed ({underlying} Call): Armed for retracement retest [{fvg_bottom:.1f}-{fvg_top:.1f}]"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    return

            # 2. Bearish Setup (Put buying)
            elif st["sweep_status"] == "BEARISH_SWEEP":
                has_displacement = c2.close < c1.low and c2.close < vwap
                has_fvg = (c1.low - c3.high) >= self.cfg.get("fvg_min_points", 2.0)

                if has_displacement and has_fvg:
                    fvg_top = c1.low
                    fvg_bottom = c3.high
                    st["armed_fvg"] = {
                        "source": "ILSME_REVERSAL",
                        "type": "BUY_PE",
                        "top": fvg_top,
                        "bottom": fvg_bottom,
                        "displacement_high": c2.high,
                        "displacement_low": c2.low,
                        "underlying": underlying,
                        "armed_time": now_ist()
                    }
                    status_msg = f"FVG Formed ({underlying} Put): Armed for retracement retest [{fvg_bottom:.1f}-{fvg_top:.1f}]"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    return

        # Trade Cooldown Guard: Prevent immediate re-entry churn on the same underlying
        last_exit = st.get("last_exit_time")
        in_cooldown = False
        if last_exit:
            elapsed_cooldown = (now_ist() - last_exit).total_seconds() / 60.0
            if elapsed_cooldown < self.trade_cooldown_mins:
                in_cooldown = True

        # =====================================================================
        # MODEL 2: MOMENTUM TREND / OPENING RANGE BREAKOUT (ORB) ENGINE
        # =====================================================================
        is_pos_open = any(p.underlying == underlying and p.is_open for p in self.state_mgr.positions.values())
        if (
            self.cfg.get("enable_momentum_breakout", True)
            and st.get("or_settled")
            and not st.get("or_triggered_today")
            and not st.get("armed_fvg")
            and not self._is_in_trade(underlying)
            and not in_cooldown
            and not is_pos_open
        ):
            now_t = ist_time()
            orb_cutoff_str = str(self.risk_cfg.get("orb_cutoff_time", self.cfg.get("orb_cutoff_time", "11:00")))
            try:
                ch, cm = map(int, orb_cutoff_str.split(":"))
                orb_cutoff = time(ch, cm)
            except Exception:
                orb_cutoff = time(11, 0)

            if (time(9, 30) <= now_t <= orb_cutoff) and not self._is_midday_chop():
                or_h = st["or_high"]
                or_l = st["or_low"]
                or_rng = max(1.0, or_h - or_l)

                # Minimum Volatility Expansion Filter: Block breakouts on compressed/dead chop days
                min_or_thresh = 45.0 if underlying == "NIFTY" else (160.0 if underlying == "SENSEX" else (120.0 if underlying == "BANKNIFTY" else 40.0))
                min_or_cfg = self.cfg.get(f"min_orb_range_{underlying.lower()}", min_or_thresh)
                if or_rng < min_or_cfg:
                    # Opening range is too narrow / low-volatility chop regime
                    return

                # Institutional Penetration Buffer: Volatility-Adaptive (min_penetration or 0.25x ATR)
                min_pen_cfg = float(self.cfg.get(f"orb_min_penetration_{underlying.lower()}", 6.0 if underlying == "NIFTY" else (25.0 if underlying == "SENSEX" else 20.0)))
                use_adaptive_pen = bool(self.cfg.get("orb_use_adaptive_atr_buffer", True))
                atr_cur = self._calculate_atr(token, period=14)
                min_penetration = max(min_pen_cfg, (atr_cur * 0.25) if (use_adaptive_pen and atr_cur > 1.0) else min_pen_cfg)

                # Volume Expansion Filter: Require breakout bar volume >= volume_expansion_multiplier * 20-bar SMA
                require_vol = bool(self.cfg.get("require_volume_expansion", True))
                vol_mult = float(self.cfg.get("volume_expansion_multiplier", 1.25))
                vol_bars = [b.volume for b in closed_3m[-20:-1] if hasattr(b, 'volume') and b.volume > 0]
                avg_vol = (sum(vol_bars) / len(vol_bars)) if vol_bars else 0

                # Candle Anatomy & Body Quality Ratio: Ensure directional impulse body (>= 50% of range)
                candle_rng = max(0.01, bar.high - bar.low)
                candle_body = abs(bar.close - bar.open)
                body_ratio = candle_body / candle_rng
                min_body_ratio = float(self.cfg.get("orb_min_body_ratio", 0.50))
                upper_wick = (bar.high - max(bar.open, bar.close)) / candle_rng
                lower_wick = (min(bar.open, bar.close) - bar.low) / candle_rng

                # True Crossover Requirement: Check previous 3m closed candle
                prev_closed = c2.close

                # Bullish Breakout: Previous bar was <= OR High, current bar closes > OR High + Buffer + Close > VWAP
                if (
                    prev_closed <= or_h
                    and bar.close >= (or_h + min_penetration)
                    and bar.close > vwap
                    and bar.close > bar.open  # Bullish candle body
                    and upper_wick <= 0.35    # Rejection wick <= 35%
                    and (bar.close - or_h) <= (or_rng * 0.40)
                ):
                    clear_bull, reason_bull = self._check_macro_liquidity_clearance(underlying, "BULLISH", bar.close, bar.high, bar.low, min_penetration, or_h)
                    if not clear_bull:
                        logger.info(f"[STRATEGY] Filtered out Bullish ORB on {underlying}: {reason_bull}")
                        return
                    if body_ratio < min_body_ratio:
                        logger.info(f"[STRATEGY] Filtered weak-bodied Bullish ORB on {underlying}: Body ratio {body_ratio:.1%} < {min_body_ratio:.0%}. Lacks institutional impulse.")
                        return
                    if require_vol and avg_vol > 0 and bar.volume < (avg_vol * vol_mult):
                        logger.info(f"[STRATEGY] Filtered low-volume Bullish ORB on {underlying}: Vol {bar.volume} < {avg_vol * vol_mult:.0f}. Institutional participation missing.")
                        return

                    st["or_triggered_today"] = True
                    st["armed_fvg"] = {
                        "source": "MOMENTUM_ORB",
                        "type": "BUY_CE",
                        "top": bar.high,
                        "bottom": max(or_h, bar.low),
                        "displacement_low": or_h,
                        "displacement_high": bar.high,
                        "breakout_boundary": or_h,
                        "underlying": underlying
                    }
                    status_msg = f"🚀 Momentum ORB Formed ({underlying} Call): Fresh Breakout above OR High ₹{or_h:.2f} (+{bar.close - or_h:.1f} pts, Vol: {bar.volume})"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    # Direct execution on momentum bar
                    await self._generate_sniper_signal(underlying, "BUY_CE", bar.close, st["armed_fvg"])
                    st["armed_fvg"] = None

                # Bearish Breakdown: Previous bar was >= OR Low, current bar closes < OR Low - Buffer + Close < VWAP
                elif (
                    prev_closed >= or_l
                    and bar.close <= (or_l - min_penetration)
                    and bar.close < vwap
                    and bar.close < bar.open  # Bearish candle body
                    and lower_wick <= 0.35    # Rejection wick <= 35%
                    and (or_l - bar.close) <= (or_rng * 0.40)
                ):
                    clear_bear, reason_bear = self._check_macro_liquidity_clearance(underlying, "BEARISH", bar.close, bar.high, bar.low, min_penetration, or_l)
                    if not clear_bear:
                        logger.info(f"[STRATEGY] Filtered out Bearish ORB on {underlying}: {reason_bear}")
                        return
                    if body_ratio < min_body_ratio:
                        logger.info(f"[STRATEGY] Filtered weak-bodied Bearish ORB on {underlying}: Body ratio {body_ratio:.1%} < {min_body_ratio:.0%}. Lacks institutional impulse.")
                        return
                    if require_vol and avg_vol > 0 and bar.volume < (avg_vol * vol_mult):
                        logger.info(f"[STRATEGY] Filtered low-volume Bearish ORB on {underlying}: Vol {bar.volume} < {avg_vol * vol_mult:.0f}. Institutional participation missing.")
                        return

                    st["or_triggered_today"] = True
                    st["armed_fvg"] = {
                        "source": "MOMENTUM_ORB",
                        "type": "BUY_PE",
                        "top": min(or_l, bar.high),
                        "bottom": bar.low,
                        "displacement_high": or_l,
                        "displacement_low": bar.low,
                        "breakout_boundary": or_l,
                        "underlying": underlying
                    }
                    status_msg = f"🚀 Momentum ORB Formed ({underlying} Put): Fresh Breakdown below OR Low ₹{or_l:.2f} (-{or_l - bar.close:.1f} pts, Vol: {bar.volume})"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    # Direct execution on momentum bar
                    await self._generate_sniper_signal(underlying, "BUY_PE", bar.close, st["armed_fvg"])
                    st["armed_fvg"] = None

        # =====================================================================
        # MODEL 3: 15-MINUTE DONCHIAN TREND BREAKOUT & MOMENTUM EXPANSION
        # =====================================================================
        is_paper = (self.state_mgr.execution_mode == "PAPER")
        current_trades = self.state_mgr.paper_trades_taken if is_paper else self.state_mgr.trades_taken_today
        if (
            self.cfg.get("enable_trend_pullback", True)
            and underlying in self.active_indices
            and not st.get("armed_fvg")
            and not self._is_in_trade(underlying)
            and not in_cooldown
            and current_trades < self.state_mgr.max_trades_allowed
        ):
            now_t = ist_time()
            if (time(9, 30) <= now_t <= time(14, 45)) and not self._is_midday_chop():
                if len(closed_3m) >= 6:
                    ema_fast_len = int(self.cfg.get("ema_fast_period", 9))
                    ema_slow_len = int(self.cfg.get("ema_slow_period", 21))
                    k_fast = 2.0 / (ema_fast_len + 1.0)
                    k_slow = 2.0 / (ema_slow_len + 1.0)

                    ema_fast = closed_3m[0].close
                    ema_slow = closed_3m[0].close
                    for b in closed_3m:
                        ema_fast = (b.close * k_fast) + (ema_fast * (1.0 - k_fast))
                        ema_slow = (b.close * k_slow) + (ema_slow * (1.0 - k_slow))

                    # Multi-Bar Rolling Donchian Range (configurable lookback, default 15 bars = 45m)
                    donch_bars = self.donchian_lookback_bars
                    if len(closed_3m) < (donch_bars + 1):
                        return
                    prior_donch_bars = closed_3m[-(donch_bars + 1):-1]
                    d_high = max(b.high for b in prior_donch_bars)
                    d_low = min(b.low for b in prior_donch_bars)
                    curr_bar = closed_3m[-1]

                    # Opening Range filter: block breakout if price is trapped inside Opening Range
                    or_h = st.get("or_high", 0.0)
                    or_l = st.get("or_low", 999999.0)
                    pass_or_bull = (not self.donchian_require_or_break) or (or_h > 0 and curr_bar.close > or_h)
                    pass_or_bear = (not self.donchian_require_or_break) or (or_l < 999999.0 and curr_bar.close < or_l)

                    # Volatility-Normalized Rubber-Band Ceiling (ATR Multiplier with structural OR displacement adaptation)
                    atr_val = self._calculate_atr(token, period=14)
                    min_vd = 12.0 if underlying == "NIFTY" else (36.0 if underlying == "SENSEX" else 25.0)
                    default_max_vd = 65.0 if underlying == "NIFTY" else (180.0 if underlying == "SENSEX" else 130.0)
                    configured_max_vd = float(self.cfg.get(f"max_vwap_distance_{underlying.lower()}", default_max_vd))
                    
                    # Adapt maximum VWAP distance if requiring OR breakout so structural expansion outside wide OR is not blocked
                    or_dist_bear = max(0.0, vwap - or_l) if (or_l < 999999.0 and self.donchian_require_or_break) else 0.0
                    or_dist_bull = max(0.0, or_h - vwap) if (or_h > 0.0 and self.donchian_require_or_break) else 0.0
                    base_max_vd = max(configured_max_vd, atr_val * self.max_vwap_atr_mult if atr_val > 1.0 else configured_max_vd)
                    max_vd_bear = base_max_vd + or_dist_bear
                    max_vd_bull = base_max_vd + or_dist_bull

                    min_b = 5.0 if underlying == "NIFTY" else (15.0 if underlying == "SENSEX" else 10.0)

                    # Climax Exhaustion Guard: Avoid entering if consecutive bars in trend direction without pause
                    prior_trend_bars = closed_3m[-self.max_consecutive_trend_bars:]
                    is_bearish_exhaustion = (len(prior_trend_bars) >= self.max_consecutive_trend_bars and all(b.close < b.open for b in prior_trend_bars))
                    is_bullish_exhaustion = (len(prior_trend_bars) >= self.max_consecutive_trend_bars and all(b.close > b.open for b in prior_trend_bars))

                    # Volatility distances to VWAP
                    vwap_dist_bear = vwap - curr_bar.close
                    vwap_dist_bull = curr_bar.close - vwap

                    # Bearish Momentum Expansion: 3m Close breaks Donchian low below VWAP with EMA 9 < 21 & outside OR
                    if curr_bar.close < d_low and curr_bar.close < vwap and ema_fast < ema_slow and (min_vd <= vwap_dist_bear <= max_vd_bear):
                        if not pass_or_bear:
                            logger.info(f"[STRATEGY] Filtered out Bearish Donchian noise on {underlying}: Price ₹{curr_bar.close:.1f} is inside Opening Range (₹{or_l:.1f} - ₹{or_h:.1f}). Range chop protected.")
                            return
                        clear_bear, reason_bear = self._check_macro_liquidity_clearance(underlying, "BEARISH", curr_bar.close, curr_bar.high, curr_bar.low, min_b, or_l)
                        if not clear_bear:
                            logger.info(f"[STRATEGY] Filtered out Bearish Donchian on {underlying}: {reason_bear}")
                            return
                        if is_bearish_exhaustion:
                            logger.info(f"[STRATEGY] Blocked Bearish Donchian Breakdown on {underlying}: Climax exhaustion ({self.max_consecutive_trend_bars} consecutive red bars).")
                            return
                        if (curr_bar.open - curr_bar.close) >= min_b:
                            swing_pts = max(18.0 if underlying == "NIFTY" else 55.0, d_high - curr_bar.close)
                            st["armed_fvg"] = {
                                "source": "TREND_PULLBACK",
                                "type": "BUY_PE",
                                "top": curr_bar.high,
                                "bottom": curr_bar.low,
                                "displacement_high": d_high,
                                "displacement_low": curr_bar.low,
                                "breakout_boundary": d_low,
                                "swing_pts": swing_pts,
                                "underlying": underlying
                            }
                            status_msg = f"📉 {donch_bars*3}m Donchian Trend Breakdown ({underlying} PE): Broke {donch_bars*3}m Low ₹{d_low:.1f} below OR Low (Risk: {swing_pts:.1f} pts, VWAP Dist: {vwap_dist_bear:.1f} <= {max_vd_bear:.1f})"
                            self.state_mgr.set_strategy_status(status_msg)
                            logger.info(f"[STRATEGY] {status_msg}")
                            await self._generate_sniper_signal(underlying, "BUY_PE", curr_bar.close, st["armed_fvg"])
                            st["armed_fvg"] = None

                    # Bullish Momentum Expansion: 3m Close breaks Donchian high above VWAP with EMA 9 > 21 & outside OR
                    elif curr_bar.close > d_high and curr_bar.close > vwap and ema_fast > ema_slow and (min_vd <= vwap_dist_bull <= max_vd_bull):
                        if not pass_or_bull:
                            logger.info(f"[STRATEGY] Filtered out Bullish Donchian noise on {underlying}: Price ₹{curr_bar.close:.1f} is inside Opening Range (₹{or_l:.1f} - ₹{or_h:.1f}). Range chop protected.")
                            return
                        clear_bull, reason_bull = self._check_macro_liquidity_clearance(underlying, "BULLISH", curr_bar.close, curr_bar.high, curr_bar.low, min_b, or_h)
                        if not clear_bull:
                            logger.info(f"[STRATEGY] Filtered out Bullish Donchian on {underlying}: {reason_bull}")
                            return
                        if is_bullish_exhaustion:
                            logger.info(f"[STRATEGY] Blocked Bullish Donchian Breakout on {underlying}: Climax exhaustion ({self.max_consecutive_trend_bars} consecutive green bars).")
                            return
                        if (curr_bar.close - curr_bar.open) >= min_b:
                            swing_pts = max(18.0 if underlying == "NIFTY" else 55.0, curr_bar.close - d_low)
                            st["armed_fvg"] = {
                                "source": "TREND_PULLBACK",
                                "type": "BUY_CE",
                                "top": curr_bar.high,
                                "bottom": curr_bar.low,
                                "displacement_low": d_low,
                                "displacement_high": curr_bar.high,
                                "breakout_boundary": d_high,
                                "swing_pts": swing_pts,
                                "underlying": underlying
                            }
                            status_msg = f"📈 {donch_bars*3}m Donchian Trend Breakout ({underlying} CE): Broke {donch_bars*3}m High ₹{d_high:.1f} above OR High (Risk: {swing_pts:.1f} pts, VWAP Dist: {vwap_dist_bull:.1f} <= {max_vd_bull:.1f})"
                            self.state_mgr.set_strategy_status(status_msg)
                            logger.info(f"[STRATEGY] {status_msg}")
                            await self._generate_sniper_signal(underlying, "BUY_CE", curr_bar.close, st["armed_fvg"])
                            st["armed_fvg"] = None

    async def _evaluate_fvg_retest(self, underlying: str, current_price: float):
        """Triggers sniper limit order when spot retraces into the Fair Value Gap zone."""
        st = self.state[underlying]
        fvg = st.get("armed_fvg")
        if not fvg:
            return

        if not self._is_market_hours() or self._is_midday_chop():
            st["armed_fvg"] = None
            return

        # FVG Retest TTL Check: Invalidate FVG if price failed to retest within fvg_ttl_minutes
        fvg_armed_time = fvg.get("armed_time")
        if fvg_armed_time:
            elapsed_fvg_mins = (now_ist() - fvg_armed_time).total_seconds() / 60.0
            max_fvg_ttl = float(self.cfg.get("fvg_ttl_minutes", 15.0))
            if elapsed_fvg_mins > max_fvg_ttl:
                logger.info(f"[STRATEGY] Expiring stale FVG for {underlying}: {elapsed_fvg_mins:.1f}m elapsed (Limit: {max_fvg_ttl}m)")
                st["armed_fvg"] = None
                return

        # Check if trade already active or daily limit reached
        is_paper = (self.state_mgr.execution_mode == "PAPER")
        current_trades = self.state_mgr.paper_trades_taken if is_paper else self.state_mgr.trades_taken_today
        if self._is_in_trade(underlying) or current_trades >= self.state_mgr.max_trades_allowed or self.state_mgr.consecutive_losses >= self.consecutive_loss_limit or self.state_mgr.is_panic_active or self.state_mgr.is_halted:
            return

        triggered = False
        signal_type = fvg["type"] # "BUY_CE" or "BUY_PE"
        vwap = st.get("vwap", 0.0)
        bounce_buffer = float(self.cfg.get("fvg_bounce_confirmation_pts", 3.0))

        if signal_type == "BUY_CE":
            # Retraces into top/middle of Bullish FVG
            if current_price <= fvg["top"] and current_price >= fvg["bottom"]:
                if self.cfg.get("require_candle_confirmation", True):
                    # Track minimum price reached within the FVG
                    fvg["trough"] = min(fvg.get("trough", current_price), current_price)
                    # Anti-knife-catching: Require price to bounce off the trough by bounce_buffer AND hold above VWAP
                    if (current_price - fvg["trough"]) >= bounce_buffer and current_price >= vwap:
                        triggered = True
                else:
                    triggered = True
        elif signal_type == "BUY_PE":
            # Retraces into bottom/middle of Bearish FVG
            if current_price >= fvg["bottom"] and current_price <= fvg["top"]:
                if self.cfg.get("require_candle_confirmation", True):
                    # Track peak price reached within the FVG
                    fvg["peak"] = max(fvg.get("peak", current_price), current_price)
                    # Anti-knife-catching: Require price to reject off peak by bounce_buffer AND hold below VWAP
                    if (fvg["peak"] - current_price) >= bounce_buffer and current_price <= vwap:
                        triggered = True
                else:
                    triggered = True

        if triggered:
            st["armed_fvg"] = None
            st["sweep_status"] = "NONE"
            await self._generate_sniper_signal(underlying, signal_type, current_price, fvg)

    async def _generate_sniper_signal(self, underlying: str, signal_type: str, spot: float, fvg: Dict[str, Any]):
        """Resolves target option strike and emits SignalEvent."""
        if underlying not in self.active_indices:
            logger.warning(f"[STRATEGY] Blocked signal dispatch for {underlying}: Index is disabled in active_indices settings.")
            return

        is_paper = (self.state_mgr.execution_mode == "PAPER")
        current_trades = self.state_mgr.paper_trades_taken if is_paper else self.state_mgr.trades_taken_today
        if current_trades >= self.state_mgr.max_trades_allowed:
            logger.warning(f"[STRATEGY] Blocked signal dispatch for {underlying}: Daily trade limit reached ({current_trades}/{self.state_mgr.max_trades_allowed}).")
            return

        if self.state_mgr.consecutive_losses >= self.consecutive_loss_limit:
            logger.warning(f"[STRATEGY] Blocked signal dispatch for {underlying}: Consecutive loss circuit tripped ({self.state_mgr.consecutive_losses} losses >= {self.consecutive_loss_limit} limit).")
            return

        if self.state_mgr.is_panic_active or self.state_mgr.is_halted:
            logger.warning(f"[STRATEGY] Blocked signal dispatch for {underlying}: System is in PANIC or HALTED state.")
            return

        st = self.state[underlying]
        opt_type = "CE" if "CE" in signal_type else "PE"
        strat_source = fvg.get("source", "ILSME_REVERSAL")
        
        # Check expiry day theta protection rule:
        cur_ist = now_ist()
        now_time = cur_ist.time()
        expiry_idx = 0
        if now_time < time(13, 0):
            # Check if nearest contract expires today (handles holidays & shifted expiries dynamically)
            nearest_opt = self.loader.get_atm_option(
                underlying=underlying,
                spot_price=spot,
                option_type=opt_type,
                expiry_index=0
            )
            if nearest_opt and nearest_opt.get("expiry"):
                try:
                    exp_dt = datetime.strptime(nearest_opt["expiry"].strip(), "%d%b%Y").date()
                    if exp_dt == cur_ist.date():
                        expiry_idx = 1
                        logger.info(f"[STRATEGY] Expiry Day Protection ({underlying} - {nearest_opt['expiry']}): morning 0-DTE blocked, rolling to next cycle (index {expiry_idx})")
                except Exception:
                    pass

        option_contract = self.loader.get_atm_option(
            underlying=underlying,
            spot_price=spot,
            option_type=opt_type,
            expiry_index=expiry_idx
        )

        if not option_contract:
            logger.error(f"[STRATEGY] Failed to find ATM {opt_type} option for {underlying}")
            return

        # Liquidity & Open Interest (OI) Filter + Top-of-Book Bid-Ask Spread Filter
        min_oi = self.cfg.get("min_open_interest", 50000)
        max_spread_pct = self.cfg.get("max_bid_ask_spread_pct", 1.5)
        live_opt_ltp = None

        if self.auth_mgr:
            opt_exch = option_contract.get("exchange") or ("BFO" if underlying == "SENSEX" else "NFO")
            liq_metrics = self.auth_mgr.get_option_liquidity_metrics(
                exchange=opt_exch,
                token=option_contract.get("symboltoken", ""),
                tradingsymbol=option_contract.get("tradingsymbol", "")
            )
            live_opt_ltp = liq_metrics.get("ltp")
            oi = liq_metrics.get("oi", 0)
            spread_pct = liq_metrics.get("spread_pct", 0.0)

            # Validate OI Threshold
            if oi > 0 and oi < min_oi:
                logger.warning(f"[STRATEGY] ⚠️ Low Open Interest ({oi:,} < {min_oi:,}) on {option_contract['tradingsymbol']}. Liquidity warning.")
            
            # Validate Bid-Ask Spread Threshold
            if spread_pct > max_spread_pct:
                logger.warning(f"[STRATEGY] ⚠️ High Bid-Ask Spread ({spread_pct}% > {max_spread_pct}%) on {option_contract['tradingsymbol']}. Slippage guard active.")

        # Realistic intrinsic + time value estimation model if live exchange LTP is unreachable
        strike_val = float(option_contract.get("strike", spot))
        if opt_type == "PE":
            intrinsic = max(0.0, strike_val - spot)
        else:
            intrinsic = max(0.0, spot - strike_val)
        atm_extrinsic = 180.0 if underlying == "NIFTY" else (350.0 if underlying == "BANKNIFTY" else 300.0)
        distance = abs(spot - strike_val)
        decay_factor = max(0.15, 1.0 - (distance / max(100.0, strike_val * 0.03)))
        estimated_premium = round(intrinsic + (atm_extrinsic * decay_factor), 2)
        base_premium = max(15.0, estimated_premium)

        entry_price = round(live_opt_ltp, 2) if (live_opt_ltp and live_opt_ltp > 0) else round(base_premium, 2)
        if live_opt_ltp and live_opt_ltp > 0:
            logger.info(f"[STRATEGY] 🎯 Fetched real live option price from Angel One: {option_contract['tradingsymbol']} = ₹{entry_price}")
        else:
            logger.warning(f"[STRATEGY] Real exchange LTP unavailable for {option_contract['tradingsymbol']}; using dynamic model premium: ₹{entry_price} (Intrinsic: ₹{intrinsic:.2f}, Extrinsic: ₹{atm_extrinsic * decay_factor:.2f})")
        
        # Stop-loss calculation: If setup provides swing_pts, use structural delta-based SL,
        # but clamp unit_risk to max_sl_percent (default 12%) so single-lot risk does not exceed daily drawdown budget
        max_sl_pct = float(self.risk_cfg.get("max_sl_percent", 0.12))
        swing_pts = fvg.get("swing_pts")
        if swing_pts and swing_pts > 0:
            raw_unit_risk = round(swing_pts * 0.55, 2)
            max_allowed_unit_risk = round(entry_price * max_sl_pct, 2)
            unit_risk = min(raw_unit_risk, max_allowed_unit_risk)
            stop_loss = round(max(1.0, entry_price - unit_risk), 2)
        else:
            sl_pct = self.risk_cfg.get("initial_sl_percent", 0.12)
            stop_loss = round(entry_price * (1.0 - sl_pct), 2)
            unit_risk = entry_price - stop_loss
        
        # Target 1: +2.0R to +3.0R (Full exit on 1 lot, 50% partial exit on >=2 lots)
        target_r = self.risk_cfg.get("partial_exit_r", 2.0)
        target_1 = round(entry_price + (unit_risk * target_r), 2)

        # Structural Invalidation Level:
        # Invalidation level represents the structural support/resistance boundary that,
        # if violated by spot, indicates the breakout or reversal momentum has failed.
        # For BUY_CE: boundary is below spot (OR High, Donchian High, or displacement low).
        # For BUY_PE: boundary is above spot (OR Low, Donchian Low, or displacement high).
        if strat_source == "MOMENTUM_ORB":
            swing_inval = fvg.get("breakout_boundary", fvg.get("displacement_low" if signal_type == "BUY_CE" else "displacement_high", 0.0))
        elif strat_source == "TREND_PULLBACK":
            swing_inval = fvg.get("breakout_boundary", fvg.get("displacement_low" if signal_type == "BUY_CE" else "displacement_high", 0.0))
        else:
            swing_inval = fvg.get("displacement_low" if signal_type == "BUY_CE" else "displacement_high", 0.0)

        # Scale-Invariant & Volatility-Adaptive Invalidation Buffer:
        # 1. Calculates rolling 14-period 3m ATR for the underlying.
        # 2. Computes baseline spot-proportional percentage (default 0.07% of spot).
        # 3. Blends 0.40x ATR with spot percentage so high volatility expands buffer,
        #    low volatility contracts buffer, and price level differences (SENSEX vs NIFTY) are handled naturally.
        idx_token = self.index_tokens.get(underlying, "")
        atr_cur = self._calculate_atr(idx_token, period=14) if idx_token else 0.0
        buf_pct = float(self.risk_cfg.get("invalidation_buffer_pct", 0.07)) / 100.0
        spot_pct_buf = round(spot * buf_pct, 1) if spot > 0 else float(self.risk_cfg.get("invalidation_buffer_pts", 15.0))
        if atr_cur > 1.0:
            dyn_inval_buf = round(max(atr_cur * 0.40, spot_pct_buf), 1)
        else:
            dyn_inval_buf = spot_pct_buf

        # Human readable reason & strat name
        if strat_source == "TREND_PULLBACK":
            strat_label = "Trend Breakout" if "CE" in signal_type else "Trend Breakdown"
            reason_text = f"Trend Expansion: {underlying} {'Breakout above' if 'CE' in signal_type else 'Breakdown below'} VWAP & EMA9/21"
        elif strat_source == "MOMENTUM_ORB":
            strat_label = "Momentum Breakout"
            reason_text = f"Momentum ORB Breakout on {underlying}"
        else:
            strat_label = "ILSME Reversal"
            reason_text = f"Institutional Liquidity Sweep [{fvg.get('bottom', 0):.1f}-{fvg.get('top', 0):.1f}] with 3m MSS across VWAP"

        # Determine execution strategies to run:
        is_paper = (self.state_mgr.execution_mode == "PAPER")
        if is_paper:
            paper_strats = self.cfg.get("paper_execution_strategies", ["NAKED", "DEBIT_SPREAD"])
            if isinstance(paper_strats, str):
                paper_strats = [paper_strats]
            target_strategies = paper_strats if paper_strats else ["NAKED"]
        else:
            real_strat = self.cfg.get("real_execution_strategy", "NAKED")
            target_strategies = [real_strat]

        # 1. Dispatch Naked Signal if selected
        if "NAKED" in target_strategies:
            signal_naked = SignalEvent(
                signal_id=f"SIG_{underlying}_{int(datetime.now().timestamp())}",
                underlying=underlying,
                signal_type=signal_type,
                strike=option_contract["strike"],
                option_type=opt_type,
                expiry=option_contract["expiry"],
                symboltoken=option_contract["symboltoken"],
                tradingsymbol=option_contract["tradingsymbol"],
                exchange=option_contract["exchange"],
                lot_size=option_contract["lotsize"],
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                fvg_top=fvg.get("top", 0.0),
                fvg_bottom=fvg.get("bottom", 0.0),
                sweep_level=st.get("sweep_price", 0.0),
                swing_invalidation_level=swing_inval,
                invalidation_buffer=dyn_inval_buf,
                strategy_name=f"{strat_label} (Naked)",
                reason=reason_text,
                execution_strategy="NAKED"
            )
            logger.info(f"[STRATEGY] ===> DISPATCHING NAKED SIGNAL [{strat_label}]: {signal_naked.signal_type} {signal_naked.tradingsymbol} Entry=₹{entry_price} SL=₹{stop_loss} T1=₹{target_1} (Structural Level: {swing_inval}, Buffer: {dyn_inval_buf}pt)")
            await self.bus.publish(signal_naked)

        # 2. Dispatch Debit Spread Signal if selected
        if "DEBIT_SPREAD" in target_strategies:
            strikes_otm = int(self.cfg.get("debit_spread_strikes_otm", 1))
            hedge_contract = self.loader.get_otm_option(
                underlying=underlying,
                spot_price=spot,
                option_type=opt_type,
                strikes_otm=strikes_otm,
                expiry_index=expiry_idx
            )
            if hedge_contract:
                hedge_strike = float(hedge_contract["strike"])
                if opt_type == "PE":
                    h_intrinsic = max(0.0, hedge_strike - spot)
                else:
                    h_intrinsic = max(0.0, spot - hedge_strike)
                h_dist = abs(spot - hedge_strike)
                h_decay = max(0.10, 1.0 - (h_dist / max(100.0, hedge_strike * 0.03)))
                h_base_premium = max(10.0, round(h_intrinsic + (atm_extrinsic * h_decay * 0.65), 2))

                live_h_ltp = None
                if self.auth_mgr:
                    h_exch = hedge_contract.get("exchange") or ("BFO" if underlying == "SENSEX" else "NFO")
                    h_liq = self.auth_mgr.get_option_liquidity_metrics(
                        exchange=h_exch,
                        token=hedge_contract.get("symboltoken", ""),
                        tradingsymbol=hedge_contract.get("tradingsymbol", "")
                    )
                    live_h_ltp = h_liq.get("ltp")

                hedge_entry = round(live_h_ltp, 2) if (live_h_ltp and live_h_ltp > 0) else round(h_base_premium, 2)
                spread_w = abs(hedge_strike - strike_val)
                net_deb = max(5.0, round(entry_price - hedge_entry, 2))
                max_spread_profit = max(5.0, round(spread_w - net_deb, 2))

                spread_tp1_pct = float(self.cfg.get("debit_spread_take_profit_pct", 0.50))
                spread_sl_pct = float(self.cfg.get("debit_spread_stop_loss_pct", 0.40))

                spread_t1 = round(net_deb + (max_spread_profit * spread_tp1_pct), 2)
                spread_sl = round(max(1.0, net_deb * (1.0 - spread_sl_pct)), 2)

                signal_spread = SignalEvent(
                    signal_id=f"SIG_SPD_{underlying}_{int(datetime.now().timestamp())}",
                    underlying=underlying,
                    signal_type=signal_type,
                    strike=option_contract["strike"],
                    option_type=opt_type,
                    expiry=option_contract["expiry"],
                    symboltoken=option_contract["symboltoken"],
                    tradingsymbol=option_contract["tradingsymbol"],
                    exchange=option_contract["exchange"],
                    lot_size=option_contract["lotsize"],
                    entry_price=entry_price,
                    stop_loss=spread_sl,
                    target_1=spread_t1,
                    fvg_top=fvg.get("top", 0.0),
                    fvg_bottom=fvg.get("bottom", 0.0),
                    sweep_level=st.get("sweep_price", 0.0),
                    swing_invalidation_level=swing_inval,
                    invalidation_buffer=dyn_inval_buf,
                    strategy_name=f"{strat_label} (Debit Spread)",
                    reason=f"{reason_text} [Debit Spread: Buy {option_contract['strike']} / Sell {hedge_contract['strike']}]",
                    execution_strategy="DEBIT_SPREAD",
                    hedge_tradingsymbol=hedge_contract["tradingsymbol"],
                    hedge_symboltoken=hedge_contract["symboltoken"],
                    hedge_strike=hedge_strike,
                    hedge_entry_price=hedge_entry,
                    net_debit=net_deb,
                    spread_width=spread_w
                )
                logger.info(f"[STRATEGY] ===> DISPATCHING DEBIT SPREAD SIGNAL [{strat_label}]: Buy {signal_spread.tradingsymbol} @ ₹{entry_price} / Sell {hedge_contract['tradingsymbol']} @ ₹{hedge_entry} (Net Debit: ₹{net_deb}, Max Profit: ₹{max_spread_profit})")
                await self.bus.publish(signal_spread)

        self.state[underlying]["in_trade"] = True
        self.state[underlying]["last_signal_time"] = ist_time()
        self.state_mgr.set_strategy_status(f"Dispatched Signals ({strat_label}): {option_contract['tradingsymbol']}")

    async def trigger_test_signal(self, underlying: str = "NIFTY", signal_type: str = "BUY_CE"):
        """Manual test trigger for dashboard interactive testing."""
        st = self.state[underlying]
        spot = st["last_spot"] or 24850.0
        mock_fvg = {"top": spot + 5, "bottom": spot - 5, "type": signal_type, "source": "MANUAL_TEST"}
        await self._generate_sniper_signal(underlying, signal_type, spot, mock_fvg)

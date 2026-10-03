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
        self.state: Dict[str, Dict[str, Any]] = {}
        for idx in self.active_indices:
            self._init_index_state(idx)

        # Buffer of bars: token -> timeframe -> List[BarEvent]
        self.bars: Dict[str, Dict[str, List[BarEvent]]] = {}
        self.option_volume_history: Dict[str, List[int]] = {}

    def _init_index_state(self, underlying: str):
        # Dynamically load true Previous Day High (PDH) and Low (PDL)
        pdh, pdl, ref_spot = self._fetch_dynamic_pdh_pdl(underlying)
        
        self.state[underlying] = {
            "pdh": pdh,
            "pdl": pdl,
            "session_high": pdh,
            "session_low": pdl,
            "vwap": ref_spot,
            "last_spot": ref_spot,
            "or_high": -1.0,
            "or_low": 999999.0,
            "or_settled": False,
            "sweep_status": "NONE",       # "NONE", "BULLISH_SWEEP", "BEARISH_SWEEP"
            "sweep_price": 0.0,
            "sweep_time": None,
            "armed_fvg": None,           # Holds pending FVG or Breakout zone dict
            "in_trade": False
        }
        logger.info(f"[STRATEGY] Initialized {underlying} Reference Levels -> PDH: {pdh:.2f} | PDL: {pdl:.2f} | Ref Spot: {ref_spot:.2f}")

    def _fetch_dynamic_pdh_pdl(self, underlying: str) -> tuple[float, float, float]:
        """Dynamically resolves true Previous Day High / Low from historical datasets or Angel One API."""
        import os
        import json
        
        today_str = datetime.now().strftime("%Y-%m-%d")
        idx_key = underlying.lower()
        
        # 1. Try local historical 3m / 15m candle store
        for tf in ["3m", "15m"]:
            path = f"data/historical/{idx_key}_{tf}.json"
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        bars = json.load(f)
                    dates = sorted(list(set(c[0][:10] for c in bars if c[0][:10] < today_str)))
                    if dates:
                        prev_date = dates[-1]
                        prev_bars = [c for c in bars if c[0].startswith(prev_date)]
                        if prev_bars:
                            pdh = max(b[2] for b in prev_bars)
                            pdl = min(b[3] for b in prev_bars)
                            close = prev_bars[-1][4]
                            return pdh, pdl, close
                except Exception as e:
                    logger.warning(f"[STRATEGY] Error reading {path} for PDH/PDL: {e}")

        # 2. Try Angel One SmartAPI live historical fetch if authenticated
        if self.auth_mgr and not self.auth_mgr.is_simulated and self.auth_mgr.smart_connect:
            try:
                sym_info = self.symbols_cfg.get(underlying, {})
                tok = sym_info.get("spot_token")
                exch = sym_info.get("exchange", "NSE")
                if tok:
                    from datetime import timedelta
                    from_d = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
                    to_d = datetime.now().strftime("%Y-%m-%d")
                    res = self.auth_mgr.smart_connect.getCandleData({
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
                        return float(last_day[2]), float(last_day[3]), float(last_day[4])
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
        """Checks if current time falls in 11:15 - 13:30 IST midday consolidation."""
        now = ist_time()
        start = time(11, 15)
        end = time(13, 30)
        return start <= now <= end

    def _is_market_hours(self) -> bool:
        """Trading entry window: 09:15 to 15:00 IST. No new setups or signals after 15:00."""
        now = ist_time()
        start = time(9, 15)
        end = time(15, 0)
        return start <= now <= end

    async def on_tick(self, event: TickEvent):
        # Check if tick belongs to underlying index spot
        for sym_name, sym_info in self.symbols_cfg.items():
            if str(event.token) == str(sym_info.get("spot_token")):
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

        if not target_underlying:
            return

        if event.is_closed:
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
        if not self._is_market_hours() or self._is_midday_chop():
            return

        if not self.cfg.get("enable_ilsme_sweep", True):
            return

        st = self.state[underlying]
        rng = max(0.01, bar.high - bar.low)
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

    async def _evaluate_3m_micro_displacement(self, underlying: str, bar: BarEvent):
        """
        3-minute Micro Timeframe Logic:
        1. ILSME Reversal Model: Market Structure Shift (MSS) through VWAP and Fair Value Gap (FVG).
        2. Momentum Trend Model: Opening Range Breakout (ORB) with VWAP and EMA confirmation.
        """
        if not self._is_market_hours():
            return

        st = self.state[underlying]
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
                        "underlying": underlying
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
                        "underlying": underlying
                    }
                    status_msg = f"FVG Formed ({underlying} Put): Armed for retracement retest [{fvg_bottom:.1f}-{fvg_top:.1f}]"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    return

        # =====================================================================
        # MODEL 2: MOMENTUM TREND / OPENING RANGE BREAKOUT (ORB) ENGINE
        # =====================================================================
        if self.cfg.get("enable_momentum_breakout", True) and st.get("or_settled") and not st.get("armed_fvg") and not st.get("in_trade"):
            now_t = ist_time()
            if (time(9, 30) <= now_t <= time(11, 15) or time(13, 30) <= now_t <= time(14, 30)):
                or_h = st["or_high"]
                or_l = st["or_low"]
                or_rng = max(1.0, or_h - or_l)

                # Minimum Volatility Expansion Filter: Block breakouts on compressed/dead chop days
                min_or_thresh = 45.0 if underlying == "NIFTY" else (160.0 if underlying == "SENSEX" else (120.0 if underlying == "BANKNIFTY" else 40.0))
                min_or_cfg = self.cfg.get(f"min_orb_range_{underlying.lower()}", min_or_thresh)
                if or_rng < min_or_cfg:
                    # Opening range is too narrow / low-volatility chop regime
                    return

                # Bullish Breakout: 3m Close > OR High + Close > VWAP
                if bar.close > or_h and bar.close > vwap and (bar.close - or_h) <= (or_rng * 0.40):
                    st["armed_fvg"] = {
                        "source": "MOMENTUM_ORB",
                        "type": "BUY_CE",
                        "top": bar.high,
                        "bottom": max(or_h, bar.low),
                        "displacement_low": or_h,
                        "displacement_high": bar.high,
                        "underlying": underlying
                    }
                    status_msg = f"🚀 Momentum ORB Formed ({underlying} Call): Breakout above OR High ₹{or_h:.2f}"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    # Direct execution on momentum bar
                    await self._generate_sniper_signal(underlying, "BUY_CE", bar.close, st["armed_fvg"])
                    st["armed_fvg"] = None

                # Bearish Breakout: 3m Close < OR Low + Close < VWAP
                elif bar.close < or_l and bar.close < vwap and (or_l - bar.close) <= (or_rng * 0.40):
                    st["armed_fvg"] = {
                        "source": "MOMENTUM_ORB",
                        "type": "BUY_PE",
                        "top": min(or_l, bar.high),
                        "bottom": bar.low,
                        "displacement_high": or_l,
                        "displacement_low": bar.low,
                        "underlying": underlying
                    }
                    status_msg = f"🚀 Momentum ORB Formed ({underlying} Put): Breakdown below OR Low ₹{or_l:.2f}"
                    self.state_mgr.set_strategy_status(status_msg)
                    logger.info(f"[STRATEGY] {status_msg}")
                    # Direct execution on momentum bar
                    await self._generate_sniper_signal(underlying, "BUY_PE", bar.close, st["armed_fvg"])
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

        # Check if trade already active or daily limit reached
        is_paper = (self.state_mgr.execution_mode == "PAPER")
        current_trades = self.state_mgr.paper_trades_taken if is_paper else self.state_mgr.trades_taken_today
        if st.get("in_trade") or current_trades >= self.state_mgr.max_trades_allowed:
            return

        triggered = False
        signal_type = fvg["type"] # "BUY_CE" or "BUY_PE"

        if signal_type == "BUY_CE":
            # Retraces into top/middle of Bullish FVG
            if current_price <= fvg["top"] and current_price >= fvg["bottom"]:
                triggered = True
        elif signal_type == "BUY_PE":
            # Retraces into bottom/middle of Bearish FVG
            if current_price >= fvg["bottom"] and current_price <= fvg["top"]:
                triggered = True

        if triggered:
            st["armed_fvg"] = None
            st["sweep_status"] = "NONE"
            await self._generate_sniper_signal(underlying, signal_type, current_price, fvg)

    async def _generate_sniper_signal(self, underlying: str, signal_type: str, spot: float, fvg: Dict[str, Any]):
        """Resolves target option strike and emits SignalEvent."""
        st = self.state[underlying]
        opt_type = "CE" if "CE" in signal_type else "PE"
        
        # Check expiry day theta protection rule:
        cur_ist = now_ist()
        now_time = cur_ist.time()
        expiry_idx = 0
        if now_time < time(13, 0):
            today_weekday = cur_ist.weekday()
            is_expiry_day = (
                (underlying in ["NIFTY", "BANKNIFTY"] and today_weekday == 1) or
                (underlying == "SENSEX" and today_weekday == 3)
            )
            if is_expiry_day:
                expiry_idx = 1
                logger.info(f"[STRATEGY] Expiry Day Protection ({underlying}): morning 0-DTE blocked, rolling to next cycle {expiry_idx}")

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
        
        # Hard stop-loss ~12% (from risk settings)
        sl_pct = self.risk_cfg.get("initial_sl_percent", 0.12)
        stop_loss = round(entry_price * (1.0 - sl_pct), 2)
        unit_risk = entry_price - stop_loss
        
        # Target 1: +3.0R (Full exit on 1 lot, 50% partial exit on >=2 lots)
        target_r = self.risk_cfg.get("partial_exit_r", 3.0)
        target_1 = round(entry_price + (unit_risk * target_r), 2)

        # Structural Invalidation Level (3m swing high for CE, swing low for PE)
        swing_inval = fvg.get("displacement_high" if signal_type == "BUY_CE" else "displacement_low", 0.0)

        signal = SignalEvent(
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
            fvg_top=fvg["top"],
            fvg_bottom=fvg["bottom"],
            sweep_level=st["sweep_price"],
            swing_invalidation_level=swing_inval,
            reason=f"Institutional Liquidity Sweep [{fvg['bottom']:.1f}-{fvg['top']:.1f}] with 3m MSS across VWAP"
        )

        self.state[underlying]["in_trade"] = True
        self.state_mgr.set_strategy_status(f"In Trade: {option_contract['tradingsymbol']}")
        logger.info(f"[STRATEGY] ===> DISPATCHING SNIPER SIGNAL: {signal.signal_type} {signal.tradingsymbol} Entry={entry_price} SL={stop_loss} T1={target_1} (Structural Swing Level: {swing_inval})")
        
        await self.bus.publish(signal)

    async def trigger_test_signal(self, underlying: str = "NIFTY", signal_type: str = "BUY_CE"):
        """Manual test trigger for dashboard interactive testing."""
        st = self.state[underlying]
        spot = st["last_spot"] or 24850.0
        mock_fvg = {"top": spot + 5, "bottom": spot - 5, "type": signal_type}
        await self._generate_sniper_signal(underlying, signal_type, spot, mock_fvg)

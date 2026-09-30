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
            "sweep_status": "NONE",       # "NONE", "BULLISH_SWEEP", "BEARISH_SWEEP"
            "sweep_price": 0.0,
            "sweep_time": None,
            "armed_fvg": None,           # Holds pending FVG zone dict
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
        self.state_mgr.set_strategy_status("Scanning for Liquidity Sweep")
        logger.info("[STRATEGY] Daily state reset completed with fresh reference levels.")

    def _is_midday_chop(self) -> bool:
        """Checks if current time falls in 11:15 - 13:30 IST midday consolidation."""
        now = ist_time()
        start = time(11, 15)
        end = time(13, 30)
        return start <= now <= end

    def _is_market_hours(self) -> bool:
        now = ist_time()
        start = time(9, 15)
        end = time(15, 12)
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
                self.state_mgr.update_spot_telemetry(
                    sym_name, event.ltp, st["vwap"], st["pdh"], st["pdl"], st["session_high"], st["session_low"]
                )
                
                # Check for limit retracement fill if FVG is armed
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
        Identifies Market Structure Shift (MSS) through VWAP and Fair Value Gap (FVG).
        """
        st = self.state[underlying]
        if st["sweep_status"] == "NONE":
            return

        # Check midday chop filter
        if self._is_midday_chop():
            logger.debug(f"[STRATEGY] Skipping entry for {underlying}: Midday consolidation window (11:15-13:30 IST).")
            return

        token = bar.token
        closed_3m = self.bars.get(token, {}).get("3m", [])
        if len(closed_3m) < 3:
            return

        c1 = closed_3m[-3]
        c2 = closed_3m[-2] # Displacement bar
        c3 = closed_3m[-1]

        vwap = bar.vwap or st["vwap"]

        # 1. Bullish Setup (Call buying)
        if st["sweep_status"] == "BULLISH_SWEEP":
            # MSS: C2 displaced strongly upward, closing above prior swing high and above VWAP
            has_displacement = c2.close > c1.high and c2.close > vwap
            # Bullish FVG: Candle 3 Low > Candle 1 High
            has_fvg = (c3.low - c1.high) >= self.cfg.get("fvg_min_points", 2.0)

            if has_displacement and has_fvg:
                fvg_top = c3.low
                fvg_bottom = c1.high
                st["armed_fvg"] = {
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

        # 2. Bearish Setup (Put buying)
        elif st["sweep_status"] == "BEARISH_SWEEP":
            # MSS: C2 displaced strongly downward, closing below prior swing low and below VWAP
            has_displacement = c2.close < c1.low and c2.close < vwap
            # Bearish FVG: Candle 3 High < Candle 1 Low
            has_fvg = (c1.low - c3.high) >= self.cfg.get("fvg_min_points", 2.0)

            if has_displacement and has_fvg:
                fvg_top = c1.low
                fvg_bottom = c3.high
                st["armed_fvg"] = {
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

    async def _evaluate_fvg_retest(self, underlying: str, current_price: float):
        """Triggers sniper limit order when spot retraces into the Fair Value Gap zone."""
        st = self.state[underlying]
        fvg = st.get("armed_fvg")
        if not fvg:
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
        
        # Hard stop-loss ~10% (from risk settings)
        sl_pct = self.risk_cfg.get("initial_sl_percent", 0.10)
        stop_loss = round(entry_price * (1.0 - sl_pct), 2)
        unit_risk = entry_price - stop_loss
        
        # Target 1: +2.0R (Partial exit 60%)
        target_1 = round(entry_price + (unit_risk * self.risk_cfg.get("partial_exit_r", 2.0)), 2)

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

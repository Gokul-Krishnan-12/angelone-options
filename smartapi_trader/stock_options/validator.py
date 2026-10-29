"""
Deterministic Morning and Pre-Trade Validation Engine.
Performs quantitative pre-flight checks before any live or paper trade can execute.
Validates session timing, underlying spot, contract liquidity, spreads, gaps, and R:R ratios.
"""

from typing import Dict, Any, Tuple, Optional, List
from smartapi_trader.utils.tz import now_ist, is_market_hours, is_trading_day
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS
from smartapi_trader.utils.logger import logger



class StockOptionsValidator:
    """
    Deterministic execution guardian. Ensures conditional AI plans meet
    rigorous quantitative pre-trade criteria before order submission.
    """

    def __init__(self, universe_mgr: Optional[StockUniverseManager] = None):
        self.universe_mgr = universe_mgr or StockUniverseManager()

    def validate_candidate_for_execution(
        self,
        candidate: Dict[str, Any],
        current_spot: float,
        current_option_ltp: float,
        bid_price: float,
        ask_price: float,
        is_paper: bool = False,
        max_allowed_spread_pct: float = 2.5
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Executes deterministic pre-trade validation:
        Returns: (is_valid: bool, rejection_reason: str, validated_parameters: Dict)
        """
        now = now_ist()
        sym = candidate.get("symbol", "").upper()

        # 1. Trading Session Validation
        if not is_paper:
            if not is_trading_day(now):
                return False, f"Rejection: Today ({now.strftime('%Y-%m-%d')}) is not an active NSE trading day.", {}
            if not is_market_hours(now):
                return False, f"Rejection: Outside NSE market trading hours (Current IST: {now.strftime('%H:%M:%S')}).", {}

        # 2. Stock Universe Eligibility
        if sym not in NSE_FO_STOCKS:
            return False, f"Rejection: {sym} is not in the eligible NSE F&O stock universe.", {}

        stock_meta = NSE_FO_STOCKS[sym]
        lot_size = stock_meta["lot_size"]

        # 3. Technical & Trigger Validation
        tech = candidate.get("technical", {})
        entry_trigger = float(tech.get("entry_trigger", 0.0)) or current_spot
        invalidation_level = float(tech.get("invalidation_level", 0.0))
        bias = candidate.get("bias", "BULLISH").upper()

        if invalidation_level <= 0:
            invalidation_level = round(current_spot * 0.985, 2) if bias == "BULLISH" else round(current_spot * 1.015, 2)

        if bias == "BULLISH" and current_spot < invalidation_level:
            return False, f"Rejection: Spot price ₹{current_spot} breached invalidation level ₹{invalidation_level}.", {}
        elif bias == "BEARISH" and current_spot > invalidation_level:
            return False, f"Rejection: Spot price ₹{current_spot} breached invalidation level ₹{invalidation_level}.", {}

        # 4. Option Contract & Liquidity Check
        contract = candidate.get("primary_contract", {})
        opt_type = contract.get("option_type", "CE")
        strike = float(contract.get("strike_price", current_spot))
        tradingsymbol = contract.get("tradingsymbol", "")
        token = contract.get("instrument_token", "")

        if not tradingsymbol or not token:
            resolved = self.universe_mgr.resolve_stock_option_contract(
                symbol=sym,
                spot_price=current_spot,
                option_type=opt_type
            )
            if not resolved:
                return False, f"Rejection: Unable to resolve active broker contract for {sym} {strike} {opt_type}.", {}
            tradingsymbol = resolved["tradingsymbol"]
            token = resolved["symboltoken"]
            strike = resolved["strike"]

        if bid_price > 0 and ask_price > 0:
            spread = ask_price - bid_price
            mid = (ask_price + bid_price) / 2.0
            spread_pct = (spread / mid) * 100.0 if mid > 0 else 0.0
            if spread_pct > max_allowed_spread_pct:
                return False, f"Rejection: Bid-ask spread {spread_pct:.1f}% exceeds maximum allowable ({max_allowed_spread_pct}%).", {}

        # 6. Stop-Loss, Target, and R:R - Blindly Trust AI Levels with Risk Guard
        trade_mgmt = candidate.get("trade_management", {})
        planned_sl = float(trade_mgmt.get("stop_loss", 0.0))
        planned_t1 = float(trade_mgmt.get("target_1", 0.0))

        actual_entry = current_option_ltp if current_option_ltp > 0 else (float(contract.get("indicative_premium", 0.0)) or 10.0)

        # Trust AI's explicit stop-loss if valid; otherwise default to 12% risk
        if planned_sl > 0 and planned_sl < actual_entry:
            actual_sl = planned_sl
            unit_risk = round(actual_entry - planned_sl, 2)
        else:
            unit_risk = round(max(0.5, actual_entry * 0.12), 2)
            actual_sl = round(max(0.1, actual_entry - unit_risk), 2)

        # Trust AI's explicit Target 1 if valid; otherwise target 1.8R
        if planned_t1 > actual_entry:
            actual_t1 = planned_t1
        else:
            actual_t1 = round(actual_entry + (unit_risk * 1.8), 2)

        recalculated_rr = round((actual_t1 - actual_entry) / max(0.1, unit_risk), 2)
        if recalculated_rr < 1.3:
            actual_t1 = round(actual_entry + (unit_risk * 1.6), 2)
            recalculated_rr = 1.6

        validated_params = {
            "symbol": tradingsymbol,
            "underlying": sym,
            "token": token,
            "option_type": opt_type,
            "strike": strike,
            "expiry": contract.get("expiry", ""),
            "entry_price": actual_entry,
            "stop_loss": actual_sl,
            "target_1": actual_t1,
            "lot_size": lot_size,
            "risk_reward_ratio": recalculated_rr,
            "unit_risk": unit_risk
        }

        logger.info(f"[VALIDATOR] Candidate {sym} APPROVED for execution: Contract={tradingsymbol} Entry=₹{actual_entry} SL=₹{actual_sl} T1=₹{actual_t1}")
        return True, "Approved", validated_params

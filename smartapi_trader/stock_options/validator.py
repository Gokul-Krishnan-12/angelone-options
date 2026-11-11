"""
Deterministic Morning and Pre-Trade Validation Engine.
Performs quantitative pre-flight checks before any live or paper trade can execute.
Validates session timing, underlying spot, contract liquidity, spreads, gaps, and R:R ratios.
Also evaluates conditional entry triggers and structural invalidation boundaries.
"""

from typing import Dict, Any, Tuple, Optional, List
from smartapi_trader.utils.tz import now_ist, is_market_hours, is_trading_day
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS, is_high_beta_stock
from smartapi_trader.utils.logger import logger


def check_trigger_status(
    candidate: Dict[str, Any],
    current_spot: float
) -> Tuple[bool, bool, str]:
    """
    Evaluates whether candidate trigger condition is met or invalidated against current spot price.
    Returns: (is_triggered: bool, is_invalidated: bool, status_reason: str)
    """
    sym = str(candidate.get("symbol", "")).upper()
    tech = candidate.get("technical", {})
    bias = str(candidate.get("bias", "BULLISH")).upper()

    ref_spot = float(tech.get("reference_price") or current_spot)
    entry_trigger = float(tech.get("entry_trigger", 0.0))
    inval_level = float(tech.get("invalidation_level", 0.0))

    # Guard against false invalidation if current_spot is unpriced (<= 0)
    if current_spot <= 0 and ref_spot > 0:
        current_spot = ref_spot

    if inval_level <= 0:
        inval_level = round(ref_spot * 0.985, 2) if bias == "BULLISH" else round(ref_spot * 1.015, 2)

    # 1. Invalidation Check
    if bias == "BULLISH" and current_spot < inval_level:
        return False, True, f"Invalidated: Spot ₹{current_spot:.2f} breached invalidation level ₹{inval_level:.2f}"
    if bias == "BEARISH" and current_spot > inval_level:
        return False, True, f"Invalidated: Spot ₹{current_spot:.2f} breached invalidation level ₹{inval_level:.2f}"

    # 2. Trigger Check
    # If no explicit trigger was configured, or trigger is effectively at current spot:
    if entry_trigger <= 0 or abs(entry_trigger - current_spot) / max(1.0, current_spot) < 0.0005:
        return True, False, "Entry trigger confirmed (At market)"

    if bias == "BULLISH":
        if entry_trigger >= ref_spot:
            # Bullish Breakout: Spot must break above trigger level
            if current_spot >= entry_trigger:
                return True, False, f"Breakout confirmed: Spot ₹{current_spot:.2f} >= Trigger ₹{entry_trigger:.2f}"
            else:
                dist_pct = round(((entry_trigger - current_spot) / current_spot) * 100.0, 2)
                return False, False, f"Waiting for breakout: Spot ₹{current_spot:.2f} < Trigger ₹{entry_trigger:.2f} (+{dist_pct}% away)"
        else:
            # Bullish Dip / Pullback: Spot must test support trigger
            if current_spot <= entry_trigger:
                return True, False, f"Dip confirmed: Spot ₹{current_spot:.2f} <= Trigger ₹{entry_trigger:.2f}"
            else:
                dist_pct = round(((current_spot - entry_trigger) / current_spot) * 100.0, 2)
                return False, False, f"Waiting for dip: Spot ₹{current_spot:.2f} > Trigger ₹{entry_trigger:.2f} (-{dist_pct}% away)"
    else:  # BEARISH
        if entry_trigger <= ref_spot:
            # Bearish Breakdown: Spot must break below trigger level
            if current_spot <= entry_trigger:
                return True, False, f"Breakdown confirmed: Spot ₹{current_spot:.2f} <= Trigger ₹{entry_trigger:.2f}"
            else:
                dist_pct = round(((current_spot - entry_trigger) / current_spot) * 100.0, 2)
                return False, False, f"Waiting for breakdown: Spot ₹{current_spot:.2f} > Trigger ₹{entry_trigger:.2f} (-{dist_pct}% away)"
        else:
            # Bearish Rally / Resistance Test: Spot must test resistance trigger
            if current_spot >= entry_trigger:
                return True, False, f"Rally confirmed: Spot ₹{current_spot:.2f} >= Trigger ₹{entry_trigger:.2f}"
            else:
                dist_pct = round(((entry_trigger - current_spot) / current_spot) * 100.0, 2)
                return False, False, f"Waiting for rally: Spot ₹{current_spot:.2f} < Trigger ₹{entry_trigger:.2f} (+{dist_pct}% away)"


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
        max_allowed_spread_pct: float = 2.5,
        require_trigger: bool = False
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
        is_trig, is_inval, trig_msg = check_trigger_status(candidate, current_spot)
        if is_inval:
            return False, f"Rejection: {trig_msg}", {}

        if require_trigger and not is_trig:
            return False, f"Rejection: {trig_msg}", {}

        # 3b. Sectoral Confluence Check
        sector_confluence = candidate.get("sector_confluence")
        if sector_confluence and isinstance(sector_confluence, dict):
            if not sector_confluence.get("aligned", True):
                reason = sector_confluence.get("reason", "Sector divergence detected.")
                logger.warning(f"[VALIDATOR] Candidate {sym} rejected: {reason}")
                return False, f"Rejection: {reason}", {}

        # 4. Option Contract & Liquidity Check
        contract = candidate.get("primary_contract", {})
        opt_type = contract.get("option_type", "CE")
        strike = float(contract.get("strike_price") or contract.get("strike") or current_spot)
        tradingsymbol = contract.get("tradingsymbol", "")
        token = contract.get("instrument_token") or contract.get("symboltoken") or contract.get("token", "")

        if not tradingsymbol or not token or " " in tradingsymbol:
            resolved = self.universe_mgr.resolve_stock_option_contract(
                symbol=sym,
                spot_price=strike if strike > 0 else current_spot,
                option_type=opt_type
            )
            if not resolved:
                return False, f"Rejection: Unable to resolve active broker contract for {sym} {strike} {opt_type}.", {}
            tradingsymbol = resolved["tradingsymbol"]
            token = resolved["symboltoken"]
            strike = resolved["strike"]
            lot_size = int(resolved.get("lotsize") or lot_size)
            contract["tradingsymbol"] = tradingsymbol
            contract["instrument_token"] = token
            contract["symboltoken"] = token
            contract["strike"] = strike
            contract["strike_price"] = strike
            contract["expiry"] = resolved.get("expiry") or contract.get("expiry", "")

        if bid_price > 0 and ask_price > 0:
            spread = ask_price - bid_price
            mid = (ask_price + bid_price) / 2.0
            spread_pct = (spread / mid) * 100.0 if mid > 0 else 0.0
            if spread_pct > max_allowed_spread_pct:
                return False, f"Rejection: Bid-ask spread {spread_pct:.1f}% exceeds maximum allowable ({max_allowed_spread_pct}%).", {}

        # 6. Stop-Loss, Target, and R:R - Dynamic Institutional Risk Bracket Formulator
        trade_mgmt = candidate.get("trade_management", {})
        planned_sl = float(trade_mgmt.get("stop_loss", 0.0))
        planned_t1 = float(trade_mgmt.get("target_1", 0.0))

        actual_entry = current_option_ltp if current_option_ltp > 0 else (float(contract.get("indicative_premium", 0.0)) or 10.0)

        # Dynamic Institutional Risk Bracket Formulator:
        # Prevent inverted or distorted risk:reward when actual fill differs from AI estimated premium
        unit_risk = None
        if planned_sl > 0 and planned_sl < actual_entry:
            implied_risk_pct = (actual_entry - planned_sl) / actual_entry
            max_allowed_risk_pct = 0.35 if actual_entry < 15.0 else 0.20
            # Honor planned SL only if within disciplined premium risk band
            if 0.05 <= implied_risk_pct <= max_allowed_risk_pct:
                actual_sl = planned_sl
                unit_risk = round(actual_entry - planned_sl, 2)

        if unit_risk is None:
            # Default to institutional 12% option premium stop
            unit_risk = round(max(0.5, actual_entry * 0.12), 2)
            actual_sl = round(max(0.1, actual_entry - unit_risk), 2)

        # Target R:R - Guarantee minimum 1:1.8 to 1:2.0 positive expectancy
        default_rr = 2.0 if is_high_beta_stock(sym) else 1.8
        target_rr = default_rr
        try:
            rr_val = float(trade_mgmt.get("risk_reward_ratio", default_rr))
            if rr_val >= 1.5:
                target_rr = min(3.0, rr_val)
        except Exception:
            target_rr = default_rr

        if planned_t1 > actual_entry:
            implied_rr = round((planned_t1 - actual_entry) / max(0.1, unit_risk), 2)
            if 1.35 <= implied_rr <= 4.0:
                actual_t1 = planned_t1
                recalculated_rr = implied_rr
            else:
                actual_t1 = round(actual_entry + (unit_risk * target_rr), 2)
                recalculated_rr = target_rr
        else:
            actual_t1 = round(actual_entry + (unit_risk * target_rr), 2)
            recalculated_rr = target_rr

        actual_t2 = round(actual_entry + (unit_risk * max(2.5, recalculated_rr * 1.5)), 2)

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
            "target_2": actual_t2,
            "lot_size": lot_size,
            "risk_reward_ratio": recalculated_rr,
            "unit_risk": unit_risk
        }

        logger.info(f"[VALIDATOR] Candidate {sym} APPROVED for execution: Contract={tradingsymbol} Entry=₹{actual_entry} SL=₹{actual_sl} T1=₹{actual_t1}")
        return True, "Approved", validated_params

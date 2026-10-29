"""
AI Provider Abstraction & Structured Recommendation Schemas.
Enforces typed recommendation formats, validation rules,
and maximum candidate constraints.
"""

from abc import ABC, abstractmethod
import re
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
from smartapi_trader.stock_options.universe import is_high_beta_stock


class OptionContractPlan(BaseModel):
    option_type: Literal["CE", "PE"]
    strike_price: float
    expiry: str
    instrument_token: str = ""
    tradingsymbol: str = ""
    indicative_premium: float = 0.0
    max_acceptable_premium: float = 0.0
    bid_ask_spread: float = 0.0
    liquidity_rating: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    lot_size: int = 1


class TechnicalSetup(BaseModel):
    reference_price: float
    support_level: float
    resistance_level: float
    trend: Literal["BULLISH", "BEARISH", "SIDEWAYS"]
    momentum: str = ""
    volume_analysis: str = ""
    entry_trigger: float
    entry_conditions: str
    invalidation_level: float
    invalidation_conditions: str
    technical_rationale: str


class TradeManagement(BaseModel):
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    risk_reward_ratio: float
    max_holding_period_mins: int = 120
    exit_conditions: str
    reasons_to_skip: str = ""
    estimated_capital_required: float = 0.0


class StockCandidatePlan(BaseModel):
    symbol: str
    company_name: str = ""
    sector: str = ""
    setup_type: str = "Breakout / Momentum"
    bias: Literal["BULLISH", "BEARISH", "NO_TRADE"]
    recommendation: Literal["BUY", "HOLD", "WATCH", "SKIP"]
    confidence_score: float = Field(default=0.75, ge=0.0, le=1.0)
    confidence_limitations: str = ""
    technical: TechnicalSetup
    primary_contract: OptionContractPlan
    alternative_contracts: List[OptionContractPlan] = Field(default_factory=list)
    trade_management: TradeManagement
    news_events: str = ""
    gap_risk: str = "Normal"
    earnings_risk: str = "No immediate earnings within 3 days"
    market_context: str = ""
    evidence: List[str] = Field(default_factory=list)
    missing_information: str = ""
    approval_status: str = "PENDING"


def normalize_candidate(raw: Dict[str, Any]) -> StockCandidatePlan:
    """
    Intelligently normalizes candidate output from LLM responses into typed StockCandidatePlan.
    Handles institutional quantitative schema (setups, spot_trigger, derivative_contract, catalyst_summary)
    as well as flat, nested, and legacy naming conventions.
    """
    if not isinstance(raw, dict):
        raise ValueError("Candidate item must be a dictionary.")

    sym = str(raw.get("symbol") or raw.get("stock") or raw.get("ticker") or "").strip().upper()
    if not sym:
        raise ValueError("Missing symbol in candidate.")

    direction_val = str(raw.get("direction") or raw.get("bias") or raw.get("trend") or "BULLISH").upper().strip()
    if "BEAR" in direction_val or "PE" in direction_val:
        bias = "BEARISH"
    elif "BULL" in direction_val or "CE" in direction_val:
        bias = "BULLISH"
    elif direction_val in ("NO_TRADE", "SIDEWAYS"):
        bias = "NO_TRADE"
    else:
        bias = "BULLISH"

    rec = str(raw.get("recommendation", "BUY")).upper()
    if rec not in ("BUY", "HOLD", "WATCH", "SKIP"):
        rec = "BUY"

    catalyst = str(raw.get("catalyst_summary") or raw.get("news_events") or raw.get("market_context") or "")
    setup_type = str(raw.get("setup_type") or raw.get("strategy") or ("VWAP & OI Confluence" if catalyst else "Breakout / Momentum"))

    # Confidence score normalization: handles "1-10", "8", "8.5", 8, 0.85
    conf = 0.85
    conf_raw = raw.get("confidence_score")
    if conf_raw is not None:
        try:
            if isinstance(conf_raw, str):
                m = re.search(r"(\d+(?:\.\d+)?)", conf_raw)
                if m:
                    val = float(m.group(1))
                    conf = (val / 10.0) if val > 1.0 else val
            else:
                val = float(conf_raw)
                conf = (val / 10.0) if val > 1.0 else val
        except Exception:
            conf = 0.85
    conf = max(0.0, min(1.0, conf))

    # Technical normalization: supports spot_trigger dictionary
    tech_data = raw.get("technical")
    spot_trig = raw.get("spot_trigger")
    if isinstance(tech_data, dict):
        try:
            tech = TechnicalSetup(**tech_data)
        except Exception:
            tech = None
    else:
        tech = None

    if not tech:
        ltp = 0.0
        if isinstance(spot_trig, dict):
            try:
                ltp = float(spot_trig.get("current_spot") or 0.0)
            except Exception:
                pass
        if not ltp:
            for k in ("underlying_ltp", "spot", "reference_price", "ltp"):
                if raw.get(k) is not None:
                    try:
                        ltp = float(raw[k])
                        break
                    except Exception:
                        pass

        entry_trig = ltp
        spot_inval = round(ltp * 0.985, 2) if bias == "BULLISH" else round(ltp * 1.015, 2)
        if isinstance(spot_trig, dict):
            try:
                if spot_trig.get("entry_above_or_below") is not None:
                    entry_trig = float(spot_trig["entry_above_or_below"])
                if spot_trig.get("spot_invalidation") is not None:
                    spot_inval = float(spot_trig["spot_invalidation"])
            except Exception:
                pass
        else:
            entry_trig = float(raw.get("entry_trigger") or raw.get("trigger") or ltp)
            spot_inval = float(raw.get("invalidation_level") or spot_inval)

        supp = round(min(ltp, spot_inval) * 0.99, 2) if ltp else 100.0
        res = round(max(ltp, entry_trig) * 1.01, 2) if ltp else 110.0
        cond = str(raw.get("technical_trigger") or raw.get("entry_conditions") or f"Spot confirmation at ₹{entry_trig}")
        rationale = str(catalyst or raw.get("technical_rationale") or raw.get("strategy") or cond)
        trend = bias if bias in ("BULLISH", "BEARISH") else "SIDEWAYS"

        tech = TechnicalSetup(
            reference_price=ltp,
            support_level=supp,
            resistance_level=res,
            trend=trend,
            momentum=setup_type,
            volume_analysis="Institutional volume with fresh OI buildup",
            entry_trigger=entry_trig,
            entry_conditions=cond,
            invalidation_level=spot_inval,
            invalidation_conditions=f"Spot structural invalidation at ₹{spot_inval}",
            technical_rationale=rationale
        )

    # Primary contract normalization: supports derivative_contract dictionary
    contract_data = raw.get("primary_contract")
    deriv = raw.get("derivative_contract")
    if isinstance(contract_data, dict):
        try:
            contract = OptionContractPlan(**contract_data)
        except Exception:
            contract = None
    else:
        contract = None

    if not contract and isinstance(deriv, dict):
        strike = 0.0
        try:
            strike = float(deriv.get("strike") or 0.0)
        except Exception:
            strike = tech.reference_price

        opt_type = str(deriv.get("option_type") or ("PE" if bias == "BEARISH" else "CE")).upper().strip()
        opt_type = "PE" if "PE" in opt_type else "CE"
        expiry = str(deriv.get("expiry") or "CURRENT_MONTH").strip()

        prem = 0.0
        for pk in ("recommended_limit_entry", "current_ltp"):
            if deriv.get(pk) is not None:
                try:
                    prem = float(deriv[pk])
                    if prem > 0:
                        break
                except Exception:
                    pass

        strike_str = int(strike) if strike.is_integer() else strike
        contract = OptionContractPlan(
            option_type=opt_type,
            strike_price=strike,
            expiry=expiry,
            tradingsymbol=f"{sym} {strike_str} {opt_type}",
            indicative_premium=prem,
            liquidity_rating="HIGH"
        )

    if not contract:
        opt_str = str(raw.get("option_contract") or raw.get("contract") or raw.get("tradingsymbol") or "")
        opt_type = "PE" if ("PE" in opt_str.upper() or bias == "BEARISH") else "CE"
        strike = 0.0
        strike_match = re.search(r"(\d+(?:\.\d+)?)", opt_str)
        if strike_match:
            strike = float(strike_match.group(1))
        elif raw.get("strike_price"):
            strike = float(raw["strike_price"])
        elif raw.get("strike"):
            strike = float(raw["strike"])
        else:
            strike = tech.reference_price

        prem = 0.0
        prem_field = str(raw.get("entry_premium_range") or raw.get("entry_premium") or raw.get("indicative_premium") or "")
        p_match = re.search(r"(\d+(?:\.\d+)?)", prem_field)
        if p_match:
            prem = float(p_match.group(1))

        contract = OptionContractPlan(
            option_type=opt_type,
            strike_price=strike,
            expiry="CURRENT_MONTH",
            tradingsymbol=opt_str or f"{sym} {strike} {opt_type}",
            indicative_premium=prem,
            liquidity_rating="HIGH" if "high" in str(raw.get("liquidity_rating", "")).lower() else "MEDIUM"
        )

    # Trade management normalization: supports derivative_contract fields (stop_loss_premium, target_1, etc.)
    tm_data = raw.get("trade_management")
    if isinstance(tm_data, dict):
        try:
            tm = TradeManagement(**tm_data)
        except Exception:
            tm = None
    else:
        tm = None

    if not tm:
        source_dict = deriv if isinstance(deriv, dict) else raw
        sl = 0.0
        for k in ("stop_loss_premium", "stop_loss", "sl"):
            if source_dict.get(k) is not None:
                try:
                    sl = float(source_dict[k])
                    break
                except Exception:
                    pass
        t1 = 0.0
        for k in ("target_1", "target_1_premium", "t1", "target"):
            if source_dict.get(k) is not None:
                try:
                    t1 = float(source_dict[k])
                    break
                except Exception:
                    pass
        t2_val = None
        for k in ("target_2", "target_2_premium", "t2"):
            if source_dict.get(k) is not None:
                try:
                    t2_val = float(source_dict[k])
                    break
                except Exception:
                    pass
        # Adaptive Risk-Reward: 2.0R for High-Beta stocks, 1.5R for Standard large caps
        is_hb = is_high_beta_stock(sym) or str(raw.get("beta_profile", "")).upper() == "HIGH_BETA"
        default_expected_rr = 2.0 if is_hb else 1.5

        rr = default_expected_rr
        rr_str = str(source_dict.get("risk_reward_ratio") or "")
        if rr_str and rr_str not in ("1:X", "None", ""):
            try:
                if ":" in rr_str:
                    rr = float(rr_str.split(":")[1])
                else:
                    rr = float(rr_str)
            except Exception:
                rr = default_expected_rr
        else:
            rr = default_expected_rr

        if not sl and contract and contract.indicative_premium > 0:
            sl = round(contract.indicative_premium * 0.85, 2)
        if not t1 and contract and contract.indicative_premium > 0:
            risk_pts = max(0.5, contract.indicative_premium - sl)
            t1 = round(contract.indicative_premium + (risk_pts * rr), 2)

        tm = TradeManagement(
            stop_loss=sl,
            target_1=t1,
            target_2=t2_val,
            risk_reward_ratio=rr,
            exit_conditions=str(raw.get("exit_conditions") or "Target reached or Stop Loss hit"),
            max_holding_period_mins=120
        )

    return StockCandidatePlan(
        symbol=sym,
        company_name=str(raw.get("company_name", "")),
        sector=str(raw.get("sector", "")),
        setup_type=setup_type,
        bias=bias,
        recommendation=rec,
        confidence_score=conf,
        technical=tech,
        primary_contract=contract,
        trade_management=tm,
        market_context=catalyst or str(raw.get("execution_notes") or raw.get("market_context") or "")
    )


class AIAnalysisResponse(BaseModel):
    run_id: str
    run_type: Literal["OVERNIGHT_PLAN", "INTRADAY_SCAN"]
    timestamp: str
    intended_trading_date: str
    provider: str
    model: str
    market_summary: str = ""
    total_evaluated: int = 0
    total_shortlisted: int = 0
    candidates: List[StockCandidatePlan] = Field(default_factory=list)
    no_trade_reason: Optional[str] = None
    latency_ms: float = 0.0
    validation_warnings: List[str] = Field(default_factory=list)


class AIProvider(ABC):
    """Abstract interface implemented by all supported AI providers."""

    def __init__(self, api_key: str, model_name: str, timeout_seconds: int = 30):
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def analyze_market(
        self,
        run_type: str,
        intended_date: str,
        stock_data: List[Dict[str, Any]],
        market_context: Dict[str, Any],
        max_candidates: int = 3
    ) -> AIAnalysisResponse:
        """
        Executes an AI research or scanning query with structured JSON validation.
        max_candidates is strictly clamped between 1 and 3.
        """
        pass


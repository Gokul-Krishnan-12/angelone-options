"""
OpenAI (ChatGPT) Integration Provider.
Implements structured outputs via OpenAI REST API.
"""

import time
import json
import aiohttp
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.ai.provider_base import (
    AIProvider, AIAnalysisResponse, StockCandidatePlan, normalize_candidate
)
from smartapi_trader.utils.logger import logger


SYSTEM_PROMPT = """You are an institutional quantitative equity and derivatives analyst focusing on NSE India F&O equities.

You are provided with pre-screened market telemetry for the top momentum stocks today, including live spot prices, intraday VWAP status, Open Interest (OI) buildup, ATM option chain quotes, and breaking news/sentiment data.

### INPUT DATA:
{market_telemetry_json}

### OBJECTIVE:
Select AT MOST {max_candidates} high-probability intraday option setups where technical price action, OI positioning, and market structure exhibit strict confluence.

### EVALUATION CRITERIA:
1. Confluence Verification & Trend Confirmation:
   - Review each stock's technical indicators, VWAP status, and volume expansion ratio.
   - Bullish (CE): Spot trading above VWAP, positive price change with fresh OI addition (Long Buildup), and volume ratio > 1.2x.
   - Bearish (PE): Spot trading below VWAP, negative price change with fresh OI addition (Short Buildup), and distribution volume.
   - Filter Out: Strictly avoid stocks in tight consolidation ranges, stocks with earnings announcements today (IV crush risk), AND OVEREXTENDED STOCKS (spot trading > 1.4% away from VWAP or RSI > 72). Do NOT chase parabolic climax moves at the highs. Focus strictly on fresh BASE BREAKOUTS within 0.2% - 0.8% of VWAP.
2. Spot Confirmation Levels (CRITICAL):
   - Focus on the UNDERLYING CASH SPOT PRICE.
   - "entry_above_or_below": Define the exact cash spot breakout confirmation level (e.g., Session High or Range Breakout). The trading engine arms this trigger and monitors real exchange spot quotes every 3 seconds before executing.
   - "spot_invalidation": Structural invalidation level (e.g. VWAP or swing low/high). If the spot touches this level before breakout, the trade is cancelled.
3. Option Contract Alignment & Math Integrity:
   - Select strictly from the provided active strike contracts in the input data. Do not invent strikes or prices.
   - For HIGH_BETA stocks (beta_profile == "HIGH_BETA"): Set "risk_reward_ratio": "1:2.0" (2R Target).
   - For STANDARD large-caps: Set "risk_reward_ratio": "1:1.8" (1.8R Target).
   - Strict R:R Math: "stop_loss_premium" should be ~12% below entry (risk = entry - SL). "target_1" MUST be entry + (risk * R:R) (e.g. entry ₹5.30, SL ₹4.66 -> risk=0.64. For 1:2.0 R:R, Target 1 MUST be ₹5.30 + 1.28 = ₹6.58. Do NOT output symmetrical 1:1 targets).
   - The quantitative execution engine automatically manages dynamic 12% SL, 0.85R Breakeven capital lock, and Take-Profit at execution fill.

### OUTPUT FORMAT:
Output strictly valid JSON with no markdown formatting or commentary outside the JSON block:

{{
  "timestamp": "<ISO timestamp>",
  "market_regime": "Trending Bullish | Trending Bearish | Rangebound",
  "setups": [
    {{
      "symbol": "TICKER",
      "direction": "BULLISH | BEARISH",
      "catalyst_summary": "1-2 sentence breakdown of technical structure + OI confluence",
      "spot_trigger": {{
        "current_spot": 0.0,
        "entry_above_or_below": 0.0,
        "spot_invalidation": 0.0
      }},
      "derivative_contract": {{
        "strike": 0,
        "option_type": "CE | PE",
        "expiry": "DD-MMM-YYYY",
        "current_ltp": 0.0,
        "recommended_limit_entry": 0.0,
        "stop_loss_premium": 0.0,
        "target_1": 0.0,
        "target_2": 0.0,
        "risk_reward_ratio": "1:X"
      }},
      "confidence_score": "1-10"
    }}
  ]
}}
"""


class OpenAIProvider(AIProvider):
    API_URL = "https://api.openai.com/v1/chat/completions"

    async def analyze_market(
        self,
        run_type: str,
        intended_date: str,
        stock_data: List[Dict[str, Any]],
        market_context: Dict[str, Any],
        max_candidates: int = 3
    ) -> AIAnalysisResponse:
        clamped_max = min(3, max(1, max_candidates))
        run_id = f"OAI_{int(time.time() * 1000)}"
        start_time = time.time()
        timestamp_str = datetime.now().isoformat()

        if not self.api_key or self.api_key.strip() in ("", "YOUR_OPENAI_API_KEY", "dummy"):
            return self._build_offline_response(
                run_id=run_id,
                run_type=run_type,
                intended_date=intended_date,
                timestamp=timestamp_str,
                stock_data=stock_data,
                clamped_max=clamped_max,
                warning="OpenAI API key not configured. Candidate scanning is paused."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json"
        }

        user_content = json.dumps({
            "run_type": run_type,
            "intended_trading_date": intended_date,
            "max_candidates": clamped_max,
            "market_context": market_context,
            "shortlisted_stocks": stock_data
        }, indent=2)

        prompt_text = SYSTEM_PROMPT.format(
            max_candidates=clamped_max,
            market_telemetry_json=user_content
        )

        payload = {
            "model": self.model_name or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": "Analyze the market telemetry data and output strictly valid JSON matching the schema."}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as resp:
                    latency = round((time.time() - start_time) * 1000, 2)
                    if resp.status == 200:
                        raw = await resp.json()
                        content = raw["choices"][0]["message"]["content"]
                        parsed = json.loads(content)
                        return self._parse_json_result(
                            parsed=parsed,
                            run_id=run_id,
                            run_type=run_type,
                            intended_date=intended_date,
                            timestamp=timestamp_str,
                            latency=latency,
                            clamped_max=clamped_max,
                            total_evaluated=len(stock_data)
                        )
                    elif resp.status == 429:
                        logger.warning("[AI_OPENAI] Rate limit exceeded (HTTP 429).")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "OpenAI rate limit exceeded (429). Try again shortly.")
                    elif resp.status in (401, 403):
                        logger.error(f"[AI_OPENAI] Authentication failure (HTTP {resp.status}).")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "Invalid or unauthorized OpenAI API key.")
                    else:
                        err_text = await resp.text()
                        logger.error(f"[AI_OPENAI] API Error {resp.status}: {err_text}")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"OpenAI API error {resp.status}")

        except aiohttp.ClientConnectorError as e:
            latency = round((time.time() - start_time) * 1000, 2)
            logger.error(f"[AI_OPENAI] Network connection failure: {e}")
            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"Network error connecting to OpenAI: {e}")
        except Exception as e:
            latency = round((time.time() - start_time) * 1000, 2)
            logger.error(f"[AI_OPENAI] Unexpected exception during OpenAI analysis: {e}")
            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"OpenAI exception: {str(e)}")

    def _parse_json_result(
        self,
        parsed: Any,
        run_id: str,
        run_type: str,
        intended_date: str,
        timestamp: str,
        latency: float,
        clamped_max: int,
        total_evaluated: int
    ) -> AIAnalysisResponse:
        warnings = []
        raw_candidates: List[Any] = []
        market_summary = "Market research completed."
        no_trade_reason = None

        if isinstance(parsed, list):
            raw_candidates = parsed
            market_summary = f"Identified {len(raw_candidates)} high-probability F&O setup(s)."
        elif isinstance(parsed, dict):
            for key in ("setups", "candidates", "trade_setups", "stocks", "shortlisted_stocks", "shortlisted", "data"):
                val = parsed.get(key)
                if isinstance(val, list) and len(val) > 0:
                    raw_candidates = val
                    break
            market_summary = parsed.get("market_regime") or parsed.get("market_summary") or parsed.get("execution_notes") or market_summary
            no_trade_reason = parsed.get("no_trade_reason")

        valid_candidates: List[StockCandidatePlan] = []
        seen_symbols = set()

        for c in raw_candidates:
            if not isinstance(c, dict):
                continue
            sym = str(c.get("symbol") or c.get("stock") or c.get("ticker") or "").strip().upper()
            if not sym or sym in seen_symbols:
                continue
            seen_symbols.add(sym)
            try:
                candidate_obj = normalize_candidate(c)
                valid_candidates.append(candidate_obj)
            except Exception as e:
                warnings.append(f"Validation failure for candidate {sym}: {e}")

        # Enforce strict candidate count limit
        if len(valid_candidates) > clamped_max:
            warnings.append(f"AI returned {len(valid_candidates)} candidates; clamped to maximum {clamped_max}.")
            valid_candidates = valid_candidates[:clamped_max]

        if not valid_candidates and not no_trade_reason:
            no_trade_reason = "No qualified high-probability setups identified by AI under current market conditions."

        return AIAnalysisResponse(
            run_id=run_id,
            run_type=run_type,
            timestamp=timestamp,
            intended_trading_date=intended_date,
            provider="OpenAI",
            model=self.model_name or "gpt-4o-mini",
            market_summary=market_summary,
            total_evaluated=total_evaluated,
            total_shortlisted=len(valid_candidates),
            candidates=valid_candidates,
            no_trade_reason=no_trade_reason,
            latency_ms=latency,
            validation_warnings=warnings
        )

    def _build_error_response(self, run_id, run_type, timestamp, intended_date, latency, error_msg) -> AIAnalysisResponse:
        return AIAnalysisResponse(
            run_id=run_id,
            run_type=run_type,
            timestamp=timestamp,
            intended_trading_date=intended_date,
            provider="OpenAI",
            model=self.model_name or "gpt-4o-mini",
            market_summary=f"Analysis aborted due to error: {error_msg}",
            total_evaluated=0,
            total_shortlisted=0,
            candidates=[],
            no_trade_reason=error_msg,
            latency_ms=latency,
            validation_warnings=[error_msg]
        )

    def _build_offline_response(
        self,
        run_id: str,
        run_type: str,
        intended_date: str,
        timestamp: str,
        stock_data: List[Dict[str, Any]],
        clamped_max: int,
        warning: str
    ) -> AIAnalysisResponse:
        """Returns zero candidates and a clear warning when API key is not configured. Dummy data generation strictly disabled."""
        msg = "AI Research Provider (OpenAI) is not connected. API key is missing or not configured."
        return AIAnalysisResponse(
            run_id=run_id,
            run_type=run_type,
            timestamp=timestamp,
            intended_trading_date=intended_date,
            provider="OpenAI",
            model=self.model_name or "gpt-4o-mini",
            market_summary="OpenAI is not connected. Real-time scanning and trade candidate generation are paused until a valid API key is entered.",
            total_evaluated=len(stock_data),
            total_shortlisted=0,
            candidates=[],
            no_trade_reason=msg,
            latency_ms=0.0,
            validation_warnings=[warning or msg]
        )


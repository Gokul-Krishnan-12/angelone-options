"""
Google Gemini Integration Provider.
Implements structured JSON generation via Gemini REST API.
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


SYSTEM_INSTRUCTION = """You are an institutional quantitative derivatives analyst focusing on NSE India F&O equities.

You are provided with pre-screened market telemetry for the top momentum stocks today, including live spot prices, intraday VWAP status, Open Interest (OI) buildup, ATM option chain quotes, and breaking news/sentiment data.

### INPUT DATA:
{market_telemetry_json}

### OBJECTIVE:
Select AT MOST {max_candidates} high-probability intraday option setups where technical price action, OI positioning, and news sentiment exhibit strict confluence.

### EVALUATION CRITERIA:
1. Confluence Verification & News/Catalyst Filtering:
   - Review each stock's `news_headline`, `breaking_news_sentiment`, and `corporate_events`.
   - Bullish (CE): Spot trading above VWAP, positive price change accompanied by fresh OI addition (Long Buildup), and catalyst/neutral-to-positive news sentiment.
   - Bearish (PE): Spot trading below VWAP, negative price change with fresh OI addition (Short Buildup), and negative catalyst.
   - Filter Out: Strictly avoid stocks with upcoming earnings announcements today (IV crush risk) or those where technical bias clashes with news sentiment.
2. Adaptive Risk-Reward & Contract Precision:
   - Select strictly from the provided active strike contracts in the input data. Do not invent strikes or prices.
   - Entry Condition: Define exact spot confirmation level (e.g., Breakout above Session High / VWAP Reclaim) rather than blind market orders.
   - Invalidation (Stop Loss): Option premium SL (max 15% risk).
   - Target Calculation (Adaptive R:R):
     * For HIGH_BETA stocks (beta_profile == "HIGH_BETA"): Set Target 1 with a strict 1:2.0 Risk:Reward (2R Target). Set "risk_reward_ratio": "1:2.0".
     * For STANDARD large-caps: Set Target 1 with a 1:1.5 Risk:Reward (1.5R Target). Set "risk_reward_ratio": "1:1.5".

### OUTPUT FORMAT:
Output strictly valid JSON with no markdown formatting or commentary outside the JSON block:

{{
  "timestamp": "<ISO timestamp>",
  "market_regime": "Trending Bullish | Trending Bearish | Rangebound",
  "setups": [
    {{
      "symbol": "TICKER",
      "direction": "BULLISH | BEARISH",
      "catalyst_summary": "1-2 sentence breakdown of news + OI confluence",
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


class GeminiProvider(AIProvider):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    async def analyze_market(
        self,
        run_type: str,
        intended_date: str,
        stock_data: List[Dict[str, Any]],
        market_context: Dict[str, Any],
        max_candidates: int = 3
    ) -> AIAnalysisResponse:
        clamped_max = min(3, max(1, max_candidates))
        run_id = f"GEM_{int(time.time() * 1000)}"
        start_time = time.time()
        timestamp_str = datetime.now().isoformat()
        # Map legacy/deprecated model names to modern active 2026 Gemini models
        model_name = self.model_name or "gemini-3-flash-preview"
        if model_name in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "default"):
            model_name = "gemini-3-flash-preview"
        elif model_name in ("gemini-1.5-pro", "gemini-2.0-pro"):
            model_name = "gemini-3.1-pro-preview"

        if not self.api_key or self.api_key.strip() in ("", "YOUR_GEMINI_API_KEY", "dummy"):
            return self._build_offline_response(
                run_id=run_id,
                run_type=run_type,
                intended_date=intended_date,
                timestamp=timestamp_str,
                stock_data=stock_data,
                clamped_max=clamped_max,
                warning="Google Gemini API key not configured. Candidate scanning is paused."
            )

        endpoint = f"{self.BASE_URL.format(model=model_name)}?key={self.api_key.strip()}"

        user_content = json.dumps({
            "run_type": run_type,
            "intended_trading_date": intended_date,
            "max_candidates": clamped_max,
            "market_context": market_context,
            "shortlisted_stocks": stock_data
        }, indent=2)

        prompt_text = SYSTEM_INSTRUCTION.format(
            max_candidates=clamped_max,
            market_telemetry_json=user_content
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_seconds)
                ) as resp:
                    latency = round((time.time() - start_time) * 1000, 2)
                    if resp.status == 200:
                        raw = await resp.json()
                        candidates_parts = raw.get("candidates", [])
                        if not candidates_parts:
                            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "Empty response from Gemini.")

                        content_text = candidates_parts[0]["content"]["parts"][0]["text"]
                        clean_text = content_text.strip()
                        if clean_text.startswith("```"):
                            parts = clean_text.split("```")
                            clean_text = parts[1] if len(parts) > 1 else clean_text
                            if clean_text.startswith("json"):
                                clean_text = clean_text[4:]
                            clean_text = clean_text.strip()
                        if clean_text.endswith("```"):
                            clean_text = clean_text[:-3].strip()

                        parsed = json.loads(clean_text)
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
                        logger.warning("[AI_GEMINI] Gemini rate limit exceeded (HTTP 429).")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "Gemini rate limit exceeded. Retrying shortly.")
                    elif resp.status in (400, 403):
                        logger.error(f"[AI_GEMINI] Gemini API key or request error (HTTP {resp.status}).")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "Invalid Gemini API key or request rejected.")
                    else:
                        err_text = await resp.text()
                        logger.error(f"[AI_GEMINI] Error HTTP {resp.status}: {err_text}")
                        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"Gemini error {resp.status}")

        except aiohttp.ClientConnectorError as e:
            latency = round((time.time() - start_time) * 1000, 2)
            logger.error(f"[AI_GEMINI] Network connection error: {e}")
            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"Network error: {e}")
        except Exception as e:
            latency = round((time.time() - start_time) * 1000, 2)
            logger.error(f"[AI_GEMINI] Exception during Gemini analysis: {e}")
            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"Gemini exception: {str(e)}")

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
        market_summary = "Gemini market research completed."
        no_trade_reason = None

        if isinstance(parsed, list):
            raw_candidates = parsed
            market_summary = f"Identified {len(raw_candidates)} high-probability F&O setup(s)."
        elif isinstance(parsed, dict):
            # Inspect multiple potential candidate container keys
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
            provider="Google Gemini",
            model=self.model_name or "gemini-3-flash-preview",
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
            provider="Google Gemini",
            model=self.model_name or "gemini-1.5-flash",
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
        msg = "AI Research Provider (Google Gemini) is not connected. API key is missing or not configured."
        return AIAnalysisResponse(
            run_id=run_id,
            run_type=run_type,
            timestamp=timestamp,
            intended_trading_date=intended_date,
            provider="Google Gemini",
            model=self.model_name or "gemini-1.5-flash",
            market_summary="Google Gemini is not connected. Real-time scanning and trade candidate generation are paused until a valid API key is entered.",
            total_evaluated=len(stock_data),
            total_shortlisted=0,
            candidates=[],
            no_trade_reason=msg,
            latency_ms=0.0,
            validation_warnings=[warning or msg]
        )


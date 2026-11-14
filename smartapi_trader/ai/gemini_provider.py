"""
Google Gemini Integration Provider.
Implements structured JSON generation via Gemini REST API.
"""

import time
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.ai.provider_base import (
    AIProvider, AIAnalysisResponse, StockCandidatePlan, normalize_candidate
)
from smartapi_trader.utils.logger import logger


SYSTEM_INSTRUCTION = """You are an institutional quantitative equity and derivatives portfolio manager focusing on NSE India F&O equities.
Your primary fiduciary mandate is CAPITAL PRESERVATION. Consistent trading profitability comes from high win-rate, asymmetric Risk:Reward setups (1:2.0 to 1:3.0+), NOT from forced frequent trading. In institutional trading, CASH IS A POSITION.

### INPUT DATA:
{market_telemetry_json}

### EVALUATION CRITERIA & HIERARCHY:

1. MACRO REGIME ALIGNMENT (ABSOLUTE GATEKEEPER):
   - First, inspect `market_context.macro_nifty` and `market_context.market_regime`.
   - If NIFTY is in a BEARISH DOWNTREND (Spot < VWAP & Open):
     -> STRICTLY DISQUALIFY all Bullish Call (CE) setups across ALL stocks.
     -> You may ONLY recommend Bearish Put (PE) setups in stocks with confirmed breakdown or rejection structures.
   - If NIFTY is in a BULLISH UPTREND (Spot > VWAP & Open):
     -> STRICTLY DISQUALIFY all Bearish Put (PE) setups.
     -> You may ONLY recommend Bullish Call (CE) setups in stocks with confirmed breakout structures.
   - If NIFTY is NEUTRAL / CONSOLIDATION / CHOPPY:
     -> Be ultra-defensive. If no stock exhibits an undeniable, isolated institutional catalyst, return an EMPTY candidate list `[]` with your exact no-trade rationale.

2. ASYMMETRIC ENTRY MECHANICS: PULLBACKS & BASES OVER PARABOLIC CHASES:
   - FORBIDDEN: Do NOT chase stocks that are already extended > 1.2% away from VWAP or trading at parabolic session highs.
   - PREFERRED HIGH-EXPECTANCY SETUPS:
     a) Bullish VWAP / 20 EMA Pullback: Stock in strong uptrend pulled back to test VWAP/support and formed a bullish reversal pin-bar or base within 0.2% - 0.7% of VWAP.
     b) Bearish VWAP / 20 EMA Pullback: Stock in downtrend rallied into VWAP/overhead resistance and formed a rejection structure.
     c) Fresh Horizontal Base Breakout: Tight multi-hour base breaking with institutional volume > 1.2x SMA.

3. OPTION CONTRACT SELECTION & MATHEMATICAL INTEGRITY:
   - Select strictly from the active strike contracts provided in the input data. Do not invent strikes or prices.
   - Target minimum 1:2.0 to 1:2.5 Risk-to-Reward ratio (e.g. Stop-Loss ~12% below entry, Target 1 at least 2x the risk).
   - "confidence_score": Assign an honest institutional confidence rating from 1.0 to 10.0 (e.g. 8.5, 9.2).
     -> Only score >= 8.5 if Macro, Sector, Technical Structure, and Volume are 100% in confluence.
     -> Any setup with mixed signals, sector divergence, or counter-trend risk MUST be scored <= 7.0 or discarded.

4. EMPOWERMENT TO SELECT ZERO TRADES:
   - If market conditions are choppy, volume is low, or risk-reward is suboptimal, return `setups: []` and state the exact reasons in `no_trade_reason`. Select AT MOST {max_candidates} candidates.

### OUTPUT FORMAT:
Output strictly valid JSON with no markdown formatting or commentary outside the JSON block:

{{
  "timestamp": "<ISO timestamp>",
  "market_regime": "Trending Bullish | Trending Bearish | Rangebound Chop",
  "no_trade_reason": null,
  "setups": [
    {{
      "symbol": "TICKER",
      "direction": "BULLISH | BEARISH",
      "catalyst_summary": "1-2 sentence breakdown of technical structure + macro/sector confluence",
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
        "risk_reward_ratio": "1:2.0"
      }},
      "confidence_score": "8.5-10.0"
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
        primary_model = self.model_name or "gemini-3.5-flash"
        if primary_model in ("gemini-1.5-flash", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest", "default"):
            primary_model = "gemini-3.5-flash"
        elif primary_model in ("gemini-1.5-pro", "gemini-2.0-pro", "gemini-2.5-pro"):
            primary_model = "gemini-3.1-pro-preview"

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

        # Resilient model fallback cascade: verified high-availability active flash endpoints
        models_to_try = [primary_model]
        for fallback in [
            "gemini-flash-lite-latest",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite",
        ]:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error_msg = "Unknown Gemini error."
        last_model_used = primary_model

        try:
            async with aiohttp.ClientSession() as session:
                for current_model in models_to_try:
                    last_model_used = current_model
                    endpoint = f"{self.BASE_URL.format(model=current_model)}?key={self.api_key.strip()}"

                    # Up to 2 attempts per model for transient demand spikes (503) or rate limits (429)
                    for attempt in range(1, 3):
                        try:
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
                                        last_error_msg = f"Empty response from Gemini ({current_model})."
                                        break

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
                                        total_evaluated=len(stock_data),
                                        model_name=current_model
                                    )
                                elif resp.status in (400, 403):
                                    logger.error(f"[AI_GEMINI] Gemini API key or request error (HTTP {resp.status}).")
                                    return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, "Invalid Gemini API key or request rejected.", current_model)
                                elif resp.status in (429, 503):
                                    err_text = await resp.text()
                                    reason = "high demand (HTTP 503)" if resp.status == 503 else "rate limit (HTTP 429)"
                                    logger.warning(f"[AI_GEMINI] Model {current_model} returned {reason} on attempt {attempt}/2.")
                                    last_error_msg = f"Gemini {current_model} {reason}."
                                    if attempt < 2:
                                        await asyncio.sleep(1.5)
                                        continue
                                    else:
                                        logger.info(f"[AI_GEMINI] Falling back from {current_model} to next model in chain...")
                                        break
                                elif resp.status == 404:
                                    logger.warning(f"[AI_GEMINI] Model {current_model} not found (HTTP 404). Falling back...")
                                    last_error_msg = f"Model {current_model} unavailable."
                                    break
                                else:
                                    err_text = await resp.text()
                                    logger.error(f"[AI_GEMINI] Error HTTP {resp.status} on {current_model}: {err_text}")
                                    last_error_msg = f"Gemini error {resp.status}"
                                    break

                        except asyncio.TimeoutError:
                            logger.warning(f"[AI_GEMINI] Timeout on {current_model} (attempt {attempt}/2).")
                            last_error_msg = f"Timeout on {current_model}"
                            if attempt < 2:
                                await asyncio.sleep(1.0)
                                continue
                            break
                        except aiohttp.ClientConnectorError as e:
                            logger.error(f"[AI_GEMINI] Network connection error on {current_model}: {e}")
                            last_error_msg = f"Network connection error: {e}"
                            break

        except Exception as e:
            latency = round((time.time() - start_time) * 1000, 2)
            logger.error(f"[AI_GEMINI] Exception during Gemini analysis: {e}")
            return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, f"Gemini exception: {str(e)}", last_model_used)

        latency = round((time.time() - start_time) * 1000, 2)
        return self._build_error_response(run_id, run_type, timestamp_str, intended_date, latency, last_error_msg, last_model_used)

    def _parse_json_result(
        self,
        parsed: Any,
        run_id: str,
        run_type: str,
        intended_date: str,
        timestamp: str,
        latency: float,
        clamped_max: int,
        total_evaluated: int,
        model_name: Optional[str] = None
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
            model=model_name or self.model_name or "gemini-3-flash-preview",
            market_summary=market_summary,
            total_evaluated=total_evaluated,
            total_shortlisted=len(valid_candidates),
            candidates=valid_candidates,
            no_trade_reason=no_trade_reason,
            latency_ms=latency,
            validation_warnings=warnings
        )

    def _build_error_response(self, run_id, run_type, timestamp, intended_date, latency, error_msg, model_name: Optional[str] = None) -> AIAnalysisResponse:
        return AIAnalysisResponse(
            run_id=run_id,
            run_type=run_type,
            timestamp=timestamp,
            intended_trading_date=intended_date,
            provider="Google Gemini",
            model=model_name or self.model_name or "gemini-3-flash-preview",
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
            model=self.model_name or "gemini-3-flash-preview",
            market_summary="Google Gemini is not connected. Real-time scanning and trade candidate generation are paused until a valid API key is entered.",
            total_evaluated=len(stock_data),
            total_shortlisted=0,
            candidates=[],
            no_trade_reason=msg,
            latency_ms=0.0,
            validation_warnings=[warning or msg]
        )


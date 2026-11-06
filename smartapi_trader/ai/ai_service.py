"""
Central AI Orchestration Service.
Factory for OpenAI & Gemini providers with strict backend candidate capping,
secure credential management, and symbol deduplication.
"""

import os
from typing import Dict, Any, List, Optional
from smartapi_trader.ai.provider_base import AIProvider, AIAnalysisResponse
from smartapi_trader.ai.openai_provider import OpenAIProvider
from smartapi_trader.ai.gemini_provider import GeminiProvider
from smartapi_trader.utils.logger import logger


class AIService:
    """
    Unified AI service layer with hard backend limits on candidates.
    Guarantees no more than 3 distinct stock candidates per run.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.active_provider_name = self.config.get("provider", "OPENAI").upper()
        self.active_model = self.config.get("model", "gpt-4o-mini")
        self.timeout_seconds = int(self.config.get("timeout_seconds", 30))

        # Securely resolve API keys from config or environment variables
        self.openai_key = self.config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.gemini_key = self.config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")

    def update_credentials(
        self,
        provider: str,
        model: Optional[str] = None,
        openai_key: Optional[str] = None,
        gemini_key: Optional[str] = None
    ):
        """Updates runtime AI configuration without leaking secrets."""
        if provider:
            self.active_provider_name = provider.upper()
        if model:
            self.active_model = model
        if openai_key is not None:
            self.openai_key = openai_key.strip()
        if gemini_key is not None:
            self.gemini_key = gemini_key.strip()
        logger.info(f"[AI_SERVICE] Updated provider to {self.active_provider_name} with model {self.active_model}")

    @property
    def is_configured(self) -> bool:
        """Returns True if the active provider has a valid non-dummy API key configured."""
        prov = self.active_provider_name.upper()
        if prov == "GEMINI" or "GEMINI" in prov:
            return bool(self.gemini_key and len(self.gemini_key.strip()) > 5 and self.gemini_key.strip() not in ("YOUR_GEMINI_API_KEY", "dummy"))
        return bool(self.openai_key and len(self.openai_key.strip()) > 5 and self.openai_key.strip() not in ("YOUR_OPENAI_API_KEY", "dummy"))

    def is_provider_configured(self, provider: Optional[str] = None) -> bool:
        prov = (provider or self.active_provider_name).upper()
        if prov == "GEMINI" or "GEMINI" in prov:
            return bool(self.gemini_key and len(self.gemini_key.strip()) > 5 and self.gemini_key.strip() not in ("YOUR_GEMINI_API_KEY", "dummy"))
        return bool(self.openai_key and len(self.openai_key.strip()) > 5 and self.openai_key.strip() not in ("YOUR_OPENAI_API_KEY", "dummy"))

    def get_masked_config(self) -> Dict[str, Any]:
        """Returns safe configuration metadata for UI rendering."""
        def mask(k: str) -> str:
            if not k or len(k.strip()) < 8:
                return "Configured" if (k and len(k.strip()) > 5 and k.strip() not in ("YOUR_OPENAI_API_KEY", "YOUR_GEMINI_API_KEY", "dummy")) else "Not Configured"
            return f"{k[:4]}...{k[-4:]}"

        return {
            "provider": self.active_provider_name,
            "model": self.active_model,
            "openai_configured": bool(self.openai_key and len(self.openai_key.strip()) > 5 and self.openai_key.strip() not in ("YOUR_OPENAI_API_KEY", "dummy")),
            "gemini_configured": bool(self.gemini_key and len(self.gemini_key.strip()) > 5 and self.gemini_key.strip() not in ("YOUR_GEMINI_API_KEY", "dummy")),
            "is_active_configured": self.is_configured,
            "openai_key_preview": mask(self.openai_key),
            "gemini_key_preview": mask(self.gemini_key),
            "timeout_seconds": self.timeout_seconds,
            "max_candidates_cap": 3
        }

    def _get_provider_instance(self, override_provider: Optional[str] = None, override_model: Optional[str] = None) -> AIProvider:
        prov = (override_provider or self.active_provider_name).upper()
        mod = override_model or self.active_model

        if prov == "GEMINI" or "GEMINI" in prov:
            return GeminiProvider(
                api_key=self.gemini_key,
                model_name=mod or "gemini-3-flash-preview",
                timeout_seconds=self.timeout_seconds
            )
        else:
            return OpenAIProvider(
                api_key=self.openai_key,
                model_name=mod or "gpt-4o-mini",
                timeout_seconds=self.timeout_seconds
            )

    async def analyze(
        self,
        run_type: str,
        intended_date: str,
        stock_data: List[Dict[str, Any]],
        market_context: Dict[str, Any],
        max_candidates: int = 3,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> AIAnalysisResponse:
        """
        Executes analysis with HARD backend cap:
        - max_candidates clamped strictly between 1 and 3 (default 3).
        - AI is NOT forced to return 3.
        - Deduplicates underlying symbols.
        """
        # Hard backend cap: Never allow configured max to exceed 3
        clamped_max = min(3, max(1, int(max_candidates)))

        provider_inst = self._get_provider_instance(provider, model)
        response = await provider_inst.analyze_market(
            run_type=run_type,
            intended_date=intended_date,
            stock_data=stock_data,
            market_context=market_context,
            max_candidates=clamped_max
        )

        # Secondary Backend Defense: Deduplicate and enforce max candidate count
        unique_candidates = []
        seen_symbols = set()
        for cand in response.candidates:
            sym = cand.symbol.upper().strip()
            if sym not in seen_symbols:
                seen_symbols.add(sym)
                unique_candidates.append(cand)
            else:
                response.validation_warnings.append(f"Backend filtered duplicate candidate symbol: {sym}")

        if len(unique_candidates) > clamped_max:
            response.validation_warnings.append(
                f"Backend enforced candidate limit: trimmed from {len(unique_candidates)} to {clamped_max} top candidates."
            )
            unique_candidates = unique_candidates[:clamped_max]

        response.candidates = unique_candidates
        response.total_shortlisted = len(unique_candidates)

        if not unique_candidates and not response.no_trade_reason:
            response.no_trade_reason = "No qualified trade setups identified; capital preserved."

        logger.info(
            f"[AI_SERVICE] Completed {run_type} via {response.provider} ({response.model}). "
            f"Returned {len(response.candidates)} candidates (Max allowed: {clamped_max})."
        )
        return response

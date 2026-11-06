"""
AI Integration Layer.
Supports OpenAI and Google Gemini with typed recommendation schemas
and backend candidate limits.
"""

from smartapi_trader.ai.provider_base import (
    AIProvider,
    AIAnalysisResponse,
    StockCandidatePlan,
    OptionContractPlan,
    TechnicalSetup,
    TradeManagement
)
from smartapi_trader.ai.openai_provider import OpenAIProvider
from smartapi_trader.ai.gemini_provider import GeminiProvider
from smartapi_trader.ai.ai_service import AIService

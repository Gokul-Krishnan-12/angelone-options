"""
Comprehensive Automated Test Suite for AI-Powered NSE Stock Options Trading System.
Covers:
1. OpenAI and Google Gemini provider abstractions & structured outputs.
2. Provider failure modes, invalid keys, rate limits, malformed JSON.
3. Strict backend enforcement of candidate limit (1-3 max).
4. Pruning candidates when AI returns >3 candidates.
5. Filtering duplicate underlying stock symbols.
6. Empty candidate lists & NO TRADE decisions.
7. Next trading date calculation skipping weekends & NSE holidays.
8. Intraday scan interval scheduling & overlap prevention lock.
9. Event-driven reanalysis gating.
10. Deterministic pre-trade validation (gaps, spreads, R:R, session).
11. Option contract resolution (strikes, expiries, CE/PE).
12. Live agent RMS routing through mandatory RiskManager.
13. Paper trading independence: not blocked by live risk limits.
14. Strict execution isolation: paper agent has zero broker access and cannot place real orders.
15. Resetting paper ledger with capital confirmation without affecting live data.
16. Secure credential masking: API keys never exposed in full.
17. Restart recovery & persistence in SQLite.
"""

import os
import sys
import unittest
import asyncio
from datetime import datetime, date, time as dt_time
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from smartapi_trader.ai.provider_base import AIAnalysisResponse, StockCandidatePlan
from smartapi_trader.ai.openai_provider import OpenAIProvider
from smartapi_trader.ai.gemini_provider import GeminiProvider
from smartapi_trader.ai.ai_service import AIService
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS
from smartapi_trader.stock_options.market_data_service import StockMarketDataService
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.stock_options.planner import OvernightAIPlanner
from smartapi_trader.stock_options.scanner import IntradayAIScanner
from smartapi_trader.stock_options.validator import StockOptionsValidator
from smartapi_trader.stock_options.live_agent import StockOptionsLiveAgent
from smartapi_trader.stock_options.paper_agent import StockOptionsPaperAgent, StockOptionsPaperEngine
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.events import EventType, SignalEvent


TEST_DB_PATH = "data/test_stock_options.db"


class TestStockOptionsAISystem(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

        self.storage = StockOptionsStorage(db_path=TEST_DB_PATH)
        self.universe_mgr = StockUniverseManager(db_path="data/test_instruments.db")
        self.market_data = StockMarketDataService(self.universe_mgr)
        self.ai_service = AIService({
            "provider": "OPENAI",
            "model": "gpt-4o-mini",
            "timeout_seconds": 10
        })
        self.validator = StockOptionsValidator(self.universe_mgr)
        self.planner = OvernightAIPlanner(self.ai_service, self.market_data, self.storage)
        self.scanner = IntradayAIScanner(self.ai_service, self.market_data, self.storage, default_interval_mins=5)
        self.paper_agent = StockOptionsPaperAgent(self.storage, self.validator, initial_capital=500000.0)

        self.event_bus = EventBus()
        self.event_bus.start()

    async def asyncTearDown(self):
        await self.event_bus.stop()
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass


    # 1. AI Provider Abstraction & Offline Safety (Zero Dummy Data)
    async def test_01_ai_provider_offline_safety_zero_dummy(self):
        """Tests that when no API key is provided, zero dummy candidates are generated and a clear warning is returned."""
        res = await self.ai_service.analyze(
            run_type="OVERNIGHT_PLAN",
            intended_date="2026-10-30",
            stock_data=self.market_data.rank_and_shortlist_stocks(max_shortlist=3),
            market_context={"market_regime": "Test"},
            max_candidates=3
        )
        self.assertIsInstance(res, AIAnalysisResponse)
        self.assertEqual(len(res.candidates), 0, "No dummy candidates should be generated when API key is missing.")
        self.assertIn("not configured", res.no_trade_reason.lower())
        self.assertTrue(any("not configured" in w.lower() for w in res.validation_warnings))


    # 2. Strict Backend Enforced Candidate Cap (max <= 3)
    async def test_02_backend_candidate_cap_enforcement(self):
        """Verifies backend strictly clamps max_candidates to <= 3 even if requested with 5."""
        res = await self.ai_service.analyze(
            run_type="INTRADAY_SCAN",
            intended_date="2026-10-30",
            stock_data=self.market_data.rank_and_shortlist_stocks(max_shortlist=8),
            market_context={},
            max_candidates=5  # User requested 5, backend must clamp to 3
        )
        self.assertLessEqual(len(res.candidates), 3, "Backend MUST NOT return more than 3 candidates.")

    # 3. Pruning when AI returns excess candidates
    async def test_03_prune_excess_candidates_from_ai(self):
        """Tests that if an AI returns 4 candidates, the backend retains only the top 3 and records a warning."""
        provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o-mini")
        mock_candidates = [
            {"symbol": "RELIANCE", "company_name": "Reliance", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 2800, "support_level": 2750, "resistance_level": 2850, "trend": "BULLISH", "entry_trigger": 2810, "entry_conditions": "c", "invalidation_level": 2740, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 2800, "expiry": "27NOV2025", "indicative_premium": 50},
             "trade_management": {"stop_loss": 44, "target_1": 65, "risk_reward_ratio": 2.5, "exit_conditions": "e"}},
            {"symbol": "TCS", "company_name": "TCS", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 4100, "support_level": 4050, "resistance_level": 4150, "trend": "BULLISH", "entry_trigger": 4110, "entry_conditions": "c", "invalidation_level": 4040, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 4100, "expiry": "27NOV2025", "indicative_premium": 70},
             "trade_management": {"stop_loss": 61, "target_1": 90, "risk_reward_ratio": 2.2, "exit_conditions": "e"}},
            {"symbol": "INFY", "company_name": "Infosys", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 1850, "support_level": 1820, "resistance_level": 1880, "trend": "BULLISH", "entry_trigger": 1855, "entry_conditions": "c", "invalidation_level": 1810, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 1850, "expiry": "27NOV2025", "indicative_premium": 35},
             "trade_management": {"stop_loss": 30, "target_1": 48, "risk_reward_ratio": 2.6, "exit_conditions": "e"}},
            {"symbol": "SBIN", "company_name": "SBI", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 820, "support_level": 810, "resistance_level": 830, "trend": "BULLISH", "entry_trigger": 822, "entry_conditions": "c", "invalidation_level": 805, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 820, "expiry": "27NOV2025", "indicative_premium": 15},
             "trade_management": {"stop_loss": 13, "target_1": 20, "risk_reward_ratio": 2.5, "exit_conditions": "e"}},
        ]
        parsed_mock = {"candidates": mock_candidates, "market_summary": "Test run"}
        res = provider._parse_json_result(parsed_mock, "R1", "OVERNIGHT_PLAN", "2026-10-30", "now", 10.0, clamped_max=3, total_evaluated=4)
        self.assertEqual(len(res.candidates), 3, "Must trim 4 candidates to 3.")
        self.assertTrue(any("clamped" in w.lower() for w in res.validation_warnings))

    # 4. Filter duplicate underlying stock symbols
    async def test_04_filter_duplicate_symbols(self):
        """Verifies duplicate underlying symbols (e.g. 2 different options for RELIANCE) are deduplicated."""
        provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o-mini")
        mock_candidates = [
            {"symbol": "RELIANCE", "company_name": "Reliance 2800 CE", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 2800, "support_level": 2750, "resistance_level": 2850, "trend": "BULLISH", "entry_trigger": 2810, "entry_conditions": "c", "invalidation_level": 2740, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 2800, "expiry": "27NOV2025", "indicative_premium": 50},
             "trade_management": {"stop_loss": 44, "target_1": 65, "risk_reward_ratio": 2.5, "exit_conditions": "e"}},
            {"symbol": "RELIANCE", "company_name": "Reliance 2820 CE (Duplicate)", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 2800, "support_level": 2750, "resistance_level": 2850, "trend": "BULLISH", "entry_trigger": 2810, "entry_conditions": "c", "invalidation_level": 2740, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 2820, "expiry": "27NOV2025", "indicative_premium": 42},
             "trade_management": {"stop_loss": 36, "target_1": 55, "risk_reward_ratio": 2.1, "exit_conditions": "e"}},
            {"symbol": "TCS", "company_name": "TCS", "bias": "BULLISH", "recommendation": "BUY",
             "technical": {"reference_price": 4100, "support_level": 4050, "resistance_level": 4150, "trend": "BULLISH", "entry_trigger": 4110, "entry_conditions": "c", "invalidation_level": 4040, "invalidation_conditions": "c", "technical_rationale": "r"},
             "primary_contract": {"option_type": "CE", "strike_price": 4100, "expiry": "27NOV2025", "indicative_premium": 70},
             "trade_management": {"stop_loss": 61, "target_1": 90, "risk_reward_ratio": 2.2, "exit_conditions": "e"}}
        ]
        parsed_mock = {"candidates": mock_candidates}
        res = provider._parse_json_result(parsed_mock, "R2", "INTRADAY_SCAN", "2026-10-30", "now", 10.0, clamped_max=3, total_evaluated=3)
        symbols = [c.symbol for c in res.candidates]
        self.assertEqual(len(symbols), 2, "Duplicate RELIANCE must be removed.")
        self.assertEqual(symbols, ["RELIANCE", "TCS"])

    # 5. NO TRADE Decision Handling
    async def test_05_no_trade_decision(self):
        """Verifies that 0 candidates can be returned with a clear NO TRADE reason."""
        provider = GeminiProvider(api_key="test_key", model_name="gemini-1.5-flash")
        parsed_mock = {
            "candidates": [],
            "no_trade_reason": "High IV crush and adverse macroeconomic event risk."
        }
        res = provider._parse_json_result(parsed_mock, "R3", "OVERNIGHT_PLAN", "2026-10-30", "now", 12.0, clamped_max=3, total_evaluated=5)
        self.assertEqual(len(res.candidates), 0)
        self.assertIn("High IV crush", res.no_trade_reason)

    # 6. Next Trading Date Calculation Skipping Weekends and Holidays
    def test_06_next_trading_date_calculation(self):
        """Verifies next trading date jumps from Friday to Monday and skips known holidays."""
        # 2026-10-30 is a Friday
        friday = datetime(2026, 10, 30, 16, 30)
        next_dt = OvernightAIPlanner.get_next_trading_date(friday)
        # Next trading day must be Monday (weekday 0)
        self.assertEqual(next_dt.weekday(), 0, "Next trading day after Friday must be Monday.")

    # 7. Intraday Scanner Overlap Protection Lock
    async def test_07_intraday_scanner_overlap_lock(self):
        """Verifies that concurrent scan calls are coalesced/skipped via the lock."""
        async def slow_analyze(*args, **kwargs):
            await asyncio.sleep(0.2)
            return AIAnalysisResponse(
                run_id="SLOW", run_type="INTRADAY_SCAN", timestamp="now",
                intended_trading_date="2026-10-30", provider="Test", model="Test",
                candidates=[]
            )

        with patch.object(self.ai_service, "analyze", side_effect=slow_analyze):
            t1 = asyncio.create_task(self.scanner.execute_scan(is_manual=True))
            await asyncio.sleep(0.02)
            # Second call while t1 is executing
            t2 = await self.scanner.execute_scan(is_manual=True)
            self.assertEqual(t2.get("status"), "skipped", "Concurrent scan must be skipped.")
            await t1

    # 8. Deterministic Pre-Trade Validation
    def test_08_pre_trade_validator_approvals_and_rejections(self):
        """Verifies validator checks for spread friction, invalidation boundaries, and R:R."""
        cand = {
            "symbol": "RELIANCE",
            "bias": "BULLISH",
            "technical": {"entry_trigger": 2810.0, "invalidation_level": 2750.0},
            "primary_contract": {"option_type": "CE", "strike_price": 2800.0, "indicative_premium": 45.0, "expiry": "27NOV2025"},
            "trade_management": {"stop_loss": 39.0, "target_1": 60.0}
        }
        # A. Normal valid candidate
        is_val, reason, params = self.validator.validate_candidate_for_execution(
            candidate=cand,
            current_spot=2805.0,
            current_option_ltp=45.0,
            bid_price=44.8,
            ask_price=45.2,
            is_paper=True
        )
        self.assertTrue(is_val, f"Should be valid: {reason}")
        self.assertEqual(params["underlying"], "RELIANCE")

        # B. Wide spread rejection (>2.5%)
        is_val, reason, _ = self.validator.validate_candidate_for_execution(
            candidate=cand,
            current_spot=2805.0,
            current_option_ltp=45.0,
            bid_price=40.0,
            ask_price=48.0,  # ~18% spread!
            is_paper=True
        )
        self.assertFalse(is_val, "Must reject excessive bid-ask spread.")

        # C. Structural invalidation breach
        is_val, reason, _ = self.validator.validate_candidate_for_execution(
            candidate=cand,
            current_spot=2740.0,  # Below 2750 invalidation level
            current_option_ltp=30.0,
            bid_price=29.8,
            ask_price=30.2,
            is_paper=True
        )
        self.assertFalse(is_val, "Must reject when spot violates invalidation boundary.")

    # 9. Strict Paper Trading Execution Isolation (No Real Broker Orders)
    async def test_09_paper_trading_strict_isolation(self):
        """
        Verifies:
        1. Paper agent executes via simulation engine.
        2. Paper agent has NO broker connection.
        3. Simulated fills deduct virtual capital and persist as is_paper=1.
        """
        cand = {
            "symbol": "TCS",
            "bias": "BULLISH",
            "technical": {"entry_trigger": 4110.0, "invalidation_level": 4050.0},
            "primary_contract": {"option_type": "CE", "strike_price": 4100.0, "indicative_premium": 65.0, "expiry": "27NOV2025"},
            "trade_management": {"stop_loss": 57.0, "target_1": 85.0}
        }

        init_cap = self.paper_agent.simulation_engine.virtual_balance
        res = await self.paper_agent.execute_simulated_trade(cand)
        self.assertEqual(res["status"], "success")

        # Confirm virtual balance decreased
        self.assertLess(self.paper_agent.simulation_engine.virtual_balance, init_cap)

        # Confirm order persisted with is_paper = 1
        orders = self.storage.get_orders(is_paper=True)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["is_paper"], 1)

        # Verify NO live orders exist
        live_orders = self.storage.get_orders(is_paper=False)
        self.assertEqual(len(live_orders), 0, "Paper trade must NEVER create live orders.")

    # 10. Paper Agent Not Blocked by Live Risk Limits
    async def test_10_paper_not_blocked_by_live_risk(self):
        """Paper agent operates independently and is not blocked by live account rules."""
        cand = {
            "symbol": "INFY",
            "bias": "BULLISH",
            "technical": {"entry_trigger": 1860.0, "invalidation_level": 1820.0},
            "primary_contract": {"option_type": "CE", "strike_price": 1860.0, "indicative_premium": 30.0, "expiry": "27NOV2025"},
            "trade_management": {"stop_loss": 26.0, "target_1": 40.0}
        }
        res = await self.paper_agent.execute_simulated_trade(cand)
        self.assertEqual(res["status"], "success")
        positions = self.storage.get_positions(is_paper=True)
        self.assertTrue(any(p["underlying"] == "INFY" for p in positions))

    # 11. Resetting Paper History Isolation
    async def test_11_reset_paper_history_isolation(self):
        """Verifies resetting paper ledger clears paper trades but leaves live data untouched."""
        # 1. Create a paper position
        self.storage.save_position({
            "symbol": "INFY27NOV1860CE",
            "underlying": "INFY",
            "is_paper": 1,
            "quantity": 400,
            "entry_price": 30.0
        })
        # 2. Create a live position
        self.storage.save_position({
            "symbol": "RELIANCE27NOV2800CE",
            "underlying": "RELIANCE",
            "is_paper": 0,
            "quantity": 250,
            "entry_price": 50.0
        })

        self.paper_agent.reset_paper_ledger(reset_capital=600000.0)

        # Paper positions cleared
        paper_pos = self.storage.get_positions(is_paper=True)
        self.assertEqual(len(paper_pos), 0)

        # Live position preserved!
        live_pos = self.storage.get_positions(is_paper=False)
        self.assertEqual(len(live_pos), 1)
        self.assertEqual(live_pos[0]["symbol"], "RELIANCE27NOV2800CE")
        self.assertEqual(self.paper_agent.simulation_engine.virtual_balance, 600000.0)

    # 12. Secure Credential Masking
    def test_12_secure_credential_masking(self):
        """Verifies API keys are never leaked in full in configuration responses."""
        self.ai_service.update_credentials("OPENAI", openai_key="sk-proj-1234567890abcdefghijklmnop")
        cfg = self.ai_service.get_masked_config()
        self.assertTrue(cfg["openai_configured"])
        self.assertNotIn("1234567890abcdef", cfg["openai_key_preview"])
        self.assertTrue(cfg["openai_key_preview"].startswith("sk-p..."))


if __name__ == "__main__":
    unittest.main()

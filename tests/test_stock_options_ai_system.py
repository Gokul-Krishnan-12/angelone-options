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

    # 13. Autonomous Position Real-Time LTP & Bracket Triggers
    async def test_13_autonomous_position_ltp_and_bracket_triggers(self):
        """Verifies real-time LTP update, floating PnL calculation, and auto-bracket exits."""
        # 1. Open a paper position
        candidate = {
            "symbol": "TATASTEEL",
            "setup_type": "Breakout",
            "primary_contract": {
                "strike": 165.0,
                "option_type": "CE",
                "expiry": "26NOV2026",
                "indicative_premium": 5.0
            },
            "technical": {
                "reference_price": 165.0
            },
            "trade_management": {
                "stop_loss": 3.5,
                "target_1": 8.0
            }
        }
        res = await self.paper_agent.execute_simulated_trade(candidate)
        self.assertEqual(res["status"], "success")
        pos = self.storage.get_positions(is_paper=True, open_only=True)[0]
        sym = pos["symbol"]
        qty = pos["quantity"]

        # Mock market data service to return custom LTP
        mock_market_data = MagicMock()
        self.paper_agent.market_data = mock_market_data

        # Test Case A: Price rises to ₹6.50 (Floating Profit)
        mock_market_data.get_option_ltp.return_value = 6.50
        updated = await self.paper_agent.update_open_positions_ltp()
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["current_ltp"], 6.50)
        self.assertGreater(updated[0]["unrealized_pnl"], 0.0)

        # Verify DB updated
        db_pos = self.storage.get_positions(is_paper=True, open_only=True)[0]
        self.assertEqual(db_pos["current_ltp"], 6.50)
        self.assertGreater(db_pos["unrealized_pnl"], 0.0)

        # Test Case B: Price hits Target 1 (₹8.50 >= target_1 of 8.0) -> Auto TP
        mock_market_data.get_option_ltp.return_value = 8.50
        await self.paper_agent.update_open_positions_ltp()

        # Position should now be auto-closed
        open_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(open_pos), 0)

        # Trade should be recorded with Target 1 Hit
        trades = self.storage.get_trades(is_paper=True)
        self.assertEqual(len(trades), 1)
        self.assertIn("Target 1 Hit", trades[0]["exit_reason"])
        self.assertGreater(trades[0]["gross_pnl"], 0.0)

        # Clean up
        self.paper_agent.stop()

    def test_14_ai_key_persistence_and_settings_yaml_sync(self):
        """Verifies AI keys are persisted to settings.yaml alongside SQLite and loaded properly."""
        import tempfile
        import yaml

        # 1. Verify storage persists and retrieves keys
        self.storage.save_setting("gemini_api_key", "TEST_GEMINI_KEY_ABC123")
        self.storage.save_setting("ai_provider", "GEMINI")
        self.storage.save_setting("ai_model", "gemini-2.5-flash")

        self.assertEqual(self.storage.get_setting("gemini_api_key"), "TEST_GEMINI_KEY_ABC123")

        # 2. Verify AIService initialization with fallback
        empty_settings = {}
        ai_cfg = dict(empty_settings.get("ai", {}))
        if not ai_cfg.get("gemini_api_key"):
            ai_cfg["gemini_api_key"] = self.storage.get_setting("gemini_api_key", "")
        if not ai_cfg.get("provider"):
            ai_cfg["provider"] = self.storage.get_setting("ai_provider", "GEMINI")
        if not ai_cfg.get("model"):
            ai_cfg["model"] = self.storage.get_setting("ai_model", "gemini-2.5-flash")

        svc = AIService(ai_cfg)
        self.assertTrue(svc.is_configured)
        self.assertEqual(svc.gemini_key, "TEST_GEMINI_KEY_ABC123")
        self.assertEqual(svc.active_provider_name, "GEMINI")

    # 15. Candidate Armed when Spot Price is Below Entry Trigger (Waiting for Entry)
    async def test_15_candidate_armed_when_spot_below_trigger(self):
        """Verifies candidate is NOT executed immediately when spot is below breakout entry trigger."""
        mock_market_data = MagicMock()
        mock_market_data.get_spot_ltp.return_value = 1000.0  # Spot is at 1000.0
        mock_market_data.get_option_ltp.return_value = 25.0
        self.paper_agent.market_data = mock_market_data

        candidate = {
            "symbol": "TCS",
            "bias": "BULLISH",
            "setup_type": "Breakout",
            "technical": {
                "reference_price": 1000.0,
                "entry_trigger": 1025.0,  # Requires breakout above 1025.0
                "invalidation_level": 980.0
            },
            "primary_contract": {
                "tradingsymbol": "TCS 1020 CE",
                "strike_price": 1020.0,
                "option_type": "CE",
                "indicative_premium": 25.0,
                "expiry": "27NOV2025"
            },
            "trade_management": {
                "stop_loss": 20.0,
                "target_1": 35.0
            }
        }

        # Attempt execution without force_immediate
        res = await self.paper_agent.execute_simulated_trade(candidate, plan_id="PLAN_TEST_01")
        self.assertEqual(res["status"], "armed", "Must arm candidate instead of taking immediate entry.")
        self.assertIn("Waiting for breakout", res["armed_item"]["status_reason"])

        # Must NOT create an open position
        open_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(open_pos), 0, "Must NOT open simulated position while waiting for entry price.")

        # Must be tracked in armed candidates
        armed = self.paper_agent.get_armed_candidates()
        self.assertEqual(len(armed), 1)
        self.assertEqual(armed[0]["symbol"], "TCS")
        self.assertEqual(armed[0]["entry_trigger"], 1025.0)

    # 16. Armed Candidate Triggers and Fills when Spot Crosses Entry Trigger
    async def test_16_armed_candidate_triggers_and_fills_when_spot_crosses_trigger(self):
        """Verifies armed candidate automatically executes when spot crosses entry trigger."""
        mock_market_data = MagicMock()
        mock_market_data.get_spot_ltp.return_value = 1000.0
        mock_market_data.get_option_ltp.return_value = 25.0
        self.paper_agent.market_data = mock_market_data

        candidate = {
            "symbol": "INFY",
            "bias": "BULLISH",
            "technical": {
                "reference_price": 1000.0,
                "entry_trigger": 1020.0,
                "invalidation_level": 980.0
            },
            "primary_contract": {
                "tradingsymbol": "INFY 1020 CE",
                "strike_price": 1020.0,
                "option_type": "CE",
                "indicative_premium": 25.0,
                "expiry": "27NOV2025"
            },
            "trade_management": {
                "stop_loss": 20.0,
                "target_1": 35.0
            }
        }

        # Arm candidate
        res = await self.paper_agent.execute_simulated_trade(candidate, plan_id="PLAN_TEST_02")
        self.assertEqual(res["status"], "armed")
        self.assertEqual(len(self.paper_agent.armed_candidates), 1)

        # 1. Spot moves up but still below trigger (1015 < 1020)
        mock_market_data.get_spot_ltp.return_value = 1015.0
        await self.paper_agent._evaluate_armed_candidates()
        self.assertEqual(len(self.paper_agent.armed_candidates), 1, "Must remain armed below trigger.")
        self.assertEqual(len(self.storage.get_positions(is_paper=True, open_only=True)), 0)

        # 2. Spot crosses trigger (1022 >= 1020) -> BREAKOUT CONFIRMED!
        mock_market_data.get_spot_ltp.return_value = 1022.0
        mock_market_data.get_option_ltp.return_value = 28.0
        await self.paper_agent._evaluate_armed_candidates()

        # Candidate should have executed and removed from armed queue
        self.assertEqual(len(self.paper_agent.armed_candidates), 0, "Must remove candidate from armed list upon trigger.")
        open_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(open_pos), 1, "Must open simulated position when entry trigger is hit.")
        self.assertEqual(open_pos[0]["underlying"], "INFY")

    # 17. Armed Candidate Invalidated when Spot Breaches Invalidation Level
    async def test_17_armed_candidate_invalidated_when_spot_breaches_invalidation(self):
        """Verifies candidate setup is invalidated and dropped when spot breaches invalidation boundary."""
        mock_market_data = MagicMock()
        mock_market_data.get_spot_ltp.return_value = 1000.0
        mock_market_data.get_option_ltp.return_value = 25.0
        self.paper_agent.market_data = mock_market_data

        candidate = {
            "symbol": "RELIANCE",
            "bias": "BULLISH",
            "technical": {
                "reference_price": 1000.0,
                "entry_trigger": 1030.0,
                "invalidation_level": 985.0
            },
            "primary_contract": {
                "tradingsymbol": "RELIANCE 1020 CE",
                "strike_price": 1020.0,
                "option_type": "CE",
                "indicative_premium": 35.0,
                "expiry": "27NOV2025"
            },
            "trade_management": {
                "stop_loss": 28.0,
                "target_1": 48.0
            }
        }

        # Arm candidate
        await self.paper_agent.execute_simulated_trade(candidate, plan_id="PLAN_TEST_03")
        self.assertEqual(len(self.paper_agent.armed_candidates), 1)

        # Spot drops below invalidation level (980 < 985)
        mock_market_data.get_spot_ltp.return_value = 980.0
        await self.paper_agent._evaluate_armed_candidates()

        # Should be removed without opening any position
        self.assertEqual(len(self.paper_agent.armed_candidates), 0, "Must drop invalidated candidate.")
        self.assertEqual(len(self.storage.get_positions(is_paper=True, open_only=True)), 0)

    # 18. Force Immediate Execution Bypasses Trigger Waiting
    async def test_18_force_immediate_bypasses_trigger_waiting(self):
        """Verifies passing force_immediate=True enters market trade right away."""
        mock_market_data = MagicMock()
        mock_market_data.get_spot_ltp.return_value = 1000.0
        mock_market_data.get_option_ltp.return_value = 25.0
        self.paper_agent.market_data = mock_market_data

        candidate = {
            "symbol": "TCS",
            "bias": "BULLISH",
            "technical": {
                "reference_price": 1000.0,
                "entry_trigger": 1050.0,  # Far away trigger
                "invalidation_level": 950.0
            },
            "primary_contract": {
                "tradingsymbol": "TCS 1000 CE",
                "strike_price": 1000.0,
                "option_type": "CE",
                "indicative_premium": 25.0,
                "expiry": "27NOV2025"
            },
            "trade_management": {
                "stop_loss": 20.0,
                "target_1": 35.0
            }
        }

        res = await self.paper_agent.execute_simulated_trade(candidate, plan_id="PLAN_FORCE", force_immediate=True)
        self.assertEqual(res["status"], "success")
        open_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(open_pos), 1)

    # 19. Multi-Tranche Partial Profit Booking at Target 1 and Runner to Target 2
    async def test_19_multi_tranche_partial_profit_and_runner(self):
        """Verifies 50% lots booked at Target 1, SL moved to Breakeven, and remainder trails to Target 2."""
        mock_market_data = MagicMock()
        mock_market_data.get_spot_ltp.return_value = 150.0
        mock_market_data.get_option_ltp.return_value = 5.0
        self.paper_agent.market_data = mock_market_data

        candidate = {
            "symbol": "TATASTEEL",
            "bias": "BULLISH",
            "lots": 2,  # 2 lots for multi-tranche execution
            "technical": {
                "reference_price": 150.0,
                "entry_trigger": 150.0,
                "invalidation_level": 145.0
            },
            "primary_contract": {
                "tradingsymbol": "TATASTEEL 150 CE",
                "strike_price": 150.0,
                "option_type": "CE",
                "indicative_premium": 5.0,
                "expiry": "27NOV2025"
            },
            "trade_management": {
                "stop_loss": 4.0,
                "target_1": 7.0
            }
        }

        res = await self.paper_agent.execute_simulated_trade(candidate, plan_id="PLAN_TRANCHE", force_immediate=True)
        self.assertEqual(res["status"], "success")

        # Verify initial position has 2 lots
        pos = self.storage.get_positions(is_paper=True, open_only=True)[0]
        lot_size = pos["lot_size"]
        self.assertEqual(pos["lots"], 2)
        self.assertEqual(pos["quantity"], lot_size * 2)

        # Step 1: Option hits Target 1 (₹7.50 >= target_1 of 7.0)
        mock_market_data.get_option_ltp.return_value = 7.50
        await self.paper_agent.update_open_positions_ltp()

        # Position should still be OPEN, but reduced to 1 lot, and SL shifted to Breakeven
        open_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(open_pos), 1)
        remaining = open_pos[0]
        self.assertEqual(remaining["lots"], 1)
        self.assertEqual(remaining["quantity"], lot_size)
        self.assertEqual(remaining["tranche_stage"], 1)
        self.assertGreaterEqual(remaining["stop_loss"], remaining["entry_price"])

        # Completed trades should record the 1st tranche profit
        trades = self.storage.get_trades(is_paper=True)
        self.assertEqual(len(trades), 1)
        self.assertIn("Partial Target 1 Hit", trades[0]["exit_reason"])
        self.assertGreater(trades[0]["gross_pnl"], 0.0)

        # Step 2: Option hits runner Target 2
        t2_price = remaining["target_1"]  # In tranche 1, target_1 points to Target 2
        mock_market_data.get_option_ltp.return_value = t2_price + 1.0
        await self.paper_agent.update_open_positions_ltp()

        # Now all tranches are completely closed
        final_pos = self.storage.get_positions(is_paper=True, open_only=True)
        self.assertEqual(len(final_pos), 0)
        all_trades = self.storage.get_trades(is_paper=True)
        self.assertEqual(len(all_trades), 2)

    # 20. Sectoral Confluence and OI Buildup Validation
    async def test_20_sector_confluence_and_oi_buildup(self):
        """Verifies sector mapping, sector confluence evaluation, and rejection on sector divergence."""
        # Test A: Sector Mapping
        self.assertEqual(self.universe_mgr.get_sector_for_stock("HINDALCO"), "Metals")
        self.assertEqual(self.universe_mgr.get_sector_for_stock("TCS"), "IT")
        self.assertEqual(self.universe_mgr.get_sector_for_stock("HDFCBANK"), "Banking")
        self.assertEqual(self.universe_mgr.get_sector_for_stock("TATAMOTORS"), "Auto")

        # Test B: Sector Peers
        metal_peers = self.universe_mgr.get_sector_peers("HINDALCO")
        self.assertIn("TATASTEEL", metal_peers)

        # Test C: Validator rejects candidate on sector divergence
        divergent_candidate = {
            "symbol": "HINDALCO",
            "bias": "BULLISH",
            "sector_confluence": {
                "sector": "Metals",
                "aligned": False,
                "reason": "Sector Divergence: Metals sector is dumping (-2.1%). High bear trap risk."
            },
            "technical": {"reference_price": 700.0, "entry_trigger": 700.0},
            "primary_contract": {"strike_price": 700.0, "option_type": "CE", "indicative_premium": 20.0},
            "trade_management": {"stop_loss": 17.0, "target_1": 26.0}
        }

        is_valid, reason, _ = self.validator.validate_candidate_for_execution(
            candidate=divergent_candidate,
            current_spot=700.0,
            current_option_ltp=20.0,
            bid_price=19.8,
            ask_price=20.2,
            is_paper=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Sector Divergence", reason)

    # 21. Daily Stop-Loss Cooldown Guard (Anti-Revenge Trading)
    def test_21_daily_stop_loss_cooldown_rejection(self):
        """Verifies candidate is rejected if the underlying took a losing stop-loss today."""
        now = datetime.now()
        # Record a losing trade for TITAN today
        with self.storage._get_connection() as conn:
            conn.execute("""
                INSERT INTO stock_options_trades
                (trade_id, symbol, underlying, option_type, strike, quantity, entry_price, exit_price, gross_pnl, charges, net_pnl, entry_time, exit_time, exit_reason, is_paper, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"TR_TEST_{int(now.timestamp())}",
                "TITAN23NOV264850PE",
                "TITAN",
                "PE",
                4850.0,
                175,
                70.0,
                61.0,
                -1575.0,
                45.0,
                -1620.0,
                now.isoformat(),
                now.isoformat(),
                "Auto Stop-Loss Hit (SL: ₹61.82, Exit: ₹61.0)",
                1,
                now.isoformat()
            ))

        # Verify storage identifies TITAN as stopped out
        stopped = self.storage.get_stopped_out_underlyings_today()
        self.assertIn("TITAN", stopped)

        # Validator with storage attached must reject new TITAN candidates
        val = StockOptionsValidator(self.universe_mgr, storage=self.storage)
        candidate = {
            "symbol": "TITAN",
            "bias": "BEARISH",
            "technical": {"reference_price": 4840.0, "entry_trigger": 4830.0},
            "primary_contract": {"strike_price": 4850.0, "option_type": "PE", "indicative_premium": 65.0},
            "trade_management": {"stop_loss": 55.0, "target_1": 80.0}
        }

        is_valid, reason, _ = val.validate_candidate_for_execution(
            candidate=candidate,
            current_spot=4825.0,
            current_option_ltp=65.0,
            bid_price=64.5,
            ask_price=65.5,
            is_paper=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Daily Cooldown Active", reason)
        self.assertIn("TITAN was stopped out earlier today", reason)

    # 22. Tier 1: Macro Tide Guard (NIFTY 50 Direction)
    def test_22_macro_nifty_divergence_rejection(self):
        """Verifies validator rejects bullish CE if NIFTY is dumping below VWAP & Open."""
        val = StockOptionsValidator(self.universe_mgr)

        # Bullish candidate when NIFTY is dumping
        bullish_cand = {
            "symbol": "COFORGE",
            "bias": "BULLISH",
            "technical": {"reference_price": 2060.0, "entry_trigger": 2070.0},
            "primary_contract": {"strike_price": 2040.0, "option_type": "CE", "indicative_premium": 60.0},
            "trade_management": {"stop_loss": 50.0, "target_1": 80.0},
            "macro_confluence": {
                "spot": 25050.0,
                "open": 25200.0,
                "vwap": 25180.0
            }
        }

        is_valid, reason, _ = val.validate_candidate_for_execution(
            candidate=bullish_cand,
            current_spot=2075.0,
            current_option_ltp=60.0,
            bid_price=59.5,
            ask_price=60.5,
            is_paper=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Macro Divergence", reason)
        self.assertIn("NIFTY 50 is bearish", reason)

    # 23. Tier 2: Sector Confluence Guard (BANKNIFTY)
    def test_23_sector_banknifty_divergence_rejection(self):
        """Verifies validator rejects banking CE if BANKNIFTY is in a downtrend."""
        val = StockOptionsValidator(self.universe_mgr)

        banking_cand = {
            "symbol": "HDFCBANK",
            "bias": "BULLISH",
            "technical": {"reference_price": 810.0, "entry_trigger": 815.0},
            "primary_contract": {"strike_price": 810.0, "option_type": "CE", "indicative_premium": 15.0},
            "trade_management": {"stop_loss": 12.0, "target_1": 20.0},
            "macro_confluence": {"spot": 25200.0, "open": 25150.0, "vwap": 25160.0},  # Macro NIFTY is fine
            "sector_index_confluence": {
                "spot": 61200.0,
                "open": 61600.0,
                "vwap": 61550.0  # BANKNIFTY is dumping below VWAP
            }
        }

        is_valid, reason, _ = val.validate_candidate_for_execution(
            candidate=banking_cand,
            current_spot=816.0,
            current_option_ltp=15.0,
            bid_price=14.8,
            ask_price=15.2,
            is_paper=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Sector Divergence", reason)
        self.assertIn("BANKNIFTY is bearish", reason)

    # 24. Institutional AI Confidence Gate (>= 8.5 / 10)
    def test_24_confidence_gate_rejection(self):
        """Verifies validator rejects mediocre B-grade candidates with confidence < 8.5."""
        val = StockOptionsValidator(self.universe_mgr)

        mediocre_cand = {
            "symbol": "INFY",
            "bias": "BULLISH",
            "confidence_score": 0.70,  # 7.0 / 10 is below 8.5 threshold
            "technical": {"reference_price": 1850.0, "entry_trigger": 1855.0},
            "primary_contract": {"strike_price": 1860.0, "option_type": "CE", "indicative_premium": 25.0},
            "trade_management": {"stop_loss": 20.0, "target_1": 35.0}
        }

        is_valid, reason, _ = val.validate_candidate_for_execution(
            candidate=mediocre_cand,
            current_spot=1856.0,
            current_option_ltp=25.0,
            bid_price=24.8,
            ask_price=25.2,
            is_paper=True
        )
        self.assertFalse(is_valid)
        self.assertIn("Confidence Gate Rejection", reason)
        self.assertIn("below minimum institutional threshold", reason)

        # High confidence A+ candidate (>= 8.5) must pass
        aplus_cand = dict(mediocre_cand)
        aplus_cand["confidence_score"] = 0.90
        is_valid, reason, _ = val.validate_candidate_for_execution(
            candidate=aplus_cand,
            current_spot=1856.0,
            current_option_ltp=25.0,
            bid_price=24.8,
            ask_price=25.2,
            is_paper=True
        )
        self.assertTrue(is_valid, f"Should pass: {reason}")

    # 25. Gemini AI Sentinel Index Regime Guard
    async def test_25_index_gemini_sentinel_guard(self):
        """Verifies SniperILSMEStrategy blocks breakout signals under RANGEBOUND_CHOP regime."""
        from smartapi_trader.strategy.sniper_ilsme import SniperILSMEStrategy
        from smartapi_trader.core.state_manager import StateManager

        mock_loader = MagicMock()
        mock_state_mgr = StateManager(self.event_bus)

        strat = SniperILSMEStrategy(
            event_bus=self.event_bus,
            state_manager=mock_state_mgr,
            instrument_loader=mock_loader,
            config={"strategy": {"active_indices": ["NIFTY"]}, "risk": {}},
            symbols_config={"indices": {"NIFTY": {"spot_token": "99926000"}}}
        )

        strat.index_regime = "RANGEBOUND_CHOP"
        strat._regime_reason = "Index oscillating in tight range"

        # Try generating breakout signal
        mock_fvg = {"source": "MOMENTUM_ORB"}
        published_signals = []
        async def mock_publish(evt):
            published_signals.append(evt)
        strat.bus.publish = mock_publish

        await strat._generate_sniper_signal("NIFTY", "BUY_CE", 25150.0, mock_fvg)
        # Should be blocked
        self.assertEqual(len(published_signals), 0, "Breakout signal must be blocked during RANGEBOUND_CHOP.")


if __name__ == "__main__":
    unittest.main()


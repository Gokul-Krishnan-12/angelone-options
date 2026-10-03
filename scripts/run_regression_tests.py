#!/usr/bin/env python3
"""
Comprehensive Regression Test Suite for Angel One SmartAPI Options Sniper Platform.
Tests all quantitative models, risk filters, execution mechanics, persistence, and web APIs.
"""

import os
import sys
import json
import time
import asyncio
import unittest
from datetime import datetime

# Add root directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartapi_trader.utils.charges import calculate_option_charges
from smartapi_trader.core.events import (
    EventType, TickEvent, BarEvent, SignalEvent, OrderEvent, FillEvent, PositionEvent, RiskAlertEvent, SystemStateEvent
)
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.data.instrument_loader import InstrumentLoader
from smartapi_trader.data.candle_builder import CandleAggregator
from smartapi_trader.data.trade_storage import TradeStorage
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.strategy.sniper_ilsme import SniperILSMEStrategy
from smartapi_trader.risk.risk_manager import RiskManager
from smartapi_trader.execution.paper_engine import PaperExecutionEngine
from smartapi_trader.utils.auth import AngelAuthManager
from smartapi_trader.utils.telegram_notifier import TelegramNotifier, TelegramBotController
from smartapi_trader.strategy.backtest_engine import BacktestEngine
from smartapi_trader.web.app import app, ctx, valid_sessions, otp_store, AUTH_TOKEN_COOKIE


class Test1ChargesAndTaxation(unittest.TestCase):
    """Verifies SEBI and Angel One options charges and statutory tax calculations."""

    def test_zero_quantity_or_price(self):
        c = calculate_option_charges(entry_price=100.0, exit_price=100.0, quantity=0, exchange="NFO")
        # Brokerage = 40.0 + 18% GST (7.20) = 47.20
        self.assertAlmostEqual(c["total_charges"], 47.20, places=2)
        self.assertEqual(c["gross_pnl"], 0.0)

    def test_standard_profitable_nifty_trade(self):
        # 1 Lot Nifty = 65 Qty, Buy @ 120, Sell @ 160 -> Gross PnL = +2600.0
        c = calculate_option_charges(entry_price=120.0, exit_price=160.0, quantity=65, exchange="NFO")
        self.assertAlmostEqual(c["gross_pnl"], 2600.0, places=2)
        self.assertEqual(c["brokerage"], 40.0)  # Flat 20 buy + 20 sell
        # STT = 0.1% on sell turnover (160 * 65 = 10400 -> 10.40 STT)
        self.assertAlmostEqual(c["stt"], 10.40, places=2)
        # Stamp duty = 0.003% on buy turnover (120 * 65 = 7800 -> 0.234 -> 0.23)
        self.assertAlmostEqual(c["stamp_duty"], 0.23, places=2)
        # GST = 18% on (Brokerage + Exch charges + SEBI)
        self.assertGreater(c["gst"], 7.0)
        self.assertGreater(c["total_charges"], 55.0)
        self.assertLess(c["total_charges"], 85.0)
        self.assertAlmostEqual(c["net_pnl"], c["gross_pnl"] - c["total_charges"], places=2)

    def test_losing_trade_charges(self):
        # 1 Lot BankNifty = 30 Qty, Buy @ 250, Sell @ 225 -> Gross PnL = -750.0
        c = calculate_option_charges(entry_price=250.0, exit_price=225.0, quantity=30, exchange="NFO")
        self.assertAlmostEqual(c["gross_pnl"], -750.0, places=2)
        self.assertLess(c["net_pnl"], -750.0)  # Net PnL must be worse due to charges


class Test2EventBusAndEvents(unittest.IsolatedAsyncioTestCase):
    """Verifies Event dataclasses and asynchronous pub/sub routing."""

    async def test_event_bus_pub_sub(self):
        bus = EventBus()
        bus.start()
        received_ticks = []
        received_wildcard = []

        async def tick_handler(event):
            received_ticks.append(event)

        async def wildcard_handler(event):
            received_wildcard.append(event)

        bus.subscribe(EventType.TICK, tick_handler)
        bus.subscribe("*", wildcard_handler)

        tick = TickEvent(
            symbol="NIFTY",
            token="99926000",
            ltp=25000.0,
            best_bid=24999.0,
            best_ask=25001.0,
            volume=1000
        )
        await bus.publish(tick)
        await asyncio.sleep(0.05)

        self.assertEqual(len(received_ticks), 1)
        self.assertEqual(received_ticks[0].symbol, "NIFTY")
        self.assertEqual(len(received_wildcard), 1)
        self.assertEqual(received_wildcard[0].event_type, EventType.TICK)

        # Unsubscribe
        bus.unsubscribe(EventType.TICK, tick_handler)
        await bus.publish(tick)
        await asyncio.sleep(0.05)
        self.assertEqual(len(received_ticks), 1)
        self.assertEqual(len(received_wildcard), 2)
        await bus.stop()


class Test3InstrumentLoaderAndStrikes(unittest.TestCase):
    """Verifies SQLite instrument caching and strike resolution logic."""

    def setUp(self):
        self.db_path = "data/instruments.db"
        self.loader = InstrumentLoader(self.db_path)
        if not self.loader.is_cache_valid_for_today():
            self.loader._seed_synthetic_contracts()

    def test_instrument_lookup(self):
        res = self.loader.get_atm_option("NIFTY", 25000.0, "CE")
        self.assertIsNotNone(res)
        self.assertIn("tradingsymbol", res)
        self.assertIn("symboltoken", res)
        self.assertEqual(res["name"], "NIFTY")

    def test_banknifty_lookup(self):
        res = self.loader.get_atm_option("BANKNIFTY", 54000.0, "PE")
        self.assertIsNotNone(res)
        self.assertIn("tradingsymbol", res)
        self.assertIn("symboltoken", res)
        self.assertEqual(res["name"], "BANKNIFTY")


class Test4CandleAggregatorAndVWAP(unittest.IsolatedAsyncioTestCase):
    """Verifies OHLCV candle formation and session VWAP calculation."""

    async def test_tick_to_candle_aggregation(self):
        bus = EventBus()
        bus.start()
        aggregator = CandleAggregator(bus, timeframes=[3, 15])
        bars_emitted = []

        async def bar_handler(bar):
            bars_emitted.append(bar)

        bus.subscribe(EventType.BAR, bar_handler)

        # Tick 1
        await aggregator.on_tick(TickEvent(
            symbol="NIFTY", token="99926000", ltp=25000.0, best_bid=24999.0, best_ask=25001.0, volume=100
        ))
        # Tick 2 at same bar
        await aggregator.on_tick(TickEvent(
            symbol="NIFTY", token="99926000", ltp=25050.0, best_bid=25049.0, best_ask=25051.0, volume=200
        ))
        await asyncio.sleep(0.05)

        self.assertGreaterEqual(len(bars_emitted), 1)
        b = bars_emitted[-1]
        self.assertEqual(b.symbol, "NIFTY")
        self.assertEqual(b.open, 25000.0)
        self.assertEqual(b.high, 25050.0)
        self.assertGreater(b.vwap, 0.0)
        await bus.stop()


class Test5StateManagerAndIsolation(unittest.TestCase):
    """Verifies Paper Ledger vs Live RMS separation, PnL tracking, and SQLite persistence."""

    def setUp(self):
        self.bus = EventBus()
        self.temp_db = "data/test_reg_storage.db"
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        self.storage = TradeStorage(self.temp_db)
        self.state_mgr = StateManager(self.bus, execution_mode="PAPER", initial_capital=50000.0, storage=self.storage, max_trades_allowed=2)

    def tearDown(self):
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    def test_paper_vs_live_isolation(self):
        # Update live RMS from broker
        self.state_mgr.update_broker_rms({
            "net": 125000.0,
            "availablecash": 120000.0,
            "collateral": 5000.0,
            "utiliseddebits": 0.0
        })

        # Check paper state
        snapshot = self.state_mgr.get_snapshot()
        self.assertEqual(snapshot["paper_state"]["capital"], 50000.0)
        self.assertEqual(self.state_mgr.broker_rms["availablecash"], 120000.0)

        # Record Paper Trade using keyword args
        self.state_mgr.record_completed_trade(
            pnl=2000.0,
            entry_price=100.0,
            exit_price=140.0,
            quantity=50,
            symbol="NIFTY26OCT25000CE",
            exchange="NFO",
            is_paper=True,
            strike_price=25000,
            option_type="CE",
            exit_reason="Target +2R Hit"
        )
        self.assertEqual(self.state_mgr.paper_trades_taken, 1)
        self.assertGreater(self.state_mgr.paper_net_pnl, 1800.0)
        # Verify Live RMS was completely untouched
        self.assertEqual(self.state_mgr.broker_rms["availablecash"], 120000.0)

    def test_quota_and_reset(self):
        self.state_mgr.record_completed_trade(
            pnl=500.0, entry_price=100.0, exit_price=110.0, quantity=50, symbol="NIFTY25000CE", exchange="NFO", is_paper=True, strike_price=25000, option_type="CE", exit_reason="TP"
        )
        self.state_mgr.record_completed_trade(
            pnl=-300.0, entry_price=100.0, exit_price=94.0, quantity=50, symbol="NIFTY25000PE", exchange="NFO", is_paper=True, strike_price=25000, option_type="PE", exit_reason="SL"
        )
        self.assertEqual(self.state_mgr.paper_trades_taken, 2)

        # Reset paper trades
        self.state_mgr.reset_paper_trades()
        self.assertEqual(self.state_mgr.paper_trades_taken, 0)
        self.assertEqual(len(self.state_mgr.paper_completed_trades), 0)


class Test6RiskManagerControls(unittest.IsolatedAsyncioTestCase):
    """Verifies Risk sizing logic and circuit breaker alerts."""

    async def asyncSetUp(self):
        self.bus = EventBus()
        self.bus.start()
        self.temp_db = "data/test_reg_risk.db"
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        self.storage = TradeStorage(self.temp_db)
        self.state_mgr = StateManager(self.bus, execution_mode="PAPER", initial_capital=100000.0, storage=self.storage, max_trades_allowed=2)
        
        cfg = {
            "risk": {
                "risk_per_trade_pct": 0.015,
                "max_daily_drawdown_pct": 0.03,
                "max_trades_per_day": 2,
                "consecutive_loss_limit": 2,
                "partial_exit_r": 2.0,
                "partial_exit_qty_pct": 0.60
            }
        }
        self.risk_mgr = RiskManager(self.bus, self.state_mgr, config=cfg)

    async def asyncTearDown(self):
        await self.bus.stop()
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    async def test_signal_rejection_on_panic(self):
        self.state_mgr.trigger_panic()
        alerts = []
        async def alert_handler(evt):
            alerts.append(evt)
        self.bus.subscribe(EventType.RISK_ALERT, alert_handler)

        sig = SignalEvent(
            signal_id="SIG_001",
            underlying="NIFTY",
            signal_type="BUY_CE",
            strike=25000,
            option_type="CE",
            tradingsymbol="NIFTY 25000 CE",
            symboltoken="12345",
            lot_size=65,
            entry_price=150.0,
            stop_loss=135.0,
            target_1=180.0
        )
        await self.bus.publish(sig)
        await asyncio.sleep(0.08)
        self.assertGreaterEqual(len(alerts), 1)
        self.assertIn("Panic", alerts[0].rule_name)


class Test7PaperExecutionSlippageModeling(unittest.IsolatedAsyncioTestCase):
    """Verifies realistic Bid/Ask spread and kappa slippage in Paper Execution."""

    async def asyncSetUp(self):
        self.bus = EventBus()
        self.bus.start()
        self.state_mgr = StateManager(self.bus, execution_mode="PAPER", initial_capital=50000.0)
        cfg = {"execution": {"slippage_factor": 0.20, "simulated_latency_ms": 10}}
        self.paper_engine = PaperExecutionEngine(self.bus, self.state_mgr, config=cfg)

    async def asyncTearDown(self):
        await self.bus.stop()

    async def test_buy_fill_with_adverse_slippage(self):
        order = OrderEvent(
            order_id="ORD_TEST_001",
            symbol="NIFTY26OCT25000CE",
            token="12345",
            transaction_type="BUY",
            order_type="LIMIT",
            quantity=65,
            price=150.0,
            status="PENDING"
        )
        # Pre-seed tick: Bid=149.0, Ask=151.0 (Spread=2.0)
        # Expected Fill = Ask + (Spread * 0.20) = 151.0 + 0.40 = 151.40
        self.state_mgr.ticks["12345"] = TickEvent(
            symbol="NIFTY26OCT25000CE",
            token="12345",
            ltp=150.0,
            best_bid=149.0,
            best_ask=151.0,
            spread=2.0
        )
        await self.paper_engine._on_order_event(order)
        await asyncio.sleep(0.35)
        
        # Verify order state
        saved_order = self.state_mgr.orders.get("ORD_TEST_001")
        self.assertIsNotNone(saved_order)
        self.assertEqual(saved_order.status, "FILLED")
        self.assertAlmostEqual(saved_order.average_price, 151.40, places=2)


class Test8BacktestEngineSimulation(unittest.TestCase):
    """Verifies backtest engine simulation on actual historical data."""

    def test_backtest_run_single_session(self):
        engine = BacktestEngine(
            starting_capital=50000.0,
            risk_per_trade_pct=0.015,
            dynamic_compounding=False,
            start_date="2026-09-28",
            end_date="2026-09-28"
        )
        results = engine.run()
        self.assertIn("summary", results)
        self.assertIn("trades", results)
        summary = results["summary"]
        self.assertIn("total_net_pnl", summary)
        self.assertIn("profit_factor", summary)
        self.assertIn("win_rate_pct", summary)


class Test9TelegramBotAndCommands(unittest.TestCase):
    """Verifies 2-way Telegram bot commands and notification formatting."""

    def setUp(self):
        self.bus = EventBus()
        self.state_mgr = StateManager(self.bus, execution_mode="PAPER", initial_capital=50000.0)
        self.notifier = TelegramNotifier({"enabled": False, "bot_token": "TEST_TOKEN", "chat_id": "123456789"})
        self.bot = TelegramBotController(self.notifier, self.state_mgr, None)

    def test_help_command(self):
        res = self.bot.dispatch_command("/help", [])
        self.assertIn("OPTIONS SNIPER TELEGRAM COMMANDS", res)
        self.assertIn("/status", res)
        self.assertIn("/squareoff", res)

    def test_status_command(self):
        res = self.bot.dispatch_command("/status", [])
        self.assertIn("Execution Mode:", res)
        self.assertIn("Today's Net P&L:", res)
        self.assertIn("Active Capital:", res)


class Test10WebEndpointsAndAuthFlow(unittest.IsolatedAsyncioTestCase):
    """Verifies FastAPI REST and WebSocket endpoints, auth protection, and control plane logic."""

    async def asyncSetUp(self):
        self.bus = EventBus()
        self.bus.start()
        self.temp_db = "data/test_reg_web.db"
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)
        self.storage = TradeStorage(self.temp_db)
        self.state_mgr = StateManager(self.bus, execution_mode="PAPER", initial_capital=50000.0, storage=self.storage)
        
        ctx.event_bus = self.bus
        ctx.state_manager = self.state_mgr
        ctx.trade_storage = self.storage
        ctx.auth_manager = AngelAuthManager("", "", "", "")
        ctx.notifier = TelegramNotifier({"enabled": False})
        
        # Pre-seed an authenticated test session
        self.test_token = "test_super_secret_session_token_12345"
        valid_sessions[self.test_token] = time.time() + 3600

    async def asyncTearDown(self):
        await self.bus.stop()
        if self.test_token in valid_sessions:
            del valid_sessions[self.test_token]
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    async def test_auth_status_endpoint(self):
        from starlette.requests import Request
        # Non-authenticated
        scope_unauth = {"type": "http", "headers": [], "path": "/api/auth/status", "method": "GET"}
        req_unauth = Request(scope_unauth)
        from smartapi_trader.web.app import auth_status
        res1 = await auth_status(req_unauth)
        self.assertFalse(res1["authenticated"])

        # Authenticated
        auth_header = [(b"authorization", f"Bearer {self.test_token}".encode())]
        scope_auth = {"type": "http", "headers": auth_header, "path": "/api/auth/status", "method": "GET"}
        req_auth = Request(scope_auth)
        res2 = await auth_status(req_auth)
        self.assertTrue(res2["authenticated"])

    async def test_paper_agent_start_pause(self):
        from smartapi_trader.web.app import start_paper_agent, pause_paper_agent
        res_start = await start_paper_agent()
        self.assertEqual(res_start["paper_agent"], "RUNNING")
        self.assertEqual(self.state_mgr.paper_agent_status, "RUNNING")

        res_pause = await pause_paper_agent()
        self.assertEqual(res_pause["paper_agent"], "PAUSED")
        self.assertEqual(self.state_mgr.paper_agent_status, "PAUSED")

    async def test_paper_capital_update(self):
        from smartapi_trader.web.app import update_paper_capital, PaperCapitalRequest
        res = await update_paper_capital(PaperCapitalRequest(capital=75000.0))
        self.assertEqual(res["status"], "success")
        self.assertEqual(self.state_mgr.paper_capital, 75000.0)

    async def test_panic_and_reset_flow(self):
        from smartapi_trader.web.app import trigger_panic, reset_panic
        # Add dummy position
        self.state_mgr.positions["NIFTY25000CE"] = PositionEvent(
            symbol="NIFTY25000CE", token="123", quantity=65, entry_price=150.0,
            current_ltp=160.0, stop_loss=135.0, target_1=180.0, unrealized_pnl=650.0
        )
        res_panic = await trigger_panic()
        self.assertEqual(res_panic["status"], "panic_activated")
        self.assertTrue(self.state_mgr.is_panic_active)
        self.assertFalse(self.state_mgr.positions["NIFTY25000CE"].is_open)

        res_reset = await reset_panic()
        self.assertEqual(res_reset["status"], "panic_cleared")
        self.assertFalse(self.state_mgr.is_panic_active)

    async def test_get_state_and_orders_endpoints(self):
        from smartapi_trader.web.app import get_state, get_all_orders, get_trades_history
        state = await get_state()
        self.assertIn("execution_mode", state)
        self.assertIn("paper_state", state)
        self.assertIn("broker_rms", state)

        orders_res = await get_all_orders(include_paper=True)
        self.assertIn("positions", orders_res)
        self.assertIn("orders", orders_res)
        self.assertIn("trade_history", orders_res)

        trades_res = await get_trades_history(limit=50)
        self.assertEqual(trades_res["status"], "success")
        self.assertIn("trades", trades_res)

    async def test_calendar_and_settings_endpoints(self):
        from smartapi_trader.web.app import get_paper_calendar, get_settings, update_settings, SettingsUpdateRequest
        cal = await get_paper_calendar()
        self.assertEqual(cal["status"], "success")
        self.assertIn("summary", cal)

        settings = await get_settings()
        self.assertIn("broker", settings)
        self.assertIn("risk", settings)

        update_res = await update_settings(SettingsUpdateRequest(risk_per_trade_pct=0.018))
        self.assertEqual(update_res["status"], "success")

    async def test_mode_switch_validation(self):
        from smartapi_trader.web.app import toggle_mode, ModeRequest
        from fastapi import HTTPException
        # Switch to LIVE without valid broker credentials must raise HTTPException 400
        with self.assertRaises(HTTPException) as cm:
            await toggle_mode(ModeRequest(mode="LIVE"))
        self.assertEqual(cm.exception.status_code, 400)


def run_all_tests():
    print("=" * 70)
    print("🚀 ANGEL ONE OPTIONS SNIPER - FULL REGRESSION TEST RUNNER")
    print("=" * 70)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(Test1ChargesAndTaxation))
    suite.addTests(loader.loadTestsFromTestCase(Test2EventBusAndEvents))
    suite.addTests(loader.loadTestsFromTestCase(Test3InstrumentLoaderAndStrikes))
    suite.addTests(loader.loadTestsFromTestCase(Test4CandleAggregatorAndVWAP))
    suite.addTests(loader.loadTestsFromTestCase(Test5StateManagerAndIsolation))
    suite.addTests(loader.loadTestsFromTestCase(Test6RiskManagerControls))
    suite.addTests(loader.loadTestsFromTestCase(Test7PaperExecutionSlippageModeling))
    suite.addTests(loader.loadTestsFromTestCase(Test8BacktestEngineSimulation))
    suite.addTests(loader.loadTestsFromTestCase(Test9TelegramBotAndCommands))
    suite.addTests(loader.loadTestsFromTestCase(Test10WebEndpointsAndAuthFlow))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print(f"✅ ALL {result.testsRun} REGRESSION TESTS PASSED WITHOUT ERROR!")
    else:
        print(f"❌ REGRESSION FAILURES: {len(result.failures)} Failures, {len(result.errors)} Errors")
    print("=" * 70)
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

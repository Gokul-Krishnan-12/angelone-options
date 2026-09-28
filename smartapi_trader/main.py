import os
import sys
import yaml
import asyncio
import signal
import uvicorn
from typing import Dict, Any

from smartapi_trader.utils.logger import logger
from smartapi_trader.utils.auth import AngelAuthManager
from smartapi_trader.utils.telegram_notifier import TelegramNotifier, TelegramBotController
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.core.events import EventType
from smartapi_trader.data.trade_storage import TradeStorage
from smartapi_trader.data.instrument_loader import InstrumentLoader
from smartapi_trader.data.candle_builder import CandleAggregator
from smartapi_trader.data.stream_client import SmartStreamClient
from smartapi_trader.strategy.sniper_ilsme import SniperILSMEStrategy
from smartapi_trader.risk.risk_manager import RiskManager
from smartapi_trader.execution.paper_engine import PaperExecutionEngine
from smartapi_trader.execution.live_smartapi import LiveSmartAPIExecutionEngine
from smartapi_trader.web.app import app, ctx

def load_yaml(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        example_path = file_path.replace("settings.yaml", "settings.example.yaml")
        if os.path.exists(example_path):
            import shutil
            shutil.copy(example_path, file_path)
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

class TradingOrchestrator:
    """
    Main engine orchestrator tying together data streams, candle assembly,
    strategy signals, risk filters, execution venues, and the web control plane.
    """
    def __init__(self, config_dir: str = "smartapi_trader/config"):
        self.settings = load_yaml(os.path.join(config_dir, "settings.yaml"))
        self.symbols = load_yaml(os.path.join(config_dir, "symbols.yaml"))
        
        self.event_bus = EventBus()
        self.mode = self.settings.get("execution", {}).get("execution_mode", "PAPER")

        # Persistent SQLite storage layer for positions, orders, trades, and daily ledger
        storage_db = self.settings.get("data", {}).get("storage_db_path", "data/trading_storage.db")
        self.trade_storage = TradeStorage(storage_db)
        
        initial_cap = self.settings.get("execution", {}).get("paper_initial_capital", 100000.0)
        max_trades = self.settings.get("risk", {}).get("max_trades_per_day", 2)
        self.state_mgr = StateManager(self.event_bus, execution_mode=self.mode, initial_capital=initial_cap, storage=self.trade_storage, max_trades_allowed=max_trades)
        
        # Telegram Notifier & 2-Way Remote Controller (same keys as angelone-swing)
        telegram_cfg = self.settings.get("telegram", {})
        self.notifier = TelegramNotifier(telegram_cfg)
        self.telegram_bot = TelegramBotController(self.notifier, self.state_mgr, self)
        self._eod_task = None

        # Data & Market components
        self.instrument_loader = InstrumentLoader(self.settings.get("data", {}).get("db_path", "data/instruments.db"))
        self.candle_aggregator = CandleAggregator(self.event_bus, timeframes=[3, 15])
        
        broker_cfg = self.settings.get("broker", {})
        self.auth_manager = AngelAuthManager(
            api_key=broker_cfg.get("api_key", ""),
            client_code=broker_cfg.get("client_code", ""),
            pin=broker_cfg.get("pin", ""),
            totp_secret=broker_cfg.get("totp_secret", "")
        )
        self.smart_api, self.jwt_token, self.feed_token = self.auth_manager.initialize_session()

        # Strategy & Risk
        self.strategy = SniperILSMEStrategy(
            event_bus=self.event_bus,
            state_manager=self.state_mgr,
            instrument_loader=self.instrument_loader,
            config=self.settings,
            symbols_config=self.symbols,
            auth_manager=self.auth_manager
        )
        self.risk_manager = RiskManager(
            event_bus=self.event_bus,
            state_manager=self.state_mgr,
            config=self.settings,
            notifier=self.notifier
        )

        # Execution venues
        self.paper_engine = PaperExecutionEngine(
            event_bus=self.event_bus,
            state_manager=self.state_mgr,
            config=self.settings
        )
        
        self.live_engine = LiveSmartAPIExecutionEngine(
            event_bus=self.event_bus,
            state_manager=self.state_mgr,
            config=self.settings,
            smart_connect_instance=self.smart_api,
            jwt_token=self.jwt_token,
            api_key=broker_cfg.get("api_key", "")
        )

        # Wire execution venues into RiskManager for native exchange SL placement, modification & cancellation
        self.risk_manager.set_engines(self.live_engine, self.paper_engine)

        # Only simulate market feed if broker credentials are not configured or session failed
        is_sim = bool(self.auth_manager.is_simulated)
        self.stream_client = SmartStreamClient(
            event_bus=self.event_bus,
            auth_token=self.jwt_token,
            api_key=broker_cfg.get("api_key", ""),
            client_code=broker_cfg.get("client_code", ""),
            feed_token=self.feed_token,
            is_simulated=is_sim
        )

        # Connect pipeline event listeners
        self.event_bus.subscribe(EventType.TICK, self.candle_aggregator.on_tick)
        self.event_bus.subscribe(EventType.TICK, self.strategy.on_tick)
        self.event_bus.subscribe(EventType.BAR, self.strategy.on_bar)

        # Inject context for Web UI
        ctx.event_bus = self.event_bus
        ctx.state_manager = self.state_mgr
        ctx.trade_storage = self.trade_storage
        ctx.strategy = self.strategy
        ctx.execution_engine = self.paper_engine if self.mode == "PAPER" else self.live_engine
        ctx.auth_manager = self.auth_manager
        ctx.orchestrator = self
        ctx.risk_manager = self.risk_manager
        ctx.notifier = self.notifier
        ctx.telegram_bot = self.telegram_bot

    async def _eod_monitor_loop(self):
        """Monitors clock and dispatches daily EOD report to Telegram at 15:15 IST."""
        last_sent_date = None
        while True:
            try:
                await asyncio.sleep(15)
                from smartapi_trader.utils.tz import now_ist
                now = now_ist()
                now_str = now.strftime("%Y-%m-%d")
                
                # Check target EOD time (default 15:15 IST)
                eod_time_str = self.settings.get("telegram", {}).get("eod_report_time", "15:15")
                parts = eod_time_str.split(":")
                target_hour = int(parts[0])
                target_min = int(parts[1]) if len(parts) > 1 else 15
                
                if (now.hour == target_hour and now.minute >= target_min) or (now.hour > target_hour):
                    if last_sent_date != now_str:
                        logger.info(f"[EOD] Triggering automated Telegram EOD session report at {now.strftime('%H:%M:%S')} IST...")
                        if self.notifier:
                            self.notifier.notify_eod_summary(self.state_mgr)
                        last_sent_date = now_str
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EOD_MONITOR] Error in EOD loop: {e}")
                await asyncio.sleep(30)

    async def initialize(self):
        """Pre-flight setup: indexes scrip master and subscribes to index spot contracts."""
        logger.info("[ORCHESTRATOR] Initializing SmartAPI Index Options Engine...")
        self.event_bus.start()

        # Load & index scrip master
        logger.info("[ORCHESTRATOR] Loading scrip master index...")
        self.instrument_loader.load_instruments()

        # Subscribe to spot indices from symbols.yaml
        for sym_name, sym_info in self.symbols.get("indices", {}).items():
            if sym_info.get("is_active"):
                token = str(sym_info.get("spot_token"))
                exch = sym_info.get("exchange", "NSE")
                self.stream_client.subscribe(token=token, symbol=sym_name, exchange=exch, mode=2)

        # Re-subscribe to any active open positions recovered from storage for SL/TP management
        for sym, pos in self.state_mgr.positions.items():
            if pos.is_open and pos.token:
                self.stream_client.subscribe(token=str(pos.token), symbol=sym, exchange="NFO", mode=2)
                logger.info(f"[ORCHESTRATOR] 🛡️ Subscribed to recovered position: {sym} (Token: {pos.token})")

        # Sync live spot quotes and RMS margin balance from Angel One if authenticated
        if self.auth_manager and not self.auth_manager.is_simulated:
            try:
                live_spots = self.auth_manager.fetch_spot_ltp()
                for k, v in live_spots.items():
                    self.state_mgr.update_spot_telemetry(
                        underlying=k,
                        spot=v["spot"],
                        vwap=v.get("vwap", v["spot"]),
                        pdh=v.get("close", 0.0),
                        pdl=v.get("low", 0.0),
                        high=v.get("high", 0.0),
                        low=v.get("low", 0.0)
                    )
                    if hasattr(self, "strategy") and k in self.strategy.state:
                        self.strategy.state[k]["last_spot"] = v["spot"]
                        self.strategy.state[k]["vwap"] = v.get("vwap", v["spot"])
                        if v.get("high", 0) > 0:
                            self.strategy.state[k]["session_high"] = v["high"]
                        if v.get("low", 0) > 0:
                            self.strategy.state[k]["session_low"] = v["low"]
                        if v.get("close", 0) > 0:
                            self.strategy.state[k]["pdh"] = v["close"]
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error querying spot LTP: {e}")

            try:
                rms_res = self.auth_manager.fetch_rms_balance()
                if rms_res.get("status") and "data" in rms_res:
                    min_cap = float(self.settings.get("risk", {}).get("min_capital_required", 50000.0))
                    self.state_mgr.update_broker_rms(rms_res["data"], min_capital=min_cap)
                    logger.info("[ORCHESTRATOR] ✅ Live Angel One RMS balance automatically synced on boot.")
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error fetching initial RMS balance: {e}")

        # Start WebSocket or synthetic stream
        await self.stream_client.start()

        # Start 2-way Telegram Bot & Automated EOD Report Scheduler
        if self.settings.get("telegram", {}).get("enabled", True):
            if self.settings.get("telegram", {}).get("enable_bot_commands", True):
                self.telegram_bot.start()
            self._eod_task = asyncio.create_task(self._eod_monitor_loop())
            logger.info("[ORCHESTRATOR] Telegram 2-way bot & EOD scheduler active.")

        logger.info(f"[ORCHESTRATOR] System ready! Active Execution Mode: {self.mode}")

    async def shutdown(self):
        """Gracefully halts all components and flushes event buffers."""
        logger.warning("[ORCHESTRATOR] Initiating graceful shutdown...")
        if self._eod_task:
            self._eod_task.cancel()
        if hasattr(self, "telegram_bot") and self.telegram_bot:
            self.telegram_bot.stop()
        await self.stream_client.stop()
        await self.event_bus.stop()
        logger.info("[ORCHESTRATOR] Shutdown sequence complete.")

async def run_server():
    orchestrator = TradingOrchestrator()
    await orchestrator.initialize()

    host = orchestrator.settings.get("web", {}).get("host", "0.0.0.0")
    port = orchestrator.settings.get("web", {}).get("port", 5000)

    config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.shutdown()))
        except NotImplementedError:
            pass

    logger.info(f"[WEB] Dashboard active at http://localhost:{port} (Binding: {host}:{port})")
    await server.serve()

def main():
    try:
        asyncio.run(run_server())
    except (KeyboardInterrupt, SystemExit):
        logger.info("[MAIN] Engine exited gracefully.")

if __name__ == "__main__":
    main()

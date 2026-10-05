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
        self.event_bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)

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

    async def _on_position_update(self, event: Any):
        """Dynamically registers WebSocket feed subscription for any opened options contract."""
        if getattr(event, 'is_open', False) and getattr(event, 'token', None):
            exch = getattr(event, 'exchange', '') or ("BFO" if "SENSEX" in getattr(event, 'symbol', '') else "NFO")
            token_str = str(event.token)
            symbol_str = str(event.symbol)
            self.stream_client.subscribe(token=token_str, symbol=symbol_str, exchange=exch, mode=2)
            logger.info(f"[ORCHESTRATOR] 🎯 Live tick subscription active for open position: {symbol_str} (Token: {token_str}, Exch: {exch})")

    async def _market_health_watchdog_loop(self):
        """
        Actively monitors stream connectivity, agent status, and server health during market hours (09:15 - 15:30 IST).
        Runs every 2 minutes to minimize CPU load and sends high-priority Telegram alerts if issues are detected.
        """
        last_alert_time = 0.0
        while True:
            try:
                await asyncio.sleep(120)  # Every 2 minutes
                from smartapi_trader.utils.tz import now_ist
                now = now_ist()
                
                # Check if market is active (Mon-Fri 09:15 - 15:30 IST)
                is_weekday = (now.weekday() < 5)
                now_t = now.time()
                is_mkt_hours = is_weekday and (datetime.time(9, 15) <= now_t <= datetime.time(15, 30))
                
                if is_mkt_hours:
                    issues = []
                    
                    # 1. Check WebSocket connection
                    is_ws_conn = getattr(self.stream_client, "is_connected", False)
                    last_tick = getattr(self.stream_client, "last_tick_time", 0.0)
                    time_since_tick = time.time() - last_tick if last_tick > 0 else 9999
                    
                    if not self.stream_client.is_simulated:
                        if not is_ws_conn:
                            issues.append("🔴 SmartWebSocket is DISCONNECTED from Angel One feed.")
                        elif time_since_tick > 120:
                            issues.append(f"⚠️ Live market ticks stalled (No ticks received for {int(time_since_tick)}s).")
                    
                    # 2. Check Agent Status
                    paper_st = getattr(self.state_mgr, "paper_agent_status", "PAUSED")
                    real_st = getattr(self.state_mgr, "real_agent_status", "PAUSED")
                    is_panic = getattr(self.state_mgr, "is_panic_active", False)
                    
                    if is_panic:
                        issues.append("🚨 System is in EMERGENCY PANIC / HALT state!")
                    elif self.mode == "LIVE" and real_st != "RUNNING":
                        issues.append(f"⚠️ Mode is LIVE but Real Agent is {real_st} (not RUNNING).")
                    elif self.mode == "PAPER" and paper_st != "RUNNING":
                        issues.append(f"⚠️ Mode is PAPER but Paper Agent is {paper_st} (not RUNNING).")
                    
                    # If issues detected, alert via Telegram (throttled to once every 5 minutes)
                    if issues and (time.time() - last_alert_time > 300):
                        last_alert_time = time.time()
                        alert_body = "\n".join([f"• {iss}" for iss in issues])
                        alert_msg = (
                            f"🚨 <b>MARKET HOURS HEALTH WARNING</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"⏰ <b>Time:</b> {now.strftime('%H:%M:%S')} IST\n"
                            f"⚠️ <b>Detected Issues:</b>\n{alert_body}\n\n"
                            f"<i>Use /status to diagnose or /start to resume execution.</i>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━"
                        )
                        if self.notifier:
                            self.notifier.send_message_async(alert_msg)
                            logger.warning(f"[WATCHDOG] Market hours alert dispatched to Telegram: {issues}")
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WATCHDOG] Error in watchdog loop: {e}")
                await asyncio.sleep(60)

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
                pos_exch = pos.exchange or ("BFO" if "SENSEX" in sym else "NFO")
                self.stream_client.subscribe(token=str(pos.token), symbol=sym, exchange=pos_exch, mode=2)
                logger.info(f"[ORCHESTRATOR] 🛡️ Subscribed to recovered position: {sym} (Token: {pos.token}, Exch: {pos_exch})")

        # Sync live spot quotes and RMS margin balance from Angel One if authenticated
        if self.auth_manager and not self.auth_manager.is_simulated:
            try:
                live_spots = self.auth_manager.fetch_spot_ltp()
                for k, v in live_spots.items():
                    # Preserve correctly resolved PDH/PDL from strategy / historical store
                    strat_state = getattr(self, "strategy", None)
                    strat_st = strat_state.state.get(k, {}) if strat_state else {}
                    true_pdh = strat_st.get("pdh", 0.0) or self.state_mgr.spot_levels.get(k, {}).get("pdh", 0.0)
                    true_pdl = strat_st.get("pdl", 0.0) or self.state_mgr.spot_levels.get(k, {}).get("pdl", 0.0)

                    # Ensure PDH >= PDL integrity
                    if true_pdh > 0 and true_pdl > 0 and true_pdh < true_pdl:
                        true_pdh, true_pdl = true_pdl, true_pdh

                    self.state_mgr.update_spot_telemetry(
                        underlying=k,
                        spot=v["spot"],
                        vwap=v.get("vwap", v["spot"]),
                        pdh=true_pdh,
                        pdl=true_pdl,
                        high=v.get("high", 0.0),
                        low=v.get("low", 0.0)
                    )
                    if strat_state and k in strat_state.state:
                        strat_state.state[k]["last_spot"] = v["spot"]
                        strat_state.state[k]["vwap"] = v.get("vwap", v["spot"])
                        if v.get("high", 0) > 0:
                            strat_state.state[k]["session_high"] = max(strat_state.state[k].get("session_high", 0.0), v["high"])
                        if v.get("low", 0) > 0:
                            cur_low = strat_state.state[k].get("session_low", 0.0)
                            strat_state.state[k]["session_low"] = min(cur_low, v["low"]) if cur_low > 0 else v["low"]
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

        # Start 2-way Telegram Bot, Automated EOD Report Scheduler, and Market Health Watchdog
        if self.settings.get("telegram", {}).get("enabled", True):
            if self.settings.get("telegram", {}).get("enable_bot_commands", True):
                self.telegram_bot.start()
            self._eod_task = asyncio.create_task(self._eod_monitor_loop())
            self._watchdog_task = asyncio.create_task(self._market_health_watchdog_loop())
            logger.info("[ORCHESTRATOR] Telegram 2-way bot, EOD scheduler & market health watchdog active.")

        logger.info(f"[ORCHESTRATOR] System ready! Active Execution Mode: {self.mode}")

    async def shutdown(self):
        """Gracefully halts all components and flushes event buffers."""
        logger.warning("[ORCHESTRATOR] Initiating graceful shutdown...")
        if self._eod_task:
            self._eod_task.cancel()
        if hasattr(self, "_watchdog_task") and self._watchdog_task:
            self._watchdog_task.cancel()
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

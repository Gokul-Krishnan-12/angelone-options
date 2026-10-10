import os
import json
import logging
import datetime
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple
from smartapi_trader.utils.tz import now_ist
from smartapi_trader.utils.logger import logger

class TelegramNotifier:
    """
    Dispatches Telegram notifications asynchronously for options trading events
    and daily End of Day (EOD) session performance reports.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="TelegramNotifier"
        )
        self.bot_token = str(self.config.get("bot_token", "8834022656:AAGsTEx46GIgP7XBar5Z4URNP2oEvZGfojM")).strip()
        self.chat_id = str(self.config.get("chat_id", "650527213")).strip()
        self.enabled = bool(self.config.get("enabled", True))

    def update_config(self, config: Dict[str, Any]):
        self.config = config
        self.bot_token = str(self.config.get("bot_token", self.bot_token)).strip()
        self.chat_id = str(self.config.get("chat_id", self.chat_id)).strip()
        self.enabled = bool(self.config.get("enabled", self.enabled))

    def send_message_sync(
        self,
        text: str,
        parse_mode: str = "HTML",
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Synchronously dispatch a Telegram message via the Bot API."""
        token = (bot_token or self.bot_token).strip()
        cid = (chat_id or self.chat_id).strip()

        if not token or not cid:
            return False, "Bot Token and Chat ID are required."

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": "true",
        }

        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "SmartAPIOptionsAgent/2.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return True, "Message sent successfully"
                return False, f"Telegram API returned status {resp.status}"
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                err_body = str(e)
            logger.error(f"[TELEGRAM] HTTPError {e.code}: {err_body}")
            return False, f"Telegram Error {e.code}: {err_body}"
        except Exception as e:
            logger.error(f"[TELEGRAM] Connection error: {e}")
            return False, f"Network error: {e}"

    def send_message_async(
        self,
        text: str,
        parse_mode: str = "HTML",
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        """Queue message in thread pool to avoid blocking trading tick loops."""
        if not self.enabled:
            return None
        return self._executor.submit(
            self.send_message_sync, text, parse_mode, bot_token, chat_id
        )

    def notify_trade_entry(self, trade: Dict[str, Any]):
        """Notifies when a new options contract position is entered."""
        if not self.enabled or not self.config.get("notify_on_trade_entry", True):
            return

        symbol = trade.get("symbol", "N/A")
        opt_type = trade.get("option_type", "CE")
        entry_price = float(trade.get("entry_price", 0.0) or 0.0)
        signal_price = float(trade.get("signal_price", entry_price) or entry_price)
        slippage = float(trade.get("slippage", round(entry_price - signal_price, 2)) or 0.0)
        stop_loss = float(trade.get("stop_loss", 0.0) or 0.0)
        target_1 = float(trade.get("target_1", 0.0) or 0.0)
        quantity = int(trade.get("quantity", 0) or 0)
        lots = int(trade.get("lots", 1) or 1)
        mode = trade.get("mode", "PAPER")

        risk_pts = max(0.1, entry_price - stop_loss)
        risk_pct = (risk_pts / entry_price * 100.0) if entry_price > 0 else 0.0
        now_str = now_ist().strftime("%H:%M:%S")

        dir_icon = "🟢" if "CE" in opt_type else "🔴"
        mode_tag = "📝 PAPER" if mode == "PAPER" else "⚡ LIVE"
        strategy_label = trade.get("strategy_name") or trade.get("strategy") or "ILSME_Sniper"

        t1_label = f"₹{target_1:.2f}" if target_1 > 0 else "Dynamic"
        slip_txt = f" | Slip: {slippage:+.2f}" if abs(slippage) > 0.01 else ""

        message = (
            f"⚡ <b>NEW POSITION ENTERED</b>\n\n"
            f"{dir_icon} <b>Instrument:</b> <b>{symbol}</b>\n"
            f"🧠 <b>Strategy:</b> <code>{strategy_label}</code>\n"
            f"📦 <b>Size:</b> {lots} Lot{'s' if lots > 1 else ''} ({quantity} Qty) @ ₹{entry_price:.2f}{slip_txt}\n"
            f"🛑 <b>Stop-Loss:</b> ₹{stop_loss:.2f} (-{risk_pct:.1f}%)\n"
            f"🎯 <b>Target 1:</b> {t1_label}\n"
            f"🏷 <b>Mode:</b> {mode_tag} | ⏱ <b>Time:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_partial_tp1(self, trade: Dict[str, Any]):
        """Notifies when Target 1 is reached and partial gain is locked."""
        if not self.enabled or not self.config.get("notify_on_tp1", True):
            return

        symbol = trade.get("symbol", "N/A")
        booked_qty = trade.get("booked_qty", 0)
        price = float(trade.get("price", 0.0) or 0.0)
        gain_pts = float(trade.get("gain_pts", 0.0) or 0.0)
        pnl = float(trade.get("pnl", 0.0) or 0.0)
        mode = trade.get("mode", "PAPER")
        strategy_label = trade.get("strategy_name") or "ILSME_Sniper"
        now_str = now_ist().strftime("%H:%M:%S")

        message = (
            f"🎯 <b>TARGET 1 HIT — PARTIAL GAINS BOOKED</b>\n\n"
            f"📈 <b>Instrument:</b> <b>{symbol}</b>\n"
            f"📦 <b>Booked:</b> {booked_qty} units @ ₹{price:.2f}\n"
            f"💰 <b>Realized Gain:</b> <code>+₹{pnl:,.2f}</code> (+{gain_pts:.2f} pts)\n"
            f"🛡 <b>Action:</b> Stop-Loss on remaining lot moved to BREAKEVEN\n"
            f"🏷 <b>Mode:</b> {mode} | ⏱ {now_str} IST"
        )
        self.send_message_async(message)

    def notify_breakeven_moved(self, trade: Dict[str, Any]):
        """Notifies when stop-loss is raised to entry (breakeven shift)."""
        if not self.enabled or not self.config.get("notify_on_breakeven", True):
            return

        symbol = trade.get("symbol", "N/A")
        be_price = float(trade.get("entry_price", 0.0) or 0.0)
        current_ltp = float(trade.get("current_ltp", 0.0) or 0.0)
        now_str = now_ist().strftime("%H:%M:%S")

        message = (
            f"🛡 <b>RISK FREE: SL MOVED TO BREAKEVEN</b>\n\n"
            f"📊 <b>Instrument:</b> <b>{symbol}</b>\n"
            f"🛑 <b>New Exchange SL:</b> ₹{be_price:.2f} (Entry Price)\n"
            f"⚡ <b>Current LTP:</b> ₹{current_ltp:.2f}\n"
            f"🔒 <b>Downside Risk:</b> 0.0% (Risk Eliminated)\n"
            f"⏱ <b>Time:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_trade_exit(self, trade: Dict[str, Any]):
        """Notifies when a trade position is fully closed."""
        if not self.enabled or not self.config.get("notify_on_trade_exit", True):
            return

        symbol = trade.get("symbol", "N/A")
        entry_price = float(trade.get("entry_price", 0.0) or 0.0)
        exit_price = float(trade.get("exit_price", 0.0) or 0.0)
        quantity = int(trade.get("quantity", 0) or 0)
        gross_pnl = float(trade.get("gross_pnl", 0.0) or trade.get("pnl", 0.0) or 0.0)
        total_charges = float(trade.get("total_charges", 65.0) or 0.0)
        net_pnl = float(trade.get("net_pnl", gross_pnl - total_charges))
        reason = str(trade.get("reason", "Target / Stop-Loss"))
        mode = trade.get("mode", "PAPER")
        strategy_label = trade.get("strategy_name") or trade.get("strategy") or "ILSME_Sniper"
        now_str = now_ist().strftime("%H:%M:%S")

        is_profit = net_pnl >= 0
        header = "🎯 <b>TRADE CLOSED — PROFIT BOOKED</b>" if is_profit else "🛑 <b>TRADE CLOSED — STOP-LOSS HIT</b>"
        trend_icon = "🟢" if is_profit else "🔴"
        pnl_str = f"+₹{net_pnl:,.2f}" if is_profit else f"-₹{abs(net_pnl):,.2f}"
        gross_str = f"+₹{gross_pnl:,.2f}" if gross_pnl >= 0 else f"-₹{abs(gross_pnl):,.2f}"
        pct_gain = ((exit_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0

        mode_tag = "📝 PAPER" if mode == "PAPER" else "⚡ LIVE"

        message = (
            f"{header}\n\n"
            f"{trend_icon} <b>Contract:</b> <b>{symbol}</b>\n"
            f"🧠 <b>Strategy:</b> <code>{strategy_label}</code>\n"
            f"💵 <b>Entry:</b> ₹{entry_price:.2f} ➜ <b>Exit:</b> ₹{exit_price:.2f} ({pct_gain:+.1f}%)\n"
            f"📦 <b>Quantity:</b> {quantity}\n"
            f"💰 <b>Gross P&L:</b> {gross_str}\n"
            f"💸 <b>Charges & Tax:</b> -₹{total_charges:.2f}\n"
            f"{trend_icon} <b>Net Realized P&L:</b> <code>{pnl_str}</code>\n"
            f"📋 <b>Exit Reason:</b> {reason}\n"
            f"🏷 <b>Mode:</b> {mode_tag} | ⏱ <b>Time:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_scaling_advisory(self, stats: Dict[str, Any]):
        """Notifies operator when statistical conditions are met to scale capital up."""
        now_str = now_ist().strftime("%H:%M:%S")
        trades = stats.get("total_trades", 0)
        pf = stats.get("profit_factor", 0.0)
        winrate = stats.get("win_rate", 0.0)
        max_dd = stats.get("max_drawdown_pct", 0.0)
        avg_slip = stats.get("avg_slippage", 0.0)

        message = (
            f"🚀 <b>SYSTEM SCALING ADVISORY (GREEN LIGHT)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Milestone Achieved:</b> Statistical criteria met for Capital Scale-Up!\n\n"
            f"📊 <b>Track Record:</b>\n"
            f"  • Completed Trades: <code>{trades}</code>\n"
            f"  • Profit Factor: <code>{pf:.2f}</code>\n"
            f"  • Win Rate: <code>{winrate:.1f}%</code>\n"
            f"  • Max Drawdown: <code>{max_dd:.1f}%</code>\n"
            f"  • Average Slippage: <code>{avg_slip:.2f} pts</code>\n\n"
            f"💡 <b>Recommendation:</b> Allocation can be safely increased by <b>+25% capital</b>.\n"
            f"⏱ <b>Timestamp:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_discard_alert(self, reason: str, stats: Dict[str, Any]):
        """Dispatches high-priority quarantine alert when system health limits are breached."""
        now_str = now_ist().strftime("%H:%M:%S")
        curr_dd = stats.get("drawdown_pct", 0.0)
        consec_losses = stats.get("consecutive_losses", 0)

        message = (
            f"🛑 <b>SYSTEM HEALTH ALERT: QUARANTINE TRIGGERED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>Critical Violation:</b> <b>{reason}</b>\n\n"
            f"📉 <b>Breach Metrics:</b>\n"
            f"  • Current Drawdown: <code>{curr_dd:.1f}%</code>\n"
            f"  • Consecutive Losses: <code>{consec_losses}</code>\n\n"
            f"🔒 <b>Action Required:</b> Halt trading immediately. Review risk settings.\n"
            f"⏱ <b>Timestamp:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_panic_triggered(self, reason: str = "Operator Manual Panic"):
        """Emergency circuit breaker notification."""
        now_str = now_ist().strftime("%H:%M:%S")
        message = (
            f"🚨 <b>EMERGENCY CIRCUIT BREAKER ACTIVATED</b>\n\n"
            f"⚠️ <b>Action:</b> Panic switch triggered! All open positions liquidated at market.\n"
            f"🛑 <b>Reason:</b> {reason}\n"
            f"🔒 <b>State:</b> Trading Engine HALTED\n"
            f"⏱ <b>Timestamp:</b> {now_str} IST"
        )
        self.send_message_async(message)

    def notify_eod_summary(self, state_mgr: Any, mode_override: Optional[str] = None):
        """
        Sends clean, meaningful End of Day (EOD) Performance Reports.
        """
        if not self.enabled:
            return False, "Telegram notifications disabled"

        if hasattr(state_mgr, "check_and_perform_daily_rollover"):
            state_mgr.check_and_perform_daily_rollover()

        date_str = now_ist().strftime("%d %b %Y")
        now_str = now_ist().strftime("%H:%M:%S")

        overall_success = True
        overall_detail = "Reports sent successfully"

        # Check which mode was active today
        is_live_active = getattr(state_mgr, "execution_mode", "PAPER") == "REAL" or len(getattr(state_mgr, "completed_trades", [])) > 0

        
        # 1. LIVE REPORT (if real trades were taken or mode is REAL)
        if is_live_active:
            trades = list(getattr(state_mgr, "completed_trades", []))
            gross = float(getattr(state_mgr, "realized_pnl", 0.0))
            brokerage = float(getattr(state_mgr, "total_brokerage", 0.0))
            net = float(getattr(state_mgr, "net_pnl", gross - brokerage))
            
            rms = getattr(state_mgr, "broker_rms", {})
            net_equity = float(rms.get("net", 0.0) or getattr(state_mgr, "equity", 0.0))
            
            total = len(trades)
            wins = sum(1 for t in trades if float(t.get("net_pnl", 0.0)) > 0)
            losses = sum(1 for t in trades if float(t.get("net_pnl", 0.0)) <= 0)
            winrate = (wins / total * 100.0) if total > 0 else 0.0

            net_icon = "🟢" if net >= 0 else "🔴"
            net_prefix = "+" if net >= 0 else "-"
            gross_prefix = "+" if gross >= 0 else "-"

            trade_lines = []
            for t in trades[-10:]:
                t_sym = t.get("symbol", "OPT")
                t_net = float(t.get("net_pnl", 0.0))
                t_icon = "✅" if t_net >= 0 else "❌"
                trade_lines.append(f"  {t_icon} <code>{t_sym}</code>: {t_net:+,.2f}")
            breakdown = "\n".join(trade_lines) if trade_lines else "  <i>No positions executed today</i>"

            msg = (
                f"📊 <b>END OF DAY REPORT — {date_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷 <b>Mode:</b> ⚡ <b>REAL LIVE TRADING</b>\n"
                f"🎯 <b>Result:</b> {wins}W / {losses}L (<code>{winrate:.0f}% Win Rate</code>)\n"
                f"🔢 <b>Trades Taken:</b> {total}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Gross P&L:</b> <code>{gross_prefix}₹{abs(gross):,.2f}</code>\n"
                f"💸 <b>Brokerage & Taxes:</b> <code>-₹{brokerage:,.2f}</code>\n"
                f"{net_icon} <b>Net Realized P&L:</b> <code>{net_prefix}₹{abs(net):,.2f}</code>\n\n"
                f"💼 <b>Broker Net Balance:</b> ₹{net_equity:,.2f}\n\n"
                f"📋 <b>Today's Trades:</b>\n{breakdown}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <i>Generated at {now_str} IST</i>"
            )
            res_live, det_live = self.send_message_sync(msg)
            if not res_live:
                overall_success = False
                overall_detail = det_live

        # 2. PAPER REPORT (if paper mode or paper trades taken)
        paper_trades = list(getattr(state_mgr, "paper_completed_trades", []))
        paper_status = getattr(state_mgr, "paper_agent_status", "IDLE")
        should_send_paper = (paper_status == "RUNNING" or len(paper_trades) > 0 or getattr(state_mgr, "execution_mode", "PAPER") == "PAPER" or mode_override == "PAPER")

        if should_send_paper and not is_live_active:
            paper_gross = float(getattr(state_mgr, "paper_realized_pnl", 0.0))
            paper_brokerage = float(getattr(state_mgr, "paper_total_brokerage", 0.0))
            paper_net = float(getattr(state_mgr, "paper_net_pnl", paper_gross - paper_brokerage))
            paper_cap = float(getattr(state_mgr, "paper_capital", 50000.0))
            paper_total = len(paper_trades)
            paper_wins = sum(1 for t in paper_trades if float(t.get("net_pnl", 0.0)) > 0)
            paper_losses = sum(1 for t in paper_trades if float(t.get("net_pnl", 0.0)) <= 0)
            paper_winrate = (paper_wins / paper_total * 100.0) if paper_total > 0 else 0.0

            net_icon = "🟢" if paper_net >= 0 else "🔴"
            net_prefix = "+" if paper_net >= 0 else "-"
            gross_prefix = "+" if paper_gross >= 0 else "-"

            paper_lines = []
            for t in paper_trades[-10:]:
                t_sym = t.get("symbol", "OPT")
                t_net = float(t.get("net_pnl", 0.0))
                t_icon = "✅" if t_net >= 0 else "❌"
                paper_lines.append(f"  {t_icon} <code>{t_sym}</code>: {t_net:+,.2f}")
            paper_breakdown = "\n".join(paper_lines) if paper_lines else "  <i>No paper trades executed today</i>"

            msg_paper = (
                f"📊 <b>END OF DAY REPORT — {date_str}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏷 <b>Mode:</b> 📝 <b>PAPER SIMULATION</b>\n"
                f"🎯 <b>Result:</b> {paper_wins}W / {paper_losses}L (<code>{paper_winrate:.0f}% Win Rate</code>)\n"
                f"🔢 <b>Trades Taken:</b> {paper_total}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Gross P&L:</b> <code>{gross_prefix}₹{abs(paper_gross):,.2f}</code>\n"
                f"💸 <b>Simulated Charges:</b> <code>-₹{paper_brokerage:,.2f}</code>\n"
                f"{net_icon} <b>Net Realized P&L:</b> <code>{net_prefix}₹{abs(paper_net):,.2f}</code>\n\n"
                f"💼 <b>Paper Capital:</b> ₹{paper_cap:,.2f}\n\n"
                f"📋 <b>Today's Trades:</b>\n{paper_breakdown}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⏱ <i>Generated at {now_str} IST</i>"
            )
            res_paper, det_paper = self.send_message_sync(msg_paper)
            if not res_paper:
                overall_success = False
                overall_detail = det_paper

        return overall_success, overall_detail


class TelegramBotController:
    """
    Listens for inbound Telegram bot commands from the user to provide 2-way remote control,
    matching angelone-swing functionality.
    
    Supported commands:
    - /status: Shows live system state, active positions, daily P&L, balance
    - /positions: Detailed active open option contracts with live LTP and unrealized P&L
    - /eod: Immediately generates and sends the End of Day (EOD) Report
    - /trades: Lists today's closed trades with Gross PnL, Brokerage, and Net PnL
    - /start [paper|live]: Starts paper or live trading agent
    - /stop: Pauses active trading agent
    - /squareoff or /panic: Emergency liquidation of all active positions
    - /help: Shows command list
    """
    def __init__(self, notifier: TelegramNotifier, state_manager: Any, orchestrator: Any = None):
        self.notifier = notifier
        self.state_mgr = state_manager
        self.orchestrator = orchestrator
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        with self._lock:
            if self.is_running():
                return True

            if not self.notifier.enabled:
                logger.info("[TELEGRAM_BOT] Disabled in settings.")
                return False

            if not self.notifier.bot_token or not self.notifier.chat_id:
                logger.warning("[TELEGRAM_BOT] Missing bot_token or chat_id.")
                return False

            self._running = True
            self._thread = threading.Thread(
                target=self._poll_loop,
                daemon=True,
                name="TelegramBotController"
            )
            self._thread.start()
            logger.info(f"[TELEGRAM_BOT] 2-way bot controller started for Chat ID: {self.notifier.chat_id}")
            return True

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("[TELEGRAM_BOT] Controller stopped.")

    def _fetch_updates(self, offset: int, timeout: int = 10) -> List[Dict[str, Any]]:
        url = f"https://api.telegram.org/bot{self.notifier.bot_token}/getUpdates?offset={offset}&timeout={timeout}"
        req = urllib.request.Request(url, headers={"User-Agent": "SmartAPIOptionsAgent/2.0"})
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("ok", False):
                    return payload.get("result", [])
        return []

    def _poll_loop(self):
        logger.info("[TELEGRAM_BOT] Polling loop active.")
        while self._running:
            try:
                updates = self._fetch_updates(self._last_update_id, timeout=10)
                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id >= self._last_update_id:
                        self._last_update_id = update_id + 1

                    msg = update.get("message")
                    if msg:
                        self._process_message(msg)
            except Exception as e:
                time.sleep(2)

    def _process_message(self, message: Dict[str, Any]):
        chat = message.get("chat", {})
        cid = str(chat.get("id", "")).strip()
        text = str(message.get("text", "")).strip()

        if not text:
            return

        # Security check: authorize configured chat_id only
        if cid != self.notifier.chat_id:
            logger.warning(f"[TELEGRAM_BOT] Unauthorized access attempt from Chat ID: {cid}")
            self.notifier.send_message_async(
                "⛔ <b>Access Denied</b>\nThis bot is private to the account owner.",
                chat_id=cid
            )
            return

        parts = text.split()
        raw_cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        response = self.dispatch_command(raw_cmd, args)
        if response:
            self.notifier.send_message_async(response)

    def dispatch_command(self, cmd: str, args: List[str]) -> str:
        if cmd in ("/status", "status"):
            return self._cmd_status()
        elif cmd in ("/health", "health", "/ping", "ping"):
            return self._cmd_health()
        elif cmd in ("/positions", "positions"):
            return self._cmd_positions()
        elif cmd in ("/trades", "trades"):
            return self._cmd_trades()
        elif cmd in ("/eod", "eod", "/report", "report"):
            return self._cmd_eod()
        elif cmd in ("/start", "start"):
            return self._cmd_start(args)
        elif cmd in ("/start_real", "start_real", "/real", "real", "/start_live", "start_live", "/live", "live"):
            return self._cmd_start(["real"])
        elif cmd in ("/start_paper", "start_paper", "/paper", "paper"):
            return self._cmd_start(["paper"])
        elif cmd in ("/stop", "stop"):
            return self._cmd_stop()
        elif cmd in ("/squareoff", "squareoff", "/panic", "panic"):
            return self._cmd_squareoff()
        elif cmd in ("/help", "help"):
            return self._cmd_help()
        else:
            return (
                f"❓ Unknown command: <code>{cmd}</code>\n\n"
                "Use /help to see all available remote commands."
            )

    def _cmd_health(self) -> str:
        """Detailed server and stream diagnostic health check."""
        from smartapi_trader.utils.tz import now_ist
        now = now_ist()
        now_t = now.time()
        is_weekday = (now.weekday() < 5)
        is_mkt_hours = is_weekday and (datetime.time(9, 15) <= now_t <= datetime.time(15, 30))
        
        stream_client = getattr(self.orchestrator, "stream_client", None)
        is_ws_conn = getattr(stream_client, "is_connected", False) if stream_client else False
        total_ticks = getattr(stream_client, "total_ticks_received", 0) if stream_client else 0
        last_tick_t = getattr(stream_client, "last_tick_time", 0.0) if stream_client else 0.0
        sec_since_tick = int(time.time() - last_tick_t) if last_tick_t > 0 else -1

        paper_status = getattr(self.state_mgr, "paper_agent_status", "PAUSED")
        real_status = getattr(self.state_mgr, "real_agent_status", "PAUSED")
        panic = getattr(self.state_mgr, "is_panic_active", False)

        feed_badge = "🟢 CONNECTED" if is_ws_conn else "🔴 DISCONNECTED"
        if sec_since_tick >= 0 and sec_since_tick < 60:
            tick_badge = f"🟢 Flowing ({sec_since_tick}s ago | {total_ticks:,} total)"
        elif sec_since_tick >= 60:
            tick_badge = f"⚠️ Idle ({sec_since_tick}s ago | {total_ticks:,} total)"
        else:
            tick_badge = "⚪ No ticks recorded"

        mkt_badge = "🟢 ACTIVE (09:15 - 15:30 IST)" if is_mkt_hours else "⚪ CLOSED (Pre/Post Market or Weekend)"

        health_ok = True
        if is_mkt_hours:
            if not is_ws_conn or panic:
                health_ok = False

        overall_badge = "✅ ALL SYSTEMS HEALTHY & RUNNING AS EXPECTED" if health_ok else "⚠️ ABNORMALITY DETECTED"

        return (
            f"🩺 <b>SERVER HEALTH & DIAGNOSTIC REPORT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕒 <b>Server Time:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f"🏛 <b>Market Session:</b> {mkt_badge}\n"
            f"🚦 <b>Overall Status:</b> <b>{overall_badge}</b>\n\n"
            f"📡 <b>SmartAPI Stream:</b> {feed_badge}\n"
            f"📊 <b>Tick Ingestion:</b> {tick_badge}\n"
            f"📝 <b>Paper Agent:</b> <code>{paper_status}</code>\n"
            f"⚡ <b>Real Live Agent:</b> <code>{real_status}</code>\n"
            f"🚨 <b>Panic State:</b> {'🚨 ACTIVE' if panic else '✅ NORMAL'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Send /status for capital & PnL, or /positions for active trades.</i>"
        )

    def _cmd_status(self) -> str:
        mode = self.state_mgr.execution_mode
        paper_status = getattr(self.state_mgr, "paper_agent_status", "PAUSED")
        real_status = getattr(self.state_mgr, "real_agent_status", "PAUSED")
        panic = getattr(self.state_mgr, "is_panic_active", False)
        
        open_pos = [p for p in self.state_mgr.positions.values() if p.is_open]
        pos_count = len(open_pos)

        if mode == "PAPER":
            cap = getattr(self.state_mgr, "paper_capital", 0.0)
            avail = getattr(self.state_mgr, "paper_available_margin", 0.0)
            pnl = getattr(self.state_mgr, "paper_net_pnl", 0.0)
            trades_count = len(getattr(self.state_mgr, "paper_completed_trades", []))
        else:
            cap = getattr(self.state_mgr, "equity", 0.0)
            avail = getattr(self.state_mgr, "available_margin", 0.0)
            pnl = getattr(self.state_mgr, "net_pnl", 0.0)
            trades_count = getattr(self.state_mgr, "trades_taken_today", 0)

        # Broker live balance telemetry
        rms = getattr(self.state_mgr, "broker_rms", {})
        live_avail = float(rms.get("availablecash", 0.0) or rms.get("net", 0.0) or 0.0)
        is_synced = rms.get("is_live_synced", False)
        min_cap = 50000.0
        if self.orchestrator and hasattr(self.orchestrator, "settings"):
            min_cap = float(self.orchestrator.settings.get("risk", {}).get("min_capital_required", 50000.0))

        live_cap_badge = (
            f"🟢 ₹{live_avail:,.2f}" if live_avail >= min_cap
            else f"🔴 ₹{live_avail:,.2f} (Below ₹{min_cap:,.0f} Min)"
        ) if is_synced else "⚪ Not Connected"

        pnl_icon = "🟢" if pnl >= 0 else "🔴"
        pnl_display = f"{pnl_icon} ₹{pnl:+,.2f}"

        status_flag = "🚨 PANIC / HALTED" if panic else ("🟢 ACTIVE" if (paper_status == "RUNNING" or real_status == "RUNNING") else "🟡 PAUSED")

        # Spot indices
        spots = getattr(self.state_mgr, "spot_levels", {})
        nifty_spot = spots.get("NIFTY", {}).get("spot", 0.0)
        bnf_spot = spots.get("BANKNIFTY", {}).get("spot", 0.0)
        indices_line = f"📈 <b>Live Spots:</b> NIFTY: <code>{nifty_spot:,.2f}</code> | BNF: <code>{bnf_spot:,.2f}</code>\n"

        return (
            f"🤖 <b>OPTIONS SNIPER ENGINE STATUS</b>\n\n"
            f"🏷 <b>Execution Mode:</b> <code>{mode}</code>\n"
            f"🚦 <b>System State:</b> {status_flag}\n"
            f"{indices_line}"
            f"📝 <b>Paper Agent:</b> {paper_status}\n"
            f"⚡ <b>Real Live Agent:</b> {real_status}\n\n"
            f"💼 <b>Active Capital:</b> ₹{cap:,.2f}\n"
            f"💳 <b>Available Margin:</b> ₹{avail:,.2f}\n"
            f"🏦 <b>Live Angel One Cash:</b> {live_cap_badge}\n"
            f"💰 <b>Today's Net P&L:</b> <code>{pnl_display}</code>\n"
            f"📊 <b>Active Positions:</b> {pos_count}\n"
            f"🔢 <b>Trades Taken:</b> {trades_count}\n\n"
            f"Send /health for diagnostics, /positions for trades, or /help for menu."
        )

    def _cmd_positions(self) -> str:
        open_pos = [p for p in self.state_mgr.positions.values() if p.is_open]
        if not open_pos:
            return "📭 <b>No active open positions.</b> Strategy is currently scanning for liquidity sweeps."

        lines = ["📊 <b>ACTIVE OPEN POSITIONS:</b>\n"]
        for p in open_pos:
            ltp = p.current_ltp
            pnl = (ltp - p.entry_price) * p.quantity
            icon = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{icon} <b>{p.symbol}</b>\n"
                f"   Qty: {p.quantity} | Entry: ₹{p.entry_price:.2f} | LTP: ₹{ltp:.2f}\n"
                f"   SL: ₹{p.stop_loss:.2f} | TP1: ₹{p.target_1:.2f}\n"
                f"   Unrealized P&L: <code>₹{pnl:+,.2f}</code>\n"
            )
        return "\n".join(lines)

    def _cmd_trades(self) -> str:
        real_trades = list(getattr(self.state_mgr, "completed_trades", []))
        paper_trades = list(getattr(self.state_mgr, "paper_completed_trades", []))

        if not real_trades and not paper_trades:
            return "📝 <b>No trades completed yet today (Neither Real nor Paper).</b>"

        lines = []
        if real_trades:
            lines.append("⚡ <b>REAL LIVE TRADES TODAY:</b>")
            for t in real_trades[-5:]:
                net = float(t.get("net_pnl", 0.0))
                icon = "🟢" if net >= 0 else "🔴"
                lines.append(
                    f"{icon} <b>{t.get('symbol')}</b>\n"
                    f"   Entry: ₹{t.get('entry_price', 0):.2f} ➔ Exit: ₹{t.get('exit_price', 0):.2f} (Qty: {t.get('quantity', 0)})\n"
                    f"   Gross: ₹{t.get('gross_pnl', 0):+,.2f} | Charges: -₹{t.get('total_charges', 0):.2f}\n"
                    f"   Net P&L: <code>₹{net:+,.2f}</code>"
                )
            lines.append("")

        if paper_trades:
            lines.append("📝 <b>PAPER TRADES TODAY:</b>")
            for t in paper_trades[-5:]:
                net = float(t.get("net_pnl", 0.0))
                icon = "🟢" if net >= 0 else "🔴"
                lines.append(
                    f"{icon} <b>{t.get('symbol')}</b>\n"
                    f"   Entry: ₹{t.get('entry_price', 0):.2f} ➔ Exit: ₹{t.get('exit_price', 0):.2f} (Qty: {t.get('quantity', 0)})\n"
                    f"   Gross: ₹{t.get('gross_pnl', 0):+,.2f} | Charges: -₹{t.get('total_charges', 0):.2f}\n"
                    f"   Net P&L: <code>₹{net:+,.2f}</code>"
                )

        return "\n".join(lines)

    def _cmd_eod(self) -> str:
        self.notifier.notify_eod_summary(self.state_mgr)
        return "📬 <i>End of Day (EOD) Report dispatched above!</i>"

    def _cmd_start(self, args: List[str]) -> str:
        sub = args[0].lower() if args else "paper"
        if sub in ("real", "live"):
            # 1. Verify broker credentials & active session
            auth_mgr = getattr(self.orchestrator, "auth_manager", None)
            if auth_mgr:
                if not auth_mgr.is_configured() or auth_mgr.is_simulated:
                    return (
                        "⛔ <b>CANNOT START REAL TRADING AGENT</b>\n\n"
                        "Angel One SmartAPI credentials are not configured or invalid in Settings.\n"
                        "Please configure valid API Key, Client Code, PIN, and TOTP Secret before arming live execution."
                    )
                # Refresh live RMS balance directly from Angel One
                try:
                    rms_res = auth_mgr.fetch_rms_balance()
                    if rms_res.get("status") and "data" in rms_res:
                        self.state_mgr.update_broker_rms(rms_res["data"])
                    else:
                        err = rms_res.get("message", "Broker RMS query failed")
                        return (
                            f"⛔ <b>CANNOT START REAL TRADING AGENT</b>\n\n"
                            f"Failed to verify live RMS balance with Angel One:\n"
                            f"<code>{err}</code>\n\n"
                            f"Live trading cannot be armed without active broker margin confirmation."
                        )
                except Exception as e:
                    logger.error(f"[TELEGRAM_BOT] Exception refreshing RMS: {e}")
                    return (
                        f"⛔ <b>CANNOT START REAL TRADING AGENT</b>\n\n"
                        f"Broker RMS verification error: <code>{e}</code>"
                    )

            # 2. Get minimum capital requirement
            min_cap = 50000.0
            if self.orchestrator and hasattr(self.orchestrator, "settings"):
                min_cap = float(self.orchestrator.settings.get("risk", {}).get("min_capital_required", 50000.0))

            # 3. Check capital adequacy and arm real agent
            success, msg = self.state_mgr.start_real_agent(min_capital=min_cap)
            if not success:
                rms = getattr(self.state_mgr, "broker_rms", {})
                avail = float(rms.get("availablecash", 0.0) or rms.get("net", 0.0) or 0.0)
                return (
                    f"⛔ <b>CANNOT START REAL TRADING AGENT</b>\n\n"
                    f"⚠️ <b>Insufficient Account Capital:</b>\n"
                    f"• Available Angel One Balance: <code>₹{avail:,.2f}</code>\n"
                    f"• Minimum Capital Required: <code>₹{min_cap:,.2f}</code>\n\n"
                    f"<i>Under the strict 1.5% risk management rule, 1 lot NIFTY option risk (~₹750) requires at least ₹{min_cap:,.0f} balance. Live execution remains locked until funds are deposited into your Angel One account.</i>"
                )
            return "⚡ <b>Real Live Trading Agent ARMED!</b> Live orders enabled."
        else:
            self.state_mgr.start_paper_agent()
            return "📝 <b>Paper Trading Agent STARTED!</b> Virtual sandbox armed."

    def _cmd_stop(self) -> str:
        self.state_mgr.pause_paper_agent()
        self.state_mgr.pause_real_agent()
        return "⏸ <b>Trading Agents PAUSED.</b> Scanning paused."

    def _cmd_squareoff(self) -> str:
        self.state_mgr.trigger_panic()
        # Square off open positions
        for p in list(self.state_mgr.positions.values()):
            if p.is_open:
                p.is_open = False
                self.state_mgr.record_completed_trade(
                    pnl=p.unrealized_pnl,
                    entry_price=p.entry_price,
                    exit_price=p.current_ltp,
                    quantity=p.quantity,
                    symbol=p.symbol,
                    is_paper=(self.state_mgr.execution_mode == "PAPER")
                )
        return "🚨 <b>EMERGENCY SQUARE-OFF COMPLETE!</b> All positions liquidated and engine halted."

    def _cmd_help(self) -> str:
        return (
            "🤖 <b>OPTIONS SNIPER TELEGRAM COMMANDS</b>\n\n"
            "📊 <b>Market & Session:</b>\n"
            "• <code>/status</code> — System state, daily P&L, balance, agent status\n"
            "• <code>/health</code> — Server diagnostics, stream latency, market checks\n"
            "• <code>/positions</code> — Live active open contracts & unrealized P&L\n"
            "• <code>/trades</code> — Today's completed trades with charges\n"
            "• <code>/eod</code> — Generate and send End of Day performance report\n\n"
            "🕹 <b>Remote Engine Control:</b>\n"
            "• <code>/start paper</code> — Start paper trading agent\n"
            "• <code>/start live</code> — Arm real live Angel One execution\n"
            "• <code>/stop</code> — Pause active trading agent\n"
            "• <code>/squareoff</code> — Emergency Panic! Liquidate all contracts\n"
            "• <code>/help</code> — Show this commands menu"
        )

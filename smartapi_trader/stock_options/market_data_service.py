"""
Market Data & Quantitative Technical Metrics Service for NSE Stocks.
Aggregates underlying spot prices, technical indicators (VWAP, EMA, RSI, ATR),
relative strength, volume ratios, and option chain metrics.
"""

import re
import time
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS, HIGH_BETA_SYMBOLS, is_high_beta_stock
from smartapi_trader.utils.logger import logger


class StockMarketDataService:
    """
    Supplies validated market data, multi-timeframe technical indicators,
    and option contract pricing for shortlisted NSE F&O stocks.
    """

    def __init__(self, universe_mgr: Optional[StockUniverseManager] = None, smart_api: Optional[Any] = None, stream_client: Optional[Any] = None):
        self.universe_mgr = universe_mgr or StockUniverseManager()
        self.smart_api = smart_api
        self.stream_client = stream_client
        self._price_cache: Dict[str, Dict[str, Any]] = {}
        self._last_cache_time = 0.0
        self._ltp_cache: Dict[str, Tuple[float, float]] = {}  # token -> (ltp, timestamp)
        self._spot_quote_cache: Dict[str, Dict[str, Any]] = {}  # symbol -> {ltp, open, high, low, close, volume, ts}
        self._candle_cache: Dict[str, Tuple[List[Any], float]] = {}  # symbol -> (bars, ts)
        self._oi_snapshot_cache: Dict[str, Tuple[int, float]] = {}  # token -> (initial_oi, ts)
        self._invalid_spot_tokens: Dict[str, float] = {}  # symbol -> timestamp when token failed AB4046
        self._resolved_nse_tokens: Dict[str, str] = {}  # symbol -> verified NSE equity token from instruments DB
        self._last_rest_ts: float = 0.0

    def _resolve_nse_token(self, symbol: str) -> str:
        """Resolves NSE equity token, checking instruments DB fallback if a static token failed."""
        sym = symbol.upper().strip()
        if sym in self._resolved_nse_tokens:
            return self._resolved_nse_tokens[sym]
        tok = str(NSE_FO_STOCKS.get(sym, {}).get("token_nse") or "").strip()
        if sym not in self._invalid_spot_tokens and tok:
            return tok
        # Fallback lookup in instruments.db ({sym}-EQ)
        try:
            with self.universe_mgr._get_connection() as conn:
                row = conn.execute(
                    "SELECT token FROM instruments WHERE symbol = ? AND exch_seg = 'NSE' LIMIT 1",
                    (f"{sym}-EQ",)
                ).fetchone()
                if row and row[0]:
                    resolved = str(row[0]).strip()
                    self._resolved_nse_tokens[sym] = resolved
                    self._invalid_spot_tokens.pop(sym, None)
                    return resolved
        except Exception:
            pass
        return tok

    def _throttle_rest(self, min_gap: float = 0.36):
        """Enforces <= ~2.7 req/sec spacing for SmartAPI REST endpoints."""
        now = time.time()
        elapsed = now - self._last_rest_ts
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        self._last_rest_ts = time.time()

    def _batch_fetch_spot_quotes(self, symbols: List[str], ttl_seconds: float = 20.0) -> None:
        """
        Batch-fetches live NSE equity quotes (ltp, open, high, low, close, volume)
        via SmartAPI getMarketData(mode="FULL") in chunks of 40 tokens.
        Never mutates static NSE_FO_STOCKS metadata.
        """
        smart_conn = self._get_active_smart_api()
        if not smart_conn or not symbols:
            return

        now = time.time()
        tok_to_sym: Dict[str, str] = {}
        pending_tokens: List[str] = []
        for sym in symbols:
            s = sym.upper().strip()
            cached = self._spot_quote_cache.get(s)
            if cached and (now - cached.get("ts", 0.0)) < ttl_seconds:
                continue
            tok = str(NSE_FO_STOCKS.get(s, {}).get("token_nse") or "").strip()
            if tok and tok.isdigit():
                tok_to_sym[tok] = s
                pending_tokens.append(tok)

        if not pending_tokens:
            return

        for i in range(0, len(pending_tokens), 40):
            chunk = pending_tokens[i:i + 40]
            try:
                self._throttle_rest(0.36)
                res = smart_conn.getMarketData(mode="FULL", exchangeTokens={"NSE": chunk})
                if res and isinstance(res, dict) and res.get("status") and res.get("data", {}).get("fetched"):
                    fetch_ts = time.time()
                    for item in res["data"]["fetched"]:
                        tok = str(item.get("symbolToken") or "").strip()
                        sym = tok_to_sym.get(tok)
                        if not sym:
                            tsym = str(item.get("tradingSymbol") or "").upper().replace("-EQ", "")
                            sym = tsym if tsym in NSE_FO_STOCKS else None
                        if not sym:
                            continue
                        ltp = float(item.get("ltp") or 0.0)
                        if ltp <= 0:
                            continue
                        quote = {
                            "ltp": ltp,
                            "open": float(item.get("open") or 0.0),
                            "high": float(item.get("high") or 0.0),
                            "low": float(item.get("low") or 0.0),
                            "close": float(item.get("close") or 0.0),
                            "volume": int(item.get("tradeVolume") or 0),
                            "ts": fetch_ts,
                        }
                        self._spot_quote_cache[sym] = quote
                        if tok:
                            self._ltp_cache[f"NSE_{tok}"] = (ltp, fetch_ts)
            except Exception as e:
                self._notify_rate_limit_if_detected(str(e), "NSE batch quotes")
                logger.debug(f"[MARKET_DATA] Batch quote fetch failed: {e}")

    def _fetch_intraday_candles(self, symbol: str, token: str, ttl_seconds: float = 120.0) -> List[List[Any]]:
        """Fetches recent 5-minute OHLCV candles from SmartAPI with short caching."""
        now = time.time()
        cached = self._candle_cache.get(symbol)
        if cached and (now - cached[1]) < ttl_seconds:
            return cached[0]

        smart_conn = self._get_active_smart_api()
        if not smart_conn or not token or not str(token).isdigit():
            return []

        try:
            self._throttle_rest(0.36)
            from_dt = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d 09:15")
            to_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
            res = smart_conn.getCandleData({
                "exchange": "NSE",
                "symboltoken": str(token),
                "interval": "FIVE_MINUTE",
                "fromdate": from_dt,
                "todate": to_dt,
            })
            if res and isinstance(res, dict) and res.get("status") and res.get("data"):
                bars = res["data"]
                self._candle_cache[symbol] = (bars, time.time())
                return bars
            elif res and isinstance(res, dict) and not res.get("status"):
                self._notify_rate_limit_if_detected(res.get("message"), f"NSE candles ({symbol})")
        except Exception as e:
            self._notify_rate_limit_if_detected(str(e), f"NSE candles ({symbol})")
            logger.debug(f"[MARKET_DATA] Candle fetch failed for {symbol}: {e}")
        return cached[0] if cached else []

    @staticmethod
    def _compute_real_candle_indicators(candles: List[List[Any]], fallback_spot: float) -> Optional[Dict[str, Any]]:
        """Computes real VWAP, EMA9, EMA21, RSI14, ATR14, and Volume Ratio from 5m OHLCV bars."""
        if not candles or len(candles) < 5:
            return None

        parsed: List[Tuple[str, float, float, float, float, float]] = []
        for b in candles:
            try:
                parsed.append((str(b[0]), float(b[1]), float(b[2]), float(b[3]), float(b[4]), float(b[5] or 0.0)))
            except Exception:
                continue

        if len(parsed) < 5:
            return None

        latest_date = parsed[-1][0][:10]
        session_bars = [b for b in parsed if b[0][:10] == latest_date] or parsed

        # 1. Session Volume-Weighted Average Price (VWAP)
        tp_vol_sum = 0.0
        vol_sum = 0.0
        for _, _, h, l, c, v in session_bars:
            tp = (h + l + c) / 3.0
            if v > 0:
                tp_vol_sum += tp * v
                vol_sum += v
        if vol_sum > 0:
            vwap = round(tp_vol_sum / vol_sum, 2)
        else:
            s_high = max(b[2] for b in session_bars)
            s_low = min(b[3] for b in session_bars)
            vwap = round((s_high + s_low + fallback_spot) / 3.0, 2)

        # 2. EMA 9 & EMA 21
        closes = [b[4] for b in parsed]
        k9 = 2.0 / 10.0
        k21 = 2.0 / 22.0
        ema9 = closes[0]
        ema21 = closes[0]
        for c in closes[1:]:
            ema9 = (c * k9) + (ema9 * (1.0 - k9))
            ema21 = (c * k21) + (ema21 * (1.0 - k21))

        # 3. 14-period RSI
        period = min(14, len(closes) - 1)
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent_deltas = deltas[-period:]
        avg_gain = sum(max(0.0, d) for d in recent_deltas) / max(1, period)
        avg_loss = sum(max(0.0, -d) for d in recent_deltas) / max(1, period)
        if avg_loss == 0.0:
            rsi = 80.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        # 4. 14-period ATR (on 5m bars) + session range context
        trs: List[float] = []
        for i in range(1, len(parsed)):
            _, _, h, l, _, _ = parsed[i]
            prev_c = parsed[i - 1][4]
            trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))
        atr_sample = trs[-14:] if trs else [max(0.5, parsed[-1][2] - parsed[-1][3])]
        atr_5m = sum(atr_sample) / len(atr_sample)
        session_range = max(b[2] for b in session_bars) - min(b[3] for b in session_bars)
        atr_14 = round(max(atr_5m * 3.0, session_range * 0.65), 2)

        # 5. Real Volume Ratio (latest 5m bar vs 20-bar volume SMA)
        vols = [b[5] for b in parsed if b[5] > 0]
        if len(vols) >= 3:
            prior_vols = vols[-21:-1] if len(vols) > 2 else vols[:-1]
            sma_vol = sum(prior_vols) / max(1, len(prior_vols))
            vol_ratio = round(vols[-1] / max(1.0, sma_vol), 2)
        else:
            vol_ratio = 1.0

        return {
            "vwap": round(vwap, 2),
            "ema9": round(ema9, 2),
            "ema21": round(ema21, 2),
            "rsi_14": round(rsi, 1),
            "atr_14": round(atr_14, 2),
            "volume_ratio": vol_ratio,
            "session_high": round(max(b[2] for b in session_bars), 2),
            "session_low": round(min(b[3] for b in session_bars), 2),
            "session_open": round(session_bars[0][1], 2),
            "bars_used": len(parsed),
        }

    def get_stock_technical_summary(self, symbol: str, include_candles: bool = True) -> Optional[Dict[str, Any]]:
        """
        Computes multi-timeframe quantitative technical metrics for a stock.
        Uses live SmartAPI quotes, real 5-minute OHLCV indicators (VWAP, EMA9/21, RSI14, ATR, Volume Ratio),
        and live NFO option-chain Open Interest / Bid-Ask spreads when connected.
        """
        symbol = symbol.upper().strip()
        if symbol in ("ALL_FO", "ALL", "AUTO_DISCOVER", ""):
            return None
        if symbol not in NSE_FO_STOCKS:
            logger.warning(f"[MARKET_DATA] Stock {symbol} not in eligible NSE F&O universe. Skipping.")
            return None

        meta = NSE_FO_STOCKS[symbol]
        base_p = float(meta.get("base_price", 1000.0))
        token_nse = str(meta.get("token_nse") or "").strip()

        live_spot = None
        real_high = None
        real_low = None
        real_open = None
        real_close = None
        day_volume = 0

        # Check fresh batched quote cache first (populated by rank_and_shortlist_stocks)
        cached_q = self._spot_quote_cache.get(symbol)
        now = time.time()
        if cached_q and (now - cached_q.get("ts", 0.0)) < 25.0:
            live_spot = cached_q.get("ltp")
            real_high = cached_q.get("high") or None
            real_low = cached_q.get("low") or None
            real_open = cached_q.get("open") or None
            real_close = cached_q.get("close") or None
            day_volume = int(cached_q.get("volume") or 0)

        smart_conn = self._get_active_smart_api()
        if smart_conn and not live_spot and token_nse:
            try:
                self._throttle_rest(0.36)
                res = smart_conn.ltpData(exchange="NSE", tradingsymbol=f"{symbol}-EQ", symboltoken=token_nse)
                if res and isinstance(res, dict) and res.get("status") and res.get("data"):
                    d = res["data"]
                    live_spot = float(d.get("ltp", 0.0))
                    h = float(d.get("high", 0.0))
                    l = float(d.get("low", 0.0))
                    o = float(d.get("open", 0.0))
                    c = float(d.get("close", 0.0))
                    if h > 0: real_high = h
                    if l > 0: real_low = l
                    if o > 0: real_open = o
                    if c > 0: real_close = c
                    if live_spot and live_spot > 0:
                        self._spot_quote_cache[symbol] = {
                            "ltp": live_spot, "open": o, "high": h, "low": l, "close": c, "volume": 0, "ts": time.time()
                        }
                        self._ltp_cache[f"NSE_{token_nse}"] = (live_spot, time.time())
            except Exception as e:
                logger.debug(f"[MARKET_DATA] Live quote fetch for {symbol} failed: {e}")

        is_live_quote = bool(live_spot and live_spot > 0)
        spot = round(float(live_spot), 2) if is_live_quote else round(base_p, 2)
        day_high = round(real_high, 2) if (real_high and real_high > 0) else round(max(spot * 1.008, spot), 2)
        day_low = round(real_low, 2) if (real_low and real_low > 0) else round(min(spot * 0.992, spot), 2)
        day_open = round(real_open, 2) if (real_open and real_open > 0) else spot
        prev_close = round(real_close, 2) if (real_close and real_close > 0) else day_open

        # Compute real 5m candle indicators when SmartAPI is connected and requested
        candle_metrics = None
        if include_candles and smart_conn and token_nse:
            candles = self._fetch_intraday_candles(symbol, token_nse)
            candle_metrics = self._compute_real_candle_indicators(candles, spot)

        if candle_metrics:
            vwap = candle_metrics["vwap"]
            ema9 = candle_metrics["ema9"]
            ema21 = candle_metrics["ema21"]
            rsi = candle_metrics["rsi_14"]
            atr_14 = candle_metrics["atr_14"]
            vol_ratio = candle_metrics["volume_ratio"]
            data_source = "LIVE_CANDLES"
        else:
            vwap = round((day_high + day_low + spot) / 3.0, 2)
            real_range = max(0.5, day_high - day_low)
            atr_14 = round(real_range if (real_high and real_low) else (spot * 0.015), 2)
            intraday_move = ((spot - day_open) / day_open) * 100.0 if day_open > 0 else 0.0
            ema9 = round((spot * 0.6) + (vwap * 0.4), 2)
            ema21 = round((day_open * 0.5) + (vwap * 0.5), 2)
            rsi = round(50.0 + min(35.0, max(-35.0, ((spot - vwap) / real_range) * 50.0)), 1) if real_range > 0 else 50.0
            vol_ratio = 1.0 if not is_live_quote else round(1.0 + min(1.5, abs(intraday_move) * 0.35), 2)
            data_source = "LIVE_QUOTE_ONLY" if is_live_quote else "OFFLINE_FALLBACK"

        intraday_change_pct = round(((spot - day_open) / day_open) * 100.0, 2) if day_open > 0 else 0.0
        prev_close_chg_pct = round(((spot - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0

        # Directional bias requires both VWAP and EMA alignment
        is_bullish = (spot >= vwap and ema9 >= ema21 and intraday_change_pct >= -0.1)
        is_bearish = (spot <= vwap and ema9 <= ema21 and intraday_change_pct <= 0.1)
        if not is_bullish and not is_bearish:
            is_bullish = spot >= vwap
        opt_type = "CE" if is_bullish else "PE"

        # Resolve both ATM CE and PE contracts for real option chain / OI telemetry
        ce_contract = self.universe_mgr.resolve_stock_option_contract(
            symbol=symbol, spot_price=spot, option_type="CE", strike_offset=0
        )
        pe_contract = self.universe_mgr.resolve_stock_option_contract(
            symbol=symbol, spot_price=spot, option_type="PE", strike_offset=0
        )
        contract = ce_contract if opt_type == "CE" else pe_contract

        strike_val = float(contract.get("strike", spot)) if contract else spot
        default_exp = (datetime.now() + timedelta(days=25)).strftime("%d-%b-%Y").upper()
        expiry_str = contract.get("expiry", default_exp) if contract else default_exp

        # Fetch real NFO option chain FULL data (LTP, OI, Volume, Bid/Ask Spread) for CE + PE in 1 API call
        ce_tok = str(ce_contract.get("symboltoken") or ce_contract.get("token") or "").strip() if ce_contract else ""
        pe_tok = str(pe_contract.get("symboltoken") or pe_contract.get("token") or "").strip() if pe_contract else ""
        live_chain: Dict[str, Dict[str, Any]] = {}
        if include_candles and smart_conn:
            nfo_tokens = [t for t in (ce_tok, pe_tok) if t and t.isdigit()]
            if nfo_tokens:
                try:
                    self._throttle_rest(0.36)
                    m_res = smart_conn.getMarketData(mode="FULL", exchangeTokens={"NFO": nfo_tokens})
                    if m_res and isinstance(m_res, dict) and m_res.get("status") and m_res.get("data", {}).get("fetched"):
                        for f_data in m_res["data"]["fetched"]:
                            ftok = str(f_data.get("symbolToken") or "").strip()
                            ltp_v = float(f_data.get("ltp") or 0.0)
                            oi_v = int(f_data.get("opnInterest") or 0)
                            vol_v = int(f_data.get("tradeVolume") or 0)
                            depth = f_data.get("depth") or {}
                            buys = depth.get("buy") or []
                            sells = depth.get("sell") or []
                            bid_v = float(buys[0].get("price") or 0.0) if buys else 0.0
                            ask_v = float(sells[0].get("price") or 0.0) if sells else 0.0
                            if bid_v <= 0: bid_v = round(ltp_v * 0.995, 2)
                            if ask_v <= 0: ask_v = round(ltp_v * 1.005, 2)
                            mid_v = (bid_v + ask_v) / 2.0
                            spread_v = round(((ask_v - bid_v) / mid_v) * 100.0, 2) if mid_v > 0 else 0.0
                            live_chain[ftok] = {
                                "ltp": ltp_v,
                                "oi": oi_v,
                                "volume": vol_v,
                                "bid": bid_v,
                                "ask": ask_v,
                                "spread_pct": spread_v,
                            }
                            if ftok and ftok not in self._oi_snapshot_cache and oi_v > 0:
                                self._oi_snapshot_cache[ftok] = (oi_v, time.time())
                except Exception as e:
                    logger.debug(f"[STOCK_DATA] Live option chain query failed for {symbol}: {e}")

        # Theoretical fallback pricing only when real broker option LTP is unavailable
        ce_intrinsic = max(0.0, spot - strike_val)
        pe_intrinsic = max(0.0, strike_val - spot)
        dist_pct = abs(spot - strike_val) / max(1.0, spot)
        time_val = max(0.5, (spot * 0.02) * math.exp(-dist_pct * 8.0))
        ce_calc_prem = round(max(0.5, ce_intrinsic + time_val), 2)
        pe_calc_prem = round(max(0.5, pe_intrinsic + time_val), 2)

        ce_live = live_chain.get(ce_tok, {})
        pe_live = live_chain.get(pe_tok, {})
        ce_prem = round(ce_live["ltp"], 2) if ce_live.get("ltp", 0) > 0 else ce_calc_prem
        pe_prem = round(pe_live["ltp"], 2) if pe_live.get("ltp", 0) > 0 else pe_calc_prem
        indicative_prem = ce_prem if opt_type == "CE" else pe_prem

        ce_oi = int(ce_live.get("oi") or 0)
        pe_oi = int(pe_live.get("oi") or 0)
        pcr_oi = round(pe_oi / max(1, ce_oi), 2) if (ce_oi > 0 or pe_oi > 0) else None
        primary_live = ce_live if opt_type == "CE" else pe_live
        primary_spread_pct = float(primary_live.get("spread_pct") or 0.0)
        primary_oi = int(primary_live.get("oi") or 0)
        primary_opt_vol = int(primary_live.get("volume") or 0)

        # Real Option Chain / OI description (zero random/synthetic percentages)
        if ce_oi > 0 or pe_oi > 0:
            base_oi = self._oi_snapshot_cache.get(ce_tok if opt_type == "CE" else pe_tok, (primary_oi, 0))[0]
            oi_chg_pct = round(((primary_oi - base_oi) / max(1, base_oi)) * 100.0, 2) if base_oi > 0 else 0.0
            oi_buildup_type = "LIVE_OPTION_CHAIN"
            oi_buildup = (
                f"Live Option Chain: PCR {pcr_oi:.2f} | CE OI: {ce_oi:,} | PE OI: {pe_oi:,} "
                f"| Primary Strike OI: {primary_oi:,} ({oi_chg_pct:+.1f}% session delta, Vol: {primary_opt_vol:,})"
            )
        else:
            oi_buildup_type = "UNAVAILABLE"
            oi_buildup = "Live option chain OI unavailable — evaluate price/volume/VWAP structure only."

        # High-Beta Volatility & Dynamic Risk:Reward Calculation
        is_high_beta = is_high_beta_stock(symbol) or (atr_14 / max(1.0, spot)) >= 0.022
        target_rr = 2.0 if is_high_beta else 1.5

        vwap_diff_pct = round(((spot - vwap) / vwap) * 100.0, 2) if vwap > 0 else 0.0
        vwap_status = f"Trading Above VWAP (+{vwap_diff_pct}%)" if spot >= vwap else f"Trading Below VWAP ({vwap_diff_pct}%)"

        # Sectoral Confluence Assessment (skip redundant peer REST fetches during Stage-1 coarse screen)
        if include_candles:
            sector_confluence = self.get_sector_confluence(symbol, intended_bias="BULLISH" if is_bullish else "BEARISH")
        else:
            sector_confluence = self.get_sector_confluence(symbol, intended_bias="BULLISH" if is_bullish else "BEARISH", allow_rest=False)

        atm_chain = [
            {
                "strike": float(ce_contract.get("strike", strike_val)) if ce_contract else strike_val,
                "option_type": "CE",
                "expiry": ce_contract.get("expiry", expiry_str) if ce_contract else expiry_str,
                "current_ltp": ce_prem,
                "bid": ce_live.get("bid", round(ce_prem * 0.995, 2)),
                "ask": ce_live.get("ask", round(ce_prem * 1.005, 2)),
                "spread_pct": ce_live.get("spread_pct", 1.0),
                "open_interest": ce_oi,
                "volume": int(ce_live.get("volume") or 0),
                "is_live": bool(ce_live.get("ltp", 0) > 0),
            },
            {
                "strike": float(pe_contract.get("strike", strike_val)) if pe_contract else strike_val,
                "option_type": "PE",
                "expiry": pe_contract.get("expiry", expiry_str) if pe_contract else expiry_str,
                "current_ltp": pe_prem,
                "bid": pe_live.get("bid", round(pe_prem * 0.995, 2)),
                "ask": pe_live.get("ask", round(pe_prem * 1.005, 2)),
                "spread_pct": pe_live.get("spread_pct", 1.0),
                "open_interest": pe_oi,
                "volume": int(pe_live.get("volume") or 0),
                "is_live": bool(pe_live.get("ltp", 0) > 0),
            }
        ]

        return {
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "sector": meta.get("sector", "Equities"),
            "data_source": data_source,
            "spot": spot,
            "day_open": day_open,
            "prev_close": prev_close,
            "day_high": day_high,
            "day_low": day_low,
            "intraday_change_pct": intraday_change_pct,
            "day_change_pct": prev_close_chg_pct,
            "day_volume": day_volume,
            "vwap": vwap,
            "vwap_status": vwap_status,
            "oi_buildup": oi_buildup,
            "oi_buildup_type": oi_buildup_type,
            "pcr_oi": pcr_oi,
            "primary_spread_pct": primary_spread_pct,
            "primary_oi": primary_oi,
            "sector_confluence": sector_confluence,
            "breaking_news_sentiment": "No automated news feed connected — assess pure price, VWAP, volume & OI confluence.",
            "news_headline": "No automated news feed connected",
            "sentiment": "BULLISH" if is_bullish else "BEARISH",
            "is_high_beta": is_high_beta,
            "beta_profile": "HIGH_BETA" if is_high_beta else "STANDARD",
            "target_rr": target_rr,
            "target_rr_label": f"1:{target_rr:.1f} R:R",
            "atm_option_chain": atm_chain,
            "ema9": ema9,
            "ema21": ema21,
            "rsi_14": rsi,
            "atr_14": atr_14,
            "atr_pct": round((atr_14 / max(1.0, spot)) * 100.0, 2),
            "volume_ratio": vol_ratio,
            "trend": "BULLISH" if is_bullish else "BEARISH",
            "recommended_option_type": opt_type,
            "strike": strike_val,
            "expiry": expiry_str,
            "tradingsymbol": contract.get("tradingsymbol", f"{symbol}_{opt_type}") if contract else f"{symbol}_{opt_type}",
            "token": contract.get("symboltoken", "") if contract else "",
            "indicative_premium": indicative_prem,
            "lot_size": int(contract.get("lotsize") or meta.get("lot_size", 250)) if contract else meta.get("lot_size", 250),
            "strike_step": meta.get("strike_step", 10.0),
            "tick_size": meta.get("tick_size", 0.05),
            "corporate_events": "No automated corporate-action calendar connected",
            "timestamp": datetime.now().isoformat()
        }

    def rank_and_shortlist_stocks(
        self,
        candidate_symbols: Optional[List[str]] = None,
        max_shortlist: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Two-stage quantitative ranking of the eligible stock universe:
        Stage 1: Fast batched quote scan across all candidate symbols.
        Stage 2: Deep 5m OHLCV candle + live NFO option chain enrichment for top candidates.
        """
        clean_symbols = []
        if candidate_symbols:
            clean_symbols = [s.upper().strip() for s in candidate_symbols if s.upper().strip() in NSE_FO_STOCKS]
        if not clean_symbols:
            clean_symbols = list(NSE_FO_STOCKS.keys())

        # Stage 1: Fast batch quote pull (reduces ~200 HTTP calls to ~5 batched calls)
        self._batch_fetch_spot_quotes(clean_symbols)

        def _score_summary(summary: Dict[str, Any]) -> float:
            vol_score = min(30.0, (summary["volume_ratio"] / 2.0) * 30.0)
            trend_score = 30.0 if (
                (summary["trend"] == "BULLISH" and summary["rsi_14"] >= 55 and summary["ema9"] >= summary["ema21"]) or
                (summary["trend"] == "BEARISH" and summary["rsi_14"] <= 45 and summary["ema9"] <= summary["ema21"])
            ) else 12.0
            liq_score = 20.0
            if summary.get("primary_spread_pct", 0.0) > 2.5:
                liq_score = 0.0
            elif summary.get("primary_spread_pct", 0.0) > 1.5:
                liq_score = 10.0
            atr_score = min(20.0, (summary["atr_14"] / max(1.0, summary["spot"])) * 1000.0)

            overextension_penalty = 0.0
            vwap = float(summary.get("vwap") or 0.0)
            spot = float(summary.get("spot") or 0.0)
            rsi = float(summary.get("rsi_14") or 50.0)
            if vwap > 0 and spot > 0:
                dist_pct = abs(spot - vwap) / vwap * 100.0
                if dist_pct > 1.4:
                    overextension_penalty += min(25.0, (dist_pct - 1.4) * 20.0)
            if rsi > 75 or rsi < 25:
                overextension_penalty += 15.0

            summary["is_overextended"] = (overextension_penalty > 0.0)
            return round(max(0.0, vol_score + trend_score + liq_score + atr_score - overextension_penalty), 2)

        coarse_scored = []
        for sym in clean_symbols:
            summary = self.get_stock_technical_summary(sym, include_candles=False)
            if not summary:
                continue
            summary["ranking_score"] = _score_summary(summary)
            coarse_scored.append(summary)

        coarse_scored.sort(key=lambda x: x["ranking_score"], reverse=True)

        # Stage 2: Enrich top candidates with real 5m OHLCV indicators + live NFO option chain OI/spread
        smart_conn = self._get_active_smart_api()
        deep_pool_size = min(len(coarse_scored), max(max_shortlist * 2, 8))
        if smart_conn:
            scored = []
            for item in coarse_scored[:deep_pool_size]:
                enriched = self.get_stock_technical_summary(item["symbol"], include_candles=True)
                if enriched:
                    enriched["ranking_score"] = _score_summary(enriched)
                    scored.append(enriched)
            scored.sort(key=lambda x: x["ranking_score"], reverse=True)
        else:
            scored = coarse_scored

        # Cross-Industry Diversification:
        # Guarantee uncorrelated trades across different sectors (Banking, IT, Auto, Metals, Defense, etc.)
        diversified: List[Dict[str, Any]] = []
        sector_counts: Dict[str, int] = {}
        max_per_sector = 1 if len(clean_symbols) >= 8 else 2

        for item in scored:
            sec = item.get("sector", "General")
            broad_sec = "Banking" if "Bank" in sec else (
                "IT" if "Information Technology" in sec else (
                    "Auto" if "Auto" in sec else (
                        "Metals" if "Metal" in sec else (
                            "Pharma" if "Pharma" in sec or "Healthcare" in sec else (
                                "Energy" if "Energy" in sec or "Power" in sec or "Oil" in sec else (
                                    "Defense" if "Defense" in sec or "Aerospace" in sec else sec
                                )
                            )
                        )
                    )
                )
            )
            if sector_counts.get(broad_sec, 0) < max_per_sector:
                diversified.append(item)
                sector_counts[broad_sec] = sector_counts.get(broad_sec, 0) + 1
            if len(diversified) >= max_shortlist:
                break

        # Fallback to fill up to max_shortlist if strict sector cap was too tight
        if len(diversified) < max_shortlist:
            for item in scored:
                if item not in diversified:
                    diversified.append(item)
                if len(diversified) >= max_shortlist:
                    break

        return diversified

    def get_sector_confluence(self, symbol: str, intended_bias: str = "BULLISH", allow_rest: bool = True) -> Dict[str, Any]:
        """
        Evaluates Sectoral Index and Sector Peer Breadth Confluence.
        Verifies if sector peers are moving in the same direction before confirming a breakout.
        """
        sym = symbol.upper().strip()
        sector_name = self.universe_mgr.get_sector_for_stock(sym)
        peers = self.universe_mgr.get_sector_peers(sym)

        if not peers:
            return {
                "sector": sector_name,
                "confluence_status": "CONFLUENCE_CONFIRMED",
                "breadth_score": 100.0,
                "aligned": True,
                "reason": f"Single stock allocation in {sector_name} sector."
            }

        peer_list = [p for p in peers[:5] if p in NSE_FO_STOCKS]
        if peer_list and allow_rest:
            self._batch_fetch_spot_quotes(peer_list)

        bullish_peers = 0
        total_evaluated = 0

        for peer in peer_list:
            p_meta = NSE_FO_STOCKS.get(peer)
            if not p_meta:
                continue
            q = self._spot_quote_cache.get(peer)
            if q and q.get("ltp", 0) > 0:
                spot = float(q["ltp"])
                ref_p = float(q.get("open") or q.get("close") or p_meta.get("base_price", spot))
            elif allow_rest:
                spot = self.get_spot_ltp(peer)
                q2 = self._spot_quote_cache.get(peer)
                if q2 and (q2.get("open") or q2.get("close")):
                    ref_p = float(q2.get("open") or q2.get("close"))
                else:
                    ref_p = float(p_meta.get("base_price", spot))
            else:
                continue
            total_evaluated += 1
            if spot >= ref_p:
                bullish_peers += 1

        if total_evaluated == 0:
            return {
                "sector": sector_name,
                "confluence_status": "CONFLUENCE_CONFIRMED",
                "breadth_score": 100.0,
                "aligned": True,
                "reason": "Peer baseline neutral."
            }

        breadth_pct = round((bullish_peers / total_evaluated) * 100.0, 1)
        is_bullish = (intended_bias.upper() in ("BULLISH", "CE"))

        if is_bullish:
            # Bullish trades require >= 50% sector peers positive
            aligned = (breadth_pct >= 50.0)
            status = "CONFLUENCE_CONFIRMED" if aligned else "SECTOR_DIVERGENCE_REJECTED"
            reason = (
                f"{sector_name} sector breadth confirms bullish breakout ({breadth_pct}% peers positive)."
                if aligned else
                f"Sector Divergence: {sector_name} sector is weak ({breadth_pct}% peers positive). High bear trap risk."
            )
        else:
            # Bearish trades require <= 50% sector peers positive
            aligned = (breadth_pct <= 50.0)
            status = "CONFLUENCE_CONFIRMED" if aligned else "SECTOR_DIVERGENCE_REJECTED"
            reason = (
                f"{sector_name} sector confirms bearish breakdown ({100.0 - breadth_pct}% peers negative)."
                if aligned else
                f"Sector Divergence: {sector_name} sector is resilient ({breadth_pct}% peers positive)."
            )

        return {
            "sector": sector_name,
            "confluence_status": status,
            "breadth_score": breadth_pct,
            "aligned": aligned,
            "reason": reason
        }

    def _get_active_auth_mgr(self):
        """Resolves active AuthManager instance through orchestrator context."""
        try:
            from smartapi_trader.web.app import ctx
            if ctx.orchestrator:
                return getattr(ctx.orchestrator, "auth_manager", None) or getattr(ctx.orchestrator, "auth_mgr", None)
        except Exception:
            pass
        return None

    def _get_active_smart_api(self):
        """Resolves connected SmartAPI instance directly or through orchestrator context."""
        auth = self._get_active_auth_mgr()
        if auth and getattr(auth, "smart_api", None):
            self.smart_api = auth.smart_api
            return self.smart_api
        try:
            from smartapi_trader.web.app import ctx
            if ctx.orchestrator and getattr(ctx.orchestrator, "smart_api", None):
                self.smart_api = ctx.orchestrator.smart_api
                return self.smart_api
        except Exception:
            pass
        if self.smart_api:
            return self.smart_api
        return None

    def _get_active_stream_client(self):
        """Resolves active WebSocket StreamClient directly or through orchestrator context."""
        if self.stream_client:
            return self.stream_client
        try:
            from smartapi_trader.web.app import ctx
            if ctx.orchestrator and getattr(ctx.orchestrator, "stream_client", None):
                self.stream_client = ctx.orchestrator.stream_client
                return self.stream_client
        except Exception:
            pass
        return None

    def _notify_rate_limit_if_detected(self, err_msg: Any, endpoint: str):
        """Dispatches throttled Telegram alert when Angel One HTTP 429 rate limit is encountered."""
        err_str = str(err_msg or "")
        if any(w in err_str.lower() for w in ("exceeding access rate", "429", "rate limit")):
            try:
                from smartapi_trader.web.app import ctx
                notifier = getattr(ctx.orchestrator, "notifier", None)
                if notifier and hasattr(notifier, "notify_broker_rate_limit"):
                    notifier.notify_broker_rate_limit(endpoint=endpoint, details=err_str)
            except Exception:
                pass

    def get_spot_ltp(self, symbol: str) -> float:
        """Returns underlying stock spot price from WebSocket stream, cached rate-limited REST, or universe base price."""
        sym = symbol.upper().strip()
        meta = NSE_FO_STOCKS.get(sym, {})
        base_p = meta.get("base_price", 1000.0)
        token = self._resolve_nse_token(sym)

        # 1. First check WebSocket live tick stream (do NOT mutate static base_price)
        stream = self._get_active_stream_client()
        if stream and token:
            ws_ltp = stream.get_latest_ltp(token)
            if ws_ltp and ws_ltp > 0:
                self._ltp_cache[f"NSE_{token}"] = (ws_ltp, time.time())
                if sym in self._spot_quote_cache:
                    self._spot_quote_cache[sym]["ltp"] = ws_ltp
                    self._spot_quote_cache[sym]["ts"] = time.time()
                return round(ws_ltp, 2)

        # 2. Check 3-second cache (or recent batch quote) to avoid hitting broker REST rate limits
        now = time.time()
        cache_key = f"NSE_{token}" if token else f"NSE_{sym}"
        cached = self._ltp_cache.get(cache_key)
        if cached and (now - cached[1]) < 3.0:
            return round(cached[0], 2)

        # Skip known invalid/missing tokens for 1 hour to prevent repeated AB4046 rate-limit burn
        inv_ts = self._invalid_spot_tokens.get(sym)
        if inv_ts and (now - inv_ts) < 3600.0:
            return round(cached[0], 2) if (cached and cached[0] > 0) else base_p

        # 3. Query broker REST
        smart_conn = self._get_active_smart_api()
        if smart_conn and token:
            try:
                self._throttle_rest(0.36)
                res = smart_conn.ltpData(
                    exchange="NSE",
                    tradingsymbol=f"{sym}-EQ",
                    symboltoken=token
                )
                if res and isinstance(res, dict) and res.get("status") and res.get("data"):
                    d = res["data"]
                    ltp = float(d.get("ltp") or 0.0)
                    if ltp > 0:
                        self._ltp_cache[cache_key] = (ltp, now)
                        self._spot_quote_cache[sym] = {
                            "ltp": ltp,
                            "open": float(d.get("open") or 0.0),
                            "high": float(d.get("high") or 0.0),
                            "low": float(d.get("low") or 0.0),
                            "close": float(d.get("close") or 0.0),
                            "volume": self._spot_quote_cache.get(sym, {}).get("volume", 0),
                            "ts": now,
                        }
                        return round(ltp, 2)
                elif res and isinstance(res, dict) and not res.get("status"):
                    err_msg = res.get('message') or ""
                    err_code = str(res.get('errorcode') or "")
                    if err_code == "AB4046" or "not found in scrip master" in err_msg.lower():
                        self._invalid_spot_tokens[sym] = now
                        alt_tok = self._resolve_nse_token(sym)
                        if alt_tok and alt_tok != token:
                            res2 = smart_conn.ltpData(exchange="NSE", tradingsymbol=f"{sym}-EQ", symboltoken=alt_tok)
                            if res2 and isinstance(res2, dict) and res2.get("status") and res2.get("data"):
                                d2 = res2["data"]
                                ltp2 = float(d2.get("ltp") or 0.0)
                                if ltp2 > 0:
                                    self._ltp_cache[f"NSE_{alt_tok}"] = (ltp2, now)
                                    return round(ltp2, 2)
                    self._notify_rate_limit_if_detected(err_msg, f"NSE spot ({sym})")
                    logger.debug(f"[MARKET_DATA] SmartAPI ltpData error for {sym}: {err_msg} ({err_code})")
            except Exception as e:
                self._notify_rate_limit_if_detected(str(e), f"NSE spot ({sym})")
                logger.debug(f"[MARKET_DATA] Live spot query for {sym} failed: {e}")

        # If recent cache exists (> 3s old), prefer it over hardcoded base_p
        if cached and cached[0] > 0:
            return round(cached[0], 2)

        return base_p

    def get_option_ltp(
        self,
        symbol: str,
        underlying: str,
        token: Optional[str] = None,
        strike: Optional[float] = None,
        option_type: Optional[str] = None,
        allow_modeled: bool = True
    ) -> float:
        """
        Retrieves real-time or modeled market LTP for a stock option contract.
        1. Checks active WebSocket stream for real-time tick.
        2. Checks recent 3-second REST cache.
        3. Queries Angel One SmartAPI ltpData directly (or AuthManager).
        4. If broker quote is unavailable:
           - If allow_modeled is False (e.g. active position trailing stop/target evaluation): returns 0.0 (NEVER fake exits!).
           - If allow_modeled is True: calculates dynamic option premium using
             underlying spot price + intrinsic/extrinsic time decay model for candidate screening.
        """
        symbol = str(symbol or "").strip()
        underlying = str(underlying or "").upper().strip()
        opt_type = str(option_type or "").upper().strip()
        if not opt_type:
            opt_type = "CE" if "CE" in symbol.upper() else "PE"

        strike_val = float(strike) if strike else 0.0
        if not strike_val and symbol:
            m = re.search(r'(\d+(?:\.\d+)?)\s*(CE|PE)', symbol, re.IGNORECASE)
            if m:
                try:
                    strike_val = float(m.group(1))
                    if not option_type:
                        opt_type = m.group(2).upper()
                except Exception:
                    pass

        tok_str = str(token).strip() if token else ""
        if not strike_val or not tok_str or not tok_str.isdigit() or " " in symbol:
            try:
                contract_meta = None
                if " " not in symbol and symbol:
                    contract_meta = self.universe_mgr.get_contract_by_symbol(symbol)
                if not contract_meta and underlying:
                    target_spot = strike_val if strike_val > 0 else self.get_spot_ltp(underlying)
                    contract_meta = self.universe_mgr.resolve_stock_option_contract(
                        underlying, spot_price=target_spot, option_type=opt_type
                    )
                if contract_meta:
                    if not strike_val:
                        strike_val = float(contract_meta.get("strike", 0.0))
                    real_tok = str(contract_meta.get("token") or contract_meta.get("symboltoken", "")).strip()
                    if real_tok and real_tok.isdigit():
                        token = real_tok
                        tok_str = real_tok
                        symbol = contract_meta.get("symbol") or contract_meta.get("tradingsymbol", symbol)
            except Exception as ex:
                logger.debug(f"[MARKET_DATA] Contract resolution failed for {symbol}: {ex}")

        tok_str = str(token).strip() if token else ""

        # 1. Check WebSocket live tick
        stream = self._get_active_stream_client()
        if stream and tok_str and tok_str.isdigit():
            ws_ltp = stream.get_latest_ltp(tok_str)
            if ws_ltp and ws_ltp > 0:
                self._ltp_cache[f"NFO_{tok_str}"] = (ws_ltp, time.time())
                return round(ws_ltp, 2)

        # 2. Check 3-second cache to protect against REST rate limiting
        now = time.time()
        cache_key = f"NFO_{tok_str}" if tok_str else f"NFO_{symbol}"
        cached = self._ltp_cache.get(cache_key)
        if cached and (now - cached[1]) < 3.0:
            return round(cached[0], 2)

        # 3. Query broker REST (AuthManager or SmartAPI)
        auth_mgr = self._get_active_auth_mgr()
        if auth_mgr and tok_str and tok_str.isdigit():
            try:
                live_ltp = auth_mgr.get_token_ltp("NFO", symbol, tok_str)
                if live_ltp and live_ltp > 0:
                    self._ltp_cache[cache_key] = (float(live_ltp), now)
                    return round(float(live_ltp), 2)
            except Exception as e:
                logger.debug(f"[MARKET_DATA] auth_mgr get_token_ltp query for {symbol} ({tok_str}) failed: {e}")

        smart_conn = self._get_active_smart_api()
        if smart_conn and tok_str and tok_str.isdigit():
            try:
                res = smart_conn.ltpData(exchange="NFO", tradingsymbol=symbol, symboltoken=tok_str)
                if res and isinstance(res, dict) and res.get("status") and res.get("data"):
                    live_ltp = float(res["data"].get("ltp") or 0.0)
                    if live_ltp > 0:
                        self._ltp_cache[cache_key] = (live_ltp, now)
                        return round(live_ltp, 2)
            except Exception as e:
                self._notify_rate_limit_if_detected(str(e), f"NFO option ({symbol})")
                logger.debug(f"[MARKET_DATA] Broker ltpData query for {symbol} ({tok_str}) failed: {e}")

        # If broker query failed but we have a recently cached LTP (< 60s), use it
        if cached and cached[0] > 0 and (now - cached[1]) < 60.0:
            return round(cached[0], 2)

        # If live quote unavailable and modeled pricing is NOT allowed (e.g. trailing stops / profit targets)
        if not allow_modeled:
            logger.warning(f"[MARKET_DATA] Real broker quote unavailable for {symbol} ({tok_str}) and allow_modeled=False. Refusing synthetic price.")
            return 0.0

        # 4. Dynamic spot-anchored pricing model (ONLY for screening / indicative pricing)
        spot = self.get_spot_ltp(underlying) if underlying else 0.0
        if spot <= 0 and strike_val > 0:
            spot = strike_val
        if strike_val <= 0:
            strike_val = spot

        intrinsic = max(0.0, spot - strike_val) if opt_type == "CE" else max(0.0, strike_val - spot)
        dist_pct = abs(spot - strike_val) / max(1.0, spot) if spot > 0 else 0.0
        base_time_val = spot * 0.02
        time_val = max(0.25, round(base_time_val * math.exp(-dist_pct * 7.5), 2))
        return round(max(0.10, intrinsic + time_val), 2)

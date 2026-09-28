import time
import pyotp
from typing import Tuple, Dict, Any, Optional
from SmartApi import SmartConnect
from smartapi_trader.utils.logger import logger

class AngelAuthManager:
    """
    Manages session lifecycle, TOTP generation, JWT tokens, and feed tokens
    for Angel One SmartAPI protocol.
    """
    def __init__(self, api_key: str, client_code: str, pin: str, totp_secret: str):
        self.api_key = api_key
        self.client_code = client_code
        self.pin = pin
        self.totp_secret = totp_secret
        
        self.smart_api: Optional[SmartConnect] = None
        self.jwt_token: str = ""
        self.refresh_token: str = ""
        self.feed_token: str = ""
        self.session_expiry: float = 0
        self.is_simulated: bool = False

    def is_configured(self) -> bool:
        """Checks if real API credentials are configured."""
        placeholder_keys = ["YOUR_SMARTAPI_API_KEY", "YOUR_CLIENT_CODE", "YOUR_PIN", "YOUR_BASE32_TOTP_SECRET", ""]
        return not (self.api_key in placeholder_keys or self.client_code in placeholder_keys or self.totp_secret in placeholder_keys)

    def initialize_session(self) -> Tuple[Optional[SmartConnect], str, str]:
        """
        Authenticates against Angel One SmartAPI using TOTP.
        Returns: (smart_api_instance, jwt_token, feed_token)
        """
        if not self.is_configured():
            logger.warning("[AUTH] Placeholder credentials detected. Initializing synthetic mock session for PAPER trading.")
            self.is_simulated = True
            self.jwt_token = f"simulated_jwt_{int(time.time())}"
            self.refresh_token = f"simulated_refresh_{int(time.time())}"
            self.feed_token = f"simulated_feed_{int(time.time())}"
            self.smart_api = SmartConnect(api_key="SIMULATED_KEY")
            return self.smart_api, self.jwt_token, self.feed_token

        try:
            logger.info(f"[AUTH] Initializing SmartConnect session for client: {self.client_code}...")
            self.smart_api = SmartConnect(api_key=self.api_key)
            totp = pyotp.TOTP(self.totp_secret).now()
            
            session_data = self.smart_api.generateSession(self.client_code, self.pin, totp)
            
            if not session_data or not session_data.get("status"):
                msg = session_data.get("message") if session_data else "Unknown error"
                logger.error(f"[AUTH] Angel One Authentication failed: {msg}")
                raise ConnectionRefusedError(f"Session Authentication Failed: {msg}")

            data = session_data.get("data", {})
            self.jwt_token = data.get("jwtToken", "")
            self.refresh_token = data.get("refreshToken", "")
            self.feed_token = self.smart_api.getfeedToken()
            # Sessions generally expire after 24h
            self.session_expiry = time.time() + (23 * 3600)
            self.is_simulated = False

            logger.info(f"[AUTH] Successfully authenticated! JWT Token: {self.jwt_token[:10]}*** | Feed Token: {self.feed_token[:8]}***")
            return self.smart_api, self.jwt_token, self.feed_token

        except Exception as e:
            logger.error(f"[AUTH] Exception during session initialization: {e}")
            logger.warning("[AUTH] Falling back to simulated credentials for paper execution.")
            self.is_simulated = True
            self.jwt_token = f"simulated_jwt_{int(time.time())}"
            self.refresh_token = f"simulated_refresh_{int(time.time())}"
            self.feed_token = f"simulated_feed_{int(time.time())}"
            self.smart_api = SmartConnect(api_key=self.api_key or "SIMULATED_KEY")
            return self.smart_api, self.jwt_token, self.feed_token

    def renew_token_if_needed(self) -> str:
        """Refreshes the JWT token before expiration."""
        if self.is_simulated or not self.smart_api:
            return self.jwt_token

        if time.time() > (self.session_expiry - 1800): # within 30 min of expiry
            try:
                logger.info("[AUTH] Refreshing session JWT tokens...")
                token_data = self.smart_api.generateToken(self.refresh_token)
                if token_data.get("status"):
                    self.jwt_token = token_data["data"]["jwtToken"]
                    self.feed_token = token_data["data"]["feedToken"]
                    self.session_expiry = time.time() + (23 * 3600)
                    logger.info("[AUTH] Tokens refreshed successfully.")
                else:
                    logger.warning(f"[AUTH] Token refresh failed: {token_data.get('message')}. Re-authenticating...")
                    self.initialize_session()
            except Exception as e:
                logger.error(f"[AUTH] Exception while refreshing token: {e}. Re-authenticating...")
                self.initialize_session()

        return self.jwt_token

    def fetch_rms_balance(self) -> Dict[str, Any]:
        """Queries Angel One RMS Limit endpoint for real margin data."""
        if not self.smart_api or self.is_simulated:
            return {
                "status": False,
                "message": "Live Angel One session not authenticated",
                "data": {
                    "net": 0.0,
                    "availablecash": 0.0,
                    "collateral": 0.0,
                    "utiliseddebits": 0.0,
                    "is_simulated": True
                }
            }

        try:
            logger.info("[AUTH] Fetching live RMS balance from Angel One...")
            res = self.smart_api.rmsLimit()
            if res and res.get("status"):
                data = res.get("data", {})
                logger.info(f"[AUTH] Live RMS fetched: Net={data.get('net')} Cash={data.get('availablecash')}")
                return {"status": True, "data": data}
            else:
                msg = res.get("message") if res else "Unknown RMS failure"
                logger.warning(f"[AUTH] RMS fetch returned error: {msg}")
                return {"status": False, "message": msg}
        except Exception as e:
            logger.error(f"[AUTH] Exception fetching RMS balance: {e}")
            return {"status": False, "message": str(e)}

    def fetch_spot_ltp(self) -> Dict[str, Dict[str, float]]:
        """Queries Angel One live/closing LTP for NIFTY 50, BANK NIFTY, and SENSEX."""
        if not self.smart_api or self.is_simulated:
            return {}

        results = {}
        index_queries = [
            ("NIFTY", "NSE", "Nifty 50", "99926000"),
            ("BANKNIFTY", "NSE", "Nifty Bank", "99926009"),
            ("SENSEX", "BSE", "SENSEX", "99919000")
        ]

        for key, exch, symbol, token in index_queries:
            try:
                res = self.smart_api.ltpData(exchange=exch, tradingsymbol=symbol, symboltoken=token)
                if res and res.get("status") and "data" in res:
                    d = res["data"]
                    results[key] = {
                        "spot": float(d.get("ltp", 0.0)),
                        "close": float(d.get("close", 0.0)),
                        "high": float(d.get("high", 0.0)),
                        "low": float(d.get("low", 0.0)),
                        "open": float(d.get("open", 0.0)),
                        "vwap": float(d.get("close", 0.0)),
                    }
                    logger.info(f"[AUTH] Live LTP from Angel One: {key} = ₹{d.get('ltp')}")
            except Exception as e:
                logger.error(f"[AUTH] Error fetching LTP for {key}: {e}")
        return results

    def get_token_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        """Queries Angel One SmartAPI for real-time Last Traded Price (LTP) of any instrument."""
        if not self.smart_api:
            return None
        try:
            res = self.smart_api.ltpData(exchange=exchange, tradingsymbol=symbol, symboltoken=str(token))
            if res and res.get("status") and "data" in res:
                return float(res["data"].get("ltp", 0.0))
        except Exception as e:
            logger.error(f"[AUTH] Error fetching live LTP for {symbol} ({token}): {e}")
        return None

    def get_option_liquidity_metrics(self, exchange: str, token: str) -> Dict[str, Any]:
        """Queries Angel One getMarketData FULL mode for Open Interest, Volume, and Bid-Ask Spread."""
        if not self.smart_api:
            return {"valid": True, "oi": 100000, "volume": 100000, "spread_pct": 0.5, "ltp": 0.0}
        try:
            res = self.smart_api.getMarketData(mode="FULL", exchangeTokens={exchange: [str(token)]})
            if res and res.get("status") and res.get("data", {}).get("fetched"):
                d = res["data"]["fetched"][0]
                oi = int(d.get("opnInterest", 0))
                volume = int(d.get("tradeVolume", 0))
                ltp = float(d.get("ltp", 0.0))
                
                # Check top-of-book depth
                depth = d.get("depth", {})
                buys = depth.get("buy", [])
                sells = depth.get("sell", [])
                best_bid = float(buys[0].get("price", 0.0)) if buys and buys[0].get("price") else ltp
                best_ask = float(sells[0].get("price", 0.0)) if sells and sells[0].get("price") else ltp
                
                spread_pct = round(((best_ask - best_bid) / best_ask * 100.0), 2) if best_ask > 0 else 0.0
                return {
                    "valid": True,
                    "oi": oi,
                    "volume": volume,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread_pct": spread_pct,
                    "ltp": ltp
                }
        except Exception as e:
            logger.error(f"[AUTH] Error querying liquidity metrics for {token}: {e}")
        return {"valid": True, "oi": 100000, "volume": 100000, "spread_pct": 0.5, "ltp": 0.0}

def initialize_broker_session(api_key: str, client_code: str, pin: str, totp_secret: str):
    """Convenience helper conforming to architectural blueprint."""
    manager = AngelAuthManager(api_key, client_code, pin, totp_secret)
    smart_api, auth_token, feed_token = manager.initialize_session()
    return smart_api, auth_token, feed_token

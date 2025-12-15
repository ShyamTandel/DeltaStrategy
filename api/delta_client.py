# api/delta_client.py
import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from django.conf import settings
import logging
logger = logging.getLogger(__name__)
# Configure BASE in settings as WITHOUT the /v2 suffix:
# DELTA_API_BASE = "https://cdn-ind.testnet.deltaex.org"
API_KEY = settings.DELTA_API_KEY
API_SECRET = settings.DELTA_API_SECRET
BASE = settings.DELTA_API_BASE.rstrip('/')  # ensure no trailing slash


class DeltaClient:
    API_PREFIX = "/v2"  # keep this single source of truth

    def __init__(self, debug: bool=False):
        self.api_key = API_KEY
        self.api_secret = API_SECRET
        self.base = BASE.rstrip('/')
        self.debug = debug
        self._server_offset = None  # Will be calculated on first auth error

        if not self.api_key or not self.api_secret:
            raise RuntimeError("Missing DELTA_API_KEY or DELTA_API_SECRET")

    def _get_server_time_offset(self):
        """
        Get the time offset between local and server time by making a test request
        and parsing the error response if it contains timing information.
        """
        if self._server_offset is not None:
            return self._server_offset
            
        # Make a test request to get server time from error response
        try:
            test_timestamp = str(int(time.time()))
            test_sig = self._sign("GET", "/orders", test_timestamp)
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "api-key": self.api_key,
                "signature": test_sig,
                "timestamp": test_timestamp,
                "User-Agent": "django-delta-bot/1.0"
            }
            
            response = requests.get(f"{self.base}/v2/orders", headers=headers, timeout=5)
            
            if response.status_code == 401:
                try:
                    error_data = response.json()
                    if (error_data.get('error', {}).get('code') == 'expired_signature' and
                        'context' in error_data['error']):
                        
                        context = error_data['error']['context']
                        server_time = context.get('server_time')
                        request_time = context.get('request_time')
                        
                        if server_time and request_time:
                            self._server_offset = server_time - request_time
                            if self.debug:
                                logger.info(f"🕐 Detected server time offset: {self._server_offset} seconds")
                            return self._server_offset
                except:
                    pass
            
        except:
            pass
            
        # Fallback to known offset from your error logs
        self._server_offset = 19800  # 5.5 hours based on your logs
        if self.debug:
            logger.info(f"🕐 Using fallback server time offset: {self._server_offset} seconds")
        return self._server_offset

    def _timestamp(self):
        # Delta live API expects seconds, not milliseconds
        return str(int(time.time()))

    def _full_path(self, path):
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith(self.API_PREFIX):
            path = self.API_PREFIX + path
        return path

    def _sign(self, method, path, timestamp, body=None, query_params=None):
        request_path = self._full_path(path)

        # Canonical query string
        querystring = ""
        if query_params:
            items = []
            for k in sorted(query_params.keys()):
                v = query_params[k]
                if isinstance(v, (list, tuple)):
                    for item in v:
                        items.append((k, str(item)))
                else:
                    items.append((k, str(v)))
            querystring = "?" + urlencode(items)

        # Body string
        body_str = json.dumps(body) if body else ""

        prehash = f"{method.upper()}{timestamp}{request_path}{querystring}{body_str}"

        sig = hmac.new(
            self.api_secret.encode(),
            prehash.encode(),
            hashlib.sha256
        ).hexdigest()

        if self.debug:
            logger.info("=== SIGN DEBUG ===")
            logger.info(f"method: {method}")
            logger.info(f"timestamp: {timestamp}")
            logger.info(f"path: {request_path}")
            logger.info(f"querystring: {querystring}")
            logger.info(f"body_str: {body_str}")
            logger.info(f"prehash: {prehash}")
            logger.info(f"signature: {sig}")
            logger.info("=================")

        return sig

    def _headers(self, method, path, body=None, query_params=None):
        ts = self._timestamp()
        sig = self._sign(method, path, ts, body, query_params)
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": self.api_key,
            "signature": sig,
            "timestamp": ts,
            "User-Agent": "python-delta-client"
        }

    def _make_auth_request(self, method, path, body=None, query_params=None):
        url = self.base + self._full_path(path)
        headers = self._headers(method, path, body, query_params)

        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=query_params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=body, params=query_params)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=headers, json=body, params=query_params)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=headers, params=query_params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if self.debug or response.status_code >= 400:
            logger.info(f"[{response.status_code}] {response.text}")

        response.raise_for_status()
        return response.json()

    # -------------------------
    # Public endpoints (no auth)
    # -------------------------
    def get_option_chain(self, underlying="BTC", expiry_date=None):
        """
        GET /v2/tickers
        """
        path = self._full_path("/tickers")
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": underlying
        }
        if expiry_date:
            params["expiry_date"] = expiry_date  # format DD-MM-YYYY

        url = self.base + path
        if self.debug:
            logger.info(f"GET {url} params={params}")
        r = requests.get(url, params=params, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()


    def place_order(self, body: dict):
        """
        POST /v2/orders
        Body must contain exactly either product_id or product_symbol (not both).
        """
        # Use the same pattern as _make_auth_request for consistency
        return self._make_auth_request("POST", "/orders", body=body)

    def get_positions(self):
        """GET /v2/positions/margined"""
        return self._make_auth_request("GET", "/positions/margined")

    def close_all_positions(self, body: dict = None):
        """POST /v2/positions/close_all - Close all margined positions"""
        if body is None:
            body = {
                "close_all_portfolio": True,
                "close_all_isolated": True,
                "user_id": 0
            }
        return self._make_auth_request("POST", "/positions/close_all", body=body)

    def get_wallet_balances(self):
        """GET /v2/wallet/balances"""
        return self._make_auth_request("GET", "/wallet/balances")


    def test_auth(self):
        """Test authentication with multiple possible endpoints"""
        endpoints = ["/positions/margined", "/wallet/balances"]
        
        for endpoint in endpoints:
            try:
                path = self._full_path(endpoint)
                url = self.base + path
                headers = self._headers("GET", endpoint)
                
                logger.info(f"Testing endpoint: {endpoint}")
                logger.info(f"URL: {url}")
                if self.debug:
                    logger.info(f"Headers: {headers}")
                
                r = requests.get(url, headers=headers)
                logger.info(f"Response: {r.status_code}")
                
                if r.status_code == 200:
                    logger.info(f"✅ Authentication successful with {endpoint}")
                    return r.json()
                elif r.status_code == 401:
                    logger.info(f"❌ Authentication failed (401) with {endpoint}")
                else:
                    logger.info(f"⚠️ Endpoint {endpoint} returned {r.status_code}: {r.text[:100]}")
                    
            except Exception as e:
                logger.info(f"Error testing {endpoint}: {e}")
        
        return None


# api/delta_client.py
import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from django.conf import settings

# Configure BASE in settings as WITHOUT the /v2 suffix:
# DELTA_API_BASE = "https://cdn-ind.testnet.deltaex.org"
API_KEY = settings.DELTA_API_KEY
API_SECRET = settings.DELTA_API_SECRET
BASE = settings.DELTA_API_BASE.rstrip('/')  # ensure no trailing slash


class DeltaClient:
    API_PREFIX = "/v2"  # keep this single source of truth

    def __init__(self, api_key=None, api_secret=None, base=None, debug: bool=False):
        self.api_key = api_key or API_KEY
        self.api_secret = api_secret or API_SECRET
        self.base = (base or BASE).rstrip('/')
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
                                print(f"🕐 Detected server time offset: {self._server_offset} seconds")
                            return self._server_offset
                except:
                    pass
            
        except:
            pass
            
        # Fallback to known offset from your error logs
        self._server_offset = 19800  # 5.5 hours based on your logs
        if self.debug:
            print(f"🕐 Using fallback server time offset: {self._server_offset} seconds")
        return self._server_offset

    def _timestamp(self) -> str:
        # Use standard UTC timestamp - Delta Exchange API accepts UTC timestamps
        # The server processes options at IST times but API signatures use UTC
        utc_timestamp = int(time.time())
        
        if self.debug:
            import datetime
            utc_dt = datetime.datetime.fromtimestamp(utc_timestamp, tz=datetime.timezone.utc)
            print(f"🕐 UTC timestamp: {utc_timestamp} ({utc_dt.strftime('%Y-%m-%d %H:%M:%S UTC')})")
            
        return str(utc_timestamp)

    def _full_path(self, path: str) -> str:
        """
        Return the canonical request path used by the API and signing:
        always starts with /v2. Accept input like "/tickers" or "tickers".
        """
        if not path.startswith('/'):
            path = '/' + path
        if not path.startswith(self.API_PREFIX):
            path = self.API_PREFIX + path
        return path

    def _sign(self, method: str, path: str, timestamp: str, body: dict | None = None, query_params: dict | None = None) -> str:
        """
        Create HMAC SHA256 signature.
        prehash = METHOD + TIMESTAMP + REQUEST_PATH + QUERYSTRING + BODY_STRING
        REQUEST_PATH must match request URL path (e.g. /v2/orders).
        """
        request_path = self._full_path(path)  # ensures /v2 prefix is present

        querystring = ""
        if query_params:
            # deterministic ordering
            # urlencode a list of sorted (key,value) pairs to match canonical ordering
            items = []
            for k in sorted(query_params.keys()):
                v = query_params[k]
                # handle list values
                if isinstance(v, (list, tuple)):
                    for item in v:
                        items.append((k, str(item)))
                else:
                    items.append((k, str(v)))
            querystring = "?" + urlencode(items)

        body_str = ""
        if body:
            # JSON without sorted keys to match API expectations
            body_str = json.dumps(body, separators=(', ', ': '))

        prehash = f"{method.upper()}{timestamp}{request_path}{querystring}{body_str}"

        # ensure secret is bytes
        key = self.api_secret if isinstance(self.api_secret, (bytes, bytearray)) else self.api_secret.encode()
        sig = hmac.new(key, prehash.encode(), hashlib.sha256).hexdigest()

        if self.debug:
            print("=== SIGN DEBUG ===")
            print("method:", method)
            print("timestamp:", timestamp)
            print("request_path:", request_path)
            print("querystring:", querystring)
            print("body_str:", body_str)
            print("PREHASH:", prehash)
            print("SIGNATURE:", sig)
            print("==================")

        return sig

    def _headers(self, method: str, path: str, body: dict | None = None, query_params: dict | None = None) -> dict:
        ts = self._timestamp()
        sig = self._sign(method, path, ts, body=body, query_params=query_params)
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": self.api_key,
            "signature": sig,
            "timestamp": ts,
            "User-Agent": "django-delta-bot/1.0"
        }

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
            print("GET", url, "params=", params)
        r = requests.get(url, params=params, headers={"Accept": "application/json"})
        r.raise_for_status()
        return r.json()

    # -------------------------
    # Authenticated endpoints
    # -------------------------
    def _make_auth_request(self, method: str, path: str, body: dict = None, query_params: dict = None):
        """Generic authenticated request method"""
        full_path = self._full_path(path)
        url = self.base + full_path
        headers = self._headers(method, path, body=body, query_params=query_params)
        
        if self.debug:
            print(f"{method} {url}")
            if body:
                print(f"BODY: {body}")
            if query_params:
                print(f"PARAMS: {query_params}")
        
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, params=query_params)
        elif method.upper() == "POST":
            r = requests.post(url, json=body, headers=headers, params=query_params)
        elif method.upper() == "PUT":
            r = requests.put(url, json=body, headers=headers, params=query_params)
        elif method.upper() == "DELETE":
            r = requests.delete(url, headers=headers, params=query_params)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if r.status_code >= 400:
            if self.debug:
                print(f"Response status {r.status_code}, response text:", r.text)
        
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
        endpoints = ["/orders", "/positions/margined", "/wallet/balances", "/accounts"]
        
        for endpoint in endpoints:
            try:
                path = self._full_path(endpoint)
                url = self.base + path
                headers = self._headers("GET", endpoint)
                
                print(f"Testing endpoint: {endpoint}")
                print(f"URL: {url}")
                if self.debug:
                    print(f"Headers: {headers}")
                
                r = requests.get(url, headers=headers)
                print(f"Response: {r.status_code}")
                
                if r.status_code == 200:
                    print(f"✅ Authentication successful with {endpoint}")
                    return r.json()
                elif r.status_code == 401:
                    print(f"❌ Authentication failed (401) with {endpoint}")
                else:
                    print(f"⚠️ Endpoint {endpoint} returned {r.status_code}: {r.text[:100]}")
                    
            except Exception as e:
                print(f"Error testing {endpoint}: {e}")
        
        return None


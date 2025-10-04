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

        if not self.api_key or not self.api_secret:
            raise RuntimeError("Missing DELTA_API_KEY or DELTA_API_SECRET")

    def _timestamp(self) -> str:
        return str(int(time.time()))

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
    def place_order(self, body: dict):
        """
        POST /v2/orders
        Body must contain exactly either product_id or product_symbol (not both).
        """
        path = self._full_path("/orders")
        url = self.base + path
        headers = self._headers("POST", path, body=body)
        if self.debug:
            print("POST", url)
            print("HEADERS:", headers)
            print("BODY:", body)
        r = requests.post(url, json=body, headers=headers)
        # If error, print debug info
        if r.status_code >= 400:
            print(f"Response status {r.status_code}, response text:", r.text)
            if self.debug:
                print("Request URL:", url)
                print("Request headers:", headers)
                print("Request body:", body)
        r.raise_for_status()
        return r.json()

    def get_positions(self):
        path = self._full_path("/positions/margined")
        url = self.base + path
        headers = self._headers("GET", path)
        if self.debug:
            print("GET", url, "HEADERS:", headers)
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

    def get_account_summary(self):
        path = "/wallet/balances"   # or /accounts for newer versions — check your API docs
        method = "GET"
        ts = self._timestamp()
        sig = self._sign(method, path, ts)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": self.api_key,
            "signature": sig,
            "timestamp": ts
        }

        url = self.base + path
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

    def test_auth(self):
        path = self._full_path("/wallet/balances")
        url = self.base + path
        headers = self._headers("GET", "/wallet/balances")
        print("Signature test headers:", headers)
        print("URL:", url)
        r = requests.get(url, headers=headers)
        print("Response:", r.status_code, r.text)


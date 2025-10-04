# import time
# import hmac
# import hashlib
# import requests
# from urllib.parse import urlencode
# from django.conf import settings

# def _generate_signature(secret: str, message: str) -> str:
#     return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

# def _build_query_string(params: dict) -> str:
#     if not params:
#         return ""
#     # includes leading '?'
#     return "?" + urlencode(params, doseq=True)

# def call_delta_private(method: str, path: str, params: dict = None, body: str = "") -> requests.Response:
#     """
#     method: 'GET' or 'POST'
#     path: endpoint path starting with /, e.g. '/v2/wallet/balances'
#     params: dict of query params (or None)
#     body: raw JSON string for POST ('' for GET)
#     """
#     base = "https://api.india.delta.exchange"
#     api_key = "cgjkCujQUy59UV4xHrTCTAt0nW781S"
#     api_secret = "oPpT0m3QbnsjFhyTCfxi8wXhlUR0VXDavZAhwNWr5rt2dP4Oj8rbXGgTgbIf"
#     if not api_key or not api_secret:
#         raise RuntimeError("DELTA_API_KEY or DELTA_API_SECRET not configured in settings")

#     query_string = _build_query_string(params or {})
#     timestamp = str(int(time.time()))  # seconds since epoch
#     # per docs: signature_data = method + timestamp + path + query_string + body
#     signature_data = method + timestamp + path + query_string + (body or "")
#     signature = _generate_signature(api_secret, signature_data)

#     # headers = {
#     #     "api-key": api_key,
#     #     "timestamp": timestamp,
#     #     "signature": signature,
#     #     "User-Agent": "django-delta-client",   # docs require User-Agent
#     #     "Accept": "application/json",
#     #     "Content-Type": "application/json",
#     # }
#     headers = {
#         "api-key": api_key,
#         "signature": signature,
#         "User-Agent": "django-delta-client", 
#     'Accept': 'application/json',
#      "Content-Type": "application/json",
#     }

#     r = requests.get('https://api.india.delta.exchange/v2/tickers', params={

#     }, headers = headers)
#     return r
#     # url = base.rstrip("/") + path
#     # # Use requests to call
#     # if method.upper() == "GET":
#     #     return requests.get(url, headers=headers, params=params or {}, timeout=10)
#     # elif method.upper() == "POST":
#     #     return requests.post(url, headers=headers, data=body or "{}", params=params or {}, timeout=10)
#     # else:
#     #     raise ValueError("Unsupported method")


import os
import time
import hmac
import hashlib
import json
import requests
from urllib.parse import urlencode
from django.conf import settings

API_KEY = settings.DELTA_API_KEY
API_SECRET = settings.DELTA_API_SECRET
BASE = settings.DELTA_API_BASE

class DeltaClient:
    def __init__(self, api_key=None, api_secret=None, base=None):
        self.api_key = api_key or API_KEY
        self.api_secret = api_secret.encode() if api_secret else API_SECRET
        self.base = base or BASE
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Missing DELTA_API_KEY/DELTA_API_SECRET")

    def _timestamp(self):
        # delta expects a timestamp header (docs: use same value when creating signature)
        return str(int(time.time()*1000))

    def _sign(self, method, path, timestamp, body=None, query_params=None):
        # signature = HMAC_SHA256(secret, method + timestamp + requestPath + query + body_hexdigest?)
        # Per docs: prehash string = method + timestamp + requestPath + queryParams + body (concatenate).
        # We'll follow the docs (string concat) and then hexdigest hex.
        request_path = path  # path should include leading /v2/...
        querystring = ""
        if query_params:
            # sort keys to be deterministic
            querystring = "?" + urlencode(query_params)
        body_str = ""
        if body:
            body_str = json.dumps(body, separators=(',', ':'))  # canonical JSON (no spaces)
        prehash = method.upper() + timestamp + request_path + querystring + body_str
        sig = hmac.new(self.api_secret, prehash.encode(), hashlib.sha256).hexdigest()
        return sig

    def _headers(self, method, path, body=None, query_params=None):
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

    # 1) Get option chain (tickers) - public (no auth needed)
    # using GET /tickers?contract_types=call_options,put_options&underlying_asset_symbols={}&expiry_date={DD-MM-YYYY}
    def get_option_chain(self, underlying="BTC", expiry_date=None):
        path = "/tickers"
        params = {
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": underlying
        }
        if expiry_date:
            params["expiry_date"] = expiry_date  # format DD-MM-YYYY
        r = requests.get(self.base + path, params=params, headers={"Accept":"application/json"})
        r.raise_for_status()
        return r.json()

    # 2) Place order
    def place_order(self, body):
        path = "/orders"
        headers = self._headers("POST", path, body=body)
        r = requests.post(self.base + path, json=body, headers=headers)
        r.raise_for_status()
        return r.json()

    # 3) Get margined positions (authenticated)
    def get_positions(self):
        path = "/positions/margined"
        headers = self._headers("GET", path)
        r = requests.get(self.base + path, headers=headers)
        r.raise_for_status()
        return r.json()

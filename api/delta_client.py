import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from django.conf import settings

def _generate_signature(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def _build_query_string(params: dict) -> str:
    if not params:
        return ""
    # includes leading '?'
    return "?" + urlencode(params, doseq=True)

def call_delta_private(method: str, path: str, params: dict = None, body: str = "") -> requests.Response:
    """
    method: 'GET' or 'POST'
    path: endpoint path starting with /, e.g. '/v2/wallet/balances'
    params: dict of query params (or None)
    body: raw JSON string for POST ('' for GET)
    """
    base = "https://api.india.delta.exchange"
    api_key = "cgjkCujQUy59UV4xHrTCTAt0nW781S"
    api_secret = "oPpT0m3QbnsjFhyTCfxi8wXhlUR0VXDavZAhwNWr5rt2dP4Oj8rbXGgTgbIf"
    if not api_key or not api_secret:
        raise RuntimeError("DELTA_API_KEY or DELTA_API_SECRET not configured in settings")

    query_string = _build_query_string(params or {})
    timestamp = str(int(time.time()))  # seconds since epoch
    # per docs: signature_data = method + timestamp + path + query_string + body
    signature_data = method + timestamp + path + query_string + (body or "")
    signature = _generate_signature(api_secret, signature_data)

    # headers = {
    #     "api-key": api_key,
    #     "timestamp": timestamp,
    #     "signature": signature,
    #     "User-Agent": "django-delta-client",   # docs require User-Agent
    #     "Accept": "application/json",
    #     "Content-Type": "application/json",
    # }
    headers = {
        "api-key": api_key,
        "signature": signature,
        "User-Agent": "django-delta-client", 
    'Accept': 'application/json',
     "Content-Type": "application/json",
    }

    r = requests.get('https://api.india.delta.exchange/v2/tickers', params={

    }, headers = headers)
    return r
    # url = base.rstrip("/") + path
    # # Use requests to call
    # if method.upper() == "GET":
    #     return requests.get(url, headers=headers, params=params or {}, timeout=10)
    # elif method.upper() == "POST":
    #     return requests.post(url, headers=headers, data=body or "{}", params=params or {}, timeout=10)
    # else:
    #     raise ValueError("Unsupported method")

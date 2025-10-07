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
        # Add a small buffer to account for network latency
        return str(int(time.time()) + 1)

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

    def check_target_and_close_positions(self, target_profit: float):
        """
        Check if target profit is achieved by calculating:
        target <= realized_pnl + unrealized_pnl
        
        If target is achieved, close all positions.
        
        Args:
            target_profit: Static target profit amount
            
        Returns:
            dict: Contains status, calculations, and result
        """
        try:
            # Get current positions to calculate unrealized PnL
            positions = self.get_positions()
            
            # Calculate total unrealized PnL from open positions
            total_unrealized_pnl = 0.0
            open_positions = []
            
            if 'result' in positions and positions['result']:
                for position in positions['result']:
                    if position.get('size', 0) != 0:  # Position is open
                        unrealized_pnl = float(position.get('unrealized_pnl', 0))
                        total_unrealized_pnl += unrealized_pnl
                        open_positions.append({
                            'product_symbol': position.get('product_symbol'),
                            'size': position.get('size'),
                            'unrealized_pnl': unrealized_pnl
                        })
            
            # Get realized PnL (you may need to adjust this based on your API)
            # This might require a separate endpoint for historical PnL data
            total_realized_pnl = self._get_monthly_realized_pnl()
            
            # Calculate total PnL
            total_pnl = total_realized_pnl + total_unrealized_pnl
            
            # Check if target is achieved
            target_achieved = total_pnl >= target_profit
            
            result = {
                'target_profit': target_profit,
                'realized_pnl': total_realized_pnl,
                'unrealized_pnl': total_unrealized_pnl,
                'total_pnl': total_pnl,
                'target_achieved': target_achieved,
                'open_positions_count': len(open_positions),
                'open_positions': open_positions
            }
            
            if target_achieved:
                print(f"🎯 Target achieved! Total PnL: {total_pnl} >= Target: {target_profit}")
                print("Closing all positions...")
                
                # Close all positions
                close_result = self.close_all_positions()
                result['close_positions_result'] = close_result
                result['action_taken'] = 'positions_closed'
            else:
                print(f"Target not yet achieved. Total PnL: {total_pnl} < Target: {target_profit}")
                result['action_taken'] = 'no_action'
            
            return result
            
        except Exception as e:
            return {
                'error': str(e),
                'action_taken': 'error'
            }

    def _get_monthly_realized_pnl(self):
        """
        Get realized PnL from margined positions.
        Based on API response structure with realized_pnl as string field.
        """
        try:
            positions = self.get_positions()
            
            total_realized = 0.0
            if 'success' in positions and positions['success'] and 'result' in positions:
                for position in positions['result']:
                    # realized_pnl comes as string in API response
                    realized_pnl_str = position.get('realized_pnl', '0')
                    if realized_pnl_str and realized_pnl_str != 'string':  # handle placeholder value
                        try:
                            realized_pnl = float(realized_pnl_str)
                            total_realized += realized_pnl
                        except (ValueError, TypeError):
                            if self.debug:
                                print(f"Could not parse realized_pnl: {realized_pnl_str}")
                            continue
            
            if self.debug:
                print(f"Total realized PnL: {total_realized}")
            
            return total_realized
            
        except Exception as e:
            if self.debug:
                print(f"Error getting realized PnL: {e}")
            return 0.0

    def get_pnl_summary(self):
        """
        Get a summary of current PnL status without taking any action.
        """
        try:
            positions = self.get_positions()
            
            total_unrealized_pnl = 0.0
            position_details = []
            
            if 'result' in positions and positions['result']:
                for position in positions['result']:
                    unrealized_pnl = float(position.get('realized_pnl', 0))
                    total_unrealized_pnl += unrealized_pnl
                    
                    position_details.append({
                        'product_symbol': position.get('product_symbol'),
                        'size': position.get('size'),
                        'realized_pnl': unrealized_pnl,
                        'entry_price': position.get('entry_price'),
                        'mark_price': position.get('mark_price')
                    })
            
            total_realized_pnl = self._get_monthly_realized_pnl()
            
            return {
                'realized_pnl': total_realized_pnl,
                'unrealized_pnl': total_unrealized_pnl,
                'total_pnl': total_realized_pnl + total_unrealized_pnl,
                'positions': position_details
            }
            
        except Exception as e:
            return {'error': str(e)}

    def get_account_summary(self):
        # Try multiple possible endpoints for account info
        endpoints = ["/wallet/balances", "/accounts", "/wallet", "/profile"]
        
        for endpoint in endpoints:
            try:
                path = self._full_path(endpoint)
                url = self.base + path
                headers = self._headers("GET", endpoint)
                
                if self.debug:
                    print(f"Trying endpoint: {endpoint}")
                
                r = requests.get(url, headers=headers)
                
                if r.status_code == 200:
                    return r.json()
                elif self.debug:
                    print(f"Endpoint {endpoint} returned {r.status_code}: {r.text[:200]}")
                    
            except Exception as e:
                if self.debug:
                    print(f"Error with endpoint {endpoint}: {e}")
                continue
        
        # If all endpoints failed, try the last one and let it raise the error
        path = self._full_path("/wallet/balances")
        url = self.base + path
        headers = self._headers("GET", "/wallet/balances")
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()

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


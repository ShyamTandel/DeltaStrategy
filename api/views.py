from django.shortcuts import render
from api.delta_client import call_delta_private
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
import json
import time
import hmac
import hashlib
import requests

# Create your views here.

def home_view(request):
    """
    Home page view
    """
    context = {
        'current_time': timezone.now(),
    }
    return render(request, 'home.html', context)

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Simple health check endpoint
    """
    return Response({
        'status': 'healthy',
        'message': 'DeltaStrategy API is running'
    })


class DeltaAPIClient:
    """
    Delta Exchange API Client for authentication and API calls
    """
    def __init__(self):
        self.base_url = 'https://api.india.delta.exchange'
        self.api_key = settings.API_KEY
        self.api_secret = settings.API_SECRET
        
    def generate_signature(self, secret, message):
        """
        Generate HMAC signature for Delta API authentication
        """
        message = bytes(message, 'utf-8')
        secret = bytes(secret, 'utf-8')
        hash = hmac.new(secret, message, hashlib.sha256)
        return hash.hexdigest()
    
    def get_auth_headers(self, method, path, query_string='', payload=''):
        """
        Generate authentication headers for Delta API
        """
        # Adjust timestamp to account for time drift
        # Based on error response, local time is ~21 seconds ahead of server time
        timestamp = str(int(time.time()) - 25)  # Subtract 25 seconds for safety
        signature_data = method + timestamp + path + query_string + payload
        signature = self.generate_signature(self.api_secret, signature_data)
        
        return {
            'api-key': self.api_key,
            'timestamp': timestamp,
            'signature': signature,
            'User-Agent': 'python-rest-client',
            'Content-Type': 'application/json'
        }
    
    def make_request(self, method, endpoint, params=None, data=None):
        """
        Make authenticated request to Delta API
        """
        url = f"{self.base_url}{endpoint}"
        query_string = ''
        payload = ''
        
        if params:
            query_string = '?' + '&'.join([f"{k}={v}" for k, v in params.items()])
        
        if data:
            payload = json.dumps(data)
            
        headers = self.get_auth_headers(method, endpoint, query_string, payload)
        
        try:
            if method.upper() == 'GET':
                response = requests.get(url, params=params, headers=headers, timeout=(3, 27))
            elif method.upper() == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=(3, 27))
            elif method.upper() == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=(3, 27))
            elif method.upper() == 'DELETE':
                response = requests.delete(url, json=data, headers=headers, timeout=(3, 27))
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            # Add more detailed error information
            error_details = f"API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_response = e.response.json()
                    error_details += f" - Response: {error_response}"
                except:
                    error_details += f" - Response text: {e.response.text}"
                error_details += f" - Headers sent: {headers}"
                error_details += f" - URL: {url}"
            raise Exception(error_details)


class DeltaAccountDataView(APIView):
    """
    Delta Exchange Account Data API View
    Fetches user account information from Delta Exchange
    """
    permission_classes = [AllowAny]
    
    def __init__(self):
        super().__init__()
        self.delta_client = DeltaAPIClient()
    
    def get(self, request):
        """
        Get Delta Exchange account data
        """
        try:
            # Check if API credentials are configured
            if not settings.API_KEY or not settings.API_SECRET:
                return Response({
                    'success': False,
                    'error': 'Delta API credentials not configured. Please set API_KEY and API_SECRET in environment variables.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user profile data
            profile_data = self.delta_client.make_request('GET', '/v2/profile')
            
            # Get wallet balances
            wallet_data = self.delta_client.make_request('GET', '/v2/wallet/balances')
            
            # Get user trading preferences
            preferences_data = self.delta_client.make_request('GET', '/v2/users/trading_preferences')
            
            # Combine the data
            account_data = {
                'success': True,
                'data': {
                    'profile': profile_data.get('result', {}),
                    'wallet': {
                        'balances': wallet_data.get('result', []),
                        'meta': wallet_data.get('meta', {})
                    },
                    'trading_preferences': preferences_data.get('result', {}),
                    'timestamp': timezone.now().isoformat()
                }
            }
            
            return Response(account_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to fetch account data: {str(e)}',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request):
        """
        Get specific account data based on request parameters
        """
        try:
            # Check if API credentials are configured
            if not settings.API_KEY or not settings.API_SECRET:
                return Response({
                    'success': False,
                    'error': 'Delta API credentials not configured. Please set API_KEY and API_SECRET in environment variables.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data_type = request.data.get('data_type', 'profile')
            
            response_data = {
                'success': True,
                'data': {},
                'timestamp': timezone.now().isoformat()
            }
            
            if data_type == 'profile' or data_type == 'all':
                profile_data = self.delta_client.make_request('GET', '/v2/profile')
                response_data['data']['profile'] = profile_data.get('result', {})
            
            if data_type == 'wallet' or data_type == 'all':
                wallet_data = self.delta_client.make_request('GET', '/v2/wallet/balances')
                response_data['data']['wallet'] = {
                    'balances': wallet_data.get('result', []),
                    'meta': wallet_data.get('meta', {})
                }
            
            if data_type == 'positions' or data_type == 'all':
                positions_data = self.delta_client.make_request('GET', '/v2/positions')
                response_data['data']['positions'] = positions_data.get('result', [])
            
            if data_type == 'orders' or data_type == 'all':
                orders_data = self.delta_client.make_request('GET', '/v2/orders')
                response_data['data']['orders'] = orders_data.get('result', [])
            
            if data_type == 'preferences' or data_type == 'all':
                preferences_data = self.delta_client.make_request('GET', '/v2/users/trading_preferences')
                response_data['data']['trading_preferences'] = preferences_data.get('result', {})
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Failed to fetch account data: {str(e)}',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DeltaMarketDataView(APIView):
    """
    Delta Exchange Market Data API View
    Fetches market data from Delta Exchange (no authentication required)
    """
    permission_classes = [AllowAny]
    
    def __init__(self):
        super().__init__()
        self.base_url = 'https://api.india.delta.exchange'
    
    def get(self, request):
        """
        Get market data (products, tickers, etc.)
        """
        try:
            data_type = request.query_params.get('type', 'products')
            symbol = request.query_params.get('symbol', None)
            
            response_data = {
                'success': True,
                'data': {},
                'timestamp': timezone.now().isoformat()
            }
            
            if data_type == 'products':
                # Get all products
                url = f"{self.base_url}/v2/products"
                response = requests.get(url, timeout=(3, 27))
                response.raise_for_status()
                products_data = response.json()
                response_data['data']['products'] = products_data.get('result', [])
                
            elif data_type == 'ticker':
                if symbol:
                    # Get ticker for specific symbol
                    url = f"{self.base_url}/v2/tickers/{symbol}"
                    response = requests.get(url, timeout=(3, 27))
                    response.raise_for_status()
                    ticker_data = response.json()
                    response_data['data']['ticker'] = ticker_data.get('result', {})
                else:
                    # Get all tickers
                    url = f"{self.base_url}/v2/tickers"
                    response = requests.get(url, timeout=(3, 27))
                    response.raise_for_status()
                    tickers_data = response.json()
                    response_data['data']['tickers'] = tickers_data.get('result', [])
            
            elif data_type == 'orderbook':
                if not symbol:
                    return Response({
                        'success': False,
                        'error': 'Symbol parameter is required for orderbook data'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                url = f"{self.base_url}/v2/l2orderbook/{symbol}"
                response = requests.get(url, timeout=(3, 27))
                response.raise_for_status()
                orderbook_data = response.json()
                response_data['data']['orderbook'] = orderbook_data.get('result', {})
            
            elif data_type == 'trades':
                if not symbol:
                    return Response({
                        'success': False,
                        'error': 'Symbol parameter is required for trades data'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                url = f"{self.base_url}/v2/trades/{symbol}"
                response = requests.get(url, timeout=(3, 27))
                response.raise_for_status()
                trades_data = response.json()
                response_data['data']['trades'] = trades_data.get('result', {})
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except requests.exceptions.RequestException as e:
            return Response({
                'success': False,
                'error': f'Failed to fetch market data: {str(e)}',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def debug_delta_auth(request):
    """
    Debug endpoint to test Delta API authentication
    """
    try:
        # Check credentials
        api_key = settings.API_KEY
        api_secret = settings.API_SECRET
        
        if not api_key or not api_secret:
            return Response({
                'success': False,
                'error': 'API credentials not configured',
                'debug': {
                    'api_key_exists': bool(api_key),
                    'api_secret_exists': bool(api_secret),
                    'api_key_length': len(api_key) if api_key else 0,
                    'api_secret_length': len(api_secret) if api_secret else 0
                }
            })
        
        # Create client and test basic signature generation
        client = DeltaAPIClient()
        
        # Test signature generation
        test_message = "GET123456789/v2/profile"
        test_signature = client.generate_signature(api_secret, test_message)
        
        # Test header generation
        headers = client.get_auth_headers('GET', '/v2/profile')
        
        # Test public API call (no auth required)
        public_test = None
        try:
            public_response = requests.get(f"{client.base_url}/v2/products", timeout=(3, 27))
            public_test = {
                'status_code': public_response.status_code,
                'success': public_response.status_code == 200,
                'products_count': len(public_response.json().get('result', [])) if public_response.status_code == 200 else 0
            }
        except Exception as e:
            public_test = {
                'error': str(e),
                'success': False
            }
        
        # Test authenticated API call with detailed error info
        auth_test = None
        try:
            auth_response = requests.get(f"{client.base_url}/v2/profile", headers=headers, timeout=(3, 27))
            auth_test = {
                'status_code': auth_response.status_code,
                'success': auth_response.status_code == 200
            }
            if auth_response.status_code != 200:
                auth_test['error_response'] = auth_response.text[:500]  # First 500 chars
        except Exception as e:
            auth_test = {
                'error': str(e),
                'success': False
            }
        
        return Response({
            'success': True,
            'debug': {
                'api_key_length': len(api_key),
                'api_secret_length': len(api_secret),
                'base_url': client.base_url,
                'test_signature': test_signature,
                'headers': {
                    'api-key': headers.get('api-key'),
                    'timestamp': headers.get('timestamp'),
                    'signature_length': len(headers.get('signature', '')),
                    'user_agent': headers.get('User-Agent'),
                    'content_type': headers.get('Content-Type')
                },
                'public_api_test': public_test,
                'auth_api_test': auth_test
            }
        })
        
    except Exception as e:
        return Response({
            'success': False,
            'error': f'Debug failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

import time
import hashlib
import hmac
import requests

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

# Delta Exchange API details
BASE_URL = "https://api.india.delta.exchange"
API_KEY = settings.API_KEY
API_SECRET = settings.API_SECRET

def generate_timestamp():
    return str(int(time.time()))  # seconds only

class DeltaAccountView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            path = "/v2/wallet/balances"
            method = "GET"
            query = ""

            timestamp = generate_timestamp()

            to_sign = method + timestamp + path + query
            signature = hmac.new(
                API_SECRET.encode("utf-8"),
                to_sign.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()

            headers = {
                "Accept": "application/json",
                "api-key": API_KEY,
                "signature": signature,
                "timestamp": timestamp,
            }

            url = BASE_URL + path
            resp = requests.get(url, headers=headers)

            try:
                data = resp.json()
            except Exception:
                return Response(
                    {"error": f"Non-JSON response: {resp.status_code}, {resp.text}"},
                    status=resp.status_code
                )

            return Response(data, status=resp.status_code)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# yourapp/views.py
from django.http import JsonResponse

def check_delta_apikey(request):
    """
    Simple endpoint to check your Delta API key by calling GET /v2/wallet/balances
    """
    try:
        resp = call_delta_private("GET", "/v2/wallet/balances", params=None, body="")
    except Exception as e:
        return JsonResponse({"success": False, "error": "client_error", "details": str(e)}, status=500)

    # forward status and json (or raw text)
    try:
        data = resp.json()
    except ValueError:
        data = {"text": resp.text}

    return JsonResponse({
        "success": resp.status_code == 200,
        "http_status": resp.status_code,
        "response": data
    }, status=200 if resp.status_code == 200 else resp.status_code)


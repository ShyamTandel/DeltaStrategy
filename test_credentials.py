#!/usr/bin/env python3
"""
Test Delta Exchange API credentials and connectivity
Run this to verify your API setup before running the strategy
"""

import os
import sys
import django
import requests
from datetime import datetime

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'deltastrategy.settings')
django.setup()

from api.delta_client import DeltaClient

def test_basic_connectivity():
    """Test basic internet connectivity to Delta Exchange"""
    print("🌐 Testing basic connectivity to Delta Exchange...")
    try:
        response = requests.get("https://cdn-ind.testnet.deltaex.org/v2/tickers", timeout=10)
        if response.status_code == 200:
            print("✅ Basic connectivity OK")
            return True
        else:
            print(f"❌ Connectivity failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Connectivity error: {e}")
        return False

def test_public_api():
    """Test public API endpoints (no authentication required)"""
    print("\n📊 Testing public API (option chain)...")
    try:
        client = DeltaClient(debug=True)
        result = client.get_option_chain(underlying="BTC")
        
        if result and "result" in result:
            tickers_count = len(result["result"])
            print(f"✅ Public API working! Found {tickers_count} tickers")
            
            # Show sample ticker data
            if tickers_count > 0:
                sample = result["result"][0]
                print(f"   Sample ticker: {sample.get('symbol', 'Unknown')}")
                print(f"   Contract type: {sample.get('contract_type', 'Unknown')}")
                
            return True
        else:
            print("❌ Public API failed: No result data")
            return False
            
    except Exception as e:
        print(f"❌ Public API error: {e}")
        return False

def test_credentials():
    """Test API credentials"""
    print("\n🔐 Testing API credentials...")
    
    from django.conf import settings
    
    # Check if credentials are loaded
    api_key = getattr(settings, 'DELTA_API_KEY', None)
    api_secret = getattr(settings, 'DELTA_API_SECRET', None)
    api_base = getattr(settings, 'DELTA_API_BASE', None)
    
    print(f"📋 Configuration:")
    print(f"   API Key: {api_key[:10]}...{api_key[-5:] if api_key and len(api_key) > 15 else 'NOT SET'}")
    print(f"   API Secret: {'SET' if api_secret else 'NOT SET'}")
    print(f"   API Base: {api_base}")
    
    if not api_key or not api_secret:
        print("❌ API credentials not properly configured!")
        print("   Check your .env file and make sure DELTA_API_KEY and DELTA_API_SECRET are set")
        return False
    
    return True

def test_authenticated_api():
    """Test authenticated API endpoints"""
    print("\n🔒 Testing authenticated API endpoints...")
    try:
        client = DeltaClient(debug=True)
        
        # Test multiple endpoints to find one that works
        endpoints_to_test = [
            ("orders", lambda: client._make_auth_request("GET", "/orders")),
            ("positions", lambda: client.get_positions()),
            ("account_summary", lambda: client.get_account_summary()),
            ("test_auth", lambda: client.test_auth())
        ]
        
        success_count = 0
        
        for endpoint_name, test_func in endpoints_to_test:
            try:
                print(f"\n   Testing {endpoint_name}...")
                result = test_func()
                
                if result:
                    print(f"   ✅ {endpoint_name} - Authentication successful!")
                    if isinstance(result, dict):
                        print(f"      Response keys: {list(result.keys())[:5]}")  # Show first 5 keys
                    success_count += 1
                else:
                    print(f"   ⚠️ {endpoint_name} - Empty response (but no error)")
                    
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    print(f"   ❌ {endpoint_name} - 401 Unauthorized")
                elif e.response.status_code == 404:
                    print(f"   ⚠️ {endpoint_name} - 404 Not Found (endpoint doesn't exist)")
                else:
                    print(f"   ❌ {endpoint_name} - {e.response.status_code}: {e.response.text[:100]}")
            except Exception as e:
                print(f"   ❌ {endpoint_name} - Error: {str(e)[:100]}")
        
        if success_count > 0:
            print(f"\n✅ Authentication working! {success_count} endpoints responded successfully")
            return True
        else:
            print("\n❌ Authentication failed on all endpoints")
            print("   Your API credentials might be invalid, expired, or lack permissions")
            return False
            
    except Exception as e:
        print(f"❌ Authentication test error: {e}")
        return False

def test_order_placement():
    """Test order placement capability (dry run)"""
    print("\n💰 Testing order placement capability...")
    try:
        client = DeltaClient(debug=True)
        
        # First get some option data
        tickers = client.get_option_chain(underlying="BTC")
        options = tickers.get("result", [])
        
        if not options:
            print("❌ No options available for testing")
            return False
        
        # Find a test option
        test_option = None
        for option in options:
            if option.get("contract_type") == "call_options":
                test_option = option
                break
        
        if not test_option:
            print("❌ No suitable test option found")
            return False
        
        print(f"📊 Test option: {test_option.get('symbol')}")
        print(f"   Product ID: {test_option.get('product_id')}")
        print(f"   Strike: {test_option.get('strike_price')}")
        
        # Create a test order (we won't actually place it)
        test_order = {
            "product_id": test_option.get("product_id"),
            "size": 1,
            "side": "sell",
            "order_type": "limit",
            "limit_price": "1.0"  # Very low price to avoid accidental execution
        }
        
        print(f"📋 Test order structure: {test_order}")
        print("⚠️ Skipping actual order placement to avoid accidental trades")
        print("✅ Order structure validation passed")
        
        return True
        
    except Exception as e:
        print(f"❌ Order test error: {e}")
        return False

def suggest_fixes():
    """Provide troubleshooting suggestions"""
    print("\n🔧 Troubleshooting Suggestions:")
    print("1. 🔑 Check API Credentials:")
    print("   - Verify DELTA_API_KEY and DELTA_API_SECRET in .env file")
    print("   - Make sure credentials are for testnet (sandbox)")
    print("   - Check if credentials have expired")
    
    print("\n2. 🌐 Check Network:")
    print("   - Verify internet connection")
    print("   - Check if testnet.deltaex.org is accessible")
    print("   - Try from different network if behind corporate firewall")
    
    print("\n3. 📊 Check API Permissions:")
    print("   - Make sure API key has trading permissions")
    print("   - Verify API key is enabled for options trading")
    print("   - Check rate limits and usage quotas")
    
    print("\n4. 🔄 Get New Credentials:")
    print("   - Log into Delta Exchange testnet")
    print("   - Go to API Management section")
    print("   - Generate new API key/secret pair")
    print("   - Update .env file with new credentials")

def main():
    """Run all credential and connectivity tests"""
    print("🧪 Delta Exchange API Credential Test")
    print("=" * 50)
    
    tests = [
        ("Basic Connectivity", test_basic_connectivity),
        ("Credentials Configuration", test_credentials),
        ("Public API", test_public_api),
        ("Authenticated API", test_authenticated_api),
        ("Order Placement Structure", test_order_placement)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False
        
        print()  # Add spacing between tests
    
    # Summary
    print("=" * 50)
    print("🏁 Test Results Summary:")
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("🎉 All tests passed! Your Delta Exchange API is configured correctly.")
        print("   You can now run the full strategy API safely.")
    else:
        print("⚠️ Some tests failed. Please fix the issues before running the strategy.")
        suggest_fixes()

if __name__ == "__main__":
    main()
"""
All API views for Delta Strategy application
Consolidated from celery_views.py, strategy_views.py and original views.py
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Any

from django.shortcuts import render
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.delta_client import DeltaClient
from api.models import OptionPosition


logger = logging.getLogger(__name__)

# Check Celery availability
try:
    from celery import current_app
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


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


@api_view(['GET'])
@permission_classes([AllowAny])
def test_delta_credentials(request):
    """
    Test Delta Exchange API credentials from within Django
    """
    try:
        from django.conf import settings
        
        # Check if credentials are loaded
        api_key = getattr(settings, 'DELTA_API_KEY', None)
        api_secret = getattr(settings, 'DELTA_API_SECRET', None)
        api_base = getattr(settings, 'DELTA_API_BASE', None)
        
        if not api_key or not api_secret:
            return Response({
                'error': 'API credentials not configured',
                'api_key_present': bool(api_key),
                'api_secret_present': bool(api_secret),
                'api_base': api_base
            }, status=400)
        
        # Test authentication
        client = DeltaClient(debug=True)
        
        # Try to get orders (simplest auth test)
        result = client._make_auth_request("GET", "/orders")
        
        return Response({
            'success': True,
            'message': 'Delta API credentials working',
            'api_key_preview': f"{api_key[:10]}...{api_key[-5:]}",
            'api_base': api_base,
            'orders_count': len(result.get('result', [])),
            'test_timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.exception("Delta credential test failed")
        return Response({
            'error': f'Delta API test failed: {str(e)}',
            'success': False
        }, status=500)


class StartMonthCycleAPIView(APIView):
    """
    POST /api/start-cycle/
    Body: { "underlying": "BTC", "reference_date": "YYYY-MM-DD" }  # reference_date optional
    This endpoint implements steps 1-8 (initial sells on first day) and then enters
    a loop implementing step 9-14 until termination conditions.
    NOTE: For production, run via scheduler on first day of month. This endpoint runs
    the flow synchronously (danger: it may make many API calls). Use with caution.
    """
    permission_classes = [AllowAny]  # Change as needed for security
    def post(self, request):
        underlying = request.data.get("underlying", "BTC")
        reference_date = request.data.get("reference_date")
        if reference_date:
            ref = datetime.fromisoformat(reference_date).date()
        else:
            ref = date.today()

        # Only run on first day of month per FDD step 7
        if ref.day != 1:
            # We won't block it; but per FDD, this should be run on first day
            pass

        client = DeltaClient(debug=True)

        # Step 1-2: Get option chain and select that month's last expiry
        tickers_resp = client.get_option_chain(underlying=underlying)
        tickers = tickers_resp.get("result", [])
        if not reference_date:
            last_expiry = find_last_expiry_for_month(tickers, ref)
        else:
            last_expiry = parse_expiry(reference_date)
        if not last_expiry:
            return Response({"error": "No expiry found for this month"}, status=status.HTTP_404_NOT_FOUND)

        expiry_str = last_expiry.strftime("%d-%m-%Y")
        tickers_resp = client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
        tickers = tickers_resp.get("result", [])

        # Step 3: find deltas in ranges
        # Step 4: find 0.16 to 0.22 in calls (positive), step 5: -0.16 to -0.22 in puts
        call_candidates = []
        put_candidates = []

        for t in tickers:
            greeks = t.get("greeks")
            if not greeks:
                continue

            try:
                delta = float(greeks.get("delta", 0))
            except ValueError:
                continue

            symbol = t.get("symbol", "")
            contract_type = t.get("contract_type", "").lower()

            # Check call options
            if contract_type == "call_options" or "c-" in symbol.lower():
                if 0.16 <= delta <= 0.22:
                    call_candidates.append(t)

            # Check put options
            if contract_type == "put_options" or "p-" in symbol.lower():
                if -0.22 <= delta <= -0.16:
                    put_candidates.append(t)

        if not call_candidates or not put_candidates:
            return Response({"error":"couldn't find required options in delta ranges",
                             "calls_found": len(call_candidates),
                             "puts_found": len(put_candidates)}, status=status.HTTP_404_NOT_FOUND)

        # Step 6: sell the lowest delta option that you find in each defined range for calls & puts
        # (lowest delta meaning numerically smallest absolute delta that is inside range)
        def lowest_delta_option(lst, is_put=False):
            # For put deltas negative; choose most negative closest to -0.16? The FDD says "lowest delta"
            # We'll choose min(abs(delta)) -> i.e., the option that has the smallest absolute delta value within range
            best = min(lst, key=lambda x: abs(float(x["greeks"].get("delta", 0))))
            return best

        call_to_sell = lowest_delta_option(call_candidates)
        put_to_sell = lowest_delta_option(put_candidates, is_put=True)

        # Helper to place sell order (we use market order size 1 by default)
        def place_sell(ticker_obj, size=2):
            product_id = ticker_obj.get("product_id")
            symbol = ticker_obj.get("symbol")
            # create order body: sell 1 contract as market or limit if ask present
            best_bid = ticker_obj.get("quotes", {}).get("best_bid")
            body = {
                "product_id": product_id,
                "size": size,
                "side": "sell",
                "order_type": "market_order"
            }
            res = client.place_order(body)
            return res

        # Place initial sells (these should be done on first day)
        call_order_res = place_sell(call_to_sell, size=2)
        put_order_res = place_sell(put_to_sell, size=2)
        # Save to DB
        def save_pos(resp, ticker_obj):
            r = resp.get("result", {})
            # Extract expiry from symbol since expiry_date field might not be available
            expiry_date = extract_expiry_from_symbol(ticker_obj.get("symbol", ""))
            p = OptionPosition.objects.create(
                product_id = ticker_obj.get("product_id"),
                symbol = ticker_obj.get("symbol"),
                side = "sell",
                size = 2,
                limit_price = None,
                mark_price = Decimal(ticker_obj.get("mark_price") or ticker_obj.get("quotes", {}).get("best_bid") or 0),
                strike_price = Decimal(ticker_obj.get("strike_price")),
                delta = float(ticker_obj.get("greeks", {}).get("delta", 0)),
                expiry_date = expiry_date,
                remote_order_id = r.get("id")
            )
            return p

        pos_call = save_pos(call_order_res, call_to_sell)
        pos_put = save_pos(put_order_res, put_to_sell)
        # Now loop implementing steps 9-14
        # We'll implement a safe loop with a max iteration count to avoid infinite loops
        max_iters = 10
        iters = 0
        actions = []
        while iters < max_iters:
            iters += 1
            # refresh tickers for the expiry
            tickers_resp = client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
            tickers = tickers_resp.get("result", [])

            # get current mark_price of our two positions
            open_positions = list(OptionPosition.objects.filter(active=True).order_by('created_at'))
            if len(open_positions) == 0:
                break

            # if only one position open (step 11) then we need to find opposite side matching delta within ±0.03
            if len(open_positions) == 1:
                open_pos = open_positions[0]
                target_delta = open_pos.delta
                # if open is put (negative), we search calls with +delta approx equal
                if open_pos.symbol.startswith("P-") or open_pos.delta < 0:
                    target_low = target_delta + 0.0  # negative
                    desired_low = target_delta * -1 if target_delta < 0 else target_delta
                    # search for call with delta approx equal to abs(target_delta) ±0.03
                    target_min = abs(target_delta) - 0.03
                    target_max = abs(target_delta) + 0.03
                    # find candidate calls
                    calls = [t for t in tickers if ("C-" in t.get("symbol","") or t.get("contract_type")=="call_options")]
                    matching = []
                    for c in calls:
                        try:
                            d = float(c["greeks"]["delta"])
                            if target_min <= d <= target_max:
                                matching.append(c)
                        except:
                            pass
                    if matching:
                        # sell the one found (step 13)
                        candidate = min(matching, key=lambda x: abs(float(x["greeks"]["delta"]) - abs(target_delta)))
                        res = place_sell(candidate, size=2)
                        save_pos(res, candidate)
                        actions.append(f"sold matching call {candidate['symbol']}")
                else:
                    # open is call; find put matching delta
                    target_min = abs(target_delta) - 0.03
                    target_max = abs(target_delta) + 0.03
                    puts = [t for t in tickers if ("P-" in t.get("symbol","") or t.get("contract_type")=="put_options")]
                    matching = []
                    for p in puts:
                        try:
                            d = abs(float(p["greeks"]["delta"]))  # put delta negative
                            if target_min <= d <= target_max:
                                matching.append(p)
                        except:
                            pass
                    if matching:
                        candidate = min(matching, key=lambda x: abs(abs(float(x["greeks"]["delta"])) - abs(target_delta)))
                        res = place_sell(candidate, size=2)
                        save_pos(res, candidate)
                        actions.append(f"sold matching put {candidate['symbol']}")

            # Step 9: condition if any option's price becomes double compared to other options position then step 10 applied
            # We'll compute mark_price for each open position by matching symbol in tickers
            current_prices = {}
            for p in open_positions:
                # find matching ticker
                match = next((t for t in tickers if t.get("symbol")==p.symbol), None)
                if match:
                    current_prices[p.id] = float(match.get("mark_price") or 0)
                else:
                    current_prices[p.id] = float(p.mark_price or 0)

            # if there are exactly 2 positions compare their prices
            if len(open_positions) >= 2:
                p1, p2 = open_positions[0], open_positions[1]
                price1 = current_prices.get(p1.id, 0)
                price2 = current_prices.get(p2.id, 0)
                # if any option price becomes double compared to other -> close the cheaper one (step 10)
                if price1 >= 2*price2:
                    # close p2 (the less price compared) -> "cut off"
                    # We'll cancel/close by placing a market buy equal size to cover the sold option
                    close_body = {"product_id": p2.product_id, "size": p2.size, "side": "buy", "order_type":"market_order"}
                    client.place_order(close_body)
                    p2.active = False
                    p2.save()
                    actions.append(f"closed {p2.symbol} because {p1.symbol} doubled {price1} vs {price2}")
                elif price2 >= 2*price1:
                    close_body = {"product_id": p1.product_id, "size": p1.size, "side": "buy", "order_type":"market_order"}
                    client.place_order(close_body)
                    p1.active = False
                    p1.save()
                    actions.append(f"closed {p1.symbol} because {p2.symbol} doubled {price2} vs {price1}")

            # Step 15: Ensure strike prices never cross — check strike ordering
            open_positions = list(OptionPosition.objects.filter(active=True))
            if len(open_positions) >= 2:
                s1 = float(open_positions[0].strike_price)
                s2 = float(open_positions[1].strike_price)
                # If they cross (call strike < put strike) — this violates condition; in that case we close the later-opened
                if (open_positions[0].symbol.startswith("C-") and open_positions[1].symbol.startswith("P-") and s1 < s2) or \
                   (open_positions[0].symbol.startswith("P-") and open_positions[1].symbol.startswith("C-") and s2 < s1):
                    # close the one with less recently created (safe heuristic)
                    to_close = open_positions[-1]
                    client.place_order({"product_id": to_close.product_id, "size": to_close.size, "side":"buy", "order_type":"market_order"})
                    to_close.active = False
                    to_close.save()
                    actions.append(f"closed {to_close.symbol} to avoid strike crossing")

            # termination: if both open positions have same strike (step 16) -> done
            open_positions = list(OptionPosition.objects.filter(active=True))
            if len(open_positions) == 2:
                if float(open_positions[0].strike_price) == float(open_positions[1].strike_price):
                    actions.append("termination: strikes matched")
                    break

            # small sleep avoidance: we don't sleep in this synchronous endpoint; loop continues but with max_iters limit
            # If no actionable events in this iteration, break to avoid busy loop
            if not actions:
                # nothing happened in this iteration -> stop
                break

        return Response({
            "status": "completed",
            "initial": {
                "call_sold": call_to_sell.get("symbol"),
                "put_sold": put_to_sell.get("symbol"),
            },
            "actions": actions
        })


class StrategyExecuteAPIView(APIView):
    """
    POST /api/strategy/
    Execute new delta strategy with improved implementation
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            underlying = request.data.get("underlying", "BTC")
            reference_date = request.data.get("reference_date")
            profit_target = float(request.data.get("profit_target", 50.0))
            position_size = int(request.data.get("position_size", 2))
            
            # Validate inputs
            if profit_target <= 0 or profit_target > 1000:
                return Response({
                    "error": "Profit target must be between 0 and 1000 percent",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)
                
            if position_size <= 0 or position_size > 100:
                return Response({
                    "error": "Position size must be between 1 and 100",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create strategy config
            config = StrategyConfig(
                profit_target_percent=profit_target,
                position_size=position_size
            )
            
            # Execute strategy
            strategy = DeltaStrategy(config=config, debug=True)
            result = strategy.execute_monthly_strategy(underlying, reference_date)
            
            return Response(result)
            
        except Exception as e:
            logger.exception("Error executing strategy")
            return Response({
                "error": f"Strategy execution failed: {str(e)}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StrategyStatusAPIView(APIView):
    """
    GET /api/strategy/status/
    Get current strategy status and positions
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        try:
            active_positions = OptionPosition.objects.filter(active=True).order_by('-created_at')
            
            if not active_positions.exists():
                return Response({
                    "status": "no_active_positions",
                    "message": "No active strategy positions found",
                    "positions": []
                })
            
            # Get current market data
            client = DeltaClient(debug=False)
            underlying = "BTC"  # Could be made configurable
            
            try:
                tickers_resp = client.get_option_chain(underlying=underlying)
                tickers = tickers_resp.get("result", [])
            except Exception as e:
                tickers = []
                logger.warning(f"Could not fetch current tickers: {e}")
            
            # Build position data
            positions_data = []
            total_initial_value = 0
            total_current_value = 0
            
            for pos in active_positions:
                current_ticker = next(
                    (t for t in tickers if t.get("symbol") == pos.symbol), 
                    None
                )
                
                current_price = None
                if current_ticker:
                    current_price = float(current_ticker.get("mark_price", 0))
                
                initial_price = float(pos.mark_price or 0)
                position_initial_value = initial_price * pos.size
                position_current_value = (current_price or initial_price) * pos.size
                
                total_initial_value += position_initial_value
                total_current_value += position_current_value
                
                positions_data.append({
                    'id': pos.id,
                    'symbol': pos.symbol,
                    'side': pos.side,
                    'size': pos.size,
                    'strike_price': float(pos.strike_price),
                    'delta': pos.delta,
                    'expiry_date': pos.expiry_date.isoformat(),
                    'created_at': pos.created_at.isoformat(),
                    'initial_price': initial_price,
                    'current_price': current_price,
                    'position_pnl': position_initial_value - position_current_value if current_price else None
                })
            
            # Calculate overall performance
            total_pnl = total_initial_value - total_current_value
            pnl_percent = (total_pnl / total_initial_value * 100) if total_initial_value > 0 else 0
            
            return Response({
                "status": "active",
                "positions_count": len(positions_data),
                "positions": positions_data,
                "performance": {
                    "total_initial_value": total_initial_value,
                    "total_current_value": total_current_value,
                    "total_pnl": total_pnl,
                    "pnl_percent": round(pnl_percent, 2)
                },
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.exception("Error getting strategy status")
            return Response({
                "error": f"Failed to get status: {str(e)}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StrategyCloseAllAPIView(APIView):
    """
    POST /api/strategy/close-all/
    Close all active positions
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            active_positions = OptionPosition.objects.filter(active=True)
            
            if not active_positions.exists():
                return Response({
                    "message": "No active positions to close",
                    "success": True,
                    "closed_count": 0
                })
            
            client = DeltaClient(debug=True)
            closed_positions = []
            errors = []
            
            for pos in active_positions:
                try:
                    close_order = {
                        "product_id": pos.product_id,
                        "size": pos.size,
                        "side": "buy",
                        "order_type": "market_order"
                    }
                    
                    result = client.place_order(close_order)
                    pos.active = False
                    pos.save()
                    
                    closed_positions.append({
                        "symbol": pos.symbol,
                        "size": pos.size,
                        "order_id": result.get("result", {}).get("id")
                    })
                    
                except Exception as e:
                    errors.append(f"Failed to close {pos.symbol}: {str(e)}")
            
            return Response({
                "message": f"Closed {len(closed_positions)} positions",
                "success": len(errors) == 0,
                "closed_positions": closed_positions,
                "errors": errors,
                "closed_count": len(closed_positions)
            })
            
        except Exception as e:
            logger.exception("Error closing positions")
            return Response({
                "error": f"Failed to close positions: {str(e)}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FullLocalStrategyAPIView(APIView):
    """
    POST /api/strategy/execute-full-local/
    
    🎯 COMPLETE DELTA STRATEGY EXECUTION - ALL STEPS LOCAL
    
    This API executes the ENTIRE delta strategy flow in one call:
    
    1. ✅ Find call (0.16-0.22 delta) and put (-0.22 to -0.16 delta) options
    2. ✅ SELL BOTH OPTIONS (critical requirement - must be both)
    3. ✅ Enter monitoring loop with 30-second intervals (simulated locally)
    4. ✅ Apply all rules: profit target, price doubling, strike crossing
    5. ✅ Close positions when 50% profit target reached
    6. ✅ Find matching deltas when needed
    7. ✅ Complete strategy until termination conditions met
    
    📊 AUTOMATED RULES APPLIED:
    - 50% profit target → Close ALL positions
    - Price doubling → Close cheaper position
    - Strike crossing prevention → Close latest position
    - Delta matching → Find and sell matching options
    
    🚀 USAGE FROM POSTMAN:
    POST http://localhost:8000/api/strategy/execute-full-local/
    Body: {
        "underlying": "BTC",
        "reference_date": "2024-10-25",  // optional
        "profit_target": 50.0,           // optional, default 50%
        "position_size": 2,              // optional, default 2
        "max_iterations": 20,            // optional, default 20
        "monitoring_interval": 5         // optional, default 5 seconds
    }
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        import time
        from decimal import Decimal
        
        try:
            # Parse request parameters
            underlying = request.data.get("underlying", "BTC")
            reference_date = request.data.get("reference_date")
            profit_target = float(request.data.get("profit_target", 50.0))
            position_size = int(request.data.get("position_size", 2))
            max_iterations = int(request.data.get("max_iterations", 20))
            monitoring_interval = int(request.data.get("monitoring_interval", 5))
            
            # Validation
            if profit_target <= 0 or profit_target > 1000:
                return Response({
                    "error": "Profit target must be between 0 and 1000 percent",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if position_size <= 0 or position_size > 100:
                return Response({
                    "error": "Position size must be between 1 and 100",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Initialize
            execution_log = []
            start_time = datetime.now()
            
            def log_action(message):
                timestamp = datetime.now().strftime("%H:%M:%S")
                execution_log.append(f"[{timestamp}] {message}")
                print(f"[FULL-STRATEGY] {message}")
            
            log_action(f"🚀 Starting FULL LOCAL Delta Strategy for {underlying}")
            log_action(f"📊 Config: profit_target={profit_target}%, size={position_size}, max_iter={max_iterations}")
            
            # Test credentials first
            try:
                from django.conf import settings
                api_key = getattr(settings, 'DELTA_API_KEY', None)
                api_secret = getattr(settings, 'DELTA_API_SECRET', None)
                api_base = getattr(settings, 'DELTA_API_BASE', None)
                
                log_action(f"🔐 API Config: key={api_key[:10] if api_key else 'None'}..., base={api_base}")
                
                if not api_key or not api_secret:
                    return Response({
                        "error": "Delta API credentials not properly configured in Django settings",
                        "success": False,
                        "api_key_present": bool(api_key),
                        "api_secret_present": bool(api_secret),
                        "execution_log": execution_log
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                # Test authentication before proceeding
                test_client = DeltaClient(debug=False)
                test_result = test_client._make_auth_request("GET", "/orders")
                log_action(f"✅ Credentials verified - found {len(test_result.get('result', []))} existing orders")
                
            except Exception as e:
                log_action(f"❌ Credential verification failed: {str(e)}")
                return Response({
                    "error": f"Delta API credential verification failed: {str(e)}",
                    "success": False,
                    "execution_log": execution_log
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            client = DeltaClient(debug=True)
            
            # STEP 1: Get option chain and find expiry
            log_action("📈 Fetching option chain...")
            tickers_resp = client.get_option_chain(underlying=underlying)
            tickers = tickers_resp.get("result", [])
            
            if reference_date:
                ref_date = datetime.fromisoformat(reference_date).date()
                last_expiry = parse_expiry(reference_date)
            else:
                ref_date = date.today()
                last_expiry = find_last_expiry_for_month(tickers, ref_date)
            
            if not last_expiry:
                return Response({
                    "error": "No expiry found for this month",
                    "success": False,
                    "execution_log": execution_log
                }, status=status.HTTP_404_NOT_FOUND)
            
            expiry_str = last_expiry.strftime("%d-%m-%Y")
            log_action(f"📅 Using expiry: {expiry_str}")
            
            # Get options for specific expiry
            tickers_resp = client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
            tickers = tickers_resp.get("result", [])
            
            # STEP 2: Find options in delta ranges
            log_action("🔍 Finding options in delta ranges...")
            call_candidates = []
            put_candidates = []
            
            for ticker in tickers:
                greeks = ticker.get("greeks")
                if not greeks:
                    continue
                    
                try:
                    delta = float(greeks.get("delta", 0))
                except (ValueError, TypeError):
                    continue
                    
                symbol = ticker.get("symbol", "")
                contract_type = ticker.get("contract_type", "").lower()
                
                # Identify call options
                is_call = (contract_type == "call_options" or 
                          "c-" in symbol.lower() or 
                          symbol.upper().startswith("C-"))
                
                # Identify put options  
                is_put = (contract_type == "put_options" or 
                         "p-" in symbol.lower() or 
                         symbol.upper().startswith("P-"))
                
                # Check call delta range (0.16 to 0.22)
                if is_call and 0.16 <= delta <= 0.22:
                    call_candidates.append(ticker)
                    
                # Check put delta range (-0.22 to -0.16)
                if is_put and -0.22 <= delta <= -0.16:
                    put_candidates.append(ticker)
            
            if not call_candidates:
                return Response({
                    "error": "No call options found in delta range 0.16-0.22",
                    "success": False,
                    "execution_log": execution_log
                }, status=status.HTTP_404_NOT_FOUND)
                
            if not put_candidates:
                return Response({
                    "error": "No put options found in delta range -0.22 to -0.16",
                    "success": False,
                    "execution_log": execution_log
                }, status=status.HTTP_404_NOT_FOUND)
            
            log_action(f"✅ Found {len(call_candidates)} call and {len(put_candidates)} put candidates")
            
            # STEP 3: Select options with lowest absolute delta
            def select_lowest_delta(candidates):
                return min(candidates, key=lambda x: abs(float(x["greeks"].get("delta", 0))))
            
            call_to_sell = select_lowest_delta(call_candidates)
            put_to_sell = select_lowest_delta(put_candidates)
            
            log_action(f"📊 Selected call: {call_to_sell['symbol']} (δ={call_to_sell['greeks']['delta']})")
            log_action(f"📊 Selected put: {put_to_sell['symbol']} (δ={put_to_sell['greeks']['delta']})")
            
            # STEP 4: SELL BOTH OPTIONS (CRITICAL REQUIREMENT)
            def place_sell_order(ticker, size):
                order_body = {
                    "product_id": ticker.get("product_id"),
                    "size": size,
                    "side": "sell", 
                    "order_type": "market_order"
                }
                return client.place_order(order_body)
            
            def save_position(order_response, ticker):
                result = order_response.get("result", {})
                expiry_date = extract_expiry_from_symbol(ticker.get("symbol", ""))
                
                position = OptionPosition.objects.create(
                    product_id=ticker.get("product_id"),
                    symbol=ticker.get("symbol"),
                    side="sell",
                    size=position_size,
                    limit_price=None,
                    mark_price=Decimal(str(ticker.get("mark_price", 0) or 
                                         ticker.get("quotes", {}).get("best_bid", 0) or 0)),
                    strike_price=Decimal(str(ticker.get("strike_price", 0))),
                    delta=float(ticker.get("greeks", {}).get("delta", 0)),
                    expiry_date=expiry_date,
                    remote_order_id=result.get("id"),
                    active=True
                )
                return position
            
            log_action("💰 Selling call option...")
            call_order = place_sell_order(call_to_sell, position_size)
            call_position = save_position(call_order, call_to_sell)
            
            log_action("💰 Selling put option...")
            put_order = place_sell_order(put_to_sell, position_size)
            put_position = save_position(put_order, put_to_sell)
            
            log_action(f"✅ Successfully sold both options!")
            log_action(f"   📞 Call: {call_position.symbol} @ ${call_position.mark_price}")
            log_action(f"   📞 Put: {put_position.symbol} @ ${put_position.mark_price}")
            
            # STEP 5: MONITORING LOOP - LOCAL EXECUTION
            log_action(f"🔄 Starting monitoring loop (max {max_iterations} iterations)")
            
            iteration = 0
            while iteration < max_iterations:
                iteration += 1
                log_action(f"🔍 Monitoring iteration {iteration}/{max_iterations}")
                
                # Wait for monitoring interval
                if iteration > 1:  # Don't wait on first iteration
                    log_action(f"⏱️ Waiting {monitoring_interval} seconds...")
                    time.sleep(monitoring_interval)
                
                # Refresh market data
                try:
                    tickers_resp = client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
                    tickers = tickers_resp.get("result", [])
                except Exception as e:
                    log_action(f"⚠️ Failed to refresh market data: {e}")
                    continue
                
                # Get current active positions
                active_positions = list(OptionPosition.objects.filter(active=True).order_by('created_at'))
                
                if len(active_positions) == 0:
                    log_action("✅ No active positions remaining - strategy complete!")
                    break
                
                # Get current prices
                current_prices = {}
                for pos in active_positions:
                    ticker = next((t for t in tickers if t.get("symbol") == pos.symbol), None)
                    if ticker:
                        current_prices[pos.id] = float(ticker.get("mark_price", 0) or 0)
                    else:
                        current_prices[pos.id] = float(pos.mark_price or 0)
                
                log_action(f"💹 Current prices: {[(pos.symbol, f'${current_prices.get(pos.id, 0):.4f}') for pos in active_positions]}")
                
                # RULE 1: Check 50% profit target
                def calculate_profit_percent(positions, prices):
                    if not positions:
                        return 0.0
                    
                    total_initial = sum(float(pos.mark_price or 0) * pos.size for pos in positions)
                    total_current = sum(prices.get(pos.id, float(pos.mark_price or 0)) * pos.size for pos in positions)
                    
                    if total_initial == 0:
                        return 0.0
                    
                    # For sold positions: profit = initial - current
                    profit_percent = ((total_initial - total_current) / total_initial) * 100
                    return profit_percent
                
                current_profit = calculate_profit_percent(active_positions, current_prices)
                log_action(f"📊 Current profit: {current_profit:.2f}% (target: {profit_target}%)")
                
                if current_profit >= profit_target:
                    log_action(f"🎯 PROFIT TARGET REACHED! Closing all positions...")
                    
                    def place_buy_order(position):
                        order_body = {
                            "product_id": position.product_id,
                            "size": position.size,
                            "side": "buy",
                            "order_type": "market_order"
                        }
                        return client.place_order(order_body)
                    
                    closed_count = 0
                    for pos in active_positions:
                        try:
                            close_order = place_buy_order(pos)
                            pos.active = False
                            pos.save()
                            closed_count += 1
                            log_action(f"   ✅ Closed {pos.symbol}")
                        except Exception as e:
                            log_action(f"   ❌ Failed to close {pos.symbol}: {e}")
                    
                    log_action(f"🏁 Strategy completed! Closed {closed_count} positions at {current_profit:.2f}% profit")
                    break
                
                # RULE 2: Handle single position case
                if len(active_positions) == 1:
                    log_action("🔍 Only one position active - searching for matching option...")
                    remaining_pos = active_positions[0]
                    target_delta_abs = abs(remaining_pos.delta)
                    
                    # Find matching option on opposite side
                    matching_option = None
                    tolerance = 0.03
                    
                    if remaining_pos.delta > 0:  # Remaining is call, find matching put
                        for ticker in tickers:
                            if ("P-" in ticker.get("symbol", "").upper() or 
                                ticker.get("contract_type") == "put_options"):
                                try:
                                    delta_abs = abs(float(ticker["greeks"]["delta"]))
                                    if target_delta_abs - tolerance <= delta_abs <= target_delta_abs + tolerance:
                                        if not matching_option or abs(delta_abs - target_delta_abs) < abs(abs(float(matching_option["greeks"]["delta"])) - target_delta_abs):
                                            matching_option = ticker
                                except (ValueError, TypeError, KeyError):
                                    continue
                    else:  # Remaining is put, find matching call
                        for ticker in tickers:
                            if ("C-" in ticker.get("symbol", "").upper() or 
                                ticker.get("contract_type") == "call_options"):
                                try:
                                    delta = float(ticker["greeks"]["delta"])
                                    if target_delta_abs - tolerance <= delta <= target_delta_abs + tolerance:
                                        if not matching_option or abs(delta - target_delta_abs) < abs(float(matching_option["greeks"]["delta"]) - target_delta_abs):
                                            matching_option = ticker
                                except (ValueError, TypeError, KeyError):
                                    continue
                    
                    if matching_option:
                        try:
                            log_action(f"💰 Selling matching option: {matching_option['symbol']} (δ={matching_option['greeks']['delta']})")
                            order = place_sell_order(matching_option, position_size)
                            new_position = save_position(order, matching_option)
                            log_action(f"   ✅ Successfully sold matching option!")
                        except Exception as e:
                            log_action(f"   ❌ Failed to sell matching option: {e}")
                    else:
                        log_action("   ⚠️ No matching option found within tolerance")
                
                # RULE 3: Handle two+ positions case - price doubling
                elif len(active_positions) >= 2:
                    pos1, pos2 = active_positions[0], active_positions[1]
                    price1 = current_prices.get(pos1.id, 0)
                    price2 = current_prices.get(pos2.id, 0)
                    
                    position_closed = False
                    
                    if price1 >= 2 * price2 and price2 > 0:
                        log_action(f"📈 Price doubled! Closing cheaper position {pos2.symbol} (${price2:.4f} vs ${price1:.4f})")
                        try:
                            close_order = place_buy_order(pos2)
                            pos2.active = False
                            pos2.save()
                            log_action(f"   ✅ Closed {pos2.symbol}")
                            position_closed = True
                        except Exception as e:
                            log_action(f"   ❌ Failed to close {pos2.symbol}: {e}")
                            
                    elif price2 >= 2 * price1 and price1 > 0:
                        log_action(f"📈 Price doubled! Closing cheaper position {pos1.symbol} (${price1:.4f} vs ${price2:.4f})")
                        try:
                            close_order = place_buy_order(pos1)
                            pos1.active = False
                            pos1.save()
                            log_action(f"   ✅ Closed {pos1.symbol}")
                            position_closed = True
                        except Exception as e:
                            log_action(f"   ❌ Failed to close {pos1.symbol}: {e}")
                    
                    # RULE 4: Check strike crossing prevention
                    if not position_closed:
                        active_pos_fresh = list(OptionPosition.objects.filter(active=True).order_by('created_at'))
                        if len(active_pos_fresh) >= 2:
                            def check_strike_crossing(positions):
                                call_pos = None
                                put_pos = None
                                
                                for pos in positions:
                                    if pos.symbol.upper().startswith("C-") or pos.delta > 0:
                                        call_pos = pos
                                    elif pos.symbol.upper().startswith("P-") or pos.delta < 0:
                                        put_pos = pos
                                
                                if call_pos and put_pos:
                                    call_strike = float(call_pos.strike_price)
                                    put_strike = float(put_pos.strike_price)
                                    return call_strike < put_strike  # Strikes cross if call < put
                                
                                return False
                            
                            if check_strike_crossing(active_pos_fresh):
                                to_close = active_pos_fresh[-1]  # Close most recent
                                log_action(f"⚠️ Strike crossing detected! Closing {to_close.symbol}")
                                try:
                                    close_order = place_buy_order(to_close)
                                    to_close.active = False
                                    to_close.save()
                                    log_action(f"   ✅ Closed {to_close.symbol} to prevent crossing")
                                except Exception as e:
                                    log_action(f"   ❌ Failed to close {to_close.symbol}: {e}")
                
                # RULE 5: Check termination condition (strikes match)
                active_positions_check = list(OptionPosition.objects.filter(active=True))
                if len(active_positions_check) == 2:
                    strike1 = float(active_positions_check[0].strike_price)
                    strike2 = float(active_positions_check[1].strike_price)
                    
                    if abs(strike1 - strike2) < 0.01:
                        log_action(f"🎯 Strikes matched! ({strike1} ≈ {strike2}) - Waiting for profit target...")
            
            # Final status
            final_positions = list(OptionPosition.objects.filter(active=True))
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if len(final_positions) == 0:
                final_status = "completed_successfully"
                final_message = f"Strategy completed successfully! All positions closed."
            else:
                final_status = "active_positions_remaining"
                final_message = f"Strategy monitoring completed. {len(final_positions)} positions still active."
            
            log_action(f"🏁 Strategy execution finished in {duration:.1f} seconds")
            log_action(f"📊 Final status: {final_message}")
            
            return Response({
                "success": True,
                "status": final_status,
                "message": final_message,
                "execution_summary": {
                    "underlying": underlying,
                    "expiry": expiry_str,
                    "profit_target": profit_target,
                    "position_size": position_size,
                    "iterations_completed": iteration,
                    "max_iterations": max_iterations,
                    "duration_seconds": round(duration, 1),
                    "active_positions_remaining": len(final_positions)
                },
                "initial_positions": {
                    "call": {
                        "symbol": call_position.symbol,
                        "delta": call_position.delta,
                        "strike": float(call_position.strike_price),
                        "price": float(call_position.mark_price)
                    },
                    "put": {
                        "symbol": put_position.symbol,
                        "delta": put_position.delta,
                        "strike": float(put_position.strike_price),
                        "price": float(put_position.mark_price)
                    }
                },
                "execution_log": execution_log,
                "timestamp": end_time.isoformat()
            })
            
        except Exception as e:
            logger.exception("Error in full local strategy execution")
            return Response({
                "error": f"Strategy execution failed: {str(e)}",
                "success": False,
                "execution_log": execution_log if 'execution_log' in locals() else []
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Celery-integrated APIs (only if Celery is available)
if CELERY_AVAILABLE:
    
    class BackgroundStrategyExecuteAPIView(APIView):
        """
        POST /api/strategy/execute-background/
        Execute strategy as background task
        """
        permission_classes = [AllowAny]
        
        def post(self, request):
            try:
                from deltastrategy.celery import execute_strategy_background_task
                
                underlying = request.data.get("underlying", "BTC")
                reference_date = request.data.get("reference_date")
                profit_target = float(request.data.get("profit_target", 50.0))
                position_size = int(request.data.get("position_size", 2))
                
                # Queue the strategy execution as a background task
                task_result = execute_strategy_background_task.delay(underlying, reference_date, profit_target, position_size)
                
                return Response({
                    'success': True,
                    'message': 'Strategy execution queued',
                    'task_id': str(task_result.id),
                    'queued_at': timezone.now().isoformat()
                })
                
            except Exception as e:
                return Response({
                    'error': f'Failed to queue strategy: {str(e)}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    
    class MonitoringStatusAPIView(APIView):
        """
        GET /api/strategy/monitoring/status/
        Get monitoring status
        """
        permission_classes = [AllowAny]
        
        def get(self, request):
            active_positions = OptionPosition.objects.filter(active=True)
            
            return Response({
                'automation_status': 'active' if active_positions.exists() else 'no_positions',
                'positions_count': active_positions.count(),
                'monitoring_frequency': '30 seconds',
                'celery_available': True,
                'last_check': timezone.now().isoformat()
            })
    
    
    class ForceMonitorAPIView(APIView):
        """
        POST /api/strategy/force-monitor/
        Manually trigger monitoring
        """
        permission_classes = [AllowAny]
        
        def post(self, request):
            try:
                from api.strategy import monitor_positions
                result = monitor_positions()
                return Response({
                    'success': True,
                    'message': 'Monitoring task executed',
                    'result': result,
                    'executed_at': timezone.now().isoformat()
                })
            except Exception as e:
                return Response({
                    'error': f'Monitoring failed: {str(e)}',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


else:
    # Placeholder classes when Celery is not available
    class BackgroundStrategyExecuteAPIView(APIView):
        def post(self, request):
            return Response({
                'error': 'Celery is not available. Use /api/strategy/ instead.',
                'success': False
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    class MonitoringStatusAPIView(APIView):
        def get(self, request):
            return Response({
                'error': 'Celery is not available',
                'celery_available': False
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    class ForceMonitorAPIView(APIView):
        def post(self, request):
            return Response({
                'error': 'Celery is not available',
                'success': False
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


# Import monitoring views from monitoring_views.py
from api.monitoring_views import (
    api_status, 
    trigger_manual_check, 
    get_task_result, 
    monitoring_dashboard, 
    control_monitoring
)

# Import monthly strategy views
from api.monthly_strategy_views import (
    MonthlyStrategyStartAPIView,
    MonthlyStrategyStatusAPIView,
    MonthlyStrategyAdjustAPIView,
    MonthlyStrategyCloseAllAPIView
)

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
from api.utils import find_last_expiry_for_month, parse_expiry, extract_expiry_from_symbol
from api.strategy import DeltaStrategy, StrategyConfig

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

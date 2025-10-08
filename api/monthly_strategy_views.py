"""
API Views for Monthly Delta Strategy

New endpoints specifically for the monthly options strategy with 
proper PnL tracking and automatic position management.
"""

import logging
from datetime import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.monthly_strategy import (
    MonthlyDeltaStrategy, 
    start_monthly_cycle_if_needed, 
    check_positions_and_adjust
)
from api.models import OptionPosition

logger = logging.getLogger(__name__)


class MonthlyStrategyStartAPIView(APIView):
    """
    POST /api/monthly-strategy/start/
    Manually start monthly strategy cycle
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            underlying = request.data.get("underlying", "BTC")
            force_start = request.data.get("force_start", False)
            
            logger.info(f"🚀 Starting monthly strategy - underlying={underlying}, force_start={force_start}")
            
            strategy = MonthlyDeltaStrategy(underlying=underlying, debug=True)
            
            # Check if we should start
            should_start = strategy.should_execute_monthly_start() or force_start
            
            if should_start:
                # Pass force_start to the start_monthly_cycle method
                result = strategy.start_monthly_cycle(force_start=force_start)
                
                if result.get("success", False):
                    return Response({
                        "success": True,
                        "message": result.get("message", "Monthly cycle started successfully"),
                        "data": result,
                        "timestamp": timezone.now().isoformat()
                    })
                else:
                    return Response({
                        "success": False,
                        "message": result.get("error", "Failed to start monthly cycle"),
                        "data": result,
                        "timestamp": timezone.now().isoformat()
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                cycle_id = strategy.get_current_cycle_id()
                existing_count = OptionPosition.objects.filter(
                    strategy_cycle_id=cycle_id,
                    is_initial_position=True
                ).count()
                
                return Response({
                    "success": False,
                    "message": f"Monthly cycle conditions not met. Existing positions: {existing_count}",
                    "existing_positions": existing_count,
                    "cycle_id": cycle_id,
                    "is_start_of_month": strategy.is_start_of_month(),
                    "note": "Use force_start=true to override conditions"
                })
                
        except Exception as e:
            logger.exception("Error starting monthly strategy")
            return Response({
                "success": False,
                "message": f"Failed to start monthly strategy: {str(e)}",
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MonthlyStrategyStatusAPIView(APIView):
    """
    GET /api/monthly-strategy/status/
    Get current monthly strategy status with detailed PnL breakdown
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        try:
            underlying = request.GET.get("underlying", "BTC")
            strategy = MonthlyDeltaStrategy(underlying=underlying, debug=False)
            
            # Import live position manager
            from .live_position_manager import live_position_manager
            
            cycle_id = strategy.get_current_cycle_id()
            
            # Use live Delta Exchange API data instead of database
            live_status = live_position_manager.get_live_strategy_status()
            
            if not live_status["success"]:
                return Response({
                    "success": False,
                    "error": live_status.get("error", "Failed to get live status"),
                    "timestamp": timezone.now().isoformat()
                }, status=500)
            
            # Get live PnL data
            total_realized_pnl = live_status.get("realized_pnl", 0.0)
            total_unrealized_pnl = live_status.get("unrealized_pnl", 0.0)
            total_pnl = live_status.get("total_pnl", 0.0)
            live_position_details = live_status.get("position_details", [])
            
            # Build response using live position data
            active_positions_data = []
            for pos_detail in live_position_details:
                active_positions_data.append({
                    'symbol': pos_detail.get('symbol'),
                    'size': pos_detail.get('size'),
                    'entry_price': pos_detail.get('entry_price'),
                    'current_price': pos_detail.get('current_price'),
                    'unrealized_pnl': pos_detail.get('unrealized_pnl'),
                    'realized_pnl': pos_detail.get('realized_pnl'),
                    'product_id': pos_detail.get('product_id')
                })
            
            # For now, we'll show empty closed positions since we're using live API
            # In future, we can get historical data from Delta's fill history API  
            closed_positions_data = []
            
            # No need to check expiry time for live positions as Delta handles this
            expiry_close_soon = False
            
            return Response({
                "success": True,
                "cycle_id": cycle_id,
                "underlying": underlying,
                "status": {
                    "active_positions": live_status.get("active_positions", 0),
                    "closed_positions": 0,
                    "expiry_close_time_reached": expiry_close_soon
                },
                "pnl_summary": {
                    "total_realized_pnl": total_realized_pnl,
                    "total_unrealized_pnl": total_unrealized_pnl,
                    "total_pnl": total_pnl,
                    "currency": "USD"
                },
                "positions": {
                    "active": active_positions_data,
                    "closed": closed_positions_data
                },
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.exception("Error getting monthly strategy status")
            return Response({
                "success": False,
                "error": f"Failed to get strategy status: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MonthlyStrategyAdjustAPIView(APIView):
    """
    POST /api/monthly-strategy/adjust/
    Manually trigger adjustment check
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            target_profit = float(request.data.get("target_profit_dollars", 1000.0))
            
            result = check_positions_and_adjust(target_profit)
            
            return Response({
                "success": True,
                "adjustment_result": result,
                "target_profit": target_profit,
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.exception("Error in manual adjustment check")
            return Response({
                "success": False,
                "error": f"Adjustment check failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MonthlyStrategyCloseAllAPIView(APIView):
    """
    POST /api/monthly-strategy/close-all/
    Manually close all active positions for current cycle
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        try:
            underlying = request.data.get("underlying", "BTC")
            reason = request.data.get("reason", "Manual close via API")
            
            strategy = MonthlyDeltaStrategy(underlying=underlying, debug=True)
            cycle_id = strategy.get_current_cycle_id()
            
            active_positions = list(
                OptionPosition.objects.filter(
                    strategy_cycle_id=cycle_id,
                    active=True
                )
            )
            
            if not active_positions:
                return Response({
                    "success": True,
                    "message": "No active positions to close",
                    "closed_count": 0,
                    "cycle_id": cycle_id
                })
            
            closed_positions = []
            errors = []
            
            for position in active_positions:
                if strategy.close_position(position, reason):
                    closed_positions.append({
                        "symbol": position.symbol,
                        "size": position.size,
                        "realized_pnl": float(position.realized_pnl)
                    })
                else:
                    errors.append(f"Failed to close {position.symbol}")
            
            return Response({
                "success": len(errors) == 0,
                "message": f"Closed {len(closed_positions)} positions",
                "closed_positions": closed_positions,
                "errors": errors,
                "closed_count": len(closed_positions),
                "cycle_id": cycle_id,
                "timestamp": timezone.now().isoformat()
            })
            
        except Exception as e:
            logger.exception("Error closing all positions")
            return Response({
                "success": False,
                "error": f"Failed to close positions: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
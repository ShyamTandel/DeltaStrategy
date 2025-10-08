"""
Live Delta Position Manager

This module uses Delta Exchange's live API endpoints to:
1. Get real-time positions from /positions/margined
2. Calculate live unrealized PnL using current market prices
3. Get realized PnL directly from Delta's API
4. Provide accurate position management without database duplication

Key Features:
- Real-time position data from Delta Exchange
- Accurate PnL calculations using live market prices
- No dependency on local database for position tracking
- Direct integration with Delta's position management APIs
"""

import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.db import models

from .delta_client import DeltaClient

logger = logging.getLogger(__name__)


class LiveDeltaPositionManager:
    """
    Manages positions using live Delta Exchange API data
    """
    
    def __init__(self, underlying: str = "BTC", debug: bool = True):
        self.underlying = underlying
        self.debug = debug
        self.client = DeltaClient(debug=debug)
        
    def log(self, message: str):
        """Log with timestamp"""
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_msg = f"[LIVE-POS] {message}"
        if self.debug:
            print(f"[{timestamp}] {log_msg}")
        logger.info(f"[{timestamp}] {log_msg}")
    
    def get_live_positions(self, contract_types: str = "call_options,put_options") -> Dict:
        """
        Get live positions from Delta Exchange API
        """
        try:
            self.log("📡 Fetching live positions from Delta Exchange...")
            
            # Get margined positions with options filter
            positions = self.client.get_positions()
            
            if not positions.get("success"):
                self.log(f"❌ Failed to get positions: {positions}")
                return {"success": False, "error": "Failed to fetch positions", "positions": []}
            
            result = positions.get("result", [])
            
            # Filter for options positions (call_options, put_options)
            option_positions = []
            for pos in result:
                product_symbol = pos.get("product_symbol", "")
                
                # Check if it's an option (contains C- or P- pattern)
                is_option = (
                    product_symbol.startswith("C-") or 
                    product_symbol.startswith("P-") or
                    "call" in product_symbol.lower() or 
                    "put" in product_symbol.lower()
                )
                
                # Check if position is open (non-zero size)
                size = float(pos.get("size", 0))
                
                if is_option and size != 0:
                    option_positions.append(pos)
            
            self.log(f"✅ Found {len(option_positions)} live option positions")
            
            return {
                "success": True,
                "positions": option_positions,
                "total_count": len(option_positions)
            }
            
        except Exception as e:
            self.log(f"❌ Error fetching live positions: {e}")
            return {"success": False, "error": str(e), "positions": []}
    
    def get_current_market_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current market prices for given option symbols
        """
        try:
            # Get option chain to find current prices
            tickers_resp = self.client.get_option_chain(underlying=self.underlying)
            tickers = tickers_resp.get("result", [])
            
            prices = {}
            for symbol in symbols:
                ticker = next((t for t in tickers if t.get("symbol") == symbol), None)
                if ticker:
                    mark_price = ticker.get("mark_price") or ticker.get("quotes", {}).get("best_bid", 0)
                    prices[symbol] = float(mark_price or 0)
                else:
                    self.log(f"⚠️ No market data found for {symbol}")
                    prices[symbol] = 0.0
            
            return prices
            
        except Exception as e:
            self.log(f"❌ Error fetching market prices: {e}")
            return {}
    
    def get_monthly_realized_pnl(self, cycle_id: str) -> float:
        """
        Get total realized PnL from closed positions in database for the current month
        """
        try:
            from .models import MonthlyPnLTracker
            
            total_realized = MonthlyPnLTracker.objects.filter(
                cycle_id=cycle_id
            ).aggregate(
                total=models.Sum('realized_pnl')
            )['total'] or 0.0
            
            self.log(f"💰 Monthly realized PnL ({cycle_id}): ${total_realized:.4f}")
            return float(total_realized)
            
        except Exception as e:
            self.log(f"❌ Error getting monthly realized PnL: {e}")
            return 0.0

    def calculate_live_pnl(self, positions: List[Dict], cycle_id: str) -> Dict:
        """
        Calculate PnL using correct logic:
        - Realized PnL = Sum of all closed positions from database for this month
        - Unrealized PnL = Sum of Delta's 'realized_pnl' field for open positions (which is actually unrealized)
        - Total PnL = Realized PnL + Unrealized PnL
        """
        try:
            # Get monthly realized PnL from closed positions in database
            monthly_realized_pnl = self.get_monthly_realized_pnl(cycle_id)
            
            # Calculate unrealized PnL from open positions
            total_unrealized_pnl = 0.0
            position_details = []
            
            for pos in positions:
                symbol = pos.get("product_symbol", "")
                size = float(pos.get("size", 0))
                entry_price = float(pos.get("entry_price", 0))
                mark_price = float(pos.get("mark_price", entry_price))
                
                # Use Delta's unrealized_pnl field for open positions
                unrealized_pnl = float(pos.get("unrealized_pnl", 0))
                total_unrealized_pnl += unrealized_pnl
                
                position_details.append({
                    "symbol": symbol,
                    "size": size,
                    "entry_price": entry_price,
                    "current_price": mark_price,  # Use mark_price as current price
                    "realized_pnl": 0.0,  # This position is still open, so no realized PnL yet
                    "unrealized_pnl": unrealized_pnl,
                    "product_id": pos.get("product_id")
                })
                
                self.log(f"📊 {symbol}: size={size}, entry=${entry_price:.4f}, mark=${mark_price:.4f}, "
                        f"unrealized_pnl=${unrealized_pnl:.4f}")
            
            total_pnl = monthly_realized_pnl + total_unrealized_pnl
            
            self.log(f"💰 PnL Summary: Monthly Realized=${monthly_realized_pnl:.4f}, "
                    f"Current Unrealized=${total_unrealized_pnl:.4f}, Total=${total_pnl:.4f}")
            
            return {
                "success": True,
                "realized_pnl": monthly_realized_pnl,
                "unrealized_pnl": total_unrealized_pnl,
                "total_pnl": total_pnl,
                "position_count": len(positions),
                "position_details": position_details
            }
            
        except Exception as e:
            self.log(f"❌ Error calculating live PnL: {e}")
            return {
                "success": False,
                "error": str(e),
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_pnl": 0.0,
                "position_count": 0,
                "position_details": []
            }
    
    def get_live_strategy_status(self, profit_target: float = 1000.0, cycle_id: str = None) -> Dict:
        """
        Get complete strategy status using live Delta Exchange data
        """
        try:
            self.log("🔍 Getting live strategy status...")
            
            # Get current cycle ID if not provided
            if not cycle_id:
                current_date = timezone.now()
                cycle_id = f"{current_date.year}-{current_date.month:02d}"
            
            # Get live positions
            positions_result = self.get_live_positions()
            if not positions_result["success"]:
                return {
                    "success": False,
                    "error": positions_result.get("error", "Failed to get positions"),
                    "status": "error"
                }
            
            positions = positions_result["positions"]
            
            if not positions:
                # Even if no open positions, get monthly realized PnL
                monthly_realized_pnl = self.get_monthly_realized_pnl(cycle_id)
                return {
                    "success": True,
                    "status": "no_positions",
                    "message": "No active option positions found",
                    "active_positions": 0,
                    "realized_pnl": monthly_realized_pnl,
                    "unrealized_pnl": 0.0,
                    "total_pnl": monthly_realized_pnl,
                    "target": profit_target,
                    "target_achieved": monthly_realized_pnl >= profit_target,
                    "position_details": [],
                    "cycle_id": cycle_id
                }
            
            # Calculate live PnL with cycle_id
            pnl_result = self.calculate_live_pnl(positions, cycle_id)
            if not pnl_result["success"]:
                return {
                    "success": False,
                    "error": pnl_result.get("error", "Failed to calculate PnL"),
                    "status": "error"
                }
            
            total_pnl = pnl_result["total_pnl"]
            target_achieved = total_pnl >= profit_target
            
            # Check if we should close positions (target achieved)
            action_needed = "monitor"
            if target_achieved:
                action_needed = "close_all_positions"
                self.log(f"🎯 TARGET ACHIEVED! PnL=${total_pnl:.4f} >= Target=${profit_target:.4f}")
            
            return {
                "success": True,
                "status": "active",
                "action_needed": action_needed,
                "active_positions": len(positions),
                "realized_pnl": pnl_result["realized_pnl"],
                "unrealized_pnl": pnl_result["unrealized_pnl"],
                "total_pnl": total_pnl,
                "target": profit_target,
                "target_achieved": target_achieved,
                "position_details": pnl_result["position_details"],
                "cycle_id": cycle_id,
                "timestamp": timezone.now().isoformat()
            }
            
        except Exception as e:
            self.log(f"❌ Error getting live strategy status: {e}")
            return {
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    def record_closed_position(self, symbol: str, realized_pnl: float, close_price: float, 
                              entry_price: float, size: float, cycle_id: str = None) -> bool:
        """
        Record a closed position's realized PnL in database
        """
        try:
            from .models import MonthlyPnLTracker
            
            if not cycle_id:
                current_date = timezone.now()
                cycle_id = f"{current_date.year}-{current_date.month:02d}"
            
            # Create record
            tracker = MonthlyPnLTracker.objects.create(
                cycle_id=cycle_id,
                underlying=self.underlying,
                closed_position_symbol=symbol,
                realized_pnl=realized_pnl,
                close_price=close_price,
                entry_price=entry_price,
                size=size,
                closed_at=timezone.now()
            )
            
            self.log(f"📝 Recorded closed position: {symbol} PnL=${realized_pnl:.4f}")
            return True
            
        except Exception as e:
            self.log(f"❌ Error recording closed position: {e}")
            return False

    def close_all_positions(self, reason: str = "Target achieved") -> Dict:
        """
        Close all positions using Delta Exchange API and record realized PnL
        """
        try:
            self.log(f"🔴 Closing all positions - {reason}")
            
            # First, get current positions to record their PnL when closed
            positions_result = self.get_live_positions()
            current_positions = positions_result.get("positions", []) if positions_result["success"] else []
            
            # Use Delta's close_all_positions API
            result = self.client.close_all_positions()
            
            if result.get("success"):
                self.log("✅ All positions closed successfully via Delta API")
                
                # Record realized PnL for each closed position
                current_date = timezone.now()
                cycle_id = f"{current_date.year}-{current_date.month:02d}"
                
                for pos in current_positions:
                    symbol = pos.get("product_symbol", "")
                    unrealized_pnl = float(pos.get("unrealized_pnl", 0))  # Use Delta's unrealized_pnl field
                    entry_price = float(pos.get("entry_price", 0))
                    mark_price = float(pos.get("mark_price", entry_price))
                    size = float(pos.get("size", 0))
                    
                    # When we close, the unrealized PnL becomes realized
                    self.record_closed_position(
                        symbol=symbol,
                        realized_pnl=unrealized_pnl,  # The unrealized becomes realized
                        close_price=mark_price,  # Use mark price as close price approximation
                        entry_price=entry_price,
                        size=size,
                        cycle_id=cycle_id
                    )
                
                return {
                    "success": True,
                    "message": "All positions closed successfully",
                    "reason": reason,
                    "closed_positions": len(current_positions)
                }
            else:
                self.log(f"❌ Failed to close positions: {result}")
                return {
                    "success": False,
                    "error": f"Delta API error: {result}",
                    "reason": reason
                }
                
        except Exception as e:
            self.log(f"❌ Error closing positions: {e}")
            return {
                "success": False,
                "error": str(e),
                "reason": reason
            }
    
    def monitor_and_adjust(self, profit_target: float = 1000.0) -> Dict:
        """
        Main monitoring function - checks positions and takes action if needed
        """
        try:
            # Get live strategy status
            status = self.get_live_strategy_status(profit_target)
            
            if not status["success"]:
                return status
            
            # Take action if needed
            if status.get("action_needed") == "close_all_positions":
                close_result = self.close_all_positions("Profit target achieved")
                status["close_result"] = close_result
                
                if close_result["success"]:
                    status["action_taken"] = "positions_closed"
                else:
                    status["action_taken"] = "close_failed"
            else:
                status["action_taken"] = "monitoring"
            
            return status
            
        except Exception as e:
            self.log(f"❌ Error in monitor_and_adjust: {e}")
            return {
                "success": False,
                "error": str(e),
                "status": "error"
            }


# Global instance
live_position_manager = LiveDeltaPositionManager()


def get_live_strategy_status(profit_target: float = 1000.0) -> Dict:
    """
    Get live strategy status using Delta Exchange APIs
    Called from views and monitoring systems
    """
    return live_position_manager.get_live_strategy_status(profit_target)


def monitor_positions_live(profit_target: float = 1000.0) -> Dict:
    """
    Monitor positions and take action if needed
    Called every 30 seconds by Celery task
    """
    return live_position_manager.monitor_and_adjust(profit_target)
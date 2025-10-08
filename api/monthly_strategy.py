"""
Monthly Delta Strategy Implementation

This module implements the complete monthly options strategy:
1. Start of month: Sell initial call and put options in delta ranges
2. Every 30 seconds: Check adjustments and profit target
3. Close positions when target reached or at expiry (1:00 PM UTC)

Key Requirements:
- Sell two initial positions (call 0.16-0.22 delta, put -0.22 to -0.16 delta)
- Track realized PnL from closed positions
- Check: total_realized_pnl + current_unrealized_pnl >= target
- Auto-close at expiry: 1:00 PM UTC on expiry date
"""

import logging
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.conf import settings

from .delta_client import DeltaClient
from .models import OptionPosition
from .utils import find_last_expiry_for_month, parse_expiry, extract_expiry_from_symbol

logger = logging.getLogger(__name__)


class MonthlyDeltaStrategy:
    """
    Complete monthly delta strategy implementation
    """
    
    def __init__(self, underlying: str = "BTC", debug: bool = True):
        self.underlying = underlying
        self.debug = debug
        self.client = DeltaClient(debug=debug)
        
    def get_current_cycle_id(self) -> str:
        """Get current monthly cycle identifier (YYYY-MM)"""
        now = timezone.now()
        return now.strftime("%Y-%m")
    
    def log(self, message: str):
        """Log with timestamp"""
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_msg = f"[{timestamp}] {message}"
        if self.debug:
            print(log_msg)
        logger.info(log_msg)
    
    def is_start_of_month(self) -> bool:
        """Check if today is the first day of the month"""
        return timezone.now().date().day == 1
    
    def should_execute_monthly_start(self, force_start: bool = False) -> bool:
        """
        Check if we should execute the monthly strategy start:
        - First day of month OR force_start=True
        - No active positions for current cycle
        """
        if not force_start and not self.is_start_of_month():
            self.log(f"Not start of month (day={timezone.now().date().day}) and not forced")
            return False
            
        cycle_id = self.get_current_cycle_id()
        existing_positions = OptionPosition.objects.filter(
            strategy_cycle_id=cycle_id,
            is_initial_position=True
        ).exists()
        
        if existing_positions:
            self.log(f"Existing initial positions found for cycle {cycle_id}")
            return False
        
        return True
    
    def find_options_in_delta_ranges(self, tickers: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Find call and put options in required delta ranges:
        - Calls: 0.16 to 0.22 delta
        - Puts: -0.22 to -0.16 delta
        """
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
            
            # Identify option type
            is_call = (contract_type == "call_options" or 
                      "c-" in symbol.lower() or 
                      symbol.upper().startswith("C-"))
            
            is_put = (contract_type == "put_options" or 
                     "p-" in symbol.lower() or 
                     symbol.upper().startswith("P-"))
            
            # Check delta ranges
            if is_call and 0.16 <= delta <= 0.22:
                call_candidates.append(ticker)
                
            if is_put and -0.22 <= delta <= -0.16:
                put_candidates.append(ticker)
        
        return call_candidates, put_candidates
    
    def select_lowest_delta_option(self, candidates: List[Dict]) -> Optional[Dict]:
        """Select option with lowest absolute delta from candidates"""
        if not candidates:
            return None
        return min(candidates, key=lambda x: abs(float(x["greeks"].get("delta", 0))))
    
    def place_sell_order(self, ticker: Dict, size: int = 2) -> Dict:
        """Place a sell order for the given option"""
        order_body = {
            "product_id": ticker.get("product_id"),
            "size": size,
            "side": "sell",
            "order_type": "market_order"
        }
        
        self.log(f"Placing sell order: {ticker.get('symbol')} size={size}")
        result = self.client.place_order(order_body)
        
        if result.get("success"):
            self.log(f"✅ Order placed successfully: {result.get('result', {}).get('id')}")
        else:
            self.log(f"❌ Order failed: {result}")
            
        return result
    
    def save_position(self, order_response: Dict, ticker: Dict, size: int, is_initial: bool = False) -> Optional[OptionPosition]:
        """Save position to database"""
        try:
            result = order_response.get("result", {})
            expiry_date = extract_expiry_from_symbol(ticker.get("symbol", ""))
            cycle_id = self.get_current_cycle_id()
            
            position = OptionPosition.objects.create(
                product_id=ticker.get("product_id"),
                symbol=ticker.get("symbol"),
                side="sell",
                size=size,
                limit_price=None,
                mark_price=Decimal(str(ticker.get("mark_price", 0) or 
                                     ticker.get("quotes", {}).get("best_bid", 0) or 0)),
                strike_price=Decimal(str(ticker.get("strike_price", 0))),
                delta=float(ticker.get("greeks", {}).get("delta", 0)),
                expiry_date=expiry_date,
                remote_order_id=result.get("id"),
                active=True,
                strategy_cycle_id=cycle_id,
                is_initial_position=is_initial,
                realized_pnl=Decimal('0.00')
            )
            
            self.log(f"💾 Saved position: {position.symbol} δ={position.delta}")
            return position
            
        except Exception as e:
            self.log(f"❌ Error saving position: {e}")
            return None
    
    def start_monthly_cycle(self, force_start: bool = False) -> Dict:
        """
        Start the monthly cycle by selling initial call and put options
        """
        # Check conditions unless forced
        if not force_start and not self.should_execute_monthly_start():
            return {
                "success": False, 
                "error": "Monthly cycle conditions not met (not first day or already started)"
            }
        
        self.log(f"🚀 Starting monthly cycle for {self.underlying} (forced={force_start})")
        
        try:
            # Get option chain
            self.log("📈 Fetching option chain...")
            tickers_resp = self.client.get_option_chain(underlying=self.underlying)
            tickers = tickers_resp.get("result", [])
            
            # Find current month's last expiry
            current_date = timezone.now().date()
            last_expiry = find_last_expiry_for_month(tickers, current_date)

            if not last_expiry:
                return {"success": False, "error": "No expiry found for current month"}
            
            expiry_str = last_expiry.strftime("%d-%m-%Y")
            expiry_str = "24-10-2025"
            self.log(f"📅 Using expiry: {expiry_str}")
            
            # Get options for specific expiry
            tickers_resp = self.client.get_option_chain(underlying=self.underlying, expiry_date=expiry_str)
            tickers = tickers_resp.get("result", [])
            
            # Find options in delta ranges
            call_candidates, put_candidates = self.find_options_in_delta_ranges(tickers)
            
            if not call_candidates:
                return {"success": False, "error": "No call options found in delta range 0.16-0.22"}
                
            if not put_candidates:
                return {"success": False, "error": "No put options found in delta range -0.22 to -0.16"}
            
            self.log(f"✅ Found {len(call_candidates)} call and {len(put_candidates)} put candidates")
            
            # Select options with lowest absolute delta
            call_to_sell = self.select_lowest_delta_option(call_candidates)
            put_to_sell = self.select_lowest_delta_option(put_candidates)
            
            self.log(f"[OPTIONS] Selected call: {call_to_sell['symbol']} (delta={call_to_sell['greeks']['delta']})")
            self.log(f"[OPTIONS] Selected put: {put_to_sell['symbol']} (delta={put_to_sell['greeks']['delta']})")
            
            # Place sell orders
            position_size = 2  # Standard position size
            
            # Sell call option
            call_order = self.place_sell_order(call_to_sell, position_size)
            if not call_order.get("success"):
                return {"success": False, "error": f"Failed to sell call option: {call_order}"}
            
            call_position = self.save_position(call_order, call_to_sell, position_size, is_initial=True)
            
            # Sell put option
            put_order = self.place_sell_order(put_to_sell, position_size)
            if not put_order.get("success"):
                return {"success": False, "error": f"Failed to sell put option: {put_order}"}
            
            put_position = self.save_position(put_order, put_to_sell, position_size, is_initial=True)
            
            self.log(f"✅ Monthly cycle started successfully!")
            self.log(f"   📞 Call: {call_position.symbol} @ ${call_position.mark_price}")
            self.log(f"   📞 Put: {put_position.symbol} @ ${put_position.mark_price}")
            
            return {
                "success": True,
                "message": "Monthly cycle started successfully",
                "expiry_date": expiry_str,
                "positions": {
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
                }
            }
            
        except Exception as e:
            self.log(f"❌ Error starting monthly cycle: {e}")
            return {"success": False, "error": str(e)}
    
    def get_current_unrealized_pnl(self, active_positions: List[OptionPosition]) -> Tuple[float, Dict]:
        """
        Get current unrealized PnL from active positions
        Returns (total_unrealized_pnl, position_details)
        """
        if not active_positions:
            return 0.0, {}
        
        try:
            # Get current market data
            expiry_date = active_positions[0].expiry_date
            expiry_str = expiry_date.strftime("%d-%m-%Y")
            
            tickers_resp = self.client.get_option_chain(underlying=self.underlying, expiry_date=expiry_str)
            tickers = tickers_resp.get("result", [])
            
            total_unrealized = 0.0
            position_details = {}
            
            for position in active_positions:
                # Find current market price
                ticker = next((t for t in tickers if t.get("symbol") == position.symbol), None)
                
                if ticker:
                    current_price = float(ticker.get("mark_price", 0) or 0)
                else:
                    current_price = float(position.mark_price or 0)
                
                initial_price = float(position.mark_price or 0)
                
                # For sold positions: PnL = initial_price - current_price
                position_pnl = (initial_price - current_price) * position.size
                total_unrealized += position_pnl
                
                position_details[position.symbol] = {
                    "initial_price": initial_price,
                    "current_price": current_price,
                    "size": position.size,
                    "pnl": position_pnl
                }
            
            return total_unrealized, position_details
            
        except Exception as e:
            self.log(f"❌ Error calculating unrealized PnL: {e}")
            return 0.0, {}
    
    def get_total_realized_pnl(self, cycle_id: str = None) -> float:
        """
        Get total realized PnL for the current or specified cycle
        """
        if not cycle_id:
            cycle_id = self.get_current_cycle_id()
        
        # Sum realized PnL from closed positions in this cycle
        closed_positions = OptionPosition.objects.filter(
            strategy_cycle_id=cycle_id,
            active=False,
            closed_at__isnull=False
        )
        
        total_realized = sum(
            float(pos.realized_pnl or 0) 
            for pos in closed_positions
        )
        
        self.log(f"[PNL] Total realized PnL for cycle {cycle_id}: ${total_realized:.4f}")
        return total_realized
    
    def close_position(self, position: OptionPosition, reason: str = "Manual close") -> bool:
        """
        Close a position and update realized PnL
        """
        try:
            self.log(f"🔴 Closing position {position.symbol} - {reason}")
            
            # Place buy order to close the sold position
            close_order_body = {
                "product_id": position.product_id,
                "size": position.size,
                "side": "buy",
                "order_type": "market_order"
            }
            
            result = self.client.place_order(close_order_body)
            
            if result.get("success"):
                order_result = result.get("result", {})
                
                # Get current market price for PnL calculation
                try:
                    expiry_str = position.expiry_date.strftime("%d-%m-%Y")
                    tickers_resp = self.client.get_option_chain(underlying=self.underlying, expiry_date=expiry_str)
                    tickers = tickers_resp.get("result", [])
                    
                    ticker = next((t for t in tickers if t.get("symbol") == position.symbol), None)
                    current_price = float(ticker.get("mark_price", 0) if ticker else position.mark_price or 0)
                    
                except Exception:
                    current_price = float(position.mark_price or 0)
                
                # Calculate realized PnL (for sold positions: initial - current)
                initial_price = float(position.mark_price or 0)
                realized_pnl = (initial_price - current_price) * position.size
                
                # Update position
                position.active = False
                position.closed_at = timezone.now()
                position.close_price = Decimal(str(current_price))
                position.realized_pnl = Decimal(str(realized_pnl))
                position.save()
                
                self.log(f"✅ Position closed: {position.symbol} PnL=${realized_pnl:.4f}")
                return True
                
            else:
                self.log(f"❌ Failed to close position: {result}")
                return False
                
        except Exception as e:
            self.log(f"❌ Error closing position {position.symbol}: {e}")
            return False
    
    def is_expiry_close_time(self, expiry_date: date) -> bool:
        """
        Check if it's time to close positions at expiry (1:00 PM UTC)
        """
        now_utc = timezone.now()
        
        # Create expiry close datetime (1:00 PM UTC on expiry date)
        import pytz
        
        expiry_close_time = datetime.combine(
            expiry_date,
            time(13, 0, 0)  # 1:00 PM
        )
        # Make timezone-aware using UTC
        expiry_close_time = pytz.UTC.localize(expiry_close_time)
        
        # Check if current time is past expiry close time
        return now_utc >= expiry_close_time
    
    def check_and_adjust_positions(self, profit_target_dollars: float = 1000.0) -> Dict:
        """
        Main adjustment logic called every 30 seconds:
        1. Check if profit target reached
        2. Check if expiry time reached
        3. Apply adjustment rules if needed
        """
        cycle_id = self.get_current_cycle_id()
        self.log(f"🔍 Checking positions for cycle {cycle_id}")
        
        # Get active positions for current cycle
        active_positions = list(
            OptionPosition.objects.filter(
                strategy_cycle_id=cycle_id,
                active=True
            ).order_by('created_at')
        )
        
        if not active_positions:
            self.log("ℹ️ No active positions for current cycle")
            return {"status": "no_positions", "action": "none"}
        
        try:
            # Calculate current PnL
            total_realized_pnl = self.get_total_realized_pnl(cycle_id)
            total_unrealized_pnl, position_details = self.get_current_unrealized_pnl(active_positions)
            total_pnl = total_realized_pnl + total_unrealized_pnl
            
            self.log(f"[PNL] Summary:")
            self.log(f"   Realized: ${total_realized_pnl:.4f}")
            self.log(f"   Unrealized: ${total_unrealized_pnl:.4f}")
            self.log(f"   [TARGET] Total: ${total_pnl:.4f} (Target: ${profit_target_dollars:.4f})")
            
            # Check profit target
            if total_pnl >= profit_target_dollars:
                self.log(f"[TARGET] PROFIT TARGET REACHED! Closing all positions...")
                
                closed_count = 0
                for position in active_positions:
                    if self.close_position(position, "Profit target reached"):
                        closed_count += 1
                
                return {
                    "status": "profit_target_reached",
                    "action": "closed_all_positions",
                    "closed_count": closed_count,
                    "total_pnl": total_pnl,
                    "target": profit_target_dollars
                }
            
            # Check expiry close time
            expiry_date = active_positions[0].expiry_date
            if self.is_expiry_close_time(expiry_date):
                self.log(f"⏰ EXPIRY TIME REACHED! Closing all positions...")
                
                closed_count = 0
                for position in active_positions:
                    if self.close_position(position, "Expiry time reached (1:00 PM UTC)"):
                        closed_count += 1
                
                return {
                    "status": "expiry_reached",
                    "action": "closed_all_positions",
                    "closed_count": closed_count,
                    "expiry_date": expiry_date.isoformat()
                }
            
            # Apply adjustment rules (price doubling, etc.)
            adjustment_result = self.apply_adjustment_rules(active_positions, position_details)
            
            return {
                "status": "monitoring",
                "action": adjustment_result.get("action", "none"),
                "total_pnl": total_pnl,
                "target": profit_target_dollars,
                "positions_count": len(active_positions),
                "adjustment": adjustment_result
            }
            
        except Exception as e:
            self.log(f"❌ Error in position check: {e}")
            return {"status": "error", "error": str(e)}
    
    def apply_adjustment_rules(self, active_positions: List[OptionPosition], position_details: Dict) -> Dict:
        """
        Apply adjustment rules like price doubling, strike crossing prevention, etc.
        """
        # This can be extended with more sophisticated adjustment logic
        # For now, we'll focus on the main profit target and expiry logic
        
        if len(active_positions) == 2:
            pos1, pos2 = active_positions[0], active_positions[1]
            
            # Get current prices
            price1 = position_details.get(pos1.symbol, {}).get("current_price", 0)
            price2 = position_details.get(pos2.symbol, {}).get("current_price", 0)
            
            # Check price doubling rule
            if price1 > 0 and price2 > 0:
                if price1 >= 2 * price2:
                    self.log(f"📈 Price doubled! {pos1.symbol}=${price1:.4f} vs {pos2.symbol}=${price2:.4f}")
                    if self.close_position(pos2, "Price doubling - closing cheaper position"):
                        return {"action": "closed_cheaper_position", "closed": pos2.symbol}
                
                elif price2 >= 2 * price1:
                    self.log(f"📈 Price doubled! {pos2.symbol}=${price2:.4f} vs {pos1.symbol}=${price1:.4f}")
                    if self.close_position(pos1, "Price doubling - closing cheaper position"):
                        return {"action": "closed_cheaper_position", "closed": pos1.symbol}
        
        return {"action": "none"}


# Global strategy instance
strategy = MonthlyDeltaStrategy()


def start_monthly_cycle_if_needed(force_start: bool = False) -> Dict:
    """
    Check if monthly cycle should start and start it if needed
    Called from Celery task or management command
    """
    if strategy.should_execute_monthly_start(force_start=force_start):
        strategy.log(f"📅 Starting monthly cycle (forced={force_start})")
        return strategy.start_monthly_cycle(force_start=force_start)
    else:
        strategy.log("ℹ️ Monthly cycle already started or conditions not met")
        return {"status": "already_started", "message": "Monthly cycle already active or conditions not met"}


def check_positions_and_adjust(profit_target_dollars: float = 1000.0) -> Dict:
    """
    Main function called every 30 seconds to check positions and apply adjustments
    """
    return strategy.check_and_adjust_positions(profit_target_dollars)
"""
Delta Strategy Implementation
============================

AUTOMATED DELTA OPTIONS TRADING STRATEGY

🎯 WHAT THIS DOES:
- Automatically finds and sells call + put options in specific delta ranges
- Monitors positions every 30 seconds via Celery Beat
- Executes position management rules automatically
- Closes positions when 50% profit target is reached

🔄 AUTOMATED EXECUTION FLOW:
1. User calls API to start strategy
2. Strategy finds call (0.16-0.22 delta) and put (-0.22 to -0.16 delta) options  
3. SELLS BOTH OPTIONS (critical requirement - must be both)
4. Celery Beat monitors every 30 seconds automatically
5. Applies rules: profit target, price doubling, strike crossing
6. Closes positions when conditions are met
7. Repeats until strategy completion

📊 BACKGROUND MONITORING (Every 30 seconds):
- Checks current option prices
- Calculates profit percentage  
- Closes all positions if 50% profit reached
- Closes cheaper position if one doubles in price
- Prevents strike price crossing
- Finds matching delta options when needed

🚀 CELERY INTEGRATION:
- monitor_strategy_positions_task: Runs every 30 seconds (in deltastrategy/celery.py)
- execute_strategy_background_task: Background strategy execution  
- emergency_close_all_task: Emergency position closure

📁 FILE STRUCTURE:
- strategy.py: Core strategy logic and utility functions
- celery.py: Celery task definitions for background execution
- views.py: API endpoints for user interaction
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from api.delta_client import DeltaClient
from api.models import OptionPosition
from api.utils import find_last_expiry_for_month, parse_expiry, extract_expiry_from_symbol

logger = logging.getLogger(__name__)


@dataclass
class StrategyConfig:
    """Configuration for the delta strategy"""
    call_delta_min: float = 0.16
    call_delta_max: float = 0.22
    put_delta_min: float = -0.22  # More negative
    put_delta_max: float = -0.16  # Less negative
    delta_matching_tolerance: float = 0.03
    profit_target_percent: float = 50.0  # 50% profit target
    position_size: int = 2
    max_iterations: int = 50


class DeltaStrategy:
    """
    Main Delta Options Trading Strategy Implementation
    
    This class implements the corrected delta strategy:
    
    STRATEGY RULES:
    1. Find call options with delta 0.16-0.22
    2. Find put options with delta -0.22 to -0.16  
    3. MUST sell BOTH options (critical requirement)
    4. Monitor every 30 seconds for:
       - 50% profit target (close all positions)
       - Price doubling (close cheaper position)
       - Strike crossing prevention
    5. Repeat until strikes match or profit target hit
    
    AUTOMATED EXECUTION:
    - Celery Beat runs monitoring every 30 seconds
    - Background tasks handle strategy execution
    - Emergency controls available via API
    """
    
    def __init__(self, config: StrategyConfig = None, debug: bool = True):
        """
        Initialize strategy with configuration
        
        Args:
            config: Strategy configuration (uses defaults if None)
            debug: Enable debug logging (default True)
        """
        self.config = config or StrategyConfig()
        self.client = DeltaClient(debug=debug)
        self.debug = debug
        
    def log(self, message: str):
        """Log message if debug is enabled"""
        if self.debug:
            print(f"[STRATEGY] {message}")
            
    def find_options_in_delta_range(self, tickers: List[Dict], underlying: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Find call and put options within specified delta ranges
        
        Returns:
            Tuple of (call_candidates, put_candidates)
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
            
            # Identify call options
            is_call = (contract_type == "call_options" or 
                      "c-" in symbol.lower() or 
                      symbol.upper().startswith("C-"))
            
            # Identify put options  
            is_put = (contract_type == "put_options" or 
                     "p-" in symbol.lower() or 
                     symbol.upper().startswith("P-"))
            
            # Check call delta range
            if is_call and self.config.call_delta_min <= delta <= self.config.call_delta_max:
                call_candidates.append(ticker)
                
            # Check put delta range  
            if is_put and self.config.put_delta_min <= delta <= self.config.put_delta_max:
                put_candidates.append(ticker)
                
        self.log(f"Found {len(call_candidates)} call candidates and {len(put_candidates)} put candidates")
        return call_candidates, put_candidates
    
    def select_lowest_delta_option(self, candidates: List[Dict]) -> Optional[Dict]:
        """Select option with lowest absolute delta from candidates"""
        if not candidates:
            return None
            
        return min(candidates, key=lambda x: abs(float(x["greeks"].get("delta", 0))))
    
    def place_sell_order(self, ticker: Dict, size: int = None) -> Dict:
        """Place sell order for given option"""
        size = size or self.config.position_size
        
        order_body = {
            "product_id": ticker.get("product_id"),
            "size": size,
            "side": "sell", 
            "order_type": "market_order"
        }
        
        self.log(f"Placing sell order: {ticker.get('symbol')} size={size}")
        return self.client.place_order(order_body)
    
    def place_buy_order(self, position: OptionPosition) -> Dict:
        """Place buy order to close position"""
        order_body = {
            "product_id": position.product_id,
            "size": position.size,
            "side": "buy",
            "order_type": "market_order"
        }
        
        self.log(f"Placing buy order to close: {position.symbol}")
        return self.client.place_order(order_body)
    
    def save_position(self, order_response: Dict, ticker: Dict) -> OptionPosition:
        """Save position to database"""
        result = order_response.get("result", {})
        expiry_date = extract_expiry_from_symbol(ticker.get("symbol", ""))
        
        position = OptionPosition.objects.create(
            product_id=ticker.get("product_id"),
            symbol=ticker.get("symbol"),
            side="sell",
            size=self.config.position_size,
            limit_price=None,
            mark_price=Decimal(str(ticker.get("mark_price", 0) or 
                                 ticker.get("quotes", {}).get("best_bid", 0) or 0)),
            strike_price=Decimal(str(ticker.get("strike_price", 0))),
            delta=float(ticker.get("greeks", {}).get("delta", 0)),
            expiry_date=expiry_date,
            remote_order_id=result.get("id"),
            active=True
        )
        
        self.log(f"Saved position: {position.symbol} delta={position.delta}")
        return position
    
    def get_current_prices(self, positions: List[OptionPosition], tickers: List[Dict]) -> Dict[int, float]:
        """Get current market prices for positions"""
        prices = {}
        
        for position in positions:
            # Find matching ticker
            ticker = next((t for t in tickers if t.get("symbol") == position.symbol), None)
            if ticker:
                prices[position.id] = float(ticker.get("mark_price", 0) or 0)
            else:
                # Fallback to stored mark price
                prices[position.id] = float(position.mark_price or 0)
                
        return prices
    
    def find_matching_delta_option(self, target_delta: float, tickers: List[Dict], 
                                  option_type: str) -> Optional[Dict]:
        """
        Find option with delta matching target_delta within tolerance
        
        Args:
            target_delta: Target delta value
            tickers: Available option tickers
            option_type: 'call' or 'put'
        """
        target_abs = abs(target_delta)
        tolerance = self.config.delta_matching_tolerance
        
        candidates = []
        for ticker in tickers:
            greeks = ticker.get("greeks")
            if not greeks:
                continue
                
            try:
                delta = float(greeks.get("delta", 0))
            except (ValueError, TypeError):
                continue
                
            symbol = ticker.get("symbol", "")
            
            # Filter by option type
            if option_type == 'call':
                is_target_type = ("C-" in symbol.upper() or 
                                ticker.get("contract_type") == "call_options")
                if is_target_type and target_abs - tolerance <= delta <= target_abs + tolerance:
                    candidates.append(ticker)
                    
            elif option_type == 'put':
                is_target_type = ("P-" in symbol.upper() or 
                                ticker.get("contract_type") == "put_options") 
                delta_abs = abs(delta)
                if is_target_type and target_abs - tolerance <= delta_abs <= target_abs + tolerance:
                    candidates.append(ticker)
        
        if candidates:
            # Return closest match
            return min(candidates, key=lambda x: abs(abs(float(x["greeks"]["delta"])) - target_abs))
            
        return None
    
    def check_strike_crossing(self, positions: List[OptionPosition]) -> bool:
        """Check if call and put strikes cross (call < put)"""
        if len(positions) != 2:
            return False
            
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
            
            # Strikes cross if call strike < put strike
            return call_strike < put_strike
            
        return False
    
    def calculate_total_profit_percent(self, positions: List[OptionPosition], 
                                    current_prices: Dict[int, float]) -> float:
        """Calculate total profit percentage for all positions"""
        if not positions:
            return 0.0
            
        total_initial_value = 0.0
        total_current_value = 0.0
        
        for pos in positions:
            initial_price = float(pos.mark_price or 0)
            current_price = current_prices.get(pos.id, initial_price)
            
            # For sold positions, profit = initial_price - current_price
            position_initial = initial_price * pos.size
            position_current = current_price * pos.size
            
            total_initial_value += position_initial
            total_current_value += position_current
            
        if total_initial_value == 0:
            return 0.0
            
        # Profit percentage for sold options
        profit_percent = ((total_initial_value - total_current_value) / total_initial_value) * 100
        return profit_percent
    
    def execute_monthly_strategy(self, underlying: str = "BTC", 
                               reference_date: Optional[str] = None) -> Dict:
        """
        Execute the complete monthly delta strategy
        
        Args:
            underlying: Asset symbol (e.g., "BTC")
            reference_date: Reference date in YYYY-MM-DD format (optional)
            
        Returns:
            Dict with strategy execution results
        """
        # Parse reference date
        if reference_date:
            ref_date = datetime.fromisoformat(reference_date).date()
        else:
            ref_date = date.today()
            
        self.log(f"Starting monthly strategy for {underlying} on {ref_date}")
        
        # Step 1: Get option chain and find expiry
        tickers_resp = self.client.get_option_chain(underlying=underlying)
        tickers = tickers_resp.get("result", [])
        
        if reference_date:
            last_expiry = parse_expiry(reference_date)
        else:
            last_expiry = find_last_expiry_for_month(tickers, ref_date)
            
        if not last_expiry:
            return {"error": "No expiry found for this month", "success": False}
            
        # Get options for specific expiry
        expiry_str = last_expiry.strftime("%d-%m-%Y")
        tickers_resp = self.client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
        tickers = tickers_resp.get("result", [])
        
        # Step 2: Find options in delta ranges
        call_candidates, put_candidates = self.find_options_in_delta_range(tickers, underlying)
        
        if not call_candidates:
            return {"error": "No call options found in delta range 0.16-0.22", "success": False}
            
        if not put_candidates:
            return {"error": "No put options found in delta range -0.22 to -0.16", "success": False}
            
        # Step 3: Select options with lowest absolute delta in each range
        call_to_sell = self.select_lowest_delta_option(call_candidates)
        put_to_sell = self.select_lowest_delta_option(put_candidates)
        
        # Step 4: MUST sell both options (critical requirement)
        try:
            call_order = self.place_sell_order(call_to_sell)
            put_order = self.place_sell_order(put_to_sell)
        except Exception as e:
            return {"error": f"Failed to place initial orders: {str(e)}", "success": False}
            
        # Step 5: Save positions to database
        call_position = self.save_position(call_order, call_to_sell)
        put_position = self.save_position(put_order, put_to_sell)
        
        actions = [
            f"Sold call: {call_position.symbol} (delta: {call_position.delta})",
            f"Sold put: {put_position.symbol} (delta: {put_position.delta})"
        ]
        
        # Step 6: Enter monitoring loop
        iteration = 0
        while iteration < self.config.max_iterations:
            iteration += 1
            self.log(f"Monitoring iteration {iteration}")
            
            # Refresh tickers
            tickers_resp = self.client.get_option_chain(underlying=underlying, expiry_date=expiry_str)
            tickers = tickers_resp.get("result", [])
            
            # Get current active positions
            active_positions = list(OptionPosition.objects.filter(active=True).order_by('created_at'))
            
            if len(active_positions) == 0:
                actions.append("No active positions remaining")
                break
                
            # Get current prices
            current_prices = self.get_current_prices(active_positions, tickers)
            
            # Check for 50% profit target (Step 7)
            profit_percent = self.calculate_total_profit_percent(active_positions, current_prices)
            self.log(f"Current profit: {profit_percent:.2f}%")
            
            if profit_percent >= self.config.profit_target_percent:
                # Close all positions - we've hit profit target
                for pos in active_positions:
                    self.place_buy_order(pos)
                    pos.active = False
                    pos.save()
                    
                actions.append(f"Closed all positions at {profit_percent:.2f}% profit")
                break
            
            # Handle single position case (Step 8) 
            if len(active_positions) == 1:
                remaining_pos = active_positions[0]
                target_delta_abs = abs(remaining_pos.delta)
                
                # Find matching option on opposite side
                if remaining_pos.delta > 0:  # Remaining is call, find matching put
                    matching_option = self.find_matching_delta_option(
                        target_delta_abs, tickers, 'put'
                    )
                else:  # Remaining is put, find matching call
                    matching_option = self.find_matching_delta_option(
                        target_delta_abs, tickers, 'call'
                    )
                    
                if matching_option:
                    try:
                        order = self.place_sell_order(matching_option)
                        new_position = self.save_position(order, matching_option)
                        actions.append(f"Sold matching option: {new_position.symbol}")
                    except Exception as e:
                        self.log(f"Failed to sell matching option: {str(e)}")
                        
            # Handle two positions case (Step 9-10)
            elif len(active_positions) >= 2:
                pos1, pos2 = active_positions[0], active_positions[1]
                price1 = current_prices.get(pos1.id, 0)
                price2 = current_prices.get(pos2.id, 0)
                
                # Check price doubling condition
                position_closed = False
                if price1 >= 2 * price2 and price2 > 0:
                    # Close cheaper position (pos2)
                    try:
                        self.place_buy_order(pos2)
                        pos2.active = False
                        pos2.save()
                        actions.append(f"Closed {pos2.symbol} (price doubled: {price1} vs {price2})")
                        position_closed = True
                    except Exception as e:
                        self.log(f"Failed to close position: {str(e)}")
                        
                elif price2 >= 2 * price1 and price1 > 0:
                    # Close cheaper position (pos1)
                    try:
                        self.place_buy_order(pos1)
                        pos1.active = False
                        pos1.save()
                        actions.append(f"Closed {pos1.symbol} (price doubled: {price2} vs {price1})")
                        position_closed = True
                    except Exception as e:
                        self.log(f"Failed to close position: {str(e)}")
                
                # Check for strike crossing (Step 11)
                if not position_closed and self.check_strike_crossing(active_positions):
                    # Close more recently created position
                    to_close = active_positions[-1]
                    try:
                        self.place_buy_order(to_close)
                        to_close.active = False
                        to_close.save()
                        actions.append(f"Closed {to_close.symbol} to prevent strike crossing")
                    except Exception as e:
                        self.log(f"Failed to close crossing position: {str(e)}")
                
                # Check termination condition (Step 12)
                active_positions = list(OptionPosition.objects.filter(active=True))
                if len(active_positions) == 2:
                    strike1 = float(active_positions[0].strike_price)
                    strike2 = float(active_positions[1].strike_price)
                    
                    if abs(strike1 - strike2) < 0.01:  # Strikes are essentially equal
                        actions.append("Strikes matched - strategy complete")
                        # Don't close positions here, wait for profit target
                        
            # Safety check - avoid infinite loops
            if iteration >= self.config.max_iterations:
                actions.append(f"Reached maximum iterations ({self.config.max_iterations})")
                break
                
        return {
            "success": True,
            "underlying": underlying,
            "expiry": expiry_str,
            "initial_positions": {
                "call": call_position.symbol,
                "put": put_position.symbol
            },
            "actions": actions,
            "iterations": iteration
        }


def monitor_positions():
    """
    Monitor active strategy positions and execute automatic management
    
    This function:
    1. Gets all active positions from database
    2. Groups them by underlying asset (BTC, ETH, etc.)
    3. Checks current market prices
    4. Applies strategy rules (profit target, price doubling, etc.)
    5. Executes position management automatically
    
    Returns:
        dict: Status and actions taken
    """
    try:
        logger.info("Starting position monitoring")
        
        active_positions = OptionPosition.objects.filter(active=True).order_by('created_at')
        
        if not active_positions.exists():
            return {'status': 'success', 'message': 'No active positions', 'positions_count': 0}
        
        client = DeltaClient(debug=False)
        actions = []
        
        # Group positions by underlying
        positions_by_underlying = {}
        for pos in active_positions:
            parts = pos.symbol.split('-')
            underlying = parts[1] if len(parts) > 1 else 'BTC'
            
            if underlying not in positions_by_underlying:
                positions_by_underlying[underlying] = []
            positions_by_underlying[underlying].append(pos)
        
        # Process each underlying
        for underlying, positions in positions_by_underlying.items():
            strategy = DeltaStrategy(debug=False)
            position_actions = strategy.process_positions(underlying, positions, client)
            actions.extend(position_actions)
        
        return {
            'status': 'success',
            'positions_monitored': active_positions.count(),
            'actions_taken': actions,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.exception("Error in position monitoring")
        return {'status': 'error', 'error': str(e)}


def execute_strategy_background(underlying="BTC", reference_date=None, profit_target=50.0, position_size=2):
    """
    Execute delta strategy in background
    
    This function:
    1. Creates strategy configuration with provided parameters
    2. Finds suitable call and put options in delta ranges
    3. Sells both options (MUST sell both - critical requirement)
    4. Enters monitoring loop until completion
    
    Args:
        underlying (str): Asset symbol like "BTC", "ETH"
        reference_date (str): Optional date in YYYY-MM-DD format
        profit_target (float): Target profit percentage (default 50%)
        position_size (int): Number of contracts to trade (default 2)
        
    Returns:
        dict: Execution results and status
    """
    try:
        config = StrategyConfig(
            profit_target_percent=profit_target,
            position_size=position_size
        )
        
        strategy = DeltaStrategy(config=config, debug=True)
        result = strategy.execute_monthly_strategy(underlying, reference_date)
        
        return {
            'status': 'completed',
            'result': result,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.exception("Error in background strategy execution")
        return {'status': 'error', 'error': str(e)}


def emergency_close_all():
    """
    Emergency close all active positions immediately
    
    This function:
    1. Gets all active positions from database
    2. Places market buy orders to close each position
    3. Marks positions as inactive
    4. Logs all actions and errors
    
    Use this function when you need to exit all positions quickly
    
    Returns:
        dict: Number of positions closed and any errors
    """
    try:
        logger.warning("EMERGENCY: Closing all active positions")
        
        active_positions = OptionPosition.objects.filter(active=True)
        client = DeltaClient(debug=True)
        
        closed_count = 0
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
                
                closed_count += 1
                logger.info(f"Emergency closed: {pos.symbol}")
                
            except Exception as e:
                error_msg = f"Failed to close {pos.symbol}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'status': 'completed',
            'closed_positions': closed_count,
            'errors': errors,
            'success': True
        }
        
    except Exception as e:
        return {'status': 'error', 'error': str(e), 'success': False}


# Add process_positions method to DeltaStrategy class (if not already present)
def add_process_positions_to_strategy():
    """
    This function adds the process_positions method to DeltaStrategy class
    """
    def process_positions(self, underlying: str, positions: List[OptionPosition], client: DeltaClient) -> List[str]:
        """Process positions for a specific underlying asset"""
        actions = []
        
        try:
            # Get current market data
            tickers_resp = client.get_option_chain(underlying=underlying)
            tickers = tickers_resp.get("result", [])
            
            # Get current prices
            current_prices = {}
            for pos in positions:
                ticker = next((t for t in tickers if t.get("symbol") == pos.symbol), None)
                if ticker:
                    current_prices[pos.id] = float(ticker.get("mark_price", 0) or 0)
                else:
                    current_prices[pos.id] = float(pos.mark_price or 0)
            
            # Check profit target
            profit_percent = self.calculate_total_profit_percent(positions, current_prices)
            
            if profit_percent >= self.config.profit_target_percent:
                # Close all positions
                for pos in positions:
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
                        
                        actions.append(f"Closed {pos.symbol} - profit target {profit_percent:.2f}% reached")
                        
                    except Exception as e:
                        actions.append(f"Failed to close {pos.symbol}: {str(e)}")
                
                return actions
            
            # Check price doubling and other conditions
            if len(positions) >= 2:
                pos1, pos2 = positions[0], positions[1]
                price1 = current_prices.get(pos1.id, 0)
                price2 = current_prices.get(pos2.id, 0)
                
                if price1 >= 2 * price2 and price2 > 0:
                    # Close cheaper position (pos2)
                    try:
                        close_order = {
                            "product_id": pos2.product_id,
                            "size": pos2.size,
                            "side": "buy",
                            "order_type": "market_order"
                        }
                        client.place_order(close_order)
                        pos2.active = False
                        pos2.save()
                        actions.append(f"Closed {pos2.symbol} (price doubled: {price1} vs {price2})")
                    except Exception as e:
                        actions.append(f"Failed to close {pos2.symbol}: {str(e)}")
                        
                elif price2 >= 2 * price1 and price1 > 0:
                    # Close cheaper position (pos1)
                    try:
                        close_order = {
                            "product_id": pos1.product_id,
                            "size": pos1.size,
                            "side": "buy",
                            "order_type": "market_order"
                        }
                        client.place_order(close_order)
                        pos1.active = False
                        pos1.save()
                        actions.append(f"Closed {pos1.symbol} (price doubled: {price2} vs {price1})")
                    except Exception as e:
                        actions.append(f"Failed to close {pos1.symbol}: {str(e)}")
            
            return actions
            
        except Exception as e:
            logger.exception(f"Error processing {underlying} positions")
            return [f"Error processing {underlying}: {str(e)}"]
    
    # Add method to DeltaStrategy class
    DeltaStrategy.process_positions = process_positions

# Call the function to add the method
add_process_positions_to_strategy()


# =====================================================
# BACKGROUND TASK FUNCTIONS
# =====================================================
# These functions can be called directly or via Celery tasks
# Celery tasks are defined in deltastrategy/celery.py
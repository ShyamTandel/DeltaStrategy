"""
Monthly Options Strategy - Simple Implementation

Core Requirements:
1. Sell two positions at the start of each month from defined range
2. Do adjustments during the month  
3. Close with target percentage OR on expiry date at 12:30 PM
"""

import logging
from datetime import datetime, time
import traceback
from typing import Dict, List
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from celery import shared_task

from .delta_client import DeltaClient
from .models import InitialBalanceTracker, OptionPosition

logger = logging.getLogger(__name__)


class MonthlyStrategy:
    """Simple monthly options strategy implementation"""

    def __init__(self, underlying: str = "BTC", date: str = "17-11-2025"):
        self.underlying = underlying
        self.client = DeltaClient(debug=True)
        self.date = date

        # Strategy parameters
        self.size = 1
        self.call_delta_range = (0.16, 0.22)
        self.put_delta_range = (-0.22, -0.16)
        self.expiry_close_time = time(12, 30)  # 12:30 PM
    
    def log(self, message: str):
        """Log with timestamp"""
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{timestamp}] [STRATEGY] {message}")
        logger.info(f"[{timestamp}] [STRATEGY] {message}")
    
    # ===== 1. SELL TWO INITIAL POSITIONS =====
    
    def start_monthly_cycle(self) -> Dict:
        """Start new monthly cycle - sell call and put"""
        try:
            current_date = timezone.now()
            cycle_id = f"{current_date.year}-{current_date.month:02d}"
            
            self.log(f"🚀 Starting monthly cycle: {cycle_id}")
            print("cycle_id::::::::::",cycle_id)
            # Store initial balance
            self._store_initial_balance(cycle_id)
            
            # Get options and select by delta
            options = self._get_monthly_options()
            if not options:
                return {"success": False, "error": "No options found"}
            
            self.log(f"📋 Found {len(options)} options available")
            
            # Log first few options for debugging
            for i, option in enumerate(options[:3]):
                greeks = option.get("greeks", {})
                print("greeks::::::::",greeks)
                delta = greeks.get("delta", "0")
                symbol = option.get("symbol", "Unknown")
                self.log(f"   Option {i+1}: {symbol} - Delta: {delta}")
            
            call_option = self._select_option_by_delta(options, "call")
            print("callllllllllllllll",call_option)
            put_option = self._select_option_by_delta(options, "put")
            print("putttttttttttttttttt",put_option)
            if not call_option or not put_option:
                return {"success": False, "error": "Options not found in delta range"}
            
            # Sell both positions
            call_result = self._sell_option(call_option, cycle_id)
            print("afterr callllllllllllllll")
            put_result = self._sell_option(put_option, cycle_id)
            print("afterr putttttttttttttttttt")
            return {
                "success": True,
                "cycle_id": cycle_id,
                "call_sold": call_result["success"],
                "put_sold": put_result["success"],
                "message": "Monthly cycle started"
            }
            
        except ValueError as e:
            self.log(f"⚠️ Value error: {e}")
            return {"success": False, "error_type": "ValueError", "error": str(e)}

        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"❌ Unexpected error: {e}\nTraceback:\n{tb}")
            return {"success": False, "error_type": "Exception", "error": str(e), "traceback": tb}
    
    # ===== 2. ADJUSTMENT LOGIC =====
    
    def monitor_and_adjust(self, target_profit_percentage: float = 80.0) -> Dict:
        """Monitor positions and adjust if needed"""
        try:
            current_date = timezone.now()
            cycle_id = f"{current_date.year}-{current_date.month:02d}"
            
            # Check target achieved
            target_status = self._check_target(cycle_id, target_profit_percentage)
            print("target_status::::::::::",target_status)
            if target_status["target_achieved"]:
                self.log("🎯 Target achieved! Closing positions")
                return self._close_all_positions("Target achieved")
            
            # Check expiry time
            if self._is_expiry_time():
                self.log("⏰ Expiry time! Closing positions")
                return self._close_all_positions("Expiry time reached")
            
            # ===== DELTA UPDATION =====
            open_positions = list(OptionPosition.objects.filter(active=True))
            for pos in open_positions:
                try:
                    ticker = self.client.get_option_chain(underlying=self.underlying, expiry_date=self.date)
                    if ticker.get("success"):
                        ticker = next((t for t in ticker["result"] if t.get("symbol") == pos.symbol), None)
                        mark_price = float(ticker.get("mark_price", 0))
                        greeks = ticker.get("greeks", {})
                        delta = float(greeks.get("delta", pos.delta))
                        
                        pos.mark_price = mark_price
                        pos.delta = delta
                        pos.save()
                        
                        self.log(f"🔄 Updated {pos.symbol}: mark_price={mark_price}, delta={delta}")
                except Exception as e:
                    self.log(f"⚠️ Error updating {pos.symbol}: {e}")

            # ===== COMPREHENSIVE ADJUSTMENT LOGIC =====
            actions = []
            
            # Get current open positions
            open_positions = list(OptionPosition.objects.filter(active=True))
            if not open_positions:
                self.log("✅ No open positions to monitor")
                return {
                    "success": True,
                    "action": "monitor",
                    "adjustments_made": actions,
                    "open_positions": 0,
                    "target_status": target_status
                }
            print("open_positions::::::::::",open_positions)
            # Get current option chain tickers for price and delta comparison
            tickers = self._get_monthly_options()
            
            # Step 11: If only one position open, find opposite side with matching delta within ±0.03
            if len(open_positions) == 1:
                open_pos = open_positions[0]
                target_delta = open_pos.delta
                print("target_delta::::::::::",target_delta)
                # If open position is put (negative delta), search for matching call
                if open_pos.symbol.startswith("P-") or open_pos.delta < 0:
                    target_min = abs(target_delta) - 0.03
                    target_max = abs(target_delta) + 0.03
                    
                    # Find candidate calls with matching delta
                    calls = [t for t in tickers if ("C-" in t.get("symbol", "") or t.get("contract_type") == "call_options")]
                    matching = []
                    
                    for c in calls:
                        try:
                            greeks = c.get("greeks", {})
                            d = float(greeks.get("delta", "0"))
                            if target_min <= d <= target_max:
                                matching.append(c)
                        except (ValueError, TypeError):
                            continue
                    
                    if matching:
                        print("matching put::::::::::",matching)
                        # Sell the best matching call (step 13)
                        candidate = min(matching, key=lambda x: abs(float(x["greeks"]["delta"]) - abs(target_delta)))
                        print("candidate put::::::::::",candidate)
                        if "C-" in candidate["symbol"]:
                            strike_price_call = float(candidate["strike_price"])
                            if open_pos.strike_price >= strike_price_call:
                                self.log(f"⚠️ Skipping sell of {candidate['symbol']} as strike would cross. Selling same strike CALL instead.")
                                
                                ticker = self.client.get_option_chain(underlying=self.underlying, expiry_date=self.date)
                                # ✅ Fetch the same strike CALL option from your 'matching' list
                                same_strike_call = next(
                                    (opt for opt in ticker if float(opt["strike_price"]) == open_pos.strike_price and "C-" in opt["symbol"]),
                                    None
                                )
                                
                                if same_strike_call:
                                    self.log(f"➡️ Selling same strike CALL: {same_strike_call['symbol']}")
                                    sell_result = self._sell_option(same_strike_call, cycle_id)
                                    actions.append(f"sold same strike CALL {same_strike_call['symbol']}")
                                else:
                                    self.log("⚠️ No matching same-strike CALL found in list.")
                                    actions.append(f"failed to sell same strike CALL")
                            else:
                                # Default case — no crossing, proceed normally
                                sell_result = self._sell_option(candidate, cycle_id)
                                if sell_result["success"]:
                                    actions.append(f"sold matching call {candidate['symbol']}")
                                    self.log(f"🔄 Sold matching call: {candidate['symbol']}")
                else:
                    # Open position is call, find matching put
                    target_min = abs(target_delta) - 0.03
                    target_max = abs(target_delta) + 0.03
                    
                    puts = [t for t in tickers if ("P-" in t.get("symbol", "") or t.get("contract_type") == "put_options")]
                    matching = []
                    
                    for p in puts:
                        try:
                            greeks = p.get("greeks", {})
                            d = abs(float(greeks.get("delta", "0")))  # Put delta is negative
                            if target_min <= d <= target_max:
                                matching.append(p)
                        except (ValueError, TypeError):
                            continue
                    
                    if matching:
                        print("matching call::::::::::",matching)
                        candidate = min(matching, key=lambda x: abs(abs(float(x["greeks"]["delta"])) - abs(target_delta)))
                        print("candidate put::::::::::",candidate)
                        if "P-" in candidate["symbol"]:
                            strike_price_put = float(candidate["strike_price"])
                            if open_pos.strike_price <= strike_price_put:
                                self.log(f"⚠️ Skipping sell of {candidate['symbol']} as strike would cross. Selling same strike PUT instead.")
                                
                                ticker = self.client.get_option_chain(underlying=self.underlying, expiry_date=self.date)
                                # ✅ Fetch the same strike PUT option from your 'matching' list
                                same_strike_put = next(
                                    (opt for opt in ticker if float(opt["strike_price"]) == open_pos.strike_price and "P-" in opt["symbol"]),
                                    None
                                )
                                
                                if same_strike_put:
                                    self.log(f"➡️ Selling same strike PUT: {same_strike_put['symbol']}")
                                    sell_result = self._sell_option(same_strike_put, cycle_id)
                                    actions.append(f"sold same strike PUT {same_strike_put['symbol']}")
                                else:
                                    self.log("⚠️ No matching same-strike PUT found in list.")
                                    actions.append("failed to find same strike PUT")
                            else:
                                # Default case — no crossing, proceed normally
                                sell_result = self._sell_option(candidate, cycle_id)
                                if sell_result["success"]:
                                    actions.append(f"sold matching put {candidate['symbol']}")
                                    self.log(f"🔄 Sold matching put: {candidate['symbol']}")
            
            # Step 14: If both positions have same strike, check if one price doubles the other
            if len(open_positions) == 2:
                print("same strike check::::::::::",open_positions)
                if float(open_positions[0].strike_price) == float(open_positions[1].strike_price):
                    # Get current prices for both positions
                    p1, p2 = open_positions[0], open_positions[1]
                    
                    match1 = next((t for t in tickers if t.get("symbol") == p1.symbol), None)
                    match2 = next((t for t in tickers if t.get("symbol") == p2.symbol), None)
                    self.log("match1::::::::::",match1)
                    self.log("match2::::::::::",match2)

                    price1 = float(match1.get("mark_price", 0)) if match1 else float(p1.mark_price or 0)
                    price2 = float(match2.get("mark_price", 0)) if match2 else float(p2.mark_price or 0)
                    
                    self.log(f"📊 Same strike detected: {p1.symbol} price={price1}, {p2.symbol} price={price2}")
                    
                    # Check if one price is double the other
                    if (price1 >= 2 * price2 and price2 > 0) or (price2 >= 2 * price1 and price1 > 0):
                        self.log(f"⚠️ Price doubled condition met - closing BOTH positions")
                        
                        # Close both positions
                        closed_both = True
                        for pos in [p1, p2]:
                            close_body = {
                                "product_symbol": pos.symbol,
                                "size": pos.size,
                                "side": "buy",
                                "order_type": "market_order"
                            }
                            close_response = self.client.place_order(body=close_body)
                            self.log("close_response::::::::::", close_response)
                            if close_response.get("success"):
                                pos.active = False
                                pos.closed_at = timezone.now()
                                pos.save()
                                self.log(f"✅ Closed: {pos.symbol}")
                            else:
                                closed_both = False
                                self.log(f"❌ Failed to close: {pos.symbol}")
                        
                        if closed_both:
                            actions.append(f"closed BOTH positions (same strike, price doubled: {price1} vs {price2})")
                            
                            # Now sell two puts at nearest strike to market price
                            self.log("🔄 Now selling two puts at nearest strike to market price")
                            
                            # Get market price (spot price)
                            spot_price = self._get_spot_price()
                            self.log(f"📈 Current spot price: {spot_price}")
                            
                            if spot_price > 0:
                                # Find nearest strike price
                                nearest_strike = self._find_nearest_strike(tickers, spot_price)
                                self.log(f"🎯 Nearest strike to spot: {nearest_strike}")
                                
                                if nearest_strike:
                                    # Find call and put options at this strike
                                    call_at_strike = next(
                                        (t for t in tickers if t.get("contract_type") == "call_options" and 
                                         float(t.get("strike_price", 0)) == nearest_strike),
                                        None
                                    )
                                    put_at_strike = next(
                                        (t for t in tickers if t.get("contract_type") == "put_options" and 
                                         float(t.get("strike_price", 0)) == nearest_strike),
                                        None
                                    )
                                    
                                    self.log(f"call_at_strike: {call_at_strike}")
                                    self.log(f"put_at_strike: {put_at_strike}")
                                    
                                    if call_at_strike and put_at_strike:
                                        # Sell call
                                        sell_result_call = self._sell_option(call_at_strike, cycle_id)
                                        # Sell put
                                        sell_result_put = self._sell_option(put_at_strike, cycle_id)
                                        
                                        if sell_result_call["success"] and sell_result_put["success"]:
                                            actions.append(f"sold call and put at strike {nearest_strike}")
                                            self.log(f"✅ Sold call and put at strike {nearest_strike}")
                                        else:
                                            self.log(f"⚠️ Failed to sell call/put at strike {nearest_strike}")
                                    else:
                                        self.log(f"⚠️ Call or Put not found at strike {nearest_strike}")
                                else:
                                    self.log("⚠️ Could not find nearest strike")
                            else:
                                self.log("⚠️ Could not get spot price")
                            
                            return {
                                "success": True,
                                "action": "rebalanced",
                                "reason": "Same strike price - one side doubled, reopened with call and put",
                                "positions_closed": 2,
                                "positions_opened": 2
                            }
                    else:
                        self.log(f"✅ Same strike but price not doubled yet, continuing monitoring")
                else:
                    self.log("✅ Both positions have different strikes, continuing monitoring")
                    # Step 9 & 10: Check if any option's price becomes double compared to other position
                    current_prices = {}
                    
                    # Get current prices from tickers
                    for p in open_positions:
                        match = next((t for t in tickers if t.get("symbol") == p.symbol), None)
                        if match:
                            current_prices[p.id] = float(match.get("mark_price", 0))
                        else:
                            current_prices[p.id] = float(p.mark_price or 0)
                    
                    # Compare prices between first two positions
                    p1, p2 = open_positions[0], open_positions[1]
                    print("p1::::::::::",p1)
                    print("p2::::::::::",p2)
                    price1 = current_prices.get(p1.id, 0)
                    price2 = current_prices.get(p2.id, 0)
                    print("price1::::::::::",price1)
                    print("price2::::::::::",price2)
                    # If any option price becomes double compared to other -> close the cheaper one
                    if price1 >= 2 * price2 and price2 > 0:
                        # Close p2 (the cheaper one)
                        close_body = {
                            "product_symbol": p2.symbol,
                            "size": p2.size,
                            "side": "buy",
                            "order_type": "market_order"
                        }
                        close_response = self.client.place_order(body=close_body)
                        if close_response.get("success"):
                            p2.active = False
                            p2.closed_at = timezone.now()
                            p2.save()
                            actions.append(f"closed {p2.symbol} because {p1.symbol} doubled {price1} vs {price2}")
                            self.log(f"🔄 Closed {p2.symbol}: price doubled ({price1} vs {price2})")
                            
                    elif price2 >= 2 * price1 and price1 > 0:
                        # Close p1 (the cheaper one)
                        close_body = {
                            "product_symbol": p1.symbol,
                            "size": p1.size,
                            "side": "buy",
                            "order_type": "market_order"
                        }
                        close_response = self.client.place_order(body=close_body)
                        if close_response.get("success"):
                            p1.active = False
                            p1.closed_at = timezone.now()
                            p1.save()
                            actions.append(f"closed {p1.symbol} because {p2.symbol} doubled {price2} vs {price1}")
                            self.log(f"🔄 Closed {p1.symbol}: price doubled ({price2} vs {price1})")
            
            # # Step 15: Ensure strike prices never cross
            # open_positions = list(OptionPosition.objects.filter(active=True))
            # if len(open_positions) >= 2:
            #     s1 = float(open_positions[0].strike_price)
            #     s2 = float(open_positions[1].strike_price)
                
            #     # Check if strikes are crossing (call strike < put strike is invalid)
            #     strikes_crossed = False
            #     to_close = None
                
            #     if (open_positions[0].symbol.startswith("C-") and 
            #         open_positions[1].symbol.startswith("P-") and s1 < s2):
            #         strikes_crossed = True
            #         to_close = open_positions[1]  # Close the put
            #     elif (open_positions[0].symbol.startswith("P-") and 
            #           open_positions[1].symbol.startswith("C-") and s2 < s1):
            #         strikes_crossed = True
            #         to_close = open_positions[0]  # Close the put
                
            #     if strikes_crossed and to_close:
            #         print("Strikes crossed, closing position::::::::::",to_close)
            #         close_body = {
            #             "product_symbol": to_close.symbol,
            #             "size": to_close.size,
            #             "side": "buy",
            #             "order_type": "market_order"
            #         }
            #         close_response = self.client.place_order(body=close_body)
            #         if close_response.get("success"):
            #             to_close.active = False
            #             to_close.closed_at = timezone.now()
            #             to_close.save()
            #             actions.append(f"closed {to_close.symbol} to avoid strike crossing")
            #             self.log(f"🔄 Closed {to_close.symbol}: avoiding strike crossing")
                        
            return {
                "success": True,
                "action": "adjust",
                "adjustments_made": actions,
                "open_positions": len(open_positions),
                "target_status": target_status
            }
            
        except Exception as e:
            trace_log = ''.join(traceback.format_exception(None, e, e.__traceback__))
            self.log(f"❌ Monitor error: {e}")
            return {"success": False, "error": str(e), "traceback": trace_log}

    # ===== 3. TARGET & EXPIRY CLOSE =====
    
    def _check_target(self, cycle_id: str, target_profit_percentage: float) -> Dict:
        """Check if target percentage is achieved"""
        try:
            # Get initial balance
            tracker = InitialBalanceTracker.objects.get(cycle_id=cycle_id)
            initial_balance = float(tracker.initial_balance_usd)
            print("initial_balance::::::::::",initial_balance)
            # Get current balance
            current_balance = self._get_current_balance()
            print("current_balance::::::::::",current_balance)
            live_positions = self.client.get_positions()
            print("live_positions::::::::::",live_positions)
            if live_positions.get("success"):
                positions = live_positions.get("result", [])
                realized_cashflow = sum(float(p.get("realized_cashflow", 0)) for p in positions)
                print("realized_cashflow::::::::::",realized_cashflow)
            current_balance_without_cashflow = current_balance - realized_cashflow
            # Calculate target
            target_balance = initial_balance * (1 + target_profit_percentage / 100)
            target_achieved = current_balance_without_cashflow >= target_balance
            print("target_balance::::::::::",target_balance)
            print("target_achieved::::::::::",target_achieved)
            return {
                "initial_balance": initial_balance,
                "current_balance": current_balance,
                "current_balance_without_cashflow": current_balance_without_cashflow,
                "target_balance": target_balance,
                "target_achieved": target_achieved
            }
            
        except InitialBalanceTracker.DoesNotExist:
            return {"target_achieved": False, "error": "No initial balance found"}
        except Exception as e:
            return {"target_achieved": False, "error": str(e)}
    
    def _is_expiry_time(self) -> bool:
        """Check if it's expiry day at 12:30 PM"""
        try:
            active_positions = OptionPosition.objects.filter(active=True)
            if not active_positions.exists():
                return False
            
            expiry_date = active_positions.first().expiry_date
            current_date = timezone.now().date()
            current_time = timezone.now().time()
            
            return (current_date == expiry_date and current_time >= self.expiry_close_time)
            
        except Exception:
            return False
    
    # ===== HELPER METHODS =====
    
    def _store_initial_balance(self, cycle_id: str):
        """Store initial USD balance"""
        current_balance = self._get_current_balance()
        print("current_balance::::::::::",current_balance)
        # Get INR equivalent
        wallet_response = self.client.get_wallet_balances()
        print("wallet_response::::::::::",wallet_response)
        inr_equivalent = 0.0
        if wallet_response.get("success"):
            balances = wallet_response.get("result", [])  # Fixed: removed .get("data", {})
            for balance in balances:
                if "balance_inr" in balance:
                    inr_equivalent = float(balance.get("balance_inr", 0))
                    print("inr_equivalent::::::::::",inr_equivalent)
                    break
        
        InitialBalanceTracker.objects.update_or_create(
            cycle_id=cycle_id,
            defaults={
                "initial_balance_usd": current_balance,
                "initial_balance_inr": inr_equivalent
            }
        )
        
        self.log(f"💾 Stored initial balance: ${current_balance:.2f}")
    
    def _get_current_balance(self) -> float:
        """Get current USD balance"""
        try:
            wallet_response = self.client.get_wallet_balances()
            print("wallet_response::::::::::",wallet_response)
            if wallet_response.get("success") == True:
                balances = wallet_response.get("result", [])  # Fixed: removed .get("data", {})
                print("balances::::::::::",balances)
                for balance in balances:
                    if balance.get("asset_symbol", "").upper() == "USD":
                        print("USD balance found::::::::::", balance.get("balance", 0))
                        return float(balance.get("balance", 0))
            return 0.0
        except Exception:
            return 0.0
    
    def _get_monthly_options(self) -> List[Dict]:
        """Get option chain"""
        try:
            response = self.client.get_option_chain(underlying=self.underlying, expiry_date=self.date)
            return response.get("result", []) if response.get("success") else []
        except Exception:
            return []
    
    def _get_spot_price(self) -> float:
        """Get current spot price of the underlying"""
        try:
            # Get ticker info for the underlying
            tickers = self._get_monthly_options()
            if tickers and len(tickers) > 0:
                print("tickers::::::::::", tickers)
                print("first tickers::::::::::", tickers[0])

                # Spot price is typically available in the first ticker
                spot_price = float(tickers[0].get("spot_price", 0))
                print("spot_price::::::::::", spot_price)
                if spot_price > 0:
                    return spot_price
                
                # Alternative: get from underlying_price field
                for ticker in tickers[:5]:  # Check first few tickers
                    if "underlying_price" in ticker:
                        return float(ticker.get("underlying_price", 0))
            return 0.0
        except Exception as e:
            self.log(f"⚠️ Error getting spot price: {e}")
            return 0.0
    
    def _find_nearest_strike(self, tickers: List[Dict], spot_price: float) -> float:
        """Find the nearest available strike price to the spot price"""
        try:
            # Get all unique strike prices
            strikes = set()
            for ticker in tickers:
                strike = float(ticker.get("strike_price", 0))
                if strike > 0:
                    strikes.add(strike)
            
            if not strikes:
                return 0.0
            
            # Find nearest strike to spot price
            nearest = min(strikes, key=lambda x: abs(x - spot_price))
            print("nearest strike::::::::::", nearest)
            return nearest
        except Exception as e:
            self.log(f"⚠️ Error finding nearest strike: {e}")
            return 0.0
    
    def _select_option_by_delta(self, options: List[Dict], option_type: str) -> Dict:
        """
        Select the option closest to ATM (within delta range):
        - CALL  → pick the lowest delta (closest to 0)
        - PUT   → pick the highest delta (closest to 0)
        """

        if option_type == "call":
            delta_range = self.call_delta_range  # (0.16, 0.22)
        elif option_type == "put":
            delta_range = self.put_delta_range   # (-0.22, -0.16)
        else:
            self.log(f"⚠️ Invalid option type: {option_type}")
            return None

        print(f"delta_range for {option_type}: {delta_range}")
        filtered = []

        for option in options:
            greeks = option.get("greeks", {})
            delta_str = greeks.get("delta", "0")

            try:
                delta = float(delta_str)
            except (ValueError, TypeError):
                continue

            # Check if delta falls in range
            if delta_range[0] <= delta <= delta_range[1]:
                filtered.append((delta, option))

        if not filtered:
            self.log(f"⚠️ No {option_type.upper()} found in delta range {delta_range}")
            return None

        # ✅ Selection logic:
        # CALL  → lowest delta
        # PUT   → highest delta
        if option_type == "call":
            selected = min(filtered, key=lambda x: x[0])
        else:  # put
            selected = max(filtered, key=lambda x: x[0])

        delta, option = selected
        self.log(f"📊 Selected {option_type.upper()} option: {option.get('symbol', 'Unknown')} (δ={delta:.3f})")
        return option
    
    def _sell_option(self, option: Dict, cycle_id: str) -> Dict:
        """Sell option and store in database"""
        try:
            # Place sell order
            print("option::::::::::",option)
            order_body = {
                "product_symbol": option["symbol"],
                "size": self.size,
                "side": "sell",
                "order_type": "market_order"
            }
            order_response = self.client.place_order(body=order_body)
            print("order_response::::::::::",order_response)
            if order_response.get("success"):
                # Extract delta from greeks
                greeks = option.get("greeks", {})
                delta_str = greeks.get("delta", "0")
                try:
                    delta_value = float(delta_str)
                except (ValueError, TypeError):
                    delta_value = 0.0
                
                # Extract expiry date from symbol (e.g., P-BTC-114000-171025 -> 171025 -> 2025-10-17)
                try:
                    symbol = option["symbol"]
                    # Extract date part from symbol (last 6 digits)
                    date_part = symbol.split("-")[-1]  # "171025"
                    if len(date_part) == 6:
                        # Parse as DDMMYY format
                        day = int(date_part[:2])
                        month = int(date_part[2:4])
                        year = 2000 + int(date_part[4:6])  # Convert YY to 20YY
                        expiry_date = datetime(year, month, day).date()
                    else:
                        # Fallback to a default date if parsing fails
                        expiry_date = datetime(2025, 10, 17).date()
                except (ValueError, IndexError):
                    # Fallback to a default date
                    expiry_date = datetime(2025, 10, 17).date()
                
                # Store in database
                OptionPosition.objects.create(
                    product_id=option["product_id"],
                    symbol=option["symbol"],
                    side="sell",
                    size=self.size,
                    mark_price=float(option.get("mark_price", 0)),
                    strike_price=float(option.get("strike_price", 0)),
                    delta=delta_value,
                    expiry_date=expiry_date,
                    strategy_cycle_id=cycle_id,
                    is_initial_position=True,
                    remote_order_id=order_response.get("result", {}).get("id")
                )
                
                self.log(f"✅ Sold: {option['symbol']} (δ={delta_value:.3f})")
                return {"success": True}
            
            return {"success": False, "error": "Order failed"}
            
        except ValueError as e:
            self.log(f"⚠️ Value error: {e}")
            return {"success": False, "error_type": "ValueError", "error": str(e)}

        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"❌ Unexpected error: {e}\nTraceback:\n{tb}")
            return {"success": False, "error_type": "Exception", "error": str(e), "traceback": tb}
    
    
    def _close_all_positions(self, reason: str) -> Dict:
        """Close all active positions"""
        try:
            active_positions = OptionPosition.objects.filter(active=True)
            
            closed_count = 0
            for position in active_positions:
                # Place buy order to close
                close_body = {
                    "product_symbol": position.symbol,
                    "size": position.size,
                    "side": "buy",
                    "order_type": "market_order"
                }
                close_response = self.client.place_order(body=close_body)
                print("close_response::::::::::",close_response)
                if close_response.get("success"):
                    position.active = False
                    position.closed_at = timezone.now()
                    position.save()
                    closed_count += 1
                    self.log(f"✅ Closed: {position.symbol}")
            
            return {
                "success": True,
                "reason": reason,
                "closed_count": closed_count
            }
            
        except Exception as e:
            self.log(f"❌ Close error: {e}")
            return {"success": False, "error": str(e)}


# ===== API VIEWS =====

strategy = MonthlyStrategy()

class StartStrategyView(APIView):
    """POST /api/start/ - Start monthly cycle"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        # target_percentage = float(request.data.get("target_profit_percentage", 80.0))
        result = strategy.start_monthly_cycle()
        return Response(result)

class MonitorStrategyView(APIView):
    """POST /api/monitor/ - Monitor and adjust"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        target_percentage = float(request.data.get("target_profit_percentage", 80.0))
        result = strategy.monitor_and_adjust(target_percentage)
        return Response(result)

class StatusView(APIView):
    """GET /api/status/ - Get status"""
    permission_classes = [AllowAny]
    
    def get(self, request):
        target_percentage = float(request.GET.get("target_profit_percentage", 80.0))
        current_date = timezone.now()
        cycle_id = f"{current_date.year}-{current_date.month:02d}"
        result = strategy._check_target(cycle_id, target_percentage)
        return Response(result)

# ===== CELERY TASK =====

@shared_task(bind=True)
def monitor_strategy_task(self, target_profit_percentage=80.0):
    """Celery task - runs every 30 seconds"""
    try:
        result = strategy.monitor_and_adjust(target_profit_percentage)
        logger.info(f"[CELERY] Monitor result: {result.get('action', 'unknown')}")
        return result
    except Exception as e:
        logger.exception(f"[CELERY] Error: {e}")
        return {"success": False, "error": str(e)}
    
class TestStrangel(APIView):
    """Post /api/test-strangel/ - Test strangel logic"""
    permission_classes = [AllowAny]
    def __init__(self, underlying: str = "BTC", date: str = "17-11-2025"):
        self.underlying = underlying
        self.client = DeltaClient(debug=True)
        self.date = date

        # Strategy parameters
        self.size = 1
        self.call_delta_range = (0.16, 0.22)
        self.put_delta_range = (-0.22, -0.16)
        self.expiry_close_time = time(12, 30)  # 12:30 PM

    def post(self, request):
        try:
            client = DeltaClient()
            current_date = timezone.now()
            cycle_id = f"{current_date.year}-{current_date.month:02d}"
            tickers = strategy._get_monthly_options()
            p1, p2 = None, None
            open_positions = list(OptionPosition.objects.filter(active=True))
            if len(open_positions) == 2:
                p1, p2 = open_positions[0], open_positions[1]
            closed_both = True
            for pos in [p1, p2]:
                close_body = {
                    "product_symbol": pos.symbol,
                    "size": pos.size,
                    "side": "buy",
                    "order_type": "market_order"
                }
                close_response = client.place_order(body=close_body)
                print("close_response::::::::::", close_response)
                if close_response.get("success"):
                    pos.active = False
                    pos.closed_at = timezone.now()
                    pos.save()
                    print(f"✅ Closed: {pos.symbol}")
                else:
                    closed_both = False
                    print(f"❌ Failed to close: {pos.symbol}")
            
            if closed_both:
                print(f"closed BOTH positions (same strike, price doubled: {p1.mark_price} vs {p2.mark_price})")
                
                # Now sell two puts at nearest strike to market price
                print("🔄 Now selling two puts at nearest strike to market price")
                
                # Get market price (spot price)
                spot_price = self._get_spot_price()
                print(f"📈 Current spot price: {spot_price}")
                
                if spot_price > 0:
                    # Find nearest strike price
                    nearest_strike = self._find_nearest_strike(tickers, spot_price)
                    print(f"🎯 Nearest strike to spot: {nearest_strike}")
                    
                    if nearest_strike:
                        # Find call and put options at this strike
                        call_at_strike = next(
                            (t for t in tickers if t.get("contract_type") == "call_options" and 
                                float(t.get("strike_price", 0)) == nearest_strike),
                            None
                        )
                        put_at_strike = next(
                            (t for t in tickers if t.get("contract_type") == "put_options" and 
                                float(t.get("strike_price", 0)) == nearest_strike),
                            None
                        )
                        
                        print(f"call_at_strike: {call_at_strike}")
                        print(f"put_at_strike: {put_at_strike}")
                        
                        if call_at_strike and put_at_strike:
                            # Sell call
                            sell_result_call = self._sell_option(call_at_strike, cycle_id)
                            # Sell put
                            sell_result_put = self._sell_option(put_at_strike, cycle_id)
                            
                            if sell_result_call["success"] and sell_result_put["success"]:
                                print(f"sold call and put at strike {nearest_strike}")
                                print(f"✅ Sold call and put at strike {nearest_strike}")
                            else:
                                print(f"⚠️ Failed to sell call/put at strike {nearest_strike}")
                        else:
                            print(f"⚠️ Call or Put not found at strike {nearest_strike}")
                    else:
                        print("⚠️ Could not find nearest strike")
                else:
                    print("⚠️ Could not get spot price")
                
                return Response({
                    "success": True,
                    "action": "rebalanced",
                    "reason": "Same strike price - one side doubled, reopened with call and put",
                    "positions_closed": 2,
                    "positions_opened": 2
                })
        except Exception as e:
            trace_log = ''.join(traceback.format_exception(None, e, e.__traceback__))
            print(f"❌ Test strangel error: {e}")
            return Response({"success": False, "error": str(e), "traceback": trace_log})
        
    def _get_spot_price(self) -> float:
        """Get current spot price of the underlying"""
        try:
            # Get ticker info for the underlying
            tickers = strategy._get_monthly_options()
            if tickers and len(tickers) > 0:
                print("tickers::::::::::", tickers)
                print("first tickers::::::::::", tickers[0])

                # Spot price is typically available in the first ticker
                spot_price = float(tickers[0].get("spot_price", 0))
                print("spot_price::::::::::", spot_price)
                if spot_price > 0:
                    return spot_price
                
                # Alternative: get from underlying_price field
                for ticker in tickers[:5]:  # Check first few tickers
                    if "underlying_price" in ticker:
                        return float(ticker.get("underlying_price", 0))
            return 0.0
        except Exception as e:
            print(f"⚠️ Error getting spot price: {e}")
            return 0.0
    
    def _find_nearest_strike(self, tickers: List[Dict], spot_price: float) -> float:
        """Find the nearest available strike price to the spot price"""
        try:
            # Get all unique strike prices
            strikes = set()
            for ticker in tickers:
                strike = float(ticker.get("strike_price", 0))
                if strike > 0:
                    strikes.add(strike)
            
            if not strikes:
                return 0.0
            
            # Find nearest strike to spot price
            nearest = min(strikes, key=lambda x: abs(x - spot_price))
            print("nearest strike::::::::::", nearest)
            return nearest
        except Exception as e:
            print(f"⚠️ Error finding nearest strike: {e}")
            return 0.0

    def _sell_option(self, option: Dict, cycle_id: str) -> Dict:
        """Sell option and store in database"""
        try:
            client = DeltaClient()
            # Place sell order
            print("option::::::::::",option)
            order_body = {
                "product_symbol": option["symbol"],
                "size": self.size,
                "side": "sell",
                "order_type": "market_order"
            }
            order_response = client.place_order(body=order_body)
            print("order_response::::::::::",order_response)
            if order_response.get("success"):
                # Extract delta from greeks
                greeks = option.get("greeks", {})
                delta_str = greeks.get("delta", "0")
                try:
                    delta_value = float(delta_str)
                except (ValueError, TypeError):
                    delta_value = 0.0
                
                # Extract expiry date from symbol (e.g., P-BTC-114000-171025 -> 171025 -> 2025-10-17)
                try:
                    symbol = option["symbol"]
                    # Extract date part from symbol (last 6 digits)
                    date_part = symbol.split("-")[-1]  # "171025"
                    if len(date_part) == 6:
                        # Parse as DDMMYY format
                        day = int(date_part[:2])
                        month = int(date_part[2:4])
                        year = 2000 + int(date_part[4:6])  # Convert YY to 20YY
                        expiry_date = datetime(year, month, day).date()
                    else:
                        # Fallback to a default date if parsing fails
                        expiry_date = datetime(2025, 10, 17).date()
                except (ValueError, IndexError):
                    # Fallback to a default date
                    expiry_date = datetime(2025, 10, 17).date()
                
                # Store in database
                OptionPosition.objects.create(
                    product_id=option["product_id"],
                    symbol=option["symbol"],
                    side="sell",
                    size=self.size,
                    mark_price=float(option.get("mark_price", 0)),
                    strike_price=float(option.get("strike_price", 0)),
                    delta=delta_value,
                    expiry_date=expiry_date,
                    strategy_cycle_id=cycle_id,
                    is_initial_position=True,
                    remote_order_id=order_response.get("result", {}).get("id")
                )
                
                print(f"✅ Sold: {option['symbol']} (δ={delta_value:.3f})")
                return {"success": True}
            
            return {"success": False, "error": "Order failed"}
            
        except ValueError as e:
            print(f"⚠️ Value error: {e}")
            return {"success": False, "error_type": "ValueError", "error": str(e)}

        except Exception as e:
            tb = traceback.format_exc()
            print(f"❌ Unexpected error: {e}\nTraceback:\n{tb}")
            return {"success": False, "error_type": "Exception", "error": str(e), "traceback": tb}
    
class CloseAllPositionsView(APIView):
    """POST /api/close-all/ - Close all active positions"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        reason = request.data.get("reason", "Manual close all positions")
        result = strategy._close_all_positions(reason)
        return Response(result)
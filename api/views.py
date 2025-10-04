from django.shortcuts import render
from api.delta_client import DeltaClient
from api.models import OptionPosition
from api.utils import find_last_expiry_for_month, parse_expiry, extract_expiry_from_symbol
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from datetime import date, datetime
from decimal import Decimal
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone


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
        last_expiry = find_last_expiry_for_month(tickers, ref)
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

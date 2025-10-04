from datetime import datetime
from decimal import Decimal

def parse_expiry(date_str):
    # expects expiry in response as DD-MM-YYYY or similar -- adapt if docs show other format
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date()
    except:
        # try ISO
        return datetime.fromisoformat(date_str).date()

def find_last_expiry_for_month(option_list, reference_date):
    # option_list is list of tickers (result from /tickers)
    # find all expiry dates in same month as reference_date and pick the last one
    exps = set()
    for t in option_list:
        if "expiry_date" in t and t["expiry_date"]:
            exps.add(t["expiry_date"])
    parsed = [parse_expiry(x) for x in exps]
    same_month = [d for d in parsed if d.year == reference_date.year and d.month == reference_date.month]
    if not same_month:
        return None
    return max(same_month)

def delta_in_range(greeks, low, high):
    # greeks["delta"] is string like "0.20" or "-0.18"
    try:
        d = float(greeks.get("delta", 0))
        return low <= d <= high
    except:
        return False

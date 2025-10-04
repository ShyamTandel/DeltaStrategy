from datetime import datetime
from decimal import Decimal
import re

def parse_expiry(date_str):
    # expects expiry in response as DD-MM-YYYY or similar -- adapt if docs show other format
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").date()
    except:
        # try ISO
        return datetime.fromisoformat(date_str).date()

def extract_expiry_from_symbol(symbol: str):
    """
    Extract expiry date (DDMMYY) from a Delta option symbol like:
    'C-BTC-90000-311025' -> datetime.date(2025, 10, 31)
    """
    # pattern: {C|P}-{underlying}-{strike}-{DDMMYY}
    match = re.search(r'-(\d{6})$', symbol)
    if not match:
        return None
    date_str = match.group(1)  # e.g. 311025
    try:
        return datetime.strptime(date_str, "%d%m%y").date()
    except ValueError:
        return None


def find_last_expiry_for_month(option_list, reference_date):
    """
    Find the latest expiry in the same month as reference_date
    by parsing the symbol string (since no expiry_date field).
    """
    expiries = []
    for t in option_list:
        symbol = t.get("symbol", "")
        exp_date = extract_expiry_from_symbol(symbol)
        if exp_date:
            expiries.append(exp_date)
    same_month = [d for d in expiries if d.year == reference_date.year and d.month == reference_date.month]
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

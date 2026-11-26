"""The $500 daily cap. Day P&L = account equity - last close equity (realized + open, carried positions included).
A new trade is sized so that even if every stop is hit, the day ends no worse than -$500:
    budget = 500 + day P&L - (loss still possible down to each open position's stop)
If day P&L reaches -$500 anyway (slippage, a gap through a stop), everything is closed and the day halts."""
from . import settings as S


def day_pnl(acct):
    return float(acct["equity"]) - float(acct["last_equity"])


def open_risk(positions, stops):
    """Loss still possible from here down to the stops. A position with no known stop counts in full."""
    total = 0.0
    for p in positions:
        qty = float(p["qty"])
        px = float(p["current_price"])
        stop = stops.get(p["symbol"])
        total += qty * max(0.0, px - stop) if stop is not None else qty * px
    return total


def budget(acct, positions, stops):
    return S.DAILY_MAX_LOSS + day_pnl(acct) - open_risk(positions, stops)


def breached(acct):
    return day_pnl(acct) <= -S.DAILY_MAX_LOSS

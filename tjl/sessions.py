"""NYSE trading days. Holidays and 1:00 PM early closes for 2026-2027 (check NYSE's page each December).

Trend Join takes no trades on early-close days (user decision 2026-11-26).
"""
import datetime as dt

HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
    "2027-09-06", "2027-11-25", "2027-12-24",
}
HALF_DAYS = {"2026-11-27", "2026-12-24", "2027-11-26"}
YEARS = {2026, 2027}   # years the two tables cover; anything else raises instead of guessing


def _d(x):
    d = x if isinstance(x, dt.date) else dt.date.fromisoformat(x)
    if d.year not in YEARS:
        raise ValueError(f"tjl/sessions.py has no NYSE holidays for {d.year}: add them (NYSE's holiday page)")
    return d


def is_trading_day(day):
    day = _d(day)
    return day.weekday() < 5 and day.isoformat() not in HOLIDAYS


def is_half_day(day):
    return _d(day).isoformat() in HALF_DAYS


def next_trading_day(day):
    day = _d(day) + dt.timedelta(days=1)
    while not is_trading_day(day):
        day += dt.timedelta(days=1)
    return day


def prev_trading_day(day):
    day = _d(day) - dt.timedelta(days=1)
    while not is_trading_day(day):
        day -= dt.timedelta(days=1)
    return day


def next_full_day(day):
    """Next trading day that is not an early close (the next day Trend Join can trade)."""
    day = next_trading_day(day)
    while is_half_day(day):
        day = next_trading_day(day)
    return day


def day_status(day):
    day = _d(day)
    if not is_trading_day(day):
        return "closed"
    return "half day (no Trend Join trades)" if is_half_day(day) else "full day"

"""Load Webull connector output (saved JSON) into plain dicts.

`get_stock_bars` returns {"result": [{"symbol", "result": [bars newest first]}]}; each bar has a UTC
`time` (bar start; daily bars are stamped 05:00 UTC = midnight ET), string prices and a trading_session.
`get_stock_snapshot` returns a list of quote dicts.
"""
import datetime as dt
import json
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _load(path):
    with open(path) as f:
        return json.load(f)


def parse_time(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f%z")


def _bar(b):
    t = parse_time(b["time"]).astimezone(ET)
    return {"t": t, "date": t.date(), "open": float(b["open"]), "high": float(b["high"]),
            "low": float(b["low"]), "close": float(b["close"]), "volume": float(b["volume"] or 0),
            "session": b.get("trading_session") or ""}


def load_bars(paths):
    """Bars by symbol, oldest first, from one or more saved `get_stock_bars` results."""
    if isinstance(paths, str):
        paths = [paths]
    out = {}
    for p in paths:
        d = _load(p)
        rows = d["result"] if isinstance(d, dict) else d
        for s in rows:
            bars = sorted((_bar(b) for b in s["result"]), key=lambda b: b["t"])
            seen = {b["t"]: b for b in out.get(s["symbol"], [])}
            seen.update({b["t"]: b for b in bars})
            out[s["symbol"]] = sorted(seen.values(), key=lambda b: b["t"])
    return out


def load_snapshot(paths):
    if isinstance(paths, str):
        paths = [paths]
    out = {}
    for p in paths:
        for r in _load(p):
            out[r["symbol"]] = r
    return out


def fnum(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def minutes_et(t):
    return t.hour * 60 + t.minute

"""Position sizing and Liquid price/size rounding."""
import math

from . import config as C


def size(entry, stop, risk, max_lev=C.LEV_MAX):
    """notional = risk / stop%; leverage = lowest of 2-10x that keeps margin <= $2,500.
    If even max leverage can't fit, notional is capped and the risk logged lower."""
    stop_pct = (entry - stop) / entry
    if stop_pct <= 0:
        raise ValueError("stop must be below entry")
    notional = risk / stop_pct
    lev = max(C.LEV_MIN, math.ceil(notional / C.MARGIN_CAP))
    capped = lev > max_lev
    if capped:
        lev = max_lev
        notional = C.MARGIN_CAP * max_lev
    return {"stop_pct": stop_pct, "notional": round(notional, 2), "leverage": lev,
            "margin": round(notional / lev, 2), "risk": round(notional * stop_pct, 2),
            "risk_target": risk, "capped": capped}


def hl_price(p, sz_decimals=2):
    """Hyperliquid perp price rule: at most 5 significant figures and 6 - szDecimals decimals."""
    if p <= 0:
        return p
    sig = round(p, -int(math.floor(math.log10(abs(p)))) + 4)
    return round(sig, max(0, 6 - sz_decimals))


def floor_qty(q, sz_decimals=2):
    f = 10 ** sz_decimals
    return math.floor(q * f) / f

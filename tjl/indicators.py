"""Plain-Python indicators on lists (oldest first)."""


def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def ema_series(xs, n):
    """EMA seeded with the SMA of the first n values; None before that."""
    out = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2 / (n + 1)
    e = sum(xs[:n]) / n
    out[n - 1] = e
    for i in range(n, len(xs)):
        e = xs[i] * k + e * (1 - k)
        out[i] = e
    return out


def adr(bars, n=20):
    """Average daily range: mean of (high / low - 1) over the last n bars."""
    if len(bars) < n:
        return None
    return sum(b["high"] / b["low"] - 1 for b in bars[-n:]) / n


def vwap_series(bars):
    """Cumulative VWAP (typical price) over the given bars (pass RTH bars of one session)."""
    pv = v = 0.0
    out = []
    for b in bars:
        tp = (b["high"] + b["low"] + b["close"]) / 3
        pv += tp * b["volume"]
        v += b["volume"]
        out.append(pv / v if v else tp)
    return out


def swing_lows(bars, left=2, right=2):
    """Indexes of confirmed swing lows (low strictly below `left` bars before and `right` bars after)."""
    out = []
    for i in range(left, len(bars) - right):
        lo = bars[i]["low"]
        if all(lo < bars[j]["low"] for j in range(i - left, i)) and \
           all(lo <= bars[j]["low"] for j in range(i + 1, i + right + 1)):
            out.append(i)
    return out


def swing_highs(bars, left=2, right=2):
    out = []
    for i in range(left, len(bars) - right):
        hi = bars[i]["high"]
        if all(hi > bars[j]["high"] for j in range(i - left, i)) and \
           all(hi >= bars[j]["high"] for j in range(i + 1, i + right + 1)):
            out.append(i)
    return out

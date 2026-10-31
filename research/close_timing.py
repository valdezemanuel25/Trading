#!/usr/bin/env python3
"""Live-timing check for the ES RSI(2) pullback: decide at 15:50 ET instead of at the 16:00 close.

The backtest reads RSI(2) and the 5-day SMA at the 16:00 close and fills at that close. Live, the decision has to be
made a few minutes earlier on the still-forming daily bar. Here every entry and exit decision uses the 15:50 price as
"today's close" (yesterday and earlier use real closes), and the fill is either the 16:00 close (market-on-close)
or the 15:50 price itself.

  python3 research/close_timing.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_1m  # noqa: E402
from daily import load_daily  # noqa: E402
from rsi2 import PERIODS, adjusted, backtest, stats  # noqa: E402

POINT, COST = 50.0, 30.0


def price_at(m1, hhmm):
    """Front-contract price at hh:mm ET each day (close of the last 1-minute bar before it)."""
    mins = m1.index.hour * 60 + m1.index.minute
    cut = hhmm // 100 * 60 + hhmm % 100
    x = m1[(mins >= 570) & (mins < cut)]
    return x.groupby(x.index.tz_localize(None).normalize())["close"].last()


def run(dd, early, rsi_max=10, fill="close"):
    front, closes = dd["front"], dd["closes"]
    a = adjusted(front, closes)
    off = a - front["close"]                      # roll adjustment per day
    e = (early.reindex(a.index) + off).to_numpy()  # 15:50 price on the adjusted scale
    A = a.to_numpy()
    days, n = a.index, len(a)
    alpha = 0.5                                     # Wilder smoothing for RSI(2)
    up = dn = 0.0
    up_s, dn_s = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        d = A[i] - A[i - 1]
        up = (1 - alpha) * up + alpha * max(d, 0)
        dn = (1 - alpha) * dn + alpha * max(-d, 0)
        up_s[i], dn_s[i] = up, dn

    def rsi_early(i):
        d = e[i] - A[i - 1]
        u = (1 - alpha) * up_s[i - 1] + alpha * max(d, 0)
        w = (1 - alpha) * dn_s[i - 1] + alpha * max(-d, 0)
        return 100.0 if w == 0 else 100 - 100 / (1 + u / w)

    def sma_early(i, k):
        return (A[i - k + 1:i].sum() + e[i]) / k

    trades, i = [], 200
    while i < n:
        if np.isnan(e[i]):
            i += 1
            continue
        if rsi_early(i) < rsi_max and e[i] > sma_early(i, 200):
            sym = front["symbol"].iloc[i]
            entry = closes[(days[i], sym)] if fill == "close" else early.loc[days[i]]
            j = i + 1
            while j < n and not (not np.isnan(e[j]) and e[j] > sma_early(j, 5)):
                j += 1
            j = min(j, n - 1)
            k = j
            while (days[k], sym) not in closes.index and k > i:
                k -= 1
            ex = closes[(days[k], sym)] if fill == "close" else early.get(days[k], closes[(days[k], sym)])
            trades.append(dict(entry_date=days[i], exit_date=days[k], pts=ex - entry, days=k - i))
            i = j + 1
        else:
            i += 1
    t = pd.DataFrame(trades)
    t["net"] = t["pts"] * POINT - COST
    return t


def main():
    dd = load_daily()
    early = price_at(load_1m(), 1550)
    for rmax in (10, 30):
        base = backtest(dd, rsi_max=rmax)
        live = run(dd, early, rmax, "close")
        live2 = run(dd, early, rmax, "early")
        same = len(set(base.entry_date) & set(live.entry_date))
        print(f"\nRSI(2) < {rmax}: entry days in common with the backtest: {same} of {len(base)} backtest / {len(live)} live")
        for name, t in (("backtest: decide + fill at 16:00", base), ("live: decide 15:50, fill 16:00 close", live),
                        ("live: decide + fill at 15:50", live2)):
            print(f"  {name:38s}", " | ".join(f"{p}: {stats(t, p)[:58]}" for p in PERIODS))


if __name__ == "__main__":
    main()

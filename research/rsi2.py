#!/usr/bin/env python3
"""Long-only RSI(2) pullback with a 200-day trend filter (Connors), ES daily, 2020-2026.

Rules (standard settings from the literature, not tuned here):
- Indicators on a roll-adjusted daily close series (difference back-adjustment at each roll).
- Buy at the 16:00 ET close when close > 200-day SMA and RSI(2) < 10.
- Sell at the 16:00 ET close of the first day the close is above the 5-day SMA.
- Each trade is priced in the contract it was entered in (no roll jumps). 1 ES, $30 per round trip.
Variants: B = no 200-day filter, C = RSI(2) < 5.

  python3 research/rsi2.py            # 2020-23 and 2024-25
  python3 research/rsi2.py --holdout  # also 2026
"""
import sys

import numpy as np
import pandas as pd

from daily import load_daily

POINT, COST = 50.0, 30.0
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "HOLDOUT 2026": ("2026-01-01", "2026-11-01")}


def adjusted(front, closes):
    """Back-adjusted close: at each roll day add (new - old) to all earlier closes."""
    c = front["close"].astype(float).copy()
    sym = front["symbol"]
    adj = pd.Series(0.0, index=c.index)
    for i in range(1, len(c)):
        if sym.iloc[i] != sym.iloc[i - 1]:
            d = c.index[i]
            old = closes.get((d, sym.iloc[i - 1]))
            if old is not None and not np.isnan(old):
                adj.iloc[:i] += c.iloc[i] - old
    return c + adj


def rsi(x, n=2):
    d = x.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def backtest(dd, rsi_max=10, use_trend=True):
    front, closes = dd["front"], dd["closes"]
    a = adjusted(front, closes)
    r, sma5, sma200 = rsi(a), a.rolling(5).mean(), a.rolling(200).mean()
    days = a.index
    trades, i = [], 200
    while i < len(days):
        if r.iloc[i] < rsi_max and (not use_trend or a.iloc[i] > sma200.iloc[i]):
            sym, entry_d = front["symbol"].iloc[i], days[i]
            entry = closes[(entry_d, sym)]
            j = i + 1
            while j < len(days) and not a.iloc[j] > sma5.iloc[j]:
                j += 1
            j = min(j, len(days) - 1)
            # value in the entry contract; if it stopped trading, use its last close
            k = j
            while (days[k], sym) not in closes.index and k > i:
                k -= 1
            ex = closes[(days[k], sym)]
            trades.append(dict(entry_date=entry_d, exit_date=days[k], symbol=sym, entry=entry, exit=ex,
                               days=k - i, pts=ex - entry))
            i = j + 1
        else:
            i += 1
    t = pd.DataFrame(trades)
    t["net"] = t["pts"] * POINT - COST
    return t


def stats(t, per):
    a, b = PERIODS[per]
    x = t[(t["entry_date"] >= pd.Timestamp(a)) & (t["entry_date"] < pd.Timestamp(b))]
    if x.empty:
        return "0 trades"
    eq = x["net"].cumsum()
    return (f"{len(x)} tr, win {100 * (x.pts > 0).mean():.0f}%, {x.pts.mean():+.1f} pts/tr, net ${x.net.sum():+,.0f}, "
            f"PF {x.loc[x.net > 0, 'net'].sum() / max(-x.loc[x.net < 0, 'net'].sum(), 1):.2f}, "
            f"maxDD ${(eq - eq.cummax()).min():,.0f}, avg hold {x.days.mean():.1f}d")


def main():
    dd = load_daily()
    pers = list(PERIODS) if "--holdout" in sys.argv else list(PERIODS)[:2]
    for name, kw in {"A  RSI2<10, above 200d (classic)": dict(), "B  RSI2<10, no trend filter": dict(use_trend=False),
                     "C  RSI2<5, above 200d": dict(rsi_max=5)}.items():
        t = backtest(dd, **kw)
        print(name)
        for per in pers:
            print(f"   {per}: {stats(t, per)}")


if __name__ == "__main__":
    main()

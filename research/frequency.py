#!/usr/bin/env python3
"""Higher-frequency long-only pullback variants (target 1-3 trades a week), ES 2020-2026.

All long only, only when the daily close (roll-adjusted) is above its 200-day SMA. 1 ES, $30 per round trip.
- RSI2<x : buy at the close when RSI(2) < x; sell at the close once close > 5-day SMA.
- IBS<0.2: buy at the close when (close - low) / (high - low) < 0.2; sell at the next close.
- Down day: buy at the close of any down day; sell at the next close (baseline).
- 1h RSI2 : on regular-session 1-hour bars, buy at the bar close when RSI(2) < 10 (daily filter from the previous day);
            sell at the close of the first 1-hour bar back above its 5-bar SMA, at the latest at 16:00 on the 5th day.

  python3 research/frequency.py            # 2020-23 and 2024-25
  python3 research/frequency.py --holdout  # also 2026
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
from daily import load_daily  # noqa: E402
from rsi2 import PERIODS, adjusted, backtest, rsi  # noqa: E402

POINT, COST = 50.0, 30.0


def next_close_trades(dd, signal):
    """Buy at today's close, sell at the next day's close, both in today's contract."""
    front, closes = dd["front"], dd["closes"]
    days = front.index
    out = []
    for i in np.flatnonzero(signal.to_numpy())[:-0 or None]:
        if i + 1 >= len(days):
            continue
        sym = front["symbol"].iloc[i]
        nxt = closes.get((days[i + 1], sym))
        if nxt is None or np.isnan(nxt):
            continue
        e = closes[(days[i], sym)]
        out.append(dict(entry_date=days[i], exit_date=days[i + 1], pts=nxt - e, days=1))
    t = pd.DataFrame(out)
    t["net"] = t["pts"] * POINT - COST
    return t


def hourly_rsi2(dd):
    from data import load_1m
    m1 = load_1m()
    mins = m1.index.hour * 60 + m1.index.minute
    rth = m1[(mins >= 570) & (mins < 960)]
    # RTH hourly bars 09:30-10:30, ..., 15:30-16:00 (labelled by start), same contract within a day
    h = rth["close"].resample("60min", offset="30min", label="left", closed="left").last().dropna()
    sym = rth["symbol"].resample("60min", offset="30min", label="left", closed="left").last().reindex(h.index)
    end_t = h.index + pd.Timedelta(minutes=60)
    end_t = end_t.where(end_t.hour * 60 + end_t.minute <= 960, end_t.normalize() + pd.Timedelta(hours=16))
    # the hourly RSI is computed per contract run so roll jumps don't create fake dips
    run_id = (sym != sym.shift()).cumsum()
    r = h.groupby(run_id).transform(lambda x: rsi(x))
    sma5 = h.groupby(run_id).transform(lambda x: x.rolling(5).mean())
    a = adjusted(dd["front"], dd["closes"])
    up = (a > a.rolling(200).mean()).shift(1)        # previous day's daily trend state
    day = pd.DatetimeIndex(h.index.tz_localize(None).normalize())
    trend = up.reindex(day).fillna(False).to_numpy(bool)
    hv, rv, sv, sy = h.to_numpy(), r.to_numpy(), sma5.to_numpy(), sym.to_numpy()
    out, i, n = [], 0, len(h)
    while i < n:
        if trend[i] and rv[i] < 10:
            j = i + 1
            limit = day[i] + pd.Timedelta(days=7)
            while j < n and sy[j] == sy[i] and not hv[j] > sv[j] and day[j] < limit:
                j += 1
            j = min(j, n - 1)
            if sy[j] != sy[i]:
                j -= 1
            out.append(dict(entry_date=day[i], exit_date=day[j], pts=hv[j] - hv[i], days=(day[j] - day[i]).days))
            i = j + 1
        else:
            i += 1
    t = pd.DataFrame(out)
    t["net"] = t["pts"] * POINT - COST
    return t


def stats(t, per):
    a, b = PERIODS[per]
    x = t[(t["entry_date"] >= pd.Timestamp(a)) & (t["entry_date"] < pd.Timestamp(b))]
    if x.empty:
        return "0 trades"
    weeks = (min(pd.Timestamp(b), pd.Timestamp("2026-10-29")) - max(pd.Timestamp(a), pd.Timestamp("2020-10-16"))).days / 7
    eq = x["net"].cumsum()
    return (f"{len(x) / weeks:.1f}/wk ({len(x)} tr), win {100 * (x.pts > 0).mean():.0f}%, {x.pts.mean():+.1f} pts/tr, "
            f"net ${x.net.sum():+,.0f}, PF {x.loc[x.net > 0, 'net'].sum() / max(-x.loc[x.net < 0, 'net'].sum(), 1):.2f}, "
            f"maxDD ${(eq - eq.cummax()).min():,.0f}")


def main():
    dd = load_daily()
    front = dd["front"]
    a = adjusted(front, dd["closes"])
    up = a > a.rolling(200).mean()
    rng = (front["high"] - front["low"]).replace(0, np.nan)
    ibs = (front["close"] - front["low"]) / rng
    down = a < a.shift(1)
    start = a.index >= a.index[200]
    variants = {
        "RSI2<10 (current A)": backtest(dd),
        "RSI2<30": backtest(dd, rsi_max=30),
        "RSI2<50": backtest(dd, rsi_max=50),
        "IBS<0.2, next close": next_close_trades(dd, up & (ibs < 0.2) & start),
        "Down day, next close": next_close_trades(dd, up & down & start),
        "Any day, next close": next_close_trades(dd, up & start),
        "1h RSI2<10": hourly_rsi2(dd),
    }
    pers = list(PERIODS) if "--holdout" in sys.argv else list(PERIODS)[:2]
    for name, t in variants.items():
        print(name)
        for per in pers:
            print(f"   {per}: {stats(t, per)}")


if __name__ == "__main__":
    main()

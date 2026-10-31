#!/usr/bin/env python3
"""Session-open failed-close strategy (rules from the user, 2026-10-31). ES 1-minute data, 2020-01 to 2026-10.

Rules:
- Session opens, each in its own local time (so daylight saving is handled): Asia = Tokyo 09:00,
  London = London 08:00, New York = New York 09:30. The open price is the first trade at that minute.
- Signal candle = the first 15-minute (or 5-minute) candle of the session.
  Long  if it trades below the open (at least 1 tick) and closes above it (failed to close below).
  Short if it trades above the open and closes below it (failed to close above). Otherwise no trade.
- Entry at the signal candle's close. Stop and target at the same distance (1:1): the distance to the day's VWAP
  (anchored at the 17:00 CT Globex open), clamped to 5-10 points; 7 points when VWAP is behind the trade.
- 1-hour filter: longs only if the last completed 1-hour close is above the previous day's low, shorts only if it is
  below the previous day's high.
- Close at the end of the session: Asia at the London open, London at the New York open, New York at 16:00 ET.
- Stop and target are checked on 1-minute bars after entry; if both are touched in the same minute it counts as
  a stop. 1 ES, $30 per round trip.

  python3 research/session_open.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
from data import bars_1h, bars_day, load_1m  # noqa: E402

NY = "America/New_York"
POINT, COST, TICK = 50.0, 30.0, 0.25
SESSIONS = {"Asia": ("Asia/Tokyo", 9, 0), "London": ("Europe/London", 8, 0), "New York": (NY, 9, 30)}
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "2026": ("2026-01-01", "2026-11-01")}


def session_open(tday, name):
    tz, hh, mm = SESSIONS[name]
    return pd.Timestamp(year=tday.year, month=tday.month, day=tday.day, hour=hh, minute=mm, tz=tz).tz_convert(NY)


def backtest(m1, candle_min, lo_pts=5.0, hi_pts=10.0, behind_pts=7.0, use_filter=True):
    idx = m1.index
    o, h, l, c, v = (m1[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    # daily VWAP from the 17:00 CT (18:00 ET) Globex open = start of the trading day
    tp = (h + l + c) / 3
    g = pd.DataFrame({"pv": tp * v, "v": v}).groupby(tday.to_numpy()).cumsum()
    vwap = (g["pv"] / g["v"].where(g["v"] > 0)).to_numpy()
    # 1-hour closes (bar labelled by start, so it is complete at start + 1h) and previous-day high/low
    h1 = bars_1h(m1)["close"]
    h1_done = pd.Series(h1.to_numpy(), index=h1.index + pd.Timedelta(hours=1))
    day = bars_day(m1)
    pdh, pdl = day["high"].shift(1), day["low"].shift(1)

    trades = []
    for td in pd.Index(tday.unique()):
        if td not in pdh.index or np.isnan(pdh.get(td, np.nan)):
            continue
        opens = {n: session_open(td, n) for n in SESSIONS}
        ends = {"Asia": opens["London"], "London": opens["New York"],
                "New York": pd.Timestamp(year=td.year, month=td.month, day=td.day, hour=16, tz=NY)}
        for name in SESSIONS:
            t0 = opens[name]
            i0 = idx.searchsorted(t0)
            if i0 >= len(idx) or idx[i0] != t0:
                continue                      # no trade printed at the open minute (holiday / halt)
            i1 = idx.searchsorted(t0 + pd.Timedelta(minutes=candle_min))   # first bar after the candle
            if i1 - i0 < 1:
                continue
            op = o[i0]
            hi, lo, cl = h[i0:i1].max(), l[i0:i1].min(), c[i1 - 1]
            if lo <= op - TICK and cl > op:
                side = 1
            elif hi >= op + TICK and cl < op:
                side = -1
            else:
                continue
            entry_t = t0 + pd.Timedelta(minutes=candle_min)
            last_h1 = h1_done[:entry_t]
            if use_filter and len(last_h1):
                hc = last_h1.iloc[-1]
                if side > 0 and not hc > pdl[td]:
                    continue
                if side < 0 and not hc < pdh[td]:
                    continue
            entry = cl
            dv = (vwap[i1 - 1] - entry) * side
            dist = behind_pts if not dv > 0 else min(max(dv, lo_pts), hi_pts)
            dist = np.round(dist / TICK) * TICK
            tgt, stp = entry + side * dist, entry - side * dist
            iend = idx.searchsorted(ends[name])
            res, px, ex_t = "Session end", None, None
            for j in range(i1, iend):
                hit_s = l[j] <= stp if side > 0 else h[j] >= stp
                hit_t = h[j] >= tgt if side > 0 else l[j] <= tgt
                if hit_s:
                    res, px, ex_t = "Stop", stp, idx[j]
                    break
                if hit_t:
                    res, px, ex_t = "Target", tgt, idx[j]
                    break
            if px is None:
                if iend - 1 < i1:
                    continue
                px, ex_t = c[iend - 1], idx[iend - 1]
            trades.append(dict(tday=td, session=name, side="L" if side > 0 else "S", entry_time=entry_t,
                               entry=entry, dist=dist, vwap_behind=not dv > 0, result=res, exit=px,
                               exit_time=ex_t, pts=(px - entry) * side))
    t = pd.DataFrame(trades)
    t["net"] = t["pts"] * POINT - COST
    return t


def summary(t):
    rows = []
    for (sess, per), _ in [((s, p), None) for s in ["All"] + list(SESSIONS) for p in PERIODS]:
        a, b = PERIODS[per]
        x = t[(t["tday"] >= pd.Timestamp(a)) & (t["tday"] < pd.Timestamp(b))]
        if sess != "All":
            x = x[x["session"] == sess]
        if x.empty:
            continue
        w = (x["result"] == "Target").sum()
        s = (x["result"] == "Stop").sum()
        daily = x.groupby("tday")["net"].sum()
        rows.append(dict(session=sess, period=per, trades=len(x), win=f"{100 * w / max(w + s, 1):.0f}%",
                         pts=round(x["pts"].mean(), 2), net=round(x["net"].sum()),
                         PF=round(x.loc[x.net > 0, "net"].sum() / max(-x.loc[x.net < 0, "net"].sum(), 1), 2),
                         sharpe=round(daily.mean() / daily.std() * np.sqrt(252), 2) if len(daily) > 2 else np.nan))
    return pd.DataFrame(rows)


def main():
    m1 = load_1m()
    pd.set_option("display.width", 200)
    for cm in (15, 5):
        t = backtest(m1, cm)
        print(f"\n=== First {cm}-minute candle ===  (win = target vs stop; pts = avg gross per trade; net $ after $30)")
        print(summary(t).to_string(index=False))
        print("results:", t["result"].value_counts().to_dict(), "| distance:", t["dist"].describe()[["mean", "50%"]].round(2).to_dict(),
              "| VWAP behind:", f"{100 * t['vwap_behind'].mean():.0f}%")
        t.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"session_open_{cm}m_trades.csv"), index=False)


if __name__ == "__main__":
    main()

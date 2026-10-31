#!/usr/bin/env python3
"""Long-only trend-pullback strategy with higher-timeframe filters, ES 2020-01 to 2026-10.

Rules:
- HTF filter (completed bars only): last 1h close > 1h SMA50 and last 4h close > 4h SMA21
  (optionally also > 4h SMA200).
- Entry on a 5m candle between 09:45 and 15:00 ET that trades down to a support level (low <= level),
  closes back above it and closes green. Support = VWAP, optionally also the previous day high
  or the 1h SMA50 (whichever the candle tagged).
- Entry at that candle's close. Stop 1 tick under the candle low (risk 2-10 pts, else skip). Target = R x risk.
- Exit at the target, the stop, or the 15:55 ET close. Stop/target checked on 1-minute bars; both in one minute = stop.
- One trade at a time, max 2 per day. 1 ES, $30 per round trip.

  python3 research/long_htf.py            # train + validation grid
  python3 research/long_htf.py --holdout  # also the 2026 holdout for the frozen config
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
from data import bars_1h, bars_4h, bars_5m, bars_day, load_1m  # noqa: E402

POINT, COST, TICK = 50.0, 30.0, 0.25
PERIODS = {"train 2020-23": ("2020-01-01", "2024-01-01"), "valid 2024-25": ("2024-01-01", "2026-01-01"),
           "HOLDOUT 2026": ("2026-01-01", "2026-11-01")}


def features(m1):
    b = bars_5m(m1)
    idx = b.index
    o, h, l, c, v = (b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    g = pd.DataFrame({"pv": (h + l + c) / 3 * v, "v": v}).groupby(tday.to_numpy()).cumsum()
    vwap = (g["pv"] / g["v"].where(g["v"] > 0)).to_numpy()

    def htf(hb, n):
        # value known at a 5m bar's close: SMA and close of HTF bars completed by then
        sma = hb["close"].rolling(n).mean()
        done_at = hb.index.to_series().shift(-1).fillna(hb.index[-1] + (hb.index[-1] - hb.index[-2]))
        f = pd.DataFrame({"sma": sma.to_numpy(), "close": hb["close"].to_numpy()}, index=pd.DatetimeIndex(done_at))
        f = f[~f.index.duplicated(keep="last")].sort_index()
        m = f.reindex(idx + pd.Timedelta(minutes=5), method="ffill")
        return m["sma"].to_numpy(), m["close"].to_numpy()

    h1, h4 = bars_1h(m1), bars_4h(m1)
    s1, c1 = htf(h1, 50)
    s21, c4 = htf(h4, 21)
    s200, _ = htf(h4, 200)
    day = bars_day(m1)
    pdh = day["high"].shift(1).reindex(tday).to_numpy()
    hm = idx.hour * 100 + idx.minute
    return dict(idx=idx, o=o, h=h, l=l, c=c, vwap=vwap, tday=tday, pdh=pdh, sma1h=s1, hm=hm,
                bull=(c1 > s1) & (c4 > s21), major=c4 > s200)


def backtest(m1, f, levels=("vwap",), r_mult=1.5, need_major=False, max_per_day=2, start=945, last_entry=1500):
    idx, o, h, l, c = f["idx"], f["o"], f["h"], f["l"], f["c"]
    m1h, m1l, m1c = m1["high"].to_numpy(float), m1["low"].to_numpy(float), m1["close"].to_numpy(float)
    m1i = m1.index
    lv = {"vwap": f["vwap"], "pdh": f["pdh"], "sma1h": f["sma1h"]}
    ok_ctx = f["bull"] & (f["major"] if need_major else True)
    in_win = (f["hm"] >= start) & (f["hm"] < last_entry)
    trades, busy_until, count = [], None, {}
    for i in np.flatnonzero(in_win & ok_ctx & (c > o)):
        t_close = idx[i] + pd.Timedelta(minutes=5)
        if busy_until is not None and t_close <= busy_until:
            continue
        td = f["tday"][i]
        if count.get(td, 0) >= max_per_day:
            continue
        tagged = [k for k in levels if not np.isnan(lv[k][i]) and l[i] <= lv[k][i] < c[i]]
        if not tagged:
            continue
        entry, stop = c[i], l[i] - TICK
        risk = entry - stop
        if risk < 2 or risk > 10:
            continue
        tgt = entry + r_mult * risk
        a = m1i.searchsorted(t_close)
        end = pd.Timestamp(year=idx[i].year, month=idx[i].month, day=idx[i].day, hour=15, minute=55, tz=idx.tz)
        b = m1i.searchsorted(end)
        res, px, ex = "Time", None, None
        for j in range(a, b):
            if m1l[j] <= stop:
                res, px, ex = "Stop", stop, m1i[j]
                break
            if m1h[j] >= tgt:
                res, px, ex = "Target", tgt, m1i[j]
                break
        if px is None:
            if b - 1 < a:
                continue
            px, ex = m1c[b - 1], m1i[b - 1]
        trades.append(dict(entry_time=t_close, tday=td, level="+".join(tagged), entry=entry, stop=stop, target=tgt,
                           risk=risk, result=res, exit=px, exit_time=ex, pts=px - entry))
        busy_until = ex
        count[td] = count.get(td, 0) + 1
    t = pd.DataFrame(trades)
    if not t.empty:
        t["net"] = t["pts"] * POINT - COST
    return t


def stats(t, per):
    a, b = PERIODS[per]
    x = t[(t["entry_time"] >= pd.Timestamp(a, tz="America/New_York")) & (t["entry_time"] < pd.Timestamp(b, tz="America/New_York"))]
    if x.empty:
        return dict(n=0)
    daily = x.groupby("tday")["net"].sum()
    w, s = (x.result == "Target").sum(), (x.result == "Stop").sum()
    eq = x["net"].cumsum()
    return dict(n=len(x), win=round(100 * w / max(w + s, 1)), pts=round(x.pts.mean(), 2), net=round(x.net.sum()),
                pf=round(x.loc[x.net > 0, "net"].sum() / max(-x.loc[x.net < 0, "net"].sum(), 1), 2),
                sharpe=round(daily.mean() / daily.std() * np.sqrt(252), 2) if len(daily) > 2 else np.nan,
                dd=round((eq - eq.cummax()).min()))


def fmt(s):
    return "0" if not s.get("n") else f"{s['n']}, {s['win']}%, {s['pts']:+.2f}, {s['net']:+,}, PF {s['pf']}, Sh {s['sharpe']}"


def main():
    m1 = load_1m()
    f = features(m1)
    holdout = "--holdout" in sys.argv
    rows = []
    for levels, r, major in itertools.product((("vwap",), ("vwap", "pdh"), ("vwap", "sma1h")), (1.0, 1.5, 2.0), (False, True)):
        t = backtest(m1, f, levels, r, major)
        tr, va = stats(t, "train 2020-23"), stats(t, "valid 2024-25")
        rows.append(dict(levels="+".join(levels), R=r, sma200=major, train=fmt(tr), valid=fmt(va),
                         train_sh=tr.get("sharpe"), valid_sh=va.get("sharpe")))
    g = pd.DataFrame(rows).sort_values("train_sh", ascending=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 80)
    print("Cells: trades, win% (target vs stop), avg gross pts, net $, profit factor, Sharpe. Sorted by TRAIN Sharpe.")
    print(g.drop(columns=["train_sh", "valid_sh"]).to_string(index=False))
    if holdout:
        best = g.iloc[0]
        lv = tuple(best["levels"].split("+"))
        t = backtest(m1, f, lv, best["R"], best["sma200"])
        print(f"\nFrozen config (best train Sharpe): levels={best['levels']} R={best['R']} sma200={best['sma200']}")
        for per in PERIODS:
            print(f"  {per}: {fmt(stats(t, per))}, maxDD {stats(t, per).get('dd')}")


if __name__ == "__main__":
    main()

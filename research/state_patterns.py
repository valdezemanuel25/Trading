#!/usr/bin/env python3
"""Patterns suggested by the 2026-11-25 state (all five markets well below their 200-day SMA), not covered by the
live rules. Research only (2026-11-26).

Engine, data and costs as research/strategies2.py: total-return daily series from data/daily (00:00 UTC closes),
$5,000 per trade, 0.10% round trip, long only. Portfolio: 2 slots shared with the live rules (RSI(2) on the five,
trend reclaim with a 20-day cap on CL/GOOGL/NQ/NVDA), one position per market, live rules first on a tie.

Candidates (the variant and the markets are picked on 2020-23 only, then checked on the 2026 holdout):
  BO20   20-day breakout: close above the highest of the previous 20 closes; exit on a close below the lowest of
         the previous 10 closes, or after 20 days. Filter: none / above the 200-day SMA.
  DOWNn  n consecutive lower closes (n = 3, 4); exit on the first close above the 5-day SMA.
         Filter: below the 200-day SMA (bear rebound) / none.
  BB2    close at least 2 standard deviations below the 20-day mean; exit on the first close above the 5-day SMA.
         Filter: below the 200-day SMA / none.
  RALLY  bear-market rally: close below the 200-day SMA crosses above the 20-day SMA; exit on a close back below
         the 20-day SMA, or after 20 days.
  DEEP   deep dip: RSI(2) < 10 with the close at least X% below the 200-day SMA (X = 10, 15, 20); exit on the first
         close above the 5-day SMA.

  python3 research/state_patterns.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backtest"))
import strategies2 as s2  # noqa: E402

LIVE5 = ["ES", "NQ", "NVDA", "GOOGL", "CL"]
TR4 = ["CL", "GOOGL", "NQ", "NVDA"]
PRIO = {"RSI2": 0, "TR": 1}


def trade(strat, m, s, i, j):
    c = s["close"].to_numpy()
    return dict(strat=strat, market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                ret=c[j] / c[i] - 1, alt=[s.index[i]])


def run_rule(m, s, entry, exit_, strat, max_days=None, start=201):
    out, i, n = [], start, len(s)
    while i < n:
        if entry(i):
            j = i + 1
            while j < n and not exit_(i, j) and not (max_days and j - i >= max_days):
                j += 1
            j = min(j, n - 1)
            out.append(trade(strat, m, s, i, j))
            i = j + 1
        else:
            i += 1
    return out


def candidates(m, s):
    c = s["close"].to_numpy()
    sma200, sma5, r2 = s["sma200"].to_numpy(), s["sma5"].to_numpy(), s["rsi2"].to_numpy()
    cs = pd.Series(c, index=s.index)
    hi20 = cs.shift(1).rolling(20).max().to_numpy()
    lo10 = cs.shift(1).rolling(10).min().to_numpy()
    sma20 = cs.rolling(20).mean().to_numpy()
    sd20 = cs.rolling(20).std(ddof=0).to_numpy()
    down = np.zeros(len(c), int)
    for i in range(1, len(c)):
        down[i] = down[i - 1] + 1 if c[i] < c[i - 1] else 0
    above = c > sma200
    exit5 = lambda i, j: c[j] > sma5[j]  # noqa: E731
    out = {}
    for f in ("none", "above200"):
        ok = (lambda i: True) if f == "none" else (lambda i: above[i])
        out[f"BO20 {f}"] = run_rule(m, s, lambda i, ok=ok: c[i] > hi20[i] and ok(i),
                                    lambda i, j: c[j] < lo10[j], f"BO20 {f}", max_days=20)
    for n in (3, 4):
        for f in ("below200", "none"):
            ok = (lambda i: not above[i]) if f == "below200" else (lambda i: True)
            out[f"DOWN{n} {f}"] = run_rule(m, s, lambda i, n=n, ok=ok: down[i] >= n and ok(i), exit5, f"DOWN{n} {f}")
    for f in ("below200", "none"):
        ok = (lambda i: not above[i]) if f == "below200" else (lambda i: True)
        out[f"BB2 {f}"] = run_rule(m, s, lambda i, ok=ok: sd20[i] > 0 and (c[i] - sma20[i]) / sd20[i] <= -2 and ok(i),
                                   exit5, f"BB2 {f}")
    out["RALLY"] = run_rule(m, s, lambda i: not above[i] and c[i] > sma20[i] and c[i - 1] <= sma20[i - 1],
                            lambda i, j: c[j] < sma20[j], "RALLY", max_days=20)
    for x in (10, 15, 20):
        out[f"DEEP {x}%"] = run_rule(m, s, lambda i, x=x: r2[i] < 10 and c[i] <= sma200[i] * (1 - x / 100),
                                     exit5, f"DEEP {x}%")
    return out


def allocate(trades, slots=2):
    t = trades.copy()
    t["_p"] = t["strat"].map(lambda v: PRIO.get(v, 2))
    t = t.sort_values(["entry_date", "_p", "market"]).reset_index(drop=True)
    open_, out = [], []
    for r in t.to_dict("records"):
        open_ = [x for x in open_ if x["exit_date"] > r["entry_date"]]
        if len(open_) >= slots or any(x["market"] == r["market"] for x in open_):
            continue
        open_.append(r)
        out.append(r)
    return pd.DataFrame(out)


def busy_days(pf):
    days = set()
    for t in pf.itertuples():
        days.update(pd.bdate_range(t.entry_date, t.exit_date - pd.Timedelta(days=1)))
    return days


def line(st):
    return s2.fmt(st)


def main():
    pd.set_option("display.width", 220)
    s2.SER = s2.load_all(s2.LIVE)
    S = s2.SER
    live = s2.frame([x for m in LIVE5 for x in s2.rsi2_rule(m, S[m])] +
                    [dict(x, strat="TR") for m in TR4 for x in s2.trend_reclaim(m, S[m], 20)])
    base = allocate(live)
    busy = busy_days(base)
    print("LIVE PORTFOLIO (RSI2 + TR20, 2 slots, one per market)")
    for p in s2.PERIODS:
        print(f"  {p:13s} {line(s2.stats(s2.per(base, p), s2.years(p)))}")

    raw = {}
    for m in LIVE5:
        for k, v in candidates(m, S[m]).items():
            raw.setdefault(k, []).extend(v)
    rows = []
    for k, v in raw.items():
        t = s2.frame(v)
        picked = [m for m in LIVE5 if s2.per(t[t.market == m], "2020-23").usd.sum() > 0]
        tp = t[t.market.isin(picked)]
        pf = allocate(pd.concat([live, tp], ignore_index=True)) if len(tp) else base
        new = pf[~pf.strat.isin(["RSI2", "TR"])]
        x = tp[tp.entry_date >= "2020-01-01"]
        aside = int(sum(d not in busy for d in x.entry_date))
        rows.append(dict(cand=k, picked=picked, t=t, tp=tp, pf=pf, new=new, aside=aside, n=len(x)))

    print("\n=== each candidate on its own (all five markets), per period ===")
    for r in rows:
        print(f"\n{r['cand']}")
        for p in s2.PERIODS:
            print(f"   all five   {p:13s} {line(s2.stats(s2.per(r['t'], p), s2.years(p)))}")
        print(f"   picked on 2020-23 (net > 0): {r['picked']}")
        for p in s2.PERIODS:
            print(f"   picked     {p:13s} {line(s2.stats(s2.per(r['tp'], p), s2.years(p)))}")
        print(f"   picked entries while the live rules hold nothing: {r['aside']} of {r['n']}")
        for p in s2.PERIODS:
            a, b = s2.stats(s2.per(base, p), s2.years(p)), s2.stats(s2.per(r["pf"], p), s2.years(p))
            nn = len(s2.per(r["new"], p))
            print(f"   portfolio  {p:13s} live ${a['net']:+7,.0f} DD ${a['dd']:+6,.0f} -> with it ${b['net']:+7,.0f} "
                  f"DD ${b['dd']:+6,.0f} worst ${b['worst']:+5,.0f} ({nn} of its trades taken)")

    print("\n=== summary: portfolio net vs live (2020-23 / 2024-25 / holdout) ===")
    for r in rows:
        d = [s2.per(r["pf"], p).usd.sum() - s2.per(base, p).usd.sum() for p in s2.PERIODS]
        print(f"  {r['cand']:16s} {str(r['picked']):38s} " + " / ".join(f"{x:+7,.0f}" for x in d))


if __name__ == "__main__":
    main()

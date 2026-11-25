#!/usr/bin/env python3
"""Intraday rule search round 2 (plan in docs/backtest-log.md, "intraday rule search round 2").

  python3 research/intraday_ideas.py                 # 2020-23 and 2024-25 only
  python3 research/intraday_ideas.py --holdout A B   # also the 2026 holdout, for the named final candidates

Ideas (8 settings in all): A stock gap-and-go, B strong opening drive, C midday flush in an uptrend (long),
D CL after the EIA report. 30-minute wakes; a market order fills at the 1-minute close 5 minutes after the decision;
resting stops (Liquid TP/SL, approved with the entry) fill at the level or the bar's open if it gaps through;
everything is closed at the 15:45 wake (fill 15:50). Uses the per-day arrays of research/intraday_agent.py.
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backtest"))
import intraday_agent as ia  # noqa: E402
import strategies2 as s2  # noqa: E402

ALL = ["ES", "NQ", "CL", "NVDA", "GOOGL"]
O, H, L, C = 0, 1, 2, 3
S0 = ia.S0
COST_CMP = {"ES": ("pts", 0.6), "NQ": ("pts", 0.75), "CL": ("pts", 0.025), "NVDA": ("pct", 0.0002),
            "GOOGL": ("pct", 0.0002)}
TRAIN_SE = 2.7
DATA = {}


def px(a, t):
    return a[t - 1 - S0, C]


def market_days(m):
    if m in DATA:
        return DATA[m]
    ds = ia.days(m)
    s = s2.load_all([m])[m]
    atrp = (s["atr"] / s["close"]).rename("atrp")
    rows = []
    prev = None
    hist = []                                            # past |r30|
    for d in ds:
        a = d["a"]
        f = atrp[atrp.index < d["date"]]
        day = dict(m=m, date=d["date"], a=a, up200=d["up200"], atrp=f.iloc[-1] if len(f) else np.nan,
                   open=a[0, O], prev_close=prev[3] if prev is not None and (d["date"] - prev[0]).days <= 4 else np.nan)
        r30 = px(a, 600) / a[0, O] - 1
        day["r30"], day["r30_mean"] = r30, (np.mean(hist[-20:]) if len(hist) >= 20 else np.nan)
        hist.append(abs(r30))
        rows.append(day)
        prev = (d["date"], None, None, a[-1, C])
    DATA[m] = rows
    return rows


def range30(a):
    return a[0:30, H].max(), a[0:30, L].min()


def idea_A(day, g):
    if day["m"] not in ("NVDA", "GOOGL"):
        return []
    a, pc = day["a"], day["prev_close"]
    if not np.isfinite(pc):
        return []
    gap = day["open"] / pc - 1
    if abs(gap) < g or abs(gap) > 0.25:                  # > 25% = split day
        return []
    side = 1 if gap > 0 else -1
    if (px(a, 600) - day["open"]) * side <= 0:
        return []
    hi, lo = range30(a)
    return [entry(day, 600, side, lo if side > 0 else hi)]


def idea_B(day, k):
    if not np.isfinite(day["r30_mean"]) or abs(day["r30"]) < k * day["r30_mean"]:
        return []
    side = 1 if day["r30"] > 0 else -1
    hi, lo = range30(day["a"])
    return [entry(day, 600, side, lo if side > 0 else hi)]


def idea_C(day, k):
    if not day["up200"] or not np.isfinite(day["atrp"]):
        return []
    a, w = day["a"], 13 * 60
    if px(a, w) > day["open"] * (1 - k * day["atrp"]):
        return []
    e = px(a, w + 5)
    return [entry(day, w, 1, e * (1 - day["atrp"]))]


def idea_D(day, x):
    if day["m"] != "CL" or day["date"].weekday() != 2:
        return []
    a = day["a"]
    p0, p1 = px(a, 630), px(a, 660)
    r = p1 / p0 - 1
    if abs(r) < x:
        return []
    side = 1 if r > 0 else -1
    return [entry(day, 660, side, p0)]


def entry(day, w, side, stop):
    a = day["a"]
    t = w + 5
    e = px(a, t)
    risk = (e - stop) * side
    return dict(wake=w, side=side, entry=e, risk=risk,
                go=lambda: ia.run(a, {}, side, t, e, stop=stop) if risk > 0 else (e, "none"))


IDEAS = {"A": (idea_A, "g", [0.01, 0.02], ["NVDA", "GOOGL"]),
         "B": (idea_B, "k", [1.5, 2.0], ALL),
         "C": (idea_C, "k", [0.75, 1.0], ALL),
         "D": (idea_D, "x", [0.002, 0.004], ["CL"])}


def simulate(fn, kw, markets):
    by_date = {}
    for m in markets:
        for day in market_days(m):
            by_date.setdefault(day["date"], []).append(day)
    rows = []
    for d in sorted(by_date):
        cands = []
        for day in by_date[d]:
            for s in fn(day, **kw):
                cands.append((s["wake"], ALL.index(day["m"]), day["m"], s))
        cands.sort(key=lambda x: (x[0], x[1]))
        n, real = 0, 0.0
        for _, _, m, s in cands:
            if n >= 2 or real <= -100 or s["risk"] <= 0:
                continue
            xp, why = s["go"]()
            notional = min(ia.RISK / (s["risk"] / s["entry"]), ia.CAP)
            qty = notional / s["entry"]
            gross = (xp - s["entry"]) * s["side"] * qty
            kind, c = COST_CMP[m]
            cmp_cost = c * qty if kind == "pts" else c * notional
            n += 1
            real += gross - ia.LIQ_COST * notional
            rows.append(dict(date=d, market=m, side=s["side"], why=why, notional=notional,
                             move=(xp / s["entry"] - 1) * s["side"], liq=gross - ia.LIQ_COST * notional,
                             cmp=gross - cmp_cost))
    return pd.DataFrame(rows)


def per(t, p, col="liq"):
    a, b = ia.PERIODS[p]
    x = t[(t["date"] >= a) & (t["date"] < b)] if len(t) else t
    return x, (x[col] if len(x) else pd.Series(dtype=float))


def st(x):
    n = len(x)
    se = x.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return dict(n=n, win=(x > 0).mean() * 100 if n else 0, avg=x.mean() if n else 0, se=se, tot=x.sum(),
                t=(x.mean() / se) if n > 1 and se > 0 else 0)


def fmt(s):
    return "0 trades" if not s["n"] else (f"{s['n']}, {s['win']:.0f}%, {s['avg']:+.1f} ({s['se']:.1f}), "
                                          f"t {s['t']:+.1f}, ${s['tot']:+,.0f}")


def concentration(x):
    """Total without the best market, and without the best calendar month."""
    if not len(x):
        return 0, 0
    bm = x.groupby("market")["liq"].sum()
    mo = x.groupby(x["date"].dt.to_period("M"))["liq"].sum()
    return x["liq"].sum() - bm.max(), x["liq"].sum() - mo.max()


def main():
    holdout = set(sys.argv[sys.argv.index("--holdout") + 1:]) if "--holdout" in sys.argv else set()
    for m in ALL:
        ds = market_days(m)
        print(f"{m}: {len(ds)} days {ds[0]['date'].date()} -> {ds[-1]['date'].date()}")
    print("\nCells: trades, win %, avg $ (se), t, total $. $50 risk. Liquid 0.10% unless noted.\n")
    tried = 0
    for name, (fn, key, vals, markets) in IDEAS.items():
        print(f"## Idea {name}")
        best = None
        for v in vals:
            tried += 1
            t = simulate(fn, {key: v}, markets)
            s = st(per(t, "2020-23")[1])
            print(f"  {key}={v}: 2020-23 {fmt(s)}")
            if best is None or s["avg"] > best[2]["avg"]:
                best = (v, t, s)
        v, t, s = best
        x24, y24 = per(t, "2024-25")
        s24 = st(y24)
        print(f"  picked {key}={v}")
        print(f"    2020-23 {fmt(s)}  [needs t >= {TRAIN_SE}: {'yes' if s['t'] >= TRAIN_SE else 'NO'}]")
        print(f"    2024-25 {fmt(s24)}  [positive: {'yes' if s24['tot'] > 0 else 'NO'}]")
        x20 = per(t, "2020-23")[0]
        print(f"    compare cost: 2020-23 {fmt(st(per(t, '2020-23', 'cmp')[1]))} | 2024-25 {fmt(st(per(t, '2024-25', 'cmp')[1]))}")
        for m in markets:
            tm = t[t["market"] == m] if len(t) else t
            print(f"    {m:6s} 2020-23 {fmt(st(per(tm, '2020-23')[1]))} | 2024-25 {fmt(st(per(tm, '2024-25')[1]))}")
        if len(x20):
            print(f"    median |move| {t['move'].abs().median()*100:.2f}%, mean notional ${t['notional'].mean():,.0f}, "
                  f"exits {t['why'].value_counts().to_dict()}; 2020-23 without best market / month: "
                  f"${concentration(x20)[0]:+,.0f} / ${concentration(x20)[1]:+,.0f}")
        if name in holdout:
            xh, yh = per(t, "2026")
            sh = st(yh)
            nm, nmo = concentration(xh)
            ok = (s["tot"] > 0 and s24["tot"] > 0 and sh["tot"] > 0 and sh["n"] >= 30 and sh["avg"] > sh["se"]
                  and s["t"] >= TRAIN_SE and nm > 0 and nmo > 0)
            print(f"    HOLDOUT 2026 {fmt(sh)}; compare cost {fmt(st(per(t, '2026', 'cmp')[1]))}; "
                  f"without best market / month ${nm:+,.0f} / ${nmo:+,.0f} -> {'PASS' if ok else 'fail'}")
        print()
    print(f"Settings tried: {tried}")


if __name__ == "__main__":
    main()

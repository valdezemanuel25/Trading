#!/usr/bin/env python3
"""Out-of-sample check of real CVD on variant E (10:30-11:00 ET, T1 cap 10, breakeven at +4).

  python3 backtest/cvd_oos.py

Uses the 10:00-11:05 ET trades slices (data/trades_1m/es_trades_1m_win1000-1105_*), fetched with
  python3 backtest/fetch_trades.py --start 2025-08-08 --end 2026-04-01 --window 1000-1105 --budget 20
No settings are re-tuned: these are the rules found on 2026-04 to 2026-10 (docs/backtest-log.md).

First it checks that cutting real delta down to 10:00-11:05 leaves E unchanged on 2026-04 to 2026-10, where the
full-day data exists. E's CVD rules only look a few candles back, so it should.
1 ES, $30 per round trip.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy  # noqa: E402
from data import load_1m  # noqa: E402
from strategy import compute, run, with_params  # noqa: E402

TZ = "America/New_York"
COST, POINT = 30.0, 50.0
E = dict(win_start=1030, win_end=1100, t1_cap=10, be_trigger=4)
OOS = ("2025-08-08", "2026-04-01")
IS = ("2026-04-02", "2026-10-29")
CONFIGS = {"clv5 (current)": dict(delta_source="clv5"), "real": dict(delta_source="real"),
           "real + flip": dict(delta_source="real", use_cvd_flip=True)}


def between(t, a, b):
    return t[(t["entry_time"] >= pd.Timestamp(a, tz=TZ)) & (t["entry_time"] < pd.Timestamp(b, tz=TZ))]


def stats(t):
    if t.empty:
        return dict(n=0)
    wins, stops = (t["result"] == "T1").sum(), (t["result"] == "Stop").sum()
    return dict(n=len(t), pts=round(t["pts"].mean(), 2), se=round(t["pts"].std() / np.sqrt(len(t)), 2),
                net=round((t["pts"] * POINT - COST).sum()), win=round(100 * wins / max(wins + stops, 1), 1))


def trades(m1, **kw):
    p = with_params(**E, **kw)
    return run(m1, p, compute(m1, p))


def main():
    m1 = load_1m()

    # 1) window-only delta == full delta for E on the in-sample period
    full = between(trades(m1, delta_source="real"), *IS)
    orig = strategy.real_delta

    def windowed(m):
        d = orig(m)
        hm = d.index.hour * 100 + d.index.minute
        return d.where((hm >= 1000) & (hm < 1105))

    strategy.real_delta = windowed
    cut = between(trades(m1, delta_source="real"), *IS)
    strategy.real_delta = orig
    same = len(full) == len(cut) and (full["entry_time"].values == cut["entry_time"].values).all()
    print(f"In-sample E with real CVD: full-day {len(full)} trades, 10:00-11:05 only {len(cut)} trades, "
          f"identical={same}")

    # 2) out of sample
    rows, sets = [], {}
    for name, kw in CONFIGS.items():
        t = between(trades(m1, **kw), *OOS)
        sets[name] = t
        g = t[~t["setup"].str.startswith("Fail BO")]
        rows.append(dict(config=name, **stats(t), gated=stats(g)))
    print(f"\nOut of sample {OOS[0]} -> {OOS[1]}, variant E (avg gross pts per trade, se, net $):")
    print(pd.DataFrame(rows).to_string(index=False))

    a, b = sets["clv5 (current)"], sets["real"]
    ka, kb = set(a["entry_time"]), set(b["entry_time"])
    oa, ob = a[~a["entry_time"].isin(kb)], b[~b["entry_time"].isin(ka)]
    print(f"\nclv5 vs real: {len(ka & kb)} shared trades; only clv5 {len(oa)} (avg {oa['pts'].mean():+.2f}), "
          f"only real {len(ob)} (avg {ob['pts'].mean():+.2f})")
    print("\nBy setup, real:")
    print(b.groupby("setup")["pts"].agg(["count", "mean"]).round(2).T.to_string())
    print("\nBy month, net $ (clv5 / real):")
    by = pd.DataFrame({k: (t["pts"] * POINT - COST).groupby(t["entry_time"].dt.strftime("%Y-%m")).sum()
                       for k, t in (("clv5", a), ("real", b))}).fillna(0).round()
    print(by.T.to_string())


if __name__ == "__main__":
    main()

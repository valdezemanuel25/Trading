#!/usr/bin/env python3
"""Real CVD (Databento trades) vs candle-estimated CVD on the Journal Triggers strategy.

  python3 backtest/cvd_compare.py

Runs the baseline (A) and the best variant (E) from docs/backtest-log.md with:
  CVD source clv5 vs real, the CVD divergence gate, and the journal's real-order-flow confirmations
  (CVD flip, absorption), on the dates the trades files cover.
Splits that range into a tune period (first 4 months) and a check period (the rest).
A small grid of the flip/absorption settings is scored on the tune period only.
1 ES, $30 per round trip.
"""
import itertools
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_1m  # noqa: E402
from strategy import compute, run, with_params  # noqa: E402

TZ = "America/New_York"
COST, POINT = 30.0, 50.0
# trades files start 2026-04-01 00:00 UTC; the 04-01 session began 03-31 18:00 ET, so start on 04-02
TUNE = ("2026-04-02", "2026-08-01")
CHECK = ("2026-08-01", "2026-10-29")
BASES = {"A": {}, "E": dict(win_start=1030, win_end=1100, t1_cap=10, be_trigger=4)}


def cell(t, a, b):
    t = t[(t["entry_time"] >= pd.Timestamp(a, tz=TZ)) & (t["entry_time"] < pd.Timestamp(b, tz=TZ))]
    if t.empty:
        return dict(n=0, pts=0.0, net=0.0, win=0.0)
    wins, stops = (t["result"] == "T1").sum(), (t["result"] == "Stop").sum()
    return dict(n=len(t), pts=round(t["pts"].mean(), 2), net=round((t["pts"] * POINT - COST).sum()),
                win=round(100 * wins / max(wins + stops, 1), 1))


def fmt(c):
    return f"{c['n']}, {c['pts']:+.2f}, {c['net']:+,.0f}"


def evaluate(m1, base, **kw):
    p = with_params(**BASES[base], **kw)
    t = run(m1, p, compute(m1, p))
    return cell(t, *TUNE), cell(t, *CHECK), t


def main():
    m1 = load_1m()
    rows = []
    configs = {
        "clv5": dict(delta_source="clv5"),
        "real": dict(delta_source="real"),
        "clv5 + div": dict(delta_source="clv5", use_cvd_div=True),
        "real + div": dict(delta_source="real", use_cvd_div=True),
        "real + flip": dict(delta_source="real", use_cvd_flip=True),
        "real + absorption": dict(delta_source="real", use_absorption=True),
        "real + flip + absorption": dict(delta_source="real", use_cvd_flip=True, use_absorption=True),
    }
    for base in BASES:
        for name, kw in configs.items():
            tu, ch, _ = evaluate(m1, base, **kw)
            rows.append(dict(base=base, config=name, tune=fmt(tu), check=fmt(ch), tune_pts=tu["pts"], check_pts=ch["pts"],
                             tune_win=tu["win"], check_win=ch["win"]))
            print(rows[-1], flush=True)
    print("\nFixed configs (cells: trades, avg gross pts, net $):")
    print(pd.DataFrame(rows).to_string(index=False))

    # small grid on the tune period only
    grid = []
    for base in BASES:
        for fw in (1, 2, 3):
            tu, ch, _ = evaluate(m1, base, delta_source="real", use_cvd_flip=True, flip_within=fw)
            grid.append(dict(base=base, rule=f"flip within {fw}", tune=fmt(tu), check=fmt(ch),
                             tune_pts=tu["pts"], check_pts=ch["pts"], tune_n=tu["n"]))
        for dm, rm in itertools.product((1.5, 2.0, 3.0), (0.75, 1.0, 1.5)):
            tu, ch, _ = evaluate(m1, base, delta_source="real", use_absorption=True, abs_delta_mult=dm, abs_range_mult=rm)
            grid.append(dict(base=base, rule=f"absorption d>={dm} r<={rm}", tune=fmt(tu), check=fmt(ch),
                             tune_pts=tu["pts"], check_pts=ch["pts"], tune_n=tu["n"]))
        print(f"grid {base} done", flush=True)
    g = pd.DataFrame(grid)
    print("\nGrid (real CVD; pick on tune, read check):")
    print(g.to_string(index=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the Journal Triggers backtest on the Databento ES data.

  python3 backtest/run.py                                 # full history, default settings
  python3 backtest/run.py --start 2026-09-28 --end 2026-10-28
  python3 backtest/run.py --set use_front_run=False --set front_min_rr=0.5
  python3 backtest/run.py --intrabar                      # 1-minute bars decide T1-vs-stop inside a candle

Results are per 1 ES contract ($50/point). "net" subtracts --cost dollars per round trip (default $30:
commission plus 1 tick of slippage each side).
"""
import argparse
import os
import sys
from dataclasses import fields

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_1m  # noqa: E402
from strategy import Params, compute, run, with_params  # noqa: E402

POINT = 50.0


def parse_sets(items):
    types = {f.name: f.type for f in fields(Params)}
    out = {}
    for it in items:
        k, v = it.split("=", 1)
        if k not in types:
            raise SystemExit(f"unknown setting {k}")
        t = types[k]
        if t in (bool, "bool"):
            out[k] = v.lower() in ("1", "true", "yes", "on")
        elif t in (int, "int"):
            out[k] = int(v)
        else:
            out[k] = float(v)
    return out


def summarize(t, cost, label=""):
    if t.empty:
        return {"label": label, "trades": 0}
    usd = t["pts"] * POINT
    net = usd - cost
    wins = (t["result"] == "T1").sum()
    losses = (t["result"] == "Stop").sum()
    eq = net.cumsum()
    dd = (eq - eq.cummax()).min()
    return {"label": label, "trades": len(t), "T1": int(wins), "Stop": int(losses), "Time": int((t["result"] == "Time").sum()),
            "win%": round(100 * wins / max(wins + losses, 1), 1), "gross$": round(usd.sum(), 2),
            "net$": round(net.sum(), 2), "avg_net$": round(net.mean(), 2), "maxDD$": round(dd, 2),
            "PF": round(net[net > 0].sum() / max(-net[net < 0].sum(), 1e-9), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--intrabar", action="store_true")
    ap.add_argument("--cost", type=float, default=30.0)
    ap.add_argument("--trades-csv")
    args = ap.parse_args()

    p = with_params(**parse_sets(args.set), intrabar=args.intrabar)
    m1 = load_1m()
    t = run(m1, p, compute(m1, p))
    if args.start:
        t = t[t["entry_time"] >= pd.Timestamp(args.start, tz="America/New_York")]
    if args.end:
        t = t[t["entry_time"] < pd.Timestamp(args.end, tz="America/New_York") + pd.Timedelta(days=1)]
    if args.trades_csv:
        t.to_csv(args.trades_csv, index=False)

    pd.set_option("display.width", 200)
    print(pd.DataFrame([summarize(t, args.cost, "ALL")]).to_string(index=False))
    if t.empty:
        return
    print("\nBy setup:")
    print(pd.DataFrame([summarize(g, args.cost, k) for k, g in t.groupby("setup")]).to_string(index=False))
    print("\nBy year:")
    print(pd.DataFrame([summarize(g, args.cost, k) for k, g in t.groupby(t["entry_time"].dt.year)]).to_string(index=False))
    print("\nWith vs against HTF bias:")
    print(pd.DataFrame([summarize(g, args.cost, "with" if k else "against") for k, g in t.groupby("aligned")]).to_string(index=False))


if __name__ == "__main__":
    main()

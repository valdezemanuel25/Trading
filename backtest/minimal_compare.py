#!/usr/bin/env python3
"""Fewer indicators: the strategy with only the 9 EMA, VWAP and volume profile vs the full version.

  python3 backtest/minimal_compare.py

Indicator sets (Params.indicators): all, core (9 EMA + VWAP + value area), core_levels (core + previous
day/week/premarket highs and lows and the 5-minute opening range). Value area from VWAP +/- 1 stdev (vwap_static)
or a real developing volume profile (profile). Baseline A and variant E, 2020-2023 and 2024-2026, 1 ES, $30/trade.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_1m  # noqa: E402
from strategy import compute, run, with_params  # noqa: E402

TZ = "America/New_York"
COST, POINT = 30.0, 50.0
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-26": ("2024-01-01", "2026-10-29")}
BASES = {"A": {}, "E": dict(win_start=1030, win_end=1100, t1_cap=10, be_trigger=4)}
RUNS = [(va, ind, {}) for va in ("vwap_static", "profile") for ind in ("all", "core", "core_levels")]
RUNS += [(va, "core", dict(need_cvd=False)) for va in ("vwap_static", "profile")]


def cell(t, a, b):
    t = t[(t["entry_time"] >= pd.Timestamp(a, tz=TZ)) & (t["entry_time"] < pd.Timestamp(b, tz=TZ))]
    if t.empty:
        return "0"
    net = (t["pts"] * POINT - COST).sum()
    return f"{len(t)}, {t['pts'].mean():+.2f}, {net:+,.0f}"


def main():
    m1 = load_1m()
    rows = []
    for base, bkw in BASES.items():
        for va, ind, extra in RUNS:
            p = with_params(**bkw, va_source=va, indicators=ind, **extra)
            t = run(m1, p, compute(m1, p))
            label = ind + (" no CVD" if extra.get("need_cvd") is False else "")
            row = dict(base=base, value_area=va, indicators=label,
                       **{k: cell(t, *v) for k, v in PERIODS.items()})
            row["setups"] = ", ".join(f"{k} {v}" for k, v in t["setup"].value_counts().items())
            rows.append(row)
            print(row, flush=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 120)
    print("\nCells: trades, avg gross pts per trade, net $")
    print(pd.DataFrame(rows).drop(columns="setups").to_string(index=False))
    print("\nTrades by setup:")
    print(pd.DataFrame(rows)[["base", "value_area", "indicators", "setups"]].to_string(index=False))


if __name__ == "__main__":
    main()

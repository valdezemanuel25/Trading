#!/usr/bin/env python3
"""Frozen candidate: noise-boundary intraday momentum on ES with volatility-targeted size.

Rules (fixed 2026-10-30 before the 2026 holdout was looked at; see docs/strategy-search.md):
- Every RTH day, upper/lower boundary = max/min(09:30 open, previous 16:00 close) x (1 +/- sigma_t), where
  sigma_t = average over the previous 14 sessions of |price at that minute / open - 1|.
- Decisions at 10:00, 10:30, ..., 15:30 (bar closes); orders fill at the next minute's open.
  Long above the upper boundary, short below the lower one. Exit when price is back past max(upper, VWAP) for longs /
  min(lower, VWAP) for shorts, or reverse on the opposite signal. Flat at 16:00.
- Size = 40 / (std of the last 14 daily close-to-close moves, ES points) ES contracts, rounded to 0.1 (MES), 0.1-2.
- Costs: $30 per ES round trip ($3 per MES), scaled with size.

  python3 research/final_noise.py            # train + validation
  python3 research/final_noise.py --holdout  # also the 2026 holdout
"""
import sys

import numpy as np
import pandas as pd

from noise import run
from panel import HOLDOUT, N, POINT, COST, TRAIN, VALID, load_panel, period_mask

REF_VOL, CAP = 40.0, 2.0


def positions(d):
    p, t = run(d, lookback=14, step=30, mult=1.0, first=30, stop_rule="paper", fill="next_open")
    close_ = d["close"][:, N - 1]
    prev_close = np.r_[np.nan, close_[:-1]]
    prev_close[d["roll"]] = np.nan
    vol14 = pd.Series(close_ - prev_close).rolling(14, min_periods=10).std().shift(1).to_numpy()
    size = np.nan_to_num(np.clip(np.round(REF_VOL / vol14, 1), 0.1, CAP), nan=1.0)
    return p, t, size


def main():
    d = load_panel()
    days = d["days"]
    p, t, size = positions(d)
    net = pd.Series(p * size * POINT - t * size * COST, index=days)
    periods = [("train 2020-23", TRAIN), ("valid 2024-25", VALID)]
    if "--holdout" in sys.argv:
        periods.append(("HOLDOUT 2026", HOLDOUT))
    for name, per in periods:
        m = period_mask(days, per)
        x = net[m]
        eq = x.cumsum()
        n_tr = t[m].sum()
        print(f"{name}: {n_tr} trades on {int((t[m] > 0).sum())} days, net ${x.sum():+,.0f}, "
              f"Sharpe {x.mean() / x.std() * np.sqrt(252):.2f}, maxDD ${(eq - eq.cummax()).min():,.0f}, "
              f"gross {p[m].sum() / n_tr:+.2f} pts/trade, avg size {size[m][t[m] > 0].mean():.2f} ES, "
              f"win days {100 * (x[t[m] > 0] > 0).mean():.0f}%")
        print("   by month:", " ".join(f"{k}:{v:+,.0f}" for k, v in x.groupby(x.index.strftime('%y-%m')).sum().items())
              if name.startswith("HOLD") else "   by year: " + " ".join(
                  f"{k}:{v:+,.0f}" for k, v in x.groupby(x.index.year).sum().items()))


if __name__ == "__main__":
    main()

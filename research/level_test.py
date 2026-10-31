#!/usr/bin/env python3
"""Do session open prices act as support/resistance? Bounce rate at the first retest vs control levels.

For each trading day and level: from 30 minutes after the session open (or the NY open, whichever is later)
until 16:00 ET, find the first 1-minute bar that touches the level coming from one side. From the touch, does price
move `x` points back to the side it came from (bounce) before `x` points through (break)?
Control levels = the same open shifted by +/- 2.25, 3.75, 6.25 points (prices nobody marks).

  python3 research/level_test.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load_1m  # noqa: E402
from session_open import SESSIONS, session_open, NY  # noqa: E402

OFFSETS = (-6.25, -3.75, -2.25, 2.25, 3.75, 6.25)


def first_retest(h, l, c, lvl, x):
    """From the first bar that touches lvl after starting on one side: 1 = bounce, 0 = break, None = no result."""
    side = np.sign(c[0] - lvl) if c[0] != lvl else 0
    if side == 0:
        return None
    for i in range(1, len(h)):
        if l[i] <= lvl <= h[i]:
            # resolve from this bar on: bounce = back x pts on the original side, break = x pts through
            up, dn = lvl + x, lvl - x
            for j in range(i + 1, len(h)):
                hit_up, hit_dn = h[j] >= up, l[j] <= dn
                if hit_up and hit_dn:
                    return None
                if hit_up:
                    return 1 if side > 0 else 0
                if hit_dn:
                    return 1 if side < 0 else 0
            return None
    return None


def main():
    m1 = load_1m()
    idx = m1.index
    H, L, C, O = (m1[k].to_numpy(float) for k in ("high", "low", "close", "open"))
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    rows = []
    for td in pd.Index(tday.unique()):
        ny_open = session_open(td, "New York")
        end = pd.Timestamp(year=td.year, month=td.month, day=td.day, hour=16, tz=NY)
        for name in SESSIONS:
            t0 = session_open(td, name)
            i0 = idx.searchsorted(t0)
            if i0 >= len(idx) or idx[i0] != t0:
                continue
            lvl0 = O[i0]
            start = max(t0 + pd.Timedelta(minutes=30), ny_open)
            a, b = idx.searchsorted(start), idx.searchsorted(end)
            if b - a < 30:
                continue
            h, l, c = H[a:b], L[a:b], C[a:b]
            for x in (5.0, 10.0):
                for off in (0.0,) + OFFSETS:
                    r = first_retest(h, l, c, lvl0 + off, x)
                    if r is not None:
                        rows.append(dict(year=td.year, session=name, x=x, level="open" if off == 0 else "control", bounce=r))
    df = pd.DataFrame(rows)
    df["period"] = pd.cut(df.year, [2019, 2023, 2025, 2026], labels=["2020-23", "2024-25", "2026"])
    out = df.groupby(["x", "session", "level"], observed=True)["bounce"].agg(["mean", "size"]).unstack("level")
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    out["edge_pp"] = 100 * (out["mean_open"] - out["mean_control"])
    # standard error of the difference (binomial)
    p1, n1, p0, n0 = out["mean_open"], out["size_open"], out["mean_control"], out["size_control"]
    out["z"] = (p1 - p0) / np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    for k in ("mean_open", "mean_control"):
        out[k] = (100 * out[k]).round(1)
    pd.set_option("display.width", 200)
    print("Bounce rate (%) at the first retest during NY hours, session open vs control levels:")
    print(out.round(2).to_string())
    print("\nBy period (5-pt test, all sessions):")
    p = df[df.x == 5].groupby(["period", "level"], observed=True)["bounce"].agg(["mean", "size"]).unstack("level")
    print((p.xs("mean", axis=1, level=0) * 100).round(1).join(p.xs("size", axis=1, level=0), rsuffix="_n").to_string())


if __name__ == "__main__":
    main()

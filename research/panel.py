"""Day x minute panels of ES regular-session (09:30-16:00 ET) 1-minute bars, for strategy research.

Built from backtest/data.load_1m() (continuous front month, unadjusted). Days where the front contract changed
since the previous session are flagged `roll`: comparisons with the previous day's prices are invalid there.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
from data import CACHE, load_1m  # noqa: E402

N = 390  # minutes 09:30 .. 15:59 (bar start times)
TRAIN = ("2020-01-01", "2024-01-01")
VALID = ("2024-01-01", "2026-01-01")
HOLDOUT = ("2026-01-01", "2026-11-01")
POINT, COST = 50.0, 30.0


def load_panel(use_cache=True):
    path = os.path.join(CACHE, "rth_panel.pkl")
    m1 = load_1m()
    stamp = (len(m1), str(m1.index[-1]))
    if use_cache and os.path.exists(path):
        d = pd.read_pickle(path)
        if d["stamp"] == stamp:
            return d
    idx = m1.index
    mins = (idx.hour * 60 + idx.minute) - (9 * 60 + 30)
    rth = (mins >= 0) & (mins < N)
    r = m1[rth].copy()
    r["date"] = r.index.tz_localize(None).normalize()
    r["m"] = mins[rth]
    days = pd.Index(sorted(r["date"].unique()))
    out = {}
    for k in ("open", "high", "low", "close", "volume"):
        out[k] = r.pivot_table(index="date", columns="m", values=k, aggfunc="first").reindex(index=days, columns=range(N))
    # fill missing minutes: price carries forward, volume 0
    out["close"] = out["close"].ffill(axis=1)
    for k in ("open", "high", "low"):
        out[k] = out[k].fillna(out["close"])
    out["volume"] = out["volume"].fillna(0)
    sym = r.groupby("date")["symbol"].first().reindex(days)
    full = out["open"].notna().sum(axis=1)
    # overnight session (18:00 previous day -> 09:29) of the same trading day, same contract as RTH
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    on = m1[(~rth) & ((idx.hour >= 18) | (mins < 0))].copy()
    on["date"] = tday[(~rth) & ((idx.hour >= 18) | (mins < 0))]
    g = on.groupby("date")
    d = dict(stamp=stamp, days=days, sym=sym, nbars=full, **{k: v.to_numpy(float) for k, v in out.items()},
             on_high=g["high"].max().reindex(days).to_numpy(), on_low=g["low"].min().reindex(days).to_numpy(),
             on_open=g["open"].first().reindex(days).to_numpy())
    d["roll"] = (sym != sym.shift(1)).to_numpy().copy()
    d["roll"][0] = True
    pd.to_pickle(d, path)
    return d


def period_mask(days, period):
    return (days >= pd.Timestamp(period[0])) & (days < pd.Timestamp(period[1]))


def report(pts_by_day, days, label="", trades=None, show_hold=False):
    """pts_by_day: gross points per day (NaN or 0 = no trade); trades: number of round trips per day."""
    pts = pd.Series(pts_by_day, index=days)
    nt = pd.Series(trades if trades is not None else (pts.fillna(0) != 0).astype(int), index=days)
    net = pts.fillna(0) * POINT - nt * COST
    rows = []
    periods = [("train", TRAIN), ("valid", VALID)] + ([("hold", HOLDOUT)] if show_hold else [])
    for name, per in periods:
        msk = period_mask(days, per)
        n_, t_ = net[msk], nt[msk]
        if t_.sum() == 0:
            rows.append(f"{name}: no trades")
            continue
        daily = n_
        sharpe = daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0
        eq = daily.cumsum()
        dd = (eq - eq.cummax()).min()
        rows.append(f"{name}: {int(t_.sum())} tr, {pts[msk].fillna(0).sum() / t_.sum():+.2f} pts/tr, "
                    f"net ${n_.sum():+,.0f}, Sharpe {sharpe:.2f}, maxDD ${dd:,.0f}")
    return f"{label:38s} | " + " | ".join(rows)

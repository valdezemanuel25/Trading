#!/usr/bin/env python3
"""RSI(2) pullback (long only, above the 200-day SMA) on ES, NQ, RTY and YM, alone and as a portfolio.

Daily closes = the 00:00 UTC daily bar close for every market (Databento ohlcv-1d for NQ/RTY/YM in data/daily/,
rebuilt from 1-minute bars for ES), so all four use the same timing. Front contract per day by volume, rolling
forward only. Indicators on roll-adjusted closes; each trade priced in its entry contract.

  python3 research/multi.py
"""
import io
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import _expiry_rank, load_1m  # noqa: E402
import rsi2  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# point value and round-trip cost: full contract, micro contract
SPEC = {"ES": dict(point=50, cost=30, mpoint=5, mcost=4.0), "NQ": dict(point=20, cost=15, mpoint=2, mcost=2.5),
        "RTY": dict(point=50, cost=15, mpoint=5, mcost=2.5), "YM": dict(point=5, cost=15, mpoint=0.5, mcost=2.5)}


def front_from_bars(df):
    """df: date, symbol, close, volume (all outright contracts). Returns dict(front=..., closes=...)."""
    df = df[df.index.dayofweek < 5] if isinstance(df.index, pd.DatetimeIndex) else df
    vol = df.groupby(["date", "symbol"])["volume"].sum().reset_index()
    vol["rank"] = [_expiry_rank(s[-2:] if s.startswith("RTY") else s, d.year) if False else _rank(s, d.year)
                   for s, d in zip(vol["symbol"], vol["date"])]
    best = vol.sort_values(["date", "volume"], ascending=[True, False]).drop_duplicates("date")
    front, cur = {}, -1
    for d, s, r in zip(best["date"], best["symbol"], best["rank"]):
        if r < cur:
            c = vol[(vol["date"] == d) & (vol["rank"] >= cur)].sort_values("volume", ascending=False)
            s, r = c.iloc[0]["symbol"], c.iloc[0]["rank"]
        front[d], cur = s, r
    closes = df.set_index(["date", "symbol"])["close"]
    closes = closes[~closes.index.duplicated()]
    fr = pd.DataFrame({"symbol": pd.Series(front)})
    fr["close"] = [closes.get((d, s)) for d, s in zip(fr.index, fr["symbol"])]
    return dict(front=fr, closes=closes)


def _rank(sym, year):
    """Expiry rank for ESZ6 / NQZ6 / RTYZ6 / YMZ6 style symbols."""
    m = {"H": 3, "M": 6, "U": 9, "Z": 12}[sym[-2]]
    digit = int(sym[-1])
    y = year - (year % 10) + digit
    if y < year - 1:
        y += 10
    return y * 100 + m


def load_market(root):
    if root == "ES":
        m1 = load_1m()
        # all ES outrights are not in load_1m (front only); the front-only close is enough for a same-contract hold
        # except on roll days, so rebuild per-contract UTC-day closes from the raw files
        import glob
        from data import DATA_DIR, OUTRIGHT
        from zstd_io import read_zst
        parts = []
        for fp in sorted(glob.glob(os.path.join(DATA_DIR, "glbx-mdp3-*.ohlcv-1m.csv.zst"))):
            x = pd.read_csv(io.BytesIO(read_zst(fp)), usecols=["ts_event", "close", "volume", "symbol"])
            x = x[x["symbol"].str.match(OUTRIGHT)]
            x["date"] = pd.to_datetime(x["ts_event"]).dt.tz_localize(None).dt.normalize()
            parts.append(x.sort_values("ts_event").groupby(["date", "symbol"]).agg(close=("close", "last"),
                                                                                  volume=("volume", "sum")).reset_index())
        df = pd.concat(parts)
    else:
        x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{root}.csv"))
        x = x[x["symbol"].str.fullmatch(rf"{root}[HMUZ]\d")]
        x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
        x["close"] = x["close"] / 1e9
        df = x[["date", "symbol", "close", "volume"]]
    df = df[df["date"].dt.dayofweek < 5]
    return front_from_bars(df)


def main():
    rows, all_trades = [], []
    for root in SPEC:
        dd = load_market(root)
        for rmax in (10, 30):
            t = rsi2.backtest(dd, rsi_max=rmax)
            t["root"], t["rmax"] = root, rmax
            sp = SPEC[root]
            t["net_full"] = t["pts"] * sp["point"] - sp["cost"]
            t["net_micro"] = t["pts"] * sp["mpoint"] - sp["mcost"]
            all_trades.append(t)
    T = pd.concat(all_trades)
    pd.set_option("display.width", 220)
    for rmax in (10, 30):
        print(f"\n===== RSI(2) < {rmax}, long only above the 200-day SMA =====")
        for root in list(SPEC) + ["PORTFOLIO (1 micro each)"]:
            x = T[T.rmax == rmax] if root.startswith("PORT") else T[(T.rmax == rmax) & (T.root == root)]
            col = "net_micro" if root.startswith("PORT") else "net_full"
            cells = []
            for per, (a, b) in rsi2.PERIODS.items():
                y = x[(x.entry_date >= a) & (x.entry_date < b)].sort_values("exit_date")
                if y.empty:
                    cells.append(f"{per}: 0")
                    continue
                weeks = (min(pd.Timestamp(b), pd.Timestamp("2026-10-29")) - max(pd.Timestamp(a), pd.Timestamp("2020-10-16"))).days / 7
                eq = y[col].cumsum()
                pf = y.loc[y[col] > 0, col].sum() / max(-y.loc[y[col] < 0, col].sum(), 1)
                cells.append(f"{per}: {len(y)} tr ({len(y) / weeks:.1f}/wk), win {100 * (y.pts > 0).mean():.0f}%, "
                             f"net ${y[col].sum():+,.0f}, PF {pf:.2f}, DD ${(eq - eq.cummax()).min():,.0f}")
            print(f"{root:26s} " + " | ".join(cells))
        # how often do the markets signal on the same day?
        x = T[T.rmax == rmax]
        per_day = x.groupby("entry_date")["root"].nunique()
        print(f"signal days: {len(per_day)}, of which {100 * (per_day >= 2).mean():.0f}% have 2+ markets "
              f"and {100 * (per_day == 4).mean():.0f}% all four")
    T.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "multi_trades.csv"), index=False)


if __name__ == "__main__":
    main()

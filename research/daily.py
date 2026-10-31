"""Daily ES series for multi-day strategies.

`front`: per trading day, the front contract (same roll as backtest/data.load_1m) and its 16:00 ET close.
`closes`: 16:00 ET close of EVERY outright contract per day, so a trade can be valued in the contract it was entered
in (no roll jumps).
"""
import glob
import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtest"))
from data import CACHE, DATA_DIR, OUTRIGHT, load_1m  # noqa: E402
from zstd_io import read_zst  # noqa: E402


def load_daily(use_cache=True):
    path = os.path.join(CACHE, "daily_closes.pkl")
    if use_cache and os.path.exists(path):
        return pd.read_pickle(path)
    parts = []
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, "glbx-mdp3-*.ohlcv-1m.csv.zst"))):
        df = pd.read_csv(io.BytesIO(read_zst(fp)), usecols=["ts_event", "close", "high", "low", "symbol"])
        df = df[df["symbol"].str.match(OUTRIGHT)]
        df["ts"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("America/New_York")
        rth = (df["ts"].dt.hour * 60 + df["ts"].dt.minute).between(9 * 60 + 30, 15 * 60 + 59)
        df = df[rth]
        df["date"] = df["ts"].dt.tz_localize(None).dt.normalize()
        parts.append(df.sort_values("ts").groupby(["date", "symbol"]).agg(close=("close", "last"), high=("high", "max"),
                                                                       low=("low", "min")))
    closes = pd.concat(parts)
    m1 = load_1m()
    rth = (m1.index.hour * 60 + m1.index.minute >= 570) & (m1.index.hour * 60 + m1.index.minute < 960)
    fr = m1[rth].groupby(m1[rth].index.tz_localize(None).normalize())["symbol"].first()
    front = pd.DataFrame({"symbol": fr})
    front["close"] = [closes["close"].get((d, s)) for d, s in zip(front.index, front["symbol"])]
    front["high"] = [closes["high"].get((d, s)) for d, s in zip(front.index, front["symbol"])]
    front["low"] = [closes["low"].get((d, s)) for d, s in zip(front.index, front["symbol"])]
    out = dict(front=front, closes=closes["close"])
    pd.to_pickle(out, path)
    return out

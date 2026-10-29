"""Load Databento ES 1-minute OHLCV files and build the bars the strategy uses.

- Reads every data/glbx-mdp3-*.ohlcv-1m.csv.zst file (one per month).
- Keeps outright ES futures only (ESH6, ESM6, ... - no calendar spreads).
- Builds one continuous, unadjusted front-month series: each trading day uses the contract with the most volume
  that day, and the roll only moves forward (never back to an expiring contract). Like ToS /ES.
- Times are converted to America/New_York. The trading day runs 18:00 ET -> 17:00 ET and is labelled with the
  date it ends on (ToS GetYYYYMMDD for futures).
"""
import glob
import io
import os
import re

import numpy as np
import pandas as pd

from zstd_io import read_zst

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "backtest", ".cache")
TZ = "America/New_York"
OUTRIGHT = re.compile(r"^ES[HMUZ]\d$")
MONTH_CODE = {"H": 3, "M": 6, "U": 9, "Z": 12}


def _read_month(path):
    df = pd.read_csv(io.BytesIO(read_zst(path)), usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"])
    return df[df["symbol"].str.match(OUTRIGHT)]


def _expiry_rank(sym, year_hint):
    """Sortable (year, month) for ESZ6-style symbols; the single year digit is resolved near year_hint."""
    month = MONTH_CODE[sym[2]]
    digit = int(sym[3])
    year = year_hint - (year_hint % 10) + digit
    if year < year_hint - 1:
        year += 10
    return year * 100 + month


def load_1m(use_cache=True):
    """Continuous front-month ES 1-minute bars indexed by New York time."""
    os.makedirs(CACHE, exist_ok=True)
    cache_file = os.path.join(CACHE, "es_1m.pkl")
    files = sorted(glob.glob(os.path.join(DATA_DIR, "glbx-mdp3-*.ohlcv-1m.csv.zst")))
    if not files:
        raise SystemExit("No data files found in data/")
    stamp = (len(files), sum(os.path.getsize(f) for f in files))
    if use_cache and os.path.exists(cache_file):
        cached = pd.read_pickle(cache_file)
        if cached.attrs.get("stamp") == stamp:
            return cached

    df = pd.concat([_read_month(f) for f in files], ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(TZ)
    df = df.drop(columns="ts_event")
    # trading day: bars from 18:00 ET belong to the next calendar day's session
    df["tday"] = (df["ts"] + pd.Timedelta(hours=6)).dt.normalize().dt.tz_localize(None)

    # front month per trading day by volume, rolling forward only
    vol = df.groupby(["tday", "symbol"])["volume"].sum().reset_index()
    vol["rank"] = [_expiry_rank(s, d.year) for s, d in zip(vol["symbol"], vol["tday"])]
    best = vol.sort_values(["tday", "volume"], ascending=[True, False]).drop_duplicates("tday")
    front, cur_rank = {}, -1
    for tday, sym, rank in zip(best["tday"], best["symbol"], best["rank"]):
        if rank < cur_rank:  # never roll back to an older contract
            cand = vol[(vol["tday"] == tday) & (vol["rank"] >= cur_rank)].sort_values("volume", ascending=False)
            sym, rank = cand.iloc[0]["symbol"], cand.iloc[0]["rank"]
        front[tday], cur_rank = sym, rank
    df = df[df["symbol"].values == df["tday"].map(front).values]

    out = (df.set_index("ts")[["open", "high", "low", "close", "volume", "symbol"]]
           .sort_index())
    out = out[~out.index.duplicated(keep="first")]
    out.attrs["stamp"] = stamp
    out.to_pickle(cache_file)
    return out


def resample(m1, rule, offset=None):
    """OHLCV bars from 1-minute bars. Bars are labelled by their START time (like ToS)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    kw = {"label": "left", "closed": "left"}
    if offset is not None:
        kw["offset"] = offset
    bars = m1[["open", "high", "low", "close", "volume"]].resample(rule, **kw).agg(agg)
    return bars.dropna(subset=["open"])


def bars_5m(m1):
    return resample(m1, "5min")


def bars_1h(m1):
    return resample(m1, "1h")


def bars_4h(m1):
    """ToS futures 4h bars are anchored to the 18:00 ET session open: 18-22, 22-02, 02-06, 06-10, 10-14, 14-17.
    Built from New York wall-clock time so the anchor stays at 18:00 through daylight-saving changes.
    Each bar is labelled by its first 1-minute bar's time."""
    idx = m1.index
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    mins = ((idx.hour - 18) % 24) * 60 + idx.minute
    key = pd.MultiIndex.from_arrays([tday, mins // 240])
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    g = m1[["open", "high", "low", "close", "volume"]].groupby(key, sort=True)
    bars = g.agg(agg)
    bars.index = g.apply(lambda x: x.index[0])
    return bars.sort_index()


def bars_day(m1):
    """Trading-day (18:00 -> 17:00 ET) high/low, indexed by trading day."""
    tday = (m1.index + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    g = m1.groupby(tday)
    return pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})


if __name__ == "__main__":
    m1 = load_1m()
    print(m1.index[0], "->", m1.index[-1], f"{len(m1):,} 1m bars")
    rolls = m1["symbol"].ne(m1["symbol"].shift()).cumsum()
    print("contracts used:", m1.groupby(rolls)["symbol"].first().tolist())
    b5 = bars_5m(m1)
    print(f"{len(b5):,} 5m bars")
    print(b5.tail(3))

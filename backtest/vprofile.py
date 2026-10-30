"""Developing session volume profile (POC / VAH / VAL) on 5-minute bars, built from 1-minute bars.

Like the ToS JournalTriggers default (vaSource = PROFILE, profileReset = ETH): the profile resets at the 18:00 ET
session open and, at each 5-minute candle's close, only contains volume printed up to that close (no look-ahead).
Each 1-minute bar's volume is spread evenly over the ticks between its low and high. The value area grows from the
POC one tick at a time toward the side with more volume until it holds `pct` of the session's volume.
"""
import os

import numpy as np
import pandas as pd

from data import CACHE

TICK = 0.25


def _value_area(hist, pct):
    poc = int(np.argmax(hist))
    target = hist.sum() * pct
    vols = hist.tolist()
    lo = hi = poc
    acc = vols[poc]
    last = len(vols) - 1
    while acc < target and (lo > 0 or hi < last):
        up = vols[hi + 1] if hi < last else -1.0
        dn = vols[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return poc, hi, lo


def developing_profile(m1, pct=0.70, use_cache=True):
    """DataFrame indexed like data.bars_5m(m1) (5m bar start, New York time) with columns poc, vah, val."""
    os.makedirs(CACHE, exist_ok=True)
    cache_file = os.path.join(CACHE, f"vp_5m_{int(pct * 100)}.pkl")
    stamp = (len(m1), str(m1.index[0]), str(m1.index[-1]), float(m1["volume"].sum()))
    if use_cache and os.path.exists(cache_file):
        cached = pd.read_pickle(cache_file)
        if cached.attrs.get("stamp") == stamp:
            return cached

    idx = m1.index
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None).to_numpy()
    bar5 = idx.floor("5min")
    lo_t = np.round(m1["low"].to_numpy() / TICK).astype(np.int64)
    hi_t = np.round(m1["high"].to_numpy() / TICK).astype(np.int64)
    vol = m1["volume"].to_numpy(float)
    # last 1-minute bar of each 5-minute bucket: the profile is read after it
    b5 = bar5.asi8
    is_last = np.r_[b5[1:] != b5[:-1], True]

    starts = np.flatnonzero(np.r_[True, tday[1:] != tday[:-1]])
    ends = np.r_[starts[1:], len(idx)]
    out_t, out_poc, out_vah, out_val = [], [], [], []
    for s, e in zip(starts, ends):
        base = lo_t[s:e].min()
        hist = np.zeros(hi_t[s:e].max() - base + 1)
        for i in range(s, e):
            a, b = lo_t[i] - base, hi_t[i] - base
            hist[a:b + 1] += vol[i] / (b - a + 1)
            if is_last[i] and hist.any():
                poc, hi, lo = _value_area(hist, pct)
                out_t.append(b5[i])
                out_poc.append((poc + base) * TICK)
                out_vah.append((hi + base) * TICK)
                out_val.append((lo + base) * TICK)
    out = pd.DataFrame({"poc": out_poc, "vah": out_vah, "val": out_val},
                       index=pd.to_datetime(out_t, utc=True).tz_convert(idx.tz))
    out.attrs["stamp"] = stamp
    out.to_pickle(cache_file)
    return out

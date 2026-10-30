"""Noise-boundary intraday momentum (Zarattini, Aziz & Barbon 2024, 'Beat the Market') on ES 1-minute RTH bars.

Each day: boundaries = max/min(open, previous close) x (1 +/- sigma_t), where sigma_t is the average over the last
`lookback` days of |close at minute t / open - 1|. At each decision time (every `step` minutes from 10:00), go long
above the upper boundary, short below the lower one. A position exits when price is back inside the boundary AND past
VWAP (trailing stop = max(upper, VWAP) for longs, min(lower, VWAP) for shorts), checked at decision times.
Everything is flat at the 16:00 close. Returns gross points per day and round trips per day for 1 contract.
"""
import numpy as np

from panel import N


def sigma_table(d, lookback):
    O, C = d["open"], d["close"]
    move = np.abs(C / O[:, :1] - 1)
    sig = np.full_like(move, np.nan)
    cs = np.vstack([np.zeros((1, N)), np.cumsum(move, axis=0)])
    for i in range(lookback, len(move)):
        sig[i] = (cs[i] - cs[i - lookback]) / lookback
    return sig


def run(d, lookback=14, step=30, mult=1.0, first=30, last=None, side="both", stop_rule="paper", sig=None,
        fill="close"):
    O, H, L, C, V = d["open"], d["high"], d["low"], d["close"], d["volume"]
    nd = len(O)
    open_, close_ = O[:, 0], C[:, N - 1]
    prev_close = np.r_[np.nan, close_[:-1]]
    prev_close[d["roll"]] = np.nan
    pc = np.where(np.isnan(prev_close), open_, prev_close)
    sigma = sigma_table(d, lookback) if sig is None else sig
    ub = np.fmax(open_, pc)[:, None] * (1 + mult * sigma)
    lb = np.fmin(open_, pc)[:, None] * (1 - mult * sigma)
    tp = (H + L + C) / 3
    vwap = np.cumsum(tp * V, axis=1) / np.maximum(np.cumsum(V, axis=1), 1)
    last = N - 1 if last is None else last
    times = list(range(first - 1, last, step))
    pts = np.zeros(nd)
    trades = np.zeros(nd, int)
    for i in range(nd):
        if np.isnan(sigma[i, 0]):
            continue
        pos, entry = 0, 0.0
        for t in times:
            px = C[i, t]
            fx = O[i, t + 1] if fill == "next_open" else px  # price the order actually gets
            want = 1 if px > ub[i, t] else (-1 if px < lb[i, t] else 0)
            if side == "long" and want < 0:
                want = 0
            if side == "short" and want > 0:
                want = 0
            if pos != 0:
                stop = max(ub[i, t], vwap[i, t]) if pos > 0 else min(lb[i, t], vwap[i, t])
                if stop_rule == "paper":
                    out = px < stop if pos > 0 else px > stop
                else:  # "boundary": exit only when back inside the boundary
                    out = want != pos
                if out or want == -pos:
                    pts[i] += (fx - entry) * pos
                    pos = 0
            if pos == 0 and want != 0:
                pos, entry = want, fx
                trades[i] += 1
        if pos != 0:
            pts[i] += (close_[i] - entry) * pos
    return pts, trades

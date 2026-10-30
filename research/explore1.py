#!/usr/bin/env python3
"""Survey of documented intraday effects on ES, textbook settings, train/valid only (holdout hidden).

  python3 research/explore1.py
"""
import numpy as np

from panel import N, load_panel, report

d = load_panel()
days, O, H, L, C = d["days"], d["open"], d["high"], d["low"], d["close"]
roll = d["roll"]
open_ = O[:, 0]
close_ = C[:, N - 1]
prev_close = np.r_[np.nan, close_[:-1]]
prev_close[roll] = np.nan          # different contract: gap meaningless
nd = len(days)
out = []

# 1) overnight drift and day session
on = open_ - prev_close
out.append(report(np.where(np.isnan(on), 0, on), days, "overnight long (close->open)"))
out.append(report(close_ - open_, days, "day session long (open->close)"))

# 2) intraday momentum: sign(prev close -> 10:00) traded 15:30 -> 16:00
r1 = C[:, 29] - prev_close
sig = np.sign(r1)
pts = sig * (close_ - C[:, 359])
out.append(report(np.where(np.isnan(pts), 0, pts), days, "intraday momentum 15:30-16:00"))
# variant: sign of open -> 15:30 return traded into the close
sig2 = np.sign(C[:, 359] - open_)
out.append(report(sig2 * (close_ - C[:, 359]), days, "momentum open->15:30, last 30m"))


# 3) noise-boundary momentum (Zarattini, Aziz & Barbon 2024)
def noise_area(lookback=14, step=30, use_vwap_stop=True):
    move = np.abs(C / open_[:, None] - 1)           # |close_t / open - 1|
    sigma = np.full_like(move, np.nan)
    for i in range(lookback, nd):
        sigma[i] = move[i - lookback:i].mean(axis=0)
    ref_hi = np.fmax(open_, np.where(np.isnan(prev_close), open_, prev_close))
    ref_lo = np.fmin(open_, np.where(np.isnan(prev_close), open_, prev_close))
    ub = ref_hi[:, None] * (1 + sigma)
    lb = ref_lo[:, None] * (1 - sigma)
    tp = (H + L + C) / 3
    vol = d["volume"]
    vwap = np.cumsum(tp * vol, axis=1) / np.maximum(np.cumsum(vol, axis=1), 1)
    pts = np.zeros(nd)
    trades = np.zeros(nd, int)
    for i in range(lookback, nd):
        pos, entry = 0, 0.0
        for t in range(step - 1, N - 1, step):       # decisions at 10:00, 10:30, ... 15:30 (bar closes)
            px = C[i, t]
            want = 1 if px > ub[i, t] else (-1 if px < lb[i, t] else 0)
            if pos != 0:
                stop = (max(ub[i, t], vwap[i, t]) if pos > 0 else min(lb[i, t], vwap[i, t])) if use_vwap_stop else None
                exit_ = want != pos and (stop is None or (px < stop if pos > 0 else px > stop))
                if exit_ or want == -pos:
                    pts[i] += (px - entry) * pos
                    pos = 0
            if pos == 0 and want != 0:
                pos, entry = want, px
                trades[i] += 1
        if pos != 0:
            pts[i] += (close_[i] - entry) * pos
    return pts, trades


for lb_, step in ((14, 30), (14, 15), (10, 30)):
    pts, tr = noise_area(lb_, step)
    out.append(report(pts, days, f"noise-area momentum lb{lb_} step{step}", tr))


# 4) opening-range breakout: first k minutes, stop at the other side, exit at close
def orb(k):
    hi, lo = H[:, :k].max(axis=1), L[:, :k].min(axis=1)
    pts = np.zeros(nd)
    for i in range(nd):
        pos = 0
        for t in range(k, N):
            if pos == 0:
                if C[i, t] > hi[i]:
                    pos, entry, stop = 1, C[i, t], lo[i]
                elif C[i, t] < lo[i]:
                    pos, entry, stop = -1, C[i, t], hi[i]
                continue
            if (pos > 0 and L[i, t] <= stop) or (pos < 0 and H[i, t] >= stop):
                pts[i] = (stop - entry) * pos
                break
        else:
            if pos != 0:
                pts[i] = (close_[i] - entry) * pos
    return pts


for k in (5, 15, 30):
    out.append(report(orb(k), days, f"opening-range breakout {k}m"))

# 5) gap fade: gap beyond g points, fade at the open, target prev close, stop g points, exit 11:00
for g in (10, 20):
    gap = open_ - prev_close
    pts = np.zeros(nd)
    for i in np.flatnonzero(np.abs(np.nan_to_num(gap)) >= g):
        s = -np.sign(gap[i])
        tgt, stp = prev_close[i], open_[i] - s * g
        for t in range(0, 90):
            if (s > 0 and L[i, t] <= stp) or (s < 0 and H[i, t] >= stp):
                pts[i] = (stp - open_[i]) * s
                break
            if (s > 0 and H[i, t] >= tgt) or (s < 0 and L[i, t] <= tgt):
                pts[i] = (tgt - open_[i]) * s
                break
        else:
            pts[i] = (C[i, 89] - open_[i]) * s
    out.append(report(pts, days, f"gap fade >= {g} pts"))

print("\n".join(out))

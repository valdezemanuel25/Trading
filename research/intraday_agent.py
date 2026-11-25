#!/usr/bin/env python3
"""Intraday agent on Liquid, step 2: four hourly-wake rules on ES, NQ and CL 1-minute data (research only).

  python3 research/intraday_agent.py

The agent wakes at :45 past each hour, 9:45-15:45 ET, and decides on what it can see live: price, hourly candles
(clock hours, 24-hour session, like Liquid's 1h candles), session VWAP from 9:30 ET, hourly Bollinger Bands (20, 2),
the 9:30-10:30 opening range and the last completed daily candle (00:00 UTC, Liquid's) vs its 200-day SMA.

Fills:
  - Market orders at a wake fill at the 1-minute close 5 minutes after the wake (your approval): the close of the
    bar that starts at wake+4.
  - Wake-checked exits (an hourly close through a level) fill the same way at the wake that sees them.
  - Resting stop or take-profit triggers (Liquid position TP/SL, approved together with the entry) fill at the level,
    or at the 1-minute open if a bar opens through it. A bar touching both counts as the stop.
  - Everything still open is closed at the 15:45 wake (fill 15:50).

Rules (long and short unless noted):
  1 VWAP trend hold: 10:45 wake; long if price > VWAP, > opening-range high and VWAP rising (VWAP now > VWAP
    `slope` minutes ago). Stop: an hourly close back through VWAP, checked at the 11:45-14:45 wakes. Exit 15:45.
  2 Hourly Bollinger snap-back (long only): any wake 9:45-14:45; the last completed hourly candle closed below the
    lower band and yesterday's daily close is above its 200-day SMA -> buy. Exit at the middle band (`tp`: resting
    trigger at the entry wake's middle band, or an hourly close at or above the current middle band at a wake) or
    15:45. The rule names no stop, so it gets a resting catastrophe stop `k` x hourly ATR(14) below entry; that
    stop also sets the size.
  3 First-hour breakout: 10:45 wake; price beyond the opening range -> enter that way. Stop at the middle of the range
    (`stop`: resting trigger, or an hourly close beyond it at a wake). Exit 15:45.
  4 Band walk: rule 1, only if the 9:00-10:00 hourly candle (the last one the 10:45 wake sees) closed at %B >= `pb`
    (long) or <= 1 - `pb` (short).

Size: $50 at the stop (risk = entry to stop level at entry: VWAP for 1/4, range middle for 3, catastrophe stop for 2),
notional capped at $20,000 (2x the agent's $10,000 budget), so a stop closer than 0.25% risks less than $50.
Costs, round trip, on notional: Liquid 0.10% (step 1: unmeasured, no fills yet); futures for comparison: ES 0.6 pt,
NQ 0.75 pt, CL 0.025 (1 tick each way plus commission).
Daily limits (all markets together): at most 2 trades and no new entry after -$100 realised; markets in the order
ES, NQ, CL when signals arrive at the same wake.
Skipped days: the front contract changes during the session (roll), fewer than 370 session bars, and for the bands
any 20-hour window that spans a roll.
Settings are picked on 2020-23 (all three markets pooled, Liquid cost); 2024-25 is context; 2026-01 to 2026-10 is the
holdout. Pass: positive in 2020-23 AND the holdout, and the holdout's average trade > 1 standard error.
"""
import io
import itertools
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
from zstd_io import read_zst  # noqa: E402

TZ = "America/New_York"
CACHE = os.path.join(ROOT, "backtest", ".cache")
MARKETS = ["ES", "NQ", "CL"]
FUT_COST = {"ES": 0.6, "NQ": 0.75, "CL": 0.025}        # points per round trip
LIQ_COST = 0.001
RISK, CAP = 50.0, 20000.0
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "2026": ("2026-01-01", "2026-11-01")}
S0 = 570                                               # 9:30 ET, minute of day
WAKES = [h * 60 + 45 for h in range(9, 16)]           # 9:45 ... 15:45
LAST = 15 * 60 + 45


# ------------------------------------------------------------------ data
def load(m):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"agent_1m_{m}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    if m == "ES":
        from data import load_1m
        x = load_1m()
        df = x[["open", "high", "low", "close", "volume"]].copy()
        df["inst"] = pd.factorize(x["symbol"])[0]
    else:
        x = pd.read_csv(io.BytesIO(read_zst(os.path.join(ROOT, "data", "intraday", f"{m}_1m.csv.zst"))),
                        usecols=["ts_event", "open", "high", "low", "close", "volume", "instrument_id"])
        x.index = pd.DatetimeIndex(pd.to_datetime(x["ts_event"], unit="ns", utc=True)).tz_convert(TZ)
        df = pd.DataFrame({c: x[c].to_numpy() / 1e9 for c in ("open", "high", "low", "close")}, index=x.index)
        df["volume"] = x["volume"].to_numpy()
        df["inst"] = x["instrument_id"].to_numpy()
    df = df[~df.index.duplicated()].sort_index()
    df.to_pickle(path)
    return df


def daily_filter(m):
    """Liquid-style daily candles (00:00 UTC) on a roll-adjusted scale: close > 200-day SMA, by UTC date."""
    import strategies2 as s2
    s = s2.load_all([m])[m]
    return (s["close"] > s["sma200"]) & s["sma200"].notna()


def hourly(m1):
    h = m1.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "inst": ["min", "max"]}).dropna()
    h.columns = ["open", "high", "low", "close", "imin", "imax"]
    c = h["close"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std(ddof=0)
    h["mid"], h["up"], h["lo"] = mid, mid + 2 * sd, mid - 2 * sd
    one = (h["imin"].rolling(20).min() == h["imax"].rolling(20).max())
    h["bb_ok"] = one & mid.notna()
    pc = c.shift()
    tr = pd.concat([h["high"], pc], axis=1).max(axis=1) - pd.concat([h["low"], pc], axis=1).min(axis=1)
    h["atr"] = tr.rolling(14).mean()
    return h


def days(m):
    path = os.path.join(CACHE, f"agent_days_{m}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    m1 = load(m)
    h = hourly(m1)
    filt = daily_filter(m)
    et = m1.index
    mod = et.hour * 60 + et.minute
    sess = m1[(mod >= S0) & (mod < 960)]
    out = []
    hidx = h.index
    for d, g in sess.groupby(sess.index.normalize()):
        if d.weekday() >= 5 or len(g) < 370 or g["inst"].nunique() > 1:
            continue
        gm = g.index.hour * 60 + g.index.minute
        # minute arrays 570..959, forward-filled closes
        a = pd.DataFrame(index=np.arange(S0, 960))
        gg = g.set_index(gm)
        for c in ("open", "high", "low", "close", "volume"):
            a[c] = gg[c]
        a["close"] = a["close"].ffill()
        for c in ("open", "high", "low"):
            a[c] = a[c].fillna(a["close"])
        a["volume"] = a["volume"].fillna(0)
        if a["close"].isna().any():
            continue
        tp = (a["high"] + a["low"] + a["close"]) / 3
        cv = a["volume"].cumsum().replace(0, np.nan)
        a["vwap"] = ((tp * a["volume"]).cumsum() / cv).ffill().fillna(a["close"])
        # hourly candles seen at each wake: the one that ended at the wake's hour
        hw = {}
        for w in WAKES:
            start = d + pd.Timedelta(minutes=w - 105)              # (h-1):00
            start = start.tz_localize(None).tz_localize(TZ) if start.tzinfo is None else start
            if start in hidx:
                r = h.loc[start]
                hw[w] = dict(close=r["close"], mid=r["mid"], up=r["up"], lo=r["lo"], ok=bool(r["bb_ok"]),
                             atr=r["atr"], vwap_end=a["vwap"].get(w - 45 - 1, np.nan) if w - 45 > S0 else np.nan)
        prev_utc = (d.tz_localize(None) - pd.Timedelta(days=1))
        f = filt[filt.index <= prev_utc]
        up200 = bool(f.iloc[-1]) if len(f) else False
        orng = a.loc[S0:629]
        out.append(dict(date=d.tz_localize(None), a=a[["open", "high", "low", "close", "vwap"]].to_numpy(),
                        hw=hw, or_h=orng["high"].max(), or_l=orng["low"].min(), up200=up200))
    pd.to_pickle(out, path)
    return out


# ------------------------------------------------------------------ simulation helpers
O, H, L, C, V = range(5)


def px(a, t):
    """Close of the 1-minute bar that ends at minute t (starts at t-1)."""
    return a[t - 1 - S0, C]


def run(a, hw, side, t_fill, entry, stop=None, tp=None, wake_exit=None):
    """Walk 1-minute bars after the fill. stop/tp: resting levels. wake_exit(w) -> True exits at wake w (fill w+5).
    Returns exit price and reason."""
    next_wakes = [w for w in WAKES if w > t_fill - 5]
    for t in range(t_fill, LAST + 5):                    # bar starting at t
        i = t - S0
        o, hi, lo = a[i, O], a[i, H], a[i, L]
        if stop is not None:
            if side > 0 and lo <= stop:
                return min(o, stop), "stop"
            if side < 0 and hi >= stop:
                return max(o, stop), "stop"
        if tp is not None:
            if side > 0 and hi >= tp:
                return max(o, tp), "tp"
            if side < 0 and lo <= tp:
                return min(o, tp), "tp"
        w = t - 4                                        # the bar ending at w+5 is the fill for wake w
        if w in next_wakes:
            if w == LAST:
                return a[i, C], "15:45"
            if wake_exit is not None and wake_exit(w):
                return a[i, C], "wake"
    return a[LAST + 4 - S0, C], "15:45"


def sig_vwap(day, slope, pb=None):
    a, w = day["a"], 10 * 60 + 45
    p, vw, vw0 = px(a, w), a[w - 1 - S0, 4], a[w - 1 - slope - S0, 4]
    side = 0
    if p > vw and p > day["or_h"] and vw > vw0:
        side = 1
    elif p < vw and p < day["or_l"] and vw < vw0:
        side = -1
    if side and pb is not None:
        c = day["hw"].get(w)
        if c is None or not c["ok"] or c["up"] <= c["lo"]:
            return []
        b = (c["close"] - c["lo"]) / (c["up"] - c["lo"])
        if (side > 0 and b < pb) or (side < 0 and b > 1 - pb):
            return []
    if not side:
        return []
    t = w + 5
    e = px(a, t)
    risk = abs(e - a[t - 1 - S0, 4])
    hwd = day["hw"]

    def wx(wk):
        c = hwd.get(wk)
        if c is None or not np.isfinite(c["vwap_end"]):
            return False
        return (c["close"] < c["vwap_end"]) if side > 0 else (c["close"] > c["vwap_end"])
    return [dict(wake=w, side=side, entry=e, risk=risk, go=lambda: run(a, hwd, side, t, e, wake_exit=wx))]


def rule1(day, slope=30):
    return sig_vwap(day, slope)


def rule4(day, slope=30, pb=0.9):
    return sig_vwap(day, slope, pb)


def rule3(day, stop="rest"):
    a, w = day["a"], 10 * 60 + 45
    p = px(a, w)
    side = 1 if p > day["or_h"] else -1 if p < day["or_l"] else 0
    if not side:
        return []
    t = w + 5
    e = px(a, t)
    mid = (day["or_h"] + day["or_l"]) / 2
    if (e - mid) * side <= 0:
        return []
    hwd = day["hw"]
    if stop == "rest":
        go = lambda: run(a, hwd, side, t, e, stop=mid)  # noqa: E731
    else:
        def wx(wk):
            c = hwd.get(wk)
            return c is not None and ((c["close"] < mid) if side > 0 else (c["close"] > mid))
        go = lambda: run(a, hwd, side, t, e, wake_exit=wx)  # noqa: E731
    return [dict(wake=w, side=side, entry=e, risk=abs(e - mid), go=go)]


def rule2(day, tp="rest", k=3.0):
    """Candidate entries at each wake; the portfolio walk takes them in order and skips any while a position is open."""
    if not day["up200"]:
        return []
    a, hwd, out = day["a"], day["hw"], []
    for w in WAKES[:-1]:
        c = hwd.get(w)
        if c is None or not c["ok"] or not np.isfinite(c["atr"]) or c["close"] >= c["lo"]:
            continue
        t = w + 5
        e = px(a, t)
        st = e - k * c["atr"]
        if tp == "rest":
            lvl = c["mid"]
            if lvl <= e:
                continue
            go = (lambda t=t, e=e, st=st, lvl=lvl: run(a, hwd, 1, t, e, stop=st, tp=lvl))
        else:
            def wx(wk, w=w):
                cc = hwd.get(wk)
                return wk > w and cc is not None and np.isfinite(cc["mid"]) and cc["close"] >= cc["mid"]
            go = (lambda t=t, e=e, st=st, wx=wx: run(a, hwd, 1, t, e, stop=st, wake_exit=wx))
        out.append(dict(wake=w, side=1, entry=e, risk=e - st, go=go))
    return out


RULES = {
    "1 VWAP trend hold": (rule1, [dict(slope=s) for s in (30, 60)]),
    "2 Bollinger snap-back": (rule2, [dict(tp=t, k=k) for t in ("rest", "wake") for k in (1.5, 3.0)]),
    "3 First-hour breakout": (rule3, [dict(stop=s) for s in ("rest", "wake")]),
    "4 Band walk": (rule4, [dict(slope=s, pb=p) for s in (30, 60) for p in (1.0, 0.9, 0.8)]),
}


def simulate(fn, kw, data):
    """Portfolio walk over all markets with the daily limits. Returns trades with $ P&L under both cost models."""
    by_date = {}
    for m in MARKETS:
        for day in data[m]:
            by_date.setdefault(day["date"], []).append((m, day))
    rows = []
    for d in sorted(by_date):
        cands = []
        for order, (m, day) in enumerate(sorted(by_date[d], key=lambda x: MARKETS.index(x[0]))):
            for s in fn(day, **kw):
                cands.append((s["wake"], order, m, s))
        cands.sort(key=lambda x: (x[0], x[1]))
        n, real, busy = 0, 0.0, {}
        for wake, _, m, s in cands:
            if n >= 2 or real <= -100:
                break
            if busy.get(m, 0) > wake:                  # one position per market at a time
                continue
            if s["risk"] <= 0:
                continue
            xp, why = s["go"]()
            notional = min(RISK / (s["risk"] / s["entry"]), CAP)
            qty = notional / s["entry"]
            gross = (xp - s["entry"]) * s["side"] * qty
            liq = gross - LIQ_COST * notional
            fut = gross - FUT_COST[m] * qty
            # exit wake (approx) for the per-market busy check: exits fill before the next wake
            busy[m] = 24 * 60
            n += 1
            real += liq
            rows.append(dict(date=d, market=m, wake=wake, side=s["side"], entry=s["entry"], exit=xp, why=why,
                             notional=notional, move=(xp / s["entry"] - 1) * s["side"], liq=liq, fut=fut))
    return pd.DataFrame(rows)


def stats(t, col):
    out = {}
    for p, (a, b) in PERIODS.items():
        x = t[(t["date"] >= a) & (t["date"] < b)][col] if len(t) else pd.Series(dtype=float)
        n = len(x)
        out[p] = dict(n=n, win=(x > 0).mean() * 100 if n else 0, avg=x.mean() if n else 0,
                      se=x.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan, tot=x.sum())
    return out


def fmt(s):
    if s["n"] == 0:
        return "0 trades"
    return f"{s['n']}, {s['win']:.0f}%, {s['avg']:+.1f} ({s['se']:.1f}), ${s['tot']:+,.0f}"


def passes(st):
    h = st["2026"]
    return st["2020-23"]["tot"] > 0 and h["tot"] > 0 and h["n"] > 1 and h["avg"] > h["se"]


def main():
    data = {m: days(m) for m in MARKETS}
    for m in MARKETS:
        print(f"{m}: {len(data[m])} session days, {data[m][0]['date'].date()} -> {data[m][-1]['date'].date()}")
    print("\nCells: trades, win %, average $ per trade (standard error), total $. $50 risk per trade.\n")
    summary = []
    for name, (fn, grid) in RULES.items():
        print(f"## {name}")
        best = None
        for kw in grid:
            t = simulate(fn, kw, data)
            st = stats(t, "liq")
            print(f"  grid {kw}: 2020-23 Liquid {fmt(st['2020-23'])}")
            if best is None or st["2020-23"]["avg"] > best[2]["2020-23"]["avg"]:
                best = (kw, t, st)
        kw, t, st = best
        print(f"  picked on 2020-23: {kw}")
        for col, lab in (("liq", "Liquid 0.10%"), ("fut", "futures")):
            s = stats(t, col)
            print(f"    {lab:13s} | " + " | ".join(f"{p}: {fmt(s[p])}" for p in PERIODS) +
                  ("   PASS" if passes(s) else "   fail"))
        for m in MARKETS:
            s = stats(t[t["market"] == m] if len(t) else t, "liq")
            print(f"    {m} Liquid    | " + " | ".join(f"{p}: {fmt(s[p])}" for p in PERIODS))
        if len(t):
            print(f"    median |move| {t['move'].abs().median()*100:.2f}%, mean notional ${t['notional'].mean():,.0f}, "
                  f"cost share of avg |gross| {LIQ_COST*t['notional'].mean()/((t['liq']-(-LIQ_COST*t['notional'])).abs().mean()):.0%}, "
                  f"exits {t['why'].value_counts().to_dict()}")
        summary.append((name, kw, st, passes(st)))
        print()
    print("## Summary (Liquid cost, settings picked on 2020-23)")
    for name, kw, st, ok in summary:
        print(f"  {name} {kw}: 2020-23 ${st['2020-23']['tot']:+,.0f}, 2024-25 ${st['2024-25']['tot']:+,.0f}, "
              f"2026 ${st['2026']['tot']:+,.0f} (avg {st['2026']['avg']:+.1f}, se {st['2026']['se']:.1f}) -> "
              f"{'PASS' if ok else 'fail'}")


if __name__ == "__main__":
    main()

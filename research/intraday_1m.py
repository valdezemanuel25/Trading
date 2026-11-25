#!/usr/bin/env python3
"""Realistic intraday versions of the live rules, on 1-minute data (research only, 2026-11-25).

Data: Databento ohlcv-1m bought 2026-11-25 (backtest/fetch_1m.py): NQ and CL front month (continuous by volume),
NVDA and GOOGL Nasdaq prints, 2020-01 to 2026-10; ES from the repo's own 1-minute files. Every intraday price is put
on the daily total-return scale of research/strategies2.py: price x (that day's index close / the same contract's
last price of the UTC day), so a roll never shows up as a jump. Same costs and 2-slot / one-per-market portfolio.

1. Trend reclaim as the order agent would trade it (Liquid has no buy-stop): hourly checks at 9:45 ... 15:45 ET on
   weekdays; at the first check where the price is above yesterday's 200-day SMA (market armed: last close at or
   below it), buy at the price `delay` minutes later (your approval time: 0, 30 or 60). If no check crosses but the
   day closes above the SMA, buy at the close (the after-close wake). Exits unchanged (a close below the SMA, from
   the entry day's own close for intraday entries, or 20 trading days).
2. Pre-close decisions for all five markets: decide AND fill at 15:45 ET, for RSI(2) and trend reclaim, entries and
   exits (today's close replaced by the 15:45 price).
3. Resting RSI(2) exit (daily data, all five): from the day after entry, a reduce-only limit sell at the mean of the
   last 4 closes (a close above it = a close above the 5-day SMA), filled if the day's high reaches it.

  python3 research/intraday_1m.py
"""
import io
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
import strategies2 as s2  # noqa: E402
from intraday_entries import one_per_market, rsi2_close, show, tr_close, wilder, TR_M, RSI2_M  # noqa: E402
from zstd_io import read_zst  # noqa: E402

CHECKS = [h * 60 + 45 for h in range(9, 16)]          # 9:45 ... 15:45 ET
GRID = list(range(9 * 60 + 45, 16 * 60 + 46, 15))     # every 15 minutes to 16:45 ET (for approval delays)
PRE = 15 * 60 + 45
CACHE = os.path.join(ROOT, "backtest", ".cache")


def minute_bars(m):
    """UTC-indexed 1-minute closes with an instrument key."""
    if m == "ES":
        from data import load_1m
        x = load_1m()
        return pd.DataFrame(dict(close=x["close"].to_numpy(), inst=x["symbol"].to_numpy()),
                            index=x.index.tz_convert("UTC"))
    x = pd.read_csv(io.BytesIO(read_zst(os.path.join(ROOT, "data", "intraday", f"{m}_1m.csv.zst"))),
                    usecols=["ts_event", "close", "instrument_id"])
    x.index = pd.to_datetime(x["ts_event"], unit="ns", utc=True)
    return pd.DataFrame(dict(close=x["close"].to_numpy() / 1e9, inst=x["instrument_id"].to_numpy()), index=x.index)


def grid_prices(m, daily):
    """Price on the daily index scale at each GRID minute (ET) of each UTC day; NaN where unknown."""
    path = os.path.join(CACHE, f"grid_{m}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    b = minute_bars(m).sort_index()
    utcday = b.index.tz_localize(None).normalize()
    et = b.index.tz_convert("America/New_York")
    etmin = et.hour * 60 + et.minute
    last = b.groupby(utcday).last()                      # last print of each UTC day: close + instrument
    rows = {}
    for d, g in b.groupby(utcday):
        if d not in daily.index or d not in last.index:
            continue
        inst, raw_close = last.loc[d, "inst"], last.loc[d, "close"]
        k = daily.loc[d, "close"] / raw_close
        gm = etmin[utcday == d]
        same = (g["inst"].to_numpy() == inst)
        vals = g["close"].to_numpy()
        out = []
        for t in GRID:
            sel = np.where((gm < t) & same)[0]           # last bar that ended at or before t
            out.append(vals[sel[-1]] * k if len(sel) and gm[sel[-1]] >= t - 30 else np.nan)
        rows[d] = out
    df = pd.DataFrame.from_dict(rows, orient="index", columns=GRID).sort_index()
    df.to_pickle(path)
    return df


def tr_hourly(m, s, gp, delay):
    c, sma = s["close"].to_numpy(), s["sma200"].to_numpy()
    gp = gp.reindex(s.index)
    out, i = [], 201
    while i < len(s):
        if not (c[i - 1] <= sma[i - 1]):
            i += 1
            continue
        lvl, px, how = sma[i - 1], None, None
        for t in CHECKS:
            p = gp.at[s.index[i], t]
            if np.isfinite(p) and p > lvl:
                q = gp.at[s.index[i], t + delay] if t + delay in gp.columns else np.nan
                px, how = (q if np.isfinite(q) else p), "hourly"
                break
        if px is None and c[i] > sma[i]:
            px, how = c[i], "close"
        if px is None:
            i += 1
            continue
        j = i if how == "hourly" else i + 1
        while j < len(s) and c[j] >= sma[j] and not (j - i >= 20):
            j += 1
        j = min(j, len(s) - 1)
        out.append(dict(strat="TR", market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                        ret=c[j] / px - 1, how=how, slip=px / lvl - 1, same_day=(j == i), alt=[s.index[i]]))
        i = j + 1
    return out


def pre_close(m, s, e, rule):
    """Decide and fill at the 15:45 ET price e (today's close replaced by it)."""
    c, ev, n = s["close"].to_numpy(), e.reindex(s.index).to_numpy(), len(s)
    up, dn = wilder(c)

    def sma_e(k, L):
        return (c[k - L + 1:k].sum() + ev[k]) / L

    def rsi_e(k):
        d = ev[k] - c[k - 1]
        u, w = 0.5 * up[k - 1] + 0.5 * max(d, 0), 0.5 * dn[k - 1] + 0.5 * max(-d, 0)
        return 100.0 if w == 0 else 100 - 100 / (1 + u / w)

    out, i = [], 201
    while i < n:
        if not np.isfinite(ev[i]):
            i += 1
            continue
        if rule == "RSI2":
            go = rsi_e(i) < 10 and ev[i] > sma_e(i, 200)
        else:
            go = c[i - 1] <= c[i - 200:i].mean() and ev[i] > sma_e(i, 200)
        if not go:
            i += 1
            continue
        j = i + 1
        while j < n:
            if np.isfinite(ev[j]):
                if rule == "RSI2" and ev[j] > sma_e(j, 5):
                    break
                if rule == "TR" and (ev[j] < sma_e(j, 200) or j - i >= 20):
                    break
            j += 1
        j = min(j, n - 1)
        px = ev[j] if np.isfinite(ev[j]) else c[j]
        out.append(dict(strat=rule, market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                        ret=px / ev[i] - 1, alt=[s.index[i]]))
        i = j + 1
    return out


def rsi2_resting_exit(m, s):
    c, h, o, sma200, rr = (s[k].to_numpy() for k in ("close", "high", "open", "sma200", "rsi2"))
    out, i = [], 200
    while i < len(s):
        if rr[i] < 10 and c[i] > sma200[i]:
            j, px = i + 1, None
            while j < len(s):
                x = c[j - 4:j].mean()
                if h[j] >= x:
                    px = max(x, o[j])
                    break
                j += 1
            j = min(j, len(s) - 1)
            out.append(dict(strat="RSI2", market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                            ret=(px if px is not None else c[j]) / c[i] - 1, alt=[s.index[i]]))
            i = j + 1
        else:
            i += 1
    return out


def main():
    pd.set_option("display.width", 220)
    s2.SER = s2.load_all(s2.LIVE)
    S = s2.SER
    rc = s2.frame([x for m in RSI2_M for x in rsi2_close(m, S[m])])
    trc = s2.frame([x for m in TR_M for x in tr_close(m, S[m])])
    G = {m: grid_prices(m, S[m]) for m in RSI2_M}
    for m in RSI2_M:
        cov = G[m][PRE].reindex(S[m].index).loc["2020-10-01":].notna().mean()
        print(f"{m}: 15:45 ET price known on {100 * cov:.0f}% of days since 2020-10")

    print("=" * 100 + "\n1. TREND RECLAIM, hourly checks + approval delay (fallback: the after-close entry)")
    base = one_per_market(pd.concat([rc, trc], ignore_index=True))
    show("PORTFOLIO live (RSI2 close + TR close)", base)
    show("TR close entry alone (4 markets)", trc)
    for delay in (0, 30, 60):
        t = s2.frame([x for m in TR_M for x in tr_hourly(m, S[m], G[m], delay)])
        hr = t[t.how == "hourly"]
        print(f"\n delay {delay} min: {len(hr)} hourly entries, {len(t) - len(hr)} close entries; hourly fill vs "
              f"level: median {100 * hr.slip.median():+.2f}%, mean {100 * hr.slip.mean():+.2f}%; same-day exits "
              f"(false breakouts) {int(hr.same_day.sum())} (${hr[hr.same_day].usd.sum():+,.0f})")
        show(f"TR hourly, delay {delay} min, alone", t)
        show(f"PORTFOLIO RSI2 close + TR hourly (delay {delay})", one_per_market(pd.concat([rc, t], ignore_index=True)))

    print("\n" + "=" * 100 + "\n2. PRE-CLOSE: decide and fill at 15:45 ET")
    rp = s2.frame([x for m in RSI2_M for x in pre_close(m, S[m], G[m][PRE], "RSI2")])
    tp = s2.frame([x for m in TR_M for x in pre_close(m, S[m], G[m][PRE], "TR")])
    for m in RSI2_M:
        a, b = rc[rc.market == m], rp[rp.market == m]
        same = len(set(a.entry_date) & set(b.entry_date))
        print(f"\n {m}: RSI(2) entry days in common {same} of {len(a)} (close) / {len(b)} (15:45)")
        show("RSI(2) close", a)
        show("RSI(2) 15:45 ET", b)
        if m in TR_M:
            show("TR close", trc[trc.market == m])
            show("TR 15:45 ET", tp[tp.market == m])
    show("\nPORTFOLIO RSI2 15:45 + TR 15:45", one_per_market(pd.concat([rp, tp], ignore_index=True)))
    show("PORTFOLIO RSI2 15:45 + TR close", one_per_market(pd.concat([rp, trc], ignore_index=True)))
    show("PORTFOLIO RSI2 close + TR 15:45", one_per_market(pd.concat([rc, tp], ignore_index=True)))

    print("\n" + "=" * 100 + "\n3. RSI(2) EXIT by resting reduce-only limit at the mean of the last 4 closes (daily data)")
    rx = s2.frame([x for m in RSI2_M for x in rsi2_resting_exit(m, S[m])])
    show("RSI(2) close exit (live)", rc)
    show("RSI(2) resting-limit exit", rx)
    show("PORTFOLIO RSI2 resting exit + TR close", one_per_market(pd.concat([rx, trc], ignore_index=True)))


if __name__ == "__main__":
    main()

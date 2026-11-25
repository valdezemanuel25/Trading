#!/usr/bin/env python3
"""New daily/weekly strategies to run beside the live RSI(2) rule on Liquid (research only, 2026-11-25).

Data: Databento ohlcv-1d in data/daily/ (00:00 UTC days) plus ES rebuilt from the 1-minute files, as in
research/rsi2_markets.py. Every market becomes one daily series:
- futures: front contract by volume, rolling forward only, chained into a total-return index (each day's return is
  measured in YESTERDAY's front contract, so rolls add no jump). Open/high/low are on the same scale.
- stocks: split-adjusted prices (splits detected and snapped to standard sizes), no dividends.
Weekday bars only. Decisions use the daily close and fill at that close (the live check runs 20 minutes after it).
P&L: $5,000 notional per trade, 0.10% round-trip cost, no funding. Portfolio: $10,000 at 1x = 2 slots of $5,000,
shared with the live RSI(2) rule (RSI(2) wins ties), first come first served.

Strategies:
  RSI2   live rule: close > 200-day SMA and RSI(2) < 10, exit on the first close above the 5-day SMA
  1 TR   trend reclaim: first close back above the 200-day SMA; exit on a close below it, or after N days
  2 DIP  RSI(2) < 10 with the close BELOW the 200-day SMA (what "no trend filter" adds to the live rule)
  3 ROT  weekly rotation: last weekday close of each week, hold the top 1-2 markets by mean(63d, 126d return)
         among those above their 200-day SMA; sell when a market drops out
  4 STOP the live RSI(2) rule plus a catastrophe stop k x ATR(14) below entry, checked on daily lows
  5 PAIR log-spread z-score (20 days) mean reversion: BZ vs CL and GOOGL vs NQ, long one / short the other

  python3 research/strategies2.py
"""
import glob
import io
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
from data import CACHE, DATA_DIR, OUTRIGHT  # noqa: E402
from zstd_io import read_zst  # noqa: E402
from rsi2 import rsi  # noqa: E402
from rsi2_markets import load_stock, rank  # noqa: E402

PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "2026 holdout": ("2026-01-01", "2026-10-29")}
END = pd.Timestamp("2026-10-28")
NOTIONAL, COST = 5000.0, 0.001
LIVE = ["ES", "NQ", "NVDA", "GOOGL", "CL"]                  # SP500, XYZ100, NVDA, GOOGL, CL on Liquid
WATCH = ["BTC", "BZ", "ETH", "AAPL", "MSFT", "META"]
INDEXF = ["RTY", "YM"]                                     # extra index futures (not on Liquid; context only)
FUT = {"ES", "NQ", "RTY", "YM", "CL", "BZ", "BTC", "ETH"}
NAMES = {"ES": "S&P 500", "NQ": "Nasdaq 100", "CL": "WTI", "BZ": "Brent", "BTC": "BTC", "ETH": "ETH", "RTY": "Russell",
         "YM": "Dow"}


# ------------------------------------------------------------------ data
def contracts(root):
    """Per-contract daily OHLCV (UTC days), outrights only."""
    path = os.path.join(CACHE, f"contracts_{root}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    if root == "ES":
        parts = []
        for fp in sorted(glob.glob(os.path.join(DATA_DIR, "glbx-mdp3-*.ohlcv-1m.csv.zst"))):
            x = pd.read_csv(io.BytesIO(read_zst(fp)), usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"])
            x = x[x["symbol"].str.match(OUTRIGHT)]
            x["date"] = pd.to_datetime(x["ts_event"]).dt.tz_localize(None).dt.normalize()
            parts.append(x.sort_values("ts_event").groupby(["date", "symbol"]).agg(
                open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum")).reset_index())
        df = pd.concat(parts)
    else:
        x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{root}.csv"))
        x = x[x["symbol"].str.fullmatch(rf"{root}[FGHJKMNQUVXZ]\d{{1,2}}")]
        x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
        for c in ("open", "high", "low", "close"):
            x[c] = x[c] / 1e9
        df = x[["date", "symbol", "open", "high", "low", "close", "volume"]]
    df = df[df["date"].dt.dayofweek < 5]
    os.makedirs(CACHE, exist_ok=True)
    df.to_pickle(path)
    return df


def future_series(root):
    df = contracts(root)
    vol = df.groupby(["date", "symbol"])["volume"].sum().reset_index()
    vol["rank"] = [rank(s, root, d.year) for s, d in zip(vol["symbol"], vol["date"])]
    front, cur = {}, -1
    for d, g in vol.groupby("date"):
        g = g[g["rank"] >= cur].sort_values("volume", ascending=False)
        if not g.empty:
            front[d], cur = g.iloc[0]["symbol"], g.iloc[0]["rank"]
    px = df.set_index(["date", "symbol"])[["open", "high", "low", "close"]]
    px = px[~px.index.duplicated()]
    days = sorted(front)
    idx = np.empty(len(days))
    o = np.empty(len(days)); h = np.empty(len(days)); lo = np.empty(len(days))
    idx[0] = 100.0
    o[0] = h[0] = lo[0] = 100.0
    bad = 0
    for i in range(1, len(days)):
        d, prev = days[i], days[i - 1]
        f = front[prev]
        key, pkey = (d, f), (prev, f)
        if key not in px.index:                      # yesterday's front stopped trading: use today's front
            f = front[d]
            key, pkey = (d, f), (prev, f)
        p0 = px["close"].get(pkey)
        row = px.loc[key] if key in px.index else None
        if row is None or p0 is None or not np.isfinite(p0) or p0 <= 0 or row["close"] <= 0:
            idx[i], o[i], h[i], lo[i] = idx[i - 1], idx[i - 1], idx[i - 1], idx[i - 1]
            bad += 1
            continue
        k = idx[i - 1] / p0
        idx[i], o[i], h[i], lo[i] = row["close"] * k, row["open"] * k, row["high"] * k, row["low"] * k
    s = pd.DataFrame(dict(open=o, high=h, low=lo, close=idx), index=pd.DatetimeIndex(days))
    s.attrs["bad_days"] = bad
    return s


def stock_series(sym):
    dd, _ = load_stock(sym)                          # split-adjusted closes
    x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{sym}.csv"))
    x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
    x = x[x["date"].dt.dayofweek < 5].set_index("date").sort_index()
    raw = x["close"] / 1e9
    f = dd["front"]["close"] / raw                   # split factor per day
    return pd.DataFrame({c: x[c] / 1e9 * f for c in ("open", "high", "low", "close")})


def load_all(names):
    out = {}
    for n in names:
        s = future_series(n) if n in FUT else stock_series(n)
        s = s[s.index <= END]
        c = s["close"]
        s["sma200"], s["sma5"], s["rsi2"] = c.rolling(200).mean(), c.rolling(5).mean(), rsi(c)
        pc = c.shift()
        tr = pd.concat([s["high"], pc], axis=1).max(axis=1) - pd.concat([s["low"], pc], axis=1).min(axis=1)
        s["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
        out[n] = s
    return out


# ------------------------------------------------------------------ strategies -> trade lists
def trade(strat, m, s, i, j, exit_px=None, alt=None):
    entry, ex = s["close"].iloc[i], (s["close"].iloc[j] if exit_px is None else exit_px)
    return dict(strat=strat, market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                ret=ex / entry - 1, above200=bool(s["close"].iloc[i] > s["sma200"].iloc[i]), alt=alt or [s.index[i]])


def rsi2_rule(m, s, trend="above", stop_k=None, strat="RSI2"):
    c, sma200, sma5, r, lo, op, atr = (s[k].to_numpy() for k in ("close", "sma200", "sma5", "rsi2", "low", "open", "atr"))
    out, i = [], 200
    while i < len(s):
        ok = r[i] < 10 and (trend == "any" or (trend == "above" and c[i] > sma200[i]) or (trend == "below" and c[i] <= sma200[i]))
        if not ok:
            i += 1
            continue
        stop = c[i] - stop_k * atr[i] if stop_k else None
        j, px = i + 1, None
        while j < len(s):
            if stop is not None and lo[j] <= stop:
                px = min(stop, op[j])
                break
            if c[j] > sma5[j]:
                break
            j += 1
        j = min(j, len(s) - 1)
        out.append(trade(strat, m, s, i, j, px))
        i = j + 1
    return out


def trend_reclaim(m, s, max_days=None, strat="TR"):
    c, sma = s["close"].to_numpy(), s["sma200"].to_numpy()
    out, i = [], 201
    while i < len(s):
        if c[i] > sma[i] and c[i - 1] <= sma[i - 1]:
            j = i + 1
            while j < len(s) and c[j] >= sma[j] and not (max_days and j - i >= max_days):
                j += 1
            j = min(j, len(s) - 1)
            out.append(trade(strat, m, s, i, j))
            i = j + 1
        else:
            i += 1
    return out


def rotation(series, top_n, strat="ROT"):
    """Weekly: last weekday close of each ISO week. Score = mean of 63- and 126-trading-day returns."""
    closes = pd.DataFrame({m: s["close"] for m, s in series.items()})
    sma = pd.DataFrame({m: s["sma200"] for m, s in series.items()})
    r63 = pd.DataFrame({m: s["close"] / s["close"].shift(63) - 1 for m, s in series.items()})
    r126 = pd.DataFrame({m: s["close"] / s["close"].shift(126) - 1 for m, s in series.items()})
    wk = closes.index.to_series().groupby(closes.index.to_period("W")).max().values
    holdings, spans, out = {}, [], []
    for d in wk:
        c, sm = closes.loc[:d].ffill().iloc[-1], sma.loc[:d].ffill().iloc[-1]
        sc = ((r63.loc[:d].ffill().iloc[-1] + r126.loc[:d].ffill().iloc[-1]) / 2)
        live = sc[(c > sm) & sc.notna() & closes.loc[:d].notna().any()]
        top = list(live.sort_values(ascending=False).index[:top_n])
        for m in list(holdings):
            if m not in top:
                spans.append((m, holdings.pop(m), d))
        for m in top:
            if m not in holdings:
                holdings[m] = [d]
            else:
                holdings[m].append(d)
    for m, ds in holdings.items():
        spans.append((m, ds, pd.Timestamp(wk[-1])))
    for m, ds, end in spans:
        s = series[m]
        i, j = s.index.get_indexer([ds[0]], method="pad")[0], s.index.get_indexer([end], method="pad")[0]
        if j <= i:
            continue
        t = trade(strat, m, s, i, j, alt=[pd.Timestamp(x) for x in ds])   # can still be entered at a later week
        out.append(t)
    return out


def pairs(a, b, sa, sb, z_in=2.0, look=20, max_days=20, strat="PAIR"):
    """Long the cheap leg, short the rich leg ($5,000 each), exit when z crosses 0 or after max_days."""
    df = pd.DataFrame(dict(a=sa["close"], b=sb["close"])).dropna()
    ls = np.log(df.a / df.b)
    z = ((ls - ls.rolling(look).mean()) / ls.rolling(look).std()).to_numpy()
    A, B, out, i = df.a.to_numpy(), df.b.to_numpy(), [], look
    while i < len(df):
        if abs(z[i]) >= z_in:
            side = -1 if z[i] > 0 else 1          # +1: long a / short b
            j = i + 1
            while j < len(df) and not (np.sign(z[j]) != np.sign(z[i]) or j - i >= max_days):
                j += 1
            j = min(j, len(df) - 1)
            ra, rb = A[j] / A[i] - 1, B[j] / B[i] - 1
            out.append(dict(strat=strat, market=f"{a}/{b}", entry_date=df.index[i], exit_date=df.index[j], days=j - i,
                            ret=(side * ra - side * rb), legs=2, above200=None, alt=[df.index[i]]))
            i = j + 1
        else:
            i += 1
    return out


# ------------------------------------------------------------------ stats and portfolio
def frame(trades):
    t = pd.DataFrame(trades)
    if t.empty:
        return t
    legs = t["legs"].fillna(1) if "legs" in t else 1
    t["usd"] = NOTIONAL * t["ret"] - NOTIONAL * COST * legs
    return t


def per(t, p):
    a, b = PERIODS[p]
    return t[(t.entry_date >= a) & (t.entry_date < b)].sort_values("exit_date")


def years(p):
    a, b = PERIODS[p]
    return (min(pd.Timestamp(b), END) - max(pd.Timestamp(a), pd.Timestamp("2020-01-01"))).days / 365.25


def stats(x, yrs):
    if x.empty:
        return dict(tr=0, per_yr=0, win=np.nan, net=0.0, avg=np.nan, worst=np.nan, dd=0.0)
    eq = x.usd.cumsum()
    return dict(tr=len(x), per_yr=len(x) / yrs, win=100 * (x.usd > 0).mean(), net=x.usd.sum(), avg=x.usd.mean(),
                worst=x.usd.min(), dd=(eq - eq.cummax()).min())


def fmt(st):
    if st["tr"] == 0:
        return "0 tr"
    return (f"{st['tr']:3d} tr ({st['per_yr']:4.1f}/yr) win {st['win']:3.0f}% net ${st['net']:+7,.0f} "
            f"avg ${st['avg']:+6.1f} worst ${st['worst']:+6,.0f} DD ${st['dd']:+7,.0f}")


def table(title, t, markets=None):
    print(f"\n--- {title} ---")
    groups = [(m, t[t.market == m]) for m in (markets or sorted(t.market.unique()))] + [("ALL", t)]
    for m, x in groups:
        print(f"  {m:10s} " + " | ".join(f"{p}: {fmt(stats(per(x, p), years(p)))}" for p in PERIODS))


def picked_on_2020_23(t):
    return [m for m in sorted(t.market.unique()) if per(t[t.market == m], "2020-23").usd.sum() > 0]


def portfolio(trades, slots=2, priority=("RSI2",)):
    """Shared slots, entries in date order; on the same day, `priority` strategies first, then by market name.
    A trade with `alt` dates (rotation) can be entered at its first alt date with a free slot."""
    cands = []
    for k, t in enumerate(trades.to_dict("records")):
        for a in t["alt"]:
            if a < t["exit_date"]:
                cands.append((a, 0 if t["strat"] in priority else 1, t["market"], k))
    cands.sort()
    open_until, taken, done = [], [], set()
    for a, _, _, k in cands:
        if k in done:
            continue
        t = trades.iloc[k]
        need = int(t.get("legs", 1) if pd.notna(t.get("legs", 1)) else 1)
        open_until = [d for d in open_until if d > a]
        if len(open_until) + need > slots:
            continue
        done.add(k)
        open_until += [t["exit_date"]] * need
        r = dict(t)
        if a != t["entry_date"]:                       # late entry into a rotation span
            s = SER[t["market"]]
            r["entry_date"], r["ret"] = a, s["close"].asof(t["exit_date"]) / s["close"].asof(a) - 1
        r["usd"] = NOTIONAL * r["ret"] - NOTIONAL * COST * need
        taken.append(r)
    return pd.DataFrame(taken)


def portfolio_report(label, base, extra):
    both = pd.concat([base, extra], ignore_index=True)
    pf, alone = portfolio(both), portfolio(base)
    print(f"\n  PORTFOLIO 2 slots x $5,000: RSI2 live + {label}")
    for p in PERIODS:
        a, b = stats(per(alone, p), years(p)), stats(per(pf, p), years(p))
        newx = per(pf[pf.strat != "RSI2"], p)
        skipped = len(per(extra, p)) - len(newx)
        print(f"    {p:13s} RSI2 alone: net ${a['net']:+6,.0f} DD ${a['dd']:+6,.0f} ({a['tr']} tr) | with {label}: "
              f"net ${b['net']:+6,.0f} DD ${b['dd']:+6,.0f} worst ${b['worst']:+5,.0f} ({b['tr']} tr, {len(newx)} new, "
              f"{skipped} new skipped for no slot)")
    return pf


def standing_aside(base, extra):
    """How many of `extra`'s entries happen on a day the live RSI(2) rule holds nothing."""
    days = set()
    for t in base.itertuples():
        days.update(pd.bdate_range(t.entry_date, t.exit_date - pd.Timedelta(days=1)))
    x = extra[extra.entry_date >= "2020-01-01"]
    return int(sum(d not in days for d in x.entry_date)), len(x)


# ------------------------------------------------------------------ main
def main():
    global SER
    pd.set_option("display.width", 250)
    SER = load_all(LIVE + WATCH + INDEXF)
    for m in FUT:
        if SER[m].attrs.get("bad_days"):
            print(f"note: {m} has {SER[m].attrs['bad_days']} day(s) with no usable return (e.g. CL April 2020), held flat")
    base = frame([t for m in LIVE for t in rsi2_rule(m, SER[m])])
    print("=" * 110)
    table("RSI2 live rule (baseline, this engine)", base, LIVE)

    # 1. trend reclaim
    print("\n" + "=" * 110 + "\n1. TREND RECLAIM: first close back above the 200-day SMA; exit on a close below it or after N days")
    universe = LIVE + WATCH + INDEXF
    res1 = {}
    for n in (None, 10, 20):
        lab = f"TR exit {'below SMA only' if n is None else f'or {n} days'}"
        t = frame([x for m in universe for x in trend_reclaim(m, SER[m], n, strat=f"TR{n or ''}")])
        res1[n] = t
        table(lab, t, universe)
        pick = [m for m in picked_on_2020_23(t) if m in LIVE + WATCH]
        tp = t[t.market.isin(pick)]
        print(f"  picked on 2020-23 (Liquid markets with net > 0): {pick}")
        for p in PERIODS:
            print(f"    picked set {p:13s} {fmt(stats(per(tp, p), years(p)))}")
        sa, tot = standing_aside(base, tp)
        print(f"    picked-set entries while RSI2 holds nothing: {sa} of {tot}")
        portfolio_report(lab + " (picked)", base, tp)

    # 2. dips below the 200-day
    print("\n" + "=" * 110 + "\n2. RSI(2) < 10 BELOW the 200-day SMA (what variant B adds), live five markets")
    dip = frame([t for m in LIVE for t in rsi2_rule(m, SER[m], trend="below", strat="DIP")])
    table("DIP: RSI(2) < 10, close <= 200-day SMA, exit close > 5-day SMA", dip, LIVE)
    pick = picked_on_2020_23(dip)
    print(f"  picked on 2020-23: {pick}")
    for p in PERIODS:
        print(f"    picked set {p:13s} {fmt(stats(per(dip[dip.market.isin(pick)], p), years(p)))}")
    sa, tot = standing_aside(base, dip[dip.market.isin(pick)])
    print(f"    picked-set entries while RSI2 holds nothing: {sa} of {tot}")
    portfolio_report("DIP (picked)", base, dip[dip.market.isin(pick)])
    varb = frame([t for m in LIVE for t in rsi2_rule(m, SER[m], trend="any", strat="RSI2")])
    print("\n  Variant B as ONE rule (no filter at all), portfolio of the live five, 2 slots:")
    pb = portfolio(varb)
    for p in PERIODS:
        print(f"    {p:13s} {fmt(stats(per(pb, p), years(p)))}")

    # 3. weekly rotation
    print("\n" + "=" * 110 + "\n3. WEEKLY MOMENTUM ROTATION among the live five + watch list (only markets above their 200-day SMA)")
    rot_univ = {m: SER[m] for m in LIVE + WATCH}
    for n in (1, 2):
        t = frame(rotation(rot_univ, n, strat=f"ROT{n}"))
        table(f"ROT top {n} (standalone, every pick taken)", t, LIVE + WATCH)
        print(f"    avg hold {t.days.mean():.0f} trading days")
        sa, tot = standing_aside(base, t)
        print(f"    entries while RSI2 holds nothing: {sa} of {tot}")
        portfolio_report(f"ROT{n}", base, t)

    # 4. catastrophe stop
    print("\n" + "=" * 110 + "\n4. CATASTROPHE STOP on the live RSI(2) rule (k x ATR(14) below entry, daily lows)")
    for k in (2, 3):
        t = frame([x for m in LIVE for x in rsi2_rule(m, SER[m], stop_k=k)])
        table(f"RSI2 + {k}x ATR stop", t, LIVE)
        print(f"    stopped out: {int((t.ret < 0).sum())} losers in all; worst trade ${t.usd.min():+,.0f} vs ${base.usd.min():+,.0f} without")
        pf = portfolio(t)
        for p in PERIODS:
            print(f"    portfolio {p:13s} {fmt(stats(per(pf, p), years(p)))}")
    pf0 = portfolio(base)
    for p in PERIODS:
        print(f"    no stop   {p:13s} {fmt(stats(per(pf0, p), years(p)))}")

    # 5. pairs
    print("\n" + "=" * 110 + "\n5. SPREAD MEAN REVERSION (long cheap / short rich, $5,000 a leg = both slots), z 20d >= 2, exit z through 0 or 20 days")
    for a, b in (("BZ", "CL"), ("GOOGL", "NQ")):
        t = frame(pairs(a, b, SER[a], SER[b]))
        table(f"{a} vs {b}", t)
        portfolio_report(f"PAIR {a}/{b}", base, t)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""RSI(2) pullback: rule variants and the 200-day filter definition, on ES, NQ, RTY and YM (00:00 UTC daily closes).

Same data, roll handling and rules as research/multi.py (long only: close > 200-day SMA and RSI(2) < 10, sell on the
first close above the 5-day SMA, each trade priced in its entry contract). Variants:

  a. entry threshold RSI(2) < 10 vs < 30
  b. time stop: also exit at the close N trading days after entry (N = 5, 7, 10) if the 5-day-SMA exit hasn't fired
  c. sizing: flat $5,000 notional vs ATR(14)-scaled notional (same average notional as flat in 2020-23)
  filter definition (signal accuracy): 200-weekday SMA (backtest) vs Liquid's sma200 = mean of the last 200 CALENDAR
     daily candles (weekend candles included, filled here with Friday's close) vs weekday closes inside that window.

A change is accepted only if it helps in 2020-23 AND holds on the 2026 holdout (2024-25 shown for context).

  python3 research/rsi2_variants.py            # all tables
  python3 research/rsi2_variants.py --csv      # also write research/rsi2_variant_trades.csv
"""
import glob
import io
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
sys.path.insert(0, HERE)
from data import CACHE, DATA_DIR, OUTRIGHT  # noqa: E402
from zstd_io import read_zst  # noqa: E402
from multi import SPEC, front_from_bars  # noqa: E402
from rsi2 import adjusted, rsi  # noqa: E402

PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "2026 holdout": ("2026-01-01", "2026-11-01")}
# years each period can actually trade (first signal needs 200 days of history; data ends 2026-10-28)
YEARS = {"2020-23": (pd.Timestamp("2024-01-01") - pd.Timestamp("2020-10-16")).days / 365.25, "2024-25": 2.0,
         "2026 holdout": (pd.Timestamp("2026-10-28") - pd.Timestamp("2026-01-01")).days / 365.25}
NOTIONAL, LIQ_COST = 5000.0, 0.001   # flat size per trade on Liquid; assumed round-trip cost 0.10% of notional


# ---------------------------------------------------------------- data (closes plus highs/lows for ATR)
def load_hl(root):
    path = os.path.join(CACHE, f"utc_daily_hl_{root}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    if root == "ES":
        parts = []
        for fp in sorted(glob.glob(os.path.join(DATA_DIR, "glbx-mdp3-*.ohlcv-1m.csv.zst"))):
            x = pd.read_csv(io.BytesIO(read_zst(fp)), usecols=["ts_event", "high", "low", "close", "volume", "symbol"])
            x = x[x["symbol"].str.match(OUTRIGHT)]
            x["date"] = pd.to_datetime(x["ts_event"]).dt.tz_localize(None).dt.normalize()
            parts.append(x.sort_values("ts_event").groupby(["date", "symbol"]).agg(
                close=("close", "last"), high=("high", "max"), low=("low", "min"), volume=("volume", "sum")).reset_index())
        df = pd.concat(parts)
    else:
        x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{root}.csv"))
        x = x[x["symbol"].str.fullmatch(rf"{root}[HMUZ]\d")]
        x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
        for c in ("close", "high", "low"):
            x[c] = x[c] / 1e9
        df = x[["date", "symbol", "close", "high", "low", "volume"]]
    df = df[df["date"].dt.dayofweek < 5]
    dd = front_from_bars(df[["date", "symbol", "close", "volume"]])
    hl = df.set_index(["date", "symbol"])[["high", "low"]]
    hl = hl[~hl.index.duplicated()]
    fr = dd["front"]
    fr["high"] = [hl["high"].get((d, s)) for d, s in zip(fr.index, fr["symbol"])]
    fr["low"] = [hl["low"].get((d, s)) for d, s in zip(fr.index, fr["symbol"])]
    os.makedirs(CACHE, exist_ok=True)
    pd.to_pickle(dd, path)
    return dd


def indicators(dd):
    front, closes = dd["front"], dd["closes"]
    a = adjusted(front, closes)
    off = a - front["close"].astype(float)
    h, l = front["high"].astype(float) + off, front["low"].astype(float) + off
    pc = a.shift()
    tr = pd.concat([h, pc], axis=1).max(axis=1) - pd.concat([l, pc], axis=1).min(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    # Liquid-style 200 SMA: 200 calendar days, weekends carry Friday's close
    cal = a.reindex(pd.date_range(a.index[0], a.index[-1], freq="D")).ffill()
    sma_cal = cal.rolling(200).mean().reindex(a.index)
    in_win = a.rolling("200D").mean()           # weekday closes inside the last 200 calendar days (~143)
    in_win[a.index < a.index[0] + pd.Timedelta(days=199)] = np.nan
    return pd.DataFrame(dict(a=a, rsi=rsi(a), sma5=a.rolling(5).mean(), wd200=a.rolling(200).mean(),
                             cal200=sma_cal, win200=in_win, atr=atr))


# ---------------------------------------------------------------- backtest
def backtest(dd, ind, rsi_max=10, max_days=None, filt="wd200"):
    front, closes = dd["front"], dd["closes"]
    a, r, s5, f, atr = ind["a"], ind["rsi"], ind["sma5"], ind[filt], ind["atr"]
    days, trades, i = a.index, [], 200
    while i < len(days):
        if r.iloc[i] < rsi_max and a.iloc[i] > f.iloc[i]:
            sym, entry_d = front["symbol"].iloc[i], days[i]
            entry = closes[(entry_d, sym)]
            j, why = i + 1, "sma5"
            while j < len(days) and not a.iloc[j] > s5.iloc[j]:
                if max_days and j - i >= max_days:
                    why = "time"
                    break
                j += 1
            j = min(j, len(days) - 1)
            k = j
            while (days[k], sym) not in closes.index and k > i:
                k -= 1
            ex = closes[(days[k], sym)]
            trades.append(dict(entry_date=entry_d, exit_date=days[k], symbol=sym, entry=entry, exit=ex, days=k - i,
                               pts=ex - entry, atr_pct=atr.iloc[i] / a.iloc[i], exit_by=why))
            i = j + 1
        else:
            i += 1
    return pd.DataFrame(trades)


def run(rsi_max=10, max_days=None, filt="wd200", markets=SPEC):
    out = []
    for root in markets:
        dd = load_hl(root)
        t = backtest(dd, indicators(dd), rsi_max, max_days, filt)
        sp = SPEC[root]
        t["root"] = root
        t["micro"] = t["pts"] * sp["mpoint"] - sp["mcost"]
        t["ret"] = t["pts"] / t["entry"]
        out.append(t)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------- stats
def per(t, name):
    a, b = PERIODS[name]
    return t[(t.entry_date >= a) & (t.entry_date < b)].sort_values("exit_date")


def summary(x, col, years):
    if x.empty:
        return dict(tr=0)
    eq = x[col].cumsum()
    loss = -x.loc[x[col] < 0, col].sum()
    return dict(tr=len(x), per_yr=len(x) / years, win=100 * (x[col] > 0).mean(), net=x[col].sum(),
                avg=x[col].mean(), worst=x[col].min(), dd=(eq - eq.cummax()).min(),
                pf=x.loc[x[col] > 0, col].sum() / loss if loss else np.inf, hold=x.days.mean())


def fmt(s, money=True):
    if s.get("tr", 0) == 0:
        return "0 trades"
    m = (lambda v: f"${v:+,.0f}") if money else (lambda v: f"{v:+.2f}")
    return (f"{s['tr']} tr ({s['per_yr']:.0f}/yr), win {s['win']:.0f}%, net {m(s['net'])}, avg {m(s['avg'])}, "
            f"worst {m(s['worst'])}, maxDD {m(s['dd'])}, PF {s['pf']:.2f}, hold {s['hold']:.1f}d")


def table(label, t, col="micro", by_market=False):
    print(f"\n--- {label} ---")
    groups = [("portfolio", t)] + ([(r, t[t.root == r]) for r in SPEC] if by_market else [])
    for g, x in groups:
        for p in PERIODS:
            print(f"  {g:10s} {p:13s} {fmt(summary(per(x, p), col, YEARS[p]))}")


def main():
    pd.set_option("display.width", 200)
    base = run()

    print("=" * 100)
    print("BASELINE: RSI(2) < 10, 5-day SMA exit, 200-weekday SMA filter; $ = 1 micro each, net of costs")
    table("baseline", base, by_market=True)

    print("\n" + "=" * 100)
    print("2a. ENTRY THRESHOLD")
    r30 = run(rsi_max=30)
    table("RSI(2) < 30", r30, by_market=True)

    print("\n" + "=" * 100)
    print("2b. TIME STOP (exit at the close N trading days after entry if the 5-day-SMA exit hasn't fired)")
    for n in (5, 7, 10):
        t = run(max_days=n)
        table(f"time stop {n} days ({(t.exit_by == 'time').sum()} of {len(t)} trades exit on time)", t)
    print("\n  Baseline trades held longer than 5/7/10 days, all periods:",
          ", ".join(f"{n}d: {(base.days > n).sum()}" for n in (5, 7, 10)))
    worst = base.sort_values("micro").head(5)[["root", "entry_date", "exit_date", "days", "pts", "micro"]]
    print("  Five worst baseline trades (1 micro):\n" + worst.to_string(index=False))

    print("\n" + "=" * 100)
    print(f"2c. SIZING on Liquid: ${NOTIONAL:,.0f} flat vs ATR(14)-scaled notional, cost {LIQ_COST:.2%} round trip")
    calib = per(base, "2020-23")
    k = NOTIONAL / (1 / calib.atr_pct).mean()      # average ATR-sized notional in 2020-23 = $5,000
    base["flat"] = NOTIONAL * base.ret - NOTIONAL * LIQ_COST
    base["size_atr"] = k / base.atr_pct
    base["atr_sized"] = base.size_atr * base.ret - base.size_atr * LIQ_COST
    base["size_cap"] = base.size_atr.clip(upper=2 * NOTIONAL)
    base["atr_capped"] = base.size_cap * base.ret - base.size_cap * LIQ_COST
    print(f"  ATR sizing: notional = {k:,.1f} / (ATR14/close); in 2020-23 it ranged "
          f"${calib.atr_pct.rdiv(k).min():,.0f}-${calib.atr_pct.rdiv(k).max():,.0f}")
    for col, lab in (("flat", "flat $5,000"), ("atr_sized", "ATR-sized"), ("atr_capped", "ATR-sized, capped at $10,000")):
        print(f"\n  {lab}")
        for p in PERIODS:
            x = per(base, p)
            s = summary(x, col, YEARS[p])
            sharpe = x[col].mean() / x[col].std() * np.sqrt(len(x) / YEARS[p]) if len(x) > 2 else np.nan
            print(f"    {p:13s} {fmt(s)}, net/maxDD {s['net'] / max(-s['dd'], 1):.1f}, "
                  f"trade Sharpe {sharpe:.2f}, avg size ${x['size_atr' if col != 'flat' else 'ret'].mean() if col != 'flat' else NOTIONAL:,.0f}")
        for r in SPEC:
            x = base[base.root == r]
            print(f"    {r:4s} all periods: net ${x[col].sum():+,.0f}, worst ${x[col].min():+,.0f}")

    print("\n" + "=" * 100)
    print("3. FILTER DEFINITION: 200-weekday SMA vs Liquid's 200-calendar-day SMA vs weekdays inside that window")
    for root in ("ES", "NQ", "RTY", "YM"):
        ind = indicators(load_hl(root)).dropna(subset=["wd200", "cal200", "win200"])
        ind = ind[ind.index >= "2021-01-01"]
        above_wd, above_cal, above_win = ind.a > ind.wd200, ind.a > ind.cal200, ind.a > ind.win200
        sig = ind.rsi < 10
        print(f"  {root:3s} days {len(ind)}: filter differs on {100 * (above_wd != above_cal).mean():.1f}% of days "
              f"(cal), {100 * (above_wd != above_win).mean():.1f}% (in-window weekdays), cal vs in-window "
              f"{100 * (above_cal != above_win).mean():.2f}%; RSI(2)<10 days {sig.sum()}, of which filter differs on "
              f"{(sig & (above_wd != above_cal)).sum()}; Liquid-style SMA vs 200-weekday SMA: median gap "
              f"{100 * ((ind.cal200 / ind.wd200) - 1).abs().median():.2f}%")
    for filt, lab in (("wd200", "200 weekdays (backtest)"), ("cal200", "Liquid sma200 (200 calendar days)"),
                      ("win200", "weekdays in last 200 calendar days")):
        table(f"filter = {lab}", run(filt=filt))

    if "--csv" in sys.argv:
        base.to_csv(os.path.join(HERE, "rsi2_variant_trades.csv"), index=False)


if __name__ == "__main__":
    main()

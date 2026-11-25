#!/usr/bin/env python3
"""RSI(2) pullback, exact live rules, on the extra markets Liquid offers (research/rsi2_variants.py has the rules).

Data: Databento ohlcv-1d (00:00 UTC days) in data/daily/, fetched with backtest/fetch_daily.py:
- futures GC (gold), SI (silver), CL (WTI), BZ (Brent), BTC and ETH (CME): front contract per day by volume, rolling
  forward only; indicators on roll-adjusted closes; each trade priced in its entry contract (as research/multi.py).
- Nasdaq stocks AAPL NVDA MSFT TSLA AMZN GOOGL META (XNAS.ITCH prints): splits removed by back-adjusting at the
  detected split day; dividends ignored.
- ES and NQ (the two live markets) from the same pipeline for reference.
Weekday closes only (CME crypto futures and stocks don't trade weekends; Liquid's perps do).

P&L is in Liquid terms: $5,000 notional per trade at 1x, 0.10% round-trip cost assumed. Perp funding is NOT
included (it can matter for crypto longs).

  python3 research/rsi2_markets.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backtest"))
import rsi2  # noqa: E402
import rsi2_variants as rv  # noqa: E402

MONTHS = {c: i + 1 for i, c in enumerate("FGHJKMNQUVXZ")}
FUTURES = {"GC": "xyz:GOLD", "SI": "xyz:SILVER", "CL": "xyz:CL", "BZ": "xyz:BRENTOIL", "BTC": "BTC", "ETH": "ETH"}
STOCKS = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL", "META"]
NOTIONAL, COST = 5000.0, 0.001
PERIODS = rv.PERIODS
END = pd.Timestamp("2026-10-28")


def rank(sym, root, year):
    code = sym[len(root):]
    m, y = MONTHS[code[0]], int(code[1:])
    if len(code[1:]) == 1:
        y = year - (year % 10) + y
        if y < year - 1:
            y += 10
    else:
        y += 2000
    return y * 100 + m


def load_future(root):
    x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{root}.csv"))
    x = x[x["symbol"].str.fullmatch(rf"{root}[FGHJKMNQUVXZ]\d{{1,2}}")]
    x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
    x["close"] = x["close"] / 1e9
    x = x[x["date"].dt.dayofweek < 5]
    vol = x.groupby(["date", "symbol"])["volume"].sum().reset_index()
    vol["rank"] = [rank(s, root, d.year) for s, d in zip(vol["symbol"], vol["date"])]
    front, cur = {}, -1
    for d, g in vol.groupby("date"):
        g = g[g["rank"] >= cur].sort_values("volume", ascending=False)
        if g.empty:
            continue
        front[d], cur = g.iloc[0]["symbol"], g.iloc[0]["rank"]
    closes = x.set_index(["date", "symbol"])["close"]
    closes = closes[~closes.index.duplicated()]
    fr = pd.DataFrame({"symbol": pd.Series(front)})
    fr["close"] = [closes.get((d, s)) for d, s in zip(fr.index, fr["symbol"])]
    return dict(front=fr, closes=closes)


def load_stock(sym):
    x = pd.read_csv(os.path.join(ROOT, "data", "daily", f"{sym}.csv"))
    x["date"] = pd.to_datetime(x["ts_event"], unit="ns").dt.normalize()
    x = x[x["date"].dt.dayofweek < 5].set_index("date").sort_index()
    c = x["close"] / 1e9
    ratio = c / c.shift()
    factor = pd.Series(1.0, index=c.index)
    splits = []
    for d, r in ratio.items():
        if r < 0.6:
            n = min((2, 3, 4, 5, 8, 10, 15, 20, 25, 30), key=lambda k: abs(1 / r - k) / k)   # standard split sizes
            if abs(1 / r - n) / n < 0.1:
                factor[factor.index < d] *= 1 / n
                splits.append(f"{d.date()} {n}:1")
    adj = c * factor
    fr = pd.DataFrame({"symbol": sym, "close": adj})
    closes = pd.Series(adj.values, index=pd.MultiIndex.from_arrays([adj.index, [sym] * len(adj)]))
    return dict(front=fr, closes=closes), splits


def trades_for(name, dd):
    t = rsi2.backtest(dd, rsi_max=10)
    t["market"] = name
    t["ret"] = t["pts"] / t["entry"]
    t["usd"] = NOTIONAL * t["ret"] - NOTIONAL * COST
    first = dd["front"].index[200] if len(dd["front"]) > 200 else END
    return t, first


def summarize(t, first):
    out = {}
    for p, (a, b) in PERIODS.items():
        a, b = max(pd.Timestamp(a), first), min(pd.Timestamp(b), END)
        yrs = max((b - a).days / 365.25, 0.01)
        x = t[(t.entry_date >= a) & (t.entry_date < b)].sort_values("exit_date")
        if x.empty:
            out[p] = dict(tr=0, per_yr=0.0)
            continue
        eq = x.usd.cumsum()
        out[p] = dict(tr=len(x), per_yr=len(x) / yrs, win=100 * (x.usd > 0).mean(), net=x.usd.sum(), avg=x.usd.mean(),
                      worst=x.usd.min(), dd=(eq - eq.cummax()).min())
    return out


def cell(s):
    if s["tr"] == 0:
        return "0 tr"
    return (f"{s['tr']} tr ({s['per_yr']:.0f}/yr), {s['win']:.0f}% win, net ${s['net']:+,.0f}, avg ${s['avg']:+.1f}, "
            f"worst ${s['worst']:+,.0f}, DD ${s['dd']:+,.0f}")


def main():
    pd.set_option("display.width", 250)
    markets = {}
    for root in ("ES", "NQ"):
        markets[root] = rv.load_hl(root)
    for root in FUTURES:
        markets[root] = load_future(root)
    for s in STOCKS:
        dd, splits = load_stock(s)
        markets[s] = dd
        print(f"{s}: splits removed {splits or 'none'}")
    all_t, rows = [], []
    for name, dd in markets.items():
        t, first = trades_for(name, dd)
        all_t.append(t)
        sm = summarize(t, first)
        print(f"\n{name:6s} (first possible entry {first.date()})")
        for p in PERIODS:
            print(f"   {p:13s} {cell(sm[p])}")
        rows.append(dict(market=name, **{f"{p}|{k}": v for p in PERIODS for k, v in sm[p].items()}))
    T = pd.concat(all_t, ignore_index=True)
    T.to_csv(os.path.join(HERE, "rsi2_markets_trades.csv"), index=False)

    # whole 2020-10 .. 2026-10 per market, for the summary table
    print("\n=== summary, all periods (2020-2026-10), $5,000 per trade ===")
    for name in markets:
        x = T[(T.market == name) & (T.entry_date >= "2020-01-01")].sort_values("exit_date")
        eq = x.usd.cumsum()
        yrs = (END - max(pd.Timestamp("2020-01-01"), markets[name]["front"].index[200])).days / 365.25
        ok = {p: (summarize(T[T.market == name], markets[name]["front"].index[200])[p].get("net", 0) > 0) for p in PERIODS}
        print(f"{name:6s} {len(x):3d} tr ({len(x) / yrs:4.1f}/yr) win {100 * (x.usd > 0).mean():3.0f}%  net ${x.usd.sum():+7,.0f}  "
              f"avg ${x.usd.mean():+6.1f}  worst ${x.usd.min():+6,.0f}  maxDD ${(eq - eq.cummax()).min():+6,.0f}  "
              f"positive: " + " ".join(f"{p.split()[0]}={'Y' if v else 'n'}" for p, v in ok.items()))

    # capital: with $10,000 at 1x only two $5,000 positions fit; how often would more be open at once?
    def concurrency(names):
        x = T[T.market.isin(names) & (T.entry_date >= "2020-01-01")]
        days = pd.date_range("2020-01-01", END, freq="B")
        openn = np.zeros(len(days), int)
        for a, b in zip(x.entry_date, x.exit_date):
            openn += (days >= a) & (days < b)
        return openn
    print("\n=== out-of-sample market selection: pick on 2020-23 only (net > 0), then look at the later periods ===")
    picked = [m for m in markets if m not in ("ES", "NQ")
              and T[(T.market == m) & (T.entry_date >= "2020-01-01") & (T.entry_date < "2024-01-01")].usd.sum() > 0]
    print(f"picked on 2020-23: {picked}")
    for p in ("2024-25", "2026 holdout"):
        a, b = PERIODS[p]
        for lab, names in (("picked", picked), ("ES+NQ", ["ES", "NQ"])):
            y = T[T.market.isin(names) & (T.entry_date >= a) & (T.entry_date < b)]
            print(f"   {p:13s} {lab:7s} {len(y):3d} tr, win {100 * (y.usd > 0).mean():.0f}%, net ${y.usd.sum():+,.0f}, "
                  f"avg ${y.usd.mean():+.1f}/trade, markets positive {sum(T[(T.market == m) & (T.entry_date >= a) & (T.entry_date < b)].usd.sum() > 0 for m in names)}/{len(names)}")

    print("\n=== portfolios: $10,000 account at 1x (no leverage); a signal is skipped when no slot is free ===")
    sets = {"ES+NQ (live)": ["ES", "NQ"], "+ NVDA, GOOGL": ["ES", "NQ", "NVDA", "GOOGL"],
            "+ NVDA, GOOGL, CL": ["ES", "NQ", "NVDA", "GOOGL", "CL"],
            "+ NVDA, GOOGL, CL, BTC": ["ES", "NQ", "NVDA", "GOOGL", "CL", "BTC"]}
    for label, names in sets.items():
        o = concurrency(names)
        print(f"\n{label}: days with more than 2 positions open if every signal were taken: {(o > 2).mean():.1%}, "
              f"more than 4: {(o > 4).mean():.1%}")
        for slots in (2, 4):
            x = portfolio(T[T.market.isin(names)], slots, 10_000 / slots)
            for p in PERIODS:
                a, b = PERIODS[p]
                y = x[(x.entry_date >= a) & (x.entry_date < b)].sort_values("exit_date")
                eq = y.pnl.cumsum()
                yrs = rv.YEARS[p]
                print(f"   {slots} slots x ${10_000 / slots:,.0f}  {p:13s} {len(y):3d} tr ({len(y) / yrs:4.1f}/yr), "
                      f"skipped {int(x.attrs['skipped'][p])}, net ${y.pnl.sum():+7,.0f}, worst ${y.pnl.min():+6,.0f}, "
                      f"maxDD ${(eq - eq.cummax()).min():+7,.0f}")


def portfolio(x, slots, size):
    """Take signals in date order (ties by market name); skip one when `slots` positions are already open."""
    x = x[x.entry_date >= "2020-01-01"].sort_values(["entry_date", "market"])
    open_until, taken, skipped = [], [], {p: 0 for p in PERIODS}
    for _, t in x.iterrows():
        open_until = [d for d in open_until if d > t.entry_date]   # exits fill at the close before new entries
        if len(open_until) >= slots:
            for p, (a, b) in PERIODS.items():
                skipped[p] += a <= str(t.entry_date.date()) < b
            continue
        open_until.append(t.exit_date)
        taken.append(dict(entry_date=t.entry_date, exit_date=t.exit_date, market=t.market,
                          pnl=size * t.ret - size * COST))
    out = pd.DataFrame(taken)
    out.attrs["skipped"] = skipped
    return out


if __name__ == "__main__":
    main()

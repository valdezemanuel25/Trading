#!/usr/bin/env python3
"""Download Databento ES trades (with aggressor side) and save per-minute buy/sell volume.

Needs:  pip install databento   and   DATABENTO_API_KEY in the environment (never in the repo or chat).
Needs network access to hist.databento.com.

  python3 backtest/fetch_trades.py --start 2026-04-01 --end 2026-10-29 --budget 100

- Checks the cost with Databento BEFORE downloading and stops if it is over --budget (US$).
- Downloads one day at a time (keeps memory small), keeps outright ES contracts only.
- Aggressor side from Databento's `side`: "B" = buyer hit the ask (buy), "A" = seller hit the bid (sell).
- Writes data/trades_1m/es_trades_1m_YYYY-MM.csv.zst with columns:
    ts (UTC minute), symbol, buy_vol, sell_vol, trades
  That is all real CVD needs: delta = buy_vol - sell_vol. The raw ticks are not kept.
"""
import argparse
import io
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "trades_1m")
OUTRIGHT = re.compile(r"^ES[HMUZ]\d$")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True, help="exclusive")
    ap.add_argument("--budget", type=float, required=True, help="max US$ to spend")
    ap.add_argument("--dry-run", action="store_true", help="only print the cost")
    args = ap.parse_args()

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("DATABENTO_API_KEY is not set in this environment")
    import databento as db
    import zstandard

    client = db.Historical(key)
    q = dict(dataset="GLBX.MDP3", schema="trades", symbols=["ES.FUT"], stype_in="parent")
    cost = client.metadata.get_cost(start=args.start, end=args.end, **q)
    print(f"Databento cost for {args.start} -> {args.end}: ${cost:.2f} (budget ${args.budget:.2f})")
    if cost > args.budget:
        sys.exit("Over budget - nothing downloaded. Shorten the range or raise --budget.")
    if args.dry_run:
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    days = pd.date_range(args.start, pd.Timestamp(args.end) - pd.Timedelta(days=1), freq="D")
    months = {}
    for d in days:
        if d.weekday() == 5:  # no Saturday session
            continue
        store = client.timeseries.get_range(start=d.strftime("%Y-%m-%d"),
                                            end=(d + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), **q)
        df = store.to_df(map_symbols=True)
        if df.empty:
            continue
        df = df[df["symbol"].str.match(OUTRIGHT)]
        df["minute"] = df.index.floor("1min")
        df["buy"] = df["size"].where(df["side"] == "B", 0)
        df["sell"] = df["size"].where(df["side"] == "A", 0)
        agg = (df.groupby(["minute", "symbol"])
                 .agg(buy_vol=("buy", "sum"), sell_vol=("sell", "sum"), trades=("size", "size"))
                 .reset_index().rename(columns={"minute": "ts"}))
        months.setdefault(d.strftime("%Y-%m"), []).append(agg)
        print(d.date(), f"{len(df):,} trades -> {len(agg):,} minute rows", flush=True)

    for m, parts in months.items():
        out = pd.concat(parts, ignore_index=True)
        path = os.path.join(OUT_DIR, f"es_trades_1m_{m}.csv.zst")
        raw = out.to_csv(index=False).encode()
        with open(path, "wb") as fh:
            fh.write(zstandard.ZstdCompressor(level=10).compress(raw))
        print("wrote", path, f"{os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

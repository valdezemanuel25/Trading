#!/usr/bin/env python3
"""Download Databento ES trades (with aggressor side) and save per-minute buy/sell volume.

Needs DATABENTO_API_KEY in the environment (never in the repo or chat) and network access to hist.databento.com.
Talks to Databento's HTTP API directly, so the `databento` package is not required.

  python3 backtest/fetch_trades.py --start 2026-04-01 --end 2026-10-29 --budget 100 --dry-run
  python3 backtest/fetch_trades.py --start 2026-04-01 --end 2026-10-29 --budget 100

- Checks the cost with Databento BEFORE downloading and stops if it is over --budget (US$).
- Downloads one UTC day at a time and keeps outright ES contracts only. Each finished day is cached in
  backtest/.cache/trades_days/, so a rerun never pays for the same day twice. The running total of what was
  actually requested is checked against --budget before every day.
- Aggressor side from Databento's `side`: "B" = buyer hit the ask (buy), "A" = seller hit the bid (sell),
  "N" = no aggressor (counted in `trades` only).
- Writes data/trades_1m/es_trades_1m_YYYY-MM.csv.zst with columns:
    ts (UTC minute), symbol, buy_vol, sell_vol, trades
  That is all real CVD needs: delta = buy_vol - sell_vol. The raw ticks are not kept.
"""
import argparse
import io
import os
import re
import sys
import time

import pandas as pd
import requests

from zstd_io import decompress, write_zst

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "trades_1m")
DAY_CACHE = os.path.join(ROOT, "backtest", ".cache", "trades_days")
OUTRIGHT = re.compile(r"^ES[HMUZ]\d$")
API = "https://hist.databento.com/v0/"
QUERY = dict(dataset="GLBX.MDP3", schema="trades", symbols="ES.FUT", stype_in="parent")


def api(session, endpoint, **params):
    # retry dropped connections (proxy resets); HTTP errors stop the run
    for attempt in range(4):
        try:
            r = session.post(API + endpoint, data={**QUERY, **params}, timeout=600)
            break
        except requests.exceptions.ConnectionError as e:
            if attempt == 3:
                raise
            print(f"  connection error ({e.__class__.__name__}), retrying in {2 ** (attempt + 1)}s", flush=True)
            time.sleep(2 ** (attempt + 1))
    # Databento answers some days with 206 and the full data (e.g. 2026-09-06); a truncated body fails to parse
    if r.status_code == 206:
        print(f"  note: {endpoint} returned 206 Partial Content", flush=True)
    elif r.status_code != 200:
        sys.exit(f"Databento {endpoint} failed ({r.status_code}): {r.text[:300]}")
    return r


def get_cost(session, start, end):
    return float(api(session, "metadata.get_cost", start=start, end=end).text)


def fetch_day(session, start, end):
    r = api(session, "timeseries.get_range", start=start, end=end, encoding="csv", compression="zstd",
            map_symbols="true")
    raw = decompress(r.content)
    if not raw.strip():
        return pd.DataFrame(columns=["ts", "symbol", "buy_vol", "sell_vol", "trades"]), 0
    df = pd.read_csv(io.BytesIO(raw), usecols=["ts_event", "side", "size", "symbol"],
                     dtype={"ts_event": "int64", "side": "category", "size": "int64", "symbol": "category"})
    n = len(df)
    df = df[df["symbol"].astype(str).str.match(OUTRIGHT)]
    df["ts"] = pd.to_datetime(df["ts_event"], utc=True).dt.floor("1min")
    df["buy"] = df["size"].where(df["side"] == "B", 0)
    df["sell"] = df["size"].where(df["side"] == "A", 0)
    agg = (df.groupby(["ts", df["symbol"].astype(str)])
             .agg(buy_vol=("buy", "sum"), sell_vol=("sell", "sum"), trades=("size", "size"))
             .reset_index())
    return agg, n


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
    session = requests.Session()
    session.auth = (key, "")

    os.makedirs(DAY_CACHE, exist_ok=True)
    days = pd.date_range(args.start, pd.Timestamp(args.end) - pd.Timedelta(days=1), freq="D")
    todo = [d for d in days if d.weekday() != 5  # no Saturday session
            and not os.path.exists(os.path.join(DAY_CACHE, d.strftime("%Y-%m-%d") + ".csv"))]

    cost = get_cost(session, args.start, args.end)
    print(f"Databento cost for {args.start} -> {args.end}: ${cost:.2f} (budget ${args.budget:.2f}); "
          f"{len(todo)} days still to download")
    if cost > args.budget:
        sys.exit("Over budget - nothing downloaded. Shorten the range or raise --budget.")
    if args.dry_run:
        return

    spent = 0.0
    for d in todo:
        s, e = d.strftime("%Y-%m-%d"), (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        day_cost = get_cost(session, s, e)
        if spent + day_cost > args.budget:
            sys.exit(f"Stopping before {s}: ${spent:.2f} spent, next day ${day_cost:.2f} would pass the budget")
        agg, n = fetch_day(session, s, e)
        spent += day_cost
        agg.to_csv(os.path.join(DAY_CACHE, s + ".csv"), index=False)
        print(f"{s}  {n:,} trades -> {len(agg):,} minute rows  (${day_cost:.2f}, total ${spent:.2f})", flush=True)

    # assemble monthly files from every cached day in range
    os.makedirs(OUT_DIR, exist_ok=True)
    parts = [pd.read_csv(os.path.join(DAY_CACHE, d.strftime("%Y-%m-%d") + ".csv")) for d in days
             if os.path.exists(os.path.join(DAY_CACHE, d.strftime("%Y-%m-%d") + ".csv"))]
    allm = pd.concat(parts, ignore_index=True)
    allm["ts"] = pd.to_datetime(allm["ts"], utc=True)
    for m, g in allm.groupby(allm["ts"].dt.strftime("%Y-%m")):
        path = os.path.join(OUT_DIR, f"es_trades_1m_{m}.csv.zst")
        g = g.sort_values(["ts", "symbol"])
        g = g.assign(ts=g["ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        write_zst(path, g.to_csv(index=False).encode())
        print("wrote", path, f"{os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

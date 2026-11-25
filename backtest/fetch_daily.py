#!/usr/bin/env python3
"""Download Databento daily bars (ohlcv-1d, 00:00 UTC days) for the RSI(2) market-expansion research.

Needs DATABENTO_API_KEY in the environment (never in the repo or chat) and network access to hist.databento.com.
Checks the cost with Databento BEFORE downloading anything and stops if the total is over --budget (US$).

  python3 backtest/fetch_daily.py --dry-run            # print the cost of every request, download nothing
  python3 backtest/fetch_daily.py --budget 10          # download what isn't on disk yet

Writes data/daily/<NAME>.csv in the same raw Databento CSV form as NQ/RTY/YM (ts_event in ns, prices x 1e9):
- Futures (GLBX.MDP3, parent symbology, every contract incl. spreads; the research filters outrights):
  GC gold, SI silver, CL WTI, BZ Brent (NYMEX Brent last-day financial), BTC and ETH (CME), 2019-01-01 to 2026-10-29.
- Single stocks (XNAS.ITCH, Nasdaq prints only, NOT split-adjusted; the research adjusts splits):
  AAPL NVDA MSFT TSLA AMZN GOOGL META, 2019-01-01 to 2026-10-29.
"""
import argparse
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "daily")
API = "https://hist.databento.com/v0/"
START, END = "2019-01-01", "2026-10-29"
REQUESTS = {
    **{n: dict(dataset="GLBX.MDP3", symbols=f"{n}.FUT", stype_in="parent") for n in ("GC", "SI", "CL", "BZ", "BTC", "ETH")},
    **{n: dict(dataset="XNAS.ITCH", symbols=n, stype_in="raw_symbol") for n in ("AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL", "META")},
}


def post(session, endpoint, **data):
    for attempt in range(4):
        try:
            r = session.post(API + endpoint, data=data, timeout=600)
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
            if attempt == 3:
                raise
            print(f"  connection error ({e.__class__.__name__}), retrying in {2 ** (attempt + 1)}s", flush=True)
            time.sleep(2 ** (attempt + 1))
    if r.status_code not in (200, 206):
        sys.exit(f"Databento {endpoint} failed ({r.status_code}): {r.text[:300]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=10.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*", help="names to fetch (default: all)")
    args = ap.parse_args()
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        sys.exit("DATABENTO_API_KEY is not set")
    s = requests.Session()
    s.auth = (key, "")
    names = [n for n in REQUESTS if not args.only or n in args.only]
    todo = [n for n in names if not os.path.exists(os.path.join(OUT, f"{n}.csv"))]
    costs = {}
    for n in todo:
        q = REQUESTS[n]
        costs[n] = float(post(s, "metadata.get_cost", schema="ohlcv-1d", start=START, end=END, **q).text)
        print(f"{n:6s} {q['dataset']:10s} {q['symbols']:8s} ${costs[n]:.4f}", flush=True)
    total = sum(costs.values())
    print(f"TOTAL ${total:.2f} for {len(todo)} requests (budget ${args.budget:.2f}); already on disk: "
          f"{[n for n in names if n not in todo]}")
    if args.dry_run:
        return
    if total > args.budget:
        sys.exit("over budget, nothing downloaded")
    for n in todo:
        q = REQUESTS[n]
        r = post(s, "timeseries.get_range", schema="ohlcv-1d", start=START, end=END, encoding="csv",
                 map_symbols="true", pretty_px="false", pretty_ts="false", **q)
        path = os.path.join(OUT, f"{n}.csv")
        with open(path, "wb") as f:
            f.write(r.content)
        print(f"{n}: {len(r.content.splitlines()) - 1} rows -> {os.path.relpath(path, ROOT)}", flush=True)


if __name__ == "__main__":
    main()

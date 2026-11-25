#!/usr/bin/env python3
"""Download Databento 1-minute bars (ohlcv-1m) for the intraday-entry research (approved 2026-11-25, ~$19).

Needs DATABENTO_API_KEY in the environment and network access to hist.databento.com. Checks the total cost first
and stops if it is over --budget (US$). Front month only for futures (continuous by volume, `.v.0`), Nasdaq prints
for stocks. Writes data/intraday/<NAME>_1m.csv.zst (raw Databento CSV: ts_event in ns, prices x 1e9, symbol).

  python3 backtest/fetch_1m.py --dry-run
  python3 backtest/fetch_1m.py --budget 20
"""
import argparse
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "intraday")
API = "https://hist.databento.com/v0/"
START, END = "2020-01-01", "2026-10-29"
REQ = {"NQ": dict(dataset="GLBX.MDP3", symbols="NQ.v.0", stype_in="continuous"),
       "CL": dict(dataset="GLBX.MDP3", symbols="CL.v.0", stype_in="continuous"),
       "NVDA": dict(dataset="XNAS.ITCH", symbols="NVDA", stype_in="raw_symbol"),
       "GOOGL": dict(dataset="XNAS.ITCH", symbols="GOOGL", stype_in="raw_symbol")}


def post(s, endpoint, stream=False, **data):
    for attempt in range(4):
        try:
            r = s.post(API + endpoint, data=data, timeout=1800, stream=stream)
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
            if attempt == 3:
                raise
            print(f"  connection error ({e.__class__.__name__}), retrying", flush=True)
            time.sleep(2 ** (attempt + 1))
    if r.status_code not in (200, 206):
        sys.exit(f"Databento {endpoint} failed ({r.status_code}): {r.text[:300]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=20.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    s = requests.Session()
    s.auth = (os.environ["DATABENTO_API_KEY"], "")
    os.makedirs(OUT, exist_ok=True)
    todo = [n for n in REQ if not os.path.exists(os.path.join(OUT, f"{n}_1m.csv.zst"))]
    cost = {n: float(post(s, "metadata.get_cost", schema="ohlcv-1m", start=START, end=END, **REQ[n]).text) for n in todo}
    for n, c in cost.items():
        print(f"{n:6s} ${c:.2f}")
    total = sum(cost.values())
    print(f"TOTAL ${total:.2f} (budget ${a.budget:.2f})", flush=True)
    if a.dry_run:
        return
    if total > a.budget:
        sys.exit("over budget, nothing downloaded")
    for n in todo:
        r = post(s, "timeseries.get_range", stream=True, schema="ohlcv-1m", start=START, end=END, encoding="csv",
                 compression="zstd", map_symbols="true", pretty_px="false", pretty_ts="false", **REQ[n])
        path = os.path.join(OUT, f"{n}_1m.csv.zst")
        with open(path + ".part", "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.replace(path + ".part", path)
        print(f"{n}: {os.path.getsize(path) / 1e6:.1f} MB -> {os.path.relpath(path, ROOT)}", flush=True)


if __name__ == "__main__":
    main()

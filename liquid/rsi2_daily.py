#!/usr/bin/env python3
"""Daily RSI(2) check for every live market (approved 2026-11-25): merge history, compute signals, rank by slot.

Markets (Liquid perps): SP500 = xyz:SP500, NQ100 = xyz:XYZ100, NVDA = xyz:NVDA, GOOGL = xyz:GOOGL, CL = xyz:CL.
Rules: long only; close > 200-day SMA and RSI(2) < 10 -> LONG SETUP; first close above the 5-day SMA -> EXIT.
$5,000 notional per trade, at most 2 positions open; when more setups than free slots, take them in the backtest's
order: CL, SP500, GOOGL, NQ100, NVDA (alphabetical by futures/stock root, as in research/rsi2_markets.py).

200-day filter: the mean of the last 200 completed WEEKDAY closes, from the saved history (liquid/history/<KEY>.json,
mirrored in the dashboard store at data/rsi2/history/<KEY>; candles stored as {t: ms, c: close}). Until a market has 200 weekday closes saved (about mid-Feb
2027 from the 2026-11-25 seed), the filter falls back to Liquid's own sma200 (200 calendar candles) and says so.

Usage (W = a work directory):
  W/candles/<KEY>.json  the show_chart answer (interval 1d, limit 30) for each market: {"candles":[{timestamp, close}...]}
  python3 liquid/rsi2_daily.py W --sma200 SP500=7564.3 NQ100=29292.34 NVDA=209.62 GOOGL=344.41 CL=87.57 \\
      [--holding SP500,NVDA] [--history-dir liquid/history]
Writes the merged history back to --history-dir (default liquid/history) and to W/history_out/<KEY>.json, and prints
a JSON report (one row per market plus the slot decision).
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsi2_signal import completed_weekdays, signal  # noqa: E402

MARKETS = {"SP500": "xyz:SP500", "NQ100": "xyz:XYZ100", "NVDA": "xyz:NVDA", "GOOGL": "xyz:GOOGL", "CL": "xyz:CL"}
PRIORITY = ["CL", "SP500", "GOOGL", "NQ100", "NVDA"]
SLOTS, NOTIONAL = 2, 5000
DAY = 86_400_000


def load_history(path):
    if not os.path.exists(path):
        return {}
    d = json.load(open(path))
    out = {}
    for x in d.get("candles", []):
        ts, c = (x["t"], x["c"]) if isinstance(x, dict) else x
        out[int(ts)] = float(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--sma200", nargs="+", required=True, help="KEY=value from get_technical_indicators")
    ap.add_argument("--holding", default="", help="comma-separated KEYs with an open position")
    ap.add_argument("--history-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "history"))
    ap.add_argument("--now-ms", type=int, default=None)
    a = ap.parse_args()
    now = a.now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    sma = {k: float(v) for k, v in (s.split("=") for s in a.sma200)}
    holding = {h for h in a.holding.split(",") if h}
    os.makedirs(os.path.join(a.workdir, "history_out"), exist_ok=True)
    rows, warnings = [], []
    for key, sym in MARKETS.items():
        cpath = os.path.join(a.workdir, "candles", f"{key}.json")
        if not os.path.exists(cpath):
            warnings.append(f"{key}: no candles file, skipped")
            continue
        candles = json.load(open(cpath))["candles"]
        hpath = os.path.join(a.history_dir, f"{key}.json")
        hist = load_history(hpath)
        new = {int(c["timestamp"]): float(c["close"]) for c in candles if int(c["timestamp"]) + DAY <= now}
        if hist and new and min(new) - max(hist) > DAY:
            warnings.append(f"{key}: gap in saved history between {max(hist)} and {min(new)}")
        hist.update(new)
        doc = {"market": key, "symbol": sym, "candles": [{"t": ts, "c": hist[ts]} for ts in sorted(hist)]}
        for p in (hpath, os.path.join(a.workdir, "history_out", f"{key}.json")):
            json.dump(doc, open(p, "w"))
        r = signal(candles, sma[key], now_ms=now, history=hist, use_weekday_sma=True)
        r.update(market=key, symbol=sym, holding=key in holding,
                 filter_used=r.get("filter_used", "liquid_sma200 (fewer than 200 weekday closes saved)"))
        rows.append(r)
    free = SLOTS - len(holding)
    setups = sorted((r for r in rows if r["action"] == "LONG SETUP" and not r["holding"]),
                    key=lambda r: PRIORITY.index(r["market"]))
    for r in rows:
        if r["action"] == "LONG SETUP" and r["holding"]:
            r["todo"] = "already holding: no action"
        elif r["action"] == "LONG SETUP":
            r["todo"] = (f"BUY ${NOTIONAL:,} paper long, 1x (needs approval)" if setups.index(r) < free
                         else "skip: no free slot")
        elif r["action"] == "EXIT":
            r["todo"] = "SELL: close the paper long (needs approval)" if r["holding"] else "no position: no action"
        else:
            r["todo"] = "holding" if r["holding"] else "no action"
    print(json.dumps(dict(free_slots=free, rows=rows, warnings=warnings), indent=1, default=str))


if __name__ == "__main__":
    main()

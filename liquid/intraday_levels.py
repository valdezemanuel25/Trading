#!/usr/bin/env python3
"""Intraday trigger levels for the proposed order agent (designed 2026-11-25; NOT wired into any live task yet).

Reads the saved daily closes (dashboard store data/rsi2/history, or liquid/history) and the open-position records
(data/rsi2/open), and prints, per market, the prices that matter during the next UTC day:
- tr_trigger: trend reclaim. If the market is armed (no position, last close at or below its 200-day SMA), the
  price that would be a reclaim: the 200-day SMA on the last completed candle. Liquid has no buy-stop order, so the
  agent proposes a market buy once the live price is above it.
- rsi2_limit: the highest close that would give RSI(2) < 10 (only meaningful above the 200-day SMA). The resting
  limit-buy variant was rejected in the backtest; shown for the pre-close check only.
- rsi2_exit_above: for a held RSI(2) position, a close above this price is a close above the 5-day SMA.
- tr_exit_below: for a held TR position, a close below the 200-day SMA (this level, roughly) is the exit.
With --live KEY=price ..., it also evaluates each rule as if that price were today's close (pre-close check).

  python3 liquid/intraday_levels.py --history-dir DIR [--open-dir DIR] [--live SP500=7200 CL=88.1 ...]
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsi2_daily import MARKETS, TR_ORDER, load_history, rsi2, sma200_at, weekday  # noqa: E402

DAY = 86_400_000


def wilder_state(closes):
    up = dn = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        up, dn = 0.5 * up + 0.5 * max(d, 0), 0.5 * dn + 0.5 * max(-d, 0)
    return up, dn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history-dir", required=True)
    ap.add_argument("--open-dir", default=None)
    ap.add_argument("--live", nargs="*", default=[])
    ap.add_argument("--now-ms", type=int, default=None)
    a = ap.parse_args()
    now = a.now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    live = {k: float(v) for k, v in (x.split("=") for x in a.live)}
    open_pos = {}
    if a.open_dir and os.path.isdir(a.open_dir):
        for f in os.listdir(a.open_dir):
            if f.endswith(".json"):
                d = json.load(open(os.path.join(a.open_dir, f)))
                open_pos[d.get("market", f[:-5])] = d
    out = []
    for key, sym in MARKETS.items():
        hist, liq = load_history(os.path.join(a.history_dir, f"{key}.json"))
        wk = [t for t in sorted(hist) if weekday(t) and t + DAY <= now]
        if len(wk) < 7:
            continue
        last_ts = wk[-1]
        closes = [hist[t] for t in wk[-30:]]
        sma, src = sma200_at(hist, last_ts, liq.get(last_ts))
        up, dn = wilder_state(closes)
        c = closes[-1]
        p = c + (dn / 9 - up) if dn / 9 - up > 0 else c - (9 * up - dn)
        pos = open_pos.get(key)
        row = dict(market=key, symbol=sym, last_candle=str(dt.datetime.fromtimestamp(last_ts / 1000, dt.timezone.utc).date()),
                   last_close=c, sma200=round(sma, 4), sma200_source=src, position=(pos or {}).get("strategy"),
                   tr_armed=bool(key in TR_ORDER and not pos and c <= sma), tr_trigger=round(sma, 4) if key in TR_ORDER else None,
                   rsi2_limit=round(p, 4), rsi2_limit_above_sma=bool(p > sma),
                   rsi2_exit_above=round(sum(closes[-4:]) / 4, 4), tr_exit_below=round(sma, 4))
        if key in live:
            x = live[key]
            r = rsi2(closes + [x])
            sma5 = (sum(closes[-4:]) + x) / 5
            row.update(live=x, live_rsi2=round(r, 1), live_above_sma200=x > sma,
                       live_tr_cross=bool(row["tr_armed"] and x > sma),
                       live_rsi2_setup=bool(not pos and x > sma and r < 10),
                       live_rsi2_exit=bool(pos and pos.get("strategy") == "RSI2" and x > sma5),
                       live_tr_exit=bool(pos and pos.get("strategy") == "TR" and x < sma))
        out.append(row)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()

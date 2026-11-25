#!/usr/bin/env python3
"""Daily positioning log (approved 2026-11-25): turn Liquid analyze_market answers into one small record per market.

Data collection only; no rule uses it yet. After 6-12 months it can be tested as a filter on the live rules, e.g.
whether entries where smart money is less long than the losing crowd do better, or whether high funding hurts.

Usage (W = the daily check's work directory, DATE = the completed candle's date, YYYY-MM-DD):
  W/positioning/<KEY>.json   the analyze_market answer for each market, saved as returned
  python3 liquid/positioning.py W DATE
Writes W/positioning_out/<DATE>_<KEY>.json, each a document for the dashboard store collection
data/rsi2/positioning (doc id <DATE>_<KEY>), and prints a one-line summary per market.
"""
import json
import os
import re
import sys

KEYS = ["SP500", "NQ100", "NVDA", "GOOGL", "CL"]


def num(x):
    if x is None:
        return None
    s = re.sub(r"[^0-9eE.+-]", "", str(x).replace("−", "-"))
    try:
        return float(s)
    except ValueError:
        return None


def record(key, date, a):
    t = a.get("ticker", {})
    sec = a.get("sections", {}) or {}
    sm = sec.get("smartMoney") or a.get("smartMoney") or ""
    m = re.search(r"smart money\s+(\d+(?:\.\d+)?)%\s+long.*?losing crowd\s+(\d+(?:\.\d+)?)%\s+long", sm, re.I | re.S)
    size = (sec.get("size") or {}).get("breakdownBySize", [])
    total = sum(b.get("totalPositionValue") or 0 for b in size)
    longv = sum(b.get("totalPositionValueLong") or 0 for b in size)
    return dict(
        date=date, market=key, symbol=t.get("coin") or a.get("symbol"),
        mark_px=num(t.get("markPx")), funding_pct=num(t.get("funding")), oi_usd=num(t.get("openInterest")),
        day_volume_usd=num(t.get("dayNtlVlm")), change_24h_pct=num(t.get("change24h")),
        smart_long_pct=float(m.group(1)) if m else None, crowd_long_pct=float(m.group(2)) if m else None,
        smart_money_text=sm[:300] or None,
        long_share_all=round(longv / total, 4) if total else None,
        bias_by_size=[dict(size=b.get("size"), bias=b.get("bias"), value=b.get("totalPositionValue"),
                           count=b.get("positionCount")) for b in size],
        snapshot_at=(sec.get("size") or {}).get("createdAt"),
    )


def main():
    w, date = sys.argv[1], sys.argv[2]
    out = os.path.join(w, "positioning_out")
    os.makedirs(out, exist_ok=True)
    for key in KEYS:
        p = os.path.join(w, "positioning", f"{key}.json")
        if not os.path.exists(p):
            print(f"{key}: no analyze_market file, skipped")
            continue
        r = record(key, date, json.load(open(p)))
        json.dump(r, open(os.path.join(out, f"{date}_{key}.json"), "w"))
        print(f"{key}: funding {r['funding_pct']}%, OI ${r['oi_usd'] or 0:,.0f}, smart {r['smart_long_pct']}% long vs "
              f"crowd {r['crowd_long_pct']}% long, all positions {r['long_share_all']} long")


if __name__ == "__main__":
    main()

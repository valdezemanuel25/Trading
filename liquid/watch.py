#!/usr/bin/env python3
"""Watch list: two setups tracked as shadow trades, INFORMATION ONLY (approved 2026-11-26).

Never an order, never a slot: the live rules (liquid/rsi2_daily.py) don't see these. Settings are fixed until the
review (docs/live-setup.md, "Watch list"): 2027-05-31, or earlier once either setup has 8 closed shadow trades.

- DEEP (NVDA, GOOGL): RSI(2) < 10 and the close at least 10% below the 200-day SMA -> shadow buy at the close.
- DOWN4-B200 (SP500, NQ100, NVDA, GOOGL): 4 lower closes in a row (or more) with the close below the 200-day SMA
  -> shadow buy at the close.
- Both exit at the first later close above the 5-day SMA. One shadow position per setup and market; the two setups
  are independent of each other.
- Shadow P&L: $5,000 x (exit / entry - 1) - 0.10% of $5,000 ($5 per round trip), as research/strategies2.py.

Same data as the live check: saved weekday 00:00 UTC closes (data/rsi2/history, merged by rsi2_daily.py), the same
200-day SMA (sma200_at: 200 weekday closes, Liquid's sma200 until then) and the same RSI(2).

State: one file per processed candle date, liquid/watch/<YYYY-MM-DD>.json = {date, events, open, closed} where
`open` = shadow positions still open after that candle and `closed` = every closed shadow trade so far. Each run
starts from the latest file dated before the newest candle and replays every newer weekday candle, so a missed day is
caught up; a re-run for the same candle rewrites that day's file from the same starting point.

  python3 liquid/watch.py --history-dir DIR [--watch-dir liquid/watch] [--now-ms MS]
Prints {"lines": [...WATCH lines for the report...], "files": [...written...], "review_due": bool}.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsi2_daily import DAY, day_str, load_history, rsi2, sma200_at, weekday  # noqa: E402

START = "2026-11-26"            # first candle tracked (the day the watch list was approved)
REVIEW_DATE, REVIEW_TRADES = "2027-05-31", 8
NOTIONAL, COST = 5000.0, 0.001
SETUPS = {"DEEP": ["NVDA", "GOOGL"], "DOWN4-B200": ["SP500", "NQ100", "NVDA", "GOOGL"]}
DEEP_GAP, RSI_MAX, DOWN_N = 0.10, 10, 4
WATCH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "liquid", "watch")


def pnl(entry, px):
    return round(NOTIONAL * (px / entry - 1) - NOTIONAL * COST, 2)


def state_at(hist, liq, wk, i):
    """Indicators on weekday candle wk[i] (needs i >= 5)."""
    ts = wk[i]
    closes = [hist[t] for t in wk[max(0, i - 29):i + 1]]
    sma, src = sma200_at(hist, ts, liq.get(ts))
    down = 0
    while down < i and hist[wk[i - down]] < hist[wk[i - down - 1]]:
        down += 1
    return dict(close=closes[-1], rsi2=rsi2(closes), sma5=sum(closes[-5:]) / 5, sma200=sma, sma200_source=src,
                down=down)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history-dir", required=True)
    ap.add_argument("--watch-dir", default=WATCH_DIR)
    ap.add_argument("--now-ms", type=int, default=None)
    a = ap.parse_args()
    now = a.now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    os.makedirs(a.watch_dir, exist_ok=True)

    data = {}
    for m in sorted({m for ms in SETUPS.values() for m in ms}):
        hist, liq = load_history(os.path.join(a.history_dir, f"{m}.json"))
        wk = [t for t in sorted(hist) if weekday(t) and t + DAY <= now]
        data[m] = (hist, liq, wk)
    days = sorted({day_str(t) for _, _, wk in data.values() for t in wk})
    if not days:
        sys.exit("no saved closes")
    newest = days[-1]
    prev = sorted(f[:-5] for f in os.listdir(a.watch_dir) if f.endswith(".json") and f[:-5] < newest)
    if prev:
        st = json.load(open(os.path.join(a.watch_dir, prev[-1] + ".json")))
        open_, closed, after = st["open"], st["closed"], prev[-1]
    else:
        open_, closed, after = [], [], None
    todo = [d for d in days if d >= START and (after is None or d > after)]

    lines, files = [], []
    for d in todo:
        events = []
        for setup, markets in SETUPS.items():
            for m in markets:
                hist, liq, wk = data[m]
                idx = {day_str(t): k for k, t in enumerate(wk)}
                if d not in idx or idx[d] < 5:
                    continue
                s = state_at(hist, liq, wk, idx[d])
                pos = next((p for p in open_ if p["setup"] == setup and p["market"] == m), None)
                if pos:
                    days_held = sum(1 for t in wk if pos["entry_date"] < day_str(t) <= d)
                    if s["close"] > s["sma5"]:
                        tr = dict(pos, exit_date=d, exit_px=s["close"], days=days_held,
                                  pnl=pnl(pos["entry_px"], s["close"]))
                        open_.remove(pos)
                        closed.append(tr)
                        events.append(dict(tr, event="EXIT", note=f"close {s['close']:g} above 5-day SMA "
                                                                  f"{s['sma5']:.6g}"))
                    else:
                        pos["last_date"], pos["last_px"] = d, s["close"]
                        pos["unrealized"], pos["days"] = pnl(pos["entry_px"], s["close"]), days_held
                    continue
                gap = s["close"] / s["sma200"] - 1
                if setup == "DEEP":
                    hit = s["rsi2"] < RSI_MAX and gap <= -DEEP_GAP
                    why = f"RSI(2) {s['rsi2']:.1f}, {100 * gap:+.1f}% vs 200-day SMA {s['sma200']:.6g}"
                else:
                    hit = s["down"] >= DOWN_N and gap < 0
                    why = f"{s['down']} lower closes in a row, {100 * gap:+.1f}% vs 200-day SMA {s['sma200']:.6g}"
                if hit:
                    p = dict(setup=setup, market=m, entry_date=d, entry_px=s["close"], notional=NOTIONAL,
                             last_date=d, last_px=s["close"], unrealized=pnl(s["close"], s["close"]), days=0)
                    open_.append(p)
                    events.append(dict(p, event="ENTRY", note=f"{why} ({s['sma200_source']})"))
        doc = dict(date=d, info_only=True, events=events, open=open_, closed=closed)
        path = os.path.join(a.watch_dir, f"{d}.json")
        json.dump(doc, open(path, "w"), indent=1)
        files.append(os.path.relpath(path))
        for e in events:
            if e["event"] == "ENTRY":
                lines.append(f"WATCH {e['setup']} {e['market']} ENTRY {d}: shadow buy $5,000 at {e['entry_px']:g}; "
                             f"{e['note']}. Info only, no order")
            else:
                lines.append(f"WATCH {e['setup']} {e['market']} EXIT {d}: shadow sell at {e['exit_px']:g} (entry "
                             f"{e['entry_date']} at {e['entry_px']:g}, {e['days']} days); shadow P&L "
                             f"${e['pnl']:+,.2f} after costs")
    for p in open_:
        lines.append(f"WATCH {p['setup']} {p['market']} open since {p['entry_date']} at {p['entry_px']:g}: "
                     f"{p['last_px']:g} on {p['last_date']}, day {p['days']}, shadow P&L ${p['unrealized']:+,.2f}")
    tally = {s: [t for t in closed if t["setup"] == s] for s in SETUPS}
    summary = "; ".join(f"{s} {len(t)} closed, ${sum(x['pnl'] for x in t):+,.2f}" for s, t in tally.items())
    review_due = newest >= REVIEW_DATE or any(len(t) >= REVIEW_TRADES for t in tally.values())
    if not any(l.startswith("WATCH") and (" ENTRY " in l or " EXIT " in l) for l in lines):
        lines.insert(0, f"WATCH: no new signals (candle {newest})")
    lines.append(f"WATCH totals: {summary} (review at {REVIEW_TRADES} trades or {REVIEW_DATE})"
                 + (". REVIEW DUE: apply the adoption rule in docs/live-setup.md" if review_due else ""))
    print(json.dumps(dict(candles=todo, lines=lines, files=files, review_due=review_due), indent=1))


if __name__ == "__main__":
    main()

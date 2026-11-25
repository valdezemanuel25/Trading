#!/usr/bin/env python3
"""Daily check for the live Liquid paper rules (RSI(2) approved 2026-11-25; trend reclaim approved 2026-11-25).

Markets (Liquid perps): SP500 = xyz:SP500, NQ100 = xyz:XYZ100, NVDA = xyz:NVDA, GOOGL = xyz:GOOGL, CL = xyz:CL.

Rules (all long only, decided on the completed 00:00 UTC daily candle, weekday closes only):
- RSI2 (all five): close > 200-day SMA and RSI(2) < 10 -> BUY. Exit on the first close above the 5-day SMA.
- TR, trend reclaim (CL, GOOGL, NQ100, NVDA): first close back above the 200-day SMA (yesterday's close at or below
  yesterday's SMA, today's above today's) -> BUY. Exit on a close below the 200-day SMA, or at the close of the 20th
  trading day after entry.
- $5,000 notional, 1x. At most 2 positions open and at most one per market. New entries in this order when there are
  more than free slots: RSI2 first (CL, SP500, GOOGL, NQ100, NVDA), then TR (CL, GOOGL, NQ100, NVDA).

200-day SMA: the mean of the last 200 completed WEEKDAY closes from the saved history (liquid/history/<KEY>.json,
mirrored in the dashboard store at data/rsi2/history/<KEY>; candles stored as {t: ms, c: close}). Until 200 weekday
closes are saved (about mid-Feb 2027 from the 2026-11-25 seed), it is the Liquid-style SMA: the mean of the last 200
calendar candles (what get_technical_indicators reports as sma200), computed from the saved history; when fewer than
200 calendar candles are saved, Liquid's reported sma200 for that day is used (saved daily in the history doc as
liquid_sma200: [{t, v}]).

Open positions and which rule opened them: one JSON per market in --open-dir (dashboard store data/rsi2/open/<KEY>,
fields market, symbol, strategy "RSI2"|"TR", entry_date YYYY-MM-DD, entry_px, notional). Claude writes it after an
approved order fills and deletes it after the close fills.

Usage (W = a work directory):
  W/candles/<KEY>.json  the show_chart answer (interval 1d, limit 30): {"candles":[{timestamp, close}...]}
  python3 liquid/rsi2_daily.py W --sma200 SP500=.. NQ100=.. NVDA=.. GOOGL=.. CL=.. \\
      [--history-dir DIR] [--open-dir DIR] [--liquid-holding SP500,NVDA]
--liquid-holding lists the markets Liquid's portfolio shows as open, to cross-check the open-position records.
Writes the merged history to --history-dir and W/history_out/<KEY>.json; prints a JSON report.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rsi2_signal import RSI_ENTRY  # noqa: E402

MARKETS = {"SP500": "xyz:SP500", "NQ100": "xyz:XYZ100", "NVDA": "xyz:NVDA", "GOOGL": "xyz:GOOGL", "CL": "xyz:CL"}
RSI2_ORDER = ["CL", "SP500", "GOOGL", "NQ100", "NVDA"]
TR_ORDER = ["CL", "GOOGL", "NQ100", "NVDA"]
TR_MAX_DAYS = 20
SLOTS, NOTIONAL = 2, 5000
DAY = 86_400_000


def load_history(path):
    """-> ({ts: close}, {ts: Liquid sma200 reported on that completed candle})"""
    if not os.path.exists(path):
        return {}, {}
    d = json.load(open(path))
    out = {}
    for x in d.get("candles", []):
        ts, c = (x["t"], x["c"]) if isinstance(x, dict) else x
        out[int(ts)] = float(c)
    liq = {int(x["t"]): float(x["v"]) for x in d.get("liquid_sma200", [])}
    return out, liq


def weekday(ts):
    return dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).weekday() < 5


def day_str(ts):
    return str(dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date())


def sma200_at(hist, ts, liquid_today=None):
    """200-day SMA on the completed candle `ts`: (value, source). `liquid_today` = Liquid's sma200 for that candle."""
    wk = [hist[t] for t in sorted(hist) if t <= ts and weekday(t)]
    if len(wk) >= 200:
        return sum(wk[-200:]) / 200, "200 trading days"
    if liquid_today is not None:
        return liquid_today, f"Liquid sma200 ({len(wk)}/200 trading days saved)"
    cal = [hist[t] for t in sorted(hist) if t <= ts]
    if len(cal) >= 200:
        return sum(cal[-200:]) / 200, f"Liquid-style 200 calendar days ({len(wk)}/200 trading days saved)"
    return (sum(cal) / len(cal) if cal else float("nan")), f"approx: only {len(cal)} calendar candles saved"


def rsi2(closes):
    up = dn = 0.0
    for i in range(1, len(closes)):            # Wilder RSI, length 2
        d = closes[i] - closes[i - 1]
        up, dn = 0.5 * up + 0.5 * max(d, 0), 0.5 * dn + 0.5 * max(-d, 0)
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--sma200", nargs="+", required=True, help="KEY=value from get_technical_indicators")
    ap.add_argument("--history-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "history"))
    ap.add_argument("--open-dir", default=None)
    ap.add_argument("--liquid-holding", default="")
    ap.add_argument("--holding", default="", help="(old flag) same as --liquid-holding")
    ap.add_argument("--now-ms", type=int, default=None)
    a = ap.parse_args()
    now = a.now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    liq_sma = {k: float(v) for k, v in (s.split("=") for s in a.sma200)}
    liquid_holding = {h for h in (a.liquid_holding or a.holding).split(",") if h}
    open_pos = {}
    if a.open_dir and os.path.isdir(a.open_dir):
        for f in os.listdir(a.open_dir):
            if f.endswith(".json"):
                d = json.load(open(os.path.join(a.open_dir, f)))
                open_pos[d.get("market", f[:-5])] = d
    os.makedirs(os.path.join(a.workdir, "history_out"), exist_ok=True)
    warnings = []
    for k in liquid_holding - set(open_pos):
        warnings.append(f"{k}: Liquid shows a position but there is no open-position record (strategy unknown: "
                        f"add data/rsi2/open/{k} before acting on exits)")
    for k in set(open_pos) - liquid_holding:
        if a.liquid_holding or a.holding:
            warnings.append(f"{k}: open-position record but Liquid shows no position (delete the record if it closed)")
    rows = []
    for key, sym in MARKETS.items():
        cpath = os.path.join(a.workdir, "candles", f"{key}.json")
        if not os.path.exists(cpath):
            warnings.append(f"{key}: no candles file, skipped")
            continue
        candles = json.load(open(cpath))["candles"]
        hpath = os.path.join(a.history_dir, f"{key}.json")
        hist, liq_hist = load_history(hpath)
        new = {int(c["timestamp"]): float(c["close"]) for c in candles if int(c["timestamp"]) + DAY <= now}
        if hist and new and min(new) - max(hist) > DAY:
            warnings.append(f"{key}: gap in saved history between {day_str(max(hist))} and {day_str(min(new))}")
        hist.update(new)
        done = [t for t in sorted(hist) if t + DAY <= now]
        if key in liq_sma and done:
            liq_hist[done[-1]] = liq_sma[key]           # Liquid's sma200 now = on the last completed candle
        doc = {"market": key, "symbol": sym, "candles": [{"t": ts, "c": hist[ts]} for ts in sorted(hist)],
               "liquid_sma200": [{"t": ts, "v": liq_hist[ts]} for ts in sorted(liq_hist)]}
        os.makedirs(a.history_dir, exist_ok=True)
        for p in (hpath, os.path.join(a.workdir, "history_out", f"{key}.json")):
            json.dump(doc, open(p, "w"))

        wk_ts = [t for t in sorted(hist) if weekday(t) and t + DAY <= now]
        closes = [hist[t] for t in wk_ts[-30:]]
        today, yday = wk_ts[-1], wk_ts[-2]
        last, prev = hist[today], hist[yday]
        sma_t, src = sma200_at(hist, today, liq_sma.get(key))
        sma_y, _ = sma200_at(hist, yday, liq_hist.get(yday))
        sma5 = sum(closes[-5:]) / 5
        prev_below5 = closes[-2] <= sum(closes[-6:-1]) / 5
        r = rsi2(closes)
        pos = open_pos.get(key)
        row = dict(market=key, symbol=sym, date=day_str(today), close=last, rsi2=round(r, 1), sma5=round(sma5, 4),
                   sma200=round(sma_t, 4), sma200_prev=round(sma_y, 4), sma200_source=src,
                   sma200_liquid=liq_sma.get(key), above_200=last > sma_t,
                   holding=(pos or {}).get("strategy") if pos else None)
        # signals
        rsi2_buy = last > sma_t and r < RSI_ENTRY
        tr_buy = key in TR_ORDER and last > sma_t and prev <= sma_y
        row["rsi2_signal"] = "BUY" if rsi2_buy else ("EXIT" if last > sma5 and prev_below5 else "none")
        row["tr_signal"] = "BUY" if tr_buy else ("n/a" if key not in TR_ORDER else "none")
        if pos:
            if pos["strategy"] == "RSI2":
                ex = last > sma5
                row["todo"] = ("SELL: RSI2 exit, close above the 5-day SMA (needs approval)" if ex
                               else "hold (RSI2): exit on a close above the 5-day SMA")
            else:
                held = sum(1 for t in wk_ts if day_str(t) > pos["entry_date"])
                row["tr_days_held"] = held
                if last < sma_t:
                    row["todo"] = "SELL: TR exit, close below the 200-day SMA (needs approval)"
                elif held >= TR_MAX_DAYS:
                    row["todo"] = f"SELL: TR exit, {TR_MAX_DAYS} trading days held (needs approval)"
                else:
                    row["todo"] = f"hold (TR): day {held} of {TR_MAX_DAYS}; exit on a close below the 200-day SMA"
        rows.append(row)

    by = {r["market"]: r for r in rows}
    free = SLOTS - len(open_pos)
    queue = [(m, "RSI2") for m in RSI2_ORDER if m in by and by[m]["rsi2_signal"] == "BUY" and m not in open_pos]
    queue += [(m, "TR") for m in TR_ORDER if m in by and by[m]["tr_signal"] == "BUY" and m not in open_pos
              and (m, "RSI2") not in queue]
    for m, strat in queue:
        if free > 0:
            by[m]["todo"] = f"BUY ({strat}): ${NOTIONAL:,} paper long, 1x (needs approval)"
            free -= 1
        else:
            by[m]["todo"] = f"skip ({strat} setup): no free slot"
    for r in rows:
        r.setdefault("todo", "no action")
    print(json.dumps(dict(open_positions={k: v.get("strategy") for k, v in open_pos.items()},
                          free_slots_before=SLOTS - len(open_pos), rows=rows, warnings=warnings),
                     indent=1, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""RSI(2) pullback signal from Liquid daily candles (Liquid-only workflow).

Feed it the JSON of a Liquid `show_chart` call (interval 1d, limit 30) plus the `sma200` from
`get_technical_indicators` (interval 1d), e.g.:
  python3 liquid/rsi2_signal.py candles.json 7564.3

Rules (same as research/rsi2.py): long only. LONG SETUP = close > 200-day SMA and RSI(2) < 10;
EXIT = first close back above the 5-day SMA (act only if holding). Uses COMPLETED weekday candles only
(Liquid's markets trade 24/7; Saturday/Sunday candles are dropped, so Monday's close carries the weekend move).
Daily candles close at 00:00 UTC (19:00 ET in winter, 20:00 in summer).

200-day filter. Liquid's sma200 is the mean of the last 200 CALENDAR daily candles, i.e. about 143 weekday closes,
not the 200 weekday closes the backtest uses (checked 2026-11-25: 7,563-7,565 vs Liquid's 7,564.3). Dropping the
weekend candles alone changes almost nothing (weekday-only mean of the same window: 7,564.8); the window length is
what differs (research/rsi2_variants.py: the filter disagrees with the 200-weekday SMA on 4-10% of days).
PROPOSED FIX, OPT-IN (the default output is unchanged):
  --history FILE   a JSON file of past Liquid daily candles ({"candles":[{"timestamp"|"ts", "close"}, ...]}, any
                   length). It is merged with candles.json, and the weekday-only 200-day SMA is reported as
                   `sma200_weekday` once at least 200 completed weekday closes are available, with `filter_agrees`.
  --use-weekday-sma  decide the filter with `sma200_weekday` instead of Liquid's sma200 (only when it is available).
show_chart returns at most 200 candles (~143 weekdays), so the history file has to be kept by saving each day's
candles (or seeded from another daily source); see docs/backtest-log.md, 2026-11-25.
"""
import datetime as dt
import json
import sys

RSI_ENTRY = 10


def _candles(data):
    out = {}
    for c in data["candles"]:
        ts = int(c.get("timestamp", c.get("ts")))
        out[ts] = float(c["close"])
    return out


def completed_weekdays(candles_by_ts, now_ms):
    rows = []
    for ts in sorted(candles_by_ts):
        t = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc)
        if ts + 86_400_000 <= now_ms and t.weekday() < 5:
            rows.append((t.date(), candles_by_ts[ts]))
    return rows


def sma200_weekday(rows):
    """Mean of the last 200 completed weekday closes, or None if fewer are available."""
    closes = [x for _, x in rows]
    return sum(closes[-200:]) / 200 if len(closes) >= 200 else None


def signal(candles, sma200, now_ms=None, history=None, use_weekday_sma=False):
    now_ms = now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    by_ts = {int(c.get("timestamp", c.get("ts"))): float(c["close"]) for c in candles}
    rows = completed_weekdays(by_ts, now_ms)
    closes = [x for _, x in rows]
    up = dn = 0.0
    for i in range(1, len(closes)):            # Wilder RSI, length 2
        d = closes[i] - closes[i - 1]
        up, dn = 0.5 * up + 0.5 * max(d, 0), 0.5 * dn + 0.5 * max(-d, 0)
    rsi2 = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    last, sma5 = closes[-1], sum(closes[-5:]) / 5
    prev_below5 = closes[-2] <= sum(closes[-6:-1]) / 5
    extra = {}
    trend = sma200
    if history is not None:
        merged = dict(history)
        merged.update(by_ts)
        wk = sma200_weekday(completed_weekdays(merged, now_ms))
        extra = dict(sma200_weekday=None if wk is None else round(wk, 2),
                     weekday_closes=len(completed_weekdays(merged, now_ms)),
                     filter_agrees=None if wk is None else (last > wk) == (last > sma200))
        if use_weekday_sma and wk is not None:
            trend = wk
            extra["filter_used"] = "sma200_weekday"
    if last > trend and rsi2 < RSI_ENTRY:
        action = "LONG SETUP"
    elif last > sma5 and prev_below5:
        action = "EXIT"
    else:
        action = "NONE"
    return dict(date=str(rows[-1][0]), close=last, rsi2=round(rsi2, 1), sma5=round(sma5, 2), sma200=sma200,
                above_200=last > trend, action=action, **extra)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    hist = None
    if "--history" in sys.argv:
        hist = _candles(json.load(open(sys.argv[sys.argv.index("--history") + 1])))
        args = [a for a in args if a != sys.argv[sys.argv.index("--history") + 1]]
    data = json.load(open(args[0]))
    print(json.dumps(signal(data["candles"], float(args[1]), history=hist,
                            use_weekday_sma="--use-weekday-sma" in sys.argv), indent=1))

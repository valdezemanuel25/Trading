#!/usr/bin/env python3
"""RSI(2) pullback signal from Liquid daily candles (Liquid-only workflow).

Feed it the JSON of a Liquid `show_chart` call (interval 1d, limit 30) plus the `sma200` from
`get_technical_indicators` (interval 1d), e.g.:
  python3 liquid/rsi2_signal.py candles.json 7564.3

Rules (same as research/rsi2.py): long only. LONG SETUP = close > 200-day SMA and RSI(2) < 10;
EXIT = first close back above the 5-day SMA (act only if holding). Uses COMPLETED weekday candles only
(Liquid's markets trade 24/7; Saturday/Sunday candles are dropped, so Monday's close carries the weekend move).
Daily candles close at 00:00 UTC (19:00 ET in winter, 20:00 in summer).
Note: Liquid's sma200 counts calendar-day candles (weekends included), so it is close to, not identical to,
a 200 trading-day SMA.
"""
import datetime as dt
import json
import sys

RSI_ENTRY = 10


def signal(candles, sma200, now_ms=None):
    now_ms = now_ms or int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    rows = []
    for c in candles:
        t = dt.datetime.fromtimestamp(c["timestamp"] / 1000, dt.timezone.utc)
        complete = c["timestamp"] + 86_400_000 <= now_ms
        if complete and t.weekday() < 5:
            rows.append((t.date(), float(c["close"])))
    closes = [x for _, x in rows]
    up = dn = 0.0
    for i in range(1, len(closes)):            # Wilder RSI, length 2
        d = closes[i] - closes[i - 1]
        up, dn = 0.5 * up + 0.5 * max(d, 0), 0.5 * dn + 0.5 * max(-d, 0)
    rsi2 = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    last, sma5 = closes[-1], sum(closes[-5:]) / 5
    prev_below5 = closes[-2] <= sum(closes[-6:-1]) / 5
    if last > sma200 and rsi2 < RSI_ENTRY:
        action = "LONG SETUP"
    elif last > sma5 and prev_below5:
        action = "EXIT"
    else:
        action = "NONE"
    return dict(date=str(rows[-1][0]), close=last, rsi2=round(rsi2, 1), sma5=round(sma5, 2), sma200=sma200,
                above_200=last > sma200, action=action)


if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    print(json.dumps(signal(data["candles"], float(sys.argv[2])), indent=1))

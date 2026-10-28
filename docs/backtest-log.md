# Backtest log: JournalTriggersStrategy (thinkorswim)

All runs use /ES on a 5-minute chart with extended hours on and `vaSource = VWAP_STATIC`, trading 1 contract. Results come from the strategy's **FPL** (total P/L on the loaded chart) and the **GATES** label. Fills are idealized: entry at the signal candle's close, and T1 and the stop fill exactly at their price, with no commissions or slippage. "After costs" assumes about $30 per round trip (commission plus 1 tick of slippage on each side).

## 2026-10-28: filter on/off tests (30D, history ending 2026-10-27)

Each row turns off **one** filter, with everything else on.

| Run | GATES (candidates > chop > trend/band > magnet > room > fired) | Fired | FPL | Avg/trade | Verdict |
|---|---|---|---|---|---|
| All on (front-run v1) | 108 > 93 > 62 > 44 > 22 > 19 | 19 | $2,050.00 | ~$108 | baseline |
| `useFrontRun` off | 108 > 93 > 62 > 44 > 44 > 28 | 28 | $2,725.00 | ~$97 | front-run v1 too strict (-$675) |
| `useMagnetCheck` off* | 94 > 83 > 62 > 62 > 36 > 24 | 24 | $1,475.00 | ~$61 | keep magnet (+$575) |
| `useTrendFilter` off | 108 > 93 > 74 > 53 > 28 > 24 | 24 | $1,650.00 | ~$69 | keep trend filter (+$400) |
| `useBandWalk` off | 108 > 93 > 63 > 44 > 22 > 19 | 19 | $2,050.00 | ~$108 | no effect, kept as a backup |
| `useStrictTrigger` off | 156 > 138 > 65 > 46 > 23 > 20 | 20 | $1,812.50 | ~$91 | keep strict trigger (+$237.50) |

\* `useMagnetCheck` also controls the BB FAIL setup, so this row also drops BB FAIL trades.

## 2026-10-28: front-run v2 (30D, same history)

Front-run v2 changes:
- T1 is still capped `frontPad` before the first obstacle (4h/1h SMAs, previous day/week high/low).
- A trade is skipped only when the capped R:R is under `frontMinRR` = 0.7.
- With-trend trades aren't capped at all.

| Run | GATES | Fired | FPL | Avg/trade | After costs |
|---|---|---|---|---|---|
| **All on (front-run v2)** | 108 > 93 > 62 > 44 > 38 > 26 | **26** | **$2,887.50** | ~$111 | ~$2,107 |

**Current settings:** all filters on, with the defaults in `thinkorswim/JournalTriggers.ts` as of this commit.

## Caveats and next checks
- **Small, in-sample test.** About 20–28 trades over the same 30 days the filters were tuned on. Re-run on a longer or different period before trusting the numbers.
- **Forward test** for 2–4 weeks on sim, and log each signal in Notion with the Bookmap read.
- **Per-setup breakdown:** export Show Report to CSV and check which setups carry the profit.

When adding a run, append a dated section with the chart period, settings changed, GATES line, fired count and FPL.

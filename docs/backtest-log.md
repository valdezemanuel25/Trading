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

## 2026-10-29: Python backtest on Databento ES 1-minute data, 2020-01 to 2026-10

Engine: `backtest/` (`python3 backtest/run.py`). It is a rule-for-rule port of the ToS strategy, with the same settings (VWAP_STATIC, all filters on, front-run v2). Each trading day uses the most-traded ES contract (unadjusted, like /ES). Bars are 5-minute, built from 1-minute data, plus 1h and 4h bars anchored at 18:00 ET.

**Validation against ToS:** these trades match the ToS screenshots to the tick on target and stop:
- 10/27 Sweep L (T 7749.25 / S 7729.5)
- 10/27 Fail BO S (T1 7740.5 / S 7764.75)
- 10/02 VAH flip S (T1 7775.25 / S 7805.75)
- 10/13 Fail BO L (T1 7855.5 / S 7842.75)

The 4h SMA21 on 10/27 is 7703.43 vs 7703.29 in ToS. For 9/28 to 10/28, Python gives 19 trades and +$3,912.50 gross, vs ToS's 26 trades and +$2,887.50. The difference comes from window edges and small roll differences in the 4h SMA200.

**Full history (1 ES, $30/trade costs):**

| Trades | T1 / Stop / Time | Win% (T1 vs stop) | Gross | Net | Max drawdown | Profit factor |
|---|---|---|---|---|---|---|
| 1,677 | 447 / 768 / 462 | 36.8% | +$9,100 | **-$41,210** | -$48,538 | 0.89 |

Averages: +0.11 points per trade gross; wins average +11.0 pts, stops -8.0 pts, time-outs +3.0 pts. Using 1-minute bars to decide T1 vs stop inside a candle changed nothing (0 ambiguous candles).

**By setup, net $ (2020-23 / 2024-26):**

| Setup | 2020-23 | 2024-26 |
|---|---|---|
| Sweep L | -13,132 (419) | -2,198 (312) |
| Sweep S | -17,332 (344) | -2,965 (208) |
| Fail BO L | +3,730 (54) | -1,678 (48) |
| Fail BO S | -3,408 (49) | -3,778 (38) |
| BB fail L | +1,158 (31) | -1,805 (26) |
| BB fail S | -542 (46) | +1,678 (32) |
| HTF L | +510 (13) | -3,128 (8) |
| HTF S | -1,302 (3) | -770 (4) |
| VAH flip S | +1,682 (11) | -610 (12) |
| VAL flip L | +1,818 (14) | +862 (5) |

Trade counts are in parentheses.

**Conclusion:** as automated rules, the strategy has no edge over 6.8 years. It breaks even before costs and loses after them. The 30-day ToS result was a favorable stretch. Only VAL flip L is positive in both halves, and on very few trades.

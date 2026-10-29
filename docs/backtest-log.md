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

## 2026-10-29: free improvement tests (same data, 1 ES, $30/trade)

New backtest settings, all off by default, so the baseline is unchanged:
- `delta_source` (clv5 / clv1 / bvc1)
- `use_cvd_div`
- `t1_cap`
- `be_trigger`
- `disabled`

Each cell is trades, average gross points per trade, and net $.

| Config | 2020-2023 | 2024-2026 |
|---|---|---|
| A baseline | 984, +0.05, -26,820 | 693, +0.18, -14,390 |
| CVD from 1-minute close location (clv1) | 954, +0.06, -25,895 | 681, +0.26, -11,530 |
| CVD from 1-minute bulk-volume classification (bvc1) | 1011, -0.05, -32,805 | 702, +0.03, -19,910 |
| clv5 + CVD divergence gate | 280, -0.44, -14,500 | 176, -0.79, -12,205 |
| clv1 + divergence | 266, -0.01, -8,092 | 184, -0.21, -7,470 |
| B: 10:30-11:00 ET only | 385, +0.71, +2,175 | 281, +0.42, -2,505 |
| C: T1 cap 10 + breakeven at +4 | 1077, +0.54, -3,172 | 773, +0.14, -17,728 |
| D: no sweeps | 273, +0.38, -3,015 | 201, -0.63, -12,355 |
| **E = B + C** | **396, +0.53, -1,418** | **295, +0.66, +862** |
| F = B + C + D | 139, +0.89, +2,005 | 109, +0.24, -1,982 |
| G = E with clv1 CVD | 377, +0.21, -7,398 | 288, +0.49, -1,590 |

**Findings:**
- **CVD estimated from candles doesn't help.** No variant adds edge, and the divergence gate built on estimated CVD makes the average trade worse. Real aggressor data (Databento Trades) would be needed to test the journal's CVD rules properly.
- **Best combination (E):** trade only 10:30-11:00 ET, cap T1 at 10 points, and move the stop to breakeven at +4. That gives about +0.5-0.7 pts per trade gross in both periods, which is roughly breakeven after costs (0.6 pts).
- **Caveat on E:** the 10:30-11:00 window was spotted in the full 2020-2026 time-of-day table, so it isn't a clean out-of-sample result.

## 2026-10-29: real CVD from Databento trades (2026-04-02 to 2026-10-28)

Plan: `docs/real-cvd-plan.md`. Data: Databento GLBX.MDP3 `trades` for `ES.FUT`, 2026-04-01 to 2026-10-28 (about $88), kept as per-minute aggressor buy/sell volume per contract in `data/trades_1m/`. Buy + sell volume matches the 1-minute OHLCV volume of the front month to 0.01% (the rest is trades with no aggressor side), and every front-month minute is covered.

New backtest settings (all off by default, so earlier results are unchanged):
- `delta_source=real`: 5m delta = buy - sell volume of the contract `data.load_1m()` uses.
- `use_cvd_flip`: the 3-bar CVD change turns against the move on the signal candle (`flip_within` candles).
- `use_absorption`: within the last 3 candles, a candle at the extreme with large delta into the level (at least `abs_delta_mult` x its average) and a small range (no more than `abs_range_mult` x the median), both over the last 78 RTH candles.
- The CVD gates (divergence, flip, absorption) skip failed breakouts, as `use_cvd_div` already did.

Script: `python3 backtest/cvd_compare.py`. Tune = 2026-04-02 to 07-31 (4 months), check = 08-01 to 10-28 (3 months). Each cell is trades, average gross points per trade, and net $ (1 ES, $30/trade). "Gated" leaves out failed breakouts, which no CVD gate touches.

| Base | Config | Tune | Check | Gated tune | Gated check |
|---|---|---|---|---|---|
| A | clv5 (current) | 86, +0.17, -1,830 | 67, +1.07, +1,565 | 67, +0.46, -472 | 56, +1.22, +1,745 |
| A | real | 76, +0.56, -142 | 67, +0.10, -1,672 | 57, +0.73, +378 | 55, -0.20, -2,212 |
| A | clv5 + div | 23, -0.39, -1,140 | 18, +1.86, +1,135 | 3, -1.00, -240 | 6, +2.75, +645 |
| A | real + div | 26, -0.65, -1,630 | 18, +0.07, -478 | 6, -1.83, -730 | 6, -2.62, -968 |
| A | real + flip | 44, +1.28, +1,505 | 29, +1.06, +668 | 24, +2.60, +2,405 | 17, +0.81, +178 |
| A | real + absorption | 20, -0.30, -900 | 12, +1.42, +490 | 0 | 0 |
| E | clv5 (current) | 41, -0.16, -1,568 | 31, +0.68, +120 | 25, +0.31, -362 | 19, +1.58, +930 |
| **E** | **real** | **41, +0.57, -55** | **32, +1.24, +1,028** | **25, +1.52, +1,150** | **20, +2.44, +1,838** |
| E | real + div | 18, -1.07, -1,502 | 13, -1.23, -1,190 | 2, -2.38, -298 | 1, -7.00, -380 |
| E | real + flip | 27, -0.57, -1,585 | 18, +0.71, +98 | 11, -0.09, -380 | 6, +3.62, +908 |
| E | real + absorption | 16, -0.91, -1,205 | 12, -0.75, -810 | 0 | 0 |

The flip window was tuned on the tune period: `flip_within` 1 is best there on both bases, and windows of 2-3 candles are worse in the check period on A. Absorption thresholds from 1.0-2.0 x delta and 1.0-1.5 x range made no difference.

**Findings:**
- **Real CVD as the source (E): passes both halves.** On E it improves the average trade in tune (+0.57 vs -0.16) and check (+1.24 vs +0.68). E is about +$970 net over 7 months vs about -$1,450 with clv5. Real and clv5 agree on 59 of about 72 trades; the 13 trades only clv5 takes average -3.85 pts, and the 14 only real takes average -0.07. On the baseline (A) real CVD is better in tune but worse in check, so it is not a general improvement.
- **CVD flip: candidate only.** On A it improves both halves vs real CVD (+1.28 / +1.06 vs +0.56 / +0.10), with roughly half as many trades. On E it makes tune worse (-0.57 vs +0.57), so it fails the two-period rule there.
- **CVD divergence: drop.** It is worse with real CVD than with estimated CVD, and negative in both halves of E.
- **Absorption: not testable on 5-minute candles.** Absorption candles happen (about 1,300 in the window), but they line up with only 5 of 215 sweep and BB-fail candidates. A sweep candle has a wide range, so "big delta, small range" just before it is rare. A real test needs a 1-minute or tick definition at the level.
- **Noise:** the standard error of the average trade is about 0.8-1.2 pts for these samples (sd about 7-11 pts, 70-150 trades). Every difference above is within about 1 standard error. None of this is statistically significant. It is a direction, not proof.

**Rules to carry forward:**
- **Bookmap checklist (E window, 10:30-11:00 ET):** take a sweep or fade only when the trigger candle's **real** delta is in the trade's direction and the 3-candle CVD is moving with it (the strategy's `need_cvd` rule, read from Bookmap's real CVD instead of the ToS candle estimate). ToS can't compute this, so it stays a manual check.
- Keep logging the **CVD flip** (3-candle CVD turning on the trigger candle) in the Notion journal as an observation, not a rule.
- No ToS alert filter change.

## 2026-10-29: out-of-sample check of real CVD on E (2025-08-08 to 2026-03-31)

Data: Databento trades for **10:00-11:05 ET only** on each weekday (`fetch_trades.py --window 1000-1105`, $19.71), in `data/trades_1m/es_trades_1m_win1000-1105_*`. That slice is enough for E. Its CVD rules look at most 4 candles back, never at the day's total, and failed breakouts (which can fire until 13:00) don't use CVD. Check: on 2026-04 to 2026-10, cutting real delta down to 10:00-11:05 gives the same 73 E trades as the full-day data.

Nothing was re-tuned: these are E and the rules from the previous section. Script: `python3 backtest/cvd_oos.py`.

| E with | Trades | Avg gross pts (se) | Net $ | Gated (no failed breakouts) |
|---|---|---|---|---|
| clv5 (current) | 57 | +1.08 (0.91) | +1,378 | 43, +0.71, +235 |
| real | 57 | +0.59 (0.97) | -35 | 43, +0.05, -1,178 |
| real + flip | 28 | +0.72 (1.56) | +172 | 14, -0.79, -970 |

The two sources share 46 trades. The 11 trades only clv5 takes average +2.50 pts, and the 11 only real takes average -0.07. In-sample it was the reverse (-3.85 vs -0.07).

**Conclusion: real CVD does not hold up out of sample.**
- In sample (2026-04 to 10), real beat clv5 on E by about 0.7 pts/trade. Out of sample it lost by about 0.5.
- Pooled over both periods (about 130 trades each), clv5 averages about +0.59 pts and real about +0.75. That difference is far inside the noise (se about 0.6-0.7).
- **Withdrawn:** the Bookmap checklist rule from the previous section. Reading the trigger candle's delta from real CVD instead of the candle estimate isn't shown to help E.
- **Not supported:** CVD flip. On E it is worse than plain clv5 again.
- For reference, E itself (clv5) made +1.08 pts/trade gross out of sample, about +$1,380 net over 8 months on 57 trades. That is consistent with "roughly breakeven to slightly positive after costs", not a proven edge.

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

## 2026-10-30: fewer indicators (9 EMA + VWAP + volume profile only), 2020-01 to 2026-10

Question: would the strategy do as well, or better, using only the 9 EMA, VWAP and volume profile?

New backtest settings (defaults unchanged):
- `indicators=core`: only the 9 EMA, VWAP (with its 1-stdev bands) and the value area (POC/VAH/VAL, previous POC). This removes:
  - the SMA50, Bollinger Bands, 1h/4h SMAs and round numbers;
  - the previous day/week/premarket/opening-range levels;
  - so also the BB-fail, HTF-test and failed-breakout setups, the HTF bias filter, the magnet check and the front-run cap.
- `indicators=core_levels`: core plus the previous day/week high/low, premarket high/low and 5-minute opening range (plain price lines, not indicators).
- `va_source=profile`: a real developing session volume profile (`backtest/vprofile.py`), like the ToS study's live default (`vaSource = PROFILE`, ETH reset). It uses 1-minute volume spread over each bar's range, read at each 5m close with no look-ahead, and a 70% value area. Until now the backtest used the VWAP +/- 1 stdev stand-in (`VWAP_STATIC`), because ToS history shows each day's final profile.

Script: `python3 backtest/minimal_compare.py`. Each cell is trades, average gross points per trade, and net $ (1 ES, $30/trade).

| Base | Value area | Indicators | 2020-23 | 2024-26 |
|---|---|---|---|---|
| A | vwap_static | **all (current)** | 984, +0.05, -26,820 | 693, +0.18, -14,390 |
| A | vwap_static | core | 821, -0.16, -31,105 | 533, -0.20, -21,265 |
| A | vwap_static | core_levels | 1326, -0.15, -49,555 | 901, -0.16, -34,318 |
| A | profile | all | 1021, -0.02, -31,868 | 715, +0.20, -14,438 |
| A | profile | core | 988, -0.05, -32,165 | 643, +0.22, -12,378 |
| A | profile | core_levels | 1417, -0.30, -63,448 | 965, +0.20, -19,075 |
| E | vwap_static | **all (current)** | **396, +0.53, -1,418** | **295, +0.66, +862** |
| E | vwap_static | core | 282, -0.20, -11,322 | 162, -0.11, -5,748 |
| E | vwap_static | core_levels | 485, +0.25, -8,562 | 352, +0.02, -10,185 |
| E | profile | all | 407, +0.39, -4,285 | 299, +0.71, +1,718 |
| E | profile | core | 334, +0.13, -7,782 | 205, +0.06, -5,500 |
| E | profile | core_levels | 509, +0.16, -11,320 | 369, +0.16, -8,132 |
| E | vwap_static | core, no CVD | 374, -0.18, -14,670 | 227, +0.46, -1,635 |
| E | profile | core, no CVD | 456, +0.24, -8,255 | 295, +0.23, -5,462 |

**Findings:**
- **Fewer indicators is worse, not better.** On E every reduced set loses $5k-$12k more per period than the full version. The higher-timeframe pieces (1h/4h SMAs, previous day/week levels) aren't decoration; they do the filtering:
  - the HTF bias filter;
  - the magnet check, which skips fades with an untested HTF level just beyond the stop;
  - the front-run cap on T1.
  Without them the strategy takes more trades of lower quality.
- **Adding plain price levels back without those filters (core_levels) makes it worse still.** It adds sweep trades at more levels with nothing filtering them.
- **Real volume profile vs VWAP +/- 1 sd: about the same.** E with the full set is -$4,285 / +$1,718 with the real profile vs -$1,418 / +$862 with the stand-in. That's within noise, and earlier results still hold for the live ToS default (PROFILE).
- **Dropping the CVD condition doesn't help either.**
- **Where E's result comes from (full set, net $ 2020-23 / 2024-26):**
  - Fail BO L +1,230 / +2,098 (54 / 43 trades): positive in both halves.
  - Fail BO S -1,540 / -2,530: negative in both.
  - Sweeps: -2,095 / +545 (L) and -1,288 / +2,072 (S).
  - Failed breakouts need the 1h/4h SMAs, so the core sets drop them. "Long-only failed breakouts" is a lead to test out of sample, not a rule.

**Conclusion:** keep the current indicator set. Removing indicators to declutter the chart is fine for **display** (the Lite study), but the logic should keep the HTF SMAs and previous day/week levels.

## 2026-11-25: RSI(2) round 2: more markets, rule variants, the 200-day filter, live measurement

Research only when written. The user then approved three changes, which are now live (see `docs/live-setup.md`): NVDA, GOOGL and CL added; the 200-trading-day filter from saved closes; the worst-trade correction.

Script: `python3 research/rsi2_variants.py`. It uses the same data and rules as `research/multi.py`: ES, NQ, RTY and YM futures, 00:00 UTC daily closes, roll-adjusted indicators, each trade priced in its entry contract. Long only: close above the 200-day SMA and RSI(2) below 10; sell on the first close above the 5-day SMA. Unless noted, $ is 1 micro each, net of costs, and the baseline reproduces the existing results exactly ($+5,460 / $+9,474 / $+12,021).

**Acceptance rule:** a change must beat the baseline in 2020-23 **and** hold up on the 2026 holdout (2026-01 to 2026-10-28). 2024-25 is shown for context only.

**Correction:** the "-$4,990 worst trade (MNQ)" in `docs/live-setup.md` comes from the RSI(2) < 30 run. Under the live rule (RSI(2) < 10) the worst trade is **-$3,988** (MNQ, 2025-02-21 to 03-14, held 15 days). It is the same Feb-Mar 2025 slide; ES lost $2,009 on the same dates.

### 1. More markets with the same rules

**Data.** Databento `ohlcv-1d` (00:00 UTC days), 2019-01 to 2026-10-28, cost $7.85. Fetched with `backtest/fetch_daily.py` (it checks the cost first) into `data/daily/`:
- Futures: GC (gold), SI (silver), CL (WTI), BZ (NYMEX Brent), BTC and ETH (CME), outright contracts only.
- Nasdaq stocks: AAPL, NVDA, MSFT, TSLA, AMZN, GOOGL, META (`XNAS.ITCH`).

**Method.** Script: `python3 research/rsi2_markets.py`.
- Futures use the front contract by volume, rolling forward; indicators on roll-adjusted closes; each trade priced in its entry contract.
- Stocks are split-adjusted at detected split days (AAPL 4:1 2020, NVDA 4:1 2021 and 10:1 2024, TSLA 4:1 2020 and 3:1 2022, AMZN 20:1 2022, GOOGL 20:1 2022). Dividends are ignored.
- Same rules as live, weekday closes only.
- P&L in Liquid terms: **$5,000 notional per trade, 0.10% round-trip cost. Perp funding is not included.**
- Liquid symbols: `xyz:GOLD`, `xyz:SILVER`, `xyz:CL`, `xyz:BRENTOIL`, `BTC`, `ETH`, `xyz:<ticker>`.

| Market | Trades/yr | Win | Net 2020-23 | Net 2024-25 | Net 2026 holdout | Net all | Avg/trade | Worst trade | Max DD |
|---|---|---|---|---|---|---|---|---|---|
| ES (live) | 10.2 | 82% | $+344 | $+676 | $+495 (12 tr) | $+1,515 | $+24 | -$338 | -$338 |
| NQ (live) | 9.3 | 71% | $+17 | $+406 | $+452 (10 tr) | $+875 | $+16 | -$465 | -$465 |
| **NVDA** | 8.1 | 80% | $+1,531 | $+3,059 | $+743 (9 tr) | $+5,333 | $+97 | -$866 | -$1,203 |
| **GOOGL** | 7.9 | 72% | $+1,303 | $+531 | $+258 (10 tr) | $+2,091 | $+39 | -$351 | -$440 |
| **CL (WTI)** | 5.1 | 77% | $+2,323 | $+182 | $+342 (5 tr) | $+2,847 | $+81 | -$394 | -$586 |
| BTC | 6.2 | 67% | $+895 | $+351 | $+180 (2 tr) | $+1,425 | $+34 | -$1,140 | -$1,644 |
| BZ (Brent) | 5.4 | 73% | $+2,659 | $+18 | $-240 (5 tr) | $+2,437 | $+66 | -$369 | -$705 |
| ETH | 5.9 | 66% | $+1,272 | $+648 | $-84 (2 tr) | $+1,836 | $+63 | -$420 | -$1,243 |
| MSFT | 6.6 | 73% | $+2,056 | $+161 | 0 trades | $+2,218 | $+49 | -$257 | -$274 |
| META | 7.9 | 76% | $+1,788 | $+351 | $-12 (2 tr) | $+2,127 | $+65 | -$457 | -$737 |
| AAPL | 9.1 | 66% | $+1,594 | $+407 | $-189 (9 tr) | $+1,811 | $+29 | -$202 | -$222 |
| AMZN | 7.2 | 61% | $+661 | $-230 | $-30 (5 tr) | $+401 | $+8 | -$590 | -$754 |
| GC (gold) | 6.3 | 60% | $-192 | $+875 | $-675 (3 tr) | $+9 | $+0 | -$536 | -$894 |
| SI (silver) | 5.6 | 50% | $-973 | $+82 | $-1,185 (5 tr) | $-2,076 | $-55 | -$567 | -$2,190 |
| TSLA | 6.3 | 58% | $-650 | $-1,499 | $+127 (4 tr) | $-2,022 | $-47 | -$1,668 | -$3,136 |

**Selecting markets without peeking at the holdout.** Picking only on 2020-23 (net > 0) keeps 10 markets: CL, BZ, BTC, ETH, AAPL, NVDA, MSFT, AMZN, GOOGL, META.

| | 2024-25 | 2026 holdout |
|---|---|---|
| The 10 picked on 2020-23 | 152 tr, 65% win, $+5,476, **$+36/trade**, 9 of 10 positive | 49 tr, 63% win, $+967, **$+20/trade**, 4 of 10 positive |
| ES + NQ (live) | 48 tr, 83% win, $+1,082, $+23/trade | 22 tr, 95% win, $+947, $+43/trade |

The rule carries over to other markets: the 2020-23 picks stay positive as a group in both later periods. But the edge per trade on the holdout is about half of ES/NQ's, and only 4 of the 10 were positive there. **The rule travels; which markets it works best on is noisy.**

**Capital.** The $10,000 paper account at 1x holds only two $5,000 positions. With ES+NQ that never binds. Adding markets means some signals arrive with no slot free; they are skipped, first come first served, same-day ties by market name.

| Portfolio | Sizing | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|---|
| ES+NQ (live) | 2 x $5,000 | 15 tr/yr, $+361, maxDD -$530 | 24/yr, $+1,082, DD -$802 | 27/yr, $+947, DD -$6 |
| **+ NVDA, GOOGL, CL** | **2 x $5,000** | **29/yr, $+4,862, DD -$1,077** (29 skipped) | **34/yr, $+2,411, DD -$754** (26 skipped) | **43/yr, $+1,925, DD -$394** (11 skipped) |
| + NVDA, GOOGL, CL | 4 x $2,500 | 38/yr, $+2,759, DD -$701 | 47/yr, $+2,170, DD -$864 | 56/yr, $+1,145, DD -$197 |
| + NVDA, GOOGL, CL, BTC | 2 x $5,000 | 34/yr, $+5,244, DD -$1,248 | 40/yr, $+2,624, DD -$787 | 44/yr, $+2,094, DD -$394 |

**Findings:**
- **Adding NVDA, GOOGL and CL roughly doubles the trade count** (holdout 27 to 43 per year) and raises net in every period. The holdout goes from $+947 to $+1,925, at the cost of a larger drawdown (-$394 vs -$6 on the holdout, -$1,077 vs -$530 in 2020-23).
- These three are the only new markets positive in all three periods with at least 5 holdout trades.
- **BTC is also positive in all three, but:**
  - it had only 2 holdout trades;
  - its worst trade is the largest of the candidates (-$1,140);
  - CME futures skip weekends while Liquid's BTC trades 24/7;
  - funding on a crypto long is not modelled.
- **Drop:** SI, GC and TSLA (negative overall or in 2 of 3 periods) and AMZN (positive only in 2020-23).
- **Watch:** BZ, ETH, AAPL, MSFT and META (positive in 2020-23 and 2024-25, flat or negative on a thin holdout).

### 2a. Entry threshold: RSI(2) < 10 vs < 30 (portfolio, 1 micro each)

| Rule | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| **< 10 (live)** | 100 tr (31/yr), win 69%, **avg $+55**, net $+5,460, worst -$1,530, maxDD -$2,902 | 88 tr, 74%, avg $+108, net $+9,474, worst -$3,988, DD -$6,221 | 42 tr (51/yr), 83%, **avg $+286**, net **$+12,021**, worst -$752, DD -$789 |
| < 30 | 224 tr (70/yr), 67%, **avg $+28**, net $+6,260, worst -$2,138, maxDD -$7,094 | 184 tr, 69%, avg $+43, net $+7,955, worst -$4,990, DD -$10,623 | 90 tr (110/yr), 76%, **avg $+111**, net **$+9,974**, worst -$2,158, DD -$2,158 |

- RSI(2) < 30 gives 2.2x the trades, but the average trade falls by half (2020-23) to three fifths (holdout), and max drawdown is 2.4-2.7x larger.
- Net is about the same in 2020-23 and lower on the holdout.
- By market, < 30 loses money on RTY in 2020-23 (-$1,124) and on YM in 2024-25 (-$859).
- **Verdict: drop.** More trades, not more profit, and fails on the holdout.

### 2b. Time stop: also exit N trading days after entry (portfolio, 1 micro each)

| Exit rule | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| **5-day SMA only (live)** | net **$+5,460**, worst -$1,530, DD -$2,902 | $+9,474, worst -$3,988, DD -$6,221 | **$+12,021**, worst -$752 |
| + 5-day time stop | $+3,374, worst -$2,006, DD -$4,216 | $+13,482, worst -$1,577, DD -$2,347 | $+11,215, worst -$636 |
| + 7-day time stop | $+4,379, worst -$2,196, DD -$4,245 | $+10,928, worst -$2,166, DD -$3,374 | $+11,927, worst -$846 |
| + 10-day time stop | $+4,395, worst -$1,530, DD -$3,332 | $+11,140, worst -$2,908, DD -$4,426 | $+12,021 (unchanged) |

- Only 38 of 238 trades last more than 5 days, 17 more than 7, and 8 more than 10.
- A time stop cuts the Feb-Mar 2025 loser (worst trade -$3,988 becomes -$1,577 with a 5-day stop), which is why 2024-25 improves.
- In 2020-23 it is worse at every N: slow trades there tended to recover, and the worst trade gets worse (-$2,006 / -$2,196).
- On the holdout it is the same or lower.
- **Verdict: drop.** It helps the one period that contains the big loser and fails both test periods.

### 2c. Volatility sizing: flat $5,000 vs ATR-scaled notional (Liquid sizing, 0.10% round-trip cost assumed)

ATR-sized notional = 57.4 / (ATR14 / close). This averages $5,000 in 2020-23; per-trade sizes ranged $2,186-$8,717 and never needed leverage above 2x.

| Sizing | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| **Flat $5,000 (live)** | net **$+1,250**, worst -$342, maxDD -$773, net/DD 1.6, trade Sharpe 0.77 | $+1,142, worst -$465, DD -$865, net/DD 1.3, Sharpe 0.91 | **$+1,532**, worst -$160, DD -$204, net/DD 7.5, Sharpe 4.26 |
| ATR-scaled | $+1,183, worst -$282, DD -$819, net/DD 1.4, Sharpe 0.81 | $+1,074, worst -$374, DD -$881, net/DD 1.2, Sharpe 0.91 | $+1,177, worst -$131, DD -$215, net/DD 5.5, Sharpe 3.91 |

- ATR sizing trims the worst trade by about 20%.
- Net, drawdown and net/maxDD are no better in 2020-23 and worse on the holdout. Calm, rising markets (where it sizes up) and stressed ones (where it sizes down) did not differ enough in edge.
- **Verdict: drop.** Keep the flat $5,000.
- For scale: $5,000 notional is about 1/7 of one MES and 1/10 of one MNQ, so the paper P&L is about a tenth of the micro numbers above.

### 3. Signal accuracy: Liquid's sma200 vs a 200-trading-day SMA

**What Liquid computes:**
- `sma200` from `get_technical_indicators` is the mean of the last **200 calendar daily candles**: 7,563-7,565 from `show_chart` vs 7,564.3 reported (candles saved in `research/data/liquid_sp500_1d_200.json`).
- Those 200 candles hold only **142-143 weekday closes**, so it is roughly a 143-trading-day average.
- Dropping the weekend candles from the same window barely moves it (7,564.8, a 0.02% difference). Weekend perp prices sit close to Friday's close.

**How often it changes the filter.** Simulated on the futures data since 2021, with weekend candles filled with Friday's close:

| Market | Days where above/below the 200-day differs: Liquid-style vs 200 weekdays | Same, weekdays-in-window vs Liquid-style | RSI(2)<10 days with a different filter | Median gap between the two SMAs |
|---|---|---|---|---|
| ES | 5.8% | 0.20% | 15 of 157 | 1.5% |
| NQ | 4.4% | 0.13% | 10 of 160 | 2.1% |
| RTY | 10.2% | 0.53% | 23 of 185 | 1.6% |
| YM | 5.7% | 0.07% | 20 of 181 | 1.1% |

**Backtest with each filter (portfolio, 1 micro each):**

| Filter | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| **200 weekdays (what the backtest assumes)** | 100 tr, $+5,460 | 88 tr, $+9,474 | **42 tr, $+12,021** |
| Liquid sma200 (200 calendar candles) | 94 tr, $+8,753 | 81 tr, $+8,544 | 37 tr, $+9,764 |
| Weekday closes inside the same window | 95 tr, $+9,037 | 81 tr, $+8,544 | 37 tr, $+9,764 |

**Findings:**
- **It matters.** The live filter disagrees with the tested one on about 1 day in 17 (ES and NQ). On the holdout it would have skipped 5 of 42 trades (ES 02-05 and 03-03, RTY 03-06, YM 10-01, NQ 10-22): four winners and one -$36 loser, $2,257 in total.
- **Liquid's shorter window is not better:** it wins in 2020-23 but loses in 2024-25 and on the holdout, so it fails the acceptance rule. The 200-weekday SMA stays the reference.
- **"Weekday-only closes" alone doesn't fix it.** The weekend candles are not the problem; the window length is. A true 200-weekday SMA needs about 280 calendar candles, more than `show_chart` returns.

**Proposed fix (not applied to the live check):**
- `liquid/rsi2_signal.py` now takes `--history FILE` (past Liquid daily candles) and reports `sma200_weekday` and `filter_agrees` once 200 weekday closes exist. `--use-weekday-sma` would make it the filter.
- Without those flags the output is byte-for-byte the same as before.
- To use it, the daily check would need to save each day's candles to a history file. Seeded with today's 200 candles (142 weekdays), it reaches 200 weekdays in about 12 weeks (mid-February 2027). Seeding from an outside daily source (see item 1) would make it available at once.
- The dashboard's `signals` calc would change the same way: read the saved history instead of only the last 30 candles.
- Today it makes no difference: both indices are 5-11% below either version of the average.

### 4. Measurement: live vs backtest on the dashboard

New section "Live vs backtest" on the RSI2 Forward Test dashboard (https://claude.ai/artifact/22FJo7qvavG7uHKQSckF7L). For each closed paper trade it shows:
- the live return and P&L;
- the backtest's average trade for that market at the same size: ES +0.589% gross / $+24.4 net at $5k, NQ +0.412% / $+15.6, over 2020-2026 (file `rsi2_bt_per_trade.json` on the dashboard);
- the difference between the two.

It also shows the **close-timing gap**: the live return (Liquid's 00:00 UTC closes) minus the futures return between the CME settlements on the same entry and exit dates. An editor enters the two settlement prices per trade in a small form on the page. They are stored with the dashboard (`data/settlements`), because no connected source has CME settlements.

The section stays empty until a paper trade closes. Close timing is worth watching: ES alone made $+28,500 (16:00 ET closes, `rsi2.py`) vs $+18,075 (00:00 UTC closes, `multi.py`) in 2020-23 on the same 25 signals, and $+21,202 vs $+39,840 on the holdout.

### Recommendation

| Item | Verdict |
|---|---|
| RSI(2) < 30 entry | **Drop.** Half the profit per trade, 2.5x the drawdown, lower holdout net. |
| Time stop (5/7/10 days) | **Drop.** Only helps 2024-25 (the Feb 2025 loser); worse in 2020-23 and not better on the holdout. |
| ATR sizing | **Drop.** Smaller worst trade, but lower net and net/DD in both test periods. Keep $5,000 flat. |
| 200-day filter: Liquid's 200-calendar-candle sma200 | **Fix (pending your approval).** It differs from the tested 200-weekday SMA on ~5% of days and would have skipped 5 holdout trades worth $2,257 net. Keep a Liquid daily-close history and use `sma200_weekday` once it has 200 weekdays; until then, show both on the dashboard. |
| Live-vs-backtest section | **Adopted** (measurement only, no rule change). |
| More markets | **Adopt NVDA, GOOGL and CL (WTI)** on Liquid (`xyz:NVDA`, `xyz:GOOGL`, `xyz:CL`), $5,000 each, at most 2 open positions, first signal first. Watch BTC, BZ, ETH, AAPL, MSFT and META. Drop SI, GC, TSLA and AMZN. Caveat: the selection used all periods; picked on 2020-23 alone the new markets made about half of ES/NQ's per-trade edge on the holdout. |
| Docs | Correct the worst trade in `docs/live-setup.md` to -$3,988 (MNQ, RSI(2) < 10) once you approve live-doc edits. |

## 2026-11-25: new strategies beside the live RSI(2) rule (research only)

**Question.** All five live markets are below their 200-day SMA, so RSI(2) rarely fires. Which daily or weekly strategies could share the two $5,000 slots?

**Status.** Research only. No live rule, scheduled task or Liquid order changed.

**Script and data.** `python3 research/strategies2.py`, on the Databento daily data already in `data/daily/` (no new data bought).
- Every market is one daily series. Futures are chained front contracts into a total-return index, so rolls add no jump. Stocks are split-adjusted.
- Decisions and fills at the 00:00 UTC daily close.
- $5,000 per trade, 0.10% round-trip cost, no funding.
- Portfolio: 2 slots shared with the live RSI(2) rule; RSI(2) wins same-day ties, otherwise first come first served.
- This engine's RSI(2) baseline differs slightly from `rsi2_markets.py` (total-return index instead of entry-contract pricing): 2 slots, live five = 2020-23 $+5,082, 2024-25 $+2,198, 2026 holdout $+1,766.

**Selection rule.** Markets and settings are picked on 2020-23 only, then checked on the 2026 holdout (to 2026-10-28). 2024-25 is context. A strategy is accepted only if it is positive in 2020-23 **and** holds on the holdout, both on its own and in the shared portfolio.

### 1. Trend reclaim (long): first close back above the 200-day SMA

Tested on the live five, the watch list, RTY and YM. Exit on a close back below the SMA, or after N days.

| Exit | Picked on 2020-23 (Liquid markets, net > 0) | Own result 2020-23 / 2024-25 / holdout | Portfolio with RSI(2): 2020-23 / 2024-25 / holdout |
|---|---|---|---|
| Close below SMA only | AAPL BTC BZ CL ES ETH GOOGL MSFT NQ NVDA | $+81,594 / $+1,747 / $+15,181 (win 22%) | $+46,865 / **$-2,942** / $+10,725 |
| or 10 days | AAPL BTC BZ NQ NVDA | $+5,652 / $-622 / $+1,895 | $+10,559 / $+1,593 / $+3,063 |
| **or 20 days** | AAPL BTC BZ CL GOOGL NQ NVDA | $+7,213 / $-724 / $+3,351 | $+14,171 / $+2,885 / $+3,706 |
| **or 20 days, live markets only (CL, GOOGL, NQ, NVDA)** | the four live ones from the 20-day list | **$+3,301 / $+13 / $+2,482** (37 / 41 / 12 trades, win 30% / 27% / 58%, worst -$377, max DD -$1,950) | **$+9,362 / $+2,665 / $+3,495** (RSI(2) alone $+5,082 / $+2,198 / $+1,766) |

- **It's a trend-follower:** 20-30% winners, small losses, a few large wins.
- **The "close below SMA" exit is dominated by a few huge holds:** NVDA 2023-25 is $+39,630 of the 2020-23 result, and one 2026 Brent trade is $+7,149. It holds slots for months, crowds out RSI(2) and loses $2,942 in 2024-25 in the portfolio. Too dependent on one or two trades.
- **The 20-day cap keeps the trades short** (9 days on average) and is positive in the portfolio in all three periods.
  - Choosing 20 days over "below SMA only" used 2024-25 (context), not the holdout.
  - Choosing 20 days over 10 used 2020-23.
- **It fires when RSI(2) can't:** 65 of 90 entries on the four live markets came on days RSI(2) held nothing. Those are exactly the days just after a market reclaims its 200-day.
- **Holdout caveat:** only 12 trades.

### 2. RSI(2) < 10 below the 200-day SMA (what variant B adds)

Live five markets, entry only when the close is at or below the 200-day SMA, exit on the first close above the 5-day SMA.

| Market | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| ES | 21 tr, 71% win, $+449, worst -$328 | 4 tr, $+74 | 3 tr, $+130 |
| NQ | 20 tr, 70%, $+271, worst -$369 | 5 tr, $+206 | 3 tr, $+224 |
| NVDA | 17 tr, 76%, $+2,407, worst -$434 | 5 tr, $+2,020 | 3 tr, $+528 |
| GOOGL | 24 tr, 62%, $+266, worst -$488 | 9 tr, $+719 | 3 tr, $-132 |
| CL | 27 tr, 48%, **$-3,397**, worst -$1,909 | 21 tr, $+793 | 1 tr, $+321 |
| **Picked on 2020-23 (ES, NQ, NVDA, GOOGL)** | 82 tr (20/yr), 70%, $+3,393, DD -$1,520 | 23 tr, $+3,019 | 12 tr, 83%, $+749, worst -$493 |
| Portfolio with RSI(2) | $+6,748 (vs $+5,082) | $+4,277 (vs $+2,198) | $+1,878 (vs $+1,766) |

- **Buying deep dips below the 200-day pays on the indices and the two stocks. It doesn't pay on WTI:** -$3,397 in 2020-23, with a -$1,909 trade in the 2020 oil crash.
- 83 of 117 entries came while RSI(2) held nothing.
- On the holdout it adds only $+112 in the portfolio.
- **Variant B as one rule** (no filter at all) on the live five is worse than the live rule in 2020-23 ($+2,182, DD -$5,014). The filter earns its keep on WTI.

### 3. Weekly momentum rotation

Universe: the live five plus BTC, BZ, ETH, AAPL, MSFT and META. At the last weekday close of each week, hold the top 1 or 2 by mean(63-day, 126-day return), only among markets above their 200-day SMA.

| Top | Own result 2020-23 / 2024-25 / holdout | Portfolio with RSI(2) |
|---|---|---|
| 1 | $+15,990 / $+1,896 / **$-299** (14 tr) | $+19,468 / $+2,677 / **$+795** (vs $+1,766) |
| 2 | $+23,397 / $+9,289 / $+200 (19 tr, 37% win) | $+23,604 / $+9,178 / **$-207** (vs $+1,766) |

- Strong in 2020-25 (NVDA and BTC trends), but flat to negative on the 2026 holdout.
- It holds both slots for weeks (average hold 22-31 trading days), so RSI(2) took only 3 trades on the holdout with top 2.
- Fails the holdout.

### 4. Catastrophe stop on the live RSI(2) rule

Stop at k x ATR(14) below entry, checked on daily lows, filled at the stop or the open if lower.

| Stop | Worst trade (live five) | Portfolio 2020-23 / 2024-25 / holdout |
|---|---|---|
| None (live) | -$866 (NVDA) | $+5,082 / $+2,198 / $+1,766 |
| 2x ATR | -$666 | $+3,351 / $+2,129 / $+1,894 |
| 3x ATR | -$820 | $+3,931 / $+2,302 / $+1,766 |

- **A wide stop barely trims the worst trade, and costs $1,150-1,730 in 2020-23.** RSI(2) losers usually come back. After a stop the rule often re-enters and loses again (CL holdout: -$666 with the stop vs -$526 without).
- At $5,000 a trade the worst loss without a stop is already only -$866.

### 5. Spread mean reversion (optional)

Long the cheap leg, short the rich leg, $5,000 each, so a trade uses both slots. Entry at a 20-day z-score of 2 or more; exit when z crosses 0 or after 20 days.

| Pair | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| Brent vs WTI | 38 tr, $-263 | 16 tr, $-85 | 8 tr, $+322 |
| GOOGL vs Nasdaq 100 | 42 tr, $-767 | 21 tr, $-575, worst -$1,243 | 8 tr, $-76 |

Both negative in 2020-23. Drop.

### Combining the two that pass

| RSI(2) live plus | 2020-23 | 2024-25 | 2026 holdout | Max DD (worst period) |
|---|---|---|---|---|
| nothing (live) | $+5,082 | $+2,198 | $+1,766 | -$1,077 |
| **trend reclaim, 20-day cap, CL/GOOGL/NQ/NVDA** | **$+9,362** | **$+2,665** | **$+3,495** | -$1,247 |
| DIP on ES/NQ/NVDA/GOOGL | $+6,748 | $+4,277 | $+1,878 | -$1,486 |
| both | $+9,970 | $+4,599 | $+2,639 | -$1,686 |

Adding DIP on top of the trend reclaim lowers the holdout (it takes slots the reclaim trades would use).

### Proposed (not switched on): log Liquid positioning daily

Add one step to the daily check, after the signals:
- For each live market, call `analyze_market` and save one document to the dashboard store: collection `data/rsi2/positioning`, doc id `<YYYY-MM-DD>_<KEY>`.
- Fields:
  - `date`, `symbol`, `markPx`;
  - `funding_pct` (number from "0.0006%");
  - `oi_usd`, `day_volume_usd`;
  - `smart_long_pct` and `crowd_long_pct`, parsed from the smartMoney line ("smart money 35% long vs losing crowd 80% long");
  - the per-size-bucket `bias` (10 numbers) and `createdAt`.
- About 2 KB per market per day.
- No order or rule depends on it.

**Test after enough trades:**
- whether entries with smart money below the crowd (a contrarian gap) do better than the rest;
- whether high funding before an entry hurts.

At about 40-60 signals a year across the live rules, a first look needs 6-12 months of logging. Nothing can be backtested earlier, because Liquid has no history of this data.

### Adopt / drop / watch

| Strategy | Verdict | Why |
|---|---|---|
| **Trend reclaim, exit below the 200-day or after 20 days, on CL, GOOGL, NQ, NVDA** | **Adopted 2026-11-25** (with one position per market: portfolio $+7,974 / $+3,088 / $+3,495) | Positive in 2020-23 ($+3,301) and on the holdout ($+2,482, 12 trades); in the shared portfolio better in all three periods ($+9,362 / $+2,665 / $+3,495 vs $+5,082 / $+2,198 / $+1,766). Fires when RSI(2) is standing aside. |
| RSI(2) < 10 below the 200-day (DIP) on ES, NQ, NVDA, GOOGL | **Watch** | Passes the rule ($+3,393 / holdout $+749) but adds only $+112 on the holdout in the portfolio and lowers it when combined with the trend reclaim. Never on CL. |
| Trend reclaim with no time cap | Drop | Result rests on one or two multi-month holds; loses $2,942 in 2024-25 in the portfolio. |
| Weekly momentum rotation (top 1 or 2) | Drop | Negative or flat on the 2026 holdout; blocks RSI(2) for weeks. |
| Catastrophe stop 2x / 3x ATR | Drop | Costs $1,150-1,730 in 2020-23 to trim the worst trade by $0-200. |
| Brent/WTI and GOOGL/Nasdaq spreads | Drop | Negative in 2020-23; each trade takes both slots and needs a short leg. |
| Positioning log | **Adopted 2026-11-25** | Data collection only; test as a filter after 6-12 months. |

## 2026-11-25: intraday entries for the live rules, and what Liquid's orders allow (research only)

No live rule, scheduled task or Liquid order changed. Script: `python3 research/intraday_entries.py`. Same engine and costs as `research/strategies2.py`. Portfolio: 2 slots x $5,000, one position per market, RSI(2) first on ties.

### What Liquid's order tools allow for entries (from the connector's tool schemas, 2026-11-25)

| Need | Possible? | How / why not |
|---|---|---|
| Market entry | Yes | Sent as an immediate-or-cancel limit at mid +/- `maxSlippageBps` (1-500). |
| Resting limit buy | Yes | `type: limit` with `timeInForce` `gtc` (rests until filled or cancelled), `ioc` or `alo` (post-only). |
| Order expiry (good-till-date) | **No** | `gtc` has no expiry. The agent must cancel stale orders itself. |
| Buy-stop / stop-limit / trigger entry | **No** | Only `market` and `limit`. Liquid's own tool text: "A plain limit is not a breakout trigger." A buy limit above the market just fills at once. |
| TP / SL attached at entry | Yes | `tp` and `sl` trigger prices on the order. They are not placed if the order only partly fills; then add them later with `modify_position`. |
| Resting exit orders | Yes | Reduce-only limit sells, native trailing stops (`set_trailing_stop`), and TP/SL triggers on a position. |
| Change an order in place | **No** | No modify-order tool: moving an order means cancel and place a new one. |
| Baskets | Yes | Up to 8 orders confirmed together. |
| Approvals | Every order | Every new order (and TP/SL change) needs an explicit chat confirmation of the exact previewed terms in the session that places it. A cancel needs only the user's request. The saved "automated trading" policy authorizes nothing. |
| Paper mode | Unknown for resting orders | The paper simulator handles orders, but whether a paper `gtc` limit really rests and fills on a touch is untested; it needs one small approved test order. |

### a. Trend reclaim: buy-stop at the 200-day SMA vs the close-based entry

The buy-stop entry rests at yesterday's 200-day SMA while the last close is at or below it. It fills if the day's high reaches the level, at the level (or the open if it gaps above). The entry day's own close can already exit it.

| CL, GOOGL, NQ, NVDA | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| Close entry (live) | 37 tr, 30% win, $+3,301, DD -$1,950 | 41 tr, $+13 | 12 tr, $+2,482 |
| Buy-stop entry | 80 tr, 19% win, $+3,425, DD -$2,420 | 68 tr, $+814 | 22 tr, $+3,020 |
| **Portfolio, live** | $+7,974, DD -$1,232 | $+3,088 | $+3,495 |
| **Portfolio, RSI(2) close + TR buy-stop** | **$+8,312**, DD -$1,021 | **$+3,874** | **$+4,094** |

- **False breakouts are common:** 83 of 176 fills (47%) closed back below the SMA the same day, losing $5,162 in total (2020-23 -$3,070, holdout -$374). The earlier entry on the real breakouts more than pays for them.
- Per market, the stop is better on NQ (2024-25), NVDA and GOOGL, and worse on CL in 2020-23 (-$343 vs $+236).
- **It passes the rule:** better in the portfolio in all three periods, and the holdout is $+599. Liquid can't rest a buy-stop, though (see above), so the backtest's fill at the level is optimistic.

### b. RSI(2): resting limit buy at the RSI(2) = 10 price vs the close-based entry

The limit price is the highest price at which today's close would give RSI(2) < 10, placed only when that price is above yesterday's 200-day SMA. It fills if the day's low reaches it.

| All five | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| Close entry (live) | 121 tr, avg $+46, $+5,615 | 93 tr, $+4,640 | 46 tr, avg $+47, $+2,158 |
| Limit entry | 207 tr, avg $+34, $+7,003 | 138 tr, $+4,845 | 69 tr, avg $+24, **$+1,619** |
| **Portfolio, RSI(2) limit + TR close** | **$+6,836** (vs $+7,974) | $+3,543 | $+3,586 (vs $+3,495) |

- The limit fills on many intraday dips that recover by the close. Those were the good ones (avg $+60).
- Fills where the close also gave RSI(2) < 10 averaged $-1: buying before the close on a falling day gets a worse price than waiting.
- In the shared slots it crowds out better trades: $-1,138 in 2020-23. **Fails.**

### c. Pre-close decision at 15:45 ET (ES only: the only market with 1-minute data here)

| ES RSI(2) | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| Decide + fill at the 00:00 UTC close (live) | 25 tr, $+343 | 25 tr, $+676 | 12 tr, $+495 |
| Decide + fill at 15:45 ET | 25 tr, $+736 | 26 tr, $+698 | 11 tr, $+487 |
| Portfolio (ES at 15:45 ET, rest unchanged) | $+8,435 (vs $+7,974) | $+3,065 (vs $+3,088) | $+3,569 (vs $+3,495) |

- 44 of 62 entry days are the same at both times.
- Deciding at the US cash close is at least as good as waiting for Liquid's 00:00 UTC close: better in 2020-23, equal since. It passes, but only for ES.
- Testing NQ, CL, NVDA and GOOGL needs 1-minute data. Databento quote: front-month continuous ohlcv-1m 2020-01 to 2026-10, NQ $8.80, CL $8.72, NVDA $0.90, GOOGL $0.77, **about $19.20** (all contracts instead: $191). Not bought.
- **The same data would also test the realistic version of (a):** entering at the first hourly check after the cross, plus approval delay, instead of at the level.

### Adopt / drop

| Change | Verdict | Why |
|---|---|---|
| TR entry by buy-stop at the 200-day SMA | **Adopt in principle; needs a realistic test first** | Portfolio better in all three periods ($+8,312 / $+3,874 / $+4,094 vs $+7,974 / $+3,088 / $+3,495). Liquid has no stop orders, so live it is "order agent sees the price above the level, proposes a market buy, you approve". The fill comes later than the level, and nothing fills while you're away. Test that version on 1-minute data (about $19) before relying on it. |
| RSI(2) entry by resting limit | **Drop** | $-1,138 in 2020-23 in the portfolio; lower average trade; worse holdout on its own. |
| Pre-close (15:45 ET) decisions | **Watch: ES passes, others untested** | ES better in 2020-23 and equal since. Needs the same 1-minute data for NQ, CL, NVDA and GOOGL. |
| RSI(2) exit by resting reduce-only limit at the mean of the last 4 closes | Not tested | A close above that price is the 5-day-SMA exit, but an intraday touch would sell early. Can be tested on the same 1-minute data. |

The order-agent design (proposed, not set up) is in `liquid/order_agent.md`.

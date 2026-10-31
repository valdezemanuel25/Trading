# Strategy search: ES intraday, 2020-01 to 2026-10

Goal (2026-10-30): find a rule-based ES strategy with a real edge after costs, free of the Journal Triggers rules.

## Method (fixed before testing)
- Data: Databento ES 1-minute bars, continuous front month (`backtest/data.py`). RTH panel in `research/panel.py`. Contract-roll days are excluded from anything that uses the previous close.
- **Train 2020-2023**: pick and tune ideas here only. **Validation 2024-2025**: the same settings must still be profitable. **Holdout 2026-01 to 2026-10**: looked at once, after the rules are frozen.
- Costs: $30 per ES round trip (commission + 1 tick slippage each side), $3 per MES.
- Prefer documented effects with textbook settings over tuned ones.

## Survey (`research/explore1.py` and inline checks), 1 ES, net $
| Idea | Train 2020-23 | Valid 2024-25 | Verdict |
|---|---|---|---|
| Overnight long (16:00 -> 09:30) | +7,788, Sharpe 0.08 | +43,800, Sharpe 0.75 | Unstable, deep drawdowns |
| Day session long | +15,740, 0.13 | +735, 0.01 | No |
| Intraday momentum, last 30 min (Gao et al.) | -50,390 | -15,022 | No |
| **Noise-boundary momentum (Zarattini et al. 2024)** | **+72,548, 1.23** | **+9,260, 0.26** | **Only effect positive in every period** |
| Opening-range breakout 5 / 15 / 30 min | -2,645 / +14,915 / +12,458 | -13,880 / +9,820 / +6,938 | Weak |
| Gap fade >= 10 / 20 pts | -13,930 / -37,615 | +8,120 / -65 | No |
| Turn of month | +54,190, 0.95 | -30,958, -0.56 | Fails validation |
| Monday open->close long | +42,942, 0.94 | +28,465, 1.05 | Best of 5 days tested, t about 2: weak |
| VWAP trend (5/15/30-min checks) | all negative or flat | all negative | No |
| 5-minute opening candle direction | -10,302 | -26,550 | No |

## Noise-boundary momentum
- Robustness:
  - grid of 48 settings (lookback 10/14/20, step 30/60, width 0.75-2.0, first check 10:00/10:30);
  - the textbook setting (14 / 30 / 1.0 / 10:00) is also the best on train;
  - 44 of 48 settings are profitable in validation.
- Volatility regime filters on train: no consistent pattern, not used.
- Volatility-targeted size (paper's method, 14-day lookback): train Sharpe 1.23 -> 1.40, validation 0.26 -> 0.63.
- Fills at the next minute's open instead of the decision bar's close: -0.03 pts/trade, negligible.

### Frozen rules (`research/final_noise.py`), committed before the holdout run
- Boundaries: max/min(open, previous close) x (1 +/- sigma_t). sigma_t is the 14-session average of |price at that minute / open - 1|.
- Checks at 10:00, 10:30 ... 15:30; fills at the next minute's open.
- Long above the upper boundary, short below the lower one.
- Exit when back past max(upper, VWAP) / min(lower, VWAP), or reverse on the opposite signal. Flat at 16:00.
- Size: 40 / (14-day std of daily close-to-close moves in points) ES, in 0.1 steps, from 0.1 to 2 ES.

| Period | Trades | Net $ | Sharpe | Max DD | Gross pts/trade |
|---|---|---|---|---|---|
| Train 2020-23 | 963 | +85,666 | 1.37 | -12,484 | +2.08 |
| Valid 2024-25 | 488 | +22,288 | 0.61 | -18,498 | +0.97 |

By year: 2020 +21,168 | 2021 +20,380 | 2022 +18,650 | 2023 +25,468 | 2024 +25,440 | 2025 -3,152.

## Holdout 2026
Run once on 2026-10-30, after the rules above were committed (503fa76). Nothing was changed afterwards.

| Period | Trades | Net $ | Sharpe | Max DD | Gross pts/trade |
|---|---|---|---|---|---|
| **Holdout 2026-01 to 10-28** | 222 | **-16,348** | **-1.36** | -19,004 | -1.30 |

By month: Jan -3,827 | Feb +2,734 | Mar +148 | Apr -1,818 | May -4,293 | Jun +5,038 | Jul -8,497 | Aug -1,340 | Sep -5,640 | Oct +1,147.

**Verdict: failed.**
- The edge was strong in 2020-2024 and flat to negative from 2025 on (2025 -3,152, 2026 -16,348).
- That fits an effect that decayed after it was published (early 2024) and became crowded, or a regime change.
- It is not a strategy to trade. The holdout has now been used, so re-tuning on 2026 would only fit noise.

## Conclusion
None of the documented intraday ES effects tested here has a durable edge after costs in 2025-2026. Neither does the Journal Triggers strategy (see `docs/backtest-log.md`). The one that did work for four years stopped working.

## 2026-10-31: session-open failed-close (user's rules), `research/session_open.py`
Rules (confirmed with the user before running; nothing tuned):
- Asia (Tokyo 09:00), London (08:00) and New York (09:30) opens, each in local time, so daylight saving is handled.
- First 15-minute (or 5-minute) candle: long if it wicks below the open and closes above it; short if it wicks above and closes below; no wick = no trade.
- Entry at the candle's close.
- 1:1 stop/target = distance to the daily VWAP (from 17:00 CT), kept between 5 and 10 pts; 7 pts if VWAP is behind the trade.
- 1h filter: longs only if the last 1h close is above the previous day's low, shorts only if it is below the previous day's high.
- Closed at the session end (Asia at the London open, London at the New York open, New York at 16:00 ET).
- 1 ES, $30/trade. Same minute stop + target = stop.

Each cell is trades, win% (target vs stop), average gross pts per trade, and net $.

| Candle | Session | 2020-23 | 2024-25 | 2026 |
|---|---|---|---|---|
| 15m | All | 2391, 51%, +0.06, -65,042 | 1222, 49%, -0.16, -46,248 | 517, 44%, -0.84, -37,335 |
| 15m | Asia | 799, 50%, -0.07, -26,882 | 395, 53%, +0.30, -5,850 | 169, 46%, -0.51, -9,408 |
| 15m | London | 781, 48%, -0.26, -33,618 | 402, 46%, -0.52, -22,548 | 172, 38%, -1.55, -18,510 |
| 15m | New York | 811, 53%, +0.49, -4,542 | 425, 49%, -0.24, -17,850 | 176, 47%, -0.47, -9,418 |
| 5m | All | 2256, 49%, -0.15, -84,068 | 1135, 49%, -0.12, -40,650 | 498, 45%, -0.64, -30,865 |
| 5m | New York | 811, 51%, +0.08, -21,030 | 415, 49%, -0.16, -15,825 | 176, 49%, -0.16, -6,668 |

- Stop and target sizes average 6.7 pts. VWAP is behind the trade about 70-77% of the time, so most trades use 7 pts.

**Verdict: no edge.**
- A 1:1 trade is won about 49% of the time, and the average gross result is about 0 pts (-0.12 over all 4,130 trades). The $30 cost (0.6 pt) then makes every session and period lose.
- Trading the opposite direction would also be about 0 pts gross, so it would lose too.
- The best cell, New York 15m in 2020-23, is +0.49 pts gross: still below costs, and negative after 2023.

## 2026-10-31: are session open prices support/resistance? `research/level_test.py`
At the first retest during NY hours (from 30 min after the open), does price bounce `x` pts back before breaking `x` pts through? Compared with control levels (the same open shifted +/-2.25, 3.75, 6.25 pts).

| Level | 5-pt bounce: open vs control | 10-pt bounce: open vs control |
|---|---|---|
| Asia open | 52.0% vs 52.5% (z -0.3) | 50.9% vs 51.2% |
| London open | **54.8% vs 51.4% (z 2.1)** | 50.8% vs 50.2% |
| New York open | 53.4% vs 51.0% (z 1.5) | 50.6% vs 49.4% |

The effect holds in every period (5-pt test, all sessions): 2020-23 53.4% vs 51.0%; 2024-25 53.9% vs 52.9%; 2026 52.2% vs 51.7%.

**Verdict: a small, short-range effect for the London and New York opens, none for Asia.**
- It is a 2-3 point bump in bounce rate over 5 pts and disappears over 10 pts.
- A 5-pt 1:1 trade needs about 56% wins to cover $30 costs, so it is too small to trade alone. At most it is confluence.

## 2026-10-31: long only with higher-timeframe filters
1. **Intraday trend pullback** (`research/long_htf.py`):
   - Buy a green 5m candle that dips to VWAP (or the previous day high / 1h SMA50) and closes back above it, while the 1h close > 1h SMA50 and the 4h close > 4h SMA21. Stop under the candle, target 1-2R.
   - **All 18 variants lose**, already before costs (-0.1 to -0.9 pts/trade).
2. **Day hold filtered by the 1h/4h trend** (09:30 -> 16:00 long):
   - On days the 1h+4h trend is **up**: -$10,875 (2020-23) / -$31,020 (2024-25).
   - On days it is **down**: +$26,615 / +$31,755.
   - So in ES, short-term weakness inside a rising market is what pays. That points to the classic pullback strategy.
3. **RSI(2) pullback (Connors), daily** (`research/rsi2.py`):
   - Indicators use roll-adjusted closes; each trade is priced in its entry contract.
   - The family was chosen after point 2 (2020-25 data). The settings are the literature's standard ones, fixed before the 2026 holdout was run once.

| Variant | 2020-23 | 2024-25 | **2026 holdout** |
|---|---|---|---|
| **A: close > 200d SMA, RSI(2) < 10, exit close > 5d SMA** | 25 tr, 72% win, +23.4 pts, **+$28,500**, PF 2.4 | 25 tr, 92%, +46.0 pts, **+$56,800**, PF 13.2 | 12 tr, 67%, +35.9 pts, **+$21,202**, PF 3.8 |
| B: A without the 200d filter | 44 tr, 73%, +23.7, +$50,855 | 30 tr, 93%, +50.5, +$74,812 | 14 tr, 71%, +48.0, +$33,192 |
| C: A with RSI(2) < 5 | 16 tr, 81%, +31.1, +$24,408 | 14 tr, 93%, +62.5, +$43,305 | 5 tr, 100%, +107.7, +$26,775 |

- **Against a random 3-day long** (same periods): +4.3 vs +23.4 pts (t 1.5) in 2020-23, and +9.9 vs +46.0 pts (t 4.0) in 2024-25.
- **Caveats:**
  - only 62 trades in total;
  - no stop: the worst trade was -148 pts, about -$7,400 on 1 ES;
  - overnight and weekend gap risk;
  - 2020-26 was mostly a rising market;
  - the 200d filter did **not** help in this sample (B >= A), but it is the standard protection against long bear markets, which this data barely contains (2022).
- ToS versions:
  - `thinkorswim/RSI2PullbackStrategy.ts`: Show Report backtest on the /ES daily chart.
  - `thinkorswim/RSI2PullbackAlert.ts`: live setup label and alert. Check at about 15:50 ET, then act at the close.
- **Verdict: the first strategy in this search that passed train, validation and an untouched holdout.** It still needs a forward test before real money, at MES size.

## 2026-10-31: short strategy search
1. **RSI(2) mirror, daily** (`research/rsi2.py --short`): short at the close when RSI(2) > 90 (and close < 200d SMA); cover at the close when close < 5d SMA.

| Variant | 2020-23 | 2024-25 | 2026 holdout |
|---|---|---|---|
| S-A: below 200d, RSI(2) > 90 | 12 tr, 67%, +34.4 pts, +$20,290 | 3 tr, -18.2 pts, -$2,828 | 1 tr, **-447.5 pts, -$22,405** (2026-04-06 -> 04-21) |
| S-B: no trend filter | 50 tr, 66%, +4.8 pts, +$10,600, PF 1.2 | 30 tr, 57%, -13.8 pts, **-$21,538** | 11 tr, -32.7 pts, **-$18,318** |
| S-C: below 200d, RSI(2) > 95 | 8 tr, +$19,398 | 2 tr, -$1,910 | 0 trades |

- ES was below its 200d SMA on only 217 days in 2022, 40 in 2023, 53 in 2025 and 17 in 2026. The filtered short made its money in the 2022 bear market and has almost no trades since.
- Without the filter, shorting sharp rallies loses in a rising market.
- With no stop, a single squeeze (April 2026, +447 pts against the short) wipes out years of gains.

2. **Noise-boundary momentum, short side only**:
   - 2020-23 +$20,230 (Sharpe 0.44); 2024-25 +$5,772 (0.20); 2026 -$13,140 (-1.21).
   - The 2026 result for both sides together had already been seen, so this is not a clean holdout.

3. Earlier intraday shorts:
   - Failed breakout shorts lost in 6 of 7 years.
   - Sweep shorts and VAH flips are inconsistent (`docs/backtest-log.md`).

**Verdict: no short strategy with an edge in 2020-2026.**
- The index's upward drift works against every short, and a short-side edge here would need bear markets, which this data barely contains.
- Practical rule: in a downtrend (close < 200d SMA), stand aside: the long RSI(2) strategy already does that.

## 2026-10-31: combined long + short (200-day regime switch)
- Above the 200d SMA: RSI(2) < 10 -> long; exit when close > 5d SMA.
- Below it: RSI(2) > 90 -> short; cover when close < 5d SMA.

| Net $, 1 ES | 2020-23 | 2024-25 | 2026 |
|---|---|---|---|
| Long only (A) | +28,500 (DD -11,960) | +56,800 (DD -3,342) | +21,202 (DD -5,622) |
| A + S-A (short below 200d) | +48,790 (DD -11,740) | +53,972 (DD -6,390) | -1,202 (DD -28,028) |
| A + S-B (short any RSI(2) > 90) | +39,100 (DD -17,538) | +35,262 (DD -9,102) | +2,885 (DD -37,238) |

- Shorts helped only in 2020-23, because of the 2022 bear market.
- The ToS files have the short side behind `enableShorts`, **off by default**.

## 2026-10-31: more trades per week? (`research/frequency.py`, long only above the 200d SMA, 1 ES)
| Variant | Trades/wk | 2020-23 | 2024-25 |
|---|---|---|---|
| RSI(2) < 10 (A) | 0.1-0.2 | +$28,500, PF 2.37 | +$56,800, PF 13.2 |
| RSI(2) < 30 | 0.4-0.5 | +$31,142, PF 1.62, DD -18,690 | +$58,222, PF 2.63 |
| RSI(2) < 50 | 0.5-0.6 | +$38,860, PF 1.65 | +$26,090, PF 1.41 |
| IBS < 0.2, sell next close | 0.7 | +$385, PF 1.00 | +$34,260, PF 1.71 |
| Down day, sell next close | 1.5-1.9 | +$6,015, PF 1.03 | +$14,700, PF 1.08 |
| Every day, sell next close | 3.4-4.4 | +$16,850, PF 1.04, DD -59,198 | +$60,422, PF 1.17 |
| 1h RSI(2) < 10 | 1.3-1.4 | -$8,228, PF 0.92 | +$20,408, PF 1.27 |

- Edge per trade falls fast as frequency rises.
- At 1-3 trades a week, what is left is mostly the market's upward drift: PF about 1.0-1.2, large drawdowns.
- RSI(2) < 30 keeps a real edge at about 2 trades a month.
- More trades without a weaker signal = the same rule on more markets (NQ, RTY, YM daily data: about $0.23 in total on Databento).

## 2026-10-31: RSI(2) pullback on four index futures (`research/multi.py`)
- Data: Databento ohlcv-1d for NQ/RTY/YM (`data/daily/`, $0.23); ES rebuilt from 1-minute bars.
- Timing: all four use the 00:00 UTC daily close, so the basis is the same. On ES this timing gives somewhat different numbers from the 16:00 ET close (RSI(2)<30: +$22k / +$43k / +$14k vs +$31k / +$58k / +$7k).
- Rules: long only, close > 200d SMA. Buy at the close when RSI(2) < 10 (or < 30); sell at the close once close > 5d SMA.

Full contracts, net $ (ES $30, others $15 per round trip):

| Market | RSI(2)<10: 2020-23 / 2024-25 / 2026 | RSI(2)<30: 2020-23 / 2024-25 / 2026 |
|---|---|---|
| ES | +18,075 / +46,438 / +39,840 | +22,915 / +36,158 / +20,390 |
| NQ | +9,425 / +43,905 / +57,570 | +43,380 / +39,590 / +28,445 |
| RTY | +10,665 / +4,840 / +12,330 | **-10,850** / +13,790 / +20,915 |
| YM | +17,440 / +440 / +10,890 | +9,395 / **-8,150** / +30,890 |

**Portfolio, 1 micro of each (MES, MNQ, M2K, MYM):**

| Variant | 2020-23 | 2024-25 | 2026 |
|---|---|---|---|
| RSI(2)<10 | 0.6/wk, 70% win, +$5,460, PF 1.51, DD -$2,902 | 0.8/wk, 74%, +$9,474, PF 1.85, DD -$6,221 | 1.0/wk, 83%, +$12,021, PF 8.4, DD -$789 |
| **RSI(2)<30** | **1.3/wk**, 67%, +$6,260, PF 1.26, DD -$7,094 | **1.8/wk**, 69%, +$7,955, PF 1.33, DD -$10,623 | **2.1/wk**, 76%, +$9,974, PF 2.10, DD -$2,158 |

- Markets signal together often: 34-41% of signal days have 2+ markets, and up to 4 positions are open at once.
- Worst single micro trade: -$4,990 (MNQ, entered 2025-02-20, held through the spring 2025 selloff; no stop).
- **Verdict:**
  - RSI(2)<30 across four micros gives the requested 1-3 trades a week, and it is positive in every period.
  - The edge per trade is thinner than RSI(2)<10 (PF 1.3 vs 1.5-1.9).
  - Individual markets have losing periods, but the portfolio did not.
  - In ToS: run `RSI2PullbackAlert.ts` on /MES, /MNQ, /M2K and /MYM daily charts, with `rsiLongEntry` = 30 for more trades or 10 for stronger ones.

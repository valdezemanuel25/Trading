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

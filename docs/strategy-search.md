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
(Not run yet at the time of this commit.)

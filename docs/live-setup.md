# Live setup and handoff (as of 2026-11-25)

Read this first in a new session. Research history: `docs/strategy-search.md` and `docs/backtest-log.md`.

## What runs
Two forward tests. Neither is proven for real size.

### 1. Journal Triggers, variant E (intraday, ToS sim)
| Item | Setting |
|---|---|
| ToS study | `thinkorswim/JournalTriggers.ts` (the user's chart names it "JournalStrat") |
| Chart | /ES or /MES **5-minute**, extended hours on |
| Inputs | `winStart = 1030`, `winEnd = 1100` (failed breakouts fire until `fboEnd` 13:00) |
| Manual exits | T1 capped at 10 pts; stop to breakeven at +4 pts; close after 12 candles (1 h) |
| Alerts | In-platform only: sound, pop-up and Message Center. Text: `JT \| <setup> \| <Long/Short> \| check Bookmap` |
| Log | Notion **E Signals** on the page "Forward Test: Journal Triggers E" (private). Every signal by hand, losers and skips included |
| Backtest | Roughly breakeven to slightly positive after costs |

### 2. RSI(2) pullback (daily, long only), paper traded on Liquid
| Item | Setting |
|---|---|
| Rules | Close > 200-day SMA and RSI(2) < 10 -> buy at the close; sell at the close once close > 5-day SMA. No shorts, no stop |
| Signal source | ToS `thinkorswim/RSI2PullbackAlert.ts` on **/MES** and **/MNQ daily** charts (`market` input set per chart, `rsiLongEntry = 10`). Check at about 15:50 ET / 14:50 CT |
| Execution | **Liquid paper trading**: `xyz:SP500` (for /MES) and `xyz:XYZ100` (for /MNQ). Liquid has no Russell or Dow |
| Size | $5,000 notional per market at 1x leverage; both can be open at once ($10k paper account) |
| Order flow | The user says e.g. "RSI2 long S&P" or "RSI2 exit Nasdaq". Claude prepares the paper order, the user approves the exact order, then Claude executes it |
| Log | Notion **RSI2 Signals** on the page "Forward Test: RSI(2) Pullback" (private). Claude adds a row per trade: entry, exit, points, days held |
| Backtest (4 micros, 1 each, net) | 2020-23 +$5,460, 2024-25 +$9,474, 2026 holdout +$12,021. Worst single trade -$4,990 (MNQ) |

**Liquid account state:**
- Paper mode is ON in the user's mobile app **and** on Claude's Liquid connection (enabled 2026-11-25).
- Paper account: $10,000, no positions.
- Each platform keeps its own mode. Before any order, check `paper_trading_status`, and keep Liquid's own order-approval rules.
- Liquid's indicator tool gives the SMA200 but not RSI(2) or the 5-day SMA: signals come from ToS.

**Market state on 2026-11-25:**
- Both indices are below their 200-day SMA (S&P500 7,181 vs 7,564; NASDAQ100 26,127 vs 29,292).
- The strategy is standing aside; no trades until a close back above the 200-day.

## Not used (tested 2026-11)
- **ToS study alerts can't be emailed.** `Alert()` in a chart study fired in the platform only; no email reached Gmail with "Alert is triggered -> Send e-mail" on. So the email -> Zapier -> Notion plan was dropped.
- **Zapier's connection can't build Zaps.** It runs single actions only.
- **Logging is by hand,** about 2-3 rows a week in total.
- **No scheduled tasks:** the user doesn't want them run from Claude sessions.

## Tested, no durable edge (don't revisit without new data)
- Journal Triggers on default settings.
- Real-CVD filters, CVD divergence, flip and absorption.
- Fewer-indicator versions.
- Noise-boundary momentum (failed the 2026 holdout).
- Session-open failed close.
- RSI(2) shorts.
- ORB, gap fade, VWAP trend, turn of month.

## Open questions for the next session
- **Notion journal:** its 60 logged trades average +8 pts, but Jun-Oct shows 96% wins (losers probably not logged). The Oct 22 fully-logged day was breakeven. A complete log for 4-6 weeks decides whether the discretionary version has an edge.
- **Code location:** everything (code, data, docs) is on branch `claude/real-cvd-plan-bgj7d7`. The ToS files were also copied to `claude/trading-chart-trigger-winners-8ne4fd`. `main` has only the raw data upload.

# Live setup and handoff (as of 2026-11-25)

Read this first in a new session. Research history: `docs/strategy-search.md` and `docs/backtest-log.md`.

**New work in progress (2026-11-26):** intraday **stock** strategy research (VWAP / Trend Join Long, Liquid stock perps), research only, nothing built: `docs/intraday-stock-research.md`.

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

### 2. RSI(2) pullback (daily, long only): Liquid only
Decision 2026-11-25: Liquid only for this strategy. **No ToS and no Zapier.**

| Item | Setting |
|---|---|
| Rules | Long only. Close > 200-day SMA and RSI(2) < 10 -> buy. Sell on the first close back above the 5-day SMA. No shorts, no stop |
| Markets | Liquid **paper**: `xyz:SP500` and `xyz:XYZ100` (no Russell or Dow on Liquid) |
| Data | Liquid `show_chart` (1d, limit 30) for the candles and `get_technical_indicators` (1d, sma) for the SMA200. Compute with `liquid/rsi2_signal.py`: completed **weekday** candles only, 00:00 UTC closes |
| Daily check | The user sends one message, e.g. **"RSI2 check"**, any time after the daily candle closes (00:00 UTC = 7 PM ET winter / 8 PM summer). Claude fetches both markets, computes the signal and reports LONG SETUP / EXIT / NONE |
| Orders | On LONG SETUP, or EXIT while holding: Claude prepares the paper order ($5,000 notional, 1x), the user approves the exact order, Claude executes it. Liquid requires this approval for every order |
| Log | Liquid's own history (`get_position_history`, `get_portfolio`) is the trade log. The Notion RSI2 Signals page is optional |
| Backtest (00:00 UTC closes, 1 micro each, ES+NQ part of research/multi.py) | Positive in every period. Worst single trade -$4,990 (MNQ); no stop |

**Why one manual message a day:**
- Liquid has no alerts or scheduler. Its "automated trading" tool only saves a spending limit.
- The user doesn't want scheduled tasks run from Claude sessions.
- Every Liquid order needs the user's explicit approval anyway.

**Liquid account state:**
- Paper mode is ON in the user's mobile app **and** on Claude's Liquid connection (enabled 2026-11-25).
- Paper account: $10,000, no positions.
- Each platform keeps its own mode. Check `paper_trading_status` before any order.

**Signal on 2026-11-24 (last completed candle):**
- S&P500: close 7,184.9, RSI(2) 49.8, SMA200 7,564 -> NONE (below the 200-day).
- NASDAQ100: close 26,143, RSI(2) 42.1, SMA200 29,292 -> NONE (below the 200-day).
- No trades until a close back above the 200-day SMA.

## Not used (tested 2026-11)
- **ToS study alerts can't be emailed.** `Alert()` in a chart study fired in the platform only; no email reached Gmail with "Alert is triggered -> Send e-mail" on. So the email -> Zapier -> Notion plan was dropped.
- **Zapier's connection can't build Zaps.** It runs single actions only.
- **Logging:** Journal Triggers E by hand in Notion; RSI(2) uses Liquid's own history.
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
- **Code location:** everything (code, data, docs) is on `main` (merged 2026-11-25 from `claude/real-cvd-plan-bgj7d7`).

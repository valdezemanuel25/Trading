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

### 2. RSI(2) pullback (daily, long only): Liquid only
Decision 2026-11-25: Liquid only for this strategy. **No ToS and no Zapier.**
Updated 2026-11-25, approved after the research in `docs/backtest-log.md` ("RSI(2) round 2"):
- three markets added;
- the 200-trading-day filter;
- the worst-trade figure corrected.

| Item | Setting |
|---|---|
| Rules | Long only. Close > 200-day SMA and RSI(2) < 10 -> buy. Sell on the first close back above the 5-day SMA. No shorts, no stop, no time stop |
| Markets | Liquid **paper**: `xyz:SP500`, `xyz:XYZ100`, `xyz:NVDA`, `xyz:GOOGL`, `xyz:CL` (WTI). Watch list, not traded: BTC, Brent, ETH, AAPL, MSFT, META |
| Size | $5,000 notional per trade, 1x. **At most 2 positions open** ($10,000 paper account). With more setups than free slots, take them in the order CL, SP500, GOOGL, NQ100, NVDA (the backtest's order) and skip the rest |
| 200-day filter | Mean of the last **200 weekday closes**, from saved Liquid daily candles. Until a market has 200 saved weekday closes, the filter uses Liquid's own `sma200`, which is the mean of the last 200 *calendar* candles (~143 trading days). Seeded 2026-11-25 with 142 weekday closes per market, so the switch comes about mid-February 2027 |
| Saved closes | Dashboard store `data/rsi2/history/<KEY>` (`{market, symbol, candles: [{t, c}]}`), copied to `liquid/history/<KEY>.json` on this branch. The daily check adds each day's completed candles |
| Signal code | `liquid/rsi2_daily.py` (all markets, history merge, slots) on top of `liquid/rsi2_signal.py`. Completed **weekday** candles only, 00:00 UTC closes |
| Daily check | Scheduled task **"RSI2 daily check"**, cron `20 0 * * 2-6` UTC = 00:20 UTC Tue-Sat (7:20 PM ET winter / 8:20 PM summer), 20 min after each weekday candle closes. It fires into the Claude session that holds the Liquid connection (a fresh session would have no Liquid tools). It saves the closes, runs the check and reports LONG SETUP / EXIT / NONE per market. It never places orders. The user can also send **"RSI2 check"** by hand |
| Orders | On LONG SETUP with a free slot, or EXIT while holding: Claude prepares the paper order ($5,000 notional, 1x), the user approves the exact order, Claude executes it. Liquid requires this approval for every order |
| Log | Liquid's own history (`get_position_history`, `get_portfolio`). The dashboard (https://claude.ai/artifact/22FJo7qvavG7uHKQSckF7L) shows signals for all five markets, the account, the trades, and live vs backtest per trade. Reference closes (CME settlement or Nasdaq close) are entered on the page for the close-timing gap |
| Backtest, $5,000 per trade, 0.10% cost | Avg/trade (all periods): S&P +$24, Nasdaq +$16, NVDA +$97, GOOGL +$39, WTI +$81. 2 slots x $5,000 with all five: 2020-23 $+4,862, 2024-25 $+2,411, 2026 holdout $+1,925 (vs $+361 / $+1,082 / $+947 for S&P + Nasdaq alone). Worst single trade -$866 (NVDA) at $5,000 |
| Backtest, 1 micro each of ES/NQ/RTY/YM (older reference) | 2020-23 $+5,460, 2024-25 $+9,474, 2026 holdout $+12,021. Worst single trade **-$3,988** (MNQ, 2025-02-21 to 03-14). The -$4,990 quoted before came from the RSI(2) < 30 variant |

**Why a scheduled check plus manual approval:**
- Liquid has no alerts or scheduler. Its "automated trading" tool only saves a spending limit.
- The user asked for a scheduled task on 2026-11-25. It only reports and saves closes; it never places orders.
- Every Liquid order needs the user's explicit approval anyway.

**Liquid account state:**
- Paper mode is ON in the user's mobile app **and** on Claude's Liquid connection (enabled 2026-11-25).
- Paper account: $10,000, no positions.
- Each platform keeps its own mode. Check `paper_trading_status` before any order.

**Signal on 2026-11-24 (last completed candle):** NONE in all five markets. Every one is below its 200-day average:

| Market | Close | 200-day avg (Liquid's) | Needs |
|---|---|---|---|
| S&P 500 | 7,184.9 | 7,564 | +5.3% |
| Nasdaq 100 | 26,143 | 29,292 | +12.0% |
| NVDA | 152.71 | 209.62 | +37% |
| GOOGL | 279.36 | 344.41 | +23% |
| WTI | 81.65 | 87.57 | +7.3% |

## Not used (tested 2026-11)
- **ToS study alerts can't be emailed.** `Alert()` in a chart study fired in the platform only; no email reached Gmail with "Alert is triggered -> Send e-mail" on. So the email -> Zapier -> Notion plan was dropped.
- **Zapier's connection can't build Zaps.** It runs single actions only.
- **Logging:** Journal Triggers E by hand in Notion; RSI(2) uses Liquid's own history.
- **Scheduled tasks:** only the "RSI2 daily check" (see above), added at the user's request on 2026-11-25. It reports signals and saves daily closes; it never places orders.

## Tested, no durable edge (don't revisit without new data)
- Journal Triggers on default settings.
- Real-CVD filters, CVD divergence, flip and absorption.
- Fewer-indicator versions.
- Noise-boundary momentum (failed the 2026 holdout).
- Session-open failed close.
- RSI(2) shorts.
- RSI(2) variants (2026-11-25): entry below 30, time stops of 5/7/10 days, ATR sizing. All failed the 2026 holdout.
- RSI(2) on silver, gold, TSLA and AMZN (2026-11-25).
- ORB, gap fade, VWAP trend, turn of month.

## Open questions for the next session
- **Notion journal:** its 60 logged trades average +8 pts, but Jun-Oct shows 96% wins (losers probably not logged). The Oct 22 fully-logged day was breakeven. A complete log for 4-6 weeks decides whether the discretionary version has an edge.
- **Code location:** `main` has the research up to 2026-11-25 morning. The live RSI(2) setup (five markets, saved closes, `liquid/rsi2_daily.py`, the round-2 research and Databento daily data) is on `claude/focused-hypatia-pwaszc`, which the daily check uses. Merge it to `main` when convenient.

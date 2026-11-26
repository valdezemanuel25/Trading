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

### 2. RSI(2) pullback + trend reclaim (daily, long only): Liquid only
Decision 2026-11-25: Liquid only for this strategy. **No ToS and no Zapier.**
Updated 2026-11-25, approved after the research in `docs/backtest-log.md` ("RSI(2) round 2"):
- three markets added;
- the 200-trading-day filter;
- the worst-trade figure corrected.

Updated again 2026-11-25 (approved after "new strategies beside the live RSI(2) rule" in `docs/backtest-log.md`):
- trend reclaim added as a second rule;
- one position per market;
- daily positioning log.

| Item | Setting |
|---|---|
| Rule 1: RSI(2) | All five markets. Long only. Close > 200-day SMA and RSI(2) < 10 -> buy. Sell on the first close back above the 5-day SMA. No shorts, no stop, no time stop |
| Rule 2: trend reclaim (TR) | `xyz:CL`, `xyz:GOOGL`, `xyz:XYZ100`, `xyz:NVDA` (not S&P 500: negative in 2020-23). Buy the first close back above the 200-day SMA (yesterday's close at or below yesterday's SMA, today's above today's). Sell on a close back below the 200-day SMA, or at the close of the 20th trading day after entry, whichever comes first |
| Markets | Liquid **paper**: `xyz:SP500`, `xyz:XYZ100`, `xyz:NVDA`, `xyz:GOOGL`, `xyz:CL` (WTI). Also followed, not traded: BTC, Brent, ETH, AAPL, MSFT, META |
| Size | $5,000 notional per trade, 1x. **At most 2 positions open and one per market** ($10,000 paper account). With more setups than free slots: RSI(2) first (CL, SP500, GOOGL, NQ100, NVDA), then TR (CL, GOOGL, NQ100, NVDA); skip the rest |
| Open-position records | Each open position records which rule opened it, because the exits differ: dashboard store `data/rsi2/open/<KEY>` (`{market, symbol, strategy: "RSI2"|"TR", entry_date, entry_px, notional}`), mirrored in `liquid/open/<KEY>.json`. Claude writes it after an approved order fills and deletes it after the close fills. The check warns if Liquid and the records disagree |
| 200-day filter | Mean of the last **200 weekday closes**, from saved Liquid daily candles. Until a market has 200 saved weekday closes, the filter uses Liquid's own `sma200`, which is the mean of the last 200 *calendar* candles (~143 trading days). Seeded 2026-11-25 with 142 weekday closes per market, so the switch comes about mid-February 2027 |
| Saved closes | Dashboard store `data/rsi2/history/<KEY>` (`{market, symbol, candles: [{t, c}], liquid_sma200: [{t, v}]}`), copied to `liquid/history/<KEY>.json` on this branch. The daily check adds each day's completed candles and Liquid's reported sma200 (TR needs yesterday's SMA too) |
| Signal code | `liquid/rsi2_daily.py` (both rules, all markets, history merge, slots, open-position records). Completed **weekday** candles only, 00:00 UTC closes |
| Positioning log | Data only, no rule uses it. Each check saves Liquid `analyze_market` per market (`liquid/positioning.py`): funding, open interest, volume, smart money vs losing crowd long %, bias by position size. Store `data/rsi2/positioning/<DATE>_<KEY>` (full log) and `data/rsi2/positioning_latest/<KEY>` (dashboard). First analysis at 60 logged trading days (see Watch list, point 4) |
| Daily check | Scheduled task **"RSI2 daily check"**, cron `20 0 * * 2-6` UTC = 00:20 UTC Tue-Sat (7:20 PM ET winter / 8:20 PM summer), 20 min after each weekday candle closes. It fires into the Claude session that holds the Liquid connection (a fresh session would have no Liquid tools). It saves the closes and positioning, runs the check and reports RSI(2) and TR entries and exits per market. It places orders only after the user approves them (see Orders). The user can also send **"RSI2 check"** by hand |
| Orders | **One approval per day** (since 2026-11-25). The check prepares every order first: sells as a `close_positions_batch` preview with an explicit list of the symbols to close (or `close_position` for one); buys as a `suggest_trades_batch` preview (or `suggest_trade` for one), each $5,000 notional, 1x, market, long. It shows one numbered list and asks once: "Reply approve to place all N orders, or name any to skip." On approve it executes exactly the previewed orders, sells first, then buys (one idempotency key per batch). A skip, a preview older than 15 minutes, or a changed portfolio means a fresh preview and a new approval. It reports each outcome (filled, rejected or pending) and updates `data/rsi2/open/<KEY>` and `liquid/open/<KEY>.json`. No order is placed without that approval |
| Log | Liquid's own history (`get_position_history`, `get_portfolio`). The dashboard (https://claude.ai/artifact/22FJo7qvavG7uHKQSckF7L) shows signals for all five markets, the account, the trades, and live vs backtest per trade. Reference closes (CME settlement or Nasdaq close) are entered on the page for the close-timing gap |
| Backtest, both rules, 2 slots, one position per market | 2020-23 $+7,974, 2024-25 $+3,088, 2026 holdout $+3,495 (RSI(2) alone $+5,082 / $+2,198 / $+1,766; `research/strategies2.py` engine). TR alone on its four markets: $+3,301 / $+13 / $+2,482, about 30% winners, worst trade -$377 |
| Backtest, RSI(2), $5,000 per trade, 0.10% cost | Avg/trade (all periods): S&P +$24, Nasdaq +$16, NVDA +$97, GOOGL +$39, WTI +$81. 2 slots x $5,000 with all five: 2020-23 $+4,862, 2024-25 $+2,411, 2026 holdout $+1,925 (vs $+361 / $+1,082 / $+947 for S&P + Nasdaq alone). Worst single trade -$866 (NVDA) at $5,000 |
| Backtest, 1 micro each of ES/NQ/RTY/YM (older reference) | 2020-23 $+5,460, 2024-25 $+9,474, 2026 holdout $+12,021. Worst single trade **-$3,988** (MNQ, 2025-02-21 to 03-14). The -$4,990 quoted before came from the RSI(2) < 30 variant |

**Why a scheduled check plus manual approval:**
- Liquid has no alerts or scheduler. Its "automated trading" tool only saves a spending limit.
- The user asked for a scheduled task on 2026-11-25. It reports, saves closes and positioning, and places the day's orders only after one explicit approval of the exact previewed list.
- Every Liquid order needs the user's explicit approval anyway.

**Liquid account state:**
- Paper mode is ON in the user's mobile app **and** on Claude's Liquid connection (enabled 2026-11-25).
- Paper account: $10,000, no positions.
- Each platform keeps its own mode. Check `paper_trading_status` before any order.

**Signal on 2026-11-24 (last completed candle):** NONE in all five markets. Every one is below its 200-day average, so RSI(2) can't fire; a close back above it would be a TR entry (except S&P 500):

| Market | Close | 200-day avg (Liquid's) | Needs |
|---|---|---|---|
| S&P 500 | 7,184.9 | 7,564 | +5.3% |
| Nasdaq 100 | 26,143 | 29,292 | +12.0% |
| NVDA | 152.71 | 209.62 | +37% |
| GOOGL | 279.36 | 344.41 | +23% |
| WTI | 81.65 | 87.57 | +7.3% |

### Watch list (info only, approved 2026-11-26)
Plan fixed on 2026-11-26 after "patterns suggested by the first live check" in `docs/backtest-log.md`.

1. **Two setups, shadow trades only.** They never place an order and never take a slot. Code: `liquid/watch.py`. It
   uses the same saved closes, 200-day SMA and RSI(2) as the live check, from the 2026-11-26 candle on.

   | Setup | Markets | Entry (at the close) | Exit |
   |---|---|---|---|
   | DEEP | NVDA, GOOGL | RSI(2) < 10 and close at least 10% below the 200-day SMA | First close above the 5-day SMA |
   | DOWN4-B200 | SP500, NQ100, NVDA, GOOGL | 4 lower closes in a row, close below the 200-day SMA | First close above the 5-day SMA |

   - One shadow position per setup and market. Shadow P&L = $5,000 x return - 0.10% ($5 per round trip).
   - The daily report shows one "WATCH" line per entry or exit, the open shadow trades, and running totals.
   - Shadow trades are logged to `liquid/watch/<candle date>.json` (that day's events, open shadow trades, all closed
     ones) and committed with the daily run.
   - Wired into the "RSI2 daily check" prompt only once the user approves the exact prompt diff.
2. **Adoption rule (fixed now).** At the review, a setup is proposed for live only if all three hold:
   - at least 8 closed shadow trades;
   - net > 0 after costs;
   - the backtest's portfolio change (`research/state_patterns.py`) stays positive when re-run with data to the
     review date.

   Otherwise it is dropped. No changes to either setup's settings before the review.
3. **Review date: 2027-05-31**, or earlier once either setup has 8 closed shadow trades (the report then says
   "REVIEW DUE"). Until then:
   - no new strategy research rounds;
   - no new watch setups (the cap is two).
4. **Positioning: logging only.** First analysis once the log has 60 trading days: about mid-February 2027 (60
   weekdays from 2026-11-24), later if days are missed. Question: does the crowd-vs-smart-money gap at entry change
   RSI(2) and TR outcomes? It is tested as a filter on the existing rules only, not as a new setup.

## Not used (tested 2026-11)
- **ToS study alerts can't be emailed.** `Alert()` in a chart study fired in the platform only; no email reached Gmail with "Alert is triggered -> Send e-mail" on. So the email -> Zapier -> Notion plan was dropped.
- **Zapier's connection can't build Zaps.** It runs single actions only.
- **Logging:** Journal Triggers E by hand in Notion; RSI(2) uses Liquid's own history.
- **Scheduled tasks:** only the "RSI2 daily check" (see above), added at the user's request on 2026-11-25. It reports signals, saves daily closes and positioning, and places orders only after the user's one daily approval of the previewed list.

## Tested, no durable edge (don't revisit without new data)
- Journal Triggers on default settings.
- Real-CVD filters, CVD divergence, flip and absorption.
- Fewer-indicator versions.
- Noise-boundary momentum (failed the 2026 holdout).
- Session-open failed close.
- RSI(2) shorts.
- RSI(2) variants (2026-11-25): entry below 30, time stops of 5/7/10 days, ATR sizing. All failed the 2026 holdout.
- RSI(2) on silver, gold, TSLA and AMZN (2026-11-25).
- Beside RSI(2) (2026-11-25): weekly momentum rotation, trend reclaim with no time cap, 2x/3x ATR catastrophe stops, Brent/WTI and GOOGL/Nasdaq spreads. RSI(2) dips below the 200-day (DIP) on watch.
- ORB, gap fade, VWAP trend, turn of month.

## Open questions for the next session
- **Notion journal:** its 60 logged trades average +8 pts, but Jun-Oct shows 96% wins (losers probably not logged). The Oct 22 fully-logged day was breakeven. A complete log for 4-6 weeks decides whether the discretionary version has an edge.
- **Code location:** `main` has the research up to 2026-11-25 morning. The live RSI(2) setup (five markets, saved closes, `liquid/rsi2_daily.py`, the round-2 research and Databento daily data) is on `claude/focused-hypatia-pwaszc`, which the daily check uses. Merge it to `main` when convenient.

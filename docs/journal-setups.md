# Journal setups: step 1 of the intraday agent (read only)

Written 2026-11-25 from the Notion database "Trading Journal" (62 entries, 2026-04-27 to 2026-10-29). Nothing in
Notion was changed. The trade-by-trade classification is in `research/journal/journal_trades.csv`; rerun the
numbers by reading that file (the snippet at the end of this doc).

## What the journal holds

- **Market:** ES and MES only (S&P 500 futures). One SPY put (2026-04-27) is left out. No NQ or CL trades.
- **Time of day:** the regular-session open. Most reviews say "at market open", "first 5 minutes", "after the first
  10-15 minutes". The only entries with clock times (2026-10-22) run 9:37-10:24 ET. Hold time is usually under
  5-30 minutes ("very fast trade", "less than 5 minutes").
- **Risk:** about 1:1 reward to risk, with a 6-10 point stop and an 8-15 point target on ES.
- **The page template's checklist** is all four of: key level (POC/VAH/VAL/LVN lined up with a previous-day or
  weekly high/low), CVD plus a "custom sweep signal", a Bookmap liquidity wall, and a closed 5-minute candle.
- **Fields:** Direction, Points and PnL are filled in only for the last 9 entries. For the others I read the
  direction from the review text and computed points from entry and exit. One title is wrong: "Long ES" on
  2026-05-05 (7281 to 7271, +$500) was a short.

## Setups and logged results

Points are ES points per contract, before costs. "se" is the standard error of the average.

| Setup | Trades | Win rate | Avg pts (se) | Avg win / loss | Dates |
|---|---|---|---|---|---|
| **A. Fade a failed high** (short) | 28 | 86% | **+10.8** (1.7) | +13.5 / -5.2 | 05-05 to 10-27 |
| **B. Reclaim a swept low** (long) | 10 | 100% | **+14.0** (2.4) | +14.0 / none | 05-12 to 10-29 |
| C. Trend / breakout continuation | 11 | 64% | +4.1 (2.7) | +9.8 / -6.1 | 05-05 to 09-01 |
| Other (counter-trend, platform problem) | 5 | 25% | -2.3 (3.8) | | 04-29 to 05-19 |
| Eval-account scalps, no notes (10-22) | 7 | 57% | 0.0 (2.3) | +4.9 / -6.5 | 10-22 |
| All | 61 | 77% | +8.0 (1.3) | +12.2 / -5.9 | |

A and B are the same idea mirrored. Together: 38 trades, 89% win, +11.6 pts on average.

**A. Fade a failed high (short).**
- Where: price pushes into a resistance level and fails. The level is a previous-day, weekly, premarket or
  all-time high, VAH, or a 1h/4h SMA or VWAP, usually one that "rejected 2-5 times" or showed on the Bookmap
  heatmap.
- Entry: a 5-minute candle closes back below the level, or below the 5-minute 9/21 EMA or SMA50, or below VAH.
  The 09-03 variant is a candle closing below the low of the first 5-minute candle.
- Stop: just above the high of the push (6-10 pts).
- Target: POC, VAL, VWAP (5m, 15m or 1h) or the previous day's low.
- Context: price is above VAH or VWAP or in the upper Bollinger band ("overextended"), and the higher timeframe
  is bearish or at resistance.

**B. Reclaim a swept low (long).** The mirror image of A.
- Where: price wicks below the premarket low, previous-day low, monthly low or a 4h SMA.
- Entry: the next 5-minute candle closes back above the level.
- Stop: just below the wick.
- Target: POC, VAL, VAH, the 5-minute EMA or SMA21, or the 1h VWAP.

**C. Trend continuation.**
- Entry: a 5-minute close above POC, or below POC or the premarket low, with CVD agreeing.
- Target: the next value-area edge or VWAP.

Most of C's losses are the trades the reviews call mistakes ("stop going against the trend", "wait for candle
closure", "should have waited for a retest").

## Why these numbers overstate the edge

1. **Selective logging.** From July on, 20 of 20 logged A and B trades are winners. The one day logged straight
   from the broker with clock times (10-22, the eval account, 7 trades) is a coin flip: 57% win, average 0.0 pts.
   This looks like a journal of trades worth writing up, not every trade taken. Unless every trade from May to
   October is in Notion, the win rate can't be trusted. Can you confirm whether it is? Your broker's statements
   would settle it.
2. **Small sample.** 38 reversal trades in 6 months, all in one market regime (ES rising from about 7,150 to
   7,850).
3. **Reviews written after the fact.** The level that "was very strong" is often identified once the trade is over.
4. **The rule-based version of this strategy is already in the repo, and it didn't hold up.**
   `thinkorswim/JournalTriggers.ts` and its Python port `backtest/` (`docs/backtest-log.md`, 2026-10-29 and
   2026-10-30) turn these same setups into rules:
   - sweep L/S is setup B/A;
   - failed breakout and BB fail are setup A;
   - VAH/VAL flips are setup C.

   On ES 1-minute data, 2020-01 to 2026-10:
   - The full strategy: 1,677 trades, **-$41,210 net**, +0.11 pts gross per trade.
   - The best variant, E (10:30-11:00 ET only, target capped at 10 pts, breakeven at +4), is roughly breakeven
     after costs: +0.5-0.7 pts gross per trade.
   - Real CVD from Databento trades and a real volume profile didn't change that out of sample.
   - The only lead positive in both halves was **long-only failed breakouts**: about +$1,230 / +$2,098 on E,
     54 / 43 trades.

## Judgment calls an agent can't follow yet

Each of these needs an exact definition before an agent can follow it:

| Journal wording | What's missing | Live data the agent has |
|---|---|---|
| "Very strong level", "rejected 3-5 times", "level that showed on the 4h" | Which levels count, how close counts as a touch, how many touches | Price and candles: yes |
| "Liquidity wall / strong heat levels on Bookmap", "red bubbles getting bigger" | Size threshold, depth, persistence | Liquid's order book is a crypto-venue book for the S&P perp, not the CME book Bookmap shows. No history to test |
| "CVD confirms", "CVD flip from 12k to -1k", "CVD divergence" | Window and threshold. CVD is cumulative from when? | No live CVD on Liquid. Tested on CME data: no edge out of sample |
| "Custom sweep signal fired" | The signal's formula (a TradingView/ToS script?) | Unknown |
| "Daily bias", "overextended", "price not agreeing" | A rule (e.g. price above VAH and above the VWAP +1 sd band) | Price and candles: yes |
| "Strong level" for the target (POC vs VAL vs 1h VWAP vs previous-day low) | Which one wins when several are in range | Computable from candles |
| News ("Iran peace deal", "no news today") | Skip-day rule (e.g. no trades on CPI/FOMC days, or after a gap over X points) | Calendar can be listed in advance |
| Volume profile (POC/VAH/VAL) | Session start (RTH or ETH) and value-area % | Computable from 1-minute volume |

## The constraint that matters most for an agent

These are 5-to-30-minute trades with 6-10 point stops, decided on a closed 5-minute candle in the first hour.
That doesn't fit the agent's limits:

- **Wakes:** the agent wakes at most hourly. By the next wake the trade is usually over.
- **Approval:** every order needs your approval in the agent's session. The order fills only when you answer, so
  you'd need to be watching anyway.
- **No stop entries:** Liquid has no buy-stop or sell-stop entry orders. It does have limit orders and TP/SL
  brackets (`execute_tpsl`).
- **Market:** Liquid's S&P instrument is `xyz:SP500`, a perpetual on the index, not ES futures. Spread, funding
  and the 9:30 ET open behave differently.

Options for step 2, best first:

1. **Hourly-compatible version.** Test whether the same reversal still pays when the entry comes up to 60 minutes
   late, with you approving each one. The earlier trend-reclaim test lost most of its edge this way.
2. **Resting limit at the level, with a bracket.** Before the open the agent proposes a limit order at a level,
   with a stop and target attached (setup A without the candle-close confirmation). You approve once and it fills
   while you're away. It drops your checklist's "closed 5-minute candle" rule. Liquid's handling of resting paper
   orders also needs one small test.
3. **Long-only failed breakouts** (the existing `backtest/` lead), with an hourly or resting-limit entry.

## Data

- **ES:** the repo already has ES 1-minute data, 2020-01 to 2026-10 (`data/glbx-mdp3-*.ohlcv-1m.csv.zst`). It
  also has real trades/CVD for 2026-04 to 10 plus 10:00-11:05 ET windows back to 2025-08 (`data/trades_1m/`).
  Your market is covered, so nothing needs buying for step 3.
- **NQ and CL:** 1-minute data is also in the repo, but you don't trade them.
- **Bookmap depth:** testing these rules would need CME market-by-price data. That's a large purchase, and it
  wouldn't match Liquid's book anyway. I'd leave Bookmap out of the agent's rules.

## Reproduce

```
python3 - <<'EOF'
import csv, statistics as st
from collections import defaultdict
g = defaultdict(list)
for r in csv.DictReader(open('research/journal/journal_trades.csv')):
    if r['pts']: g[r['setup']].append(float(r['pts']))
for k, p in g.items():
    print(k, len(p), sum(x > 0 for x in p), round(st.mean(p), 2))
EOF
```

# Intraday agent: draft rules (step 2, waiting for your OK)

Written 2026-11-25, from `docs/journal-setups.md`: setup A (fade a failed high) and setup B (reclaim a swept low).
These are the journal's two best setups. Nothing here runs or trades.

## Inputs (the agent can see all of these live; all can be rebuilt from ES 1-minute data)

- 5-minute candles, regular session 9:30-16:00 ET.
- **Levels, fixed before the open at 9:25 ET:**
  - PDH / PDL: previous regular-session high and low.
  - ONH / ONL: overnight high and low, 18:00 to 9:30 ET (the journal's "premarket high/low").
  - PWH / PWL: previous week high and low.
- Session VWAP (from 9:30) and the developing POC.
- **Not used:**
  - Bookmap depth: Liquid's book isn't the CME book, and there is no history to test it on.
  - CVD: not available live on Liquid, and no edge out of sample on CME data.
  - The "custom sweep signal": its formula isn't in the journal.
  - News: replaced by the skip-day rule below.

## Common rules

| | Rule |
|---|---|
| Market | Backtest on ES. Live on Liquid `xyz:SP500`, with points converted to % of price (8 pts ~ 0.10%) |
| Trade window | Entries 9:35-11:00 ET only |
| Skip days | No trades on CPI and FOMC days, or when the open gaps more than 1.0% from the previous close (the journal's "news-driven" days). The agent gets the calendar list once a month |
| Stop | 1 pt beyond the sweep extreme, with a minimum of 6 and a maximum of 12 pts. Setups needing a wider stop are skipped |
| Target | 1.25 x the stop distance, which is about the journal's typical R:R. The backtest also tests "VWAP or POC, whichever is nearer and at least 1 x the stop" |
| Time exit | Close at market on the first wake after 12:00 ET. Flat by 15:55 ET in all cases |
| Size | Separate paper budget of $10,000. Risk $50 per trade (stop hit, including costs). Notional = $50 / stop %, capped at $30,000 (3x) |
| Max per day | 2 trades. Stop for the day after a -$100 loss (two stops) |
| Max per market | 1 position at a time. No long and short on the same day after a loss |

## Setup A: fade a failed high (short)

1. A 5-minute candle's high trades at least 0.25 pt above a level L, where L is ONH, PDH or PWH (the sweep).
2. The same candle or the next one **closes** back below L (the journal's checklist: a closed 5m candle, no wick
   entries).
3. Price is above session VWAP when the sweep happens (the journal's "overextended / above VAH").
4. Entry at that close. Stop 1 pt above the highest high of the sweep. Target as above.

## Setup B: reclaim a swept low (long)

The mirror of A, using ONL, PDL or PWL: the low trades below L, a candle closes back above it, and price is below
VWAP.

## How the agent would place them on Liquid: two versions to test

Liquid has no stop entries, and the agent wakes at most hourly. So step 3 tests these two versions against the
ideal fill:

| Version | How it trades | What it gives up |
|---|---|---|
| **R. Resting limit with a bracket** | At 9:25 ET the agent places a sell limit at the nearest of ONH / PDH / PWH at least 3 pts above price, and a buy limit at the nearest low at least 3 pts below. Each has a stop and target attached (a TP/SL bracket). Whatever hasn't filled is cancelled at the 11:00 wake. If one side fills, the other stays open (at most 2 trades and -$100) | The candle-close confirmation: it fills on the wick. The stop is fixed in advance (8 pts) instead of above the sweep extreme |
| **H. Hourly late entry** | At each wake (9:45, 10:45 ET), the agent checks the last hour's candles for A or B. If the setup is there and price is still between the entry and halfway to the target, it enters at market with the setup's stop and target | Timing: entries come 0-60 minutes late, and many setups are already done or stopped out by the wake |

Both are compared with **I. Ideal**: entry at the confirming candle's close, which is what you do by hand.

**Comparison: long-only failed breakouts** (`Fail BO L` in `backtest/strategy.py`). It was the only lead positive
in both halves earlier. It's run through the same R and H fill models.

## How step 3 judges them (same method as before)

- Data: ES 1-minute, 2020-01 to 2026-10. Settings (the level set, target choice, VWAP filter on or off) are picked
  on 2020-23 only. They're then checked on 2024-25 for context and the 2026 holdout (2026-01 to 2026-10).
- Costs: ES $30 per round trip (about 0.6 pts). For Liquid, the fee plus slippage measured from the paper fills
  so far.
- Pass: positive net in 2020-23 **and** in the holdout, with the holdout's average trade above about 1 standard
  error. Anything weaker is reported as noise.

## Approvals: what Liquid allows

You asked for the agent to approve its own trades. Liquid's connector doesn't allow that. Every order needs your
explicit approval in chat, in paper mode too. Its "automated trading" policy only saves a per-order limit; the tool
itself says it "does not authorize automated orders in this MCP profile, or bypass … order confirmation".

What fits instead:
- **Version R needs one approval a day.** At 9:25 ET the agent shows the two bracket orders and you approve
  them once. After that, Liquid fills, stops and exits on its own while you're away. The agent never changes or
  cancels anything without asking, except the 11:00 cancel of unfilled orders, which you approve with the morning
  orders.
- **Version H needs an approval per trade.** It only fills when you answer.
- **A fully autonomous agent** would need a different execution route: your own code with exchange API keys, not
  this connector. I'd only look at that if a rule passes step 3.

Changing the rules later from its logs and paper trades works as you describe. The agent keeps its own order log
and dashboard section, and you or I review them and change the rules.

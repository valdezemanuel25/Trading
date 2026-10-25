# Trading

## Journal Triggers (TradingView indicator)

`pine/journal_triggers.pine` flags the setups behind the winning trades in the Notion trading journal. `docs/journal-setups.md` explains where each rule came from.

| Signal | What it means |
|---|---|
| 🔻 **SWEEP SHORT (score)** | Price was stretched above value, wicked a key level, then closed back below it and below the fast EMA while CVD rolled over |
| 🔺 **SWEEP LONG (score)** | The mirror: swept PML/PDL/support from below value and closed back above it |
| ✖ **POC RECLAIM LONG / POC LOSS SHORT** | First close through POC after rotating off VAL/VAH, with CVD agreeing |

Each label names the level(s) that were swept, for example `PDH+4h SMA21+Round`. It also shows the target (nearest magnet), the stop (past the sweep extreme) and the R:R. The score is the number of confluent levels, plus 1 for each stretch condition (above VAH, upper VWAP band, outside BB), plus 1 if CVD agrees.

### Install
1. In TradingView, open **Pine Editor**, paste the contents of `pine/journal_triggers.pine`, then click **Save** and **Add to chart**.
2. Use an ES1! or MES1! **5-minute chart with extended hours on**. Premarket high/low and the ETH profile need overnight bars.
3. For alerts, go to **Alerts → Create** and set Condition to *Journal Triggers → Any alert() function call*. You can also pick one of the named conditions instead.

### thinkorswim version
`thinkorswim/JournalTriggers.ts` has the same rules written in thinkScript.
1. In ToS, open **Charts → Studies → Edit studies → Create**. Name the study `JournalTriggers`, paste the file contents, then click **OK** and **Apply**.
2. Use a /ES or /MES 5-minute chart with **Show extended-hours trading session** turned on.
3. Arrows and bubbles only appear after the signal candle closes. The `Alert()` calls ring inside ToS on the next bar's open.

The ToS version adds four things:
- **Repeat-rejection bonus.** It counts separate rejections of the swept level over the last `touchLook` bars (48 bars = 4h on 5m). Each touch past the first adds +1 to the score, up to `touchBonusCap`. The bubble shows the count, for example `3x rejected`.
- **HTF bias filter (`biasMode`).** A fade only fires if both the 1h and 4h are on its side, judged by the last close vs the SMA50 / SMA21. It also fires if the sweep happened *at* an HTF level: PDH/PDL, PWH/PWL, an HTF SMA or a round number. POC reclaims never fire against the HTF trend. The top label shows HTF BEAR / BULL / MIXED.
- **Opening-range candle.** The high/low of the first `orMinutes` of RTH (yellow dashes) become sweep levels from 9:35.
- **Scorecard.** Every signal is followed to target, stop, or a `maxHoldBars` time-out, one trade at a time, and the labels tally the results by setup. Scores of `aPlusScore` and up get their own tally, along with average hold and net points. Green and red dots show where each signal hit its target or stop. Load 30+ days of 5m bars so the counts are meaningful.

ToS limitations:
- ToS scans and server-side study alerts don't allow secondary timeframes, and this study uses 1h/4h SMAs. Its alerts therefore only fire while the chart is open in ToS desktop, with no phone push.
- On past days, ToS draws each day's *final* POC/VA on every bar. Historical arrows are optimistic as a result. Live signals use the profile as it develops.
- The POC/VAH/VAL/VWAP lines are hidden by default, because you already chart them. Turn on `showProfileVwap` to compare them with your own studies.

### Tuning
- `Signal window` defaults to 9:30–11:30 NY, when nearly all journal winners happened.
- `Min score` defaults to 3. Raise it to 4 or 5 for fewer, A+ signals only.
- `Row size` is the volume-profile bucket size. 1 pt works for ES/MES.
- If your profile tool resets at the cash open, set `Volume profile resets on` to RTH so the POC/VAH/VAL match it.

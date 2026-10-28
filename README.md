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

- **Targets.** The ToS version targets the nearest level that is at least `minTgt` away *and* gives at least `minRR` for that stop. If POC is too close for 1:1, it targets VAH/VWAP instead. The max stop is 12 pts.
- **VAL Flip long / VAH Flip short** (lime / orange arrows). These catch a failed breakdown at the bottom of a flush. Price drops at least `flushPts` within `flushLook` bars and trades under VAL by more than `lvlTol` but no more than `flipMaxBeyond`. It is stretched below the lower VWAP band or Bollinger Band. Then a strong green candle (closing in the top 40% of its range, with positive bar delta) closes back above VAL. CVD doesn't need to have turned, which matches the 06-25 and 10-15 journal longs. The stop goes under the flush low, and the target is the nearest of POC / VWAP / BB mid / VAH that gives 1:1. The mirror short fades a blow-off above VAH. `flipNeedBias = no` lets these trade against the 1h/4h, since the flush itself is the setup.
- **HTF level test** (big magenta arrows): rejection of the 4h SMA200 / 4h SMA21 / 1h SMA50, checked in that order.
  - *Short:* price came from **below**, meaning no close above the level in the last `firstLook` bars (156 ≈ 13h on 5m). It wicked into the level ± `htfTol`, and a red candle closed back below the level and below the EMA.
  - *Cancel rule:* the setup is off if price was accepted above, meaning 2+ closes more than `cancelPts` above the level in the last `cancelLook` bars.
  - *Long:* the mirror, a hold of the level after price came from above.
  - *Score:* starts at 3, with +2 on the **first touch** in `firstLook` bars, plus stretch, CVD and any other levels swept on the same candle.
  - *Bubble:* shows T1 (nearest level giving 1:1), T2 (the next level beyond), the stop (above the level/sweep high) and the R:R.
  - *Scorecard:* tracked as `HTF S` / `HTF L`.
- **HTF zone label + lines.** Within `zoneTol` of a 4h/1h SMA, a yellow label names the level and gives both the study's value (completed HTF bars) and the chart's value (which includes the forming bar). It also says which side price is testing from. The three HTF SMAs are drawn on the 5m chart (`showHtfLines`).
- **Failed breakout / breakdown** (violet arrows, `useFbo`). After price is *accepted* beyond a 4h/1h SMA (2+ closes more than `cancelPts` past it within `fboLook` bars), the first close back through the level is a signal. A short also needs a red candle closing below the EMA; a long, the mirror. This setup alone runs until `fboEnd` (13:00 ET), because these traps usually show up after the morning window.
- **Chop filter** (`useChop`). With at least `chopCrosses` EMA crosses in the last `chopLook` bars, and the whole range no wider than `chopRange` points, every signal is paused. An orange CHOP label and a shaded zone mark it.
- **T1 / T2.** Reversal bubbles show T1 (nearest level giving 1:1) and T2 (the next level at least `minTgt` beyond it). While a tracked trade is live, T2 is drawn as a green short-dash line. All prices are rounded to the tick.
- **Ghost bubbles** (gray, `showGhosts`). A setup that qualified while the same-side cooldown was running still gets a small bubble showing only its T / S / RR.
- **One bubble per move.** If a candle passes both the Flip and the Sweep rules, the Flip wins and its bubble is marked `+ SWEEP (score)`.
- **`vaSource`.** `PROFILE` (the default) uses the ToS volume profile. ToS re-checks today's earlier candles against the latest POC/VA, so today's bubbles can change during the session; alerts still fire once, at the candle close. `VWAP_STATIC` uses VWAP as POC and VWAP ±1σ as VAH/VAL. It is built only from candles already printed, so bubbles never move.
- **Labels.** By default only the status label (HTF bias with the short/long score) shows, plus the CHOP and HTF ZONE labels when they apply. The scorecard is **off** (`showScorecard`) because it's hard to read live. Turn it on to review results: W/L per setup, net points, W/L with vs against the HTF bias, and how often T2 was reached. The green and red outcome dots stay on (`showOutcomes`). The POC Reclaim / POC Loss setups are off by default (`useReclaim`). `showDebug = yes` adds the score breakdown and the funnel.

ToS limitations:
- ToS scans and server-side study alerts don't allow secondary timeframes, and this study uses 1h/4h SMAs. Its alerts therefore only fire while the chart is open in ToS desktop, with no phone push.
- On past days, ToS draws each day's *final* POC/VA on every bar. Historical arrows are optimistic as a result. Live signals use the profile as it develops.
- The POC/VAH/VAL/VWAP lines are hidden by default, because you already chart them. Turn on `showProfileVwap` to compare them with your own studies.

### Backtesting in ToS
`thinkorswim/JournalTriggersStrategy.ts` is a ToS **Strategy** built from the study by `thinkorswim/build_strategy.py`. Re-run `python3 thinkorswim/build_strategy.py` after changing the study, and don't edit the strategy file by hand.
1. In ToS, open **Studies → Edit studies → Strategies tab → Import**, pick the file, and add it to a /ES 5m chart with extended hours on. Load the most history the chart allows.
2. Right-click the chart → **Strategies → Show Report** to see the trade list, win rate and P/L. The report can be exported to CSV.
3. Each entry is named by setup (`Sweep L`, `VAL flip L`, `HTF S`, `Fail BO S`…), and each exit by outcome (`T1`, `Stop`, `Time`).
4. `vaSource` defaults to **VWAP_STATIC** here so past trades only use information that existed at the time. Switching to PROFILE gives optimistic results.
5. Fills are idealized: entry at the signal candle's close, and T1 and the stop fill exactly at their price, with no slippage or commissions.

### Tuning
- `Signal window` defaults to 9:30–11:30 NY, when nearly all journal winners happened.
- `Min score` defaults to 3. Raise it to 4 or 5 for fewer, A+ signals only.
- `Row size` is the volume-profile bucket size. 1 pt works for ES/MES.
- If your profile tool resets at the cash open, set `Volume profile resets on` to RTH so the POC/VAH/VAL match it.

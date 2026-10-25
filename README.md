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

### Tuning
- `Signal window` defaults to 9:30–11:30 NY, when nearly all journal winners happened.
- `Min score` defaults to 3. Raise it to 4 or 5 for fewer, A+ signals only.
- `Row size` is the volume-profile bucket size. 1 pt works for ES/MES.
- If your profile tool resets at the cash open, set `Volume profile resets on` to RTH so the POC/VAH/VAL match it.

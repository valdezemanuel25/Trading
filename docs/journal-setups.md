# Winning setups from the Notion trading journal

This covers the 63 journal entries from 2026-04-27 to 2026-10-22, mostly ES/MES. About 35 winners have written reviews. Winners and losers were sorted by reading each Review, because most older rows have no Direction or PnL filled in. The Oct 22 Lucid scalps have no review text, so they were left out.

The winners come from three repeatable setups. `pine/journal_triggers.pine` encodes each one.

## 1. Sweep & Reject: short (about 20 winners, the main edge)

**Pattern.** Price runs up and is stretched: above VAH, in the upper VWAP band or outside the upper Bollinger Band. It wicks into a strong level and can't hold above it. A 5m candle then closes back below the level and below the 5m EMA/SMA. Short it to the nearest magnet below: POC, VWAP, VAL or the BB mid.

CVD is often still positive when this happens. The reviews treat that as divergence, not a reason to skip the trade. The confirmation is CVD rolling over on the trigger candle.

| Date | Level rejected | Target |
|---|---|---|
| 05-05 | PDH + VAH, rejected twice | POC |
| 05-07 | Week high | POC |
| 05-14 | PDH wick, next candle closed below | POC |
| 05-22 | PMH sweep, above VWAP + VAH | POC |
| 05-29 | 7611 rejected, above VAH, upper VWAP band, close < EMA | POC |
| 06-09 | PDH + 4h SMA21 wick | POC |
| 06-23 | 4h SMA200/21 not closed above, CVD flipped 12k → −1k | POC |
| 07-09 | Overextended above VAH/VWAP, close < VAH and EMA | VAL |
| 07-10 | ATH sweep, close < EMA and VAH | 4h level |
| 07-31 | Weekly level + 4h SMA + VAH | 4h VWAP |
| 08-13 | 7838 rejected 3×, close < VAH and EMA | VWAP |
| 08-14 | 7830 1h resistance, close < 5m EMA | Prior day open |
| 08-20 | 5m SMA50 + 1h VWAP, rejected 3× | BB mid |
| 09-03 | Outside upper VWAP + BB, close < opening candle | VWAP |
| 09-15 | Week high failed, close < VWAP and SMA50 | VAL |
| 09-22 | ATH wick, close < 9 SMA | VAL / 4h SMA200 |
| 09-25 | 7800 + VAH + upper BB | — |
| 09-29 | 7766 HTF rejection, POC/VWAP | VAL |
| 10-01 | POC + SMA50, rejected 4× | SMA200 |
| 10-13 | 7864 HTF resistance / PMH, first 5m candle failed | POC |
| 10-16 | 7800 rejected 5× (4h SMA21) | Lower VWAP |
| 10-20 | VWAP/POC/SMA, 7730 failed twice | VAL |

## 2. Sweep & Reclaim: long (8 winners)

**Pattern.** The mirror of setup 1. Price has dropped and is stretched: below VAL or in the lower VWAP/BB band. It sweeps PML, PDL, the weekly or monthly low, or HTF support. The next 5m candle closes back above the level. Go long to POC, VAL, the EMA or VWAP.

Dates: 05-12 (PDL sweep), 05-21 (PML), 05-27 (PML), 06-23 (HTF support), 06-25 (PML/PDL/monthly low), 07-17 (daily low tested 3×), 08-27 (PML below VAL and lower BB), 10-15 (7730 premarket low).

Most of these longs did **not** wait for a close above the EMA; on 08-27 the EMA was the target. For that reason the EMA filter is on for shorts and off for longs by default.

## 3. POC Reclaim / POC Loss: continuation (about 5 winners)

**Pattern.** Price rotates off one edge of value, and the first candle closes through POC with CVD agreeing. Target the other edge of value or VWAP.

Dates: 05-12 (close above POC → VWAP), 05-15 (above VAL twice, then above POC → VAH), 09-01 (POC + SMA50 → 1h VWAP/VAH), 05-19 short (POC rejection → VAL).

## Lessons from the losers, built in as filters

| Lesson from the reviews | How the script applies it |
|---|---|
| "Wait for candle closure" (05-08 ×2, 05-21) | Signals only fire on closed bars |
| "Stop going against the trend", shorted with no rejection (04-29, 05-01, 05-28) | Needs a swept level plus a close back through it, and CVD turning |
| Chop at POC (05-28, 05-21) | POC is only a target for sweep trades, and the score needs confluence beyond POC |
| Targets/stops too far, poor R:R (05-15) | Picks the nearest magnet at least `Min target` away; requires R:R ≥ 1 and stop ≤ 10 pts |
| Above VAH with no retest (05-21) | Breakout entries are never flagged, only rejections and reclaims |

## What the script can't see

- **Bookmap liquidity walls.** These still have to be checked by hand, so every alert ends with "check Bookmap".
- **True CVD.** The script estimates delta from where each candle closes in its range. It tracks the direction of real CVD, not its size.
- **Daily HTF bias calls**, such as gap fills and news. Use the signal window and your own premarket plan for these.

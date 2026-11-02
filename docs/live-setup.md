# What runs live (forward test on sim), as of 2026-11-02

Two strategies run live. Both are **forward tests on sim / micros**, not proven for real size. Everything else in
`docs/strategy-search.md` and `docs/backtest-log.md` was tested and is **not** run live.

## 1. Journal Triggers, variant E (intraday)
| Item | Setting |
|---|---|
| ToS study | `thinkorswim/JournalTriggers.ts` (or `JournalTriggersLite.ts`) |
| Chart | /ES (or /MES) **5-minute**, extended hours on |
| Inputs | `winStart = 1030`, `winEnd = 1100` (failed breakouts still fire until `fboEnd` 13:00) |
| Manual rules | T1 capped at 10 pts; stop to breakeven at +4 pts; close after 12 candles (1 h) if neither hit |
| Alert text | `JT \| <setup> \| <Long/Short> \| check Bookmap` |
| Zapier | Email Parser mailbox #1 -> Notion **E Signals** (page "Forward Test: Journal Triggers E") |
| Parser fields | `setup`, `direction` |
| Backtest | Roughly breakeven to slightly positive after costs (2025-08 to 2026-03: about +1 pt/trade, about 1.7 trades/week) |

## 2. RSI(2) pullback (daily, long only)
| Item | Setting |
|---|---|
| ToS study (live) | `thinkorswim/RSI2PullbackAlert.ts` on **four daily charts**: /MES, /MNQ, /M2K, /MYM |
| Inputs | Set `market` to match each chart; `rsiLongEntry = 10` (about 1 trade/week in total) or 30 (about 2/week); `enableShorts = no` |
| ToS strategy (optional) | `thinkorswim/RSI2PullbackStrategy.ts` on the same charts, for Show Report only |
| Routine | At about 15:50 ET (14:50 CT): LONG SETUP label -> buy at the close; EXIT label while long -> sell at the close |
| Alert text | `RSI2 \| <LONG SETUP/EXIT> \| <market> \| Long \| ...` |
| Zapier | Email Parser mailbox #2 -> Notion **RSI2 Signals** (page "Forward Test: RSI(2) Pullback") |
| Parser fields | `action` (e.g. LONG SETUP), `market` (e.g. MNQ) |
| Backtest, 1 micro each, net | 2020-23 +$5,460, 2024-25 +$9,474, 2026 +$12,021 (RSI(2)<10); no stop, worst trade -$4,990 (MNQ) |

**Note:**
- Daily bars form during the day, so an RSI2 alert can fire early and then disappear.
- The Zapier rows are a record of alerts. Tick **Confirmed at 15:50** only for the setups still showing at the check.

## Zapier (free plan, two 2-step Zaps)
1. **Two Email Parser mailboxes**, one per format: a parser mailbox learns one template.
   - Send each a sample:
     - `JT | Sweep S | Short | check Bookmap`
     - `RSI2 | LONG SETUP | MNQ | Long | buy at the close`
   - Highlight the fields listed above.
2. **Zap A:** parser #1 -> Notion "Create Data Source Item" in **E Signals**.
   - Signal and Setup = `setup`; Direction = `direction`; Date = email date; Alert text = body.
3. **Zap B:** parser #2 -> Notion in **RSI2 Signals**.
   - Signal = `action` + `market`; Action = `action`; Market = `market`; Date = email date; Alert text = body.
4. **ToS email:**
   - Setup -> Application Settings -> Notifications: email for study alerts.
   - Send everything to Gmail, with two filters:
     - emails containing `JT |` -> forward to parser #1;
     - emails containing `RSI2 |` -> forward to parser #2.
   - Or point ToS at one parser and forward the other.
5. ToS must be open with all five charts loaded, because study alerts run on your computer.

## Not live (tested, no durable edge)
- Journal Triggers on default settings.
- Real-CVD filters, CVD divergence, flip and absorption.
- Fewer-indicator versions.
- Noise-boundary momentum (failed the 2026 holdout).
- Session-open failed close.
- RSI(2) shorts.
- ORB, gap fade, VWAP trend, turn of month.

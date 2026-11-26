# Trend Join Long paper bot (built 2026-11-26)

Unattended paper trading of the Trend Join Long rules in `docs/intraday-stock-research.md` (source of truth).
The rule decisions are made by the same code as the manual routines (`tjl/`); `tjlbot/` only fetches data,
places orders and keeps state.

## Why not Liquid
Liquid's connector requires an approval in chat for every single order ("saved policy or routine authority never
authorize a trade"), and it has no API outside a Claude chat. So an unattended bot can't trade there. The bot uses
**Alpaca paper** instead: a free paper account for US stocks with an API, bracket orders (stop and target sent with
the entry), and a paper balance that can be set to **$25,000**, the doc's sizing base. RSI(2) stays on Liquid as before.

## What runs, and when (New York time, weekdays)
| Time | What happens |
|---|---|
| 8:40 | GitHub Actions starts the job (`.github/workflows/tjl-bot.yml`) on GitHub's servers. No PC needed. It runs the tests first; a failing test means no trading |
| 9:15 | **Premarket scan**, using consolidated data up to 9:00 (the doc's 9:00 morning check). Daily bars of the 75-name universe -> after-close screen (`tjl.after_close`), then gap / prior-day high / premarket volume and RVOL (`tjl.morning`), the 9 A+ boxes, final 1-2 names. Headlines since yesterday's close classify the catalyst (box 6); a trap headline (offering, probe, miss, denied...) drops the name |
| 9:15-10:00 | Nothing to do if no name is flagged (and nothing is carried): the report is written and the job ends |
| 10:00-15:30 | Every 30 s: is a flagged name above max(premarket high, high of day so far)? `tjl.trigger` checks windows (A 10:00, B 10:05), RVOL (A premarket > 1.5, B intraday >= 2.0 vs 14 days), SPY regime, grade, and picks the version (alternating on days both qualify; the other is simulated as Shadow). Entry = market buy with the stop and targets attached at the broker |
| all day | Management by `tjl.manage`: A exits the last third on a 5m close below the 21 EMA once both targets filled; B moves the stop to breakeven at +1R, then under 5m swing lows. Stops are always at the broker, so a crashed job leaves no position unprotected |
| 14:15 | The morning job hands over to the afternoon job (GitHub's 6-hour limit). Positions keep their broker stops during the hand-over |
| 15:45 | Overnight check (doc line 28 rule plus the limits below); otherwise close |
| 15:50 | Everything not carried is closed (flat by 15:51) |
| 16:12 | Report: P&L from the fills, both versions simulated on the day's 5m bars, rows for Notion, `report.md` |
| 16:37 | **Claude's daily report** (scheduled task): writes the rows to Notion "TJL Trades", re-reads the catalysts, refreshes market caps and the earnings calendar, sends you a summary |

Half days: no new trades (doc). Holidays: the job sees the closed market and stops.

## Hard limits (code: `tjlbot/settings.py`, `tjlbot/risk.py`)
- **Daily loss -$500, no matter what** (user, 2026-11-26). Day P&L = account equity vs last close (realized + open, carried positions included). Each new trade's risk is cut to what is left: `500 + day P&L - (loss still possible down to every open stop)`. Below $50 left, no trade. If day P&L reaches -$500 anyway (slippage, a gap through a stop), everything is closed and the day stops.
- Max 2 trades a day (doc), max 2 open positions (carried ones count), one entry per ticker per day, max 40 orders a day.
- Risk $250 normal / $500 A+, notional cap $25,000 per position (same as the Liquid plan).
- Test drawdown -$3,000 from the starting equity -> no new trades (doc's pause rule).
- Paper only: the client refuses any non-paper URL.
- Any position in the account that the bot didn't open is closed (the account is the bot's alone).

## Kill switches
- **Stop new trades:** create a file named `HALT` at the top of the `tjl-state` branch (GitHub web: Add file). Remove it to resume. Or tell Claude "halt the bot".
- **Close everything now:** a file named `FLATTEN`, same place. It stays in force until removed.
- **Turn the bot off:** set the repository variable `TJL_BOT_ENABLED` to anything but `true` (Settings > Secrets and variables > Actions > Variables), or disable the workflow in the Actions tab.
- In the Alpaca app you can always close positions by hand; the bot then sees the position gone and records the exit.

## One-time setup (only you can do these)
1. Create a free account at alpaca.markets. In the **Paper** dashboard: reset the paper account with a **$25,000** balance, then generate API keys (paper).
2. In GitHub, repo Settings > Secrets and variables > Actions:
   - Secrets: `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`.
   - Variables: `TJL_BOT_ENABLED` = `true`. Optional: `TJL_FEED` = `sip` if you buy Alpaca's real-time data plan.
3. The workflow file must be on `main` (GitHub runs schedules from the default branch only).
Then it runs by itself from the next weekday. To test right away: Actions tab > tjl-bot > Run workflow.

## Data: free plan vs paid
Free (default, `TJL_FEED=iex`): prices in real time from IEX; consolidated volume (all exchanges) only 15+ minutes late.
So premarket high, premarket RVOL and the 9:15 scan are on full data (up to 9:00), while version B's intraday RVOL
compares volume up to 16 minutes ago against the same window on the prior 14 days. The high of day for the newest
15 minutes comes from IEX trades, which can miss a print on another exchange. Alpaca's Algo Trader Plus plan
(about $99/month) gives real-time consolidated data: set `TJL_FEED=sip` and the delay goes away.

## Assumptions the doc doesn't settle (each is a setting; tell Claude to change any)
1. **Overnight:** the doc's line-28 rule (carry if in profit and above the 21 EMA, stop to breakeven), plus: no carry into a weekend, holiday, half day or earnings (needs `earnings.json` from the daily report; without it, no carry), and only if the carried position is <= $5,000, so a 10% overnight gap stays within the $500 daily cap. The doc's open question (A+ only? last third?) is still yours.
2. **Catalyst (box 6):** mechanical headline classification instead of Claude's judgment at 9:00; Claude re-reads it after the close and notes disagreements in the Notion row.
3. **Universe:** the same 75 Liquid names (`tjl/config.py`), market caps from Webull (refreshed daily by the report task).
4. **Prior-day high/low** from regular-hours 5m bars (the doc's levels are regular-hours levels).
5. **Fees:** Alpaca paper charges none; costs show up only as fill slippage. Real money would add tiny SEC/FINRA fees.

## Output and state
Branch `tjl-state` (public, like the repo): `runs/tjl-bot/<date>/` holds `morning.json` (the plan, same format as the
manual routine), `events.jsonl` (every decision and order), `report.md`, `notion_rows.json`; `runs/tjl-bot/book.json`
holds the trades across days. Notion rows use the existing "TJL Trades" schema; the Notes field says
`Executor: Alpaca paper bot`, the planned risk, `sim_r` (the trade's own simulation, for fair A/B pairs) and the
catalyst read. "Liquid order IDs" holds the Alpaca order ids.

## Known limits
- GitHub may start a scheduled run 5-20 minutes late, and rarely drops one; the 10:27 backup and the clock-based
  logic cover that. Between 14:15 and the afternoon start nothing is watched except the broker stops.
- GitHub disables schedules in a public repo after 60 days with no commits; the bot's daily state commits count.
- Unverified until the first live run: Alpaca's daily bars vs Webull's, and that bracket legs replace and cancel as expected on paper.

## Tests
`python3 -m pytest tests/ -q`: rule tests (`tests/test_tjl.py`) and the engine on an in-memory broker
(`tests/test_tjlbot.py`: entries, partials, breakeven, carry cap, flat by 15:51, daily cap sizing and breaker,
kill files, unknown positions, restart recovery, end-of-day rows, premarket scan).

# Trend Join Long: daily routines (built 2026-11-26)

How Claude runs the paper test each day. The rules themselves live in `docs/intraday-stock-research.md`
(source of truth); the mechanical parts are coded in `tjl/` (tested in `tests/test_tjl.py`).
No scheduled tasks: each routine starts when the user sends its message.

| Message | When (ET) | What happens |
|---|---|---|
| **after-close check** | After 4:00 PM; after 7:00 PM (winter) / 8:00 PM (summer) for a fresh RSI(2) candle | Close out today's trades, SPY regime, sector heat, screen, catalysts, top-5 watchlist, Webull watchlist update, RSI(2) check |
| **morning check** | About 9:00-9:30 | Gappers (3%+), premarket high/volume/RVOL, final 1-2 names with trigger, stop, 1R, size |
| **TJ trigger \<TICKER\>** | When a Webull alert fires, 10:00-15:30 | 5m chart check, version choice, Liquid paper order with stop + reduce-only partials for approval, Notion log |
| **TJ check \<TICKER\>** | Any time a position is open (suggested: 10:30, 11:30, 13:00, 14:30, 15:45) | Breakeven / trail / 21-EMA exit / 15:51 close, proposed for approval |
| **TJ audit** | Weekly (e.g. Friday after the close), and at the 2-month mark | Go/no-go metrics from the Notion log, splits by version, grade, box, window, regime |

How it works: Claude fetches data with the Webull, Liquid and Notion connectors and saves the raw JSON in the
session scratchpad. Then it runs `python3 -m tjl <command>` on those files. The script prints a markdown
report and writes `runs/tjl/<date>/<name>.json/.md` into the repo. Claude adds the judgment parts (catalyst
quality, "gap into resistance") and commits `runs/` so the next routine (possibly in a new container) finds the state.
Large connector results are saved to files automatically; pass those file paths to the script.

**The code never has an opinion** (same principle as the presenter's pipeline): it applies the pass/fail rules,
ranks and sizes. Claude writes the catalyst read and flags traps (up on bad news, denied rumor = skip).

---

## 1. after-close check

0. **Close out today** (if any Trend Join trade today):
   - Liquid `get_portfolio` + `get_position_history`: fills, fees, P&L of today's trades; update their Notion
     rows (Status Closed, exit price/time/reason, Fees $, Funding $, P&L $, MFE/MAE, Rule followed, Mistakes).
   - Shadow rows: Webull `get_stock_bars` (symbol, M5, `PRE,RTH`, count 200, `end_time` = 16:00 ET today) ->
     `python3 -m tjl shadow --trade runs/tjl/<D>/trigger-<T>.json --bars5 <file>` -> update the Shadow row with
     its `notion_update` block. The same command with `--version <real>` gives MFE/MAE R for the real trade.
1. **Data** (Webull, ~7 calls):
   - Daily bars, universe in batches of 20: `get_stock_bars` (category US_STOCK, timespan D, count 260), symbols from
     `tjl/config.py` `UNIVERSE` (75 names; 4 calls).
   - ETFs: `get_stock_bars` (US_ETF, D, 260) for `SPY, QQQ, SMH, IGV, XLE, XBI`.
   - Snapshot: `get_stock_snapshot` (US_STOCK, the 75 names, `extend_hour_required` true) -> market cap, 52-week range.
   - Context (reported, not scored): `get_market_sectors` (US_STOCK, D5 and MO1).
2. **Earnings:** Liquid `upcoming_earnings` (week). Pass the names as `--earnings "CRWD:2026-12-01 post-market,..."`.
3. **Run:** `python3 -m tjl after-close --stocks <4 files> --etfs <file> --snapshot <file> --earnings "..."`
4. **Catalysts:** Webull `get_stock_news` for each top-5 name (plus any earnings name). Write one line per name:
   catalyst, type (earnings/guidance > M&A > FDA > index > sympathy > analyst > none), trap or not.
5. **Webull watchlist "Trend Join"** (`469684da9c224d59978706608a36c55a`): `get_watchlist_instruments`, then
   `remove_watchlist_instruments` for names no longer in the top 5 and `add_watchlist_instruments` (US_STOCK) for new ones.
6. **RSI(2) check** (`docs/live-setup.md`): Liquid `show_chart` (1d, limit 30) for `xyz:SP500` and `xyz:XYZ100`,
   `get_technical_indicators` (1d, sma) for the sma200, then `python3 liquid/rsi2_signal.py <candles.json> <sma200>`.
   EXIT only matters when holding (check `get_portfolio`).
7. **Commit** `runs/tjl/<session>/after_close.*` and push.

Report: regime (+ the 200d note), sector heat table, top-5 table with levels, catalysts, planned grade/risk,
watchlist change, RSI(2) result, and what tomorrow is (full day / half day / closed).

## 2. morning check

1. State: `runs/tjl/<prior session>/after_close.json` (pull the branch first if the container is new).
2. **Snapshot** all step-1 names + the top 5 (`get_stock_snapshot`, `extend_hour_required` true). Names with
   premarket price >= 2% above the prior close are the gap candidates.
3. **Premarket bars** for the gap candidates (max 20 per call): `get_stock_bars` (M5, `trading_sessions` PRE,
   count 1000, `end_time` = now). That covers ~15 days, so the premarket RVOL compares the same clock window
   over the prior 14 days (real exchange volume).
4. **Run:** `python3 -m tjl morning --state <after_close.json> --snapshot <file> --pre <file> --now HH:MM`
5. Catalyst check (news since last night) on the final names; decide box 6.
6. Report the final 1-2 names: **trigger** (= premarket high; if price makes a new high before 10:00, the
   trigger moves up to it), provisional stop / 1R / size for A and B, grade. The user sets one Webull alert per
   name ("price crosses above <trigger>"). No final names -> "no alerts today".
7. Log setups that reached the list but fail a rule later as Skipped when they would have triggered.

## 3. TJ trigger \<TICKER\>

1. Pre-checks: `paper_trading_status` (must be ENABLED), `get_portfolio` (margin, open positions),
   today's Trend Join P&L and trade count from Notion (rows with today's Date, Status Open/Closed).
   Version of the last real trade (Status not Shadow) -> `--prev-version`.
2. **Data:** Webull `get_stock_bars` (ticker, M5, `PRE,RTH`, count 200, `real_time_required` true) for today;
   Webull `get_stock_bars` (ticker, M5, RTH, count 1200) for the 14-day RVOL (version B). Liquid `analyze_market`
   for the mark price (and max leverage).
3. **Run:** `python3 -m tjl trigger <T> --state runs/tjl/<D>/morning.json --bars5 <today> --hist5 <hist>
   --liquid-price <mark> --day-pnl <x> --trades-today <n> --prev-version <A|B> --catalyst yes|no
   --catalyst-text "..." --catalyst-type "Earnings/guidance"`
   - Checks: trading day and not a half day, < 2 trades, day P&L > -$500, morning rules passed, price above
     max(PMH, HOD before this bar), time window (A 10:00-15:30, B 10:05-15:30), RVOL (A: premarket > 1.5;
     B: intraday >= 2.0 vs the same time over 14 days), SPY below 200d -> A+ only.
   - Video 5 confirmation (5m close above VWAP and the 8 EMA) is reported and logged, not required.
   - Version: if both qualify, alternate (the other becomes a **Shadow** row); else the one that qualifies.
   - Stops (Webull levels): A = lower of PMH - 1% and LOD; B = LOD - 1%. Mapped to Liquid by percent.
   - Size: risk $500 (A+, all 9 boxes) or $250; notional = risk / stop %; leverage 2-10x so margin <= $2,500
     (capped -> lower risk logged).
4. **Orders (each needs the user's approval in chat):**
   1. `suggest_order` with the printed fields -> show the returned preview -> on approval `execute_order`
      (market, `sl` attached, `confirmed: true`, one idempotency key). If it fills only partly, set the stop with `execute_tpsl`.
   2. Partials: `execute_order` reduce-only limit sells (quantity in coins) at +1R and +2R (A) or +0.75R (B).
      Check the quantity against the actual fill; the script assumes `--sz-decimals 2` (fix it from the preview if Liquid rejects it).
5. **Notion:** create the rows printed under `notion` (real = Planned -> Open after the fill with the fill price
   and Liquid order IDs; shadow = Shadow). Commit `runs/tjl/<D>/trigger-<T>.*`.
6. Management: see "TJ check".

## 4. TJ check \<TICKER\>

1. Liquid `get_portfolio`: position size (coins), current stop, mark. Webull `get_stock_bars` (ticker, M5, `PRE,RTH`,
   count 200, `real_time_required` true).
2. **Run:** `python3 -m tjl check --trade runs/tjl/<D>/trigger-<T>.json --bars5 <file> --now HH:MM --qty <coins>
   --stop <current Liquid stop> --liquid-price <mark> [--fill <entry fill>]`
3. It proposes one of: **hold**; **move stop** (B: breakeven once +1R was reached, then under the latest confirmed
   5m swing low; never lower) as a `modify_position` preview -> approval -> `execute_tpsl`; **close** (A: both
   partials filled and a 5m close below the 21 EMA; both: from 15:45, flat by 15:51) as a `close_position` preview ->
   approval -> execute. Cancel leftover reduce-only partials after a close (`cancel_order`).
4. Update the Notion row (partials filled, stop moves in Notes). Overnight holds: rule still open, so flat by 15:51.

## 5. TJ audit

1. Notion: `notion-query-data-sources` SQL `SELECT * FROM "collection://424af207-66ae-8152-bcb1-000b322dc897"`
   (the R multiple formula can't be selected; the audit computes P&L $ / Risk $). Save the result as JSON.
2. **Run:** `python3 -m tjl audit --rows <file>`. Rows titled "TEST..." are ignored.
3. Report: verdict (TOO EARLY until 30 closed trades and 61 days; PAUSE at -$3,000 drawdown; then GO / EXTEND /
   NO-GO per the criteria), overall stats, splits by version (with and without shadow rows), grade, entry window,
   SPY regime, catalyst type, overnight, 5m confirm, each A+ box with/without, paired A vs B setups, Skipped/Missed.

---

## Files
| Path | What |
|---|---|
| `tjl/config.py` | Every threshold, sizing number, the 75-name universe with Liquid symbols and sector groups, ids |
| `tjl/sessions.py` | NYSE holidays and half days 2026-2027 (update each December) |
| `tjl/after_close.py` | Regime, sector heat, screen metrics, planned boxes, ranking, report |
| `tjl/morning.py` | Gap, premarket high/vol/RVOL, morning rules, provisional plan |
| `tjl/trigger.py` | 5m checks, version choice, sizing, Liquid order plan, Notion rows |
| `tjl/shadow.py` | Exit simulation on 5m bars (shadow rows, MFE/MAE) |
| `tjl/manage.py` | TJ check: breakeven, trail, 21-EMA exit, 15:51 close proposals |
| `tjl/audit.py` | Go/no-go audit of the Notion log |
| `tjl/sizing.py` | Sizing and Liquid price/size rounding (5 significant figures, 6 - szDecimals decimals) |
| `runs/tjl/<date>/` | Each routine's JSON state + markdown report (committed) |

Tests: `python3 -m pytest tests/test_tjl.py -q`.

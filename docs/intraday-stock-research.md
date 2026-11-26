# Intraday stock strategy: research notes (started 2026-11-26)

Status: **built 2026-11-26, paper test ready to start** (routines in `docs/tjl-routines.md`, code in `tjl/`). Goal: add an intraday stock strategy next to the after-market (after-close) analysis.
Read this first in a new session that continues this work.

## Decisions so far (from the user)
- **Stocks, not futures.** The ES backtests in `docs/strategy-search.md` and `docs/backtest-log.md` are not to be used as guidance here (different instrument and behaviour).
- **Both directions**, long and short. Shorts are same-day only (see video 3: swing shorts were the source's biggest leak).
- **Large caps** (liquid, and most of what Liquid lists). Volatility comes from catalyst days and a high average daily range, not from small caps.
- **Venue: Liquid first** (stock perpetuals, paper mode). Add other data sources only if Liquid falls short.
- **Overnight holds allowed** (for A+ trades; see the open question below).
- **Grade and size:** A+ = every filter passes plus a real catalyst, sized 2-3x; average setups normal or smaller.
- **Trade frequency: at most 2 trades a day**, and only when the stock and the after-market analysis line up. Zero-trade days are fine (no forcing trades).
- **No backtesting on stocks** (decided 2026-11-26). The strategy is validated by **forward paper trading on Liquid** instead. Don't spend a new session on historical stock backtests.
- **Run both Trend Join versions on paper** (video 4 and video 6 rules), each trade tagged with its version. Document everything; more documentation is better.
- **Long only for now.** Shorts come later.
- **Sizing:** see "Risk per trade" below ($250 normal / $500 A+ on a $25k sizing base).
- **A+ checklist:** drafted from videos 3, 4, 6 and 7 (see "Watchlist rules and A+ checklist"). Videos 7-8 give no grading system of their own.
- **Paper test length: at least 2 months** before judging.
- **After-market analysis definition: left to Claude** (draft defaults below, under "After-market analysis: draft defaults").
- **Daily loss limit: -$500 per day** (decided 2026-11-26). Once the day's realized + open loss on Trend Join trades reaches -$500, no new trades that day; open trades keep their stops. (With 2 trades max, that is one A+ stop or two normal stops.)
- **Risk per trade (decided 2026-11-26, replaces the 1%/2% of $10k plan): sized for a $25k account. A+ risks $500 (2%), normal trades $250 (1%).** The stop is placed per the rules, and the position is sized so that hitting it loses that amount: notional = risk $ / stop %. Never more than $500 per trade.
  - Liquid's paper reset only restores the default $10,000 (it cannot be set to $25k), so the paper account stays at $10k and **$25k is a sizing base, tracked in the trade log** (results in $ and R). No reset was done.
  - Margin cap: 10% of $25k = **$2,500 of margin per position**; leverage 2-10x (lowest that fits; most stock perps allow 10x, MU's max is 10x). Example: $500 risk, 3% stop -> $16,667 notional at 7x ($2,381 margin). $250 risk, 3% stop -> $8,333 at 4x ($2,083 margin). Stops under ~2% would need more than 10x: size down and log the lower risk.
  - Margin check on the real $10k paper balance: 2 Trend Join positions use up to $5,000 of margin; the RSI(2) test at 1x uses $5,000 per signal. **Done:** RSI(2) now runs at 2x ($5k notional, $2.5k margin; `docs/live-setup.md` updated 2026-11-26), so max margin in use = 2 x $2,500 (Trend Join) + 2 x $2,500 (RSI(2)) = $10,000.
- **Build: hybrid** (decided 2026-11-26). Mechanical rules in Python (`tjl/`, tested); a written routine (`docs/tjl-routines.md`) for the connector calls, report layout and approvals. Claude judges catalysts and traps in the report text.
- **Half days (1:00 PM closes): no Trend Join trades** (decided 2026-11-26). Logged as no-trade days.
- **Overnight holds allowed** (decided 2026-11-26, replaces "flat by 3:51"). Claude's default rule: at the 15:45 check, the rest of the position carries overnight if it is in profit and the last 5m close is above the 21 EMA; the stop then goes to at least breakeven. Otherwise flat by 15:51. On later days the same management continues (A: exit on a 5m close below the 21 EMA; B: trail under 5m swing lows) and the 15:45 check repeats. Funding is checked and logged. Shadow rows don't simulate overnight: a carried part is marked at the 15:50 open ("Carry (marked 15:50)").
- **Morning check at 9:00 ET every day** (30 minutes before the open; decided 2026-11-26). Entries keep the rules' 10:00 (A) / 10:05 (B) start.
- **Versions A and B share one Liquid position per ticker, so: alternate + shadow** (decided 2026-11-26). The real order follows one version, alternating when both qualify; the other version is logged as a **Shadow** row (new Status option in Notion) whose result is simulated from Webull 5m bars after the close. Shadow rows don't count toward the 30 trades; they give a paired A vs B comparison.
- **Keep all filters, in tiers** so there is activity most days on paper: the core Trend Join filters are the daily screen (setups on about 65-70% of days); the focus filters (ADR >= 4-6%, $100B+ cap, high liquidity, hot sector, near highs, not extended) grade a setup A+ and size it up. Paper results by grade will show whether the focus filters matter.

## Sources reviewed (all Humbled Trader, YouTube)
Videos were watched with the `/watch` skill. Gemini returned HTTP 503 ("high demand") on every model for hours on 2026-11-26, even for plain text calls, so the summaries came from Claude Code on the user's PC (local engine: captions + frames). Timestamps refer to the videos.

| # | Video | Main use |
|---|---|---|
| 1 | "VWAP Trading Strategy Crash Course" | VWAP setups and traps (discretionary) |
| 2 | "ChatGPT AI Made Me A TRADING STRATEGY" (`Jh5rJskkEkU`) | Plain VWAP cross has ~no edge |
| 3 | "I'm a Verified 7 Figure Trader, Here's how I use AI for Trading" (`zU0i9rBbEkI`, 12:32) | Stock-selection filters, regime and time-of-day data from a real trade log |
| 4 | "I Replaced my 6AM Premarket Trading Routine with Claude + Codex" (`PKFkJ4TprVo`, 23:29) | **Complete backtested rule set: Trend Join Long**, premarket report pipeline |
| 5 | "Live Trading on the 5-Minute Time Frame (how I keep it simple)" (25:57; presumably `gn02_Ic9i5U`) | **5m entry trigger (close above VWAP + 8 EMA)**, 8 EMA trail, first-red-day short |
| 6 | "Claude + IBKR API: Complete AI Trading Bot Guide" (`UgWQtQ3MEVE`, 23:27) | Automated Trend Join Long (second rule version); **bot is slightly negative on paper** |
| 7 | "How To Find Profitable Stocks To Trade – My Secrets REVEALED" (`VDN4jp4Uf1k`, 21:07, 2023) | **Watchlist scanner filters**, daily-level long/short decision, 1-2 names |
| 8 | "How to Find Stocks to Trade – Live Tutorial Shorting Stocks" (`1kFtbpWq7a4`, 14:14, 2022) | Short-selling logistics only (borrow, locate cost) |
| 9 | "How to Find Stocks to Trade for FREE (Day Trading for Beginners 2026)" (`sP9u2oiwikU`, 18:02; actually uploaded 2021-10-20) | Free Finviz small-cap scan, daily breakout-ready charts, "alert = go look" |

### 1. VWAP crash course
- Chart setup: session VWAP (bands off) + volume only; 2m and 5m intraday, daily alongside.
- Above VWAP = buyers in control (buy dips); below = sellers (short bounces).
- Setups:
  - **Breakout + VWAP hold, long** (10:21-13:12): daily breakout (prior high / daily level) at the open on strong volume; dips hold at/above VWAP with higher lows. Don't short these.
  - **VWAP reclaim, long** (5:43-7:18): below VWAP early, 1-2 failed reclaims, reclaim ~10:30-11:00 with higher lows and rising buy volume; enter the pullback.
  - **Breakdown fade, short** (7:27-8:26, 13:20-16:16): repeated VWAP rejections with rising sell volume; ride to the close.
  - **Parabolic-open short** (23:15-30:15): catalyst gap into daily resistance; short with the high of day as risk; add once VWAP breaks (COIN, about +$15k).
  - **Short-trap warning** (16:24-21:38): midday (11-12) below VWAP with higher lows on low volume -> squeeze on the reclaim. A reason not to short.
- Risk: stops on structure, **never right at VWAP** (algos wick through it, 38:05-42:46). Start partial, add on confirmation, scale out.
- No backtest; two live trades (COIN +$15k, PYPL about -$400).

### 2. ChatGPT VWAP strategy (transcript only)
- ChatGPT Pine Script: long above / short below a 30-period VWAP on TSLA daily, $100k.
- About 300 trades, +$384, 28% win, PF 1.77; would likely lose after commissions.
- Adding +3% targets, long only, shorts, -1% stop: +$121 / -$41 / +$48. Stops slipped about 10% on overnight gaps.
- Takeaway: a bare VWAP cross is not an edge; context (catalyst, breakout day, reclaim after failed attempts, time window, volume) has to carry it.

### 3. AI trade-log audit (one trader, Jan 1 - Aug 14 2026)
Speech came from a translated Arabic auto-dub (English captions were rate-limited); on-screen numbers were checked against frames. Some panels disagree with each other.
- Overall: 127 round trips, +$209,493 net, 56% win, PF 1.44, max DD -$123,311. Top 5 trades = 58% of gross profit; MU alone +$327k.
- **Focus filters** (72% win) vs avoid (35%):

| | Focus | Avoid |
|---|---|---|
| Average daily range (20d) | > 4% (6%+ preferred) | < 4% |
| $ volume per day | > $5B | < $2B |
| Market cap | > $100B | < $2B |
| Other | Hot sector (AI, semis, memory) | Swing shorts |

- Winners vs losers: ADR 7.1% vs 5.5%; $10.3B vs $3.1B per day; 6.1% vs 10.1% above the 20 SMA (less extended); entry-day gap 1.8% vs 0.9%; 86.7% vs 76.4% of the 52-week range.
- By sector: semis/memory 55 trades, 71% win, +$408k; everything else 61 trades, 41%, -$200k.
- By SPY day at entry: deep red +$28k, red +$110k, **sideways -$77k**, green +$163k.
- By entry time: premarket -$2k, 9:30-10:00 +$77k, 10:00-11:00 +$54k, 11:00-2:00 +$31k, after 2pm +$64k. (An earlier quick read said "skip 11-2"; the dashboard does not support that.)
- Holding period: same day 47 trades, 53% win, +$69k; overnight 24, 71%, +$46k; 2-4 days +$38k; 5-9 days -$52k; 10+ days +$123k.
- Tickers per day: 1-2 best (+$2-4k/day), 4+ negative.
- Shorts: intraday SNDK +$74k; swing short CAR -$63k.
- Sizing lesson: same size on best and worst setups was the biggest mistake -> size up only on A+.
- Routine: weekend screen and watchlist; AI to prepare the plan, not to pick trades.

### 4. Premarket routine + Trend Join Long rules
Rules were only on screen, in a prompt (about 5:14-6:15). Her blog post (linked in the video description) has the prompts in copyable form.

**Trend Join Long (day trade, long only)**

| Part | Rule |
|---|---|
| Filters | Gap > 3%, price > $3, market cap >= $1B, premarket relative volume > 1.5, price above the prior day's high |
| Window | Entries 10:00am-3:30pm ET |
| Entry | Break above both the premarket high and the prior high of day (most likely the day's high so far; confirm in the blog) |
| Stop | Lower of (premarket high - 1%) or low of day; that distance = 1R |
| Exits | 1/3 at +1R, 1/3 at +2R, trail the last 1/3 on the 21-EMA (timeframe not stated, probably 5m), flat by 3:51pm |
| Backtest (hers) | 54.6% win, PF 1.59, 280 trades. No date range, costs or data source given |

- Example (SSRM): trigger above PMH 30.53 and prior HOD 30.03; stop = LOD 28.95 (lower than 30.22); 1R about 1.58.
- Swing list (not fully specified): gap >= 8%, opens above the prior day's high and the 200d SMA, market cap >= $800M, real catalyst. Her swing backtests: news 57.6% win, PF 5.34; earnings 44.7%, PF 2.57.
- Pipeline: rules file (WATCHLIST_CRITERIA.md) -> free data (Yahoo, earnings/economic calendars) -> pass/fail flags ("the code never has an opinion") -> Claude writes the report, Codex reviews independently -> HTML email by about 8:45am. Rules decide who is on the list; the AIs only comment on quality.
- Context checked each morning: risk-on/off, VIX, oil, dollar, rates, breadth, economic calendar. Skip names whose catalyst is a denied rumor.

### 5. Live trading on the 5-minute chart
English captions + frames (a selection of the 100 frames was read). Mostly a 1m vs 5m comparison plus one live short.
- Indicators: VWAP and the **8 EMA** only (3:27); volume; prior day's high/low marked from the daily first (1:41). Daily MAs look like EMA 10/20 (too small to confirm).
- **Long trigger** (TSLA, 4:10-7:21): enter after the **first 5m candle that closes above both VWAP and the 8 EMA**. Wicks or intrabar pops don't count; 1m double bottoms and repeated 1m VWAP/EMA crosses are called false signals (5:57, 17:48).
- Stop: below VWAP / the 8 EMA (7:15). No fixed distance. A 1m low-of-day stop would have been hit by a false double bottom (5:30).
- Exits: partial at a daily level (TSLA prior-day high ~$252, 11:15); **trail the rest until a 5m candle closes below the 8 EMA** (8:44-11:15; TSLA ran ~$248 -> $259).
- **First-red-day short** (ZAPP live, 19:47-25:20): after a parabolic daily run, short the first red day once 5m candles stay below VWAP and the 8 EMA with weak bounces; add on a 5m bear flag; a bounce on lower volume than the prior selling candle keeps the short valid (21:17). Starter 500 sh at $12 avg, built to ~1,900 sh at $11.70; covered in pieces ($10.82, $10.22, rest ~12:00); target ~$10; closed ~$8.90. ZAPP was a hard-to-borrow, short-sale-restricted small cap.
- Time: open to ~11:30 is the most volatile "golden window" (15:03); choppy opens happen too; TSLA chopped 10:15-11:00.
- Filters: skip range-bound names (NVDA with a $1-2 range on $120, 16:25) and sideways, choppy days (15:23). Check SPY/QQQ before treating a gap down as bearish; gap downs get bought in strong markets without bad news (2:45).
- Performance: one day only, +$1,723.64 (ZAPP +$2,009.47, LGVN -$285.83). No win rate or sample.
- Warnings: 1m charts drive FOMO and revenge trading; 5m gives fewer trades but better R:R; some of it is hindsight (7:00, 21:17).

### 6. Automated Trend Join Long on an IBKR paper account
English captions + frames (strategy, backtest, scanner and dashboard frames read; sponsor 7:29-9:44 skipped). Rules read aloud at 12:05; `rules.json` shown at 13:37.
- **Rules (bot version):**
  - Filters: price above the prior day's high; prior close above the 200d SMA; gap >= 3% from the prior close.
  - Intraday: price above the premarket high and above today's high of day; relative volume >= 2.0 (14-day lookback). 5m chart, long only.
  - Stop: 1% below the low of day (12:26). Example: LITE entry 976.79, stop 940.75, R/share 36.04.
  - Exits: partial at +0.75R (size not stated), stop to breakeven at +1R, then trail under 5m swing lows; forced close 15:51.
  - Window: entries 10:05-15:30.
  - Size: risk 1% of the account per trade, max 10% of the account per position (12:47).
- **How it runs:** rescans every 30 minutes (5 possible, 15:14), places orders, Telegram alerts (scan list, buys, sells, partials, trails), end-of-day P&L, dashboard of R per trade. Demo universe: S&P 500 (503 tickers scanned in ~14 s, 20 survived the 3% gap filter, heavy semis/storage tilt). Her live manual trading: any stock > $1B cap and > $3; sectors with outsized relative strength (semis, AI).
- **Results:**
  - TradingView backtest, MU 5m, 2026-03-09 to 05-21: 14 trades, 64.3% win, PF 2.48, +12.1%, max DD 7.25%. Same strategy on TSLA (2025-10-01 to 2026-05-15): -7.8%, max DD 24.9%.
  - "Previously" recap: 175 trades, 55.4% win, +$16,218 across a stock list.
  - **Live paper bot (to 2026-05-31): month 17 trades, 35.3% win, total -0.72R (-$134.78); year 29 trades, 44.8% win, avg -0.04R (-$47.75).** She calls it "very meh": the backtest doesn't carry over, and her manual execution isn't fully coded; her manual trading does much better.
- **Warnings:** AI is a multiplier; with no edge a bot loses faster. Paper trade "until it runs clean for weeks". Backtests don't transfer directly to live.

**The two Trend Join Long versions disagree:**

| | Video 4 (premarket report) | Video 6 (IBKR bot) |
|---|---|---|
| Relative volume | > 1.5 | >= 2.0 (14-day lookback) |
| Entry window | 10:00-3:30 | 10:05-3:30 |
| Stop | Lower of PMH - 1% or low of day | 1% below the low of day |
| Exits | 1/3 at +1R, 1/3 at +2R, trail last 1/3 on the 21-EMA | Partial at +0.75R, breakeven at +1R, trail under 5m swing lows |
| Backtest | 54.6% win, PF 1.59, 280 trades | 64% win, PF 2.48, 14 trades on MU (TSLA lost) |
| Sizing | Not given | 1% risk per trade, max 10% of the account |

Shared by both: gap > 3%, price > $3, cap > $1B, prior close above the 200d SMA, price above the prior day's high, trigger above both the premarket high and the high of day, flat by 3:51.

**What this means for us:** the only out-of-sample, automated evidence for Trend Join Long (her own paper bot) is flat to slightly negative. Her edge looks discretionary (stock and sector selection, manual execution), which matches video 3's finding that selection, not entries, made her year. Treat the published backtests as unproven; test both exit versions as separate variants on the same stock list.

### 7. How the presenter finds stocks (2023)
English captions + frames (scanner settings and Finviz screener read at full resolution).
- **Trade Ideas Pro, "Mid-Big Cap Gainers"** (5:13-7:36, settings on screen): price $5-$400 ($1 OK); change from prior close >= 2%, no max; float >= 10M (5M OK); market cap >= $1B; premarket volume >= 20,000 (low on purpose: large caps get volume after the open); sorted by biggest % change. Display columns: average volume, % institutional, sector, relative volume. Not filtered on ADR or sector.
- **Finviz (free)** (12:20-13:55): market cap > $2B (Mid+), average volume > 1M, relative volume > 1.5, float > 10M; then the Charts view to see which daily charts break out or down. Data delayed ~15 min, so evening/swing planning only unless Elite. Other free scanners named: Webull desktop, thinkorswim (10:19).
- **Daily levels decide direction** (18:03): mark prior close, prior highs/lows and gap-fill areas. BBIO +67% premarket gapped **into** the $18 daily level and couldn't hold it -> short idea, not long (not traded). AZUL +21% on an earnings beat held above $5.30/$5.60 -> long "join the trend", targets $6.50-6.70 then $7.20; it squeezed.
- **Ranking:** sort by gap %, look at the top ~5, then volume, average volume, institutional %, sector (7:57); work down until one fits a strategy (15:39); trade only 1-2 (20:27).
- **When:** every morning premarket, or the evening before with Finviz (1:53, 12:48). "Most of the work happens outside market hours" (0:52).
- No catalyst grading, no A+ system, no performance numbers.
- Warnings: beginners stick to mid/large caps (2:06); a scanner is not a buy signal, skip names that don't follow the plan (19:45); mark levels premarket, "failing to plan is planning to fail" (20:05); don't trade the whole list (20:27).
- Filters tightened over time: 2023 gap >= 2% / cap >= $1B; 2026 (videos 4 and 6) gap >= 3% and premarket RVOL > 1.5 / >= 2.0.

### 8. Shorting logistics (2022)
English captions + frames. Not a watchlist video despite the title.
- Large caps are easy to borrow (ETB, "S" next to the ticker, 3:50); pumped penny stocks and overextended small floats are hard to borrow (6:23).
- **Locate rule** (11:35-13:21): borrow cost <= 1% of the stock price (ideally 1-2 cents on a $5 stock); above 1%, require >= 1:4 reward to risk.
- Brokers for hard-to-borrow: TradeZero (< $30K accounts, Canada), Cobra, Centerpoint.
- **On Liquid this doesn't apply** (perpetuals, no borrow; funding instead). Keep for later if shorts ever move to a stock broker.

### 9. Free Finviz watchlist (2021, small caps)
English captions + frames. Title says 2026, but uploaded 2021-10-20 (Finviz screen dated 2021-10-08).
- **Finviz scan** (0:57-4:15; URL filters `cap_smallunder, sh_curvol_o5000, sh_price_u10, sh_relvol_o1.5`): any exchange; market cap small (< $2B; separate large-cap scan mentioned); relative volume > 1.5 ("ideally over 1 or even 2"); current volume > 5M (1M in general); price < $10 for small caps. No gap, float, ADR or sector filter; average volume ignored.
- **Daily chart** (5:20-11:23): look for stocks **consolidating under resistance**, "slowly about to set up for a breakout"; rising daily volume ("increasing volume precedes the breakout, consistent volume sustains it", 7:06). A long is valid only after a break **and hold** above the most recent resistance. Examples: CEI key $2.46 (targets $3, $3.70, $4+); GROM key ~$5.50 (support $3, target ~$6.70); NXTP held $1.30 for weeks, broke $1.50.
- Average daily volume should be at least 1-2M shares (12:44). Only shown: a 200-day SMA on the thinkorswim daily chart.
- **Narrow to 3 names**, mark levels in thinkorswim, add to the watchlist, **set price alerts at key resistance** (shown: "CEI when mark >= 2.46").
- **An alert is not an entry** (15:13-16:15): VYGR touched $4.60 resistance; buying the touch meant a 20 cent drawdown; she waited for higher lows and a retest, then it broke to ~$4.90.
- "A+ setup" = the right volume, the right breakout daily chart and the right levels (16:36); no scoring.
- No catalysts, no performance numbers. Warnings: don't be "a sheep" following scanners/chat; don't buy everything the scan returns; breakouts without volume "pop and fail"; not every name will run.
- Small caps are outside our universe (Liquid is large caps), so only the method carries over.

## Candidate strategy (draft, not final)
- **Core:** Trend Join Long, two exit variants to compare (video 4: thirds at +1R/+2R and a 21-EMA trail; video 6: partial at +0.75R, breakeven at +1R, trail under 5m swing lows). Add the 200d SMA filter (both versions use it).
- **Base sizing (video 6):** risk 1% of the account per trade, max 10% of the account per position; A+ 2-3x would need that cap revisited.
- **On top:** video 3 focus filters (ADR >= 4-6%, $100B+ cap, hot sector, near the 52-week high, not stretched above the 20 SMA), skip sideways SPY days, 1-2 names per day, A+ sizing 2-3x.
- **Entry confirmation (video 5):** act only on a 5m candle **close** (above VWAP and the 8 EMA for longs, below both for shorts), not on wicks or 1m signals. Could serve as the confirmation for Trend Join breakouts, or as its own VWAP-reclaim trigger.
- **Trail option (video 5):** 5m close below the 8 EMA, as an alternative to video 4's unspecified 21-EMA trail. Test both.
- **Shorts:** video 1 breakdown fade and parabolic-open short, plus video 5's first-red-day short after a parabolic daily run; same day only. On Liquid there is no borrow or short-sale restriction, but Liquid lists few parabolic small caps, so first-red-day shorts will be rare on large caps.
- **Chop filter (videos 3 and 5):** skip sideways SPY days and range-bound names.
- **Overnight:** idea: on A+ trades only, carry the trailed last third overnight while above the 21-EMA; everything else flat by 3:51.

### Routine
1. **After the close (the after-market analysis):** SPY regime (trend vs sideways), VIX, sector ranking, screen Liquid's stock list (ADR, market cap, near-high, extension), tomorrow's earnings/catalysts -> watchlist with levels and a planned grade.
2. **Morning (about 9:00-9:30 ET):** which names gap 3%+, premarket high and volume, catalyst check -> final 1-2 names and triggers.
3. **10:00-3:30:** trigger alerts and trade management.
4. **After the session:** trade audit in the style of video 3 (P&L by setup, time, regime, grade/size, holding period) from Liquid's history.

## Liquid data check (2026-11-26)
Liquid lists about 120 single stocks and ETFs (`xyz:`, `para:`, `io:` prefixes), mostly large caps: NVDA, TSLA, AMD, META, MSFT, AAPL, AMZN, GOOGL, AVGO, MU, SNDK, para:COHR, MRVL, WDC, NFLX, PLTR, COIN, MSTR, HOOD, ARM, SMCI, ORCL, TSM, LLY, plus ETFs (SMH, SOXL, TQQQ, XLE, IGV, XBI, TLT).

They are **24/7 perpetuals** (NVDA candles printed on Thanksgiving with the NYSE closed). Shorting needs no borrow; there is funding; max leverage 10x on MU.

| Need | Liquid | Note |
|---|---|---|
| ADR | Yes | Daily candles; drop weekend candles first (tiny volume and range) |
| Market cap, sector | Yes | `get_asset_profile` |
| $ volume ($5B rule) | **No** | Only Liquid's own volume (MU about $107M/24h vs billions on the exchange). Use market cap >= $100B plus rank by Liquid volume |
| Sector heat | Proxy | Sector ETFs and member returns from candles |
| SPY regime | Yes | `xyz:SP500` daily candles |
| 52-week high | Partial | `show_chart` returns at most 200 candles (about 140 trading days) |
| SMA/EMA, RSI, ATR | Careful | `get_technical_indicators` counts weekend candles (calendar days); compute our own from weekday candles |
| Gap | Different | No opening gap; use the 9:30 ET price vs the 4:00 PM close |
| Premarket high | Yes | 4:00-9:30 ET candles (thin overnight trading) |
| Premarket RVOL | Weak | Liquid's own volume only |
| Earnings | Yes | `upcoming_earnings` (week or month, with market cap) |
| News | Weak | General headlines; unusual-activity list was all crypto |
| Intraday VWAP | Yes | 5m candles with volume, 200 per call (one session). Built from Liquid's volume, so not the exchange VWAP |
| Extra | Yes | Funding, open interest, smart money vs crowd positioning |

On 2026-11-26 MU was about $605, down about 50% from a June high near $1,250 and below its 20/50/200-day averages: the 2026 "hot sector" of video 3 has since crashed, so sector heat must be re-ranked daily.

## Open questions and risks
- **Universe size:** with ~120 Liquid stocks, many days will have no 3%+ gapper. Estimate the trade frequency from Liquid candles before designing.
- **Order approval:** Liquid needs the user's approval for every order (entry, stop, two partials, trail). Workable on paper with the user at the phone; slow for fast breakouts.
- **Stop size:** the low-of-day stop can be wide (5% on SSRM). Size from the stop distance, not a fixed notional, especially with 2-3x A+ size.
- **10:00 start vs 9:30-10:00 being the best window** in video 3. Test both.
- **Overnight vs flat by 3:51:** the rules say flat; video 3 data favors overnight holds. User allowed overnight; the exact rule is undecided.
- **The automated version already underperformed:** video 6's paper bot is -0.72R over 29 trades. A mechanical copy may not have an edge; any test must include costs and a period the rules were not tuned on.
- **Evidence quality:** one trader, one year (a semis/memory boom), top 5 trades = 58% of gross; the Trend Join backtest has no period or costs and was run on the whole market, not Liquid's list.
- **Real dollar volume / exchange data:** if needed later, a stock-data source (Yahoo as in video 4, Databento equities, Polygon or Alpaca). Not added yet (Liquid first).

## Tooling notes for the next session
- `/watch` in cloud sessions: Gemini key is set in `~/.config/watch/.env` of the cloud container (not in the repo), and `generativelanguage.googleapis.com` was added to the Trading environment's allowed hosts. Gemini returned 503 all day on 2026-11-26; the local engine can't run in the cloud container (YouTube blocked, no yt-dlp).
- **Working route:** run `/watch` in Claude Code on the user's Windows PC (local engine works: Python, ffmpeg, yt-dlp installed) and paste the summary. Remote Control (`claude remote-control` in `C:\Users\valde\trading-research`) starts sessions on the PC but does not attach the PC to an existing cloud session.
- Prompt used for each video:
  `/watch:watch <URL> | Summarize this trading video for building an intraday stock strategy. With timestamps, list: setups and exact entry triggers, stop placement, targets/exits, position sizing and adding/scaling rules, time-of-day windows, indicators and settings, stock selection criteria (catalysts, gaps, volume, market cap), any pre-market or after-close routine, any performance numbers (win rate, P/L, sample size), and warnings/pitfalls. Separate what is said from what is only shown on screen.`

## Confirmed Trend Join Long rules (from the presenter's blog posts, read 2026-11-26)
Sources: "How to Build a Free AI Premarket Analyst with Claude & Codex" (https://www.humbledtrader.com/blog/claude-codex-ai-premarket-analyst/, 2026-06-16; linked from video 4 as linktw.in/ai-premarket-analyst) and "Build an AI Trading Bot with Claude + Interactive Brokers" (https://www.humbledtrader.com/blog/ai-trading-bot-claude-ibkr/, 2026-05-21, updated 2026-09-24; video 6). The bot post says its rules come from the strategy backtested in "the last blog post" (TradingView + Claude, Part 1 of the series).

### Version A: "TJL-report" (premarket report, `WATCHLIST_CRITERIA.md`, video 4)
Verbatim rules: "Premarket selection, all required: Gap % vs prev close > 3%; Price > $3; Market cap > $1B; Premarket relative volume (RVOL) > 1.5; Price breaking above yesterday's high. Intraday plan: window 10:00am to 3:30pm ET; trigger price > premarket high AND > prior high-of-day; stop 1% below premarket high or LOD (whichever is lower) = 1R; scale 1/3 at +1R, 1/3 at +2R, trail the last 1/3 on the 21-EMA; flat by 3:51pm." Backtest stated: 54.6% win rate, profit factor 1.59, 280 trades.
- Her scanner's code flag: `day_eligible = gap > 3 AND price > 3 AND market_cap > $1B AND rvol > 1.5 AND price > prior-day high`.
- RVOL caveat (hers): free data (yfinance) has almost no premarket volume, so her RVOL is today's volume / 20-day average volume, a full-day stand-in; true premarket RVOL needs a premarket feed. **We use Webull's real extended-hours volume instead.**
- Her scanner pre-filters movers at |gap| >= 4% and price >= $3 (top 12) before the 3% rule; a quiet morning can be thin ("temporarily lower the gap filter to 2%" for a demo).
- Swing list (not traded by us yet): gap >= 8%, price > $3, open > prior-day high, open > 200-day SMA, market cap >= $800M, real catalyst (earnings on the gap day, or news with no earnings); entries/exits "still being built". Backtest: 57.6% / PF 5.34 (news), 44.7% / PF 2.57 (earnings).
- Catalyst handling in her prompts: no catalyst found = SKIP; up on bad news (dilution, probe, miss) = TRAP. Catalyst ranking used by her second AI: earnings/guidance > M&A > FDA > index inclusion > sympathy > analyst upgrade > none.

### Version B: "TJL-bot" (IBKR bot, `rules.json`, video 6)
Verbatim `rules.json`:
```
strategy_name: Trend Join Long; direction: long_only; trade_timeframe: 5m
universe_filters: index S&P 500, min_price_usd 3.0
daily_filters: D1_above_prior_day_high true; D2_prior_close_above_sma200 true; D3_min_gap_pct_from_prior_close 3.0
intraday_filters: I1_above_premarket_high true; I2_above_today_hod true; I3_rvol_min 2.0; I3_rvol_lookback_days 14
time_filter: earliest_entry_et 10:05; latest_entry_et 15:30; force_close_et 15:51
exit: initial_stop_rule lod_minus_1pct; partial_profit_trigger_R 0.75; partial_profit_fraction 0.3333;
      breakeven_trigger_R 1.0; post_breakeven_trail swing_low_5m_2_2
risk: max_risk_per_trade_pct 1.0; max_position_size_pct_of_portfolio 10; max_concurrent_positions 5
```
- Her words: "I2: price above today's high so far (joining strength, not buying a fade)"; "If all six filters pass, the bot takes a trade on the stock. If any one fails, it doesn't execute."
- Her `.env`: paper trading, portfolio $25,000, max trade size $2,500, max 5 trades a day, max risk 1% per trade.

### What the blogs settle
- **"Prior high-of-day" = today's high so far** (version B states it; same trigger in both).
- **Version B's partial = 1/3** at +0.75R; trail after breakeven = **5m swing lows with 2 bars on each side** (`swing_low_5m_2_2`, our reading of the name).
- Both versions run on the **5-minute** chart (B states it; A's 21-EMA trail is assumed to be on the 5m too, not stated).
- Version B also caps concurrent positions at 5; we cap at **2 trades a day** (user decision).

### Our assumptions where the blogs are silent (tag them in the trade log)
- A's 21-EMA trail: 5m chart; exit when a 5m candle closes below the 21-EMA.
- A's stop when "1% below premarket high" vs LOD: take the lower price, as written.
- B's RVOL >= 2.0 over 14 days: Webull volume so far today vs the 14-day average volume for the same time of day if available, otherwise vs the 14-day average daily volume (full-day stand-in, like hers).
- Market cap > $1B (A) is implied for B by the S&P 500 universe; we apply it to both.

## Watchlist rules and A+ checklist (draft, 2026-11-26)
Built from videos 3 (trade-log audit), 4 and 6 (Trend Join rules) and 7 (scanner). Universe: Liquid's US-listed single stocks. Data: Webull (real quotes, extended hours, market cap, 52-week range, sectors), Liquid for orders. Long only for now.

### Step 1: after the close (watch candidates)
Keep names that pass all of:
- Price >= $5 (video 7) and prior close above its 200-day SMA (videos 4, 6).
- Market cap >= $1B and average volume >= 1M shares (videos 4, 7; every Liquid stock should pass).
- Not range-bound: ADR20 >= 3% (video 5's "skip tight ranges"; the A+ bar is higher).
Mark each name's daily levels: prior close, prior high/low, recent swing highs/lows, gap-fill areas (video 7).
Flag **breakout-ready** daily charts: consolidating just under resistance with rising daily volume (video 9). Used as a tiebreaker when ranking.

### Step 2: morning (about 9:00-9:30 ET), the trade list
- Gap >= 3% vs the prior close (videos 4, 6; 2% acceptable per video 7 if the list is empty), from Webull's extended-hours price.
- Premarket volume >= 20,000 shares and premarket relative volume >= 1.5 (video 4; video 6 uses >= 2.0, tag which one a trade met).
- The gap **holds above** a daily level, not gapping **into** one (video 7's AZUL vs BBIO). Long only, so a gap into resistance is a skip.
- Rank by gap %, take the top ~5 to the Webull "Trend Join" watchlist, trade at most 2 (videos 3, 7).
- SPY regime "sideways" -> no trades that day (videos 3, 5).

### Step 3: grade (A+ = every box ticked)
| # | A+ condition | Source |
|---|---|---|
| 1 | Passes steps 1-2 | videos 4, 6, 7 |
| 2 | ADR20 >= 4% (6%+ counts as top quality) | video 3 |
| 3 | Dollar volume >= $5B/day (20-day average) | video 3 |
| 4 | Market cap >= $100B | video 3 |
| 5 | In a top-2 hot sector (Webull sectors D5/MO1 + our groups) | video 3 |
| 6 | Real catalyst: earnings or company news today; not a rumor, not a denied rumor | videos 4, 7 |
| 7 | Not extended: <= 10% above its 20-day SMA | video 3 (winners 6.1% vs losers 10.1%) |
| 8 | In the upper part of its 52-week range (about >= 80%, or within ~15% of the 52-week high) | video 3 (winners 86.7%) |
| 9 | SPY trending (not sideways) | video 3 |

- **A+** -> risk 2% of the account; may carry the trailed last third overnight.
- **Everything else that passes steps 1-2** -> normal, risk 1%; flat by 3:51.
- Log each condition's tick per trade so the 2-month paper test can show which conditions matter.

### Step 4: trigger and trade
**The alert means "go look", not "buy"** (videos 7, 9): confirm the break holds before entering. Per the Trend Join versions (videos 4 and 6, tag each trade): after 10:00/10:05, break above both the premarket high and the high of day; optional video 5 confirmation (5m close above VWAP and the 8 EMA). Trigger price goes into a Webull price alert; the user messages Claude when it fires; Claude prepares the Liquid paper order.

## After-market analysis: draft defaults (chosen by Claude, 2026-11-26; change freely)
Run once a day after the close, in the same message as the RSI(2) check (one "daily check" message from the user; no scheduled tasks).
1. **Regime (SPY = `xyz:SP500`, weekday daily closes):** *trend* if the close is at least 1% from its 20-day SMA and the 20-day SMA's 5-day slope has the same sign; otherwise *sideways* -> no new Trend Join trades tomorrow (video 3: sideways days lost $77k). Also report the 200-day state; longs only below it with an A+ grade.
2. **Sector heat:** rank groups by 5-day and 20-day return (average rank): semis/AI (SMH; NVDA, AMD, AVGO, MU, MRVL, SNDK, WDC, LRCX, AMAT, ARM, TSM), software (IGV; MSFT, ORCL, NOW, CRWD, PANW, NET, PLTR), internet (GOOGL, META, AMZN, NFLX), crypto-linked (COIN, MSTR, HOOD, IREN, CIFR), energy (XLE, CVX, VST, GEV), health (XBI, LLY, MRNA, HIMS). Top 2 groups = hot.
3. **Watchlist screen** (Liquid's US-listed stocks, weekday daily candles): prior close > $3 and above its own 200-day SMA (computed from weekday candles); ADR20; distance from the 20-day SMA; position in the available high/low range. Rank: hot sector first, then ADR20, then nearness to highs; mark anything > 10% above its 20-day SMA as extended.
4. **Catalysts:** `upcoming_earnings` (week) and `get_news` headlines for the names on the list.
5. **Output:** top 5 names (trade at most 2), each with prior-day high/low, the 200d/20d levels, ADR, sector, catalyst, planned grade (A+ or normal) and risk (2% or 1%).
6. **Morning update (about 9:00-9:30 ET):** which watchlist names gap >= 3% vs the 4:00 PM close (Liquid price), their premarket high, Liquid volume vs normal; confirm or drop.

## Build (2026-11-26)
Routines: `docs/tjl-routines.md` (after-close check, morning check, TJ trigger). Code: `tjl/` (`python3 -m tjl after-close|morning|trigger|shadow`), tests `tests/test_tjl.py` (15 pass). Outputs per day in `runs/tjl/<date>/` (committed so a new container can continue).

**Choices made while building (Claude; change freely):**
- **Universe: 75 names** = Liquid's US-listed single stocks with Webull market cap >= $1B (`tjl/config.py`). Out: ETFs and leveraged ETFs, non-US listings (SK Hynix, Samsung, Xiaomi, ...), pre-IPO markets (SpaceX, Anthropic), STRC (preferred), QNT (Liquid/Webull mapping unverified), sub-$1B names. Liquid prefixes: `para:` for COHR, SMCI, CRDO, TER, STX, SOFI, MELI, VST, CIEN, CIFR; `io:` for IONQ; `xyz:` for the rest.
- **SPY regime and sector heat use Webull's real SPY/ETF daily bars** (not Liquid's `xyz:SP500`, whose 00:00 UTC candles don't match the session). Same rule as the draft: trend if the close is >= 1% from the 20d SMA and the 20d SMA's 5-day change has the same sign.
- **Sector groups** (12; median member return, 5d and 20d ranks averaged, groups with < 3 members can't be hot): Semis, Memory/storage, AI hardware/optical, AI cloud, Software, Internet, Crypto-linked, Energy/power, Health, Consumer/auto, Financials, Space/quantum/other. Webull's own sector table (D5/MO1) is reported as context only.
- **Ranking of the screen:** hot group first, then ADR20 in 1% steps, then breakout-ready, then 52-week position. **Breakout-ready** = close within 3% of the prior 20-day high and 5-day average volume above the 20-day average.
- **Morning:** all step-1 names are scanned for gaps (not only the top 5), since a gapper can come from anywhere on the list. Premarket RVOL = premarket volume up to now / average over the same clock window of the prior 14 sessions (Webull 5m PRE bars). Final names ranked by A+ boxes met, then gap. "Gap into resistance" is flagged when a swing high, the 52-week high or the 200d SMA sits within 1 ADR above the premarket price (Claude decides).
- **Trigger:** trigger level = max(premarket high, high of day before the current 5m bar); the price must be above it. Version B's RVOL = RTH volume so far / average over the same clock window of the prior 14 sessions. Webull levels set the stop %; Liquid prices are mapped by the same percent from the Liquid mark (perp and stock prices differ slightly).
- **Shadow simulation conventions** (conservative): entry at the Webull price at the trigger time, simulation from the next 5m bar, stop checked before targets inside a bar, flat at the 15:50 bar's open, fees 0.15% of notional. A's 21-EMA exit applies to the last third only after both partials; B's breakeven at +1R, then the stop trails confirmed 5m swing lows (2 bars each side).

**First runs (data through Wed 2026-11-25; Thursday 11/26 is Thanksgiving, Friday 11/27 a half day):**
- After-close (session 11/25): SPY **Trend down** (-3.2% vs the 20d SMA, below the 200d) -> A+ longs only. Hot groups: Financials and Consumer/auto (relative leaders in a selloff; semis/memory/crypto worst, -30 to -39% over 20 days). 12 of 75 pass step 1. Top 5: GME, TWST, MRNA, CRWD, NET; none can reach A+ (max 5 of the 7 after-close boxes), so no trade is likely until the regime improves. Watchlist "Trend Join" filled with these 5. Next tradable day: Mon 11/30.
- Replay of 11/25 (after-close as of 11/24, morning with real premarket bars to 9:25): every name gapped down (TSLA -3.7%, CRWD -5.2%), so **no final names**, which is correct for a gap-down day.
- Forced test (not a real setup): TSLA broke its premarket high at 13:45 on 11/25. The trigger, order plan and both shadow simulations were checked against the raw bars (+0.15R MFE, -0.10R MAE, flat at 15:50 for about +0.06R net). A test row "TEST (delete) 2026-11-25 TSLA A" was written to Notion to check the field mapping (all fields accepted).
- RSI(2) (11/25 candle): S&P500 RSI 56.0, below the 200d -> EXIT signal but nothing held; NASDAQ100 RSI 39.0 -> NONE. Paper account $10,000, no positions.

**Added later on 2026-11-26:** "TJ check <ticker>" (`tjl/manage.py`: hold / breakeven / swing-low trail / 21-EMA exit / 15:51 close, proposed as Liquid previews for approval; replayed on the TSLA test: hold at 14:30, close at 15:47) and "TJ audit" (`tjl/audit.py`: go/no-go verdict and splits from the Notion log; today: TOO EARLY, 0 trades). 18 tests pass.

**Still open (user decisions):** shorts. (Overnight and the 9:00 morning check decided 2026-11-26.) **To verify on the first live days:** Webull snapshot fields in premarket, Liquid size decimals and real fees from the first fill.

## Intraday trigger: connection options (2026-11-26)
| Option | What it gives | Status |
|---|---|---|
| **TradingView alerts** | Price alerts or a Pine script alert on the 5m chart (break above PMH and HOD, optional 5m close above VWAP + 8 EMA), pushed to the phone app, email or a webhook (paid plan). Uses real exchange data, so premarket high, VWAP and volume are the real ones. | No connector found in Claude's directory. Works without one: the alert reaches the user's phone, the user messages Claude, Claude prepares the Liquid order. The repo already has Pine code (`pine/`). |
| **Webull connector** | Real stock quotes, watchlists, analyst data and more (70+ tools); may cover premarket movers / screening. | Connected at the org level but **needs the user to sign in again** in claude.ai connector settings. Check its tools after sign-in. |
| **Finviz** | Gap/volume screener (premarket gappers); Elite has alerts. | No connector. The public screener page could be read with Firecrawl (check finviz's terms). |
| **Liquid** | `edit_watchlist` (named watchlists in the Liquid app); prices and 5m candles on request. | No alerts or scheduler. |
| **Script on the user's PC** | A loop like video 6's bot (scan every 5-30 min, alert by Telegram/email). | Most work; only if the simpler options fall short. |

Draft default: TradingView alerts for the trigger (real data, phone push), Liquid for paper orders, Webull (after sign-in) to cross-check real premarket gappers and volume.

**Free start (chosen 2026-11-26): Webull price alerts** (decided by the user), in the Webull app (real exchange data incl. premarket). No Pine script or webhook needed. To check after the Webull connector is signed in again: whether its tools can create the price alerts and a "Trend Join" watchlist directly, and give real premarket gappers/volume for the morning update.
1. The morning update gives each of the 1-2 names one **trigger price** = max(premarket high, high of day so far), plus the stop and 1R.
2. The user sets one "price crosses above" alert per name (2 alerts max).
3. When it fires after 10:00, the user messages Claude ("TJ trigger NVDA"). Claude checks the 5m chart on Liquid (optional video 5 rule: a 5m close above VWAP + 8 EMA) and prepares the Liquid paper order with the stop; the user approves.
4. If price makes a new high of day before 10:00, the trigger moves up to it (reset the alert at 10:00).
Fallback with no app at all: the user messages Claude at fixed times (e.g. 10:00, 10:30, 11:00, then hourly) and Claude checks the levels on Liquid; free, but late on fast breakouts.

**Webull connector test (2026-11-26): works, read-only.**
- Authorization: the one account (`...9227`) is **Non-Trading**: market data, account info and watchlists only; no orders (fine: orders go through Liquid paper).
- **No tool creates price alerts.** The trigger alerts have to be set by hand in the Webull app (the `get_financial_alert` tool is a risk-indicator lookup, not price alerts).
- Watchlists: can list, create (max 20), add/remove symbols. **"Trend Join" watchlist created 2026-11-26** (id `469684da9c224d59978706608a36c55a`), empty for now. The after-market analysis fills it with the day's top names (`add_watchlist_instruments` / `remove_watchlist_instruments`, category US_STOCK); the user sets trigger alerts on them in the Webull app.
- **Fills the Liquid data gaps with real exchange data:**
  - `get_stock_snapshot` (up to 100 symbols, `extend_hour_required`): price, open/high/low, real volume, market cap, 52-week high/low, pre/after-hours last price, change, volume and high/low. (MU: market cap $680B, 52-week high $1,254.61, close $601.25, after-hours $615.30.)
  - `get_stock_bars` (up to 20 symbols, 1200 bars, M1-M240/D/W, `trading_sessions` PRE/RTH/ATH/OVN): real premarket high and 5m bars with real volume (real VWAP).
  - `get_gainers_losers` (`rank_type` PRE_MARKET / DAY_1 / MIN_5 ..., sort incl. RELATIVE_VOLUME_10D, MARKET_VALUE): premarket gappers. The top of the list is micro caps, so screen our own list with snapshots instead of using the raw ranking.
  - `get_market_sectors` (D1/D5/MO1/MO3): sector performance (on D5: semis -7.6%, software -2.0%, pharma +2.7%).
  - Also: earnings calendar, macro calendar, news, unusual activity, 52-week high/low rankings, most active.
- So the after-market screen and morning update can use **Webull for data** (real $ volume, market cap, 52-week range, premarket high/gap/RVOL, sector heat) and **Liquid for paper orders**.

## Liquid checks for the paper test (2026-11-26, read-only)
- **Paper mode:** enabled on Claude's Liquid connection. Paper account: **$10,000 equity, no positions, no margin used.** The paper account is shared by wallet (RSI(2) test uses the same one).
- **Fees (Liquid's `help`):** Liquid charges 0.05% of notional on every fill (open and close); the exchange's maker/taker fee is added on top and varies by market. A paper fill shows one combined fee. So a round trip costs roughly 0.1% plus exchange fees (about 0.15-0.2% in total, to be confirmed from the first paper fills). With a 2-5% stop that is about 0.03-0.1R per trade.
- **Spreads** (2026-11-26, market closed for Thanksgiving): MU 607.12 / 607.17 (0.008%), NVDA 150.21 / 150.22 (0.007%). Top-of-book depth is a few thousand dollars per level, enough for $1-10k paper positions. Recheck during US hours.
- **Funding** (overnight holds): MU -0.0035% at the time (Hyperliquid funding is hourly; about 0.05% over a 16-hour hold at that rate). Sign and size vary; read it with `analyze_market` before carrying a position overnight.
- **Stop and take-profit at entry: yes.** `execute_order` takes `tp` and `sl` with the entry, so one approval covers entry + stop. Caveat: if a market order only partly fills, the attached TP/SL is not placed (set it with `execute_tpsl`).
- **Partial take-profits: yes.** A `reduceOnly` limit sell at the target with a coin quantity (e.g. 1/3 of the position). These can be placed right after entry as resting orders, so the approvals happen up front.
- **Stop moves (breakeven at +1R):** `modify_position` (preview) -> `execute_tpsl` (needs approval each time).
- **Trailing stop: native, but percent only.** `set_trailing_stop` trails the best price by a fixed price distance (percent / leverage), optional `activationPrice`, optional `sizePercent`. It **cannot follow an EMA or swing lows**. Options:
  - Version A's 21-EMA trail and version B's 5m swing-low trail are done by hand: Claude recalculates at check-ins and moves the stop with `execute_tpsl` (approval each time).
  - Approximation for version B: a trailing stop with `activationPrice` = entry + 1R and a retracement of 1R. At activation the stop sits at entry (breakeven), then trails by 1R. This replaces "breakeven at +1R, then trail" with one approval. Tag such trades `trail=native`.
- **Order flow per trade (paper):** (1) entry with stop attached; (2) reduce-only partial(s); (3) later stop moves or a native trailing stop; (4) close by 3:51 with `close_position` (preview + approval). Every step needs the user's approval in chat.
- **Paper capital: decided 2026-11-26 (see Decisions).** Background: The $10k paper account is shared with the RSI(2) test ($5k notional per signal, up to two markets). Trend Join risk sizing: 1% = $100, A+ 2% = $200 of risk; with a 3% stop that is about $3,300 / $6,700 notional. Version B's "max 10% of the portfolio per position" ($1,000) conflicts with that risk (it would cap risk far below 1% unless the stop is 10%+). Options: reset the paper account to a larger balance (`reset_paper_account`, affects RSI(2) too), use 2-5x leverage so margin stays small, or apply the 10% cap to margin instead of notional.

## Trade log (Notion, created 2026-11-26)
- Page: **"Forward Test: Trend Join Long (stocks)"** (private, workspace level): https://app.notion.com/p/424af20766ae813a85dbcaddf592a712 . Holds the setup summary and logging rules.
- Database: **"TJL Trades"** inside it: https://app.notion.com/p/424af20766ae81f8a9b9e7b9c3f59db5 , data source `collection://424af207-66ae-8152-bcb1-000b322dc897`. IDs `TJL-STK-n`.
- **One row per setup that reached the trade list**: taken trades (Status Planned -> Open -> Closed) and setups not taken (Skipped = a rule said no; Missed = the rules said yes but it wasn't taken).
- Fields (all labeled for later analysis): Trade (title, "date ticker version"), Date, Ticker, Status, Version (A: TJL-report / B: TJL-bot), Grade (A+ / Normal), A+ boxes (multi-select of the 9 checklist items, tick only those met), Sector, Catalyst (headline), Catalyst type, SPY regime, Gap %, Premarket RVOL, ADR20 %, Extension vs 20d SMA %, 52w range position %, Premarket high, Trigger price, 5m confirm (VWAP + 8 EMA), Entry time, Entry window (10-11 / 11-14 / 14-15:30), Entry price, Stop price, Stop %, Risk $, Position $, Leverage, Margin $, Partial 1 price, Partial 2 price, Final exit price, Exit time, Exit reason (Stop / Breakeven / Trail / Time 3:51 / Overnight exit / Manual), Trail method (21-EMA 5m / Swing low 5m / Native trailing / None), Held overnight, Fees $, Funding $, P&L $ (net), **R multiple** (formula = P&L $ / Risk $), MFE R, MAE R, Rule followed, Mistakes (Chased / Early entry / Late exit / Moved stop / Ignored rule / Missed alert), Liquid order IDs, Notes.
- The Liquid paper history (`get_position_history`) is the source of truth for fills and fees; copy them into the row when the trade closes.

## Go / no-go criteria for the 2-month paper test (set by Claude, 2026-11-26)
Judge after **at least 2 months and at least 30 closed trades** (if fewer than 30, extend until there are 30). All numbers net of fees and funding, in R (P&L $ / Risk $).
- **Go** (consider small real-money trading at the same $ risk or lower) only if all hold:
  1. Expectancy >= **+0.20R per trade** over all closed trades.
  2. Profit factor >= **1.3** and total net P&L > $0.
  3. Max drawdown no worse than **-$3,000** (about -12% of the $25k sizing base, ~6-12R).
  4. **Rules followed on >= 90%** of trades (Rule followed ticked, no "Ignored rule"/"Moved stop").
  5. No single loss worse than **-1.3R** (stops and slippage under control).
- **Extend one more month** (once) if expectancy is between 0 and +0.20R or profit factor between 1.1 and 1.3.
- **No-go** (stop, back to research) if expectancy <= 0R, or profit factor < 1.1, or drawdown hits -$3,000 at any point (that also pauses the test immediately for a review).
- **Decisions inside the test:**
  - Version A vs B: keep the version with the higher expectancy; drop a version whose expectancy is below 0R after 15+ trades of its own.
  - A+ vs normal: if A+ trades don't beat normal trades in expectancy, drop the 2x size ($500) and risk $250 on everything.
  - Each A+ box and each field (entry window, SPY regime, catalyst type, overnight, 5m confirm) gets a split: expectancy with vs without. Any filter whose "with" group is not better after 30+ trades is a candidate to drop.
  - Skipped/Missed rows: if Missed setups would have done better than taken ones, look at execution (alerts, approvals, speed).

## Trade-frequency estimate (2026-11-26)
Liquid can't answer this historically (200 candles per call; daily candles run 00:00-24:00 UTC, so no 9:30 open or gap). Used Databento **EQUS.SUMMARY ohlcv-1d** (consolidated US daily bars, available from 2024-07-01, cost $0.07) for the 74 US-listed single stocks on Liquid (ETFs left out). Window with a valid 200d SMA: 2025-04-17 to 2026-11-25, 405 trading days. The ad-hoc script and data stayed in the session scratchpad (not in the repo).

Definitions (all known before the open): gap = open / prior close - 1; prior close > 200d SMA and > $3; ADR20 = mean of (high/low - 1) over the prior 20 days; $vol20 = mean of close x volume over the prior 20 days. "Trigger proxy" = the day's high later exceeds both the open and the prior day's high by 0.1% (a crude daily stand-in for the intraday breakout; it can't check the 10:00-3:30 window or the premarket high). Market cap isn't available historically, so $vol20 >= $5B stands in for the large-cap focus filter.

| Variant | Days with a setup | Setup days/week | Trades/week (cap 2/day) | 2025 / 2026 days with a setup |
|---|---|---|---|---|
| A: gap >= 3%, above 200d | 70% (66% with trigger proxy) | 3.5 | 6.0 | 69% / 71% |
| B: A + ADR20 >= 4% | 64% (60%) | 3.2 | 5.3 | 61% / 67% |
| **C: B + $vol20 >= $5B** (video 3 focus) | **24% (21%)** | **1.2** | **1.9** | **12% / 34%** |
| D: C with ADR20 >= 6% | 14% (13%) | 0.7 | 1.1 | 2% / 24% |
| E: C with gap >= 2% | 36% (30%) | 1.8 | 2.9 | 25% / 45% |

- **The full focus set (C) gives about 1 setup day a week, about 2 trades a week at the 2/day cap.** Most of the cut comes from the $5B dollar-volume filter.
- **Strongly regime- and sector-dependent:** C had setups on 12% of days in 2025 vs 34% in 2026; by month from 0 (2025-09) to 13 (2026-05). C's names are dominated by memory/semis: MU 51, SNDK 43, INTC 29, AMD 28, MRVL 20, LITE 13, AVGO 8.
- The looser sets (A/B) have a setup most days, so the 2/day cap binds; the question becomes picking the best 1-2, not finding any.
- Counts only, not results: nothing here says these setups make money.

## Gaps to fill (updated 2026-11-26: no backtests, forward paper trading, all filters kept in tiers)

Closed: historical data source and backtest (not doing them); trade frequency (estimated); filter level (core screens, focus grades); Trend Join version (run both, tagged); long only for now; sizing (1% normal, 2% A+); A+ checklist (drafted); paper test length (>= 2 months); trigger tool (Webull price alerts) and data source (Webull read-only); after-market analysis (Claude's draft defaults).

### 1. Rules to lock before paper trading
- ~~Trend Join version~~ Done: both run on paper, tagged; exact rules confirmed from the blogs (see "Confirmed Trend Join Long rules"). Remaining assumption: version A's 21-EMA trail on the 5m.
- Entry start: 10:00/10:05 (rules) vs 9:30 (best window in video 3).
- Video 5's confirmation: require a 5m close above VWAP and the 8 EMA on the breakout, or not.
- **Overnight rule:** which part carries (draft: A+ only, last third, while above the 21-EMA), its stop, Fridays/weekends, funding cost.
- **Short side:** exact trigger, stop and exit for the breakdown fade, parabolic-open short and first-red-day short (videos 1 and 5), or start long only on paper and add shorts later.
- **A+ definition:** a checkable list (which focus filters, what counts as a real catalyst, how "hot sector" is measured and its cutoff).
- ~~Sizing~~ Done: $250 normal / $500 A+ on a $25k sizing base, $2,500 margin cap, 2-10x leverage.

### 2. The after-market analysis (define exactly)
- SPY regime: an exact "sideways" rule (skip day) vs trend.
- Sector heat: which ETFs/groups on Liquid (SMH, IGV, XLE, XBI, TLT, member stocks), lookback, how many count as hot.
- Watchlist: size and ranking (top 1-2 trade, a few backups).
- Output and timing: where it goes (chat, Notion, email) and when (after the close, plus the morning gap update). Default: a manual message per day, like the RSI(2) check (no scheduled tasks).
- Combine with the RSI(2) daily check in one report, or keep separate.

### 3. Liquid checks (quick, read-only)
Done 2026-11-26 (see "Liquid checks for the paper test"). Remaining: confirm the real round-trip fee from the first paper fill; decide the paper capital split.
- Fees per trade, typical spread on the stock perps, funding for overnight holds.
- Order features: stop/TP attached at entry (one approval), partial take-profits, trailing stop (fixed distance only, or can it follow an EMA/swing low?).
- Liquid's VWAP and premarket high vs the exchange's on a few days.
- **Paper account capital:** the $10k paper account is shared with the RSI(2) test ($5k notional per trade). Decide the split, or reset/raise it.

### 4. Operations during the session
- Who watches the trigger from 10:00 to 3:30: user check-ins by message, a TradingView alert, or a script on the user's PC. Every Liquid order still needs the user's approval.
- ~~Risk limits~~ Done: -$500 daily loss limit, max 2 trades a day.
- ~~Trade log~~ Done: Notion "TJL Trades" database (see "Trade log").

### 5. Paper-test success criteria
- ~~Done~~: see "Go / no-go criteria" (2 months and 30+ trades). Previously open: what decides go / no-go (expectancy in R after fees, A+ vs other grades, drawdown).

## Next steps (suggested order)
1. ~~Read the presenter's blog rules~~ Done (see "Confirmed Trend Join Long rules"). Lock the rest of section 1.
2. Run the quick Liquid checks in section 3 (fees, order features, paper capital).
3. Define the after-market analysis in section 2 and the session operations in section 4.
4. Set the paper-test success criteria (section 5).
5. ~~Then build: after-close report, morning gap update, intraday alerts, trade log.~~ Done 2026-11-26 (see "Build"). Next: run the paper test from Mon 2026-11-30; still open: shorts.

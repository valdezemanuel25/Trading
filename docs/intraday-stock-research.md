# Intraday stock strategy: research notes (started 2026-11-26)

Status: **research only, nothing built.** Goal: add an intraday stock strategy next to the after-market (after-close) analysis.
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
- **Sizing:** base 1% of the account at risk per trade; **A+ setups risk 2%**. Sized from the stop distance.
- **A+ checklist: pending** another video from the user on how the presenter picks stocks.
- **Paper test length: at least 2 months** before judging.
- **After-market analysis definition: left to Claude** (draft defaults below, under "After-market analysis: draft defaults").
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
| 7 | `VDN4jp4Uf1k` (how the presenter builds the watchlist) | **Pending**: source for the A+ checklist; run `/watch` on the PC and paste the summary |

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

## After-market analysis: draft defaults (chosen by Claude, 2026-11-26; change freely)
Run once a day after the close, in the same message as the RSI(2) check (one "daily check" message from the user; no scheduled tasks).
1. **Regime (SPY = `xyz:SP500`, weekday daily closes):** *trend* if the close is at least 1% from its 20-day SMA and the 20-day SMA's 5-day slope has the same sign; otherwise *sideways* -> no new Trend Join trades tomorrow (video 3: sideways days lost $77k). Also report the 200-day state; longs only below it with an A+ grade.
2. **Sector heat:** rank groups by 5-day and 20-day return (average rank): semis/AI (SMH; NVDA, AMD, AVGO, MU, MRVL, SNDK, WDC, LRCX, AMAT, ARM, TSM), software (IGV; MSFT, ORCL, NOW, CRWD, PANW, NET, PLTR), internet (GOOGL, META, AMZN, NFLX), crypto-linked (COIN, MSTR, HOOD, IREN, CIFR), energy (XLE, CVX, VST, GEV), health (XBI, LLY, MRNA, HIMS). Top 2 groups = hot.
3. **Watchlist screen** (Liquid's US-listed stocks, weekday daily candles): prior close > $3 and above its own 200-day SMA (computed from weekday candles); ADR20; distance from the 20-day SMA; position in the available high/low range. Rank: hot sector first, then ADR20, then nearness to highs; mark anything > 10% above its 20-day SMA as extended.
4. **Catalysts:** `upcoming_earnings` (week) and `get_news` headlines for the names on the list.
5. **Output:** top 5 names (trade at most 2), each with prior-day high/low, the 200d/20d levels, ADR, sector, catalyst, planned grade (A+ or normal) and risk (2% or 1%).
6. **Morning update (about 9:00-9:30 ET):** which watchlist names gap >= 3% vs the 4:00 PM close (Liquid price), their premarket high, Liquid volume vs normal; confirm or drop.

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

Closed: historical data source and backtest (not doing them); trade frequency (estimated); filter level (core screens, focus grades).

### 1. Rules to lock before paper trading
- **Trend Join version:** video 4 (stop = lower of PMH - 1% or LOD; thirds at +1R/+2R; 21-EMA trail) or video 6 (stop 1% under LOD; partial at +0.75R, breakeven at +1R, trail under 5m swing lows; RVOL >= 2.0). Or run both on paper and tag each trade. Read the presenter's blog rules (linked from video 4) first.
- 21-EMA trail timeframe (probably 5m) and the partial size in video 6's version.
- Entry start: 10:00/10:05 (rules) vs 9:30 (best window in video 3).
- Video 5's confirmation: require a 5m close above VWAP and the 8 EMA on the breakout, or not.
- **Overnight rule:** which part carries (draft: A+ only, last third, while above the 21-EMA), its stop, Fridays/weekends, funding cost.
- **Short side:** exact trigger, stop and exit for the breakdown fade, parabolic-open short and first-red-day short (videos 1 and 5), or start long only on paper and add shorts later.
- **A+ definition:** a checkable list (which focus filters, what counts as a real catalyst, how "hot sector" is measured and its cutoff).
- **Sizing:** base 1% risk per trade (video 6), A+ 2-3x, vs the 10% per-position cap; sized from the stop distance.

### 2. The after-market analysis (define exactly)
- SPY regime: an exact "sideways" rule (skip day) vs trend.
- Sector heat: which ETFs/groups on Liquid (SMH, IGV, XLE, XBI, TLT, member stocks), lookback, how many count as hot.
- Watchlist: size and ranking (top 1-2 trade, a few backups).
- Output and timing: where it goes (chat, Notion, email) and when (after the close, plus the morning gap update). Default: a manual message per day, like the RSI(2) check (no scheduled tasks).
- Combine with the RSI(2) daily check in one report, or keep separate.

### 3. Liquid checks (quick, read-only)
- Fees per trade, typical spread on the stock perps, funding for overnight holds.
- Order features: stop/TP attached at entry (one approval), partial take-profits, trailing stop (fixed distance only, or can it follow an EMA/swing low?).
- Liquid's VWAP and premarket high vs the exchange's on a few days.
- **Paper account capital:** the $10k paper account is shared with the RSI(2) test ($5k notional per trade). Decide the split, or reset/raise it.

### 4. Operations during the session
- Who watches the trigger from 10:00 to 3:30: user check-ins by message, a TradingView alert, or a script on the user's PC. Every Liquid order still needs the user's approval.
- Risk limits: max daily loss, max open positions (2), stop for the day after N losses.
- Trade log: where each trade is logged (Liquid history + Notion?), with setup, grade, size, R, time window, regime, holding period, so the after-session audit (video 3 style) can run.

### 5. Paper-test success criteria
- How long (weeks / number of trades) before judging, and what decides go / no-go (expectancy in R after fees, A+ vs other grades, drawdown).

## Next steps (suggested order)
1. Read the presenter's blog rules and lock section 1 (rules).
2. Run the quick Liquid checks in section 3 (fees, order features, paper capital).
3. Define the after-market analysis in section 2 and the session operations in section 4.
4. Set the paper-test success criteria (section 5).
5. Then build: after-close report, morning gap update, intraday alerts, trade log.

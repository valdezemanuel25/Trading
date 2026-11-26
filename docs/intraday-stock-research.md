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

## Gaps to fill (reviewed 2026-11-26, after all six videos)

### 1. Evidence: does it work at all?
- No independent test. All numbers are the presenter's, and their own paper bot is slightly negative. We need our own test with costs on a period the rules weren't tuned on.
- Historical data: Liquid gives 200 candles per call, too little for a months-long 5m backtest. Needs an intraday stock-data source (Databento equities, Polygon or Alpaca).
- Trade frequency: with ~120 Liquid stocks and a 3%+ gap rule, many days may have no candidate. Estimate it from Liquid daily candles first.

### 2. Rule decisions still open
- Which Trend Join version (relative volume 1.5 vs 2.0, stop, exits). Read the presenter's blog rules.
- The 21-EMA trail's timeframe and the bot version's partial size.
- Entry start: 10:00 (rules) vs 9:30-10:00 (best window in video 3's data).
- Overnight: exact rule (draft: A+ only, last third, while above the 21-EMA), overnight stop, weekends.
- Short side: breakdown fade, parabolic-open short and first red day have no exact trigger/stop/exit.
- A+ grading: a checkable definition of a real catalyst and of a "hot sector" (measure and cutoff).
- Sizing: 2-3x A+ vs the 10% per-position cap.

### 3. Defining the after-market analysis
- Regime rule: an exact definition of "SPY sideways".
- Sector heat: which ETFs/groups, lookback, how many count as hot.
- Watchlist size and ranking.
- Output and timing: where it goes (chat, Notion, email) and when. The user doesn't want scheduled tasks from Claude sessions, so default is a manual daily message (like the RSI(2) check).
- Relation to the RSI(2) daily check: separate or one combined report.

### 4. Liquid-specific unknowns
- Do Liquid's VWAP and premarket high behave like the exchange's? Compare on a few days of candles.
- Costs: trading fees, spreads on the stock perps, funding for overnight holds.
- Execution: every order needs the user's approval. Can stop/TP attach at entry? Partial take-profits?
- Trailing stops: can they follow an EMA or swing lows, or only a fixed distance?

### 5. Operations and risk
- Intraday alerts: Liquid has no alerts or scheduler. Options: user check-ins by message, a TradingView alert, or a script on the user's PC (like video 6's bot).
- Portfolio limits: max daily loss, positions at once (1-2 names per video 3), stop-trading rule after losses.
- Trade log and audit format (video 3's dashboard), to measure whether filters and grades help.

## Next steps (suggested order)
1. Estimate trade frequency from Liquid daily candles (quick, no new data). Cap is 2 trades/day (decided); the open question is how many days have any qualifying setup.
2. Read the presenter's blog rules (linked from video 4) and reconcile with video 6's `rules.json`; then lock the rule decisions above.
3. Check Liquid's costs and order features (stop/TP at entry, partials, trailing stops).
4. Choose a historical stock-data source for a real backtest.
5. Then design the after-close report, the morning update and the intraday alerts.

# Order agent for the Liquid paper rules (PROPOSED, not set up; NOT recommended for now)

**2026-11-25, after the 1-minute test (`docs/backtest-log.md`, "realistic intraday tests"):**
- No intraday variant beats the close-based rules by more than noise, so the agent isn't recommended.
- This design is kept for a future rule that needs intraday orders.

Status: design only, written 2026-11-25. Nothing here runs until the user approves it. It depends on Part A
(`docs/backtest-log.md`, "intraday entries"): today only the trend-reclaim (TR) intraday entry passed, and only
in principle, because Liquid has no buy-stop orders.

## Who does what

| | Order agent (new session) | Review session (this session, "RSI2 daily check") |
|---|---|---|
| Wakes | Hourly 9:45-15:45 ET Mon-Fri, plus 00:35 UTC Tue-Sat | 00:20 UTC Tue-Sat (unchanged) |
| Reads | `data/rsi2/history`, `data/rsi2/open`, `data/rsi2/signals`, `data/rsi2/orders`, Liquid portfolio and open orders | Same, plus the day's order log |
| Decides | Today's trigger prices (`liquid/intraday_levels.py`), whether a live price crossed one, which close-based signals from the review session need an order | Saves the closes and positioning, computes the close-based signals (`liquid/rsi2_daily.py`) and writes them to `data/rsi2/signals/<date>` |
| Orders | Proposes every new, changed or cancelled order as a preview in its own session. **Never executes without your explicit approval there.** | Places no orders any more. It reviews the agent's day |
| Writes | One event per document in `data/rsi2/orders/<id>`, mirrored in `liquid/orders/<YYYY-MM-DD>.jsonl`; `data/rsi2/open/<KEY>` after a fill or close | `data/rsi2/signals/<date>`; the "today's orders" review on the dashboard |

Why two sessions: a Liquid order can only be approved in the session that previews it. The review session stays
read-only for orders, so the two can never both propose the same order.

## What you do to create it

1. Check that Liquid is connected to your account at https://claude.ai/customize/connectors (it is today). A
   session only reads connectors when it starts.
2. At https://claude.ai/code start a **new session**:
   - repository `valdezemanuel25/Trading`, branch `claude/focused-hypatia-pwaszc`;
   - the same environment as this session.
3. Paste the setup message below as its first message. It checks its tools and paper mode, then creates its own
   two scheduled tasks. Created from inside that session, they fire into that same session, which keeps the
   Liquid connector. A fresh session per firing would have no Liquid tools.
4. Tell this session it's running. I then change this session's 00:20 UTC check to:
   - stop proposing orders;
   - write `data/rsi2/signals/<date>`;
   - add the review and the dashboard's "today's orders" section.
5. Approve orders only in the agent's session. Its hourly wakes ask you there; the Claude app notifies you when
   a scheduled run finishes.

## Schedule (created by the agent in its own session)

| Scheduled task | Cron | When |
|---|---|---|
| "RSI2 order agent: hourly" | `CRON_TZ=America/New_York 45 9-15 * * 1-5` | 9:45, 10:45 ... 15:45 ET, weekdays (7 wakes). The 15:45 wake is also the pre-close check |
| "RSI2 order agent: after close" | `35 0 * * 2-6` (UTC) | 00:35 UTC Tue-Sat, 15 minutes after the review session has saved the closes and signals |

## Setup message (paste into the new session)

```
You are the order agent for my Liquid paper-trading rules. Read docs/live-setup.md and liquid/order_agent.md
(branch claude/focused-hypatia-pwaszc) first. Then:
1. Check that the Liquid tools work: paper_trading_status must say ENABLED; get_portfolio; view_open_orders.
   If Liquid tools are missing, stop and tell me.
2. Check ArtifactData can read https://claude.ai/artifact/22FJo7qvavG7uHKQSckF7L (collection data/rsi2/history).
3. Create two scheduled tasks with create_trigger, default mode (fire into THIS session), initiation human_request:
   - name "RSI2 order agent: hourly", cron "CRON_TZ=America/New_York 45 9-15 * * 1-5", prompt: the HOURLY PROMPT
     section of liquid/order_agent.md, verbatim;
   - name "RSI2 order agent: after close", cron "35 0 * * 2-6", prompt: the AFTER-CLOSE PROMPT section, verbatim.
4. Reply with the two task ids and the session's state (paper mode, positions, open orders). Place no order.
```

## HOURLY PROMPT

```
RSI2 order agent, hourly wake. Rules: docs/live-setup.md (branch claude/focused-hypatia-pwaszc, git pull first).
You NEVER place, change or cancel a Liquid order without my explicit approval of the exact previewed terms in
this session. A preview older than 15 minutes, or with changed terms, needs a new preview and a new approval.
Dashboard url: https://claude.ai/artifact/22FJo7qvavG7uHKQSckF7L. W = <scratchpad>/agent/<UTC timestamp>.

1. Liquid paper_trading_status (must be ENABLED, else warn and stop), get_portfolio, view_open_orders.
2. ArtifactData list with out_dir W/store: data/rsi2/history, data/rsi2/open, data/rsi2/orders (today's events).
3. Live price per market (SP500 xyz:SP500, NQ100 xyz:XYZ100, NVDA xyz:NVDA, GOOGL xyz:GOOGL, CL xyz:CL): the
   currentPrice from get_technical_indicators (interval 1h, indicators ["sma"]).
4. python3 liquid/intraday_levels.py --history-dir W/store/data/rsi2/history --open-dir W/store/data/rsi2/open
   --live SP500=<p> NQ100=<p> NVDA=<p> GOOGL=<p> CL=<p>
5. Trend reclaim (only rule with an intraday entry): for each market with live_tr_cross true, no position, no
   order or open proposal for it today, and a free slot (at most 2 positions, one per market; if two cross at once,
   order CL, GOOGL, NQ100, NVDA): log a "signal" event, then prepare a suggest_trade preview: long, $5,000
   notional, 1x, market, maxSlippageBps 30, reasoning "TR intraday: price <p> above 200-day SMA <trigger>". Log
   "proposed" and ask me to approve. On approval: execute_order with one idempotency key, log "approved", then
   "placed"/"filled"/"rejected" from the result (Liquid order id, fill price, slippage vs the trigger). On a fill,
   write data/rsi2/open/<KEY> = {market, symbol, strategy "TR", entry_date <today's UTC date>, entry_px, notional}
   and liquid/open/<KEY>.json.
6. 15:45 ET wake only: report each market's live_rsi2_setup / live_rsi2_exit / live_tr_exit as INFORMATION (the
   pre-close rule is not adopted; do not propose these unless docs/live-setup.md says it is).
7. Resting orders: any open Liquid order that no rule calls for (e.g. an unfilled limit from an earlier day) ->
   log "signal", then ask me whether to cancel it (name it exactly); cancel only after I say so; log "cancelled".
8. Log every event as its own document data/rsi2/orders/<YYYYMMDDTHHMMSSZ>_<KEY>_<event> (ArtifactData set) and
   append the same JSON line to liquid/orders/<YYYY-MM-DD>.jsonl; commit "orders <date>" and push. Fields: time (UTC
   ISO), market, symbol, rule (TR|RSI2), event (signal|proposed|approved|placed|filled|cancelled|rejected|expired),
   side, type, trigger_price, limit_price, size_usd, fill_price, slippage_pct, liquid_order_id, idempotency_key, note.
9. If nothing crossed and nothing is pending, reply with one line: "<time ET>: no triggers" and the closest market
   (live price vs trigger, %). A proposal I didn't answer before the next wake: log "expired" and re-check.
```

## AFTER-CLOSE PROMPT

```
RSI2 order agent, after-close wake (00:35 UTC). Same approval rules as the hourly wake.
1. Liquid paper_trading_status, get_portfolio, view_open_orders.
2. ArtifactData get data/rsi2/signals/<date of the last completed candle> (written by the review session's 00:20
   check). If it is missing, say so and stop (do not compute signals yourself).
3. For each BUY todo (RSI2, or TR not already entered intraday today) and each SELL todo: log "signal", prepare the
   preview (BUY: suggest_trade long $5,000 1x market maxSlippageBps 30; SELL: close_position for the whole
   position), log "proposed", ask me to approve, execute only after approval, and log the outcome as in the hourly
   wake (events, data/rsi2/open/<KEY> write or delete, liquid/open, liquid/orders, commit and push).
4. One-line summary: proposals made, approved, filled; positions and free slots now.
```

## The review session's changes (after approval)

- `liquid/rsi2_daily.py` also writes `W/signals.json`. The 00:20 check stores it as `data/rsi2/signals/<date>`
  and stops preparing orders itself.
- New review step, reading `data/rsi2/orders` for the previous UTC day:
  - every fill vs the rule (was the trigger really crossed; was a slot free; one per market);
  - slippage = fill / trigger - 1 (and vs the 00:00 UTC close for close-based orders);
  - missed signals: a signal with no approved order, and why (expired, rejected, no slot);
  - wrong orders: any order with no matching signal, and any resting order left over.
  It adds one line per finding to the report.
- Dashboard: a "Today's orders" section, from `data/rsi2/orders` for the last UTC day. Columns: time, market,
  rule, event, side, trigger, fill, slippage, Liquid order id. It shows a review line per day, and is empty until
  the agent logs something.
- The store returns at most 1,000 documents per collection (oldest first by id). The review session moves order
  events older than 30 days to `liquid/orders/` only and deletes them from the store.

## Known limits

- **No buy-stop on Liquid.** The TR intraday entry is "agent sees price above the level at an hourly wake, you
  approve, a market order fills". It fills after the level, sometimes much later, and not at all while you're away.
  The backtest assumed a fill at the level; the realistic version needs 1-minute data to test (about $19).
- **Every order needs you.** A scheduled wake can only propose; nothing fills until you answer in the agent's session.
- **Resting paper orders are untested.** A `gtc` limit's behaviour in paper mode needs one small approved test.

# Plan: test real CVD (Databento trades) on the Journal Triggers strategy

**Status (2026-10-29): done.** Results are in `docs/backtest-log.md`, section "real CVD from Databento trades". The trades data is in `data/trades_1m/`.

**Context for a new session:** read `docs/backtest-log.md` first. The Python backtester in `backtest/` copies the ToS strategy rule for rule and is validated on ES 1-minute data from 2020-2026 (`data/`). As automated rules, the strategy is about breakeven before costs. The best variant (10:30-11:00 ET, T1 capped at 10, breakeven at +4) is about breakeven after costs. CVD **estimated from candles** added nothing.

The open question is whether **real** CVD helps: buyer vs seller aggression, as on Bookmap and in the Notion journal.

## Setup (done by the user, then a new session)
1. In the environment settings, allow network access to `hist.databento.com`.
2. Add the Databento API key as a network secret or environment variable named `DATABENTO_API_KEY`. Never put it in chat or the repo.
3. Start a new session and ask it to run this plan.

## Steps
1. `pip install databento zstandard`
2. Check the cost first:
   `python3 backtest/fetch_trades.py --start 2026-04-01 --end 2026-10-29 --budget 100 --dry-run`
   The user has about $110 in Databento credits. Stay under $100, and shorten the range if needed.
3. Download:
   `python3 backtest/fetch_trades.py --start 2026-04-01 --end 2026-10-29 --budget 100`
   This writes `data/trades_1m/es_trades_1m_YYYY-MM.csv.zst` with per-minute buy/sell volume per contract. Commit those files; they are small.
4. Add `delta_source = "real"` to `backtest/strategy.py`:
   - per 5m bar, delta = sum of (buy_vol - sell_vol) for the front-month contract used by `data.load_1m()`;
   - only for dates covered by the trades files.
5. Compare on 2026-04 to 2026-10, for both the baseline and the best variant (E in the log):
   - CVD source `clv5` vs `real`;
   - with and without `use_cvd_div` (real CVD divergence);
   - new real-order-flow confirmations from the journal:
     - **CVD flip:** CVD change over the last 3 bars changes sign on the trigger candle.
     - **Absorption:** large opposite delta at the level with little price movement (high volume, small range).
6. Split the 7 months into the first 4 (tune) and the last 3 (check). Only keep a rule that improves both.
7. Log the results in `docs/backtest-log.md`. If something holds up, it becomes a **Bookmap checklist rule** (ToS can't compute real CVD) and/or a ToS alert filter.

## Notes
- Databento trade `side`: `B` = buy aggressor (hit the ask), `A` = sell aggressor (hit the bid).
- About 7 months of trades is about 150-200 strategy signals: enough to see a large effect, not a small one.

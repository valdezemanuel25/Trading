#!/usr/bin/env python3
"""Intraday entry versions of the live Liquid rules (research only, 2026-11-25).

Engine, data, costs and the 2-slot / one-position-per-market portfolio are those of research/strategies2.py
(total-return daily series from Databento ohlcv-1d, 00:00 UTC days, $5,000 per trade, 0.10% round trip).

a. Trend reclaim (CL, GOOGL, NQ, NVDA). Live: buy the first CLOSE back above the 200-day SMA.
   Intraday: while the last close is at or below the SMA, rest a buy-stop at yesterday's 200-day SMA; filled if the
   day's high reaches it, at the stop or the open if it gaps above. Exits unchanged (a close below the SMA, checked
   from the entry day's own close, or 20 trading days). A "false breakout" = filled, then closed back below the SMA
   the same day (sold at that close).
b. RSI(2) (all five). Live: buy at the close when RSI(2) < 10 and the close is above the 200-day SMA.
   Intraday: rest a limit buy at P, the highest price at which today's close would give RSI(2) < 10, only if P is
   above yesterday's 200-day SMA; filled if the day's low reaches P, at P or the open if it gaps below. Exit
   unchanged (first close above the 5-day SMA, from the entry day's own close).
c. Pre-close decision (15:45 ET) for ES (the only market with 1-minute data in the repo): decide and fill at the
   15:45 ET price instead of the 00:00 UTC close, for entries and exits.

Daily bars can't say whether the low came before or after anything else in the day; every exit here is at a close,
so the order of the day's high and low doesn't change a result.

  python3 research/intraday_entries.py
"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "backtest"))
import strategies2 as s2  # noqa: E402

RSI2_M = ["ES", "NQ", "NVDA", "GOOGL", "CL"]
TR_M = ["CL", "GOOGL", "NQ", "NVDA"]
TR_MAX = 20


def wilder(c):
    up, dn = np.zeros(len(c)), np.zeros(len(c))
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        up[i] = 0.5 * up[i - 1] + 0.5 * max(d, 0)
        dn[i] = 0.5 * dn[i - 1] + 0.5 * max(-d, 0)
    return up, dn


def rsi2_limit_price(c_prev, up_prev, dn_prev):
    """Highest close X that gives RSI(2) < 10 (Wilder, alpha 0.5)."""
    if dn_prev / 9 - up_prev > 0:          # even an up close can still give RSI < 10
        return c_prev + (dn_prev / 9 - up_prev)
    return c_prev - (9 * up_prev - dn_prev)


def tr_trade(m, s, i, entry_px, strat, j0):
    c, sma = s["close"].to_numpy(), s["sma200"].to_numpy()
    j = j0
    while j < len(s) and c[j] >= sma[j] and not (j - i >= TR_MAX):
        j += 1
    j = min(j, len(s) - 1)
    return dict(strat=strat, market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                ret=c[j] / entry_px - 1, same_day=(j == i), alt=[s.index[i]])


def tr_close(m, s):
    c, sma = s["close"].to_numpy(), s["sma200"].to_numpy()
    out, i = [], 201
    while i < len(s):
        if c[i] > sma[i] and c[i - 1] <= sma[i - 1]:
            t = tr_trade(m, s, i, c[i], "TR", i + 1)
            out.append(t)
            i = s.index.get_loc(t["exit_date"]) + 1
        else:
            i += 1
    return out


def tr_stop(m, s):
    c, h, o, sma = (s[k].to_numpy() for k in ("close", "high", "open", "sma200"))
    out, i = [], 201
    while i < len(s):
        lvl = sma[i - 1]
        if c[i - 1] <= sma[i - 1] and np.isfinite(lvl) and h[i] >= lvl:
            px = max(lvl, o[i])
            t = tr_trade(m, s, i, px, "TR", i)          # the entry day's own close can already exit
            t["false_breakout"] = bool(c[i] < sma[i])
            t["close_entry_same_day"] = bool(c[i] > sma[i])
            out.append(t)
            i = s.index.get_loc(t["exit_date"]) + 1
        else:
            i += 1
    return out


def rsi2_close(m, s):
    return s2.rsi2_rule(m, s)


def rsi2_limit(m, s):
    c, lo, o, sma, sma5 = (s[k].to_numpy() for k in ("close", "low", "open", "sma200", "sma5"))
    up, dn = wilder(c)
    out, i = [], 201
    while i < len(s):
        p = rsi2_limit_price(c[i - 1], up[i - 1], dn[i - 1])
        if p > sma[i - 1] and lo[i] <= p:
            px = min(p, o[i])
            j = i
            while j < len(s) and not c[j] > sma5[j]:
                j += 1
            j = min(j, len(s) - 1)
            r = s2.rsi(s["close"]).to_numpy()
            out.append(dict(strat="RSI2", market=m, entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                            ret=c[j] / px - 1, same_day=(j == i), close_rule_too=bool(r[i] < 10 and c[i] > sma[i]),
                            alt=[s.index[i]]))
            i = j + 1
        else:
            i += 1
    return out


def one_per_market(trades, slots=2):
    t = trades.copy()
    t["_p"] = (t["strat"] != "RSI2").astype(int)
    t = t.sort_values(["entry_date", "_p", "market"]).reset_index(drop=True)
    open_, out = [], []
    for r in t.to_dict("records"):
        open_ = [x for x in open_ if x["exit_date"] > r["entry_date"]]
        if len(open_) >= slots or any(x["market"] == r["market"] for x in open_):
            continue
        open_.append(r)
        out.append(r)
    return pd.DataFrame(out)


def show(label, t):
    print(f"  {label}")
    for p in s2.PERIODS:
        x = s2.per(t, p)
        print(f"    {p:13s} {s2.fmt(s2.stats(x, s2.years(p)))}")


def early_es(s):
    """ES 15:45 ET price on the total-return scale, per UTC day (ratio to the same contract's 00:00 UTC close)."""
    from data import load_1m
    m1 = load_1m()
    utc = m1.index.tz_convert("UTC")
    df = pd.DataFrame(dict(close=m1["close"].to_numpy(), symbol=m1["symbol"].to_numpy(),
                           utcday=utc.tz_localize(None).normalize(),
                           et=(m1.index.hour * 60 + m1.index.minute).to_numpy()), index=m1.index)
    last = df.groupby("utcday").last()                       # last front-month print of the UTC day
    e = df[df.et < 15 * 60 + 45].groupby("utcday").last()    # last print before 15:45 ET
    both = last.join(e, rsuffix="_e", how="inner")
    both = both[both.symbol == both.symbol_e]
    ratio = both.close_e / both.close
    return (s["close"] * ratio.reindex(s.index)).rename("early")


def es_pre_close(s, e):
    """RSI(2) on ES deciding and filling at the 15:45 ET price (today's close replaced by it)."""
    c, ev, sma200 = s["close"].to_numpy(), e.to_numpy(), s["sma200"].to_numpy()
    up, dn = wilder(c)
    out, i, n = [], 201, len(s)

    def rsi_e(k):
        d = ev[k] - c[k - 1]
        u, w = 0.5 * up[k - 1] + 0.5 * max(d, 0), 0.5 * dn[k - 1] + 0.5 * max(-d, 0)
        return 100.0 if w == 0 else 100 - 100 / (1 + u / w)

    def sma_e(k, L):
        return (c[k - L + 1:k].sum() + ev[k]) / L

    while i < n:
        if np.isnan(ev[i]):
            i += 1
            continue
        if rsi_e(i) < 10 and ev[i] > sma_e(i, 200):
            j = i + 1
            while j < n and not (not np.isnan(ev[j]) and ev[j] > sma_e(j, 5)):
                j += 1
            j = min(j, n - 1)
            px_out = ev[j] if not np.isnan(ev[j]) else c[j]
            out.append(dict(strat="RSI2", market="ES", entry_date=s.index[i], exit_date=s.index[j], days=j - i,
                            ret=px_out / ev[i] - 1, alt=[s.index[i]]))
            i = j + 1
        else:
            i += 1
    return out


def main():
    pd.set_option("display.width", 220)
    s2.SER = s2.load_all(s2.LIVE)
    S = s2.SER

    print("=" * 100 + "\na. TREND RECLAIM: close entry vs buy-stop at yesterday's 200-day SMA")
    trc = s2.frame([x for m in TR_M for x in tr_close(m, S[m])])
    trs = s2.frame([x for m in TR_M for x in tr_stop(m, S[m])])
    for m in TR_M + [None]:
        a = trc if m is None else trc[trc.market == m]
        b = trs if m is None else trs[trs.market == m]
        print(f"\n {m or 'ALL four'}")
        show("close entry (live)", a)
        show("buy-stop entry", b)
    fb = trs[trs.false_breakout]
    print(f"\n  buy-stop fills: {len(trs)}, false breakouts (closed back below the same day): {len(fb)} "
          f"({100 * len(fb) / len(trs):.0f}%), avg ${fb.usd.mean():+.1f}, total ${fb.usd.sum():+,.0f}; "
          f"fills where the close-based rule also entered that day: {int(trs.close_entry_same_day.sum())}")
    for p in s2.PERIODS:
        x = s2.per(fb, p)
        print(f"    false breakouts {p:13s} {len(x)} trades, ${x.usd.sum():+,.0f}")

    print("\n" + "=" * 100 + "\nb. RSI(2): close entry vs resting limit at the RSI(2)=10 price")
    rc = s2.frame([x for m in RSI2_M for x in rsi2_close(m, S[m])])
    rl = s2.frame([x for m in RSI2_M for x in rsi2_limit(m, S[m])])
    for m in RSI2_M + [None]:
        a = rc if m is None else rc[rc.market == m]
        b = rl if m is None else rl[rl.market == m]
        print(f"\n {m or 'ALL five'}")
        show("close entry (live)", a)
        show("limit entry", b)
    print(f"\n  limit fills: {len(rl)}; of which the close also gave RSI(2) < 10 above the SMA: "
          f"{int(rl.close_rule_too.sum())}; avg ${rl[rl.close_rule_too].usd.mean():+.1f} vs "
          f"${rl[~rl.close_rule_too].usd.mean():+.1f} for fills the close rule would not have taken; "
          f"sold the same day: {int(rl.same_day.sum())}")

    print("\n" + "=" * 100 + "\nPORTFOLIO: 2 slots x $5,000, one position per market, RSI(2) first on ties")
    combos = {"live (RSI2 close + TR close)": (rc, trc), "RSI2 close + TR buy-stop": (rc, trs),
              "RSI2 limit + TR close": (rl, trc), "RSI2 limit + TR buy-stop": (rl, trs)}
    for lab, (a, b) in combos.items():
        show(lab, one_per_market(pd.concat([a, b], ignore_index=True)))

    print("\n" + "=" * 100 + "\nc. PRE-CLOSE DECISION at 15:45 ET, ES RSI(2) (1-minute data only for ES)")
    e = early_es(S["ES"])
    pc = s2.frame(es_pre_close(S["ES"], e))
    base = rc[rc.market == "ES"]
    common = len(set(base.entry_date) & set(pc.entry_date))
    print(f"  entry days in common with the 00:00 UTC rule: {common} of {len(base)} (00:00 UTC) / {len(pc)} (15:45 ET)")
    show("ES RSI(2), decide + fill at the 00:00 UTC close (live)", base)
    show("ES RSI(2), decide + fill at 15:45 ET", pc)
    show("PORTFOLIO with ES at 15:45 ET (others unchanged)",
         one_per_market(pd.concat([rc[rc.market != "ES"], pc, trc], ignore_index=True)))


if __name__ == "__main__":
    main()

"""After-close check: SPY regime, sector heat, screen of Liquid's US stocks, top-5 watchlist.

Rules (docs/intraday-stock-research.md, "Watchlist rules and A+ checklist" and
"After-market analysis: draft defaults"). The code only applies pass/fail rules and ranks; catalyst
quality is judged by Claude in the report text.
"""
import datetime as dt
import statistics

from . import config as C
from . import sessions
from .indicators import adr, sma, swing_highs, swing_lows
from .webull import fnum


def _upto(bars, asof):
    return [b for b in bars if b["date"] <= asof] if asof else bars


def regime(spy):
    closes = [b["close"] for b in spy]
    s20 = sma(closes, 20)
    s20_prev = sma(closes[:-C.REGIME_SLOPE_DAYS], 20)
    s200 = sma(closes, 200)
    close = closes[-1]
    dist = close / s20 - 1
    slope = s20 - s20_prev
    if abs(dist) >= C.REGIME_MIN_DIST and dist > 0 and slope > 0:
        state = "Trend up"
    elif abs(dist) >= C.REGIME_MIN_DIST and dist < 0 and slope < 0:
        state = "Trend down"
    else:
        state = "Sideways"
    return {"date": spy[-1]["date"].isoformat(), "close": close, "sma20": round(s20, 2),
            "dist20_pct": round(dist * 100, 2), "sma20_slope5": round(slope, 2),
            "sma200": round(s200, 2) if s200 else None, "above200": bool(s200 and close > s200),
            "state": state}


def _ret(bars, n):
    if len(bars) <= n:
        return None
    return bars[-1]["close"] / bars[-1 - n]["close"] - 1


def sector_heat(bars, etf_bars):
    rows = []
    for g, members in C.GROUPS.items():
        r5 = [x for x in (_ret(bars[t], 5) for t in members if t in bars) if x is not None]
        r20 = [x for x in (_ret(bars[t], 20) for t in members if t in bars) if x is not None]
        etf = C.GROUP_ETF.get(g)
        rows.append({"group": g, "n": len(r5), "ret5": statistics.median(r5) if r5 else None,
                     "ret20": statistics.median(r20) if r20 else None, "etf": etf,
                     "etf_ret5": _ret(etf_bars[etf], 5) if etf in etf_bars else None,
                     "etf_ret20": _ret(etf_bars[etf], 20) if etf in etf_bars else None})
    ok = [r for r in rows if r["n"] >= C.MIN_GROUP_SIZE and r["ret5"] is not None]
    for key in ("ret5", "ret20"):
        for i, r in enumerate(sorted(ok, key=lambda r: -r[key])):
            r[f"rank_{key}"] = i + 1
    for r in ok:
        r["score"] = (r["rank_ret5"] + r["rank_ret20"]) / 2
    ok.sort(key=lambda r: (r["score"], -r["ret5"]))
    for i, r in enumerate(ok):
        r["rank"] = i + 1
        r["hot"] = i < C.HOT_GROUPS
    small = [r for r in rows if r not in ok]
    for r in small:
        r["rank"], r["hot"] = None, False
    return ok + small


def daily_levels(bars):
    """Prior-day levels for the next session plus nearby swing levels (last ~60 bars)."""
    last = bars[-1]
    recent = bars[-60:]
    close = last["close"]
    res = sorted({round(recent[i]["high"], 2) for i in swing_highs(recent) if recent[i]["high"] > close})
    sup = sorted({round(recent[i]["low"], 2) for i in swing_lows(recent) if recent[i]["low"] < close},
                 reverse=True)
    return {"prior_close": close, "pdh": last["high"], "pdl": last["low"],
            "high20": max(b["high"] for b in bars[-20:]), "resistance": res[:3], "support": sup[:3]}


def metrics(ticker, bars, snap, asof=None):
    closes = [b["close"] for b in bars]
    last = bars[-1]
    close = last["close"]
    s20, s200 = sma(closes, 20), sma(closes, 200)
    a20 = adr(bars, 20)
    vol20 = sum(b["volume"] for b in bars[-20:]) / min(20, len(bars))
    dvol20 = sum(b["volume"] * b["close"] for b in bars[-20:]) / min(20, len(bars))
    vol5 = sum(b["volume"] for b in bars[-5:]) / min(5, len(bars))
    yr = bars[-252:]
    hi52, lo52 = max(b["high"] for b in yr), min(b["low"] for b in yr)
    if snap and not asof:   # Webull's 52-week values cover the full year even for short histories
        hi52 = max(hi52, fnum(snap.get("fifty_two_wk_high"), hi52))
        lo52 = min(lo52, fnum(snap.get("fifty_two_wk_low"), lo52))
    mcap = fnum(snap.get("market_value"), 0) if snap else 0
    pos52 = (close - lo52) / (hi52 - lo52) if hi52 > lo52 else None
    from_high = close / hi52 - 1
    prior20_high = max(b["high"] for b in bars[-21:-1]) if len(bars) > 21 else None
    lv = daily_levels(bars)
    m = {"ticker": ticker, "liquid": C.liquid_symbol(ticker), "group": C.TICKER_GROUP.get(ticker, "?"),
         "date": last["date"].isoformat(), "close": close, "sma20": s20, "sma200": s200,
         "adr20": a20, "avg_vol20": vol20, "dollar_vol20": dvol20, "mcap": mcap,
         "ext20": close / s20 - 1 if s20 else None, "hi52": hi52, "lo52": lo52, "pos52": pos52,
         "from_high": from_high, "bars": len(bars), "levels": lv,
         "breakout_ready": bool(prior20_high and close >= prior20_high * 0.97 and vol5 > vol20),
         "vol5_vs_20": vol5 / vol20 if vol20 else None}
    fails = []
    if close < C.MIN_PRICE:
        fails.append("price < $5")
    if s200 is None:
        fails.append(f"no 200d SMA ({len(bars)} bars)")
    elif close <= s200:
        fails.append("below 200d")
    if mcap < C.MIN_MCAP:
        fails.append("cap < $1B")
    if vol20 < C.MIN_AVG_VOL:
        fails.append("avg vol < 1M")
    if a20 is None or a20 < C.MIN_ADR_CORE:
        fails.append("ADR20 < 3%")
    m["step1_fails"] = fails
    m["step1"] = not fails
    return m


def planned_boxes(m, hot_groups, spy):
    """A+ boxes knowable after the close. Box 1 (gap + morning rules) and 6 (catalyst) are decided later."""
    return {
        1: None,
        2: m["adr20"] is not None and m["adr20"] >= C.ADR_APLUS,
        3: m["dollar_vol20"] >= C.DOLLAR_VOL_APLUS,
        4: m["mcap"] >= C.MCAP_APLUS,
        5: m["group"] in hot_groups,
        6: None,
        7: m["ext20"] is not None and m["ext20"] <= C.EXT_MAX,
        8: (m["pos52"] or 0) >= C.POS52_MIN or m["from_high"] >= -C.FROM_HIGH_MAX,
        9: spy["state"] != "Sideways",
    }


def rank_key(m):
    """Hot sector first, then ADR20 (1% buckets), then breakout-ready, then nearness to the 52w high."""
    return (not m["hot"], -int((m["adr20"] or 0) * 100), not m["breakout_ready"], -(m["pos52"] or 0))


def run(stock_bars, etf_bars, snapshot, earnings=None, asof=None, top_n=5):
    asof = dt.date.fromisoformat(asof) if isinstance(asof, str) else asof
    stock_bars = {t: _upto(b, asof) for t, b in stock_bars.items() if t in C.TICKER_GROUP}
    etf_bars = {t: _upto(b, asof) for t, b in etf_bars.items()}
    spy = regime(etf_bars["SPY"])
    heat = sector_heat(stock_bars, etf_bars)
    hot = [r["group"] for r in heat if r["hot"]]
    session_date = dt.date.fromisoformat(spy["date"])
    nxt = sessions.next_trading_day(session_date)
    earnings = earnings or {}

    rows = []
    for t, bars in stock_bars.items():
        if len(bars) < 25:
            continue
        m = metrics(t, bars, snapshot.get(t), asof)
        m["hot"] = m["group"] in hot
        m["boxes"] = planned_boxes(m, hot, spy)
        m["mech_boxes"] = sum(1 for k, v in m["boxes"].items() if v)
        m["aplus_candidate"] = all(v for v in m["boxes"].values() if v is not None)
        m["planned_grade"] = "A+ (if gap + catalyst)" if m["aplus_candidate"] else "Normal"
        m["planned_risk"] = C.RISK_APLUS if m["aplus_candidate"] else C.RISK_NORMAL
        m["extended"] = m["ext20"] is not None and m["ext20"] > C.EXT_MAX
        m["earnings"] = earnings.get(t)
        rows.append(m)
    passed = sorted([m for m in rows if m["step1"]], key=rank_key)
    for i, m in enumerate(passed):
        m["rank"] = i + 1
    top = passed[:top_n]

    notes = []
    if spy["state"] == "Sideways":
        notes.append("SPY sideways: no new Trend Join trades next session.")
    if not spy["above200"]:
        notes.append("SPY below its 200-day SMA: longs only with an A+ grade.")
    status = sessions.day_status(nxt)
    if status != "full day":
        notes.append(f"Next session {nxt} is a {status}. Plan below is for {sessions.next_full_day(session_date)}.")
    return {"kind": "after_close", "session": spy["date"], "next_session": nxt.isoformat(),
            "next_session_status": status, "next_full_day": sessions.next_full_day(session_date).isoformat(),
            "spy": spy, "heat": heat, "hot_groups": hot, "notes": notes,
            "universe": len(rows), "step1_pass": [m["ticker"] for m in passed],
            "top": top, "all": {m["ticker"]: m for m in rows}}


# ---------- report ----------

def _p(x, d=1):
    return "-" if x is None else f"{x * 100:.{d}f}%"


def _bn(x):
    return f"${x / 1e9:.0f}B" if x >= 1e9 else f"${x / 1e6:.0f}M"


def report(st):
    s = st["spy"]
    out = [f"## After-close check: session {st['session']} (next: {st['next_session']}, {st['next_session_status']})", ""]
    out.append(f"**SPY regime: {s['state']}.** Close {s['close']:.2f}, {s['dist20_pct']:+.2f}% vs 20d SMA "
               f"{s['sma20']} (5-day slope {s['sma20_slope5']:+.2f}); 200d SMA {s['sma200']} "
               f"({'above' if s['above200'] else 'BELOW'}).")
    for n in st["notes"]:
        out.append(f"- {n}")
    out += ["", "**Sector heat** (median member return; rank = average of 5d and 20d ranks)", "",
            "| # | Group | 5d | 20d | ETF 5d / 20d | Hot |", "|---|---|---|---|---|---|"]
    for r in st["heat"]:
        etf = f"{r['etf']} {_p(r['etf_ret5'])} / {_p(r['etf_ret20'])}" if r["etf"] else ""
        out.append(f"| {r['rank'] or '-'} | {r['group']} ({r['n']}) | {_p(r['ret5'])} | {_p(r['ret20'])} | {etf} | "
                   f"{'HOT' if r['hot'] else ''} |")
    out += ["", f"**Screen:** {st['universe']} stocks, {len(st['step1_pass'])} pass step 1 "
            f"(> $5, above 200d, cap >= $1B, avg vol >= 1M, ADR20 >= 3%).", "",
            "**Top 5 watchlist** (trade at most 2; needs a 3%+ gap tomorrow morning)", "",
            "| # | Ticker | Group | Close | PDH / PDL | 20d / 200d SMA | ADR20 | Ext 20d | 52w pos | $vol20 | Cap | Boxes | Plan |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in st["top"]:
        lv = m["levels"]
        flags = (" BO-ready" if m["breakout_ready"] else "") + (" EXTENDED" if m["extended"] else "")
        out.append(f"| {m['rank']} | {m['ticker']}{flags} | {m['group']} | {m['close']:.2f} | {lv['pdh']:.2f} / {lv['pdl']:.2f} | "
                   f"{m['sma20']:.2f} / {m['sma200']:.2f} | {_p(m['adr20'])} | {_p(m['ext20'])} | {_p(m['pos52'], 0)} | "
                   f"{_bn(m['dollar_vol20'])} | {_bn(m['mcap'])} | {m['mech_boxes']}/7 | {m['planned_grade']}, ${m['planned_risk']} |")
    out += ["", "Levels (resistance above / support below):"]
    for m in st["top"]:
        lv = m["levels"]
        e = f"; earnings {m['earnings']}" if m["earnings"] else ""
        out.append(f"- **{m['ticker']}** ({m['liquid']}): res {', '.join(f'{x:.2f}' for x in lv['resistance']) or 'none in 60d'}"
                   f"; 20d high {lv['high20']:.2f}; 52w high {m['hi52']:.2f}; sup {', '.join(f'{x:.2f}' for x in lv['support']) or '-'}{e}")
    missing = [f"{m['ticker']} ({'; '.join(m['step1_fails'])})" for m in st["all"].values()
               if not m["step1"] and m["group"] in st["hot_groups"]]
    if missing:
        out += ["", "Hot-group names failing step 1: " + ", ".join(sorted(missing))]
    return "\n".join(out)

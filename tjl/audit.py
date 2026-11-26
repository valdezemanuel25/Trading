"""Audit of the TJL Trades log against the go/no-go criteria (docs/intraday-stock-research.md).

Input: the Notion SQL result (SELECT * on the data source), saved as JSON. Rows whose title starts with
"TEST" are ignored. Real trades = Status Closed; Shadow rows are compared with the real trade of the same
date + ticker (paired A vs B). R = P&L $ / Risk $ (net of fees and funding, as logged).
"""
import datetime as dt
import json

MIN_TRADES, MIN_DAYS = 30, 61


def _multi(x):
    if not x:
        return []
    if isinstance(x, list):
        return x
    try:
        return json.loads(x)
    except ValueError:
        return [x]


def _r(row):
    try:
        return row["P&L $"] / row["Risk $"]
    except (TypeError, ZeroDivisionError, KeyError):
        return None


def stats(rows):
    rs = [_r(x) for x in rows if _r(x) is not None]
    pnl = [x["P&L $"] for x in rows if x.get("P&L $") is not None]
    if not rs:
        return {"n": 0}
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p < 0]
    eq = peak = dd = 0.0
    for p in pnl:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {"n": len(rs), "win": len([r for r in rs if r > 0]) / len(rs), "exp_r": sum(rs) / len(rs),
            "pf": (sum(wins) / -sum(losses)) if losses else None, "total": sum(pnl), "max_dd": dd,
            "worst_r": min(rs)}


def followed(row):
    m = _multi(row.get("Mistakes"))
    return row.get("Rule followed") == "__YES__" and "Ignored rule" not in m and "Moved stop" not in m


def verdict(s, days, rule_pct):
    if s["n"] and s["max_dd"] <= -3000:
        return "NO-GO / PAUSE: drawdown hit -$3,000"
    if s["n"] < MIN_TRADES or days < MIN_DAYS:
        return f"TOO EARLY: {s['n']}/{MIN_TRADES} closed trades, {days}/{MIN_DAYS} days"
    if s["exp_r"] <= 0 or (s["pf"] is not None and s["pf"] < 1.1):
        return "NO-GO: expectancy <= 0R or profit factor < 1.1"
    ok = (s["exp_r"] >= 0.20 and (s["pf"] is None or s["pf"] >= 1.3) and s["total"] > 0
          and rule_pct >= 0.90 and s["worst_r"] >= -1.3)
    return "GO (small real money, same $ risk or lower)" if ok else "EXTEND one month (between no-go and go)"


def run(rows, today=None):
    rows = [r for r in rows if not (r.get("Trade") or "").upper().startswith("TEST")]
    real = sorted([r for r in rows if r.get("Status") == "Closed"],
                  key=lambda r: (r.get("date:Exit time:start") or r.get("date:Date:start") or ""))
    shadow = [r for r in rows if r.get("Status") == "Shadow" and r.get("P&L $") is not None]
    dates = sorted(r["date:Date:start"] for r in real if r.get("date:Date:start"))
    today = today or dt.date.today()
    days = (today - dt.date.fromisoformat(dates[0])).days if dates else 0
    overall = stats(real)
    rule_pct = (sum(followed(r) for r in real) / len(real)) if real else 0

    def split(key, fn=None):
        groups = {}
        for r in real:
            k = fn(r) if fn else r.get(key)
            groups.setdefault(str(k), []).append(r)
        return {k: stats(v) for k, v in sorted(groups.items())}

    boxes = {}
    for b in sorted({b for r in real for b in _multi(r.get("A+ boxes"))}):
        boxes[b] = {"with": stats([r for r in real if b in _multi(r.get("A+ boxes"))]),
                    "without": stats([r for r in real if b not in _multi(r.get("A+ boxes"))])}
    pairs = []
    for s in shadow:
        mate = [r for r in real if r.get("Ticker") == s.get("Ticker") and r.get("date:Date:start") == s.get("date:Date:start")]
        if mate:
            pairs.append({"date": s["date:Date:start"], "ticker": s["Ticker"], "real": mate[0].get("Version"),
                          "real_r": _r(mate[0]), "shadow": s.get("Version"), "shadow_r": _r(s)})
    by_version_incl_shadow = {}
    for r in real + shadow:
        by_version_incl_shadow.setdefault(r.get("Version"), []).append(r)
    return {"kind": "audit", "date": today.isoformat(), "days": days, "overall": overall, "rule_pct": rule_pct,
            "verdict": verdict(overall, days, rule_pct),
            "by_version": split("Version"), "by_grade": split("Grade"), "by_window": split("Entry window"),
            "by_regime": split("SPY regime"), "by_catalyst": split("Catalyst type"),
            "by_overnight": split("Held overnight"), "by_5m_confirm": split("5m confirm (VWAP + 8 EMA)"),
            "boxes": boxes, "pairs": pairs,
            "version_with_shadow": {k: stats(v) for k, v in by_version_incl_shadow.items()},
            "skipped": sum(r.get("Status") == "Skipped" for r in rows),
            "missed": sum(r.get("Status") == "Missed" for r in rows),
            "missed_stats": stats([r for r in rows if r.get("Status") == "Missed"])}


def _fmt(s):
    if not s.get("n"):
        return "n 0"
    pf = "-" if s["pf"] is None else f"{s['pf']:.2f}"
    return (f"n {s['n']}, win {s['win'] * 100:.0f}%, exp {s['exp_r']:+.2f}R, PF {pf}, ${s['total']:+,.0f}, "
            f"max DD ${s['max_dd']:,.0f}, worst {s['worst_r']:+.2f}R")


def report(st):
    out = [f"## TJL audit ({st['date']}, day {st['days']} of the test)", "",
           f"**{st['verdict']}**", "", f"All closed trades: {_fmt(st['overall'])}; rules followed {st['rule_pct'] * 100:.0f}%",
           f"Skipped {st['skipped']}, Missed {st['missed']} ({_fmt(st['missed_stats'])})", ""]
    for title, key in (("Version", "by_version"), ("Grade", "by_grade"), ("Entry window", "by_window"),
                       ("SPY regime", "by_regime"), ("Catalyst type", "by_catalyst"),
                       ("Held overnight", "by_overnight"), ("5m confirm", "by_5m_confirm")):
        out.append(f"**{title}**")
        out += [f"- {k}: {_fmt(v)}" for k, v in st[key].items()]
    out.append("**Version incl. shadow rows** (A vs B on more setups)")
    out += [f"- {k}: {_fmt(v)}" for k, v in st["version_with_shadow"].items()]
    if st["pairs"]:
        out.append(f"**Paired setups ({len(st['pairs'])})**")
        out += [f"- {p['date']} {p['ticker']}: real {p['real']} {p['real_r']:+.2f}R vs shadow {p['shadow']} {p['shadow_r']:+.2f}R"
                for p in st["pairs"]]
    out.append("**A+ boxes** (with / without)")
    out += [f"- {b}: {_fmt(v['with'])} | {_fmt(v['without'])}" for b, v in st["boxes"].items()]
    return "\n".join(out)

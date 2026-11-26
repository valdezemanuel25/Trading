"""Morning check (about 9:00-9:30 ET): gappers among the step-1 names, premarket high, volume and RVOL,
final 1-2 names with trigger, planned stop, 1R and size for each version.

Stops here are provisional (the low of day isn't known before the open; the premarket low stands in).
The trigger command recomputes everything from the live 5m chart.
"""
import datetime as dt

from . import config as C
from . import sessions
from .sizing import size
from .webull import fnum, minutes_et


def _pre_stats(bars, day, now_min):
    """Premarket high/low/volume for `day` up to now_min, and RVOL vs the same window on prior days."""
    today = [b for b in bars if b["date"] == day and b["session"] == "PRE" and minutes_et(b["t"]) < now_min]
    if not today:
        return None
    prior_days = sorted({b["date"] for b in bars if b["date"] < day and b["session"] == "PRE"})[-C.RVOL_LOOKBACK:]
    vols = []
    for d in prior_days:
        vols.append(sum(b["volume"] for b in bars if b["date"] == d and b["session"] == "PRE"
                        and minutes_et(b["t"]) < now_min))
    avg = sum(vols) / len(vols) if vols else 0
    vol = sum(b["volume"] for b in today)
    return {"pmh": max(b["high"] for b in today), "pml": min(b["low"] for b in today),
            "pm_last": today[-1]["close"], "pm_vol": vol, "pm_rvol": vol / avg if avg else None,
            "rvol_days": len(vols), "source": "5m PRE bars"}


def _snap_stats(s):
    last = fnum(s.get("extend_hour_last_price")) or fnum(s.get("price"))
    return {"pmh": fnum(s.get("extend_hour_high")), "pml": fnum(s.get("extend_hour_low")), "pm_last": last,
            "pm_vol": fnum(s.get("extend_hour_volume"), 0), "pm_rvol": None, "rvol_days": 0,
            "source": "snapshot (no RVOL)"}


def evaluate(m, pm, spy, half_day):
    lv = m["levels"]
    prior = lv["prior_close"]
    gap = pm["pm_last"] / prior - 1
    adr_px = (m["adr20"] or 0.03) * pm["pm_last"]
    overhead = sorted(x for x in lv["resistance"] + [m["hi52"]] + ([m["sma200"]] if m["sma200"] else [])
                      if x > pm["pm_last"])
    near_res = overhead[0] if overhead and overhead[0] - pm["pm_last"] <= adr_px else None
    checks = {
        "gap >= 3%": gap >= C.GAP_MIN,
        "above prior-day high": pm["pm_last"] > lv["pdh"],
        "premarket vol >= 20k": pm["pm_vol"] >= C.PM_VOL_MIN,
        "SPY not sideways": spy["state"] != "Sideways",
        "full session": not half_day,
    }
    core = all(checks.values())
    boxes = {int(k): v for k, v in m["boxes"].items()}
    boxes[1] = core
    others = [boxes[k] for k in (2, 3, 4, 5, 7, 8, 9)]
    aplus_if_catalyst = core and all(others)
    blocked = None
    if not spy["above200"] and not aplus_if_catalyst:
        blocked = "SPY below 200d: A+ only"
    rvol = pm["pm_rvol"]
    return {"ticker": m["ticker"], "liquid": m["liquid"], "group": m["group"], "prior_close": prior,
            "pdh": lv["pdh"], "gap": gap, **pm, "checks": checks, "core": core,
            "a_rvol_ok": rvol is not None and rvol > C.RVOL_A,
            "boxes": boxes, "box_count": sum(1 for v in boxes.values() if v),
            "aplus_if_catalyst": aplus_if_catalyst, "blocked": blocked, "near_resistance": near_res,
            "adr20": m["adr20"], "ext20": m["ext20"], "pos52": m["pos52"], "mcap": m["mcap"],
            "earnings": m.get("earnings")}


def plan(r):
    """Provisional trigger, stops, 1R and size for both versions (premarket low stands in for LOD)."""
    trig = r["pmh"]
    lod = r["pml"]
    risk = C.RISK_APLUS if r["aplus_if_catalyst"] else C.RISK_NORMAL
    out = {"trigger": trig, "risk_planned": risk}
    for v, stop in (("A", min(r["pmh"] * 0.99, lod)), ("B", lod * 0.99)):
        try:
            sz = size(trig, stop, risk)
        except ValueError:
            continue
        out[v] = {"stop": stop, "one_r": trig - stop, **sz}
    return out


def run(prev, snapshot, pre_bars, date=None, now=None):
    day = dt.date.fromisoformat(date) if date else dt.date.fromisoformat(prev["next_session"])
    if now:
        hh, mm = map(int, now.split(":"))
        now_min = hh * 60 + mm
    else:
        now_min = C.RTH_OPEN
    spy = prev["spy"]
    half = sessions.is_half_day(day)
    rows = []
    for t in prev["step1_pass"]:
        m = prev["all"][t]
        pm = _pre_stats(pre_bars[t], day, now_min) if t in pre_bars else None
        if pm is None and t in snapshot:
            pm = _snap_stats(snapshot[t])
        if pm is None or not pm["pm_last"]:
            continue
        rows.append(evaluate(m, pm, spy, half))
    rows.sort(key=lambda r: (not r["core"], r["blocked"] is not None, -r["box_count"], -r["gap"]))
    final = [r for r in rows if r["core"] and not r["blocked"]][:C.MAX_TRADES_PER_DAY]
    for r in final:
        r["plan"] = plan(r)
    watch_top = [m["ticker"] for m in prev["top"]]
    return {"kind": "morning", "date": day.isoformat(), "day_status": sessions.day_status(day),
            "now_et": f"{now_min // 60:02d}:{now_min % 60:02d}", "prior_session": prev["session"],
            "spy": spy, "hot_groups": prev["hot_groups"], "watchlist": watch_top,
            "rows": rows, "final": [r["ticker"] for r in final],
            "final_rows": {r["ticker"]: r for r in final},
            "all_rows": {r["ticker"]: r for r in rows}}


def _p(x):
    return "-" if x is None else f"{x * 100:+.1f}%"


def report(st):
    out = [f"## Morning check: {st['date']} ({st['day_status']}), data to {st['now_et']} ET", ""]
    s = st["spy"]
    out.append(f"SPY regime (prior close): **{s['state']}**, {'above' if s['above200'] else 'below'} the 200d.")
    if st["day_status"] != "full day":
        out.append(f"**{st['day_status']}: no Trend Join trades today.** Table for the record only.")
    out += ["", "| Ticker | Gap | PM last | PM high | PM vol | PM RVOL | > PDH | Core | Boxes | Note |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in st["rows"]:
        if r["gap"] < 0.02 and r["ticker"] not in st["watchlist"]:
            continue
        note = []
        if r["blocked"]:
            note.append(r["blocked"])
        if r["near_resistance"]:
            note.append(f"resistance {r['near_resistance']:.2f} within 1 ADR")
        failed = [k for k, v in r["checks"].items() if not v]
        if failed:
            note.append("fails: " + ", ".join(failed))
        rv = "-" if r["pm_rvol"] is None else f"{r['pm_rvol']:.1f}"
        out.append(f"| {r['ticker']} | {_p(r['gap'])} | {r['pm_last']:.2f} | {r['pmh'] or 0:.2f} | {r['pm_vol']:,.0f} | {rv} | "
                   f"{'yes' if r['checks']['above prior-day high'] else 'no'} | {'PASS' if r['core'] else '-'} | "
                   f"{r['box_count']}/8 | {'; '.join(note)} |")
    out.append("")
    if not st["final"]:
        out.append("**Final list: none.** No name passes the core + morning rules. No alerts needed.")
        return "\n".join(out)
    out.append("**Final list** (set one Webull alert per name: price crosses above the trigger; it means \"go look\")")
    for t in st["final"]:
        r = st["final_rows"][t]
        p = r["plan"]
        grade = "A+ if the catalyst holds up" if r["aplus_if_catalyst"] else "Normal"
        rv = "-" if r["pm_rvol"] is None else f"{r['pm_rvol']:.1f}"
        out += ["", f"### {t} ({r['liquid']}): trigger **{p['trigger']:.2f}**, {grade}, risk ${p['risk_planned']}",
                f"Gap {_p(r['gap'])}, PM high {r['pmh']:.2f}, PM low {r['pml']:.2f}, PM RVOL {rv}"
                f" (A needs > {C.RVOL_A}: {'yes' if r['a_rvol_ok'] else 'no'}). Entries from 10:00 (A) / 10:05 (B); "
                "if price makes a new high before then, the trigger moves up to it."]
        for v in ("A", "B"):
            if v in p:
                x = p[v]
                out.append(f"- {C.VERSION_NAME[v]}: stop {x['stop']:.2f} ({x['stop_pct'] * 100:.1f}%), 1R {x['one_r']:.2f}, "
                           f"${x['notional']:,.0f} at {x['leverage']}x (margin ${x['margin']:,.0f}), risk ${x['risk']:.0f}"
                           + (" (capped by margin)" if x["capped"] else ""))
    out.append("\nStops are provisional (premarket low stands in for the low of day); the trigger check recomputes them.")
    return "\n".join(out)

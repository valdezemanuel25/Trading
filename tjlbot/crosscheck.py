"""Daily cross-check of the bot's 9:15 scan against Webull's data (run by Claude's 4:37 PM report task).

For every name in the universe, Webull's 5m premarket bars (up to 9:00) and its prior close give an independent
gap, premarket high and volume. The script then answers two questions:
  1. Data: do Webull and the bot's feed (Alpaca) agree on the numbers the rules use?
  2. Misses: is there a name Webull shows gapping 3%+ above its prior-day high that the bot didn't flag, and why?
No opinions: it reports the rule that excluded each name, from the bot's own after_close.json / morning.json.
"""
import json
import os

from tjl import config as C
from tjl.morning import _pre_stats
from tjl.webull import fnum

GAP_TOL = 0.005     # 0.5 percentage point
PX_TOL = 0.005      # 0.5% on prices
VOL_TOL = 0.30      # 30% on premarket volume (different feeds count odd lots and late prints differently)


def _load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def run(day_dir, snapshot, pre_bars, date):
    """snapshot: {ticker: Webull snapshot dict, taken after today's close (pre_close = prior session's close)}.
    pre_bars: {ticker: tjl bar dicts}, Webull 5m PRE bars of today (more days give RVOL too)."""
    import datetime as dt
    day = dt.date.fromisoformat(date)
    ac = _load(os.path.join(day_dir, "after_close.json"), {}) or {}
    ms = _load(os.path.join(day_dir, "morning.json"), {}) or {}
    daily = _load(os.path.join(day_dir, "day.json"), {}) or {}
    rows = ms.get("all_rows", {})
    final = set(daily.get("final", ms.get("final", [])))
    skipped = daily.get("skipped", {})
    out = {"date": date, "bot_ran": bool(ms), "names": {}, "data_issues": [], "missed": [], "flagged_both": [],
           "flagged_bot_only": []}
    for t in C.UNIVERSE:
        snap = snapshot.get(t) or {}
        prior = fnum(snap.get("pre_close"))
        pm = _pre_stats(pre_bars.get(t, []), day, 9 * 60) if pre_bars.get(t) else None
        m = (ac.get("all") or {}).get(t, {})
        r = rows.get(t)
        rec = {"webull_prior_close": prior, "bot_prior_close": (m.get("levels") or {}).get("prior_close")}
        if pm and prior:
            rec.update(webull_gap=pm["pm_last"] / prior - 1, webull_pmh=pm["pmh"], webull_pm_vol=pm["pm_vol"],
                       webull_pm_rvol=pm["pm_rvol"])
        if r:
            rec.update(bot_gap=r["gap"], bot_pmh=r["pmh"], bot_pm_vol=r["pm_vol"], bot_pm_rvol=r.get("pm_rvol"))
        out["names"][t] = rec
        issues = []
        if prior and rec["bot_prior_close"] and abs(rec["bot_prior_close"] / prior - 1) > 0.002:
            issues.append(f"prior close {rec['bot_prior_close']:.2f} (bot) vs {prior:.2f} (Webull)")
        if r and "webull_gap" in rec:
            if abs(rec["webull_gap"] - r["gap"]) > GAP_TOL or (rec["webull_gap"] >= C.GAP_MIN) != (r["gap"] >= C.GAP_MIN):
                issues.append(f"gap {r['gap'] * 100:+.1f}% (bot) vs {rec['webull_gap'] * 100:+.1f}% (Webull)")
            if r["pmh"] and abs(rec["webull_pmh"] / r["pmh"] - 1) > PX_TOL:
                issues.append(f"premarket high {r['pmh']:.2f} (bot) vs {rec['webull_pmh']:.2f} (Webull)")
            if max(r["pm_vol"], rec["webull_pm_vol"]) >= C.PM_VOL_MIN and \
                    abs(rec["webull_pm_vol"] - r["pm_vol"]) > VOL_TOL * max(r["pm_vol"], rec["webull_pm_vol"]):
                issues.append(f"premarket volume {r['pm_vol']:,.0f} (bot) vs {rec['webull_pm_vol']:,.0f} (Webull)")
        if issues:
            out["data_issues"].append({"ticker": t, "issues": issues})
        # would Webull's numbers pass the gap / prior-day high / volume rules?
        pdh = (m.get("levels") or {}).get("pdh")
        wb_pass = ("webull_gap" in rec and rec["webull_gap"] >= C.GAP_MIN and pdh is not None
                   and pm["pm_last"] > pdh and pm["pm_vol"] >= C.PM_VOL_MIN)
        if t in final and wb_pass:
            out["flagged_both"].append(t)
        elif t in final:
            out["flagged_bot_only"].append(t)
        elif wb_pass:
            out["missed"].append({"ticker": t, "webull_gap": rec["webull_gap"], "why": _why(t, m, r, final, skipped, ms)})
    return out


def _why(t, m, r, final, skipped, ms):
    if not m:
        return "not in the bot's after-close data (missing daily bars?)"
    if not m.get("step1"):
        return "failed step 1: " + "; ".join(m.get("step1_fails", []))
    if t in skipped:
        return skipped[t].get("why", "skipped")
    if not r:
        return "no premarket bars on the bot's feed"
    if not r.get("core"):
        return "bot's numbers failed: " + ", ".join(k for k, v in r["checks"].items() if not v)
    if r.get("blocked"):
        return r["blocked"]
    return f"passed but ranked below the top {C.MAX_TRADES_PER_DAY} (A+ boxes, then gap): final = {', '.join(sorted(final)) or 'none'}"


def report(st):
    out = [f"### Webull cross-check ({st['date']})"]
    if not st["bot_ran"]:
        out.append("The bot has no morning scan for this date (closed, half day, or the job didn't run).")
    n = sum(1 for r in st["names"].values() if "webull_gap" in r)
    out.append(f"Names with Webull premarket data: {n} of {len(st['names'])}. Data disagreements: {len(st['data_issues'])}. "
               f"Flagged by both: {', '.join(st['flagged_both']) or 'none'}. "
               f"Flagged by the bot only: {', '.join(st['flagged_bot_only']) or 'none'}. "
               f"Webull gappers the bot didn't flag: {len(st['missed'])}.")
    for d in st["data_issues"]:
        out.append(f"- data {d['ticker']}: " + "; ".join(d["issues"]))
    for x in st["missed"]:
        out.append(f"- missed {x['ticker']} (Webull gap {x['webull_gap'] * 100:+.1f}%): {x['why']}")
    return "\n".join(out)

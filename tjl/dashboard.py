"""Build the two small files the "Trend Join Tracker" dashboard reads: status.json (one row: regime, next
session, RSI(2)) and plan.json (watchlist / final names with levels). Uploaded after each after-close and
morning check. Trades and positions are live on the dashboard (Notion, Liquid), not in these files.
"""
import datetime as dt
import json
import os


def _r(x, d=2):
    return None if x is None else round(x, d)


def build(after_close, morning=None, rsi2=None):
    st = after_close
    s = st["spy"]
    stage = "after-close"
    rows = []
    if morning and morning.get("prior_session") == st["session"]:
        stage = "morning"
        final = set(morning["final"])
        for t, r in morning["all_rows"].items():
            if t not in final and t not in morning["watchlist"]:
                continue
            p = r.get("plan") or {}
            rows.append({"ticker": t, "group": r["group"], "status": "Alert set" if t in final else "Dropped",
                         "gap_pct": _r(r["gap"] * 100, 1), "pm_high": _r(r["pmh"]), "trigger": _r(p.get("trigger")),
                         "stop_a": _r((p.get("A") or {}).get("stop")), "stop_b": _r((p.get("B") or {}).get("stop")),
                         "grade": "A+?" if r["aplus_if_catalyst"] else "Normal", "risk": p.get("risk_planned"),
                         "note": "; ".join(k for k, v in r["checks"].items() if not v) or ""})
        rows.sort(key=lambda x: (x["status"] != "Alert set", -(x["gap_pct"] or 0)))
    else:
        for m in st["top"]:
            rows.append({"ticker": m["ticker"], "group": m["group"], "status": "Watch", "gap_pct": None,
                         "pm_high": None, "trigger": None, "stop_a": None, "stop_b": None,
                         "grade": "A+?" if m["aplus_candidate"] else "Normal", "risk": m["planned_risk"],
                         "note": f"close {m['close']:.2f}, PDH {m['levels']['pdh']:.2f}, ADR {m['adr20'] * 100:.1f}%"
                                 + (", earnings " + m["earnings"] if m.get("earnings") else "")})
    rsi2 = rsi2 or {}
    status = [{"as_of": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "stage": stage,
               "session": st["session"], "next_trade_day": st["next_full_day"],
               "no_trade_days": "" if st["next_session"] == st["next_full_day"] else
               f"{st['next_session']} ({st['next_session_status'].split(' (')[0]})", "spy_state": s["state"], "spy_dist20_pct": s["dist20_pct"],
               "spy_above200": "yes" if s["above200"] else "no", "longs_allowed": (
                   "None (sideways)" if s["state"] == "Sideways" else ("A+ only" if not s["above200"] else "All grades")),
               "hot_groups": ", ".join(st["hot_groups"]), "step1_pass": len(st["step1_pass"]),
               "rsi2_sp": rsi2.get("sp"), "rsi2_sp_action": rsi2.get("sp_action"),
               "rsi2_nq": rsi2.get("nq"), "rsi2_nq_action": rsi2.get("nq_action")}]
    return status, rows


def write(out_dir, status, rows, source_note):
    os.makedirs(out_dir, exist_ok=True)
    for name, data in (("status.json", status), ("plan.json", rows)):
        with open(os.path.join(out_dir, name), "w") as f:
            json.dump({"rows": data, "meta": [{"label": "Built from", "value": source_note}]}, f, indent=1)

"""End-of-day output: P&L from Alpaca fills, both versions simulated on the day's 5m bars (sim vs sim for A/B),
rows in the Notion "TJL Trades" schema (same keys the manual routine writes), and a markdown report."""
import datetime as dt

from tjl import shadow
from tjl import config as C

from . import settings as S

LIQUID_ONLY = ("Leverage", "Margin $")


def apply_fills(t, fills):
    """Entry and exit fills of this trade, in time order, until the position is flat again."""
    bq = bv = sq = sv = 0.0
    last = None
    for f in sorted(fills, key=lambda f: f["transaction_time"]):
        q, p = float(f["qty"]), float(f["price"])
        if f["side"] == "buy":
            if bq and sq >= bq:
                break
            bq, bv = bq + q, bv + q * p
        else:
            sq, sv, last = sq + q, sv + q * p, f
        if bq and sq >= bq - 1e-9:
            break
    t["bought"], t["sold"] = bq, sq
    if bq:
        t["fill"] = bv / bq
    if bq and sq >= bq - 1e-9 and last:
        t["pnl"] = round(sv - bv, 2)
        t["exit_px"] = round(sv / sq, 4)
        t["final_exit_px"] = float(last["price"])
        t["exit_time"] = last["transaction_time"]
    else:
        t["pnl"] = None


def simulate(st, bars, day):
    """Both versions' exits on the day's bars from the trigger time (tjl.shadow conventions, no fees on Alpaca)."""
    hh, mm = map(int, st["time_et"].split(":"))
    out = {}
    for v, leg in (st.get("legs") or {}).items():
        try:
            s = shadow.simulate(bars, day, hh * 60 + mm, st["chart"]["last"], leg["webull_stop"], v)
        except (ValueError, IndexError, ZeroDivisionError):
            continue
        out[v] = {"r": round(s["r_gross"], 3), "mfe_r": round(s["mfe_r"], 2), "mae_r": round(s["mae_r"], 2),
                  "final_price": s["final_price"], "final_reason": s["final_reason"],
                  "final_time": s["final_time"].isoformat(), "risk": leg["risk"]}
    return out


def _clean(props):
    return {k: v for k, v in props.items() if v is not None and k not in LIQUID_ONLY}


def _exit_reason(reason):
    return reason if reason in ("Stop", "Breakeven", "Trail", "Time 3:51") else (
        "Time 3:51" if str(reason).startswith("Carry") else "Manual")


def notion_rows(bot, touched, sims):
    today = bot.day.isoformat()
    rows = []
    for t in touched:
        st, v = t["st"], t["version"]
        base = dict((st.get("notion") or [{}])[0])
        sim = sims.get(t["id"], {})
        cat = t.get("catalyst") or {}
        props = {**base, "Status": "Closed" if t["status"] == "closed" else "Open",
                 "Entry price": round(t["fill"], 2), "Stop price": t["stop0"],
                 "Stop %": round((t["fill"] - t["stop0"]) / t["fill"] * 100, 2), "Risk $": t.get("risk_actual"),
                 "Position $": round(t["fill"] * t["qty"], 2), "Fees $": 0, "Funding $": 0,
                 "Held overnight": "__YES__" if t.get("carried") else "__NO__", "Rule followed": "__YES__",
                 "Liquid order IDs": ", ".join(t.get("order_ids", []))}
        tps = [x["price"] for x in sorted(t.get("targets", []), key=lambda x: x["n"])]
        props["Partial 1 price"] = tps[0] if tps else None
        props["Partial 2 price"] = tps[1] if len(tps) > 1 else None
        if t.get("pnl") is not None:
            props.update({"P&L $": t["pnl"], "Final exit price": t["final_exit_px"],
                          "date:Exit time:start": t["exit_time"], "date:Exit time:is_datetime": 1,
                          "Exit reason": t.get("exit_reason") or "Manual"})
        if v in sim:
            props["MFE R"], props["MAE R"] = sim[v]["mfe_r"], sim[v]["mae_r"]
        props["Notes"] = "; ".join(x for x in (
            f"Executor: Alpaca paper bot (feed {S.FEED})",
            f"planned risk ${t['risk_planned']:.0f}" + (f" (target ${st.get('risk_target')})" if st.get("risk_target") else ""),
            f"sim_r={sim[v]['r']:+.3f}" if v in sim else "",
            f"catalyst auto: {cat.get('type', 'None')} - {cat.get('headline', '')}"[:300],
            f"exit: {t.get('exit_why', '')}" if t.get("exit_why") else "",
            f"stop moved to {t['stop_now']}" if t["stop_now"] != t["stop0"] else "") if x)
        if t["date"] == today or t["status"] == "closed":
            rows.append({"key": props["Trade"], "action": "upsert", "properties": _clean(props)})
        sv = st.get("shadow")
        if t["date"] == today and sv and sv in sim and len(st.get("notion") or []) > 1:
            s = sim[sv]
            sh = {**st["notion"][1], "Status": "Shadow", "Final exit price": round(s["final_price"], 4),
                  "date:Exit time:start": s["final_time"], "date:Exit time:is_datetime": 1,
                  "Exit reason": _exit_reason(s["final_reason"]), "MFE R": s["mfe_r"], "MAE R": s["mae_r"],
                  "Fees $": 0, "P&L $": round(s["r"] * s["risk"], 2),
                  "Notes": f"Executor: Alpaca paper bot; shadow simulated from 5m bars; sim_r={s['r']:+.3f}"}
            rows.append({"key": sh["Trade"], "action": "upsert", "properties": _clean(sh)})
    for name, sk in bot.daily["skipped"].items():
        if any(t["ticker"] == name and t["date"] == today for t in touched):
            continue
        st = sk.get("st") or {}
        sim = sims.get("skip-" + name, {})
        r = (bot.plan or {}).get("all_rows", {}).get(name, {})
        props = {"Trade": f"{today} {name} (skipped)", "date:Date:start": today, "date:Date:is_datetime": 0,
                 "Ticker": name, "Status": "Skipped", "Grade": st.get("grade"), "Sector": r.get("group"),
                 "SPY regime": (bot.plan or {}).get("spy", {}).get("state"),
                 "Gap %": round(r["gap"] * 100, 2) if r.get("gap") is not None else None,
                 "Premarket RVOL": round(r["pm_rvol"], 2) if r.get("pm_rvol") else None,
                 "Trigger price": st.get("trigger_level"),
                 "Notes": f"Executor: Alpaca paper bot; not taken at {sk.get('time', 'premarket')}: {sk['why']}"[:1500]
                          + "".join(f"; would-be {v} sim {x['r']:+.2f}R" for v, x in sim.items())}
        rows.append({"key": props["Trade"], "action": "upsert", "properties": _clean(props)})
    return rows


def markdown(bot, touched, sims):
    today = bot.day.isoformat()
    d = bot.daily
    out = [f"## Trend Join bot: {today}", ""]
    plan = bot.plan or {}
    out.append(f"SPY regime: {plan.get('spy', {}).get('state', '?')}. Final names: {', '.join(d['final']) or 'none'}."
               + (f" Halted: {d['halted']}." if d["halted"] else ""))
    if plan.get("final_rows"):
        out += ["", "| Ticker | Gap | PM high | PM RVOL | Boxes | Catalyst (auto) |", "|---|---|---|---|---|---|"]
        for t, r in plan["final_rows"].items():
            c = d["catalyst"].get(t, {})
            rv = "-" if r.get("pm_rvol") is None else f"{r['pm_rvol']:.1f}"
            out.append(f"| {t} | {r['gap'] * 100:+.1f}% | {r['pmh']:.2f} | {rv} | {r['box_count']}/8 | "
                       f"{c.get('type', '-')}: {c.get('headline', '')[:80]} |")
    out += ["", "**Trades**"]
    if not touched:
        out.append("- none")
    for t in touched:
        sim = sims.get(t["id"], {})
        r = (t["pnl"] / t["risk_actual"]) if t.get("pnl") is not None and t.get("risk_actual") else None
        out.append(f"- {t['id']} ({t['grade']}): {t['qty']} @ {t['fill']:.2f}, stop {t['stop0']} -> {t['stop_now']}, "
                   f"risk ${t.get('risk_actual', 0):.0f}; "
                   + (f"P&L ${t['pnl']:+.2f} ({r:+.2f}R), exit {t.get('exit_reason')} ({t.get('exit_why', '')})"
                      if t.get("pnl") is not None else "OPEN (carried)" if t["status"] == "open" else "closed, fills missing")
                   + "".join(f"; sim {v} {x['r']:+.2f}R" for v, x in sim.items()))
    if d["skipped"]:
        out += ["", "**Setups not taken**"] + [f"- {k}: {v['why']}" for k, v in d["skipped"].items()]
    closed = [t for t in bot.book["trades"].values() if t["status"] == "closed" and t.get("pnl") is not None
              and t.get("risk_actual")]
    if closed:
        rs = [t["pnl"] / t["risk_actual"] for t in closed]
        out += ["", f"**Test so far:** {len(rs)}/{30} closed trades, expectancy {sum(rs) / len(rs):+.2f}R, "
                f"win {sum(r > 0 for r in rs) / len(rs) * 100:.0f}%, net ${sum(t['pnl'] for t in closed):+,.2f}."]
    out.append(f"\nOrders sent today: {d['orders']}. Full log: events.jsonl.")
    return "\n".join(out)

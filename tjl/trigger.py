"""Trigger check ("TJ trigger <ticker>"): 5m chart checks, version choice, Liquid order plan, Notion rows.

Levels come from Webull (real exchange data). Liquid prices are mapped by percent distance from the
Webull entry reference, so the stop % and R multiples are the same on Liquid's perp.
"""
import datetime as dt

from . import config as C
from . import sessions
from .indicators import ema_series, vwap_series
from .sizing import floor_qty, hl_price, size
from .webull import ET, minutes_et

PARTIALS = {"A": [(1.0, 1 / 3), (2.0, 1 / 3)], "B": [(0.75, 1 / 3)]}
TRAIL = {"A": "21-EMA 5m", "B": "Swing low 5m"}


def window_label(mins):
    if mins < 11 * 60:
        return "10:00-11:00"
    if mins < 14 * 60:
        return "11:00-14:00"
    return "14:00-15:30"


def chart(bars, day, now_min):
    """Today's 5m state up to now. The last bar may be in progress."""
    today = [b for b in bars if b["date"] == day and minutes_et(b["t"]) < now_min]
    pre = [b for b in today if b["session"] == "PRE"]
    rth = [b for b in today if b["session"] == "RTH"]
    if not rth:
        raise ValueError(f"no RTH bars for {day} before {now_min // 60}:{now_min % 60:02d}")
    done = [b for b in today if minutes_et(b["t"]) + 5 <= now_min]   # completed bars
    rth_done = [b for b in done if b["session"] == "RTH"]
    closes = [b["close"] for b in done]
    e8, e21 = ema_series(closes, 8), ema_series(closes, 21)
    vw = vwap_series(rth_done)[-1] if rth_done else None
    last_done = done[-1]
    cur = today[-1]
    hod_before = max(b["high"] for b in rth[:-1]) if len(rth) > 1 else None
    return {"pmh": max(b["high"] for b in pre) if pre else None, "hod_before": hod_before,
            "hod": max(b["high"] for b in rth), "lod": min(b["low"] for b in rth),
            "last": cur["close"], "cur_high": cur["high"], "last_done_close": last_done["close"],
            "last_done_time": last_done["t"].strftime("%H:%M"), "vwap": vw, "ema8": e8[-1], "ema21": e21[-1],
            "rth_vol": sum(b["volume"] for b in rth)}


def intraday_rvol(hist, day, now_min, today_vol):
    days = sorted({b["date"] for b in hist if b["date"] < day and b["session"] == "RTH"})[-C.RVOL_LOOKBACK:]
    if not days:
        return None, 0
    vols = [sum(b["volume"] for b in hist if b["date"] == d and b["session"] == "RTH" and minutes_et(b["t"]) < now_min)
            for d in days]
    avg = sum(vols) / len(vols)
    return (today_vol / avg if avg else None), len(days)


def choose(eligible, prev_version):
    """Real version: the only eligible one, or alternate when both are. Shadow: the other when both are."""
    if not eligible:
        return None, None
    if len(eligible) == 1:
        return eligible[0], None
    real = "B" if prev_version == "A" else "A"
    return real, ("A" if real == "B" else "B")


def leg_plan(v, entry_ref, stop_ref, lp, risk, sz_dec, max_lev):
    stop_pct = (entry_ref - stop_ref) / entry_ref
    liq_stop = hl_price(lp * (1 - stop_pct), sz_dec)
    sz = size(lp, liq_stop, risk, max_lev)
    qty = floor_qty(sz["notional"] / lp, sz_dec)
    parts = []
    for r_mult, frac in PARTIALS[v]:
        parts.append({"r": r_mult, "price": hl_price(lp * (1 + r_mult * stop_pct), sz_dec),
                      "quantity": floor_qty(qty * frac, sz_dec)})
    return {**sz, "version": v, "webull_stop": round(stop_ref, 4), "stop_pct": round(stop_pct * 100, 2),
            "liquid_entry_ref": lp, "liquid_stop": liq_stop, "one_r_liquid": round(lp - liq_stop, 4),
            "quantity": qty, "partials": parts, "breakeven_at": hl_price(lp * (1 + stop_pct), sz_dec)}


def run(ticker, ms, bars5, hist5, liquid_price, now=None, day_pnl=0.0, trades_today=0, prev_version=None,
        catalyst=False, catalyst_text="", catalyst_type="None", sz_decimals=2, max_lev=10):
    r = ms["all_rows"].get(ticker)
    if r is None:
        raise SystemExit(f"{ticker} is not in the morning list ({', '.join(ms['all_rows'])})")
    bars = bars5[ticker]
    day = dt.date.fromisoformat(ms["date"])
    if now:
        hh, mm = map(int, now.split(":"))
        now_min = hh * 60 + mm
    else:
        now_min = minutes_et([b for b in bars if b["date"] == day][-1]["t"]) + 5
    ch = chart(bars, day, now_min)
    pmh = ch["pmh"] or r["pmh"]
    level = max(pmh, ch["hod_before"] or 0)
    rvol_b, rvol_days = intraday_rvol(hist5.get(ticker, []), day, now_min, ch["rth_vol"]) if hist5 else (None, 0)

    blocks = []
    if not sessions.is_trading_day(day) or sessions.is_half_day(day):
        blocks.append(f"{day} is a {sessions.day_status(day)}")
    if trades_today >= C.MAX_TRADES_PER_DAY:
        blocks.append("2 trades already today")
    if day_pnl <= C.DAILY_LOSS_LIMIT:
        blocks.append(f"daily loss limit hit ({day_pnl:+.0f})")
    if not r["core"]:
        blocks.append("failed the morning rules: " + ", ".join(k for k, v in r["checks"].items() if not v))
    broke = ch["cur_high"] > level
    holds = ch["last"] > level
    if not holds:
        blocks.append(f"price {ch['last']:.2f} not above the trigger {level:.2f} (PMH {pmh:.2f}, HOD {ch['hod_before'] or 0:.2f})")
    if now_min >= C.FLAT_BY:
        blocks.append("after 15:51")

    conds = {
        "A": {"window 10:00-15:30": C.WINDOW["A"][0] <= now_min <= C.WINDOW["A"][1],
              f"PM RVOL > {C.RVOL_A}": bool(r["a_rvol_ok"])},
        "B": {"window 10:05-15:30": C.WINDOW["B"][0] <= now_min <= C.WINDOW["B"][1],
              f"RVOL >= {C.RVOL_B} (14d, same time)": rvol_b is not None and rvol_b >= C.RVOL_B},
    }
    eligible = [v for v in ("A", "B") if all(conds[v].values())] if not blocks else []

    boxes = dict(r["boxes"])
    boxes = {int(k): v for k, v in boxes.items()}
    boxes[6] = catalyst
    grade = "A+" if all(boxes.values()) else "Normal"
    if grade != "A+" and not ms["spy"]["above200"]:
        blocks.append("SPY below 200d and the grade isn't A+")
        eligible = []
    risk = C.RISK_APLUS if grade == "A+" else C.RISK_NORMAL
    real, shadow_v = choose(eligible, prev_version)

    stops = {"A": min(pmh * 0.99, ch["lod"]), "B": ch["lod"] * 0.99}
    legs = {}
    for v in ("A", "B"):   # both computed, so either version can be simulated later
        if stops[v] < ch["last"]:
            legs[v] = leg_plan(v, ch["last"], stops[v], liquid_price, risk, sz_decimals, max_lev)

    st = {"kind": "trigger", "date": ms["date"], "time_et": f"{now_min // 60:02d}:{now_min % 60:02d}",
          "ticker": ticker, "liquid": r["liquid"], "group": r["group"], "chart": ch, "pmh": pmh,
          "trigger_level": level, "broke": broke, "holds": holds,
          "confirm_5m": bool(ch["vwap"] and ch["ema8"] and ch["last_done_close"] > ch["vwap"]
                             and ch["last_done_close"] > ch["ema8"]),
          "rvol_b": rvol_b, "rvol_days": rvol_days, "pm_rvol": r["pm_rvol"], "conditions": conds,
          "blocks": blocks, "eligible": eligible, "real": real, "shadow": shadow_v, "grade": grade,
          "boxes": boxes, "risk": risk, "legs": legs, "spy_state": ms["spy"]["state"],
          "catalyst": catalyst_text, "catalyst_type": catalyst_type, "gap": r["gap"],
          "row": {k: r.get(k) for k in ("adr20", "ext20", "pos52", "prior_close", "pdh", "pm_vol")}}
    st["orders"] = orders(st) if real else []
    st["notion"] = notion_rows(st)
    return st


def orders(st):
    leg = st["legs"][st["real"]]
    sym = st["liquid"]
    why = f"TJL {C.VERSION_NAME[st['real']]} {st['grade']} paper: break of {st['trigger_level']:.2f}"
    out = [{"step": "1 entry + stop (suggest_order, then execute_order)",
            "suggest_order": {"asset": sym, "side": "long", "orderType": "market", "size": leg["notional"],
                              "leverage": leg["leverage"], "stopLoss": leg["liquid_stop"],
                              "markPrice": leg["liquid_entry_ref"], "reasoning": why}}]
    for i, p in enumerate(leg["partials"], 1):
        out.append({"step": f"{i + 1} partial {i}: reduce-only limit sell at +{p['r']}R",
                    "execute_order": {"symbol": sym, "side": "sell", "type": "limit", "price": p["price"],
                                      "quantity": p["quantity"], "reduceOnly": True, "timeInForce": "gtc",
                                      "reasoning": f"TJL partial {i} at +{p['r']}R"}})
    return out


def _et_iso(day, hhmm):
    t = dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=ET)
    return t.isoformat()


def _r1(x, d=2):
    return None if x is None else round(x, d)


def notion_rows(st):
    rows = []
    for v, status in ((st["real"], "Planned"), (st["shadow"], "Shadow")):
        if not v:
            continue
        leg = st["legs"][v]
        props = {
            "Trade": f"{st['date']} {st['ticker']} {v}" + (" (shadow)" if status == "Shadow" else ""),
            "date:Date:start": st["date"], "date:Date:is_datetime": 0,
            "Ticker": st["ticker"], "Status": status, "Version": C.VERSION_NAME[v], "Grade": st["grade"],
            "A+ boxes": [C.BOX_NAMES[k] for k, ok in sorted(st["boxes"].items()) if ok],
            "Sector": st["group"], "Catalyst": st["catalyst"], "Catalyst type": st["catalyst_type"],
            "SPY regime": st["spy_state"], "Gap %": _r1(st["gap"] * 100),
            "Premarket RVOL": _r1(st["pm_rvol"]), "ADR20 %": _r1((st["row"]["adr20"] or 0) * 100),
            "Extension vs 20d SMA %": _r1((st["row"]["ext20"] or 0) * 100),
            "52w range position %": _r1((st["row"]["pos52"] or 0) * 100, 0),
            "Premarket high": _r1(st["pmh"], 4), "Trigger price": _r1(st["trigger_level"], 4),
            "5m confirm (VWAP + 8 EMA)": "__YES__" if st["confirm_5m"] else "__NO__",
            "date:Entry time:start": _et_iso(st["date"], st["time_et"]), "date:Entry time:is_datetime": 1,
            "Entry window": window_label(int(st["time_et"][:2]) * 60 + int(st["time_et"][3:])),
            "Entry price": leg["liquid_entry_ref"], "Stop price": leg["liquid_stop"], "Stop %": leg["stop_pct"],
            "Risk $": leg["risk"], "Position $": leg["notional"], "Leverage": leg["leverage"],
            "Margin $": leg["margin"], "Trail method": TRAIL[v],
            "Partial 1 price": leg["partials"][0]["price"],
            "Partial 2 price": leg["partials"][1]["price"] if len(leg["partials"]) > 1 else None,
            "Notes": (f"Webull entry ref {st['chart']['last']:.2f}, Webull stop {leg['webull_stop']:.2f}; "
                      f"RVOL B {st['rvol_b'] and round(st['rvol_b'], 2)}; "
                      + ("shadow: result simulated from Webull 5m bars after the close" if status == "Shadow"
                         else "entry price = Liquid mark at trigger; replace with the fill")),
        }
        rows.append({k: val for k, val in props.items() if val is not None})
    return rows


def report(st):
    ch = st["chart"]
    out = [f"## TJ trigger {st['ticker']} ({st['liquid']}) at {st['time_et']} ET, {st['date']}", "",
           f"Last {ch['last']:.2f} vs trigger {st['trigger_level']:.2f} (PMH {st['pmh']:.2f}, HOD before this bar "
           f"{ch['hod_before'] or 0:.2f}); LOD {ch['lod']:.2f}. Broke: {'yes' if st['broke'] else 'no'}, holds: "
           f"{'yes' if st['holds'] else 'no'}.",
           f"5m (last completed bar {ch['last_done_time']}): close {ch['last_done_close']:.2f}, VWAP "
           f"{(ch['vwap'] or 0):.2f}, 8 EMA {(ch['ema8'] or 0):.2f}, 21 EMA {(ch['ema21'] or 0):.2f} -> "
           f"video 5 confirm: {'yes' if st['confirm_5m'] else 'no'} (logged, not required).",
           f"RVOL: premarket {st['pm_rvol'] and round(st['pm_rvol'], 2)}, intraday {st['rvol_b'] and round(st['rvol_b'], 2)} "
           f"({st['rvol_days']} days)."]
    for v in ("A", "B"):
        c = ", ".join(f"{k} {'ok' if ok else 'NO'}" for k, ok in st["conditions"][v].items())
        out.append(f"- {C.VERSION_NAME[v]}: {c}")
    if st["blocks"]:
        out += ["", "**NO TRADE:** " + "; ".join(st["blocks"])]
    if not st["real"]:
        if not st["blocks"]:
            out += ["", "**NO TRADE:** neither version's conditions pass."]
        out.append("Log it in Notion as Skipped (rule said no) or Missed (rules said yes, not taken).")
        return "\n".join(out)
    out += ["", f"**Trade: {C.VERSION_NAME[st['real']]}, grade {st['grade']}**"
            + (f"; shadow {C.VERSION_NAME[st['shadow']]}" if st["shadow"] else "")]
    for v, leg in ((v, st["legs"][v]) for v in (st["real"], st["shadow"]) if v):
        parts = ", ".join(f"{p['quantity']} at {p['price']} (+{p['r']}R)" for p in leg["partials"])
        out.append(f"- {v}{' (shadow)' if v == st['shadow'] else ''}: Liquid entry ~{leg['liquid_entry_ref']}, stop "
                   f"{leg['liquid_stop']} ({leg['stop_pct']}%), 1R {leg['one_r_liquid']}, ${leg['notional']:,.0f} at "
                   f"{leg['leverage']}x (margin ${leg['margin']:,.0f}), qty {leg['quantity']}, risk ${leg['risk']:.0f}"
                   f"{' (capped)' if leg['capped'] else ''}; partials {parts}")
    out += ["", "Orders for approval (paper):"]
    for o in st["orders"]:
        out.append(f"{o['step']}: `{o.get('suggest_order') or o.get('execute_order')}`")
    if st["real"] == "A":
        out.append("Management A: after both partials, exit the last third on a 5m close below the 21 EMA; flat by 15:51.")
    else:
        out.append(f"Management B: at +1R ({st['legs']['B']['breakeven_at']}) stop to breakeven, then trail under "
                   "5m swing lows (2 bars each side); flat by 15:51.")
    return "\n".join(out)

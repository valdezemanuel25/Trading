"""Trade management check ("TJ check <ticker>"): what the rules say to do with an open position now.

A: 1/3 at +1R and 1/3 at +2R rest as reduce-only limits; once both filled, exit the last third on a 5m close
   below the 21 EMA. B: 1/3 at +0.75R; stop to breakeven once +1R is reached; then trail the stop under
   confirmed 5m swing lows (2 bars each side).
Overnight (user allowed 2026-11-26; Claude's default rule): at the 15:45 check the rest of the position is
carried if it is in profit and the last 5m close is above the 21 EMA; the stop then goes to at least breakeven.
Otherwise flat by 15:51. On later days the same management runs on that day's bars (A: exit on a 5m close
below the 21 EMA; B: trail under swing lows) and the 15:45 check repeats.
Levels are found on Webull 5m bars and mapped to Liquid by percent from the entry (same as the trigger).
The output is a proposal; every stop move or close needs the user's approval in chat.
"""
import datetime as dt

from . import config as C
from .indicators import ema_series
from .sizing import hl_price
from .webull import minutes_et


def _confirmed_swing_lows(bars):
    out = []
    for j in range(2, len(bars) - 2):
        lo = bars[j]["low"]
        if all(lo < bars[j - q]["low"] for q in (1, 2)) and all(lo <= bars[j + q]["low"] for q in (1, 2)):
            out.append(j)
    return out


def run(trade, bars5, now, position_qty, current_stop, liquid_price, fill_price=None, sz_decimals=2, today=None):
    v = trade["real"]
    leg = trade["legs"][v]
    entry_day = dt.date.fromisoformat(trade["date"])
    day = dt.date.fromisoformat(today) if isinstance(today, str) else (today or entry_day)
    carried = day > entry_day
    hh, mm = map(int, now.split(":"))
    now_min = hh * 60 + mm
    eh, em = map(int, trade["time_et"].split(":"))
    entry_min = eh * 60 + em
    bars = [b for b in bars5[trade["ticker"]] if b["date"] == day]
    done = [b for b in bars if minutes_et(b["t"]) + 5 <= now_min]
    after = [b for b in done if b["session"] == "RTH" and (carried or minutes_et(b["t"]) >= entry_min - 5)]
    e21 = ema_series([b["close"] for b in done], 21)

    entry_w, stop_w = trade["chart"]["last"], leg["webull_stop"]
    one_r_w = entry_w - stop_w
    liq_entry = fill_price or leg["liquid_entry_ref"]
    to_liq = lambda px: hl_price(liq_entry * px / entry_w, sz_decimals)   # noqa: E731
    last_w = done[-1]["close"] if done else entry_w
    hi_w = max((b["high"] for b in after), default=entry_w)
    r_now = (liquid_price - liq_entry) / (liq_entry - leg["liquid_stop"])
    qty0 = leg["quantity"]
    thirds_left = round(position_qty / (qty0 / 3)) if qty0 else 0

    actions, notes = [], []
    above21 = bool(e21 and e21[-1] and done and done[-1]["close"] >= e21[-1])
    if position_qty <= 0:
        actions.append({"do": "nothing open", "why": "position is flat (stop or targets filled); run the close-out"})
    elif now_min >= C.CARRY_CHECK:
        if r_now > 0 and above21:
            be = hl_price(liq_entry, sz_decimals)
            if current_stop < be:
                actions.append({"do": "move stop", "to": be, "why": "carry overnight (in profit, above the 21 EMA): stop to breakeven"})
            notes.append(f"Overnight: CARRY ({r_now:+.2f}R, 5m close {done[-1]['close']:.2f} >= 21 EMA {e21[-1]:.2f}). "
                         "Check funding with analyze_market; tick 'Held overnight' in Notion.")
        else:
            why = "not in profit" if r_now <= 0 else "below the 21 EMA"
            actions.append({"do": "close", "why": f"15:45 overnight check failed ({why}): flat by 15:51"})
    elif v == "A":
        partials_done = thirds_left <= 1 or carried
        if partials_done and e21[-1] and done[-1]["close"] < e21[-1]:
            actions.append({"do": "close", "why": f"{'carried position' if carried else 'both partials filled'} and the "
                                                  f"{done[-1]['t']:%H:%M} 5m close {done[-1]['close']:.2f} is below the 21 EMA {e21[-1]:.2f}"})
        else:
            notes.append(f"A: {3 - thirds_left} of 3 thirds sold; 21 EMA {e21[-1]:.2f} (exit trigger only after both partials)"
                         if e21[-1] else "A: 21 EMA not ready")
    else:   # B
        reached_1r = carried or hi_w >= entry_w + one_r_w
        new_stop = current_stop
        why = None
        if reached_1r and current_stop < liq_entry:
            new_stop, why = hl_price(liq_entry, sz_decimals), "+1R reached: stop to breakeven"
        if reached_1r:
            lows = [after[j]["low"] for j in _confirmed_swing_lows(after)]
            if lows:
                trail = to_liq(lows[-1])
                if trail > max(new_stop, current_stop) and trail < liquid_price:
                    new_stop, why = trail, f"trail under the last confirmed 5m swing low {lows[-1]:.2f} (Webull)"
        if why:
            actions.append({"do": "move stop", "to": new_stop, "why": why})
        else:
            notes.append("B: +1R not reached yet; stop unchanged" if not reached_1r else "B: no higher swing low yet")

    sym = trade["liquid"]
    for a in actions:
        if a["do"] == "move stop":
            a["modify_position"] = {"asset": sym, "action": "modify_tpsl", "positionSide": "long",
                                    "positionSize": position_qty, "stopLoss": a["to"], "currentPrice": liquid_price,
                                    "reasoning": f"TJL {v}: {a['why']}"}
        elif a["do"] == "close":
            a["close_position"] = {"symbol": sym, "reasoning": f"TJL {v}: {a['why']}"}
    return {"kind": "check", "date": day.isoformat(), "carried": carried, "time_et": now, "ticker": trade["ticker"], "version": v,
            "liquid": sym, "r_now": r_now, "last_webull": last_w, "high_since_entry": hi_w,
            "position_qty": position_qty, "thirds_left": thirds_left, "current_stop": current_stop,
            "actions": actions, "notes": notes,
            "mfe_r_so_far": (hi_w - entry_w) / one_r_w,
            "mae_r_so_far": (min((b["low"] for b in after), default=entry_w) - entry_w) / one_r_w}


def report(st):
    out = [f"## TJ check {st['ticker']} ({st['liquid']}) at {st['time_et']} ET, version {st['version']}",
           f"Now {st['r_now']:+.2f}R on Liquid; best so far {st['mfe_r_so_far']:+.2f}R, worst {st['mae_r_so_far']:+.2f}R. "
           f"Position {st['position_qty']} ({st['thirds_left']} of 3 thirds left), stop {st['current_stop']}."]
    out += [f"- {n}" for n in st["notes"]]
    if not st["actions"]:
        out.append("**Action: hold.** Nothing to change.")
    for a in st["actions"]:
        call = a.get("modify_position") or a.get("close_position")
        out.append(f"**Action: {a['do']}{' to ' + str(a['to']) if 'to' in a else ''}** ({a['why']}). "
                   f"For approval: `{call}`" if call else f"**{a['do']}**: {a['why']}")
    return "\n".join(out)

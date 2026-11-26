"""Simulate a version's exits on the day's 5m bars (shadow rows, and MFE/MAE for real trades).

Conventions (conservative): entry at the Webull reference price at the trigger time; simulation starts
with the next 5m bar; inside a bar the stop is checked before targets; flat at the open of the 15:50 bar.
A: 1/3 at +1R, 1/3 at +2R; the last third exits on a 5m close below the 21 EMA once both partials are
done (stop only before that). B: 1/3 at +0.75R; stop to breakeven at +1R; then trail under confirmed
5m swing lows (2 bars each side). Fees: 0.15% of notional estimated round trip.
"""
from . import config as C
from .indicators import ema_series
from .webull import minutes_et


def simulate(bars, day, entry_min, entry, stop, version):
    day_bars = [b for b in bars if b["date"] == day]
    closes = [b["close"] for b in day_bars]
    e21 = ema_series(closes, 21)
    one_r = entry - stop
    legs = [1 / 3, 1 / 3, 1 / 3]
    open_ = [True, True, True]
    exits = []
    cur_stop = stop
    be = False
    mfe = mae = 0.0
    idx = [i for i, b in enumerate(day_bars) if b["session"] == "RTH" and minutes_et(b["t"]) >= entry_min]
    for i in idx:
        b = day_bars[i]
        if minutes_et(b["t"]) >= C.FLAT_BY - 1:   # 15:50 bar
            for k in range(3):
                if open_[k]:
                    open_[k] = False
                    exits.append((k, b["open"], "Time 3:51", b["t"]))
            break
        mfe = max(mfe, (b["high"] - entry) / one_r)
        mae = min(mae, (b["low"] - entry) / one_r)
        if b["low"] <= cur_stop:
            reason = "Stop" if cur_stop < entry else ("Breakeven" if cur_stop == entry else "Trail")
            for k in range(3):
                if open_[k]:
                    open_[k] = False
                    exits.append((k, cur_stop, reason, b["t"]))
            break
        targets = [(0, 1.0), (1, 2.0)] if version == "A" else [(0, 0.75)]
        for k, rm in targets:
            if open_[k] and b["high"] >= entry + rm * one_r:
                open_[k] = False
                exits.append((k, entry + rm * one_r, f"Partial +{rm}R", b["t"]))
        if version == "A":
            if not open_[0] and not open_[1] and open_[2] and e21[i] and b["close"] < e21[i]:
                open_[2] = False
                exits.append((2, b["close"], "Trail", b["t"]))
        else:
            if not be and b["high"] >= entry + one_r:
                be = True
                cur_stop = max(cur_stop, entry)
            if be and i - 2 > idx[0]:
                j = i - 2   # bar j is a confirmed swing low once bars j+1, j+2 exist
                if all(day_bars[j]["low"] < day_bars[j - q]["low"] for q in (1, 2)) and \
                   all(day_bars[j]["low"] <= day_bars[j + q]["low"] for q in (1, 2)):
                    cur_stop = max(cur_stop, day_bars[j]["low"])
        if not any(open_):
            break
    if any(open_):   # data ended before 15:50
        last = day_bars[-1]
        for k in range(3):
            if open_[k]:
                exits.append((k, last["close"], "End of data", last["t"]))
    r_gross = sum(legs[k] * (px - entry) / one_r for k, px, _, _ in exits)
    final = max(exits, key=lambda e: e[3])
    return {"r_gross": r_gross, "mfe_r": mfe, "mae_r": mae, "exits": exits, "final_price": final[1],
            "final_reason": final[2], "final_time": final[3]}


def run(trade, bars5, version=None):
    import datetime as dt
    v = version or trade.get("shadow") or trade["real"]
    leg = trade["legs"][v]
    day = dt.date.fromisoformat(trade["date"])
    hh, mm = map(int, trade["time_et"].split(":"))
    entry = trade["chart"]["last"]
    stop = leg["webull_stop"]
    sim = simulate(bars5[trade["ticker"]], day, hh * 60 + mm, entry, stop, v)
    fee_r = C.FEE_ROUND_TRIP_EST / ((entry - stop) / entry)
    risk = leg["risk"]
    out = {"kind": "shadow", "date": trade["date"], "ticker": trade["ticker"], "version": v, "entry": entry,
           "stop": stop, "risk": risk, **sim, "fee_r": fee_r, "r_net": sim["r_gross"] - fee_r}
    out["pnl"] = round(out["r_net"] * risk, 2)
    reason = sim["final_reason"]
    out["notion_update"] = {
        "Status": "Shadow" if v == trade.get("shadow") else "Closed",
        "Final exit price": round(sim["final_price"], 4),
        "date:Exit time:start": sim["final_time"].isoformat(), "date:Exit time:is_datetime": 1,
        "Exit reason": reason if reason in ("Stop", "Breakeven", "Trail", "Time 3:51") else "Manual",
        "MFE R": round(sim["mfe_r"], 2), "MAE R": round(sim["mae_r"], 2),
        "Fees $": round(fee_r * risk, 2), "P&L $": out["pnl"],
    }
    return out


def report(st):
    out = [f"## Shadow {st['ticker']} version {st['version']} ({st['date']})",
           f"Entry {st['entry']:.2f}, stop {st['stop']:.2f}. Result {st['r_gross']:+.2f}R gross, "
           f"{st['r_net']:+.2f}R net of est. fees, ${st['pnl']:+.2f}. MFE {st['mfe_r']:+.2f}R, MAE {st['mae_r']:+.2f}R.",
           "Exits:"]
    for k, px, why, t in sorted(st["exits"], key=lambda e: e[3]):
        out.append(f"- third {k + 1}: {px:.2f} ({why}) at {t.strftime('%H:%M')}")
    return "\n".join(out)

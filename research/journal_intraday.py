#!/usr/bin/env python3
"""Step 3: backtest the journal's two reversal setups (docs/intraday-rules.md) on ES 1-minute data.

  python3 research/journal_intraday.py

Setups:
  A (short): a 5m candle's high trades >= 0.25 pt above a level L, coming from below (previous 5m close < L);
     that candle or the next closes back below L.
  B (long): the mirror image at the lows.
Levels (fixed before the open): ON = overnight high/low 18:00-9:30 ET, PD = previous RTH high/low,
PW = previous week's RTH high/low.

Fill models:
  I  ideal: entry at the confirming 5m close (what the journal does by hand).
  H  hourly agent: wakes at 9:45 and 10:45 ET see setups confirmed since the last wake; the fill is the 1m close
     5 minutes after the wake (approval delay). It only enters if the stop and target haven't been hit yet and
     price is below the stop and not past halfway to the target (mirror for longs).
  R  resting limit: at 9:29 ET a sell limit at the nearest selected high >= 3 pts above price and a buy limit at the
     nearest selected low >= 3 pts below. Fixed stop 8 pts and target 10 pts from the limit. Fills when price trades
     0.25 pt through the limit, 9:30-10:59 ET.
Exits: stop or target on 1m bars (a minute that touches both counts as the stop), else the 12:45 ET close.
Daily rules (I and H): one position at a time, at most 2 trades, stop for the day at -$100, no opposite side after a
loss. Days with a gap > 1% at the open, and roll days (front contract changes), are skipped.
P&L: risk $50 per trade at the stop, so $ = 50 * (pts - cost) / risk. Costs: CME ES 0.6 pts round trip;
Liquid 0.10% of price round trip (the cost the RSI(2) research uses for Liquid).
Settings are picked on 2020-23 (Liquid cost, I model, at least 30 trades), then shown for 2024-25 and the 2026
holdout.
"""
import itertools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backtest"))
from data import load_1m  # noqa: E402

RISK_USD, CME_COST, LIQ_COST = 50.0, 0.6, 0.001
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2024-25": ("2024-01-01", "2026-01-01"),
           "2026": ("2026-01-01", "2026-10-29")}
LEVELS = {"ON": ["on"], "PD": ["pd"], "PW": ["pw"], "ON+PD": ["on", "pd"], "all": ["on", "pd", "pw"]}


def mins(ts):
    return ts.hour * 60 + ts.minute


def prepare(m1):
    m1 = m1.copy()
    m1["tday"] = (m1.index + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    m1["mod"] = m1.index.hour * 60 + m1.index.minute
    days = []
    prev = None
    week_hi = {}
    for tday, d in m1.groupby("tday", sort=True):
        if d.index[0].weekday() == 5:
            continue
        rth = d[(d["mod"] >= 570) & (d["mod"] < 960)]
        # overnight = everything in this trading day before 9:30 ET on the session date
        sess_date = tday
        on = d[(d.index.tz_localize(None) < sess_date + pd.Timedelta(hours=9, minutes=30))]
        if len(rth) < 300 or len(on) < 30:
            prev = None
            continue
        sym = rth["symbol"].iloc[0]
        info = dict(tday=tday, sym=sym, rth=rth, on_h=on["high"].max(), on_l=on["low"].min(),
                    pre_px=on["close"].iloc[-1], rth_h=rth["high"].max(), rth_l=rth["low"].min(),
                    rth_c=rth["close"].iloc[-1], week=tday.isocalendar()[:2])
        if prev is not None and prev["sym"] == sym:
            info["pd_h"], info["pd_l"], info["prev_c"] = prev["rth_h"], prev["rth_l"], prev["rth_c"]
            pw = week_hi.get(_prev_week(info["week"]))
            info["pw_h"], info["pw_l"] = (pw[0], pw[1]) if pw and pw[2] == sym else (np.nan, np.nan)
            days.append(info)
        wk = week_hi.get(info["week"])
        if wk is None or wk[2] != sym:
            week_hi[info["week"]] = [info["rth_h"], info["rth_l"], sym]
        else:
            wk[0], wk[1] = max(wk[0], info["rth_h"]), min(wk[1], info["rth_l"])
        prev = info
    return days


def _prev_week(w):
    y, n = w
    d = pd.Timestamp.fromisocalendar(y, n, 1) - pd.Timedelta(days=7)
    return d.isocalendar()[:2]


def day_arrays(day):
    if "_arr" in day:
        return day["_arr"]
    r = day["rth"]
    tp = (r["high"] + r["low"] + r["close"]) / 3
    vwap = (tp * r["volume"]).cumsum() / r["volume"].cumsum().replace(0, np.nan)
    b5 = r[["open", "high", "low", "close"]].resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    day["_arr"] = (r, vwap, b5)
    return day["_arr"]


def levels_for(day, keys, side):
    out = []
    for k in keys:
        v = day.get(f"{k}_{'h' if side < 0 else 'l'}", np.nan)
        if not np.isnan(v):
            out.append(v)
    return out


def setups(day, r, vwap, b5, keys, vwap_filter, target_mode):
    """Signals: dict(side, conf_min (minute label of the 1m bar whose close is the entry), entry, stop, target)."""
    sig = []
    idx = list(b5.index)
    for side in (-1, 1):
        for L in levels_for(day, keys, side):
            for j in range(1, len(idx)):
                t = idx[j]
                if mins(t) > 10 * 60 + 55:
                    break
                bj, bp = b5.iloc[j], b5.iloc[j - 1]
                swept = (bj["high"] >= L + 0.25 and bp["close"] < L) if side < 0 else \
                        (bj["low"] <= L - 0.25 and bp["close"] > L)
                if not swept:
                    continue
                for k in (j, j + 1):
                    if k >= len(idx):
                        break
                    tk = idx[k]
                    if mins(tk) < 9 * 60 + 35 or mins(tk) > 10 * 60 + 55:
                        break
                    bk = b5.iloc[k]
                    if (bk["close"] < L) if side < 0 else (bk["close"] > L):
                        conf = tk + pd.Timedelta(minutes=4)
                        entry = bk["close"]
                        ext = b5["high"].iloc[j:k + 1].max() if side < 0 else b5["low"].iloc[j:k + 1].min()
                        risk = max(abs(ext - entry) + 1.0, 6.0)
                        if risk > 12:
                            break
                        vw = vwap.get(conf, np.nan)
                        if vwap_filter and not ((L > vw) if side < 0 else (L < vw)):
                            break
                        stop = entry - side * risk
                        if target_mode == "vwap":
                            dist = (entry - vw) * -side
                            if not (dist >= risk):
                                break
                            target = vw
                        else:
                            target = entry + side * 1.25 * risk
                        sig.append(dict(side=side, conf=conf, entry=entry, stop=stop, target=target, level=L))
                        break
                break  # first sweep of each level only
    return sorted(sig, key=lambda s: s["conf"])


def simulate(r, side, start_min_label, entry, stop, target, check_first=True):
    """Walk 1m bars after start_min_label. Returns (exit_price, exit_label, result)."""
    after = r[r.index > start_min_label]
    for t, b in after.iterrows():
        if mins(t) > 12 * 60 + 45:
            break
        hit_s = b["high"] >= stop if side < 0 else b["low"] <= stop
        hit_t = b["low"] <= target if side < 0 else b["high"] >= target
        if hit_s:
            return stop, t, "stop"
        if hit_t:
            return target, t, "target"
    last = r[r.index <= r.index[0].normalize() + pd.Timedelta(hours=12, minutes=45)]
    return last["close"].iloc[-1], last.index[-1], "time"


def run_day(day, keys, vwap_filter, target_mode, model):
    r, vwap, b5 = day_arrays(day)
    trades = []
    if model == "R":
        p = day["pre_px"]
        for side in (-1, 1):
            lv = [L for L in levels_for(day, keys, side) if (L - p) * -side >= 3]
            if not lv:
                continue
            L = min(lv) if side < 0 else max(lv)
            stop, target = L - side * 8, L + side * 10
            win = r[(r["mod"] >= 570) & (r["mod"] < 660)]
            filled = win[(win["high"] >= L + 0.25)] if side < 0 else win[(win["low"] <= L - 0.25)]
            if filled.empty:
                continue
            t0 = filled.index[0]
            b0 = filled.iloc[0]
            if (b0["high"] >= stop) if side < 0 else (b0["low"] <= stop):
                trades.append(dict(time=t0, side=side, entry=L, exit=stop, result="stop", risk=8.0))
                continue
            px, te, res = simulate(r, side, t0, L, stop, target)
            trades.append(dict(time=t0, side=side, entry=L, exit=px, result=res, risk=8.0))
        return trades

    sig = setups(day, r, vwap, b5, keys, vwap_filter, target_mode)
    busy_until, pnl, last_loss_side = None, 0.0, 0
    wakes = [r.index[0].normalize() + pd.Timedelta(hours=h, minutes=45) for h in (9, 10)]
    for s in sig:
        if len(trades) >= 2 or pnl <= -100:
            break
        if last_loss_side and s["side"] != last_loss_side:
            continue
        if model == "I":
            t_in, px_in = s["conf"], s["entry"]
        else:
            w = next((w for w in wakes if w > s["conf"]), None)
            if w is None:
                continue
            t_in = w + pd.Timedelta(minutes=5)
            between = r[(r.index > s["conf"]) & (r.index <= t_in)]
            side = s["side"]
            if between.empty:
                continue
            hit = (between["high"] >= s["stop"]).any() or (between["low"] <= s["target"]).any() if side < 0 else \
                  (between["low"] <= s["stop"]).any() or (between["high"] >= s["target"]).any()
            if hit:
                continue
            px_in = between["close"].iloc[-1]
            half = s["entry"] + side * 0.5 * abs(s["target"] - s["entry"])
            if not ((px_in < s["stop"] and px_in > half) if side < 0 else (px_in > s["stop"] and px_in < half)):
                continue
        if busy_until is not None and t_in <= busy_until:
            continue
        px, te, res = simulate(r, s["side"], t_in, px_in, s["stop"], s["target"])
        risk = abs(px_in - s["stop"])
        tr = dict(time=t_in, side=s["side"], entry=px_in, exit=px, result=res, risk=risk)
        trades.append(tr)
        busy_until = te
        usd = RISK_USD * ((px - px_in) * s["side"] - CME_COST) / risk
        pnl += usd
        if usd < 0:
            last_loss_side = s["side"]
    return trades


def run_all(days, keys, vwap_filter, target_mode, model):
    out = []
    for day in days:
        if abs(day["rth"]["open"].iloc[0] / day["prev_c"] - 1) > 0.01:
            continue
        for t in run_day(day, keys, vwap_filter, target_mode, model):
            t["pts"] = (t["exit"] - t["entry"]) * t["side"]
            out.append(t)
    t = pd.DataFrame(out)
    if t.empty:
        return t
    t["R_cme"] = (t["pts"] - CME_COST) / t["risk"]
    t["R_liq"] = (t["pts"] - LIQ_COST * t["entry"]) / t["risk"]
    return t


def stats(t, a, b, col):
    t = t[(t["time"] >= pd.Timestamp(a, tz="America/New_York")) & (t["time"] < pd.Timestamp(b, tz="America/New_York"))]
    if len(t) < 2:
        return dict(n=len(t), avgR=np.nan, se=np.nan, usd=0.0, win=np.nan)
    return dict(n=len(t), avgR=t[col].mean(), se=t[col].std() / np.sqrt(len(t)), usd=RISK_USD * t[col].sum(),
                win=(t["pts"] > 0).mean())


def fmt(s):
    if not s["n"] or np.isnan(s["avgR"]):
        return f"{s['n']} tr"
    return f"{s['n']} tr, {s['win']:.0%} win, {s['avgR']:+.2f}R ({s['se']:.2f}), ${s['usd']:+,.0f}"


def main():
    m1 = load_1m()
    days = prepare(m1)
    print(f"{len(days)} trading days, {days[0]['tday'].date()} to {days[-1]['tday'].date()}", flush=True)

    grid = []
    for lv, vf, tm in itertools.product(LEVELS, (True, False), ("1.25R", "vwap")):
        t = run_all(days, LEVELS[lv], vf, tm, "I")
        s = stats(t, *PERIODS["2020-23"], "R_liq")
        grid.append(dict(levels=lv, vwap_filter=vf, target=tm, **{k: fmt(stats(t, *v, "R_liq")) for k, v in PERIODS.items()},
                         pick=s["avgR"] if s["n"] >= 30 else -9))
        print(grid[-1], flush=True)
    g = pd.DataFrame(grid).sort_values("pick", ascending=False)
    pd.set_option("display.width", 250)
    print("\nGrid, model I, Liquid cost (cells: trades, win, avg R (se), $ at $50 risk):")
    print(g.drop(columns="pick").to_string(index=False))
    best = g.iloc[0]
    print(f"\nPicked on 2020-23: levels={best.levels} vwap_filter={best.vwap_filter} target={best.target}")

    rows = []
    for model in ("I", "H", "R"):
        t = run_all(days, LEVELS[best.levels], best.vwap_filter, best.target, model)
        for cost in ("R_cme", "R_liq"):
            rows.append(dict(model=model, cost="CME 0.6pt" if cost == "R_cme" else "Liquid 0.10%",
                             **{k: fmt(stats(t, *v, cost)) for k, v in PERIODS.items()}))
        if model == "I":
            for side, name in ((-1, "A short"), (1, "B long")):
                ts = t[t["side"] == side]
                rows.append(dict(model=f"I {name}", cost="CME 0.6pt",
                                 **{k: fmt(stats(ts, *v, "R_cme")) for k, v in PERIODS.items()}))
        t.to_csv(os.path.join(ROOT, "research", "journal", f"trades_{model}.csv"), index=False)
    print("\nPicked settings by fill model:")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Step 3 comparison: long-only failed breakouts (Fail BO L in backtest/strategy.py, variant E) with the same
fill models and exits as research/journal_intraday.py.

  python3 research/journal_fbo.py

I: entry at the signal candle's close (the strategy's own entry), its own stop and target, exits as in
journal_intraday (stop/target on 1m bars, else the 12:45 ET close). H: the same hourly-wake late fill as
journal_intraday, with wakes at :45 from 9:45 to 12:45 ET (Fail BO can fire until 13:00). R isn't possible: the
entry needs the candle-close confirmation.
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backtest"))
sys.path.insert(0, os.path.join(ROOT, "research"))
from data import load_1m  # noqa: E402
from strategy import compute, run, with_params  # noqa: E402
import journal_intraday as J  # noqa: E402


def main():
    m1 = load_1m()
    p = with_params(win_start=1030, win_end=1100, t1_cap=10, be_trigger=4, disabled="1,3,5,6,7,8,9,11,12")
    sig = run(m1, p, compute(m1, p))
    sig = sig[sig["setup"] == "Fail BO L"].copy()
    print(len(sig), "Fail BO L signals")
    m1 = m1.copy()
    m1["mod"] = m1.index.hour * 60 + m1.index.minute
    rows = {"I": [], "H": []}
    for _, s in sig.iterrows():
        conf = s["entry_time"] + pd.Timedelta(minutes=4)
        day = m1[(m1.index.normalize() == conf.normalize()) & (m1["mod"] >= 570) & (m1["mod"] < 960)]
        if J.mins(conf) > 12 * 60 + 40:
            continue
        side, stop, target = 1, s["stop"], s["target"]
        px, te, res = J.simulate(day, side, conf, s["entry"], stop, target)
        rows["I"].append(dict(time=conf, side=1, entry=s["entry"], exit=px, result=res, risk=s["entry"] - stop))
        wakes = [conf.normalize() + pd.Timedelta(hours=h, minutes=45) for h in (9, 10, 11, 12)]
        w = next((w for w in wakes if w > conf), None)
        if w is None:
            continue
        t_in = w + pd.Timedelta(minutes=5)
        between = day[(day.index > conf) & (day.index <= t_in)]
        if between.empty or (between["low"] <= stop).any() or (between["high"] >= target).any():
            continue
        px_in = between["close"].iloc[-1]
        if not (stop < px_in < s["entry"] + 0.5 * (target - s["entry"])):
            continue
        px, te, res = J.simulate(day, side, t_in, px_in, stop, target)
        rows["H"].append(dict(time=t_in, side=1, entry=px_in, exit=px, result=res, risk=px_in - stop))
    out = []
    for model, tr in rows.items():
        t = pd.DataFrame(tr)
        t["pts"] = t["exit"] - t["entry"]
        t["R_cme"] = (t["pts"] - J.CME_COST) / t["risk"]
        t["R_liq"] = (t["pts"] - J.LIQ_COST * t["entry"]) / t["risk"]
        for cost in ("R_cme", "R_liq"):
            out.append(dict(model=model, cost=cost, **{k: J.fmt(J.stats(t, *v, cost)) for k, v in J.PERIODS.items()}))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(out).to_string(index=False))


if __name__ == "__main__":
    main()

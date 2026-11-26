"""Unit tests for the Trend Join Long routines (synthetic data). Run: python3 -m pytest tests/test_tjl.py -q"""
import datetime as dt

import pytest

from tjl import after_close, morning, sessions, shadow, trigger
from tjl.indicators import adr, ema_series, swing_lows, vwap_series
from tjl.sizing import floor_qty, hl_price, size
from tjl.webull import ET

DAY = dt.date(2026, 12, 1)


def daily(closes, rng=0.04, start=dt.date(2025, 1, 1)):
    out = []
    for i, c in enumerate(closes):
        d = start + dt.timedelta(days=i)
        out.append({"t": dt.datetime(d.year, d.month, d.day, tzinfo=ET), "date": d, "open": c,
                    "high": c * (1 + rng / 2), "low": c * (1 - rng / 2), "close": c, "volume": 2e6, "session": ""})
    return out


def m5(day, hhmm, o, h, l, c, v=1000, session="RTH"):
    hh, mm = map(int, hhmm.split(":"))
    return {"t": dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET), "date": day, "open": o, "high": h,
            "low": l, "close": c, "volume": v, "session": session}


def series(day, start, prices, session="RTH", v=1000):
    hh, mm = map(int, start.split(":"))
    out = []
    for i, p in enumerate(prices):
        m = hh * 60 + mm + 5 * i
        lo, hi, c = (p, p, p) if not isinstance(p, tuple) else p
        out.append(m5(day, f"{m // 60}:{m % 60:02d}", c, hi, lo, c, v, session))
    return out


# ---------- sessions ----------
def test_sessions():
    assert not sessions.is_trading_day("2026-11-26")
    assert sessions.is_half_day("2026-11-27")
    assert sessions.next_trading_day("2026-11-25").isoformat() == "2026-11-27"
    assert sessions.next_full_day("2026-11-25").isoformat() == "2026-11-30"
    assert sessions.next_trading_day("2026-12-24").isoformat() == "2026-12-28"


# ---------- indicators ----------
def test_indicators():
    assert ema_series([1, 2, 3], 3)[-1] == 2
    assert ema_series([1, 2, 3, 4], 3)[-1] == pytest.approx(3.0)
    bars = [{"high": 11, "low": 10, "close": 10.5, "volume": 1}] * 20
    assert adr(bars) == pytest.approx(0.1)
    assert vwap_series([{"high": 2, "low": 0, "close": 1, "volume": 1}, {"high": 4, "low": 2, "close": 3, "volume": 3}])[-1] == 2.5
    lows = [{"low": x} for x in (5, 4, 3, 4, 5, 2, 3, 4)]
    assert swing_lows(lows) == [2, 5]


# ---------- sizing ----------
def test_size_normal_and_aplus():
    s = size(100, 97, 250)            # 3% stop -> $8,333 at 4x
    assert s["notional"] == pytest.approx(8333.33, abs=0.01) and s["leverage"] == 4 and s["margin"] <= 2500
    s = size(100, 97, 500)            # $16,667 at 7x
    assert s["leverage"] == 7 and not s["capped"]


def test_size_capped_and_min_lev():
    s = size(100, 99, 500)            # 1% stop needs $50k -> capped at $25k / 10x, risk $250
    assert s["capped"] and s["leverage"] == 10 and s["notional"] == 25000 and s["risk"] == pytest.approx(250)
    s = size(100, 80, 250)            # 20% stop -> $1,250, still 2x minimum
    assert s["leverage"] == 2
    with pytest.raises(ValueError):
        size(100, 101, 250)


def test_rounding():
    assert hl_price(380.8123, 2) == 380.81
    assert hl_price(1234.567, 2) == 1234.6
    assert hl_price(0.123456, 0) == 0.12346
    assert floor_qty(11.049, 2) == 11.04


# ---------- regime / heat ----------
def test_regime_states():
    up = after_close.regime(daily([100 + i * 0.5 for i in range(220)]))
    assert up["state"] == "Trend up" and up["above200"]
    down = after_close.regime(daily([200 - i * 0.5 for i in range(220)]))
    assert down["state"] == "Trend down" and not down["above200"]
    flat = after_close.regime(daily([100 + (i % 2) * 0.1 for i in range(220)]))
    assert flat["state"] == "Sideways"


def test_metrics_and_step1():
    bars = daily([50 + i * 0.1 for i in range(260)], rng=0.05)
    m = after_close.metrics("MU", bars, {"market_value": "700e9", "fifty_two_wk_high": "80", "fifty_two_wk_low": "40"})
    assert m["step1"] and m["adr20"] == pytest.approx(0.05 / 0.975, rel=1e-3)
    m = after_close.metrics("MU", bars[-150:], {"market_value": "700e9"})
    assert not m["step1"] and any("200d" in f for f in m["step1_fails"])


# ---------- morning ----------
def _m(pdh=100.0, close=99.0):
    return {"ticker": "MU", "liquid": "xyz:MU", "group": "Semis", "adr20": 0.05, "ext20": 0.02, "pos52": 0.9,
            "mcap": 7e11, "hi52": 130.0, "sma200": 80.0, "earnings": None,
            "levels": {"prior_close": close, "pdh": pdh, "resistance": [], "support": []},
            "boxes": {str(k): True for k in (2, 3, 4, 5, 7, 8, 9)} | {"1": None, "6": None}}


def test_morning_evaluate():
    spy = {"state": "Trend up", "above200": True}
    pm = {"pmh": 104, "pml": 102, "pm_last": 103.5, "pm_vol": 50_000, "pm_rvol": 2.0}
    r = morning.evaluate(_m(), pm, spy, False)
    assert r["core"] and r["aplus_if_catalyst"] and r["a_rvol_ok"]
    r = morning.evaluate(_m(pdh=104), pm, spy, False)           # below prior-day high
    assert not r["core"]
    r = morning.evaluate(_m(), pm | {"pm_last": 101.5}, spy, False)   # gap 2.5%
    assert not r["checks"]["gap >= 3%"]
    r = morning.evaluate(_m(), pm, spy, True)                   # half day
    assert not r["core"]
    r = morning.evaluate(_m(), pm, {"state": "Sideways", "above200": True}, False)
    assert not r["core"]


def test_pre_stats_rvol():
    bars = []
    for d in range(1, 15):
        bars += series(dt.date(2026, 11, d), "08:00", [10] * 6, "PRE", v=100)
    bars += series(DAY, "08:00", [10, 11, 12], "PRE", v=400)
    s = morning._pre_stats(bars, DAY, 9 * 60 + 25)
    assert s["pmh"] == 12 and s["pm_vol"] == 1200 and s["pm_rvol"] == pytest.approx(2.0)


# ---------- trigger ----------
def test_choose_alternates():
    assert trigger.choose(["A", "B"], None) == ("A", "B")
    assert trigger.choose(["A", "B"], "A") == ("B", "A")
    assert trigger.choose(["A", "B"], "B") == ("A", "B")
    assert trigger.choose(["B"], "B") == ("B", None)
    assert trigger.choose([], "A") == (None, None)


def _ms(core=True, date=DAY):
    r = {"ticker": "MU", "liquid": "xyz:MU", "group": "Semis", "pmh": 104.0, "pm_rvol": 2.0, "a_rvol_ok": True,
         "core": core, "checks": {"gap >= 3%": core}, "gap": 0.04, "adr20": 0.05, "ext20": 0.02, "pos52": 0.9,
         "prior_close": 99, "pdh": 100, "pm_vol": 50_000,
         "boxes": {str(k): True for k in range(1, 10)} | {"6": None}}
    return {"date": date.isoformat(), "spy": {"state": "Trend up", "above200": True}, "all_rows": {"MU": r}}


def _today(day=DAY):
    pre = series(day, "09:00", [(102, 104, 103)] * 6, "PRE")
    rth = series(day, "09:30", [(101, 103.5, 103)] * 6 + [(102.5, 103.8, 103.5)] * 6 + [(103.4, 105.0, 104.8)])
    return {"MU": pre + rth}


def _hist():
    h = []
    for d in range(10, 25):
        h += series(dt.date(2026, 11, d), "09:30", [100] * 78, v=100)
    return {"MU": h}


def test_trigger_trade_and_orders():
    st = trigger.run("MU", _ms(), _today(), _hist(), 105.0, now="10:33", catalyst=True)
    assert st["holds"] and st["eligible"] == ["A", "B"] and st["real"] == "A" and st["shadow"] == "B"
    assert st["grade"] == "A+" and st["risk"] == 500
    a = st["legs"]["A"]
    assert a["webull_stop"] == pytest.approx(101.0)                    # min(PMH*0.99=102.96, LOD 101)
    assert st["legs"]["B"]["webull_stop"] == pytest.approx(99.99)
    assert a["margin"] <= 2500 and 2 <= a["leverage"] <= 10
    assert st["orders"][0]["suggest_order"]["stopLoss"] == a["liquid_stop"]
    assert all(o["execute_order"]["reduceOnly"] for o in st["orders"][1:]) and len(st["orders"]) == 3
    assert [r["Status"] for r in st["notion"]] == ["Planned", "Shadow"]


def test_trigger_blocks():
    st = trigger.run("MU", _ms(), _today(), _hist(), 105.0, now="10:33", day_pnl=-500)
    assert st["real"] is None and any("loss limit" in b for b in st["blocks"])
    st = trigger.run("MU", _ms(), _today(), _hist(), 105.0, now="10:33", trades_today=2)
    assert st["real"] is None
    st = trigger.run("MU", _ms(core=False), _today(), _hist(), 105.0, now="10:33")
    assert st["real"] is None
    half = dt.date(2026, 11, 27)
    st = trigger.run("MU", _ms(date=half), _today(half), {}, 105.0, now="10:33")
    assert st["real"] is None and any("half day" in b for b in st["blocks"])
    early = {"MU": _today()["MU"][:12] + [m5(DAY, "10:00", 103.4, 105.0, 103.4, 104.8)]}
    st = trigger.run("MU", _ms(), early, _hist(), 105.0, now="10:03")   # A window only; B starts 10:05
    assert st["eligible"] == ["A"] and st["shadow"] is None


def test_trigger_not_above_level():
    t = _today()
    t["MU"][-1] = m5(DAY, "10:30", 103.4, 103.9, 103.2, 103.5)
    st = trigger.run("MU", _ms(), t, _hist(), 103.5, now="10:33")
    assert not st["holds"] and st["real"] is None


# ---------- shadow ----------
def test_shadow_a_partials_and_time_exit():
    bars = series(DAY, "09:30", [100] * 12) + series(DAY, "10:30", [(100, 102.5, 100), (101, 104.2, 101)]) \
        + series(DAY, "10:40", [104] * 80)
    s = shadow.simulate(bars, DAY, 10 * 60 + 30, 100.0, 98.0, "A")
    reasons = sorted(e[2] for e in s["exits"])
    assert reasons == ["Carry (marked 15:50)", "Partial +1.0R", "Partial +2.0R"]   # in profit, above 21 EMA
    assert s["r_gross"] == pytest.approx((1 + 2 + 2) / 3)


def test_shadow_stop_first_and_b_breakeven():
    bars = series(DAY, "09:30", [100] * 12) + series(DAY, "10:30", [(97, 103, 100)])
    s = shadow.simulate(bars, DAY, 10 * 60 + 30, 100.0, 98.0, "A")
    assert s["r_gross"] == pytest.approx(-1.0) and s["final_reason"] == "Stop"
    bars = series(DAY, "09:30", [100] * 12) + series(DAY, "10:30", [(100, 102.1, 101), (99.5, 100.5, 100)])
    s = shadow.simulate(bars, DAY, 10 * 60 + 30, 100.0, 98.0, "B")
    assert s["final_reason"] == "Breakeven"
    assert s["r_gross"] == pytest.approx(0.75 / 3)


# ---------- manage (TJ check) ----------
from tjl import audit, manage  # noqa: E402


def _trade(version="B"):
    st = trigger.run("MU", _ms(), _today(), _hist(), 105.0, now="10:33",
                     prev_version="A" if version == "B" else "B")
    assert st["real"] == version
    return st


def test_check_b_breakeven_then_trail():
    tr = _trade("B")
    entry, stop = tr["chart"]["last"], tr["legs"]["B"]["webull_stop"]
    r = entry - stop
    later = series(DAY, "10:35", [(entry, entry + 1.1 * r, entry + r)] + [(entry + 0.5 * r, entry + 1.2 * r, entry + r)] * 3)
    bars = {"MU": _today()["MU"] + later}
    st = manage.run(tr, bars, "10:55", 7.0, tr["legs"]["B"]["liquid_stop"], 106.0)
    assert st["actions"][0]["do"] == "move stop"
    assert st["actions"][0]["to"] >= tr["legs"]["B"]["liquid_entry_ref"]


def test_check_time_and_flat():
    tr = _trade("A")
    st = manage.run(tr, _today(), "15:46", 9.0, 100.0, 105.0)
    assert st["actions"][0]["do"] == "close"
    st = manage.run(tr, _today(), "11:00", 0, 100.0, 105.0)
    assert st["actions"][0]["do"] == "nothing open"


# ---------- audit ----------
def _row(i, pnl, risk=250, status="Closed", version="A: TJL-report", followed=True, title=None):
    return {"Trade": title or f"t{i}", "Status": status, "Version": version, "P&L $": pnl, "Risk $": risk,
            "date:Date:start": (dt.date(2026, 12, 1) + dt.timedelta(days=i)).isoformat(), "Ticker": "MU",
            "Rule followed": "__YES__" if followed else "__NO__", "Mistakes": None,
            "A+ boxes": '["2 ADR20 4%+"]', "Grade": "Normal"}


def test_audit_verdicts():
    rows = [_row(0, 0, title="TEST x")]
    assert audit.run(rows, dt.date(2027, 3, 1))["overall"]["n"] == 0
    good = [_row(i, 250 if i % 2 else -125) for i in range(40)]
    st = audit.run(good, dt.date(2027, 3, 1))
    assert st["overall"]["exp_r"] == pytest.approx(0.25) and st["verdict"].startswith("GO")
    st = audit.run(good[:10], dt.date(2026, 12, 20))
    assert st["verdict"].startswith("TOO EARLY")
    bad = [_row(i, -250 if i % 2 else 200) for i in range(40)]
    assert audit.run(bad, dt.date(2027, 3, 1))["verdict"].startswith("NO-GO")
    dd = [_row(i, -250) for i in range(13)]
    assert "PAUSE" in audit.run(dd, dt.date(2027, 3, 1))["verdict"]
    mid = [_row(i, 250 if i % 2 else -200) for i in range(40)]   # +0.1R
    assert audit.run(mid, dt.date(2027, 3, 1))["verdict"].startswith("EXTEND")


def test_check_overnight_carry_or_close():
    tr = _trade("A")
    entry = tr["legs"]["A"]["liquid_entry_ref"]
    up = {"MU": _today()["MU"] + series(DAY, "10:35", [(104.8, 106, 105.5)] * 63)}   # trends up to 15:45
    st = manage.run(tr, up, "15:46", 9.0, tr["legs"]["A"]["liquid_stop"], entry * 1.02)
    assert st["actions"][0]["do"] == "move stop" and st["actions"][0]["to"] >= entry   # carry, stop to breakeven
    assert any("CARRY" in n for n in st["notes"])
    st = manage.run(tr, up, "15:46", 9.0, tr["legs"]["A"]["liquid_stop"], entry * 0.99)
    assert st["actions"][0]["do"] == "close"                                            # losing -> flat
    nxt = dt.date(2026, 12, 2)
    day2 = {"MU": up["MU"] + series(nxt, "09:30", [106] * 30 + [(100, 101, 100.5)])}
    st = manage.run(tr, day2, "12:10", 3.0, entry, 101.0, today=nxt)
    assert st["carried"] and st["actions"][0]["do"] == "close"                          # close below 21 EMA next day

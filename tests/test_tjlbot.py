"""Engine tests for the unattended bot, on the in-memory broker (tests/fake_alpaca.py).
Run: python3 -m pytest tests/ -q"""
import datetime as dt
import json
import os

import pytest

from fake_alpaca import FakeAlpaca, FakeMarket, add_daily_methods
from test_tjl import DAY, _hist, _ms, _today, m5, series
from tjl import sessions
from tjl.webull import ET
from tjlbot import catalyst, risk
from tjlbot.engine import Bot, split_legs
from tjlbot.market import _with_current_bar, et


def make(tmp_path, now="10:33", price=105.0, ab_last=None, catalyst_ok=True):
    clk = {"t": et(DAY, now)}
    clock = lambda: clk["t"]   # noqa: E731
    api = FakeAlpaca(clock)
    api.px["MU"] = price
    mk = FakeMarket(api, clock, bars=_today(), hist=_hist())
    bot = Bot(api, mk, str(tmp_path), clock=clock, sleep=lambda s: None, log=lambda m: None)
    bot.load_calendar()
    bot.plan = _ms()
    bot.book["ab_last"] = ab_last
    bot.daily.update(plan_done=True, final=["MU"], catalyst={"MU": {"catalyst": catalyst_ok, "type": "Earnings/guidance",
                                                                  "headline": "Micron raises guidance"}})
    return bot, api, mk, clk


def at(clk, hhmm):
    clk["t"] = et(DAY, hhmm)
    return clk["t"]


def test_split_legs():
    assert split_legs(131, "A", [1, 2]) == [(1, 43, 1), (2, 43, 2), (3, 45, None)]
    assert split_legs(10, "B", [1]) == [(1, 3, 1), (2, 7, None)]
    assert split_legs(2, "A", [1, 2]) == [(3, 2, None)]


def test_entry_a_partials_and_flat_by_1551(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    t = bot.book["trades"][f"{DAY}-MU-A"]
    assert t["status"] == "open" and t["grade"] == "A+" and t["shadow"] == "B"
    assert [(o["side"], o["type"]) for o in api.submitted] == [("buy", "market"), ("sell", "stop")]
    assert api.submitted[1]["stop_price"] == f"{t['stop0']:.2f}" and int(api.submitted[1]["qty"]) == t["qty"]
    assert t["risk_actual"] <= 500 and [x["qty"] for x in t["targets"]] == [t["qty"] // 3] * 2
    assert bot.book["ab_last"] == "A"                                   # paired day: alternation advances
    # +1R: the first target fills at the broker; the bot sees it on the next tick
    mk.bars["MU"] += series(DAY, "10:35", [(108, 109.5, 109)] * 63)
    api.move("MU", 109.0, high=109.5)
    bot.tick(at(clk, "10:41"))
    assert t["partials_filled"] == 1 and t["status"] == "open"
    stop = api.o[t["stop_id"]]
    assert int(stop["qty"]) == api.pos["MU"]["qty"] == t["qty"] - t["targets"][0]["qty"]    # stop shrunk with it
    # 15:46: in profit and above the 21 EMA, but 2/3 of an A+ position is over the $5,000 carry cap -> flat
    bot.tick(at(clk, "15:46"))
    assert "MU" not in api.pos
    bot.tick(at(clk, "15:47"))
    assert t["status"] == "closed" and t["exit_reason"] == "Time 3:51"
    assert not [o for o in api.orders("open")]                          # nothing left at the broker


def test_b_breakeven_after_1r(tmp_path):
    bot, api, mk, clk = make(tmp_path, ab_last="A")
    bot.tick(clk["t"])
    t = bot.book["trades"][f"{DAY}-MU-B"]
    assert len(t["targets"]) == 1 and t["targets"][0]["qty"] == t["qty"] // 3
    mk.bars["MU"].append(m5(DAY, "10:35", 105, 110.5, 104.9, 110))
    api.move("MU", 110.0, high=110.5)
    bot.tick(at(clk, "10:41"))
    assert t["stop_now"] >= round(t["fill"], 2)
    stops = [o for o in api.o.values() if o["type"] == "stop" and o["status"] == "new"]
    assert len(stops) == 1 and float(stops[0]["stop_price"]) == t["stop_now"]
    assert t["partials_filled"] == 1                                  # +0.75R target taken on the way


def test_daily_cap_sizes_down(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    api.last_equity = 25_300.0                       # already -$300 today -> $200 of budget left
    bot.tick(clk["t"])
    t = bot.book["trades"][f"{DAY}-MU-A"]
    assert t["risk_actual"] <= 200 + 1e-6


def test_daily_cap_no_trade_when_spent(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    api.last_equity = 25_470.0                       # -$470: $30 left < $50 minimum
    bot.tick(clk["t"])
    assert not bot.book["trades"] and not api.submitted


def test_breaker_flattens_and_halts(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    api.last_equity = float(api.account()["equity"]) + 500      # day P&L now -$500
    bot.tick(at(clk, "10:40"))
    assert "MU" not in api.pos and bot.daily["halted"]
    api.last_equity = float(api.account()["equity"])
    bot.daily["final"] = ["MU", "NVDA"]
    bot.tick(at(clk, "10:45"))
    assert len([o for o in api.submitted if o["side"] == "buy"]) == 1     # no new entries after the halt


def test_kill_files(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    open(os.path.join(tmp_path, "HALT"), "w").close()
    bot.tick(clk["t"])
    assert not api.submitted
    os.remove(os.path.join(tmp_path, "HALT"))
    bot.tick(at(clk, "10:34"))
    assert "MU" in api.pos
    open(os.path.join(tmp_path, "FLATTEN"), "w").close()
    bot.tick(at(clk, "10:36"))
    assert "MU" not in api.pos


def test_unknown_position_is_closed(tmp_path):
    bot, api, mk, clk = make(tmp_path, now="09:45")
    api.px["TSLA"] = 300.0
    api.pos["TSLA"] = {"qty": 5, "avg": 300.0}
    bot.tick(clk["t"])
    assert "TSLA" not in api.pos


def test_restart_rebuilds_a_half_saved_entry(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    tid = f"{DAY}-MU-A"
    stop_id = bot.book["trades"][tid]["stop_id"]
    bot.book["trades"][tid].update(status="pending", stop_id=None, order_ids=[])   # the job died mid-entry
    bot.save()
    bot2 = Bot(api, mk, str(tmp_path), clock=lambda: clk["t"], sleep=lambda s: None, log=lambda m: None)
    bot2.plan = bot.plan
    bot2.reconcile(api.positions(), at(clk, "10:36"))
    t = bot2.book["trades"][tid]
    assert t["status"] == "open" and t["qty"] == api.pos["MU"]["qty"] and t["stop_id"] == stop_id


def test_lost_stop_is_replaced(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    t = bot.book["trades"][f"{DAY}-MU-A"]
    api.o[t["stop_id"]]["status"] = "canceled"                         # e.g. cancelled at the broker
    bot.tick(at(clk, "10:36"))
    assert api.o[t["stop_id"]]["status"] == "new" and int(api.o[t["stop_id"]]["qty"]) == t["qty"]


def test_stop_hit_at_broker(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    t = bot.book["trades"][f"{DAY}-MU-A"]
    api.move("MU", 100.0, low=100.0)
    bot.tick(at(clk, "10:40"))
    assert t["status"] == "closed" and t["exit_reason"] == "Stop" and not api.pos


def test_eod_rows(tmp_path):
    bot, api, mk, clk = make(tmp_path)
    bot.tick(clk["t"])
    mk.bars["MU"] += series(DAY, "10:35", [(108, 109.5, 109)] * 63) + series(DAY, "15:50", [(108, 109, 108.5)] * 2)
    api.move("MU", 109.0, high=109.5)
    bot.tick(at(clk, "10:41"))
    bot.tick(at(clk, "15:46"))
    bot.tick(at(clk, "15:47"))
    at(clk, "16:12")
    bot.eod()
    rows = json.load(open(os.path.join(bot.dd, "notion_rows.json")))
    real = [r for r in rows if r["properties"]["Status"] == "Closed"][0]["properties"]
    shadow = [r for r in rows if r["properties"]["Status"] == "Shadow"][0]["properties"]
    assert real["P&L $"] > 0 and real["Risk $"] > 0 and "sim_r=" in real["Notes"] and "Leverage" not in real
    assert shadow["Version"] == "B: TJL-bot" and "sim_r=" in shadow["Notes"]
    assert os.path.exists(os.path.join(bot.dd, "report.md"))


def test_half_day_no_plan(tmp_path):
    clk = {"t": dt.datetime(2026, 11, 27, 9, 15, tzinfo=ET)}
    api = FakeAlpaca(lambda: clk["t"])
    bot = Bot(api, FakeMarket(api, lambda: clk["t"]), str(tmp_path), clock=lambda: clk["t"], sleep=lambda s: None,
              log=lambda m: None)
    assert bot.load_calendar() and bot.half
    assert bot.premarket() == []


def test_risk_budget():
    acct = {"equity": "24800", "last_equity": "25000"}
    pos = [{"symbol": "MU", "qty": "10", "current_price": "105"}]
    assert risk.budget(acct, pos, {"MU": 101}) == pytest.approx(500 - 200 - 40)
    assert risk.budget(acct, pos, {}) == pytest.approx(500 - 200 - 1050)        # unknown stop counts in full
    assert risk.breached({"equity": "24500", "last_equity": "25000"})


def test_catalyst_classes():
    assert catalyst.classify([{"headline": "Micron beats, raises guidance"}])["type"] == "Earnings/guidance"
    assert catalyst.classify([{"headline": "Company prices $500M stock offering"}])["trap"]
    assert catalyst.classify([])["type"] == "None"


def test_current_bar_uses_last_trade():
    bars = [m5(DAY, "10:25", 1, 2, 1, 1.5)]
    _with_current_bar(bars, et(DAY, "10:32"), 2.5)
    assert bars[-1]["t"] == et(DAY, "10:30") and bars[-1]["close"] == 2.5


# ---------- premarket pipeline on a small synthetic universe ----------
def _weekdays_back(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5 and (d.year != 2026 or sessions.is_trading_day(d)):
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def _daily(days, start, step, rng=0.05, vol=5e6):
    out = []
    for i, d in enumerate(days):
        c = start + i * step
        out.append({"t": dt.datetime(d.year, d.month, d.day, tzinfo=ET), "date": d, "open": c, "high": c * (1 + rng / 2),
                     "low": c * (1 - rng / 2), "close": c, "volume": vol, "session": ""})
    return out


def _premarket_bot(tmp_path):
    day = DAY
    prior = sessions.prev_trading_day(day)
    days = _weekdays_back(prior, 260)
    names = ["MU", "NVDA", "AMD", "AVGO", "MRVL"]
    daily = {t: _daily(days, 50, 50 / 259) for t in names}          # ends at 100, steady uptrend, ADR ~5%
    daily["SPY"] = _daily(days, 500, 1.0, rng=0.01, vol=8e7)
    hist, pre_today = {}, {}
    for d in _weekdays_back(prior, 15):
        for t in names:
            hist.setdefault(t, []).extend(series(d, "04:00", [99.5] * 66, "PRE", v=100))
            hist[t] += series(d, "09:30", [(99, 100.5, 100)] * 78, v=50_000)
    pre_today["MU"] = series(day, "04:00", [(103, 104.6, 104.5)] * 60, "PRE", v=400)
    for t in names[1:]:
        pre_today[t] = series(day, "04:00", [100.2] * 60, "PRE", v=100)
    clk = {"t": et(day, "09:15")}
    api = FakeAlpaca(lambda: clk["t"])
    mk = add_daily_methods(FakeMarket(api, lambda: clk["t"], hist=hist,
                                      news=[{"headline": "Micron raises guidance", "symbols": ["MU"]}]), daily, pre_today)
    bot = Bot(api, mk, str(tmp_path), clock=lambda: clk["t"], sleep=lambda s: None, log=lambda m: None)
    bot.load_calendar()
    return bot, bot.premarket()


def test_premarket_flags_the_gapper(tmp_path):
    bot, final = _premarket_bot(tmp_path)
    assert final == ["MU"]
    assert bot.daily["catalyst"]["MU"]["type"] == "Earnings/guidance"
    ms = json.load(open(os.path.join(bot.dd, "morning.json")))
    r = ms["final_rows"]["MU"]
    assert r["gap"] > 0.03 and r["pm_rvol"] == pytest.approx(4.0) and r["pdh"] == pytest.approx(100.5)


def test_full_day_two_jobs(tmp_path):
    """Morning job from 10:30 to the 14:15 hand-over, then the afternoon job: flat by 15:51 and the report."""
    bot, api, mk, clk = make(tmp_path, now="10:30")
    mk.bars["MU"] = _today()["MU"][:12] + series(DAY, "10:30", [(104.6, 105.2, 105)] + [(104.8, 105.1, 104.9)] * 72)

    def sleep(s):
        clk["t"] += dt.timedelta(seconds=max(s, 1))
    bot.sleep = sleep
    bot.save()
    bot.auto()
    assert dt.time(14, 15) <= clk["t"].time() < dt.time(14, 17)
    t = bot.book["trades"][f"{DAY}-MU-A"]
    assert t["status"] == "open"
    at(clk, "14:17")
    bot2 = Bot(api, mk, str(tmp_path), clock=lambda: clk["t"], sleep=sleep, log=lambda m: None)   # fresh job
    bot2.auto()
    t = bot2.book["trades"][f"{DAY}-MU-A"]
    assert t["status"] == "closed" and t["exit_reason"] == "Time 3:51" and not api.pos
    assert bot2.daily["eod_done"] and os.path.exists(os.path.join(bot2.dd, "report.md"))
    assert clk["t"].time() < dt.time(16, 16)


def _webull_files(tmp_path, gaps, prior=None):
    """Webull-format saved results: a snapshot (pre_close) and today's 5m PRE bars, newest first."""
    snap, bars = [], []
    for t, last in gaps.items():
        snap.append({"symbol": t, "pre_close": str((prior or {}).get(t, 100.0)), "close": "101"})
        rows = []
        for i in range(60):   # 04:00-08:55 ET = 09:00-13:55 UTC in December
            utc = dt.datetime(2026, 12, 1, 9, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=5 * i)
            rows.append({"time": utc.strftime("%Y-%m-%dT%H:%M:%S.000+0000"), "open": str(last), "high": str(last + 0.1),
                         "low": str(last - 0.1), "close": str(last), "volume": "400", "trading_session": "PRE"})
        bars.append({"symbol": t, "result": rows[::-1]})
    sp, bp = os.path.join(tmp_path, "snap.json"), os.path.join(tmp_path, "pre.json")
    json.dump(snap, open(sp, "w"))
    json.dump({"result": bars}, open(bp, "w"))
    return sp, bp


def test_crosscheck_agrees_and_finds_misses(tmp_path):
    from tjlbot.__main__ import main
    bot, final = _premarket_bot(tmp_path)
    # Webull agrees on MU; shows NVDA gapping 4% (the bot's feed saw it flat); AMD's prior close differs
    sp, bp = _webull_files(tmp_path, {"MU": 104.5, "NVDA": 104.0, "AMD": 100.2, "AVGO": 100.2, "MRVL": 100.2},
                           prior={"AMD": 101.0})
    main(["crosscheck", "--state", str(tmp_path), "--date", DAY.isoformat(), "--snapshot", sp, "--pre", bp])
    st = json.load(open(os.path.join(bot.dd, "crosscheck.json")))
    assert st["flagged_both"] == ["MU"] and not st["flagged_bot_only"]
    assert [m["ticker"] for m in st["missed"]] == ["NVDA"] and "gap" in st["missed"][0]["why"]
    issues = {d["ticker"]: " ".join(d["issues"]) for d in st["data_issues"]}
    assert "gap" in issues["NVDA"] and "prior close" in issues["AMD"] and "MU" not in issues
    assert os.path.exists(os.path.join(bot.dd, "crosscheck.md"))

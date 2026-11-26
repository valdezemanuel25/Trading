"""The bot's trading day. Every rule decision is made by tjl/ (after_close, morning, trigger, manage, shadow), the
same code the manual routines use; this file only fetches data, places Alpaca orders and keeps state.

State (all JSON, under <state_dir>/runs/tjl-bot/):
  book.json            open/closed trades across days, A/B alternation, test starting equity
  <date>/day.json      the day's counters, plan, halts, skipped setups
  <date>/after_close.json, morning.json   the tjl states (same format as the manual routine)
  <date>/events.jsonl  every decision, order and error
  <date>/report.md, notion_rows.json      end-of-day output (rows in the TJL Trades schema)
Orders per trade: a market buy, one GTC stop for the whole position, market sells for partials and exits.
Client ids "<date>-<ticker>-<version>-<E|S|P|X><n>" let a restarted job rebuild its trades.
"""
import datetime as dt
import json
import os
import time
import traceback

from tjl import after_close, manage, morning, shadow, trigger
from tjl import config as C
from tjl.webull import ET, minutes_et

from . import catalyst, risk, report
from . import settings as S
from .broker import AlpacaError
from .market import et

HERE = os.path.dirname(os.path.abspath(__file__))
TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


def cents(p):
    return round(p + 1e-9, 2)


def hhmm(t):
    return f"{t.hour:02d}:{t.minute:02d}"


def mins(t):
    return t.hour * 60 + t.minute


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, default=str)
    os.replace(tmp, path)


def split_legs(qty, version, partial_prices):
    """A: thirds, TP at +1R and +2R, last third stop only. B: one third TP at +0.75R, the rest stop only."""
    if version == "A":
        q1 = q2 = qty // 3
        parts = [(1, q1, partial_prices[0]), (2, q2, partial_prices[1]), (3, qty - q1 - q2, None)]
    else:
        q1 = qty // 3
        parts = [(1, q1, partial_prices[0]), (2, qty - q1, None)]
    return [p for p in parts if p[1] > 0]


class Bot:
    def __init__(self, api, market, state_dir, clock=None, sleep=time.sleep, sync=None, log=print):
        self.api, self.mk = api, market
        self.state_dir = state_dir
        self.root = os.path.join(state_dir, "runs", "tjl-bot")
        self.clock = clock or (lambda: dt.datetime.now(ET))
        self.sleep, self.sync, self.log = sleep, sync, log
        self.book = _load(self._p("book.json"), {"trades": {}, "ab_last": None, "start_equity": None})
        self.day = self.clock().date()
        self.dd = os.path.join(self.root, self.day.isoformat())
        self.daily = _load(os.path.join(self.dd, "day.json"), {
            "date": self.day.isoformat(), "orders": 0, "halted": None, "plan_done": False, "eod_done": False,
            "final": [], "catalyst": {}, "skipped": {}, "notes": []})
        self.plan = _load(os.path.join(self.dd, "morning.json"), None)
        self.hist = {}
        self.close_min, self.half = 16 * 60, False
        self.errors = 0

    # ---------- plumbing ----------
    def _p(self, name):
        return os.path.join(self.root, name)

    def save(self):
        _save(self._p("book.json"), self.book)
        _save(os.path.join(self.dd, "day.json"), self.daily)

    def event(self, kind, **kw):
        rec = {"ts": self.clock().isoformat(timespec="seconds"), "kind": kind, **kw}
        os.makedirs(self.dd, exist_ok=True)
        with open(os.path.join(self.dd, "events.jsonl"), "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        self.log(f"[{rec['ts']}] {kind}: " + ", ".join(f"{k}={v}" for k, v in kw.items()))

    def _sync(self, force=False):
        if self.sync:
            try:
                self.sync(force)
            except Exception as e:   # noqa: BLE001  (a failed push must never stop trading)
                self.log(f"sync failed: {e}")

    def flags(self):
        return {f: os.path.exists(os.path.join(self.state_dir, f)) for f in ("HALT", "FLATTEN")}

    def trades(self, *status):
        return [t for t in self.book["trades"].values() if not status or t["status"] in status]

    def trades_today(self):
        return [t for t in self.book["trades"].values() if t["date"] == self.day.isoformat() and t["status"] != "failed"]

    # ---------- calendar ----------
    def load_calendar(self):
        cal = self.api.calendar(self.day, self.day)
        if not cal or cal[0]["date"] != self.day.isoformat():
            return False
        hh, mm = map(int, cal[0]["close"].split(":"))
        self.close_min = hh * 60 + mm
        self.half = self.close_min < 16 * 60
        return True

    def flatten_at(self):
        return min(S.FLATTEN_AT, self.close_min - 10)

    # ---------- premarket ----------
    def premarket(self):
        day = self.day
        if self.half:   # doc: no Trend Join trades on half days
            self.daily.update(plan_done=True, final=[])
            self.event("plan", final=[], why="half day: no new trades")
            self.save()
            return []
        daily = self.mk.daily(C.UNIVERSE + S.ETFS, day)
        stock = {s: b for s, b in daily.items() if s in C.TICKER_GROUP}
        etf = {s: b for s, b in daily.items() if s in S.ETFS}
        caps = _load(os.path.join(self.state_dir, "caps.json"), None) or _load(os.path.join(HERE, "caps.json"), {})
        caps = caps.get("caps", caps)
        earn = self.earnings()
        snap = {t: {"market_value": caps.get(t, 0)} for t in C.UNIVERSE}
        ac = after_close.run(stock, etf, snap, {t: v for t, v in earn.items() if t in stock})
        step1 = ac["step1_pass"]
        hist = self.mk.hist5(step1, day) if step1 else {}
        pre_today = self.mk.premarket(step1, day, S.PM_DATA_TO) if step1 else {}
        prior = dt.date.fromisoformat(ac["session"])
        pre = {}
        for t in step1:
            bars = hist.get(t, []) + pre_today.get(t, [])
            pre[t] = bars
            rth = [b for b in bars if b["date"] == prior and b["session"] == "RTH"]
            if rth:   # prior-day high/low from regular-hours bars (the doc's levels are RTH levels)
                lv = ac["all"][t]["levels"]
                lv["pdh"], lv["pdl"] = max(b["high"] for b in rth), min(b["low"] for b in rth)
        ms = morning.run(ac, {}, pre, day, now=S.PM_DATA_TO)
        _save(os.path.join(self.dd, "after_close.json"), ac)
        _save(os.path.join(self.dd, "morning.json"), ms)
        self.plan = ms
        final = list(ms["final"])
        cats = {}
        if final:
            start = et(prior, "16:00")
            news = self.mk.news(final, start, self.clock())
            for t in final:
                cats[t] = catalyst.classify([n for n in news if t in (n.get("symbols") or [])])
        for t in list(final):
            if cats[t]["trap"]:
                final.remove(t)
                self.daily["skipped"][t] = {"why": f"catalyst trap: {cats[t]['headline']}"}
        self.hist = {t: hist.get(t, []) for t in final}
        self.daily.update(plan_done=True, final=final, catalyst=cats, spy=ms["spy"]["state"])
        self.event("plan", final=final, spy=ms["spy"]["state"], step1=len(step1),
                   gappers=[r["ticker"] for r in ms["rows"] if r["gap"] >= C.GAP_MIN])
        self.save()
        self._sync(force=True)
        return final

    def earnings(self):
        e = _load(os.path.join(self.state_dir, "earnings.json"), {})
        return e.get("earnings", e) if isinstance(e, dict) else {}

    def hist_for(self, names):
        missing = [t for t in names if t not in self.hist]
        if missing:
            h = self.mk.hist5(missing, self.day)
            for t in missing:
                self.hist[t] = h.get(t, [])
        return {t: self.hist[t] for t in names}

    # ---------- the loop ----------
    def run_until(self, end_min, eod=False):
        while True:
            now = self.clock()
            m = mins(now)
            if eod and m >= S.EOD_AT and not self.trades("open", "pending") or (eod and m >= S.DAY_END - 2):
                self.eod()
                return
            if m >= end_min:
                break
            try:
                self.tick(now)
                self.errors = 0
            except Exception as e:   # noqa: BLE001  stops sit at the broker; keep going, log, no entries for a while
                self.errors += 1
                self.event("error", where="tick", error=repr(e), trace=traceback.format_exc(limit=3)[-600:])
            self.save()
            self._sync()
            self.sleep(S.LOOP_SECONDS)
        self.save()
        self._sync(force=True)

    def tick(self, now):
        m = mins(now)
        fl = self.flags()
        acct = self.api.account()
        if self.book["start_equity"] is None:
            self.book["start_equity"] = float(acct["equity"])
        positions = self.api.positions()
        self.reconcile(positions, now)
        positions = self.api.positions()
        live = self.trades("open")
        if fl["FLATTEN"] or risk.breached(acct):
            why = "FLATTEN file" if fl["FLATTEN"] else f"daily loss {risk.day_pnl(acct):+.0f} reached -${S.DAILY_MAX_LOSS}"
            if live or not self.daily["halted"]:
                self.event("kill", why=why, closing=[t["id"] for t in live])
            for t in live:
                self.close(t, "Manual", why)
            self.daily["halted"] = why
            return
        if live:
            bars, _cut, last = self.mk.today(sorted({t["ticker"] for t in live}), self.day)
            pos = {p["symbol"]: p for p in positions}
            for t in live:
                self.manage(t, bars, last, pos.get(t["ticker"]), now)
        if self.entry_allowed(now, acct, fl):
            self.scan_entries(now, acct)

    # ---------- entries ----------
    def entry_allowed(self, now, acct, fl):
        m = mins(now)
        if self.half or not self.daily["final"] or self.errors >= 3:
            return False
        if fl["HALT"] or self.daily["halted"]:
            return False
        if not (C.WINDOW["A"][0] <= m <= C.WINDOW["A"][1]):
            return False
        if len(self.trades_today()) >= C.MAX_TRADES_PER_DAY or len(self.trades("open", "pending")) >= S.MAX_OPEN_POSITIONS:
            return False
        if self.daily["orders"] >= S.MAX_ORDERS_PER_DAY:
            return False
        if self.book["start_equity"] and float(acct["equity"]) - self.book["start_equity"] <= S.TEST_DRAWDOWN_PAUSE:
            self.daily["halted"] = "test drawdown reached -$3,000: paused for review (go/no-go rule)"
            self.event("kill", why=self.daily["halted"])
            return False
        return True

    def scan_entries(self, now, acct):
        done = {t["ticker"] for t in self.trades_today()}
        names = [t for t in self.daily["final"] if t not in done]
        if not names:
            return
        positions = self.api.positions()
        stops = {t["ticker"]: t["stop_now"] for t in self.trades("open")}
        budget = risk.budget(acct, positions, stops)
        if budget < S.MIN_RISK:
            if not self.daily.get("budget_note"):
                self.daily["budget_note"] = True
                self.event("no entries", why=f"daily loss budget left ${budget:.0f} < ${S.MIN_RISK}")
            return
        bars, cutoff, last = self.mk.today(names, self.day)
        hist = self.hist_for(names)
        for t in names:
            px, ts = last.get(t, (None, None))
            if not px or (now - ts).total_seconds() > S.STALE_TRADE_SEC:
                continue
            cat = self.daily["catalyst"].get(t, {})
            try:
                st = trigger.run(t, self.plan, bars, hist, px, hhmm(now), day_pnl=risk.day_pnl(acct),
                                 trades_today=len(self.trades_today()), prev_version=self.book["ab_last"],
                                 catalyst=bool(cat.get("catalyst")), catalyst_text=cat.get("headline", ""),
                                 catalyst_type=cat.get("type", "None"), sz_decimals=0, max_lev=C.LEV_MAX,
                                 vol_cutoff=cutoff, price_round=cents, risk_cap=min(budget, C.RISK_APLUS))
            except ValueError as e:
                self.event("trigger skipped", ticker=t, why=str(e))
                continue
            if not st["real"]:
                if st["holds"] and t not in self.daily["skipped"]:
                    why = "; ".join(st["blocks"]) or "; ".join(
                        f"{v}: " + ", ".join(k for k, ok in c.items() if not ok) for v, c in st["conditions"].items())
                    self.daily["skipped"][t] = {"why": why, "time": hhmm(now), "st": _slim(st)}
                    self.event("setup not taken", ticker=t, why=why)
                continue
            self.enter(st, now)
            return   # one entry per tick; the budget is recomputed next tick

    def enter(self, st, now):
        """Market buy, then one GTC stop for the whole position. Partial targets are taken by the bot (stop shrunk
        first, then a market sell), so open sell orders never exceed the position and no buy ever meets a resting
        sell order (Alpaca's wash-trade check)."""
        v = st["real"]
        leg = st["legs"][v]
        qty = int(leg["quantity"])
        stop = leg["liquid_stop"]
        tid = f"{st['date']}-{st['ticker']}-{v}"
        t = {"id": tid, "date": st["date"], "ticker": st["ticker"], "version": v, "shadow": st["shadow"],
             "grade": st["grade"], "status": "pending", "entry_time": now.isoformat(), "st": _slim(st),
             "risk_planned": leg["risk"], "stop0": stop, "stop_now": stop, "partials_filled": 0, "targets": [],
             "entry_id": None, "stop_id": None, "order_ids": [], "n": 0,
             "catalyst": self.daily["catalyst"].get(st["ticker"], {})}
        self.book["trades"][tid] = t
        self.save()
        r = self._submit(t, {"symbol": st["ticker"], "qty": str(qty), "side": "buy", "type": "market",
                             "time_in_force": "day"}, "E")
        if not r:
            t["status"] = "failed"
            self.save()
            return
        t["entry_id"] = r["id"]
        self.save()
        o = self._await(r["id"])
        if o["status"] != "filled":
            self.api.cancel(r["id"])
            o = self.api.order(r["id"])
        filled = int(float(o.get("filled_qty") or 0))
        if not filled:
            t["status"] = "failed"
            self.event("entry failed", trade=tid, status=o["status"])
            self.save()
            return
        self._opened(t, filled, float(o["filled_avg_price"]))
        if st["shadow"]:
            self.book["ab_last"] = v     # alternation advances on paired days only (audit I3)
        self.event("entry", trade=tid, grade=st["grade"], qty=filled, fill=round(t["fill"], 2), stop=stop,
                   risk=t["risk_actual"], targets=[(x["n"], x["qty"], x["price"]) for x in t["targets"]],
                   shadow=st["shadow"], catalyst=t["catalyst"].get("type"))
        if not self.place_stop(t):
            self.close(t, "Manual", "the stop order was rejected, so the position was closed")
        self.save()
        self._sync(force=True)

    def _opened(self, t, filled, fill):
        prices = [p["price"] for p in t["st"]["legs"][t["version"]]["partials"]]
        t.update(fill=fill, qty=filled, qty_open=filled, status="open",
                 risk_actual=round(filled * (fill - t["stop0"]), 2),     # audit I6: R uses the risk at the fill
                 targets=[{"n": n, "qty": q, "price": tp, "done": False}
                          for n, q, tp in split_legs(filled, t["version"], prices) if tp])

    def _submit(self, t, order, tag):
        t["n"] += 1
        order = dict(order, client_order_id=f"{t['id']}-{tag}{t['n']}")
        try:
            r = self.api.submit(order)
        except AlpacaError as e:
            self.event("order error", trade=t["id"], order=tag, error=str(e))
            return None
        self.daily["orders"] += 1
        t["order_ids"].append(r["id"])
        return r

    def _await(self, oid, timeout=45):
        end = time.monotonic() + timeout
        while True:
            o = self.api.order(oid)
            if o["status"] in TERMINAL or time.monotonic() > end:
                return o
            self.sleep(1)

    def place_stop(self, t):
        for _ in range(2):
            r = self._submit(t, {"symbol": t["ticker"], "qty": str(t["qty_open"]), "side": "sell", "type": "stop",
                                 "stop_price": f"{t['stop_now']:.2f}", "time_in_force": "gtc"}, "S")
            if r:
                t["stop_id"] = r["id"]
                return True
        return False

    # ---------- management ----------
    def manage(self, t, bars, last, pos, now):
        m = mins(now)
        today = self.day.isoformat()
        qty = int(float(pos["qty"])) if pos else 0
        price = last.get(t["ticker"], (None, None))[0] or (float(pos["current_price"]) if pos else None)
        if not qty or not price:
            return
        t["qty_open"] = qty
        if m >= self.flatten_at():
            if t.get("carry_date") != today:
                self.close(t, "Time 3:51", "flat by 15:51")
            return
        if m >= C.CARRY_CHECK and not self.half:
            if t.get("carry_checked") != today:
                self.carry_decision(t, bars, price, qty, now)
            return
        entry_bar_end = dt.datetime.fromisoformat(t["entry_time"]).replace(second=0, microsecond=0)
        entry_bar_end += dt.timedelta(minutes=5 - entry_bar_end.minute % 5)
        highs = [b["high"] for b in bars.get(t["ticker"], []) if b["t"] >= entry_bar_end and b["volume"] > 0]
        t["hi_seen"] = max([t.get("hi_seen") or 0, price] + highs)
        self.take_partials(t)
        qty = t["qty_open"]
        res = manage.run(self._for_manage(t), bars, hhmm(now), qty, t["stop_now"], price, fill_price=t["fill"],
                         sz_decimals=0, today=self.day, partials_filled=t["partials_filled"], price_round=cents)
        for a in res["actions"]:
            if a["do"] == "move stop" and a["to"] > t["stop_now"]:
                self.move_stop(t, a["to"], a["why"])
            elif a["do"] == "close":
                self.close(t, "Overnight exit" if t["date"] != today else "Trail", a["why"])

    def take_partials(self, t):
        for tg in t["targets"]:
            if tg["done"] or t["hi_seen"] < tg["price"] or tg["qty"] >= t["qty_open"]:
                continue
            keep = t["qty_open"] - tg["qty"]
            try:   # shrink the stop first, so the stop plus the sale never exceed the position
                r = self.api.replace(t["stop_id"], qty=keep)
                t["stop_id"] = r["id"]
                self.daily["orders"] += 1
            except AlpacaError as e:
                self.event("order error", trade=t["id"], action="partial: shrink stop", error=str(e))
                return
            r = self._submit(t, {"symbol": t["ticker"], "qty": str(tg["qty"]), "side": "sell", "type": "market",
                                 "time_in_force": "day"}, f"P{tg['n']}-")
            if not r:
                return
            o = self._await(r["id"])
            tg.update(done=True, fill=o.get("filled_avg_price"))
            t["partials_filled"] += 1
            t["qty_open"] = keep
            self.event("partial", trade=t["id"], target=tg["n"], qty=tg["qty"], at=tg["price"], fill=tg["fill"])

    def _for_manage(self, t):
        st = json.loads(json.dumps(t["st"]))
        leg = st["legs"][t["version"]]
        leg["liquid_entry_ref"], leg["liquid_stop"], leg["quantity"] = t["fill"], t["stop0"], t["qty"]
        st["real"] = t["version"]
        return st

    def carry_decision(self, t, bars, price, qty, now):
        today = self.day.isoformat()
        t["carry_checked"] = today
        res = manage.run(self._for_manage(t), bars, hhmm(now), qty, t["stop_now"], price, fill_price=t["fill"],
                         sz_decimals=0, today=self.day, partials_filled=t["partials_filled"], price_round=cents)
        close = [a for a in res["actions"] if a["do"] == "close"]
        if close:
            self.close(t, "Time 3:51", close[0]["why"])
            return
        ok, why = self.carry_policy(t, price, qty)
        if not ok:
            self.close(t, "Time 3:51", f"carry rule passed but {why}")
            return
        for a in res["actions"]:
            if a["do"] == "move stop" and a["to"] > t["stop_now"]:
                self.move_stop(t, a["to"], a["why"])
        t["carry_date"] = today
        t["carried"] = True
        self.event("carry", trade=t["id"], qty=qty, stop=t["stop_now"], notes=res["notes"])

    def carry_policy(self, t, price, qty):
        """Assumptions where the doc is silent (docs/tjl-bot.md): no carry into a weekend, holiday or half day, or
        into earnings; carried size capped so a 10% overnight gap stays within the $500 daily cap."""
        if qty * price > S.CARRY_MAX_NOTIONAL:
            return False, f"position ${qty * price:,.0f} > ${S.CARRY_MAX_NOTIONAL:,} carry cap"
        nxt = self.api.calendar(self.day + dt.timedelta(days=1), self.day + dt.timedelta(days=10))
        if not nxt or nxt[0]["date"] != (self.day + dt.timedelta(days=1)).isoformat():
            return False, "next session is not tomorrow (weekend or holiday)"
        if nxt[0]["close"] != "16:00":
            return False, "next session is a half day"
        earn = self.earnings()
        if not earn:
            return False, "no earnings calendar (earnings.json) to check"
        when = str(earn.get(t["ticker"], ""))[:10]
        if when and when <= nxt[0]["date"]:
            return False, f"earnings {earn[t['ticker']]}"
        return True, ""

    def move_stop(self, t, to, why):
        to = cents(to)
        try:
            r = self.api.replace(t["stop_id"], stop_price=f"{to:.2f}")
        except AlpacaError as e:
            self.event("order error", trade=t["id"], action="move stop", error=str(e))
            return
        t["stop_id"] = r["id"]
        self.daily["orders"] += 1
        self.event("move stop", trade=t["id"], frm=t["stop_now"], to=to, why=why)
        t["stop_now"] = to

    def close(self, t, reason, why):
        if t.get("stop_id"):
            self.api.cancel(t["stop_id"])
            self._await(t["stop_id"], timeout=20)   # sell only once the stop no longer holds the shares
        pos = {p["symbol"]: p for p in self.api.positions()}.get(t["ticker"])
        qty = int(float(pos["qty"])) if pos else 0
        if qty > 0:
            r = self._submit(t, {"symbol": t["ticker"], "qty": str(qty), "side": "sell", "type": "market",
                                 "time_in_force": "day"}, "X")
            if not r:
                if t.get("stop_id") and self.api.order(t["stop_id"]).get("status") in TERMINAL:
                    self.place_stop(t)    # the close failed: put the stop back
                return
            self._await(r["id"])
        t["exit_reason"], t["exit_why"] = reason, why
        self.event("close", trade=t["id"], reason=reason, why=why, qty=qty)
        self.save()
        self._sync(force=True)

    # ---------- reconcile ----------
    def reconcile(self, positions, now):
        pos = {p["symbol"]: p for p in positions}
        mine = set()
        for t in self.trades("open", "pending"):
            mine.add(t["ticker"])
            if t["status"] == "pending":   # a job stopped mid-entry: rebuild from the client order ids
                try:
                    orders = self.api.orders("all", after=t["entry_time"], symbols=[t["ticker"]])
                except AlpacaError as e:
                    self.event("error", where="reconcile", error=str(e))
                    continue
                mine_o = [o for o in orders if (o.get("client_order_id") or "").startswith(t["id"] + "-")]
                entry = next((o for o in mine_o if o["client_order_id"].startswith(t["id"] + "-E")), None)
                filled = int(float(entry.get("filled_qty") or 0)) if entry else 0
                if not filled:
                    if t["ticker"] not in pos:
                        t["status"] = "failed"
                    continue
                t["entry_id"] = entry["id"]
                t["order_ids"] = [o["id"] for o in mine_o]
                self._opened(t, filled, float(entry["filled_avg_price"]))
                stop = next((o for o in mine_o if o["client_order_id"].startswith(t["id"] + "-S")
                             and o["status"] not in TERMINAL), None)
                t["stop_id"] = stop["id"] if stop else None
                self.event("entry recovered", trade=t["id"], qty=filled, stop=bool(stop))
            if t["ticker"] not in pos:
                t["status"] = "closed"
                t["closed_at"] = now.isoformat()
                if not t.get("exit_reason"):
                    s, f = t["stop_now"], t["fill"]
                    t["exit_reason"] = "Stop" if s < f - 0.005 else ("Breakeven" if abs(s - f) <= 0.01 else "Trail")
                    if t["date"] != self.day.isoformat():
                        t["exit_reason"] = "Overnight exit"
                self.cancel_all(t["ticker"])   # no orphan orders left behind
                self.event("closed", trade=t["id"], reason=t["exit_reason"])
                continue
            t["qty_open"] = int(float(pos[t["ticker"]]["qty"]))
            st = self.api.order(t["stop_id"]).get("status") if t.get("stop_id") else None
            if st is None or (st in TERMINAL and st != "filled"):   # every position keeps a stop at the broker
                self.event("stop missing", trade=t["id"], status=st)
                if not self.place_stop(t):
                    self.close(t, "Manual", "no stop at the broker and it could not be replaced")
        for sym, p in pos.items():   # the account is the bot's alone: nothing runs unmanaged
            if sym not in mine and float(p["qty"]) != 0:
                self.event("kill", why=f"unknown position {sym} {p['qty']}: closing it")
                self.cancel_all(sym)
                self.api.submit({"symbol": sym, "qty": str(abs(int(float(p["qty"])))),
                                 "side": "sell" if float(p["qty"]) > 0 else "buy", "type": "market",
                                 "time_in_force": "day"})

    def cancel_all(self, sym):
        for o in self.api.orders("open", symbols=[sym]):
            for x in [o] + list(o.get("legs") or []):
                if x.get("status") not in TERMINAL:
                    self.api.cancel(x["id"])

    # ---------- end of day ----------
    def eod(self):
        if self.daily["eod_done"]:
            return
        today = self.day.isoformat()
        touched = [t for t in self.book["trades"].values() if t["status"] != "failed" and
                   (t["date"] == today or t["status"] == "open" or (t.get("closed_at") or "")[:10] == today)]
        for t in touched:
            try:
                fills = [f for f in self.api.fills(after=t["entry_time"]) if f["symbol"] == t["ticker"]]
            except AlpacaError as e:
                self.event("error", where="eod fills", error=str(e))
                fills = []
            report.apply_fills(t, fills)
        sims = {}
        traded = sorted({t["ticker"] for t in touched if t["date"] == today} |
                        {s for s in self.daily["skipped"] if self.daily["skipped"][s].get("st")})
        if traded:
            bars = self.mk._get(traded, "5Min", et(self.day, "04:00"), self.mk._sip_end(et(self.day, "16:00")))
            for t in touched:
                if t["date"] == today:
                    sims[t["id"]] = report.simulate(t["st"], bars.get(t["ticker"], []), self.day)
            for s, sk in self.daily["skipped"].items():
                if sk.get("st"):
                    sims["skip-" + s] = report.simulate(sk["st"], bars.get(s, []), self.day)
        rows = report.notion_rows(self, touched, sims)
        _save(os.path.join(self.dd, "notion_rows.json"), rows)
        with open(os.path.join(self.dd, "report.md"), "w") as f:
            f.write(report.markdown(self, touched, sims) + "\n")
        self.daily["eod_done"] = True
        self.event("eod", trades=len(touched), rows=len(rows))
        self.save()
        self._sync(force=True)

    # ---------- the job ----------
    def auto(self):
        """One GitHub Actions job: decides by the ET clock what to do (see docs/tjl-bot.md)."""
        now = self.clock()
        m = mins(now)
        if not self.load_calendar():
            if not self.daily.get("closed_logged"):
                self.daily["closed_logged"] = True
                self.event("closed", why="market closed today")
                self.save()
                self._sync(force=True)
            return
        if m < 8 * 60 + 20:
            self.log("too early for this slot (the other DST cron line); exiting")
            return
        if m >= S.DAY_END:
            self.eod()
            return
        if not self.daily["plan_done"]:
            if m < S.SCAN_AT:
                self.sleep((S.SCAN_AT - m) * 60 - now.second)
            try:
                self.premarket()
            except Exception as e:   # noqa: BLE001  no plan -> no new trades today, open positions still managed
                self.daily.update(plan_done=True, final=[])
                self.event("error", where="premarket", error=repr(e), trace=traceback.format_exc(limit=4)[-800:])
                self.save()
        elif self.plan is None and self.daily["final"]:
            self.daily["final"] = []
        if not self.daily["final"] and not self.trades("open", "pending"):
            self.eod()
            return
        if mins(self.clock()) < S.MORNING_END - 5:
            self.run_until(S.MORNING_END)
            if self.trades("open", "pending") or (self.daily["final"] and len(self.trades_today()) < C.MAX_TRADES_PER_DAY):
                return   # the afternoon job carries on
            self.eod()
            return
        self.run_until(S.DAY_END, eod=True)


def _slim(st):
    """The parts of a trigger state that management, simulation and the Notion rows need."""
    keep = ("kind", "date", "time_et", "ticker", "liquid", "group", "chart", "pmh", "trigger_level", "confirm_5m",
            "rvol_b", "rvol_days", "pm_rvol", "conditions", "blocks", "eligible", "real", "shadow", "grade", "boxes",
            "risk", "risk_target", "legs", "spy_state", "catalyst", "catalyst_type", "gap", "row", "notion")
    return {k: st.get(k) for k in keep}

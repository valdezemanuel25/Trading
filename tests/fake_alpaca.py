"""In-memory stand-ins for Alpaca (orders, brackets, fills) and the bot's market data, for engine tests."""
import copy
import datetime as dt

from tjl import sessions

TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


class FakeAlpaca:
    def __init__(self, clock, equity=25_000.0, half_days=()):
        self.now = clock
        self.cash = equity
        self.last_equity = equity
        self.px = {}
        self.pos = {}
        self.o = {}
        self.fill_log = []
        self.n = 0
        self.half_days = set(half_days)
        self.submitted = []

    # ---- helpers ----
    def _id(self):
        self.n += 1
        return f"o{self.n}"

    def _fill(self, order, price):
        q = int(order["qty"])
        sym = order["symbol"]
        sign = 1 if order["side"] == "buy" else -1
        p = self.pos.setdefault(sym, {"qty": 0, "avg": 0.0})
        if sign > 0:
            p["avg"] = (p["avg"] * p["qty"] + price * q) / (p["qty"] + q)
        p["qty"] += sign * q
        if p["qty"] == 0:
            del self.pos[sym]
        self.cash -= sign * q * price
        order.update(status="filled", filled_qty=str(q), filled_avg_price=str(price))
        self.fill_log.append({"symbol": sym, "side": order["side"], "qty": str(q), "price": str(price),
                              "transaction_time": self.now().isoformat(), "order_id": order["id"]})
        for kid in order.get("_kids", []):
            if self.o[kid]["status"] == "held":
                self.o[kid]["status"] = "new"

    def _view(self, oid):
        o = copy.deepcopy(self.o[oid])
        o["legs"] = [copy.deepcopy(self.o[k]) for k in o.pop("_kids", [])]
        o.pop("_parent", None)
        o.pop("_t", None)
        return o

    # ---- trading API ----
    def account(self):
        eq = self.cash + sum(p["qty"] * self.px[s] for s, p in self.pos.items())
        return {"equity": str(eq), "last_equity": str(self.last_equity)}

    def calendar(self, start, end):
        out, d = [], start if isinstance(start, dt.date) else dt.date.fromisoformat(start)
        end = end if isinstance(end, dt.date) else dt.date.fromisoformat(end)
        while d <= end:
            if sessions.is_trading_day(d):
                out.append({"date": d.isoformat(), "open": "09:30",
                            "close": "13:00" if d.isoformat() in self.half_days or sessions.is_half_day(d) else "16:00"})
            d += dt.timedelta(days=1)
        return out

    def positions(self):
        return [{"symbol": s, "qty": str(p["qty"]), "current_price": str(self.px[s]), "avg_entry_price": str(p["avg"]),
                 "unrealized_pl": str((self.px[s] - p["avg"]) * p["qty"])} for s, p in self.pos.items()]

    def submit(self, order):
        self.submitted.append(order)
        oid = self._id()
        o = {"id": oid, "client_order_id": order.get("client_order_id") or oid, "symbol": order["symbol"],
             "qty": order["qty"], "side": order["side"], "type": order["type"], "status": "new",
             "stop_price": order.get("stop_price"), "limit_price": order.get("limit_price"),
             "filled_qty": "0", "filled_avg_price": None, "_kids": []}
        if order["side"] == "buy" and any(x["symbol"] == order["symbol"] and x["side"] == "sell" and
                                          x["status"] in ("new", "held") for x in self.o.values()):
            raise AssertionError("potential wash trade: buy while a sell order rests")   # Alpaca rejects this
        sells = sum(int(x["qty"]) for x in self.o.values() if x["symbol"] == order["symbol"] and x["side"] == "sell"
                    and x["status"] == "new" and x["type"] != "market")
        if order["side"] == "sell" and sells + int(order["qty"]) > self.pos.get(order["symbol"], {}).get("qty", 0):
            raise AssertionError("sell orders would exceed the position")
        o["_t"] = self.now().isoformat()
        self.o[oid] = o
        for kind, key in (("stop_loss", "stop"), ("take_profit", "limit")):
            if kind in order:
                kid = self._id()
                self.o[kid] = {"id": kid, "client_order_id": f"{o['client_order_id']}-{key}", "symbol": order["symbol"],
                               "qty": order["qty"], "side": "sell", "type": key, "status": "held",
                               "stop_price": order[kind].get("stop_price"), "limit_price": order[kind].get("limit_price"),
                               "filled_qty": "0", "filled_avg_price": None, "_parent": oid}
                o["_kids"].append(kid)
        if order["type"] == "market":
            self._fill(o, self.px[order["symbol"]])
        return self._view(oid)

    def order(self, oid):
        return self._view(oid)

    def orders(self, status="open", after=None, symbols=None, limit=500):
        out = []
        for oid, o in self.o.items():
            if "_parent" in o or (symbols and o["symbol"] not in symbols):
                continue
            kids_open = any(self.o[k]["status"] not in TERMINAL for k in o["_kids"])
            if after and o.get("_t", "") < after:
                continue
            if status == "open" and o["status"] in TERMINAL and not kids_open:
                continue
            out.append(self._view(oid))
        return out

    def replace(self, oid, **fields):
        old = self.o[oid]
        assert old["status"] not in TERMINAL, "replace of a closed order"
        new = dict(old, id=self._id(), **{k: str(v) for k, v in fields.items()})
        old["status"] = "replaced"
        self.o[new["id"]] = new
        if "_parent" in old:
            par = self.o[old["_parent"]]
            par["_kids"] = [new["id"] if k == oid else k for k in par["_kids"]]
        return copy.deepcopy({k: v for k, v in new.items() if not k.startswith("_")})

    def cancel(self, oid):
        o = self.o.get(oid)
        if not o or o["status"] in TERMINAL:
            return None
        o["status"] = "canceled"

    def fills(self, after):
        return [f for f in self.fill_log if f["transaction_time"] >= after]

    # ---- the market moves ----
    def move(self, sym, price, high=None, low=None):
        high, low = max(high or price, price), min(low or price, price)
        self.px[sym] = price
        for oid, o in list(self.o.items()):
            if o["symbol"] != sym or o["status"] != "new" or o["type"] not in ("stop", "limit"):
                continue
            hit = None
            if o["type"] == "stop" and low <= float(o["stop_price"]):
                hit = min(float(o["stop_price"]), high)
            elif o["type"] == "limit" and high >= float(o["limit_price"]):
                hit = float(o["limit_price"])
            if hit is not None:
                self._fill(o, hit)
                for sib in (self.o[o["_parent"]]["_kids"] if "_parent" in o else []):   # bracket legs: OCO
                    if sib != oid and self.o[sib]["status"] not in TERMINAL:
                        self.o[sib]["status"] = "canceled"


class FakeMarket:
    """Serves bars the test sets; the delayed cutoff is 'now - 16 min' like the free plan."""

    def __init__(self, api, clock, bars=None, hist=None, news=()):
        self.api, self.clock = api, clock
        self.bars = bars or {}
        self.h = hist or {}
        self.items = list(news)

    def today(self, symbols, day):
        now = self.clock()
        cut = now - dt.timedelta(minutes=16)
        bars = {s: [b for b in self.bars.get(s, []) if b["t"] <= now] for s in symbols}
        last = {s: (self.api.px[s], now) for s in symbols if s in self.api.px}
        return bars, f"{cut.hour:02d}:{cut.minute:02d}", last

    def hist5(self, symbols, day):
        return {s: self.h.get(s, []) for s in symbols}

    def news(self, symbols, start, end):
        return self.items

    def _sip_end(self, t):
        return t

    def _get(self, symbols, tf, start, end, **kw):
        return {s: self.bars.get(s, []) for s in symbols}


def add_daily_methods(mk, daily, pre_today):
    mk.daily = lambda symbols, day: {s: daily[s] for s in symbols if s in daily}
    mk.premarket = lambda symbols, day, upto="09:00": {s: pre_today.get(s, []) for s in symbols}
    return mk

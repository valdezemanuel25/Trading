"""Minimal Alpaca REST client (stdlib only). Paper trading only unless TJL_LIVE is set on purpose."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import settings as S


class AlpacaError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class Alpaca:
    def __init__(self, key=None, secret=None, trade_url=None, data_url=S.DATA_URL, timeout=20):
        self.key = key or os.environ.get("ALPACA_KEY_ID")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY")
        if not self.key or not self.secret:
            raise AlpacaError("ALPACA_KEY_ID / ALPACA_SECRET_KEY are not set")
        self.t = (trade_url or os.environ.get("ALPACA_TRADE_URL") or S.PAPER_URL).rstrip("/")
        if self.t != S.PAPER_URL and os.environ.get("TJL_LIVE") != "I-UNDERSTAND-THIS-IS-REAL-MONEY":
            raise AlpacaError(f"refusing to trade on {self.t}: this bot is paper only")
        self.d = data_url.rstrip("/")
        self.timeout = timeout

    def _req(self, method, url, params=None, body=None, retries=4):
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=data, method=method, headers={
                "APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")[:500]
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise AlpacaError(f"{method} {url.split('?')[0]} -> {e.code}: {text}", e.code) from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise AlpacaError(f"{method} {url.split('?')[0]} -> {e}") from None

    # ---- trading ----
    def account(self):
        return self._req("GET", f"{self.t}/v2/account")

    def clock(self):
        return self._req("GET", f"{self.t}/v2/clock")

    def calendar(self, start, end):
        return self._req("GET", f"{self.t}/v2/calendar", {"start": str(start), "end": str(end)})

    def positions(self):
        return self._req("GET", f"{self.t}/v2/positions")

    def orders(self, status="open", after=None, symbols=None, limit=500):
        return self._req("GET", f"{self.t}/v2/orders", {"status": status, "after": after, "limit": limit,
                                                        "nested": "true", "direction": "asc",
                                                        "symbols": ",".join(symbols) if symbols else None})

    def order(self, oid):
        return self._req("GET", f"{self.t}/v2/orders/{oid}", {"nested": "true"})

    def submit(self, order):
        return self._req("POST", f"{self.t}/v2/orders", body=order, retries=1)   # never blind-retry an order

    def replace(self, oid, **fields):
        return self._req("PATCH", f"{self.t}/v2/orders/{oid}", body={k: str(v) for k, v in fields.items()}, retries=1)

    def cancel(self, oid):
        try:
            return self._req("DELETE", f"{self.t}/v2/orders/{oid}", retries=2)
        except AlpacaError as e:
            if e.code in (404, 422):      # already filled / canceled
                return None
            raise

    def fills(self, after):
        out, token = [], None
        while True:
            page = self._req("GET", f"{self.t}/v2/account/activities/FILL",
                             {"after": after, "direction": "asc", "page_size": 100, "page_token": token})
            out += page or []
            if not page or len(page) < 100:
                return out
            token = page[-1]["id"]

    # ---- market data ----
    def bars(self, symbols, timeframe, start, end, feed, adjustment="raw"):
        out, token = {}, None
        while True:
            page = self._req("GET", f"{self.d}/v2/stocks/bars", {
                "symbols": ",".join(symbols), "timeframe": timeframe, "start": start, "end": end, "feed": feed,
                "adjustment": adjustment, "limit": 10000, "sort": "asc", "page_token": token})
            for sym, bars in (page.get("bars") or {}).items():
                out.setdefault(sym, []).extend(bars)
            token = page.get("next_page_token")
            if not token:
                return out

    def latest_trades(self, symbols, feed):
        page = self._req("GET", f"{self.d}/v2/stocks/trades/latest", {"symbols": ",".join(symbols), "feed": feed})
        return page.get("trades") or {}

    def news(self, symbols, start, end, limit=50):
        page = self._req("GET", f"{self.d}/v1beta1/news", {"symbols": ",".join(symbols), "start": start, "end": end,
                                                          "limit": limit, "sort": "desc"})
        return page.get("news") or []

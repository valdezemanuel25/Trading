"""Market data for the bot, as the plain bar dicts tjl/ uses (oldest first, ET times, session labels).

Free plan (FEED "iex"): consolidated SIP bars are used up to now - 16 min (volume, premarket high, RVOL);
the newest minutes come from IEX bars and the IEX last trade (price only). With FEED "sip" there is no delay.
"""
import datetime as dt

from tjl.webull import ET

from . import settings as S


def _ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _session(t):
    m = t.hour * 60 + t.minute
    if 4 * 60 <= m < 9 * 60 + 30:
        return "PRE"
    if 9 * 60 + 30 <= m < 16 * 60:
        return "RTH"
    if 16 * 60 <= m < 20 * 60:
        return "ATH"
    return "OVN"


def to_bars(raw, daily=False):
    out = []
    for b in raw:
        t = _ts(b["t"]).astimezone(ET)
        out.append({"t": t, "date": t.date(), "open": float(b["o"]), "high": float(b["h"]), "low": float(b["l"]),
                    "close": float(b["c"]), "volume": float(b.get("v") or 0), "session": "" if daily else _session(t)})
    return sorted(out, key=lambda b: b["t"])


def _iso(t):
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def et(day, hhmm):
    hh, mm = map(int, hhmm.split(":"))
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET)


class Market:
    def __init__(self, api, feed=S.FEED, delay_min=S.SIP_DELAY_MIN, clock=None):
        self.api, self.feed, self.delay = api, feed, dt.timedelta(minutes=delay_min)
        self.clock = clock or (lambda: dt.datetime.now(ET))

    def _sip_end(self, want):
        return min(want, self.clock() - self.delay - dt.timedelta(seconds=30))

    def _get(self, symbols, tf, start, end, feed="sip", daily=False, adjustment="raw"):
        out = {}
        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i + 50]
            raw = self.api.bars(chunk, tf, _iso(start), _iso(end), feed, adjustment)
            out.update({s: to_bars(v, daily) for s, v in raw.items()})
        return out

    def daily(self, symbols, day, days=400):
        """Daily bars through the session before `day` (split-adjusted)."""
        return self._get(symbols, "1Day", et(day, "00:00") - dt.timedelta(days=days), et(day, "00:00") - dt.timedelta(minutes=1),
                         daily=True, adjustment="split")

    def hist5(self, symbols, day, sessions_back=25):
        """Consolidated 5m bars (PRE + RTH) for the ~15 sessions before `day` (calendar padding included)."""
        return self._get(symbols, "5Min", et(day, "04:00") - dt.timedelta(days=sessions_back), et(day, "00:00"))

    def premarket(self, symbols, day, upto="09:00"):
        """Today's consolidated PRE bars up to `upto` (or as late as the delay allows)."""
        end = self._sip_end(et(day, upto))
        if end <= et(day, "04:00"):
            return {}
        return self._get(symbols, "5Min", et(day, "04:00"), end)

    def today(self, symbols, day):
        """Today's 5m bars up to now, the cutoff (ET HH:MM) up to which volume is consolidated, and last prices."""
        now = self.clock()
        sip_end = self._sip_end(now)
        bars = self._get(symbols, "5Min", et(day, "04:00"), sip_end) if sip_end > et(day, "04:00") else {}
        if self.feed != "sip":
            recent = self._get(symbols, "5Min", sip_end - dt.timedelta(minutes=5), now, feed="iex")
            for s, rb in recent.items():
                have = {b["t"] for b in bars.get(s, [])}
                bars.setdefault(s, []).extend(b for b in rb if b["t"] not in have)
                bars[s].sort(key=lambda b: b["t"])
        last = self.last(symbols)
        for s, (px, _ts_) in last.items():
            if px:
                _with_current_bar(bars.setdefault(s, []), now, px)
        cutoff = sip_end.astimezone(ET)
        return bars, f"{cutoff.hour:02d}:{cutoff.minute:02d}", last

    def last(self, symbols):
        raw = self.api.latest_trades(symbols, self.feed)
        return {s: (float(v["p"]), _ts(v["t"])) for s, v in raw.items()}

    def news(self, symbols, start, end):
        return self.api.news(symbols, _iso(start), _iso(end))


def _with_current_bar(bars, now, px):
    """Make the in-progress 5m bar end at the latest trade, so tjl.trigger.chart sees the price now."""
    start = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
    if bars and bars[-1]["t"] == start:
        b = bars[-1]
        b["close"] = px
        b["high"], b["low"] = max(b["high"], px), min(b["low"], px)
    elif not bars or bars[-1]["t"] < start:
        bars.append({"t": start, "date": start.date(), "open": px, "high": px, "low": px, "close": px,
                     "volume": 0.0, "session": _session(start)})

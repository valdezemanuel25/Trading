"""CLI for the Trend Join Long paper-test routines. See docs/tjl-routines.md.

  python3 -m tjl after-close --stocks F1 F2 ... --etfs F --snapshot F [--earnings "CRWD:2026-12-01 post,..."] [--asof D]
  python3 -m tjl morning --state runs/tjl/<D>/after_close.json --snapshot F --pre F [--now HH:MM] [--date D]
  python3 -m tjl trigger TICKER --state runs/tjl/<D>/morning.json --bars5 F [--hist5 F] --liquid-price P ...
  python3 -m tjl shadow --trade runs/tjl/<D>/trigger-<T>.json --bars5 F
  python3 -m tjl check --trade runs/tjl/<D>/trigger-<T>.json --bars5 F --now HH:MM --qty Q --stop S --liquid-price P
  python3 -m tjl audit --rows F   (Notion SQL result of SELECT * on TJL Trades)

Each command prints a markdown report and writes JSON + markdown under runs/tjl/<date>/.
"""
import argparse
import json
import os
import sys

from . import after_close, audit, dashboard, manage, morning, shadow, trigger
from .webull import load_bars, load_snapshot

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _save(day, name, state, md, out_dir=None):
    d = out_dir or os.path.join(ROOT, "runs", "tjl", day)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{name}.json"), "w") as f:
        json.dump(state, f, indent=1, default=str)
    with open(os.path.join(d, f"{name}.md"), "w") as f:
        f.write(md + "\n")
    return d


def _earnings(s):
    out = {}
    for part in filter(None, (s or "").split(",")):
        t, _, rest = part.strip().partition(":")
        out[t.strip().upper()] = rest.strip()
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="tjl")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("after-close")
    a.add_argument("--stocks", nargs="+", required=True, help="saved get_stock_bars (D, count 260) files")
    a.add_argument("--etfs", nargs="+", required=True, help="saved get_stock_bars for SPY + sector ETFs")
    a.add_argument("--snapshot", nargs="+", required=True)
    a.add_argument("--earnings", default="", help='"TICKER:when,..." from Liquid upcoming_earnings')
    a.add_argument("--asof", help="replay: use bars up to this date")
    a.add_argument("--out")

    m = sub.add_parser("morning")
    m.add_argument("--state", required=True, help="after_close.json of the prior session")
    m.add_argument("--snapshot", nargs="+", required=True, help="get_stock_snapshot with extend_hour_required")
    m.add_argument("--pre", nargs="*", default=[], help="get_stock_bars M5 PRE (15 days) for the gappers")
    m.add_argument("--date", help="session date (default: next session in the state)")
    m.add_argument("--now", help="ET clock time HH:MM for the RVOL window (default: last premarket bar)")
    m.add_argument("--out")

    t = sub.add_parser("trigger")
    t.add_argument("ticker")
    t.add_argument("--state", required=True, help="morning.json of the day")
    t.add_argument("--bars5", nargs="+", required=True, help="get_stock_bars M5 PRE,RTH for today")
    t.add_argument("--hist5", nargs="*", default=[], help="get_stock_bars M5 RTH, 15 sessions (RVOL for B)")
    t.add_argument("--liquid-price", type=float, required=True, help="Liquid mark price now")
    t.add_argument("--now", help="ET clock time HH:MM (default: time of the last bar)")
    t.add_argument("--day-pnl", type=float, default=0.0, help="today's Trend Join P&L so far (realized + open)")
    t.add_argument("--trades-today", type=int, default=0)
    t.add_argument("--prev-version", choices=["A", "B"], help="version of the last real trade (for alternation)")
    t.add_argument("--catalyst", choices=["yes", "no"], default="no", help="box 6, judged by Claude")
    t.add_argument("--catalyst-text", default="")
    t.add_argument("--catalyst-type", default="None")
    t.add_argument("--sz-decimals", type=int, default=2, help="Liquid size decimals of the market")
    t.add_argument("--max-lev", type=int, default=10, help="Liquid max leverage of the market")
    t.add_argument("--out")

    s = sub.add_parser("shadow")
    s.add_argument("--trade", required=True, help="trigger-<T>.json")
    s.add_argument("--bars5", nargs="+", required=True, help="get_stock_bars M5 RTH for the trade day")
    s.add_argument("--version", choices=["A", "B"], help="default: the shadow version in the trade file")
    s.add_argument("--out")

    c = sub.add_parser("check")
    c.add_argument("--trade", required=True, help="trigger-<T>.json")
    c.add_argument("--bars5", nargs="+", required=True, help="get_stock_bars M5 PRE,RTH for today")
    c.add_argument("--now", required=True, help="ET clock time HH:MM")
    c.add_argument("--qty", type=float, required=True, help="position size in coins (get_portfolio)")
    c.add_argument("--stop", type=float, required=True, help="current stop on Liquid")
    c.add_argument("--liquid-price", type=float, required=True)
    c.add_argument("--fill", type=float, help="actual entry fill on Liquid")
    c.add_argument("--sz-decimals", type=int, default=2)
    c.add_argument("--date", help="today, if the position was carried from an earlier day")
    c.add_argument("--out")

    u = sub.add_parser("audit")
    u.add_argument("--rows", required=True, help="saved Notion query result (JSON with 'results')")
    u.add_argument("--date", help="today (default: system date)")
    u.add_argument("--out")

    b = sub.add_parser("dashboard", help="build status.json + plan.json for the Trend Join Tracker dashboard")
    b.add_argument("--state", required=True, help="after_close.json")
    b.add_argument("--morning", help="morning.json of the next session, once run")
    b.add_argument("--rsi2", default="", help='"sp=56.0:EXIT,nq=39.0:NONE"')
    b.add_argument("--out", default=os.path.join(ROOT, "runs", "tjl", "dashboard"))

    args = p.parse_args(argv)
    if args.cmd == "dashboard":
        rs = {}
        for part in filter(None, args.rsi2.split(",")):
            k, _, v = part.partition("=")
            val, _, act = v.partition(":")
            rs[k], rs[k + "_action"] = float(val), act
        ac = json.load(open(args.state))
        mo = json.load(open(args.morning)) if args.morning else None
        status, rows = dashboard.build(ac, mo, rs)
        dashboard.write(args.out, status, rows, os.path.relpath(args.morning or args.state, ROOT))
        print(json.dumps(status[0], indent=1)); print(json.dumps(rows, indent=1))
        return
    if args.cmd == "after-close":
        st = after_close.run(load_bars(args.stocks), load_bars(args.etfs), load_snapshot(args.snapshot),
                             _earnings(args.earnings), args.asof)
        md = after_close.report(st)
        d = _save(st["session"], "after_close", st, md, args.out)
    elif args.cmd == "morning":
        prev = json.load(open(args.state))
        st = morning.run(prev, load_snapshot(args.snapshot), load_bars(args.pre) if args.pre else {},
                         args.date, args.now)
        md = morning.report(st)
        d = _save(st["date"], "morning", st, md, args.out)
    elif args.cmd == "trigger":
        ms = json.load(open(args.state))
        st = trigger.run(args.ticker.upper(), ms, load_bars(args.bars5), load_bars(args.hist5) if args.hist5 else {},
                         args.liquid_price, now=args.now, day_pnl=args.day_pnl, trades_today=args.trades_today,
                         prev_version=args.prev_version, catalyst=args.catalyst == "yes",
                         catalyst_text=args.catalyst_text, catalyst_type=args.catalyst_type,
                         sz_decimals=args.sz_decimals, max_lev=args.max_lev)
        md = trigger.report(st)
        d = _save(st["date"], f"trigger-{st['ticker']}", st, md, args.out)
    elif args.cmd == "check":
        tr = json.load(open(args.trade))
        st = manage.run(tr, load_bars(args.bars5), args.now, args.qty, args.stop, args.liquid_price,
                        args.fill, args.sz_decimals, args.date)
        md = manage.report(st)
        d = _save(st["date"], f"check-{st['ticker']}-{args.now.replace(':', '')}", st, md, args.out)
    elif args.cmd == "audit":
        import datetime as _dt
        data = json.load(open(args.rows))
        rows = data["results"] if isinstance(data, dict) else data
        st = audit.run(rows, _dt.date.fromisoformat(args.date) if args.date else None)
        md = audit.report(st)
        d = _save(st["date"], "audit", st, md, args.out)
    else:
        tr = json.load(open(args.trade))
        st = shadow.run(tr, load_bars(args.bars5), args.version)
        md = shadow.report(st)
        d = _save(st["date"], f"shadow-{st['ticker']}-{st['version']}", st, md, args.out)
    print(md)
    print(f"\n(saved in {os.path.relpath(d, ROOT)})", file=sys.stderr)


if __name__ == "__main__":
    main()

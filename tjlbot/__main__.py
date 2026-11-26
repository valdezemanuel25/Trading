"""python3 -m tjlbot auto   [--state DIR] [--no-sync]   one scheduled job (GitHub Actions)
   python3 -m tjlbot status [--state DIR]               account, positions, today's plan
   python3 -m tjlbot crosscheck --state DIR --date D --snapshot F [F ...] --pre F [F ...]
        compare the bot's 9:15 scan with Webull data (saved get_stock_snapshot / get_stock_bars M5 PRE results);
        writes runs/tjl-bot/<D>/crosscheck.md and .json under DIR. Needs no Alpaca keys.
"""
import argparse
import json
import os


def main(argv=None):
    p = argparse.ArgumentParser(prog="tjlbot")
    p.add_argument("cmd", choices=["auto", "status", "crosscheck"])
    p.add_argument("--state", default=os.environ.get("TJL_STATE_DIR", "state"))
    p.add_argument("--no-sync", action="store_true")
    p.add_argument("--date")
    p.add_argument("--snapshot", nargs="*", default=[])
    p.add_argument("--pre", nargs="*", default=[])
    a = p.parse_args(argv)
    if a.cmd == "crosscheck":
        from tjl.webull import load_bars, load_snapshot
        from . import crosscheck
        day_dir = os.path.join(a.state, "runs", "tjl-bot", a.date)
        st = crosscheck.run(day_dir, load_snapshot(a.snapshot) if a.snapshot else {},
                            load_bars(a.pre) if a.pre else {}, a.date)
        md = crosscheck.report(st)
        os.makedirs(day_dir, exist_ok=True)
        with open(os.path.join(day_dir, "crosscheck.json"), "w") as f:
            json.dump(st, f, indent=1, default=str)
        with open(os.path.join(day_dir, "crosscheck.md"), "w") as f:
            f.write(md + "\n")
        print(md)
        return

    from .broker import Alpaca
    from .engine import Bot
    from .market import Market
    from .sync import GitSync
    api = Alpaca()
    bot = Bot(api, Market(api), a.state, sync=None if a.no_sync else GitSync(a.state))
    if a.cmd == "auto":
        bot.auto()
    else:
        acct = api.account()
        print(json.dumps({"equity": acct["equity"], "last_equity": acct["last_equity"],
                          "positions": [(x["symbol"], x["qty"], x["unrealized_pl"]) for x in api.positions()],
                          "day": bot.daily, "open_trades": [t["id"] for t in bot.trades("open")]}, indent=1, default=str))


if __name__ == "__main__":
    main()

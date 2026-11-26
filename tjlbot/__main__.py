"""python3 -m tjlbot auto   [--state DIR] [--no-sync]   one scheduled job (GitHub Actions)
   python3 -m tjlbot status [--state DIR]               account, positions, today's plan
"""
import argparse
import json
import os

from .broker import Alpaca
from .engine import Bot, _load
from .market import Market
from .sync import GitSync


def main(argv=None):
    p = argparse.ArgumentParser(prog="tjlbot")
    p.add_argument("cmd", choices=["auto", "status"])
    p.add_argument("--state", default=os.environ.get("TJL_STATE_DIR", "state"))
    p.add_argument("--no-sync", action="store_true")
    a = p.parse_args(argv)
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

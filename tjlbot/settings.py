"""Bot settings. Rule numbers live in tjl/config.py (from docs/intraday-stock-research.md); these are the
bot's own operating limits."""
import os

from tjl import config as C

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"
# "iex": Alpaca's free plan (real-time IEX prices; consolidated SIP volume only 15+ min late).
# "sip": paid Algo Trader Plus plan (real-time consolidated data, no delay).
FEED = os.environ.get("TJL_FEED", "iex")
SIP_DELAY_MIN = 0 if FEED == "sip" else 16

# --- hard limits (user 2026-11-26: "Daily loss is max $500 no matter what") ---
DAILY_MAX_LOSS = 500          # day P&L (equity vs last close, realized + open) never planned below -$500
MIN_RISK = 50                 # skip a trade if the remaining daily budget is smaller than this
MAX_OPEN_POSITIONS = 2        # carried positions count
MAX_ORDERS_PER_DAY = 40       # runaway-loop guard
NOTIONAL_CAP = C.MARGIN_CAP * C.LEV_MAX     # $25,000, same cap as the Liquid plan ($2,500 margin at 10x)
TEST_DRAWDOWN_PAUSE = -3000   # go/no-go: pause new trades at -$3,000 from the test's starting equity
CARRY_MAX_NOTIONAL = 5000     # overnight: carry only if a 10% gap would cost <= $500 (see docs/tjl-bot.md)

# --- clock (ET minutes after midnight) ---
SCAN_AT = 9 * 60 + 15         # premarket scan; uses consolidated data up to 9:00 (the doc's 9:00 morning check)
PM_DATA_TO = "09:00"
MORNING_END = 14 * 60 + 15    # morning job hands over to the afternoon job (GitHub Actions 6-hour job limit)
FLATTEN_AT = 15 * 60 + 50     # closes go out at 15:50 so the position is flat by 15:51
DAY_END = 16 * 60 + 15
EOD_AT = 16 * 60 + 12         # consolidated 5m bars through 15:55 are available by then on the free plan
LOOP_SECONDS = 30
STALE_TRADE_SEC = 180         # no entry on a price older than this
GIT_SYNC_SECONDS = 600

ETFS = ["SPY", "QQQ", "SMH", "IGV", "XLE", "XBI"]

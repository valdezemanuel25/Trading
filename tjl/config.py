"""Trend Join Long (TJL) paper test: fixed settings and the screening universe.

Source of truth for every number here: docs/intraday-stock-research.md.
Change a rule there first, then here.
"""

# --- Accounts and sizing ($25k sizing base on the shared $10k Liquid paper account) ---
SIZING_BASE = 25_000
RISK_APLUS = 500          # A+ (all 9 boxes)
RISK_NORMAL = 250         # everything else that passes the core rules
MARGIN_CAP = 2_500        # per position
LEV_MIN, LEV_MAX = 2, 10
MAX_TRADES_PER_DAY = 2
DAILY_LOSS_LIMIT = -500   # realized + open, Trend Join trades only
FEE_ROUND_TRIP_EST = 0.0015   # 0.15% of notional, estimate until the first paper fills confirm it

# --- Rule thresholds ---
MIN_PRICE = 5.0
MIN_MCAP = 1e9
MIN_AVG_VOL = 1_000_000          # shares, 20-day average
MIN_ADR_CORE = 0.03              # step 1: not range-bound
GAP_MIN = 0.03                   # step 2
PM_VOL_MIN = 20_000              # premarket shares
RVOL_A = 1.5                     # version A: premarket RVOL > 1.5
RVOL_B = 2.0                     # version B: intraday RVOL >= 2.0 (14-day lookback)
RVOL_LOOKBACK = 14
MIN_RVOL_DAYS = 10                # fewer prior sessions than this -> RVOL unknown (fails)
# A+ boxes
ADR_APLUS = 0.04
DOLLAR_VOL_APLUS = 5e9
MCAP_APLUS = 100e9
EXT_MAX = 0.10                   # <= 10% above the 20-day SMA
POS52_MIN = 0.80                 # >= 80% of the 52-week range ...
FROM_HIGH_MAX = 0.15             # ... or within 15% of the 52-week high
HOT_GROUPS = 2
# SPY regime
REGIME_MIN_DIST = 0.01           # close at least 1% from its 20-day SMA
REGIME_SLOPE_DAYS = 5

# --- Session times (ET, minutes after midnight) ---
WINDOW = {"A": (10 * 60, 15 * 60 + 30), "B": (10 * 60 + 5, 15 * 60 + 30)}
FLAT_BY = 15 * 60 + 51          # close by here unless the overnight rule says carry
CARRY_CHECK = 15 * 60 + 45      # overnight decision time (user allowed overnight holds 2026-11-26)
MORNING_CHECK = 9 * 60          # morning check runs at 9:00 ET (30 min before the open; user 2026-11-26)
RTH_OPEN, RTH_CLOSE = 9 * 60 + 30, 16 * 60

VERSION_NAME = {"A": "A: TJL-report", "B": "B: TJL-bot"}

# --- External ids ---
WEBULL_WATCHLIST_ID = "469684da9c224d59978706608a36c55a"   # "Trend Join"
NOTION_DATA_SOURCE = "collection://424af207-66ae-8152-bcb1-000b322dc897"  # "TJL Trades"

BOX_NAMES = {
    1: "1 Core + morning rules",
    2: "2 ADR20 4%+",
    3: "3 Dollar volume $5B+",
    4: "4 Market cap $100B+",
    5: "5 Hot sector top 2",
    6: "6 Real catalyst",
    7: "7 Not extended (20d SMA 10% or less)",
    8: "8 Upper 52-week range",
    9: "9 SPY trending",
}

# --- Universe: Liquid's US-listed single stocks with market cap >= $1B (checked on Webull 2026-11-26) ---
# ticker -> Liquid symbol. Excluded: ETFs/leveraged ETFs, non-US listings, pre-IPO markets,
# STRC (preferred stock), QNT (Liquid/Webull mapping unverified), names under $1B (GPRO, SHAZ, BOT, ...).
_PARA = {"COHR", "SMCI", "CRDO", "TER", "STX", "SOFI", "MELI", "VST", "CIEN", "CIFR"}
_IO = {"IONQ"}

GROUPS = {
    "Semis": ["NVDA", "AMD", "AVGO", "MRVL", "INTC", "QCOM", "ARM", "TSM", "ASML", "LRCX", "AMAT",
              "TER", "UMC", "CRDO"],
    "Memory/storage": ["MU", "SNDK", "WDC", "STX"],
    "AI hardware/optical": ["LITE", "COHR", "CIEN", "AAOI", "GLW", "DELL", "SMCI", "NOK"],
    "AI cloud": ["CRWV", "NBIS", "CBRS"],
    "Software": ["MSFT", "ORCL", "NOW", "CRWD", "PANW", "NET", "PLTR", "ZM", "IBM"],
    "Internet": ["GOOGL", "META", "AMZN", "NFLX", "RDDT", "BABA", "MELI", "EBAY", "DKNG", "TTWO"],
    "Crypto-linked": ["COIN", "MSTR", "HOOD", "IREN", "CIFR", "CRCL", "BMNR"],
    "Energy/power": ["CVX", "VST", "GEV", "BE"],
    "Health": ["LLY", "MRNA", "HIMS", "TWST"],
    "Consumer/auto": ["AAPL", "TSLA", "COST", "RIVN", "GME"],
    "Financials": ["ICE", "BX", "SOFI"],
    "Space/quantum/other": ["RKLB", "IONQ", "USAR", "BB"],
}
GROUP_ETF = {"Semis": "SMH", "Software": "IGV", "Energy/power": "XLE", "Health": "XBI"}
MIN_GROUP_SIZE = 3   # groups smaller than this can't be "hot"

TICKER_GROUP = {t: g for g, ts in GROUPS.items() for t in ts}
UNIVERSE = sorted(TICKER_GROUP)


def liquid_symbol(ticker):
    if ticker in _PARA:
        return f"para:{ticker}"
    if ticker in _IO:
        return f"io:{ticker}"
    return f"xyz:{ticker}"

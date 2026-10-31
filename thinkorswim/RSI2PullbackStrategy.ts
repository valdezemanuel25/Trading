# RSI(2) Pullback - LONG ONLY strategy for a /ES DAILY chart (thinkorswim Strategy, for Show Report backtests)
#
# Higher-timeframe filter: close above its 200-day average (long-term uptrend).
# Buy at the close when the 2-day RSI is below 10 (a short, sharp dip).
# Sell at the close when price closes back above its 5-day average.
# Backtest (research/rsi2.py, ES 2020-2026, 1 ES, $30/trade): 2020-23 +$28,500, 2024-25 +$56,800, 2026 +$21,200.
# No stop: losers are held until price closes above the 5-day average (worst trade in the test: -148 pts).
#
# Note: ToS /ES continuous is not roll-adjusted; a roll gap can distort RSI(2) for a day. The backtest used
# roll-adjusted closes.

input rsiLength = 2;
input rsiEntry = 10;
input useTrendFilter = yes;
input trendLength = 200;
input exitLength = 5;
input contracts = 1;

def c = close;
def r = RSI(length = rsiLength);
def trendOK = !useTrendFilter or c > Average(c, trendLength);
def buySignal = r < rsiEntry and trendOK;
def exitSignal = c > Average(c, exitLength);

AddOrder(OrderType.BUY_TO_OPEN, buySignal, close, contracts, Color.GREEN, Color.GREEN, "RSI2 buy");
AddOrder(OrderType.SELL_TO_CLOSE, exitSignal, close, contracts, Color.RED, Color.RED, "RSI2 exit");

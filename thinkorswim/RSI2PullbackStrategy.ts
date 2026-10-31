# RSI(2) Pullback - regime strategy for a /ES DAILY chart (thinkorswim Strategy, for Show Report backtests)
#
# The 200-day average decides the side:
#   ABOVE the 200-day: LONG  when RSI(2) < 10 at the close; exit at the close once close > 5-day average.
#   BELOW the 200-day: SHORT when RSI(2) > 90 at the close; cover at the close once close < 5-day average.
#                      (only if enableShorts = yes - OFF by default, see below)
#
# Backtest (research/rsi2.py, ES, 1 ES, $30/trade, net):
#                    2020-23     2024-25     2026
#   longs only       +$28,500    +$56,800    +$21,200
#   longs + shorts   +$48,800    +$54,000     -$1,200  (one short squeeze in April 2026 lost 447 pts)
# No stops: positions are held until the exit rule. Overnight/weekend gap risk. Start with MES.
# ToS /ES continuous is not roll-adjusted; a roll gap can distort RSI(2) for a day.

input rsiLength = 2;
input rsiLongEntry = 10;
input rsiShortEntry = 90;
input trendLength = 200;
input exitLength = 5;
input enableShorts = no;
input contracts = 1;

def c = close;
def r = RSI(length = rsiLength);
def sma200 = Average(c, trendLength);
def sma5 = Average(c, exitLength);

def longSignal = c > sma200 and r < rsiLongEntry;
def longExit = c > sma5;
def shortSignal = enableShorts and c < sma200 and r > rsiShortEntry;
def shortExit = c < sma5;

AddOrder(OrderType.BUY_TO_OPEN, longSignal, close, contracts, Color.GREEN, Color.GREEN, "RSI2 long");
AddOrder(OrderType.SELL_TO_CLOSE, longExit, close, contracts, Color.RED, Color.RED, "RSI2 long exit");
AddOrder(OrderType.SELL_TO_OPEN, shortSignal, close, contracts, Color.MAGENTA, Color.MAGENTA, "RSI2 short");
AddOrder(OrderType.BUY_TO_CLOSE, shortExit, close, contracts, Color.CYAN, Color.CYAN, "RSI2 short cover");

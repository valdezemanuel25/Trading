# RSI(2) Pullback - LONG ONLY live study for a /ES DAILY chart: shows today's setup and alerts before the close.
#
# During the session the daily bar is still forming, so check it at about 15:50 ET (14:50 CT).
# If BUY SETUP is showing then, buy at the close. If EXIT is showing while you are long, sell at the close.

declare upper;

input rsiLength = 2;
input rsiEntry = 10;
input useTrendFilter = yes;
input trendLength = 200;
input exitLength = 5;

def c = close;
def r = RSI(length = rsiLength);
def sma200 = Average(c, trendLength);
def sma5 = Average(c, exitLength);
def trendOK = !useTrendFilter or c > sma200;
def buySignal = r < rsiEntry and trendOK;
def exitSignal = c > sma5;

plot Trend = sma200;
Trend.SetDefaultColor(Color.GRAY);
plot ExitLine = sma5;
ExitLine.SetDefaultColor(Color.CYAN);
ExitLine.SetStyle(Curve.SHORT_DASH);

plot BuyArrow = if buySignal then low else Double.NaN;
BuyArrow.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
BuyArrow.SetDefaultColor(Color.GREEN);
BuyArrow.SetLineWeight(3);

AddLabel(yes, "RSI(2) " + Round(r, 1) + (if trendOK then "  |  above 200d" else "  |  BELOW 200d - no longs"),
         if buySignal then Color.GREEN else Color.GRAY);
AddLabel(buySignal, "BUY SETUP - buy at the close", Color.GREEN);
AddLabel(exitSignal, "EXIT if long - sell at the close (close > 5d avg)", Color.CYAN);

Alert(buySignal, "RSI2 | BUY SETUP | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(exitSignal, "RSI2 | EXIT | Long | sell at the close if long", Alert.BAR, Sound.Chimes);

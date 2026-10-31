# RSI(2) Pullback - live regime study for a /ES DAILY chart: shows which side is allowed, today's setup and exits.
#
# Check at about 15:50 ET (14:50 CT) while the daily bar is still forming, then act at the close:
#   ABOVE 200d  -> LONG SETUP  when RSI(2) < 10        -> exit long  when close > 5-day average
#   BELOW 200d  -> SHORT SETUP when RSI(2) > 90        -> cover short when close < 5-day average
#                 (short side only shows if enableShorts = yes; it lost money in 2024-26, see the strategy file)

declare upper;

input rsiLength = 2;
input rsiLongEntry = 10;
input rsiShortEntry = 90;
input trendLength = 200;
input exitLength = 5;
input enableShorts = no;

def c = close;
def r = RSI(length = rsiLength);
def sma200 = Average(c, trendLength);
def sma5 = Average(c, exitLength);
def upTrend = c > sma200;

def longSignal = upTrend and r < rsiLongEntry;
def shortSignal = enableShorts and !upTrend and r > rsiShortEntry;
def longExit = c > sma5;
def shortExit = c < sma5;

plot Trend = sma200;
Trend.SetDefaultColor(Color.GRAY);
plot ExitLine = sma5;
ExitLine.SetDefaultColor(Color.CYAN);
ExitLine.SetStyle(Curve.SHORT_DASH);

plot LongArrow = if longSignal then low else Double.NaN;
LongArrow.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
LongArrow.SetDefaultColor(Color.GREEN);
LongArrow.SetLineWeight(3);
plot ShortArrow = if shortSignal then high else Double.NaN;
ShortArrow.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
ShortArrow.SetDefaultColor(Color.MAGENTA);
ShortArrow.SetLineWeight(3);

AddLabel(yes, (if upTrend then "ABOVE 200d - longs only" else if enableShorts then "BELOW 200d - shorts only" else "BELOW 200d - stand aside")
         + "  |  RSI(2) " + Round(r, 1), if upTrend then Color.GREEN else Color.GRAY);
AddLabel(longSignal, "LONG SETUP - buy at the close", Color.GREEN);
AddLabel(shortSignal, "SHORT SETUP - sell at the close", Color.MAGENTA);
AddLabel(longExit, "If long: EXIT at the close (close > 5d avg)", Color.CYAN);
AddLabel(enableShorts and shortExit, "If short: COVER at the close (close < 5d avg)", Color.CYAN);

Alert(longSignal, "RSI2 | LONG SETUP | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(shortSignal, "RSI2 | SHORT SETUP | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(longExit, "RSI2 | EXIT | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(enableShorts and shortExit, "RSI2 | COVER | Short | buy at the close if short", Alert.BAR, Sound.Chimes);

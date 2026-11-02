# RSI(2) Pullback - live regime study for DAILY charts: shows which side is allowed, today's setup and exits.
#
# Load on four DAILY charts: /MES, /MNQ, /M2K, /MYM, and set `market` on each.
# Check at about 15:50 ET (14:50 CT) while the daily bar is still forming, then act at the close:
#   ABOVE 200d  -> LONG SETUP  when RSI(2) < rsiLongEntry (10; 30 = about twice as many trades)        -> exit long  when close > 5-day average
#   BELOW 200d  -> SHORT SETUP when RSI(2) > 90        -> cover short when close < 5-day average
#                 (short side only shows if enableShorts = yes; it lost money in 2024-26, see the strategy file)

declare upper;

input rsiLength = 2;
input rsiLongEntry = 10;
input rsiShortEntry = 90;
input trendLength = 200;
input exitLength = 5;
input enableShorts = no;
# set once per chart so the alert says which market fired (alert text can't contain the symbol)
input market = {default MES, MNQ, M2K, MYM, ES, NQ, RTY, YM};

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

# Alerts: one fixed line per market (format RSI2 | <action> | <market> | <side> | ...) for the email -> Notion log.
# Daily bars are still forming during the day, so an alert can fire early and disappear: confirm at 15:50 ET.
def isMES = market == market.MES;
def isMNQ = market == market.MNQ;
def isM2K = market == market.M2K;
def isMYM = market == market.MYM;
def isES = market == market.ES;
def isNQ = market == market.NQ;
def isRTY = market == market.RTY;
def isYM = market == market.YM;
Alert(isMES and longSignal, "RSI2 | LONG SETUP | MES | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isMES and longExit, "RSI2 | EXIT | MES | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isMES and shortSignal, "RSI2 | SHORT SETUP | MES | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isMES and enableShorts and shortExit, "RSI2 | COVER | MES | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isMNQ and longSignal, "RSI2 | LONG SETUP | MNQ | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isMNQ and longExit, "RSI2 | EXIT | MNQ | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isMNQ and shortSignal, "RSI2 | SHORT SETUP | MNQ | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isMNQ and enableShorts and shortExit, "RSI2 | COVER | MNQ | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isM2K and longSignal, "RSI2 | LONG SETUP | M2K | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isM2K and longExit, "RSI2 | EXIT | M2K | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isM2K and shortSignal, "RSI2 | SHORT SETUP | M2K | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isM2K and enableShorts and shortExit, "RSI2 | COVER | M2K | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isMYM and longSignal, "RSI2 | LONG SETUP | MYM | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isMYM and longExit, "RSI2 | EXIT | MYM | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isMYM and shortSignal, "RSI2 | SHORT SETUP | MYM | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isMYM and enableShorts and shortExit, "RSI2 | COVER | MYM | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isES and longSignal, "RSI2 | LONG SETUP | ES | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isES and longExit, "RSI2 | EXIT | ES | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isES and shortSignal, "RSI2 | SHORT SETUP | ES | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isES and enableShorts and shortExit, "RSI2 | COVER | ES | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isNQ and longSignal, "RSI2 | LONG SETUP | NQ | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isNQ and longExit, "RSI2 | EXIT | NQ | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isNQ and shortSignal, "RSI2 | SHORT SETUP | NQ | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isNQ and enableShorts and shortExit, "RSI2 | COVER | NQ | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isRTY and longSignal, "RSI2 | LONG SETUP | RTY | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isRTY and longExit, "RSI2 | EXIT | RTY | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isRTY and shortSignal, "RSI2 | SHORT SETUP | RTY | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isRTY and enableShorts and shortExit, "RSI2 | COVER | RTY | Short | buy at the close if short", Alert.BAR, Sound.Chimes);
Alert(isYM and longSignal, "RSI2 | LONG SETUP | YM | Long | buy at the close", Alert.BAR, Sound.Ding);
Alert(isYM and longExit, "RSI2 | EXIT | YM | Long | sell at the close if long", Alert.BAR, Sound.Chimes);
Alert(isYM and shortSignal, "RSI2 | SHORT SETUP | YM | Short | sell at the close", Alert.BAR, Sound.Ding);
Alert(isYM and enableShorts and shortExit, "RSI2 | COVER | YM | Short | buy at the close if short", Alert.BAR, Sound.Chimes);

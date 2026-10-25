# Journal Triggers — thinkorswim port of pine/journal_triggers.pine
#
#  SWEEP SHORT  : stretched above value, wicked a key level, closed back below it (+ below fast EMA), CVD rolling over
#  SWEEP LONG   : mirror — swept a key level from below value, closed back above it
#  POC RECLAIM  : rotated off VAL (VAH), first close through POC with CVD agreeing
#
# Signals are shown only once the candle has CLOSED; alerts fire on the open of the next bar.
# Bookmap liquidity is not visible here — still check it before entry.

declare upper;

# ───── Session
input winStart = 0930;
input winEnd = 1130;
input profileReset = {default ETH, RTH};
input valueAreaPct = 70;

# ───── Indicators
input emaLen = 9;
input smaLen = 50;
input bbLen = 20;
input bbMult = 2.0;
input vwMult = 1.0;
input htf1Agg = AggregationPeriod.HOUR;
input htf1Len = 50;
input htf2Agg = AggregationPeriod.FOUR_HOURS;
input htf2Len = 21;
input htf3Agg = AggregationPeriod.FOUR_HOURS;
input htf3Len = 200;
input useRound = yes;
input roundStep = 50.0;

# ───── Trigger rules
input lvlTol = 1.0;
input acceptTol = 1.0;
input sweepLook = 3;
input stretchLook = 6;
input reclaimLook = 12;
input shortNeedEma = yes;
input longNeedEma = no;
input needCvd = yes;
input cvdLook = 3;
input minScore = 3;
input useReclaim = yes;

# ───── Risk
input minTgt = 6.0;
input stopBuf = 1.0;
input maxStop = 10.0;
input minRR = 1.0;
input cooldown = 6;

# ───── Display
input showKeyLevels = yes;
input showProfileVwap = no;

# ═════ Helpers
# 1 if price wicked to/through lvl, never closed more than acc above it, and is now closing below it
script SwS {
    input lvl = 0.0;
    input tol = 1.0;
    input acc = 1.0;
    input look = 3;
    plot r = if IsNaN(lvl) then 0 else if Highest(high, look) >= lvl - tol and Highest(close, look) <= lvl + acc and close < lvl then 1 else 0;
}
script SwL {
    input lvl = 0.0;
    input tol = 1.0;
    input acc = 1.0;
    input look = 3;
    plot r = if IsNaN(lvl) then 0 else if Lowest(low, look) <= lvl + tol and Lowest(close, look) >= lvl - acc and close > lvl then 1 else 0;
}
# Distance to a magnet in the trade direction, or 99999 if it is missing / closer than minD
script Dist {
    input m = 0.0;
    input below = yes;
    input minD = 6.0;
    def d = if below then close - m else m - close;
    plot r = if !IsNaN(m) and d >= minD then d else 99999;
}

# ═════ Sessions
def bn = BarNumber();
def newDay = GetYYYYMMDD() != GetYYYYMMDD()[1];
def isRTH = SecondsFromTime(0930) >= 0 and SecondsTillTime(1600) > 0;
def inWin = SecondsFromTime(winStart) >= 0 and SecondsTillTime(winEnd) > 0;
def rthOpen = isRTH and !isRTH[1];
def rthSeen = CompoundValue(1, if newDay then 0 else if isRTH then 1 else rthSeen[1], 0);

# Premarket (overnight) high / low, frozen at the cash open
def onHi = CompoundValue(1, if newDay then high else if !isRTH and !rthSeen then Max(onHi[1], high) else onHi[1], high);
def onLo = CompoundValue(1, if newDay then low else if !isRTH and !rthSeen then Min(onLo[1], low) else onLo[1], low);
def pmH = if rthSeen then onHi else Double.NaN;
def pmL = if rthSeen then onLo else Double.NaN;

# ═════ Indicators
def emaF = ExpAverage(close, emaLen);
def smaC = Average(close, smaLen);
def bbMid = Average(close, bbLen);
def bbSd = StDev(close, bbLen);
def bbUp = bbMid + bbMult * bbSd;
def bbLo = bbMid - bbMult * bbSd;

# Session VWAP with volume-weighted stdev bands (same formula as the built-in VWAP study)
def pv = CompoundValue(1, if newDay then hlc3 * volume else pv[1] + hlc3 * volume, hlc3 * volume);
def vs = CompoundValue(1, if newDay then volume else vs[1] + volume, volume);
def pv2 = CompoundValue(1, if newDay then Sqr(hlc3) * volume else pv2[1] + Sqr(hlc3) * volume, Sqr(hlc3) * volume);
def vw = if vs > 0 then pv / vs else Double.NaN;
def vwSd = if vs > 0 then Sqrt(Max(pv2 / vs - Sqr(vw), 0)) else Double.NaN;
def vwUp = vw + vwMult * vwSd;
def vwLo = vw - vwMult * vwSd;

# Higher-timeframe SMAs from completed HTF bars
def htf1 = Average(close(period = htf1Agg)[1], htf1Len);
def htf2 = Average(close(period = htf2Agg)[1], htf2Len);
def htf3 = Average(close(period = htf3Agg)[1], htf3Len);

def pdH = high(period = AggregationPeriod.DAY)[1];
def pdL = low(period = AggregationPeriod.DAY)[1];
def pwH = high(period = AggregationPeriod.WEEK)[1];
def pwL = low(period = AggregationPeriod.WEEK)[1];

def rUp = if useRound then Ceil(close / roundStep) * roundStep else Double.NaN;
def rDn = if useRound then Floor(close / roundStep) * roundStep else Double.NaN;

# Volume profile (built-in engine). NOTE: on past days TOS shows each day's FINAL POC/VA on every bar,
# so historical signals are optimistic; live signals use the developing profile.
def vpNew = if profileReset == profileReset.RTH then rthOpen else newDay;
profile vp = VolumeProfile("startNewProfile" = vpNew, "onExpansion" = no, "numberOfProfiles" = 1000, "pricePerRow" = PricePerRow.TICKSIZE, "value area percent" = valueAreaPct);
def poc = vp.GetPointOfControl();
def vah = vp.GetHighestValueArea();
def val = vp.GetLowestValueArea();
def pPOC = CompoundValue(1, if vpNew then poc[1] else pPOC[1], Double.NaN);

# CVD estimate from candle close location, reset each session
def rng = high - low;
def barDelta = if rng > 0 then volume * ((close - low) - (high - close)) / rng else 0;
def cvd = CompoundValue(1, if newDay then barDelta else cvd[1] + barDelta, barDelta);
def cvdUp = barDelta > 0 and cvd > GetValue(cvd, cvdLook);
def cvdDn = barDelta < 0 and cvd < GetValue(cvd, cvdLook);

# ═════ 1) Sweep & Reject (short)
def sPDH = SwS(pdH, lvlTol, acceptTol, sweepLook);
def sPDL = SwS(pdL, lvlTol, acceptTol, sweepLook);
def sPWH = SwS(pwH, lvlTol, acceptTol, sweepLook);
def sPWL = SwS(pwL, lvlTol, acceptTol, sweepLook);
def sPMH = SwS(pmH, lvlTol, acceptTol, sweepLook);
def sPML = SwS(pmL, lvlTol, acceptTol, sweepLook);
def sPOC = SwS(poc, lvlTol, acceptTol, sweepLook);
def sVAH = SwS(vah, lvlTol, acceptTol, sweepLook);
def sVAL = SwS(val, lvlTol, acceptTol, sweepLook);
def sPPOC = SwS(pPOC, lvlTol, acceptTol, sweepLook);
def sVW = SwS(vw, lvlTol, acceptTol, sweepLook);
def sSMA = SwS(smaC, lvlTol, acceptTol, sweepLook);
def sH1 = SwS(htf1, lvlTol, acceptTol, sweepLook);
def sH2 = SwS(htf2, lvlTol, acceptTol, sweepLook);
def sH3 = SwS(htf3, lvlTol, acceptTol, sweepLook);
def sRU = SwS(rUp, lvlTol, acceptTol, sweepLook);
def sRD = SwS(rDn, lvlTol, acceptTol, sweepLook);
def sConf = sPDH + sPDL + sPWH + sPWL + sPMH + sPML + sPOC + sVAH + sVAL + sPPOC + sVW + sSMA + sH1 + sH2 + sH3 + sRU + sRD;

def upVAH = Highest(high - vah, stretchLook) >= 0;
def upVW = Highest(high - vwUp, stretchLook) >= 0;
def upBB = Highest(high - bbUp, stretchLook) >= 0;
def sScore = sConf + upVAH + upVW + upBB + cvdDn;

def sStop = Highest(high, sweepLook) + stopBuf;
def sRisk = sStop - close;
def sTgtD = Min(Min(Min(Dist(poc, yes, minTgt), Dist(vw, yes, minTgt)), Min(Dist(val, yes, minTgt), Dist(pPOC, yes, minTgt))),
                Min(Min(Dist(bbMid, yes, minTgt), Dist(vwLo, yes, minTgt)), Min(Dist(pdL, yes, minTgt), Dist(pmL, yes, minTgt))));
def sRR = if sTgtD < 99999 and sRisk > 0 then sTgtD / sRisk else 0;
def rawSS = inWin and sConf > 0 and close < open and (!shortNeedEma or close < emaF) and (!needCvd or cvdDn) and sScore >= minScore and sRR >= minRR and sRisk <= maxStop;

# ═════ 2) Sweep & Reclaim (long)
def lPDH = SwL(pdH, lvlTol, acceptTol, sweepLook);
def lPDL = SwL(pdL, lvlTol, acceptTol, sweepLook);
def lPWH = SwL(pwH, lvlTol, acceptTol, sweepLook);
def lPWL = SwL(pwL, lvlTol, acceptTol, sweepLook);
def lPMH = SwL(pmH, lvlTol, acceptTol, sweepLook);
def lPML = SwL(pmL, lvlTol, acceptTol, sweepLook);
def lPOC = SwL(poc, lvlTol, acceptTol, sweepLook);
def lVAH = SwL(vah, lvlTol, acceptTol, sweepLook);
def lVAL = SwL(val, lvlTol, acceptTol, sweepLook);
def lPPOC = SwL(pPOC, lvlTol, acceptTol, sweepLook);
def lVW = SwL(vw, lvlTol, acceptTol, sweepLook);
def lSMA = SwL(smaC, lvlTol, acceptTol, sweepLook);
def lH1 = SwL(htf1, lvlTol, acceptTol, sweepLook);
def lH2 = SwL(htf2, lvlTol, acceptTol, sweepLook);
def lH3 = SwL(htf3, lvlTol, acceptTol, sweepLook);
def lRU = SwL(rUp, lvlTol, acceptTol, sweepLook);
def lRD = SwL(rDn, lvlTol, acceptTol, sweepLook);
def lConf = lPDH + lPDL + lPWH + lPWL + lPMH + lPML + lPOC + lVAH + lVAL + lPPOC + lVW + lSMA + lH1 + lH2 + lH3 + lRU + lRD;

def dnVAL = Lowest(low - val, stretchLook) <= 0;
def dnVW = Lowest(low - vwLo, stretchLook) <= 0;
def dnBB = Lowest(low - bbLo, stretchLook) <= 0;
def lScore = lConf + dnVAL + dnVW + dnBB + cvdUp;

def lStop = Lowest(low, sweepLook) - stopBuf;
def lRisk = close - lStop;
def lTgtD = Min(Min(Min(Dist(poc, no, minTgt), Dist(vw, no, minTgt)), Min(Dist(vah, no, minTgt), Dist(pPOC, no, minTgt))),
                Min(Min(Min(Dist(bbMid, no, minTgt), Dist(emaF, no, minTgt)), Dist(vwUp, no, minTgt)), Min(Dist(pdH, no, minTgt), Dist(pmH, no, minTgt))));
def lRR = if lTgtD < 99999 and lRisk > 0 then lTgtD / lRisk else 0;
def rawSL = inWin and lConf > 0 and close > open and (!longNeedEma or close > emaF) and (!needCvd or cvdUp) and lScore >= minScore and lRR >= minRR and lRisk <= maxStop;

# ═════ 3) POC Reclaim / POC Loss (continuation)
def crossUpPOC = close > poc and close[1] <= poc[1];
def crossDnPOC = close < poc and close[1] >= poc[1];
def fromVAL = Lowest(low - val, reclaimLook) <= lvlTol;
def fromVAH = Highest(high - vah, reclaimLook) >= -lvlTol;

def rlStop = Lowest(low, 5) - stopBuf;
def rlRisk = close - rlStop;
def rlTgtD = Min(Min(Dist(vah, no, minTgt), Dist(vw, no, minTgt)), Min(Min(Dist(vwUp, no, minTgt), Dist(pdH, no, minTgt)), Dist(pmH, no, minTgt)));
def rlRR = if rlTgtD < 99999 and rlRisk > 0 then rlTgtD / rlRisk else 0;
def rawRL = useReclaim and inWin and crossUpPOC and fromVAL and close > emaF and close > open and (!needCvd or cvdUp) and rlRR >= minRR and rlRisk <= maxStop;

def rsStop = Highest(high, 5) + stopBuf;
def rsRisk = rsStop - close;
def rsTgtD = Min(Min(Dist(val, yes, minTgt), Dist(vw, yes, minTgt)), Min(Min(Dist(vwLo, yes, minTgt), Dist(pdL, yes, minTgt)), Dist(pmL, yes, minTgt)));
def rsRR = if rsTgtD < 99999 and rsRisk > 0 then rsTgtD / rsRisk else 0;
def rawRS = useReclaim and inWin and crossDnPOC and fromVAH and close < emaF and close < open and (!needCvd or cvdDn) and rsRR >= minRR and rsRisk <= maxStop;

# ═════ Cooldown (same side)
def lastS = CompoundValue(1, if (rawSS or rawRS) and bn - lastS[1] > cooldown then bn else lastS[1], -100000);
def lastL = CompoundValue(1, if (rawSL or rawRL) and bn - lastL[1] > cooldown then bn else lastL[1], -100000);
def sweepShort = rawSS and lastS == bn;
def reclaimShort = !rawSS and rawRS and lastS == bn;
def sweepLong = rawSL and lastL == bn;
def reclaimLong = !rawSL and rawRL and lastL == bn;

# Only show a signal once its candle has closed (a newer bar exists)
def done = !IsNaN(close[-1]);

# ═════ Output
plot SweepShortSig = if sweepShort and done then high + TickSize() * 4 else Double.NaN;
SweepShortSig.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
SweepShortSig.SetDefaultColor(Color.RED);
SweepShortSig.SetLineWeight(3);

plot SweepLongSig = if sweepLong and done then low - TickSize() * 4 else Double.NaN;
SweepLongSig.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
SweepLongSig.SetDefaultColor(Color.GREEN);
SweepLongSig.SetLineWeight(3);

plot PocLossSig = if reclaimShort and done then high + TickSize() * 4 else Double.NaN;
PocLossSig.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
PocLossSig.SetDefaultColor(Color.DARK_RED);

plot PocReclaimSig = if reclaimLong and done then low - TickSize() * 4 else Double.NaN;
PocReclaimSig.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
PocReclaimSig.SetDefaultColor(Color.CYAN);

AddChartBubble(sweepShort and done, high,
    "SWEEP SHORT (" + sScore + ")\n" +
    (if sPDH then "PDH " else "") + (if sPWH then "PWH " else "") + (if sPMH then "PMH " else "") +
    (if sVAH then "VAH " else "") + (if sPOC then "POC " else "") + (if sPPOC then "pPOC " else "") +
    (if sVW then "VWAP " else "") + (if sSMA then "SMA " else "") + (if sH1 then "H1SMA " else "") +
    (if sH2 then "H2SMA " else "") + (if sH3 then "H3SMA " else "") + (if sRU or sRD then "Round " else "") +
    "\nT " + AsPrice(close - sTgtD) + "  S " + AsPrice(sStop) + "  RR " + Round(sRR, 2),
    Color.RED, yes);

AddChartBubble(sweepLong and done, low,
    "SWEEP LONG (" + lScore + ")\n" +
    (if lPDL then "PDL " else "") + (if lPWL then "PWL " else "") + (if lPML then "PML " else "") +
    (if lVAL then "VAL " else "") + (if lPOC then "POC " else "") + (if lPPOC then "pPOC " else "") +
    (if lVW then "VWAP " else "") + (if lSMA then "SMA " else "") + (if lH1 then "H1SMA " else "") +
    (if lH2 then "H2SMA " else "") + (if lH3 then "H3SMA " else "") + (if lRU or lRD then "Round " else "") +
    "\nT " + AsPrice(close + lTgtD) + "  S " + AsPrice(lStop) + "  RR " + Round(lRR, 2),
    Color.GREEN, no);

AddChartBubble(reclaimShort and done, high,
    "POC LOSS SHORT\nT " + AsPrice(close - rsTgtD) + "  S " + AsPrice(rsStop) + "  RR " + Round(rsRR, 2),
    Color.DARK_RED, yes);

AddChartBubble(reclaimLong and done, low,
    "POC RECLAIM LONG\nT " + AsPrice(close + rlTgtD) + "  S " + AsPrice(rlStop) + "  RR " + Round(rlRR, 2),
    Color.CYAN, no);

# Alerts fire on the first tick of the bar AFTER the signal candle closes
Alert(sweepShort[1], "Journal: SWEEP SHORT — check Bookmap", Alert.BAR, Sound.Ring);
Alert(sweepLong[1], "Journal: SWEEP LONG — check Bookmap", Alert.BAR, Sound.Ring);
Alert(reclaimShort[1], "Journal: POC LOSS SHORT — check Bookmap", Alert.BAR, Sound.Chimes);
Alert(reclaimLong[1], "Journal: POC RECLAIM LONG — check Bookmap", Alert.BAR, Sound.Chimes);

# ═════ Levels
plot PDHLine = if showKeyLevels then pdH else Double.NaN;
PDHLine.SetDefaultColor(Color.GRAY);
PDHLine.SetStyle(Curve.SHORT_DASH);
plot PDLLine = if showKeyLevels then pdL else Double.NaN;
PDLLine.SetDefaultColor(Color.GRAY);
PDLLine.SetStyle(Curve.SHORT_DASH);
plot PMHLine = if showKeyLevels then pmH else Double.NaN;
PMHLine.SetDefaultColor(Color.MAGENTA);
PMHLine.SetStyle(Curve.SHORT_DASH);
plot PMLLine = if showKeyLevels then pmL else Double.NaN;
PMLLine.SetDefaultColor(Color.MAGENTA);
PMLLine.SetStyle(Curve.SHORT_DASH);

plot POCLine = if showProfileVwap then poc else Double.NaN;
POCLine.SetDefaultColor(Color.ORANGE);
plot VAHLine = if showProfileVwap then vah else Double.NaN;
VAHLine.SetDefaultColor(Color.DARK_ORANGE);
plot VALLine = if showProfileVwap then val else Double.NaN;
VALLine.SetDefaultColor(Color.DARK_ORANGE);
plot VWAPLine = if showProfileVwap then vw else Double.NaN;
VWAPLine.SetDefaultColor(Color.CYAN);

AddLabel(yes, "Journal Triggers | CVD est " + Round(cvd / 1000, 1) + "k | short score " + sScore + " | long score " + lScore,
    if inWin then Color.WHITE else Color.GRAY);

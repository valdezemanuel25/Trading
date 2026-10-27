# Journal Triggers - thinkorswim study built from the Notion trading journal winners
#
#  SWEEP SHORT  : stretched above value, wicked a key level, closed back below it (+ below fast EMA), CVD rolling over
#  SWEEP LONG   : mirror - swept a key level from below value, closed back above it
#  POC RECLAIM  : rotated off VAL (VAH), first close through POC with CVD agreeing
#
#  Score = swept levels + repeat-rejection bonus ("rejected 3x") + stretch (VAH / VWAP band / BB) + CVD
#  HTF bias filter: fades need the 1h + 4h to agree, or the sweep to be AT an HTF level (PDH/PWH/HTF SMA/round)
#  Opening-range candle high/low (first 5 min of RTH) is a key level from 9:35 on
#  Scorecard: every signal is tracked to target / stop / time-out and tallied in the chart labels
#
# Signals are shown only once the candle has CLOSED; alerts fire on the open of the next bar.
# Bookmap liquidity is not visible here - still check it before entry.

declare upper;

# ----- Session
input winStart = 0930;
input winEnd = 1130;
input profileReset = {default ETH, RTH};
input valueAreaPct = 70;
input orMinutes = 5;

# ----- Indicators
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

# ----- Trigger rules
input lvlTol = 1.0;
input acceptTol = 1.0;
input sweepLook = 3;
input touchLook = 48;
input touchBonusCap = 2;
input stretchLook = 6;
input reclaimLook = 12;
input shortNeedEma = yes;
input longNeedEma = no;
input needCvd = yes;
input cvdLook = 3;
input minScore = 3;
input useReclaim = yes;
input biasMode = {default ALIGNED_OR_AT_HTF_LEVEL, ALIGNED_ONLY, OFF};

# ----- Risk
input minTgt = 6.0;
input stopBuf = 1.0;
input maxStop = 10.0;
input minRR = 1.0;
input cooldown = 6;

# ----- Scorecard
input showScorecard = yes;
input maxHoldBars = 12;
input aPlusScore = 6;

# ----- Display
input showKeyLevels = yes;
input showProfileVwap = no;
input showDebug = yes;

# ===== Helpers
# Short side: 0 if no sweep-rejection of lvl on this bar, otherwise the number of separate rejections of lvl
# (wicks to it that closed below) in the last touchLook bars, minimum 1.
script SwS {
    input lvl = 0.0;
    input tol = 1.0;
    input acc = 1.0;
    input look = 3;
    input touchLook = 48;
    # Every step returns 0 (never N/A) when the level doesn't exist yet, e.g. PMH before the open
    def touch = if IsNaN(lvl) then 0 else if high >= lvl - tol and close < lvl then 1 else 0;
    def tStart = CompoundValue(1, if touch and !touch[1] then 1 else 0, 0);
    def touches = Sum(tStart, touchLook);
    def swept = if IsNaN(lvl) then 0 else if Highest(high, look) >= lvl - tol and Highest(close, look) <= lvl + acc and close < lvl then 1 else 0;
    plot r = if !swept then 0 else if IsNaN(touches) then 1 else Max(touches, 1);
}
script SwL {
    input lvl = 0.0;
    input tol = 1.0;
    input acc = 1.0;
    input look = 3;
    input touchLook = 48;
    def touch = if IsNaN(lvl) then 0 else if low <= lvl + tol and close > lvl then 1 else 0;
    def tStart = CompoundValue(1, if touch and !touch[1] then 1 else 0, 0);
    def touches = Sum(tStart, touchLook);
    def swept = if IsNaN(lvl) then 0 else if Lowest(low, look) <= lvl + tol and Lowest(close, look) >= lvl - acc and close > lvl then 1 else 0;
    plot r = if !swept then 0 else if IsNaN(touches) then 1 else Max(touches, 1);
}
# Distance to a magnet in the trade direction, or 99999 if it is missing / closer than minD
script Dist {
    input m = 0.0;
    input below = yes;
    input minD = 6.0;
    def d = if below then close - m else m - close;
    plot r = if IsNaN(m) then 99999 else if d >= minD then d else 99999;
}

# ===== Sessions
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

# Opening-range candle (first orMinutes of RTH)
def inOR = isRTH and SecondsFromTime(0930) < orMinutes * 60;
def orHi = CompoundValue(1, if rthOpen then high else if inOR then Max(orHi[1], high) else orHi[1], high);
def orLo = CompoundValue(1, if rthOpen then low else if inOR then Min(orLo[1], low) else orLo[1], low);
def or5H = if isRTH and !inOR then orHi else Double.NaN;
def or5L = if isRTH and !inOR then orLo else Double.NaN;

# ===== Indicators
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

# Higher-timeframe SMAs and closes from completed HTF bars
def htf1Close = close(period = htf1Agg)[1];
def htf2Close = close(period = htf2Agg)[1];
def htf1 = Average(close(period = htf1Agg)[1], htf1Len);
def htf2 = Average(close(period = htf2Agg)[1], htf2Len);
def htf3 = Average(close(period = htf3Agg)[1], htf3Len);
def htfBear = htf1Close < htf1 and htf2Close < htf2;
def htfBull = htf1Close > htf1 and htf2Close > htf2;

def pdH = high(period = AggregationPeriod.DAY)[1];
def pdL = low(period = AggregationPeriod.DAY)[1];
def pwH = high(period = AggregationPeriod.WEEK)[1];
def pwL = low(period = AggregationPeriod.WEEK)[1];

def rUp = if useRound then Ceil(close / roundStep) * roundStep else Double.NaN;
def rDn = if useRound then Floor(close / roundStep) * roundStep else Double.NaN;

# Volume profile (built-in engine). NOTE: on past days TOS shows each day's FINAL POC/VA on every bar,
# so historical signals (and the scorecard) are optimistic; live signals use the developing profile.
def vpNew = if profileReset == profileReset.RTH then rthOpen else newDay;
profile vp = VolumeProfile("startNewProfile" = vpNew, "onExpansion" = no, "numberOfProfiles" = 1000, "pricePerRow" = PricePerRow.TICKSIZE, "value area percent" = valueAreaPct);
# The profile can return N/A on some bars; carry the last value forward (same as TOS's own VolumeProfile study)
def poc = CompoundValue(1, if IsNaN(vp.GetPointOfControl()) then poc[1] else vp.GetPointOfControl(), Double.NaN);
def vah = CompoundValue(1, if IsNaN(vp.GetHighestValueArea()) then vah[1] else vp.GetHighestValueArea(), Double.NaN);
def val = CompoundValue(1, if IsNaN(vp.GetLowestValueArea()) then val[1] else vp.GetLowestValueArea(), Double.NaN);
def pPOC = CompoundValue(1, if vpNew then poc[1] else pPOC[1], Double.NaN);

# CVD estimate from candle close location, reset each session
def rng = high - low;
def barDelta = if rng > 0 then volume * ((close - low) - (high - close)) / rng else 0;
def cvd = CompoundValue(1, if newDay then barDelta else cvd[1] + barDelta, barDelta);
def cvdUp = barDelta > 0 and cvd > GetValue(cvd, cvdLook);
def cvdDn = barDelta < 0 and cvd < GetValue(cvd, cvdLook);

# ===== 1) Sweep & Reject (short)
def sPDH = SwS(pdH, lvlTol, acceptTol, sweepLook, touchLook);
def sPDL = SwS(pdL, lvlTol, acceptTol, sweepLook, touchLook);
def sPWH = SwS(pwH, lvlTol, acceptTol, sweepLook, touchLook);
def sPWL = SwS(pwL, lvlTol, acceptTol, sweepLook, touchLook);
def sPMH = SwS(pmH, lvlTol, acceptTol, sweepLook, touchLook);
def sPML = SwS(pmL, lvlTol, acceptTol, sweepLook, touchLook);
def sORH = SwS(or5H, lvlTol, acceptTol, sweepLook, touchLook);
def sORL = SwS(or5L, lvlTol, acceptTol, sweepLook, touchLook);
def sPOC = SwS(poc, lvlTol, acceptTol, sweepLook, touchLook);
def sVAH = SwS(vah, lvlTol, acceptTol, sweepLook, touchLook);
def sVAL = SwS(val, lvlTol, acceptTol, sweepLook, touchLook);
def sPPOC = SwS(pPOC, lvlTol, acceptTol, sweepLook, touchLook);
def sVW = SwS(vw, lvlTol, acceptTol, sweepLook, touchLook);
def sSMA = SwS(smaC, lvlTol, acceptTol, sweepLook, touchLook);
def sH1 = SwS(htf1, lvlTol, acceptTol, sweepLook, touchLook);
def sH2 = SwS(htf2, lvlTol, acceptTol, sweepLook, touchLook);
def sH3 = SwS(htf3, lvlTol, acceptTol, sweepLook, touchLook);
def sRU = SwS(rUp, lvlTol, acceptTol, sweepLook, touchLook);
def sRD = SwS(rDn, lvlTol, acceptTol, sweepLook, touchLook);
def sConf = (sPDH > 0) + (sPDL > 0) + (sPWH > 0) + (sPWL > 0) + (sPMH > 0) + (sPML > 0) + (sORH > 0) + (sORL > 0)
          + (sPOC > 0) + (sVAH > 0) + (sVAL > 0) + (sPPOC > 0) + (sVW > 0) + (sSMA > 0)
          + (sH1 > 0) + (sH2 > 0) + (sH3 > 0) + (sRU > 0) + (sRD > 0);
def sTouch = Max(Max(Max(Max(sPDH, sPDL), Max(sPWH, sPWL)), Max(Max(sPMH, sPML), Max(sORH, sORL))),
             Max(Max(Max(Max(sPOC, sVAH), Max(sVAL, sPPOC)), Max(Max(sVW, sSMA), Max(sH1, sH2))), Max(sH3, Max(sRU, sRD))));
def sAtHtf = (sPDH > 0) or (sPWH > 0) or (sH1 > 0) or (sH2 > 0) or (sH3 > 0) or (sRU > 0) or (sRD > 0);

def hiVAH = Highest(high - vah, stretchLook);
def upVAH = if IsNaN(hiVAH) then 0 else hiVAH >= 0;
def hiVW = Highest(high - vwUp, stretchLook);
def upVW = if IsNaN(hiVW) then 0 else hiVW >= 0;
def hiBB = Highest(high - bbUp, stretchLook);
def upBB = if IsNaN(hiBB) then 0 else hiBB >= 0;
def sScore = sConf + Min(Max(sTouch - 1, 0), touchBonusCap) + upVAH + upVW + upBB + cvdDn;
def sBiasOK = biasMode == biasMode.OFF or htfBear or (biasMode == biasMode.ALIGNED_OR_AT_HTF_LEVEL and sAtHtf);

def sStop = Highest(high, sweepLook) + stopBuf;
def sRisk = sStop - close;
def sTgtD = Min(Min(Min(Dist(poc, yes, minTgt), Dist(vw, yes, minTgt)), Min(Dist(val, yes, minTgt), Dist(pPOC, yes, minTgt))),
                Min(Min(Dist(bbMid, yes, minTgt), Dist(vwLo, yes, minTgt)), Min(Dist(pdL, yes, minTgt), Dist(pmL, yes, minTgt))));
def sRR = if sTgtD < 99999 and sRisk > 0 then sTgtD / sRisk else 0;
def rawSS = inWin and sConf > 0 and sBiasOK and close < open and (!shortNeedEma or close < emaF) and (!needCvd or cvdDn) and sScore >= minScore and sRR >= minRR and sRisk <= maxStop;

# ===== 2) Sweep & Reclaim (long)
def lPDH = SwL(pdH, lvlTol, acceptTol, sweepLook, touchLook);
def lPDL = SwL(pdL, lvlTol, acceptTol, sweepLook, touchLook);
def lPWH = SwL(pwH, lvlTol, acceptTol, sweepLook, touchLook);
def lPWL = SwL(pwL, lvlTol, acceptTol, sweepLook, touchLook);
def lPMH = SwL(pmH, lvlTol, acceptTol, sweepLook, touchLook);
def lPML = SwL(pmL, lvlTol, acceptTol, sweepLook, touchLook);
def lORH = SwL(or5H, lvlTol, acceptTol, sweepLook, touchLook);
def lORL = SwL(or5L, lvlTol, acceptTol, sweepLook, touchLook);
def lPOC = SwL(poc, lvlTol, acceptTol, sweepLook, touchLook);
def lVAH = SwL(vah, lvlTol, acceptTol, sweepLook, touchLook);
def lVAL = SwL(val, lvlTol, acceptTol, sweepLook, touchLook);
def lPPOC = SwL(pPOC, lvlTol, acceptTol, sweepLook, touchLook);
def lVW = SwL(vw, lvlTol, acceptTol, sweepLook, touchLook);
def lSMA = SwL(smaC, lvlTol, acceptTol, sweepLook, touchLook);
def lH1 = SwL(htf1, lvlTol, acceptTol, sweepLook, touchLook);
def lH2 = SwL(htf2, lvlTol, acceptTol, sweepLook, touchLook);
def lH3 = SwL(htf3, lvlTol, acceptTol, sweepLook, touchLook);
def lRU = SwL(rUp, lvlTol, acceptTol, sweepLook, touchLook);
def lRD = SwL(rDn, lvlTol, acceptTol, sweepLook, touchLook);
def lConf = (lPDH > 0) + (lPDL > 0) + (lPWH > 0) + (lPWL > 0) + (lPMH > 0) + (lPML > 0) + (lORH > 0) + (lORL > 0)
          + (lPOC > 0) + (lVAH > 0) + (lVAL > 0) + (lPPOC > 0) + (lVW > 0) + (lSMA > 0)
          + (lH1 > 0) + (lH2 > 0) + (lH3 > 0) + (lRU > 0) + (lRD > 0);
def lTouch = Max(Max(Max(Max(lPDH, lPDL), Max(lPWH, lPWL)), Max(Max(lPMH, lPML), Max(lORH, lORL))),
             Max(Max(Max(Max(lPOC, lVAH), Max(lVAL, lPPOC)), Max(Max(lVW, lSMA), Max(lH1, lH2))), Max(lH3, Max(lRU, lRD))));
def lAtHtf = (lPDL > 0) or (lPWL > 0) or (lH1 > 0) or (lH2 > 0) or (lH3 > 0) or (lRU > 0) or (lRD > 0);

def loVAL = Lowest(low - val, stretchLook);
def dnVAL = if IsNaN(loVAL) then 0 else loVAL <= 0;
def loVW = Lowest(low - vwLo, stretchLook);
def dnVW = if IsNaN(loVW) then 0 else loVW <= 0;
def loBB = Lowest(low - bbLo, stretchLook);
def dnBB = if IsNaN(loBB) then 0 else loBB <= 0;
def lScore = lConf + Min(Max(lTouch - 1, 0), touchBonusCap) + dnVAL + dnVW + dnBB + cvdUp;
def lBiasOK = biasMode == biasMode.OFF or htfBull or (biasMode == biasMode.ALIGNED_OR_AT_HTF_LEVEL and lAtHtf);

def lStop = Lowest(low, sweepLook) - stopBuf;
def lRisk = close - lStop;
def lTgtD = Min(Min(Min(Dist(poc, no, minTgt), Dist(vw, no, minTgt)), Min(Dist(vah, no, minTgt), Dist(pPOC, no, minTgt))),
                Min(Min(Min(Dist(bbMid, no, minTgt), Dist(emaF, no, minTgt)), Dist(vwUp, no, minTgt)), Min(Dist(pdH, no, minTgt), Dist(pmH, no, minTgt))));
def lRR = if lTgtD < 99999 and lRisk > 0 then lTgtD / lRisk else 0;
def rawSL = inWin and lConf > 0 and lBiasOK and close > open and (!longNeedEma or close > emaF) and (!needCvd or cvdUp) and lScore >= minScore and lRR >= minRR and lRisk <= maxStop;

# ===== 3) POC Reclaim / POC Loss (continuation - never against the HTF trend)
def crossUpPOC = close > poc and close[1] <= poc[1];
def crossDnPOC = close < poc and close[1] >= poc[1];
def loRecl = Lowest(low - val, reclaimLook);
def fromVAL = if IsNaN(loRecl) then 0 else loRecl <= lvlTol;
def hiRecl = Highest(high - vah, reclaimLook);
def fromVAH = if IsNaN(hiRecl) then 0 else hiRecl >= -lvlTol;

def rlStop = Lowest(low, 5) - stopBuf;
def rlRisk = close - rlStop;
def rlTgtD = Min(Min(Dist(vah, no, minTgt), Dist(vw, no, minTgt)), Min(Min(Dist(vwUp, no, minTgt), Dist(pdH, no, minTgt)), Dist(pmH, no, minTgt)));
def rlRR = if rlTgtD < 99999 and rlRisk > 0 then rlTgtD / rlRisk else 0;
def rawRL = useReclaim and inWin and (biasMode == biasMode.OFF or !htfBear) and crossUpPOC and fromVAL and close > emaF and close > open and (!needCvd or cvdUp) and rlRR >= minRR and rlRisk <= maxStop;

def rsStop = Highest(high, 5) + stopBuf;
def rsRisk = rsStop - close;
def rsTgtD = Min(Min(Dist(val, yes, minTgt), Dist(vw, yes, minTgt)), Min(Min(Dist(vwLo, yes, minTgt), Dist(pdL, yes, minTgt)), Dist(pmL, yes, minTgt)));
def rsRR = if rsTgtD < 99999 and rsRisk > 0 then rsTgtD / rsRisk else 0;
def rawRS = useReclaim and inWin and (biasMode == biasMode.OFF or !htfBull) and crossDnPOC and fromVAH and close < emaF and close < open and (!needCvd or cvdDn) and rsRR >= minRR and rsRisk <= maxStop;

# ===== Cooldown (same side)
def lastS = CompoundValue(1, if (rawSS or rawRS) and bn - lastS[1] > cooldown then bn else lastS[1], -100000);
def lastL = CompoundValue(1, if (rawSL or rawRL) and bn - lastL[1] > cooldown then bn else lastL[1], -100000);
def sweepShort = rawSS and lastS == bn;
def reclaimShort = !rawSS and rawRS and lastS == bn;
def sweepLong = rawSL and lastL == bn;
def reclaimLong = !rawSL and rawRL and lastL == bn;

# Only show a signal once its candle has closed (a newer bar exists)
def done = !IsNaN(close[-1]);

# ===== Scorecard - one tracked trade at a time: enter at signal close, exit at target / stop / time-out
def sigDir = if sweepShort or reclaimShort then -1 else if sweepLong or reclaimLong then 1 else 0;
def sigType = if sweepShort then 1 else if reclaimShort then 2 else if sweepLong then 3 else if reclaimLong then 4 else 0;
def sigTgt = if sweepShort then close - sTgtD else if reclaimShort then close - rsTgtD else if sweepLong then close + lTgtD else if reclaimLong then close + rlTgtD else 0;
def sigStp = if sweepShort then sStop else if reclaimShort then rsStop else if sweepLong then lStop else if reclaimLong then rlStop else 0;
def sigScore = if sweepShort then sScore else if sweepLong then lScore else 0;

def oDir;
def oEnt;
def oTgt;
def oStp;
def oBar;
def oType;
def oScore;
def openPrev = bn > 1 and oDir[1] != 0;
def hitT = openPrev and (if oDir[1] < 0 then low <= oTgt[1] else high >= oTgt[1]);
def hitS = openPrev and (if oDir[1] < 0 then high >= oStp[1] else low <= oStp[1]);
def tOut = openPrev and !hitT and !hitS and (bn - oBar[1] >= maxHoldBars or !isRTH);
def resolved = hitT or hitS or tOut;
def isWin = hitT and !hitS;  # target and stop in the same bar counts as a loss
def isLoss = hitS;
def isScratch = tOut;

if (!openPrev or resolved) and sigDir != 0 {
    oDir = sigDir;
    oEnt = close;
    oTgt = sigTgt;
    oStp = sigStp;
    oBar = bn;
    oType = sigType;
    oScore = sigScore;
} else if openPrev and !resolved {
    oDir = oDir[1];
    oEnt = oEnt[1];
    oTgt = oTgt[1];
    oStp = oStp[1];
    oBar = oBar[1];
    oType = oType[1];
    oScore = oScore[1];
} else {
    oDir = 0;
    oEnt = 0;
    oTgt = 0;
    oStp = 0;
    oBar = 0;
    oType = 0;
    oScore = 0;
}

def rType = if resolved then oType[1] else 0;
def ptsR = if isWin then AbsValue(oTgt[1] - oEnt[1]) else if isLoss then -AbsValue(oStp[1] - oEnt[1]) else if isScratch then oDir[1] * (close - oEnt[1]) else 0;

def w1 = TotalSum(isWin and rType == 1);
def l1 = TotalSum(isLoss and rType == 1);
def w2 = TotalSum(isWin and rType == 2);
def l2 = TotalSum(isLoss and rType == 2);
def w3 = TotalSum(isWin and rType == 3);
def l3 = TotalSum(isLoss and rType == 3);
def w4 = TotalSum(isWin and rType == 4);
def l4 = TotalSum(isLoss and rType == 4);
def wA = TotalSum(isWin and oScore[1] >= aPlusScore);
def lA = TotalSum(isLoss and oScore[1] >= aPlusScore);
def scr = TotalSum(isScratch);
def nRes = TotalSum(resolved);
def holdSum = TotalSum(if resolved then bn - oBar[1] else 0);
def netPts = TotalSum(ptsR);

# ===== Output
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

# Outcome dots: where each tracked signal hit its target (green) or stop (red)
plot TargetHit = if showScorecard and isWin then oTgt[1] else Double.NaN;
TargetHit.SetPaintingStrategy(PaintingStrategy.POINTS);
TargetHit.SetDefaultColor(Color.GREEN);
TargetHit.SetLineWeight(4);
plot StopHit = if showScorecard and isLoss then oStp[1] else Double.NaN;
StopHit.SetPaintingStrategy(PaintingStrategy.POINTS);
StopHit.SetDefaultColor(Color.RED);
StopHit.SetLineWeight(4);

AddChartBubble(sweepShort and done, high,
    "SWEEP SHORT (" + sScore + ")" + (if sTouch > 1 then "  " + sTouch + "x rejected" else "") + (if htfBear then "  HTF bear" else "  at HTF lvl") + "\n" +
    (if sPDH then "PDH " else "") + (if sPWH then "PWH " else "") + (if sPMH then "PMH " else "") + (if sORH then "OR5H " else "") +
    (if sVAH then "VAH " else "") + (if sPOC then "POC " else "") + (if sPPOC then "pPOC " else "") +
    (if sVW then "VWAP " else "") + (if sSMA then "SMA " else "") + (if sH1 then "H1SMA " else "") +
    (if sH2 then "H2SMA " else "") + (if sH3 then "H3SMA " else "") + (if sRU or sRD then "Round " else "") +
    "\nT " + AsPrice(close - sTgtD) + "  S " + AsPrice(sStop) + "  RR " + Round(sRR, 2),
    Color.RED, yes);

AddChartBubble(sweepLong and done, low,
    "SWEEP LONG (" + lScore + ")" + (if lTouch > 1 then "  " + lTouch + "x held" else "") + (if htfBull then "  HTF bull" else "  at HTF lvl") + "\n" +
    (if lPDL then "PDL " else "") + (if lPWL then "PWL " else "") + (if lPML then "PML " else "") + (if lORL then "OR5L " else "") +
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
Alert(sweepShort[1], "Journal: SWEEP SHORT - check Bookmap", Alert.BAR, Sound.Ring);
Alert(sweepLong[1], "Journal: SWEEP LONG - check Bookmap", Alert.BAR, Sound.Ring);
Alert(reclaimShort[1], "Journal: POC LOSS SHORT - check Bookmap", Alert.BAR, Sound.Chimes);
Alert(reclaimLong[1], "Journal: POC RECLAIM LONG - check Bookmap", Alert.BAR, Sound.Chimes);

# ===== Levels
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
plot ORHLine = if showKeyLevels then or5H else Double.NaN;
ORHLine.SetDefaultColor(Color.YELLOW);
ORHLine.SetStyle(Curve.LONG_DASH);
plot ORLLine = if showKeyLevels then or5L else Double.NaN;
ORLLine.SetDefaultColor(Color.YELLOW);
ORLLine.SetStyle(Curve.LONG_DASH);

plot POCLine = if showProfileVwap then poc else Double.NaN;
POCLine.SetDefaultColor(Color.ORANGE);
plot VAHLine = if showProfileVwap then vah else Double.NaN;
VAHLine.SetDefaultColor(Color.DARK_ORANGE);
plot VALLine = if showProfileVwap then val else Double.NaN;
VALLine.SetDefaultColor(Color.DARK_ORANGE);
plot VWAPLine = if showProfileVwap then vw else Double.NaN;
VWAPLine.SetDefaultColor(Color.CYAN);

# ===== Labels
AddLabel(yes, "HTF " + (if htfBear then "BEAR" else if htfBull then "BULL" else "MIXED") + " | CVD est " + Round(cvd / 1000, 1) + "k | short " + sScore + " (lvl " + sConf + " rej " + sTouch + " str " + (upVAH + upVW + upBB) + " cvd " + cvdDn + ") | long " + lScore + " (lvl " + lConf + " rej " + lTouch + " str " + (dnVAL + dnVW + dnBB) + " cvd " + cvdUp + ")",
    if htfBear then Color.LIGHT_RED else if htfBull then Color.LIGHT_GREEN else Color.GRAY);

# Which rule is blocking a sweep signal on the current bar (turn off with showDebug)
AddLabel(showDebug, "Short: " + (if rawSS then "SIGNAL" else if sConf == 0 then "no level swept" else
    (if !inWin then "outside window " else "") + (if !sBiasOK then "HTF bias " else "") + (if close >= open then "not red " else "") +
    (if shortNeedEma and close >= emaF then "above EMA " else "") + (if needCvd and !cvdDn then "CVD " else "") +
    (if sScore < minScore then "score " else "") + (if sRR < minRR then "RR " + Round(sRR, 2) + " " else "") +
    (if sRisk > maxStop then "stop " + Round(sRisk, 2) + "pt" else "")), Color.LIGHT_GRAY);
AddLabel(showDebug, "Long: " + (if rawSL then "SIGNAL" else if lConf == 0 then "no level swept" else
    (if !inWin then "outside window " else "") + (if !lBiasOK then "HTF bias " else "") + (if close <= open then "not green " else "") +
    (if longNeedEma and close <= emaF then "below EMA " else "") + (if needCvd and !cvdUp then "CVD " else "") +
    (if lScore < minScore then "score " else "") + (if lRR < minRR then "RR " + Round(lRR, 2) + " " else "") +
    (if lRisk > maxStop then "stop " + Round(lRisk, 2) + "pt" else "")), Color.LIGHT_GRAY);

AddLabel(showScorecard, "Sweep S " + w1 + "W/" + l1 + "L" + (if w1 + l1 > 0 then " " + Round(100 * w1 / (w1 + l1), 0) + "%" else ""),
    if w1 >= l1 then Color.GREEN else Color.RED);
AddLabel(showScorecard, "Sweep L " + w3 + "W/" + l3 + "L" + (if w3 + l3 > 0 then " " + Round(100 * w3 / (w3 + l3), 0) + "%" else ""),
    if w3 >= l3 then Color.GREEN else Color.RED);
AddLabel(showScorecard, "POC S " + w2 + "W/" + l2 + "L | POC L " + w4 + "W/" + l4 + "L", Color.GRAY);
AddLabel(showScorecard, "Score " + aPlusScore + "+: " + wA + "W/" + lA + "L" + (if wA + lA > 0 then " " + Round(100 * wA / (wA + lA), 0) + "%" else ""),
    if wA >= lA then Color.GREEN else Color.RED);
AddLabel(showScorecard, "Time-outs " + scr + " | avg hold " + (if nRes > 0 then Round(holdSum / nRes, 1) else 0) + " bars | net " + Round(netPts, 2) + " pts",
    if netPts >= 0 then Color.GREEN else Color.RED);
AddLabel(showScorecard, "History uses final-day POC/VA - treat as optimistic", Color.DARK_GRAY);

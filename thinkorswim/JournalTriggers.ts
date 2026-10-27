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
# PROFILE: ToS volume profile (matches your Volume Profile study, but today's earlier candles are re-checked
#          against the latest POC/VA, so today's bubbles can change during the session).
# VWAP_STATIC: POC = VWAP, VAH/VAL = VWAP +/- 1 stdev (~70% of volume). Uses only candles already printed,
#          so bubbles never change after they appear.
input vaSource = {default PROFILE, VWAP_STATIC};
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
input useReclaim = no;
input biasMode = {default ALIGNED_OR_AT_HTF_LEVEL, ALIGNED_ONLY, OFF};

# ----- VAL / VAH Flip (failed breakdown after a flush, or failed breakout after a blow-off)
input useFlip = yes;
input flushPts = 15.0;
input flushLook = 12;
input flipLook = 6;
input flipMaxBeyond = 8.0;
input flipNeedBias = no;

# ----- HTF level test (4h SMA200 / 4h SMA21 / 1h SMA50)
input useHtf = yes;
input htfTol = 2.0;
input firstLook = 156;
input cancelPts = 2.0;
input cancelLook = 6;
input zoneTol = 3.0;

# ----- Failed breakout of an HTF SMA (accepted beyond it, then closes back through it)
input useFbo = yes;
input fboLook = 24;
input fboEnd = 1300;

# ----- Chop filter: many EMA crosses inside a tight range pauses every signal
input useChop = yes;
input chopLook = 12;
input chopCrosses = 5;
input chopRange = 15.0;

# ----- Risk
input minTgt = 6.0;
input stopBuf = 1.0;
input maxStop = 12.0;
input minRR = 1.0;
input cooldown = 6;

# ----- Scorecard
input showScorecard = no;
input maxHoldBars = 12;

# ----- Display
input showKeyLevels = yes;
input showProfileVwap = no;
input showDebug = no;
input showHtfLines = yes;
input showGhosts = yes;
input showOutcomes = yes;
input showT2Line = yes;

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
# Round a price to the instrument's tick (ES/MES = 0.25)
script RT {
    input x = 0.0;
    plot r = Round(x / TickSize(), 0) * TickSize();
}
# Failed breakout, short side: price was ACCEPTED above L (2+ closes more than cancelPts above it within look bars)
# and this candle is the first close back below L.
script FboS {
    input L = 0.0;
    input Lprev = 0.0;
    input cancelPts = 2.0;
    input look = 24;
    def accHit = if IsNaN(L) then 0 else if close > L + cancelPts then 1 else 0;
    def accepted = GetValue(Sum(accHit, look), 1) >= 2;
    def crossBack = if IsNaN(L) or IsNaN(Lprev) then 0 else if close < L and close[1] >= Lprev then 1 else 0;
    def raw = accepted and crossBack;
    plot r = if IsNaN(raw) then 0 else raw;
}
script FboL {
    input L = 0.0;
    input Lprev = 0.0;
    input cancelPts = 2.0;
    input look = 24;
    def accHit = if IsNaN(L) then 0 else if close < L - cancelPts then 1 else 0;
    def accepted = GetValue(Sum(accHit, look), 1) >= 2;
    def crossBack = if IsNaN(L) or IsNaN(Lprev) then 0 else if close > L and close[1] <= Lprev then 1 else 0;
    def raw = accepted and crossBack;
    plot r = if IsNaN(raw) then 0 else raw;
}
# HTF level rejection, short side. 0 = no signal, 1 = rejection, 2 = rejection on the FIRST touch in firstLook bars.
# Needs: price came from BELOW (no close above L in the firstLook bars before the sweep window), wicked into L +/- tol,
# closes back below L, and has NOT been accepted above (2+ closes > L + cancelPts in the last cancelLook bars).
script HtfRejS {
    input L = 0.0;
    input tol = 2.0;
    input cancelPts = 2.0;
    input cancelLook = 6;
    input look = 156;
    input sweepLook = 3;
    def zone = if IsNaN(L) then 0 else if high >= L - tol and low <= L + tol then 1 else 0;
    def closeAbove = if IsNaN(L) then 0 else if close > L then 1 else 0;
    def cancelHit = if IsNaN(L) then 0 else if close > L + cancelPts then 1 else 0;
    def priorAbove = GetValue(Sum(closeAbove, look), sweepLook);
    def priorTouch = GetValue(Sum(zone, look), sweepLook);
    def accepted = Sum(cancelHit, cancelLook) >= 2;
    def swept = if IsNaN(L) then 0 else Highest(high, sweepLook) >= L - tol;
    def raw = if IsNaN(L) then 0 else if swept and priorAbove == 0 and !accepted and close < L then (if priorTouch == 0 then 2 else 1) else 0;
    plot r = if IsNaN(raw) then 0 else raw;
}
script HtfRejL {
    input L = 0.0;
    input tol = 2.0;
    input cancelPts = 2.0;
    input cancelLook = 6;
    input look = 156;
    input sweepLook = 3;
    def zone = if IsNaN(L) then 0 else if high >= L - tol and low <= L + tol then 1 else 0;
    def closeBelow = if IsNaN(L) then 0 else if close < L then 1 else 0;
    def cancelHit = if IsNaN(L) then 0 else if close < L - cancelPts then 1 else 0;
    def priorBelow = GetValue(Sum(closeBelow, look), sweepLook);
    def priorTouch = GetValue(Sum(zone, look), sweepLook);
    def accepted = Sum(cancelHit, cancelLook) >= 2;
    def swept = if IsNaN(L) then 0 else Lowest(low, sweepLook) <= L + tol;
    def raw = if IsNaN(L) then 0 else if swept and priorBelow == 0 and !accepted and close > L then (if priorTouch == 0 then 2 else 1) else 0;
    plot r = if IsNaN(raw) then 0 else raw;
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
def vpPOC = CompoundValue(1, if IsNaN(vp.GetPointOfControl()) then vpPOC[1] else vp.GetPointOfControl(), Double.NaN);
def vpVAH = CompoundValue(1, if IsNaN(vp.GetHighestValueArea()) then vpVAH[1] else vp.GetHighestValueArea(), Double.NaN);
def vpVAL = CompoundValue(1, if IsNaN(vp.GetLowestValueArea()) then vpVAL[1] else vp.GetLowestValueArea(), Double.NaN);
def staticVA = vaSource == vaSource.VWAP_STATIC;
def poc = if staticVA then vw else vpPOC;
def vah = if staticVA then vw + vwSd else vpVAH;
def val = if staticVA then vw - vwSd else vpVAL;
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
# Nearest level that is at least minTgt away AND gives at least minRR for this stop
def sNeed = Max(minTgt, minRR * sRisk);
def sTgtD = Min(Min(Min(Dist(poc, yes, sNeed), Dist(vw, yes, sNeed)), Min(Dist(val, yes, sNeed), Dist(pPOC, yes, sNeed))),
                Min(Min(Dist(bbMid, yes, sNeed), Dist(vwLo, yes, sNeed)), Min(Dist(pdL, yes, sNeed), Dist(pmL, yes, sNeed))));
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
# Nearest level that is at least minTgt away AND gives at least minRR for this stop
def lNeed = Max(minTgt, minRR * lRisk);
def lTgtD = Min(Min(Min(Dist(poc, no, lNeed), Dist(vw, no, lNeed)), Min(Dist(vah, no, lNeed), Dist(pPOC, no, lNeed))),
                Min(Min(Min(Dist(bbMid, no, lNeed), Dist(emaF, no, lNeed)), Dist(vwUp, no, lNeed)), Min(Dist(pdH, no, lNeed), Dist(pmH, no, lNeed))));
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
# Nearest level that is at least minTgt away AND gives at least minRR for this stop
def rlNeed = Max(minTgt, minRR * rlRisk);
def rlTgtD = Min(Min(Dist(vah, no, rlNeed), Dist(vw, no, rlNeed)), Min(Min(Dist(vwUp, no, rlNeed), Dist(pdH, no, rlNeed)), Dist(pmH, no, rlNeed)));
def rlRR = if rlTgtD < 99999 and rlRisk > 0 then rlTgtD / rlRisk else 0;
def rawRL = useReclaim and inWin and (biasMode == biasMode.OFF or !htfBear) and crossUpPOC and fromVAL and close > emaF and close > open and (!needCvd or cvdUp) and rlRR >= minRR and rlRisk <= maxStop;

def rsStop = Highest(high, 5) + stopBuf;
def rsRisk = rsStop - close;
# Nearest level that is at least minTgt away AND gives at least minRR for this stop
def rsNeed = Max(minTgt, minRR * rsRisk);
def rsTgtD = Min(Min(Dist(val, yes, rsNeed), Dist(vw, yes, rsNeed)), Min(Min(Dist(vwLo, yes, rsNeed), Dist(pdL, yes, rsNeed)), Dist(pmL, yes, rsNeed)));
def rsRR = if rsTgtD < 99999 and rsRisk > 0 then rsTgtD / rsRisk else 0;
def rawRS = useReclaim and inWin and (biasMode == biasMode.OFF or !htfBull) and crossDnPOC and fromVAH and close < emaF and close < open and (!needCvd or cvdDn) and rsRR >= minRR and rsRisk <= maxStop;

# ===== 4) VAL Flip long / VAH Flip short
# Long: price flushed >= flushPts in the last flushLook bars, traded below VAL (by no more than flipMaxBeyond)
# within flipLook bars, was stretched (lower VWAP band or BB), and this green candle closes back above VAL
# in the upper part of its range with buyers stepping in (positive bar delta). CVD does NOT need to have turned:
# at a flush bottom it is still falling, as in the 06-25 and 10-15 journal longs.
def flLow = Lowest(low, flipLook);
def flushDn = Highest(high, flushLook) - flLow >= flushPts;
def flDepth = val - flLow;
def flBelow = if IsNaN(flDepth) then 0 else flDepth > lvlTol and flDepth <= flipMaxBeyond;
def flPrevNear = if IsNaN(val[1]) then 0 else Min(close[1] - val[1], close[2] - val[2]) <= lvlTol;
def flStrong = close > open and close - low >= 0.6 * (high - low);
def flStretch = dnVW or dnBB;
def flStop = flLow - stopBuf;
def flRisk = close - flStop;
def flNeed = Max(minTgt, minRR * flRisk);
def flTgtD = Min(Min(Dist(poc, no, flNeed), Dist(vw, no, flNeed)), Min(Min(Dist(pPOC, no, flNeed), Dist(bbMid, no, flNeed)), Dist(vah, no, flNeed)));
def flRR = if flTgtD < 99999 and flRisk > 0 then flTgtD / flRisk else 0;
def rawFL = useFlip and inWin and (!flipNeedBias or lBiasOK) and close > val and flPrevNear and flBelow and flushDn and flStretch and flStrong and barDelta > 0 and flRR >= minRR and flRisk <= maxStop;

def fsHigh = Highest(high, flipLook);
def flushUp = fsHigh - Lowest(low, flushLook) >= flushPts;
def fsDepth = fsHigh - vah;
def fsAbove = if IsNaN(fsDepth) then 0 else fsDepth > lvlTol and fsDepth <= flipMaxBeyond;
def fsPrevNear = if IsNaN(vah[1]) then 0 else Max(close[1] - vah[1], close[2] - vah[2]) >= -lvlTol;
def fsStrong = close < open and high - close >= 0.6 * (high - low);
def fsStretch = upVW or upBB;
def fsStop = fsHigh + stopBuf;
def fsRisk = fsStop - close;
def fsNeed = Max(minTgt, minRR * fsRisk);
def fsTgtD = Min(Min(Dist(poc, yes, fsNeed), Dist(vw, yes, fsNeed)), Min(Min(Dist(pPOC, yes, fsNeed), Dist(bbMid, yes, fsNeed)), Dist(val, yes, fsNeed)));
def fsRR = if fsTgtD < 99999 and fsRisk > 0 then fsTgtD / fsRisk else 0;
def rawFS = useFlip and inWin and (!flipNeedBias or sBiasOK) and close < vah and fsPrevNear and fsAbove and flushUp and fsStretch and fsStrong and barDelta < 0 and fsRR >= minRR and fsRisk <= maxStop;

# ===== 5) HTF level test: rejection of a 4h/1h SMA (priority 4h SMA200, then 4h SMA21, then 1h SMA50)
# Short = tested from below and rejected (your 06-23, 07-31, 09-22, 09-25 shorts). Long = tested from above and held.
def h3S = HtfRejS(htf3, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def h2S = HtfRejS(htf2, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def h1S = HtfRejS(htf1, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def hSelS = if h3S > 0 then 3 else if h2S > 0 then 2 else if h1S > 0 then 1 else 0;
def hLvlS = if hSelS == 3 then htf3 else if hSelS == 2 then htf2 else if hSelS == 1 then htf1 else Double.NaN;
def hFirstS = (if hSelS == 3 then h3S else if hSelS == 2 then h2S else h1S) == 2;
def hsScore = 3 + (if hFirstS then 2 else 0) + upVAH + upVW + upBB + cvdDn + sConf;
def hsStop = Max(Highest(high, sweepLook), hLvlS) + stopBuf;
def hsRisk = hsStop - close;
def hsNeed = Max(minTgt, minRR * hsRisk);
def hsTgtD = Min(Min(Dist(vah, yes, hsNeed), Dist(poc, yes, hsNeed)), Min(Min(Dist(vw, yes, hsNeed), Dist(bbMid, yes, hsNeed)), Dist(val, yes, hsNeed)));
def hsRR = if hsTgtD < 99999 and hsRisk > 0 then hsTgtD / hsRisk else 0;
def rawHS = useHtf and inWin and hSelS > 0 and close < open and (!shortNeedEma or close < emaF) and hsRR >= minRR and hsRisk <= maxStop;

def h3L = HtfRejL(htf3, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def h2L = HtfRejL(htf2, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def h1L = HtfRejL(htf1, htfTol, cancelPts, cancelLook, firstLook, sweepLook);
def hSelL = if h3L > 0 then 3 else if h2L > 0 then 2 else if h1L > 0 then 1 else 0;
def hLvlL = if hSelL == 3 then htf3 else if hSelL == 2 then htf2 else if hSelL == 1 then htf1 else Double.NaN;
def hFirstL = (if hSelL == 3 then h3L else if hSelL == 2 then h2L else h1L) == 2;
def hlScore = 3 + (if hFirstL then 2 else 0) + dnVAL + dnVW + dnBB + cvdUp + lConf;
def hlStop = Min(Lowest(low, sweepLook), hLvlL) - stopBuf;
def hlRisk = close - hlStop;
def hlNeed = Max(minTgt, minRR * hlRisk);
def hlTgtD = Min(Min(Dist(val, no, hlNeed), Dist(poc, no, hlNeed)), Min(Min(Dist(vw, no, hlNeed), Dist(bbMid, no, hlNeed)), Dist(vah, no, hlNeed)));
def hlRR = if hlTgtD < 99999 and hlRisk > 0 then hlTgtD / hlRisk else 0;
def rawHL = useHtf and inWin and hSelL > 0 and close > open and (!longNeedEma or close > emaF) and hlRR >= minRR and hlRisk <= maxStop;


# ===== 6) Failed breakout of a 4h/1h SMA (trapped breakout traders). Allowed until fboEnd (ET).
def fboWin = SecondsFromTime(winStart) >= 0 and SecondsTillTime(fboEnd) > 0;
def fb3S = FboS(htf3, htf3[1], cancelPts, fboLook);
def fb2S = FboS(htf2, htf2[1], cancelPts, fboLook);
def fb1S = FboS(htf1, htf1[1], cancelPts, fboLook);
def fbSelS = if fb3S then 3 else if fb2S then 2 else if fb1S then 1 else 0;
def fbsStop = Highest(high, sweepLook) + stopBuf;
def fbsRisk = fbsStop - close;
def fbsNeed = Max(minTgt, minRR * fbsRisk);
def fbsTgtD = Min(Min(Dist(vah, yes, fbsNeed), Dist(poc, yes, fbsNeed)), Min(Min(Dist(vw, yes, fbsNeed), Dist(bbMid, yes, fbsNeed)), Dist(val, yes, fbsNeed)));
def fbsRR = if fbsTgtD < 99999 and fbsRisk > 0 then fbsTgtD / fbsRisk else 0;
def rawBS = useFbo and fboWin and fbSelS > 0 and close < open and close < emaF and fbsRR >= minRR and fbsRisk <= maxStop;

def fb3L = FboL(htf3, htf3[1], cancelPts, fboLook);
def fb2L = FboL(htf2, htf2[1], cancelPts, fboLook);
def fb1L = FboL(htf1, htf1[1], cancelPts, fboLook);
def fbSelL = if fb3L then 3 else if fb2L then 2 else if fb1L then 1 else 0;
def fblStop = Lowest(low, sweepLook) - stopBuf;
def fblRisk = close - fblStop;
def fblNeed = Max(minTgt, minRR * fblRisk);
def fblTgtD = Min(Min(Dist(val, no, fblNeed), Dist(poc, no, fblNeed)), Min(Min(Dist(vw, no, fblNeed), Dist(bbMid, no, fblNeed)), Dist(vah, no, fblNeed)));
def fblRR = if fblTgtD < 99999 and fblRisk > 0 then fblTgtD / fblRisk else 0;
def rawBL = useFbo and fboWin and fbSelL > 0 and close > open and close > emaF and fblRR >= minRR and fblRisk <= maxStop;

# ===== Chop filter: >= chopCrosses EMA crosses in the last chopLook bars while the whole range is <= chopRange
def emaSide = close > emaF;
def emaCross = if IsNaN(emaF[1]) then 0 else if emaSide != emaSide[1] then 1 else 0;
def chopN = Sum(emaCross, chopLook);
def chopRng = Highest(high, chopLook) - Lowest(low, chopLook);
def isChop = if IsNaN(chopN) or IsNaN(chopRng) then 0 else useChop and chopN >= chopCrosses and chopRng <= chopRange;

# ===== Cooldown (same side)
# A single N/A inside a running (recursive) value would stick forever and block every later signal,
# so each condition is forced to 0/1 first and the cooldown recovers from N/A.
def okSS = if IsNaN(rawSS) or isChop then 0 else rawSS;
def okRS = if IsNaN(rawRS) or isChop then 0 else rawRS;
def okSL = if IsNaN(rawSL) or isChop then 0 else rawSL;
def okRL = if IsNaN(rawRL) or isChop then 0 else rawRL;
def okFS = if IsNaN(rawFS) or isChop then 0 else rawFS;
def okFL = if IsNaN(rawFL) or isChop then 0 else rawFL;
def okHS = if IsNaN(rawHS) or isChop then 0 else rawHS;
def okHL = if IsNaN(rawHL) or isChop then 0 else rawHL;
def okBS = if IsNaN(rawBS) or isChop then 0 else rawBS;
def okBL = if IsNaN(rawBL) or isChop then 0 else rawBL;
def lastS = CompoundValue(1, if IsNaN(lastS[1]) then -100000 else if (okHS or okBS or okSS or okFS or okRS) and bn - lastS[1] > cooldown then bn else lastS[1], -100000);
def lastL = CompoundValue(1, if IsNaN(lastL[1]) then -100000 else if (okHL or okBL or okSL or okFL or okRL) and bn - lastL[1] > cooldown then bn else lastL[1], -100000);
# Priority when several fire on one candle: HTF level, then Failed breakout, then Flip, then Sweep, then POC.
# A Flip that also passes the Sweep rules shows ONE bubble marked "+ SWEEP".
def htfShort = okHS and lastS == bn;
def fboShort = !okHS and okBS and lastS == bn;
def flipShort = !okHS and !okBS and okFS and lastS == bn;
def sweepShort = !okHS and !okBS and !okFS and okSS and lastS == bn;
def reclaimShort = !okHS and !okBS and !okFS and !okSS and okRS and lastS == bn;
def htfLong = okHL and lastL == bn;
def fboLong = !okHL and okBL and lastL == bn;
def flipLong = !okHL and !okBL and okFL and lastL == bn;
def sweepLong = !okHL and !okBL and !okFL and okSL and lastL == bn;
def reclaimLong = !okHL and !okBL and !okFL and !okSL and okRL and lastL == bn;

# Ghosts: a setup that qualified but was not shown because the same-side cooldown was running.
# Shown as a small gray bubble with only T / S / RR, on the first candle of each run.
def anyS = okHS or okBS or okFS or okSS or okRS;
def anyL = okHL or okBL or okFL or okSL or okRL;
def shownS = htfShort or fboShort or flipShort or sweepShort or reclaimShort;
def shownL = htfLong or fboLong or flipLong or sweepLong or reclaimLong;
def ghostS = anyS and !shownS and !anyS[1];
def ghostL = anyL and !shownL and !anyL[1];
def gTgtS = if okHS then close - hsTgtD else if okBS then close - fbsTgtD else if okFS then close - fsTgtD else if okSS then close - sTgtD else close - rsTgtD;
def gStpS = if okHS then hsStop else if okBS then fbsStop else if okFS then fsStop else if okSS then sStop else rsStop;
def gRRS = if okHS then hsRR else if okBS then fbsRR else if okFS then fsRR else if okSS then sRR else rsRR;
def gTgtL = if okHL then close + hlTgtD else if okBL then close + fblTgtD else if okFL then close + flTgtD else if okSL then close + lTgtD else close + rlTgtD;
def gStpL = if okHL then hlStop else if okBL then fblStop else if okFL then flStop else if okSL then lStop else rlStop;
def gRRL = if okHL then hlRR else if okBL then fblRR else if okFL then flRR else if okSL then lRR else rlRR;

# Only show a signal once its candle has closed (a newer bar exists)
def done = !IsNaN(close[-1]);

# ===== Scorecard - one tracked trade at a time: enter at signal close, exit at target / stop / time-out
def sigDirRaw = if htfShort or fboShort or sweepShort or flipShort or reclaimShort then -1 else if htfLong or fboLong or sweepLong or flipLong or reclaimLong then 1 else 0;
def sigType = if sweepShort then 1 else if reclaimShort then 2 else if sweepLong then 3 else if reclaimLong then 4 else if flipShort then 5 else if flipLong then 6 else if htfShort then 7 else if htfLong then 8 else if fboShort then 9 else if fboLong then 10 else 0;
def sigTgt = if sweepShort then close - sTgtD else if reclaimShort then close - rsTgtD else if sweepLong then close + lTgtD else if reclaimLong then close + rlTgtD else if flipShort then close - fsTgtD else if flipLong then close + flTgtD else if htfShort then close - hsTgtD else if htfLong then close + hlTgtD else if fboShort then close - fbsTgtD else if fboLong then close + fblTgtD else 0;
def sigStp = if sweepShort then sStop else if reclaimShort then rsStop else if sweepLong then lStop else if reclaimLong then rlStop else if flipShort then fsStop else if flipLong then flStop else if htfShort then hsStop else if htfLong then hlStop else if fboShort then fbsStop else if fboLong then fblStop else 0;
def sigScore = if htfShort then hsScore else if htfLong then hlScore else if sweepShort or (flipShort and okSS) then sScore else if sweepLong or (flipLong and okSL) then lScore else 0;
# Only track a signal whose target and stop are real numbers
def sigDir = if IsNaN(sigTgt) or IsNaN(sigStp) or IsNaN(sigScore) then 0 else sigDirRaw;

# T2 (runner): the next level beyond T1, at least minTgt further, for whichever signal fired this candle
def t1DS = if htfShort then hsTgtD else if fboShort then fbsTgtD else if flipShort then fsTgtD else if sweepShort then sTgtD else rsTgtD;
def t1DL = if htfLong then hlTgtD else if fboLong then fblTgtD else if flipLong then flTgtD else if sweepLong then lTgtD else rlTgtD;
def t2DS = Min(Min(Min(Dist(poc, yes, t1DS + minTgt), Dist(vw, yes, t1DS + minTgt)), Min(Dist(val, yes, t1DS + minTgt), Dist(vah, yes, t1DS + minTgt))),
               Min(Min(Dist(bbMid, yes, t1DS + minTgt), Dist(pdL, yes, t1DS + minTgt)), Min(Dist(pmL, yes, t1DS + minTgt), Dist(pPOC, yes, t1DS + minTgt))));
def t2DL = Min(Min(Min(Dist(poc, no, t1DL + minTgt), Dist(vw, no, t1DL + minTgt)), Min(Dist(val, no, t1DL + minTgt), Dist(vah, no, t1DL + minTgt))),
               Min(Min(Dist(bbMid, no, t1DL + minTgt), Dist(pdH, no, t1DL + minTgt)), Min(Dist(pmH, no, t1DL + minTgt), Dist(pPOC, no, t1DL + minTgt))));
def sigT2 = if sigDir < 0 and t2DS < 99999 then RT(close - t2DS) else if sigDir > 0 and t2DL < 99999 then RT(close + t2DL) else 0;
def sigT2ok = if IsNaN(sigT2) then 0 else sigT2 != 0;
def sigTgtR = RT(sigTgt);
def sigStpR = RT(sigStp);
# With the HTF bias = short while HTF BEAR, long while HTF BULL
def sigAlign = if sigDir < 0 then htfBear else if sigDir > 0 then htfBull else 0;

def oDir;
def oEnt;
def oTgt;
def oStp;
def oBar;
def oType;
def oScore;
def oAlign;
def openPrev = if bn <= 1 or IsNaN(oDir[1]) then 0 else oDir[1] != 0;
def hitT = if !openPrev then 0 else if oDir[1] < 0 then low <= oTgt[1] else high >= oTgt[1];
def hitS = if !openPrev then 0 else if oDir[1] < 0 then high >= oStp[1] else low <= oStp[1];
def tOut = openPrev and !hitT and !hitS and (bn - oBar[1] >= maxHoldBars or !isRTH);
def resolved = hitT or hitS or tOut;
def isWin = hitT and !hitS;  # target and stop in the same bar counts as a loss
def isLoss = hitS;
def isScratch = tOut;

if (!openPrev or resolved) and sigDir != 0 {
    oDir = sigDir;
    oEnt = close;
    oTgt = sigTgtR;
    oStp = sigStpR;
    oBar = bn;
    oType = sigType;
    oScore = sigScore;
    oAlign = sigAlign;
} else if openPrev and !resolved {
    oDir = oDir[1];
    oEnt = oEnt[1];
    oTgt = oTgt[1];
    oStp = oStp[1];
    oBar = oBar[1];
    oType = oType[1];
    oScore = oScore[1];
    oAlign = oAlign[1];
} else {
    oDir = 0;
    oEnt = 0;
    oTgt = 0;
    oStp = 0;
    oBar = 0;
    oType = 0;
    oScore = 0;
    oAlign = 0;
}

# T2 runner tracker: opened with each tracked signal that has a T2; T2 counts as reached if price gets there
# before the original stop, within 2 x maxHoldBars, inside RTH.
def openedNow = (!openPrev or resolved) and sigDir != 0;
def t2Dir;
def t2Lvl;
def t2Stp;
def t2Bar;
def t2Open = if bn <= 1 or IsNaN(t2Dir[1]) then 0 else t2Dir[1] != 0;
def t2Hit = if !t2Open then 0 else if t2Dir[1] < 0 then low <= t2Lvl[1] else high >= t2Lvl[1];
def t2Fail = t2Open and !t2Hit and ((if t2Dir[1] < 0 then high >= t2Stp[1] else low <= t2Stp[1]) or bn - t2Bar[1] >= 2 * maxHoldBars or !isRTH);
if openedNow and sigT2ok {
    t2Dir = sigDir;
    t2Lvl = sigT2;
    t2Stp = sigStpR;
    t2Bar = bn;
} else if t2Open and !t2Hit and !t2Fail {
    t2Dir = t2Dir[1];
    t2Lvl = t2Lvl[1];
    t2Stp = t2Stp[1];
    t2Bar = t2Bar[1];
} else {
    t2Dir = 0;
    t2Lvl = 0;
    t2Stp = 0;
    t2Bar = 0;
}
def t2Reached = TotalSum(t2Hit);
def t2Total = TotalSum(openedNow and sigT2ok);

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
def w5 = TotalSum(isWin and rType == 5);
def l5 = TotalSum(isLoss and rType == 5);
def w6 = TotalSum(isWin and rType == 6);
def l6 = TotalSum(isLoss and rType == 6);
def w7 = TotalSum(isWin and rType == 7);
def l7 = TotalSum(isLoss and rType == 7);
def w8 = TotalSum(isWin and rType == 8);
def l8 = TotalSum(isLoss and rType == 8);
def w9 = TotalSum(isWin and rType == 9);
def l9 = TotalSum(isLoss and rType == 9);
def w10 = TotalSum(isWin and rType == 10);
def l10 = TotalSum(isLoss and rType == 10);
def wAl = TotalSum(isWin and oAlign[1]);
def lAl = TotalSum(isLoss and oAlign[1]);
def wAg = TotalSum(isWin and !oAlign[1]);
def lAg = TotalSum(isLoss and !oAlign[1]);
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

plot VahFlipSig = if flipShort and done then high + TickSize() * 4 else Double.NaN;
VahFlipSig.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
VahFlipSig.SetDefaultColor(Color.ORANGE);
VahFlipSig.SetLineWeight(3);

plot ValFlipSig = if flipLong and done then low - TickSize() * 4 else Double.NaN;
ValFlipSig.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
ValFlipSig.SetDefaultColor(Color.LIME);
ValFlipSig.SetLineWeight(3);

plot HtfRejSig = if htfShort and done then high + TickSize() * 4 else Double.NaN;
HtfRejSig.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
HtfRejSig.SetDefaultColor(Color.MAGENTA);
HtfRejSig.SetLineWeight(5);

plot HtfHoldSig = if htfLong and done then low - TickSize() * 4 else Double.NaN;
HtfHoldSig.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
HtfHoldSig.SetDefaultColor(Color.MAGENTA);
HtfHoldSig.SetLineWeight(5);

# HTF SMA lines on the intraday chart (completed HTF bars, the values the study trades off)
plot H3Line = if showHtfLines then htf3 else Double.NaN;
H3Line.SetDefaultColor(Color.CYAN);
H3Line.SetStyle(Curve.LONG_DASH);
H3Line.SetLineWeight(2);
plot H2Line = if showHtfLines then htf2 else Double.NaN;
H2Line.SetDefaultColor(Color.DARK_ORANGE);
H2Line.SetStyle(Curve.LONG_DASH);
H2Line.SetLineWeight(2);
plot H1Line = if showHtfLines then htf1 else Double.NaN;
H1Line.SetDefaultColor(Color.LIGHT_GRAY);
H1Line.SetStyle(Curve.LONG_DASH);

# Outcome dots: where each tracked signal hit its target (green) or stop (red)
plot TargetHit = if showOutcomes and isWin then oTgt[1] else Double.NaN;
TargetHit.SetPaintingStrategy(PaintingStrategy.POINTS);
TargetHit.SetDefaultColor(Color.GREEN);
TargetHit.SetLineWeight(4);
plot StopHit = if showOutcomes and isLoss then oStp[1] else Double.NaN;
StopHit.SetPaintingStrategy(PaintingStrategy.POINTS);
StopHit.SetDefaultColor(Color.RED);
StopHit.SetLineWeight(4);

# T2 runner level while a tracked trade is live
plot T2Line = if showT2Line and t2Dir != 0 then t2Lvl else Double.NaN;
T2Line.SetDefaultColor(Color.GREEN);
T2Line.SetStyle(Curve.SHORT_DASH);
T2Line.SetLineWeight(2);

# Failed-breakout arrows
plot FboShortSig = if fboShort and done then high + TickSize() * 4 else Double.NaN;
FboShortSig.SetPaintingStrategy(PaintingStrategy.ARROW_DOWN);
FboShortSig.SetDefaultColor(Color.VIOLET);
FboShortSig.SetLineWeight(5);
plot FboLongSig = if fboLong and done then low - TickSize() * 4 else Double.NaN;
FboLongSig.SetPaintingStrategy(PaintingStrategy.ARROW_UP);
FboLongSig.SetDefaultColor(Color.VIOLET);
FboLongSig.SetLineWeight(5);

# Chop zone shading
AddCloud(if isChop then Highest(high, chopLook) else Double.NaN, if isChop then Lowest(low, chopLook) else Double.NaN, Color.DARK_ORANGE, Color.DARK_ORANGE);

AddChartBubble(sweepShort and done, high,
    "SWEEP SHORT (" + sScore + ")" + (if sTouch > 1 then "  " + sTouch + "x rejected" else "") + (if htfBear then "  HTF bear" else "  at HTF lvl") + "\n" +
    (if sPDH then "PDH " else "") + (if sPWH then "PWH " else "") + (if sPMH then "PMH " else "") + (if sORH then "OR5H " else "") +
    (if sVAH then "VAH " else "") + (if sPOC then "POC " else "") + (if sPPOC then "pPOC " else "") +
    (if sVW then "VWAP " else "") + (if sSMA then "SMA " else "") + (if sH1 then "H1SMA " else "") +
    (if sH2 then "H2SMA " else "") + (if sH3 then "H3SMA " else "") + (if sRU or sRD then "Round " else "") +
    "\nT1 " + AsPrice(RT(close - sTgtD)) + (if t2DS < 99999 then "  T2 " + AsPrice(RT(close - t2DS)) else "") + "  S " + AsPrice(RT(sStop)) + "  RR " + Round(sRR, 2),
    Color.RED, yes);

AddChartBubble(sweepLong and done, low,
    "SWEEP LONG (" + lScore + ")" + (if lTouch > 1 then "  " + lTouch + "x held" else "") + (if htfBull then "  HTF bull" else "  at HTF lvl") + "\n" +
    (if lPDL then "PDL " else "") + (if lPWL then "PWL " else "") + (if lPML then "PML " else "") + (if lORL then "OR5L " else "") +
    (if lVAL then "VAL " else "") + (if lPOC then "POC " else "") + (if lPPOC then "pPOC " else "") +
    (if lVW then "VWAP " else "") + (if lSMA then "SMA " else "") + (if lH1 then "H1SMA " else "") +
    (if lH2 then "H2SMA " else "") + (if lH3 then "H3SMA " else "") + (if lRU or lRD then "Round " else "") +
    "\nT1 " + AsPrice(RT(close + lTgtD)) + (if t2DL < 99999 then "  T2 " + AsPrice(RT(close + t2DL)) else "") + "  S " + AsPrice(RT(lStop)) + "  RR " + Round(lRR, 2),
    Color.GREEN, no);

AddChartBubble(reclaimShort and done, high,
    "POC LOSS SHORT\nT " + AsPrice(RT(close - rsTgtD)) + "  S " + AsPrice(RT(rsStop)) + "  RR " + Round(rsRR, 2),
    Color.DARK_RED, yes);

AddChartBubble(htfShort and done, high,
    (if hSelS == 3 then "4H SMA200" else if hSelS == 2 then "4H SMA21" else "1H SMA50") + " REJECT (" + hsScore + ")" + (if hFirstS then "  FIRST TOUCH" else "") + "\n" +
    "T1 " + AsPrice(RT(close - hsTgtD)) + (if t2DS < 99999 then "  T2 " + AsPrice(RT(close - t2DS)) else "") + "  S " + AsPrice(RT(hsStop)) + "  RR " + Round(hsRR, 2),
    Color.MAGENTA, yes);

AddChartBubble(htfLong and done, low,
    (if hSelL == 3 then "4H SMA200" else if hSelL == 2 then "4H SMA21" else "1H SMA50") + " HOLD (" + hlScore + ")" + (if hFirstL then "  FIRST TOUCH" else "") + "\n" +
    "T1 " + AsPrice(RT(close + hlTgtD)) + (if t2DL < 99999 then "  T2 " + AsPrice(RT(close + t2DL)) else "") + "  S " + AsPrice(RT(hlStop)) + "  RR " + Round(hlRR, 2),
    Color.MAGENTA, no);

AddChartBubble(fboShort and done, high,
    "FAILED BREAKOUT SHORT  " + (if fbSelS == 3 then "4h SMA200" else if fbSelS == 2 then "4h SMA21" else "1h SMA50") + "\n" +
    "T1 " + AsPrice(RT(close - fbsTgtD)) + (if t2DS < 99999 then "  T2 " + AsPrice(RT(close - t2DS)) else "") + "  S " + AsPrice(RT(fbsStop)) + "  RR " + Round(fbsRR, 2),
    Color.VIOLET, yes);

AddChartBubble(fboLong and done, low,
    "FAILED BREAKDOWN LONG  " + (if fbSelL == 3 then "4h SMA200" else if fbSelL == 2 then "4h SMA21" else "1h SMA50") + "\n" +
    "T1 " + AsPrice(RT(close + fblTgtD)) + (if t2DL < 99999 then "  T2 " + AsPrice(RT(close + t2DL)) else "") + "  S " + AsPrice(RT(fblStop)) + "  RR " + Round(fblRR, 2),
    Color.VIOLET, no);

AddChartBubble(showGhosts and ghostS and done, high,
    "T " + AsPrice(RT(gTgtS)) + "  S " + AsPrice(RT(gStpS)) + "  RR " + Round(gRRS, 2), Color.GRAY, yes);
AddChartBubble(showGhosts and ghostL and done, low,
    "T " + AsPrice(RT(gTgtL)) + "  S " + AsPrice(RT(gStpL)) + "  RR " + Round(gRRL, 2), Color.GRAY, no);

AddChartBubble(flipShort and done, high,
    "VAH FLIP SHORT" + (if okSS then " + SWEEP (" + sScore + ")" else "") + "  +" + Round(fsDepth, 2) + " above VAH\nT1 " + AsPrice(RT(close - fsTgtD)) + (if t2DS < 99999 then "  T2 " + AsPrice(RT(close - t2DS)) else "") + "  S " + AsPrice(RT(fsStop)) + "  RR " + Round(fsRR, 2),
    Color.ORANGE, yes);

AddChartBubble(flipLong and done, low,
    "VAL FLIP LONG" + (if okSL then " + SWEEP (" + lScore + ")" else "") + "  -" + Round(flDepth, 2) + " under VAL\nT1 " + AsPrice(RT(close + flTgtD)) + (if t2DL < 99999 then "  T2 " + AsPrice(RT(close + t2DL)) else "") + "  S " + AsPrice(RT(flStop)) + "  RR " + Round(flRR, 2),
    Color.LIME, no);

AddChartBubble(reclaimLong and done, low,
    "POC RECLAIM LONG\nT " + AsPrice(RT(close + rlTgtD)) + "  S " + AsPrice(RT(rlStop)) + "  RR " + Round(rlRR, 2),
    Color.CYAN, no);

# Alerts fire on the first tick of the bar AFTER the signal candle closes
Alert(sweepShort[1], "Journal: SWEEP SHORT - check Bookmap", Alert.BAR, Sound.Ring);
Alert(sweepLong[1], "Journal: SWEEP LONG - check Bookmap", Alert.BAR, Sound.Ring);
Alert(reclaimShort[1], "Journal: POC LOSS SHORT - check Bookmap", Alert.BAR, Sound.Chimes);
Alert(reclaimLong[1], "Journal: POC RECLAIM LONG - check Bookmap", Alert.BAR, Sound.Chimes);
Alert(flipShort[1], "Journal: VAH FLIP SHORT - check Bookmap", Alert.BAR, Sound.Ring);
Alert(fboShort[1], "Journal: FAILED BREAKOUT SHORT - check Bookmap", Alert.BAR, Sound.Bell);
Alert(fboLong[1], "Journal: FAILED BREAKDOWN LONG - check Bookmap", Alert.BAR, Sound.Bell);
Alert(flipLong[1], "Journal: VAL FLIP LONG - check Bookmap", Alert.BAR, Sound.Ring);
Alert(htfShort[1], "Journal: HTF SMA REJECT SHORT - check Bookmap", Alert.BAR, Sound.Bell);
Alert(htfLong[1], "Journal: HTF SMA HOLD LONG - check Bookmap", Alert.BAR, Sound.Bell);

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
AddLabel(yes, "HTF " + (if htfBear then "BEAR" else if htfBull then "BULL" else "MIXED") + " | short " + sScore + " | long " + lScore,
    if htfBear then Color.LIGHT_RED else if htfBull then Color.LIGHT_GREEN else Color.GRAY);
AddLabel(isChop, "CHOP: " + chopN + " EMA crosses / " + chopLook + " bars - signals paused", Color.ORANGE);

# HTF zone heads-up: price within zoneTol of a 4h/1h SMA. Shows the study's value (completed HTF bars)
# and the chart's value (includes the forming HTF bar), which side price is testing from,
# and that fades are allowed at the level even when the bias label disagrees.
def d3 = if IsNaN(htf3) then 99999 else AbsValue(close - htf3);
def d2 = if IsNaN(htf2) then 99999 else AbsValue(close - htf2);
def d1 = if IsNaN(htf1) then 99999 else AbsValue(close - htf1);
def zSel = if d3 <= zoneTol then 3 else if d2 <= zoneTol then 2 else if d1 <= zoneTol then 1 else 0;
def zLvl = if zSel == 3 then htf3 else if zSel == 2 then htf2 else htf1;
def zLive = if zSel == 3 then Average(close(period = htf3Agg), htf3Len) else if zSel == 2 then Average(close(period = htf2Agg), htf2Len) else Average(close(period = htf1Agg), htf1Len);
AddLabel(zSel > 0, "HTF ZONE: " + (if zSel == 3 then "4h SMA200 " else if zSel == 2 then "4h SMA21 " else "1h SMA50 ") + AsPrice(RT(zLvl)) + " (chart " + AsPrice(RT(zLive)) + ") | " +
    (if close < zLvl then "testing from BELOW" else "testing from ABOVE") +
    (if close < zLvl and htfBull then " | HTF BULL -> at level: fades allowed" else if close > zLvl and htfBear then " | HTF BEAR -> at level: holds allowed" else ""),
    Color.YELLOW);

# Scorecard (off by default - turn on showScorecard to review results, not while trading)
AddLabel(showScorecard, "Sweep S " + w1 + "/" + l1 + " | Sweep L " + w3 + "/" + l3 + " | VAH flip " + w5 + "/" + l5 + " | VAL flip " + w6 + "/" + l6 + " | HTF S " + w7 + "/" + l7 + " | HTF L " + w8 + "/" + l8 +
    " | Fail BO S " + w9 + "/" + l9 + " | Fail BO L " + w10 + "/" + l10 + " | net " + Round(netPts, 1) + " pts (W/L, history optimistic)",
    if netPts >= 0 then Color.GREEN else Color.RED);
AddLabel(showScorecard, "With HTF bias " + wAl + "/" + lAl + " | Against HTF bias " + wAg + "/" + lAg + " | T2 reached " + t2Reached + " of " + t2Total + " runners",
    Color.LIGHT_GRAY);

# ----- Debug labels (showDebug = yes) -----
AddLabel(showDebug, "CVD est " + Round(cvd / 1000, 1) + "k | short (lvl " + sConf + " rej " + sTouch + " str " + (upVAH + upVW + upBB) + " cvd " + cvdDn + ") | long (lvl " + lConf + " rej " + lTouch + " str " + (dnVAL + dnVW + dnBB) + " cvd " + cvdUp + ") | time-outs " + scr + " | avg hold " + (if nRes > 0 then Round(holdSum / nRes, 1) else 0) + " bars",
    Color.LIGHT_GRAY);

# Funnel: across all loaded history, how many in-window bars survive each rule in order.
# The step where the count collapses is the rule that is blocking signals.
def fS1 = inWin and sConf > 0;
def fS2 = fS1 and sBiasOK;
def fS3 = fS2 and close < open and (!shortNeedEma or close < emaF);
def fS4 = fS3 and (!needCvd or cvdDn);
def fS5 = fS4 and sScore >= minScore;
def fS6 = fS5 and sRisk <= maxStop;
def fS7 = fS6 and sRR >= minRR;
def fL1 = inWin and lConf > 0;
def fL2 = fL1 and lBiasOK;
def fL3 = fL2 and close > open and (!longNeedEma or close > emaF);
def fL4 = fL3 and (!needCvd or cvdUp);
def fL5 = fL4 and lScore >= minScore;
def fL6 = fL5 and lRisk <= maxStop;
def fL7 = fL6 and lRR >= minRR;
AddLabel(showDebug, "S funnel: window bars " + TotalSum(inWin) + " > swept " + TotalSum(fS1) + " > bias " + TotalSum(fS2) + " > candle/EMA " + TotalSum(fS3) +
    " > CVD " + TotalSum(fS4) + " > score " + TotalSum(fS5) + " > stop " + TotalSum(fS6) + " > RR " + TotalSum(fS7) + " > fired " + TotalSum(sweepShort), Color.LIGHT_GRAY);
AddLabel(showDebug, "L funnel: swept " + TotalSum(fL1) + " > bias " + TotalSum(fL2) + " > candle/EMA " + TotalSum(fL3) +
    " > CVD " + TotalSum(fL4) + " > score " + TotalSum(fL5) + " > stop " + TotalSum(fL6) + " > RR " + TotalSum(fL7) + " > fired " + TotalSum(sweepLong), Color.LIGHT_GRAY);

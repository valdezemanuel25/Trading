"""Python port of thinkorswim/JournalTriggersStrategy.ts (generated from JournalTriggers.ts).

Same setups, gates and one-trade-at-a-time tracker as the ToS strategy, on 5-minute ES bars:
  entry = close of the signal candle; exit = T1, stop, or time-out (maxHoldBars or end of RTH) at that candle's close.
Value area = VWAP_STATIC (POC = VWAP, VAH/VAL = VWAP +/- 1 stdev), the backtest default in ToS.

Where ToS can't tell whether T1 or the stop came first inside one 5-minute candle it counts a loss; with
`intrabar=True` the 1-minute bars inside that candle decide instead.
"""
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from data import bars_1h, bars_4h, bars_5m, bars_day

INF = 99999.0
TICK = 0.25


@dataclass(frozen=True)
class Params:
    # session (ET, bar start times)
    win_start: int = 930
    win_end: int = 1130
    fbo_end: int = 1300
    or_minutes: int = 5
    # indicators
    ema_len: int = 9
    sma_len: int = 50
    bb_len: int = 20
    bb_mult: float = 2.0
    vw_mult: float = 1.0
    htf1_len: int = 50   # 1h
    htf2_len: int = 21   # 4h
    htf3_len: int = 200  # 4h
    round_step: float = 50.0
    # triggers
    lvl_tol: float = 1.0
    accept_tol: float = 1.0
    sweep_look: int = 3
    touch_look: int = 48
    touch_bonus_cap: int = 2
    stretch_look: int = 6
    short_need_ema: bool = True
    long_need_ema: bool = False
    need_cvd: bool = True
    cvd_look: int = 3
    min_score: int = 3
    # flips
    use_flip: bool = True
    flush_pts: float = 15.0
    flush_look: int = 12
    flip_look: int = 6
    flip_max_beyond: float = 8.0
    flip_need_bias: bool = True
    opp_block_bars: int = 12
    # HTF level test
    use_htf: bool = True
    htf_tol: float = 2.0
    first_look: int = 156
    cancel_pts: float = 2.0
    cancel_look: int = 6
    # failed breakout
    use_fbo: bool = True
    fbo_look: int = 24
    # chop
    use_chop: bool = True
    chop_look: int = 12
    chop_crosses: int = 5
    chop_range: float = 15.0
    chop_hold_bars: int = 6
    chop_break: float = 2.0
    # trend / band walk / magnet
    use_trend_filter: bool = True
    trend_slope_bars: int = 3
    trend_slope_pts: float = 2.0
    use_band_walk: bool = True
    walk_look: int = 5
    walk_count: int = 3
    walk_tol: float = 1.0
    use_magnet_check: bool = True
    magnet_pad: float = 3.0
    magnet_pad_t1: float = 8.0
    magnet_look: int = 24
    bb_fail_look: int = 6
    use_strict_trigger: bool = True
    # gates
    use_one_direction: bool = True
    use_cooldown_reset: bool = True
    use_front_run: bool = True
    front_pad: float = 1.0
    front_min: float = 2.0
    front_min_rr: float = 0.7
    # risk
    min_tgt: float = 6.0
    stop_buf: float = 1.0
    max_stop: float = 12.0
    min_rr: float = 1.0
    cooldown: int = 6
    max_hold_bars: int = 12
    # backtest-only
    intrabar: bool = False
    # CVD source: "clv5" = close location of the 5m candle (what ToS uses), "clv1" = close location of each
    # 1-minute candle summed into the 5m bar, "bvc1" = bulk volume classification on 1-minute bars
    # (buy share = Phi(price change / its stdev)), a standard approximation of aggressor flow without ticks.
    # "real" = aggressor buy - sell volume from Databento trades (data/trades_1m/, front-month contract only);
    # bars outside the dates those files cover get delta 0.
    delta_source: str = "clv5"
    # CVD divergence gate for fades: price makes a new high (low) into the level over div_look bars,
    # but CVD does not.
    use_cvd_div: bool = False
    div_look: int = 12
    # CVD flip: the CVD change over the last cvd_look bars turns against the prior move (down for shorts,
    # up for longs) on the signal candle or up to flip_within - 1 candles before it.
    use_cvd_flip: bool = False
    flip_within: int = 1
    # Absorption at the level: within the last sweep_look candles, a candle near the extreme with large delta
    # INTO the level (buyers at a high for shorts, sellers at a low for longs) but a small range.
    # large = |delta| >= abs_delta_mult x its mean, small = range <= abs_range_mult x median range,
    # both over the last abs_norm_look RTH candles.
    use_absorption: bool = False
    abs_delta_mult: float = 2.0
    abs_range_mult: float = 1.0
    abs_norm_look: int = 78  # RTH bars (one session)
    # comma-separated setup codes the CVD gates (div, flip, absorption) skip; default: failed breakouts
    gate_skip: str = "9,10"
    # exits: cap T1 at t1_cap points; move the stop to entry once price has gone be_trigger points in favour (0 = off)
    t1_cap: float = INF
    be_trigger: float = 0.0
    # comma-separated setup codes to switch off, e.g. "1,3" = no sweeps (codes in SETUPS)
    disabled: str = ""
    # value area: "vwap_static" = POC = VWAP, VAH/VAL = VWAP +/- 1 stdev (ToS VWAP_STATIC);
    # "profile" = developing session volume profile from 1-minute bars (ToS PROFILE, ETH reset), see vprofile.py
    va_source: str = "vwap_static"
    va_pct: float = 0.70
    # which inputs the strategy may use:
    #   "all"         = everything above
    #   "core"        = 9 EMA, VWAP (+ its bands) and the value area only. No SMA50, Bollinger Bands, 1h/4h SMAs,
    #                   round numbers or previous day/week/premarket/opening-range levels, so no BB-fail, HTF-test or
    #                   failed-breakout setups, no HTF bias filter, no magnet check and no front-run cap
    #   "core_levels" = core + previous day/week high/low, premarket high/low and the 5-minute opening range
    indicators: str = "all"


SETUPS = {1: "Sweep S", 3: "Sweep L", 5: "VAH flip S", 6: "VAL flip L", 7: "HTF S", 8: "HTF L",
          9: "Fail BO S", 10: "Fail BO L", 11: "BB fail S", 12: "BB fail L"}


# ---------- vectorised helpers (numpy arrays, NaN = level missing) ----------
def rmax(x, n):
    return pd.Series(x).rolling(n, min_periods=1).max().to_numpy()


def rmin(x, n):
    return pd.Series(x).rolling(n, min_periods=1).min().to_numpy()


def rsum(x, n):
    return pd.Series(np.asarray(x, dtype=float)).rolling(n, min_periods=1).sum().to_numpy()


def shift(x, k=1, fill=np.nan):
    x = np.asarray(x, dtype=float)
    out = np.full_like(x, fill)
    out[k:] = x[:-k]
    return out


def ge(a, b):
    """a >= b with NaN -> False (the le/gt/lt helpers below work the same way)."""
    with np.errstate(invalid="ignore"):
        return (a >= b) & ~np.isnan(a) & ~np.isnan(b)


def le(a, b):
    with np.errstate(invalid="ignore"):
        return (a <= b) & ~np.isnan(a) & ~np.isnan(b)


def gt(a, b):
    with np.errstate(invalid="ignore"):
        return (a > b) & ~np.isnan(a) & ~np.isnan(b)


def lt(a, b):
    with np.errstate(invalid="ignore"):
        return (a < b) & ~np.isnan(a) & ~np.isnan(b)


def dist(close, m, below, min_d):
    """ToS Dist(): distance to magnet m in the trade direction if >= min_d, else INF."""
    d = close - m if below else m - close
    ok = ~np.isnan(m) & ~np.isnan(d) & (d >= min_d)
    return np.where(ok, d, INF)


def nearest(close, mags, below, min_d):
    out = np.full(close.shape, INF)
    for m in mags:
        out = np.minimum(out, dist(close, m, below, min_d))
    return out


# ---------- feature computation ----------
def compute(m1, p: Params):
    b = bars_5m(m1)
    idx = b.index
    o, h, l, c, v = (b[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(b)
    f = {}

    # sessions
    tday = (idx + pd.Timedelta(hours=6)).normalize().tz_localize(None)
    new_day = np.r_[True, tday[1:] != tday[:-1]]
    hm = idx.hour * 100 + idx.minute
    is_rth = (hm >= 930) & (hm < 1600)
    in_win = (hm >= p.win_start) & (hm < p.win_end)
    fbo_win = (hm >= p.win_start) & (hm < p.fbo_end)
    rth_open = is_rth & ~np.r_[False, is_rth[:-1]]
    day_id = np.cumsum(new_day)
    rth_seen = pd.Series(is_rth).groupby(day_id).cummax().to_numpy()
    pre = ~rth_seen
    on_hi = pd.Series(np.where(pre, h, np.nan)).groupby(day_id).cummax().groupby(day_id).ffill().to_numpy()
    on_lo = pd.Series(np.where(pre, l, np.nan)).groupby(day_id).cummin().groupby(day_id).ffill().to_numpy()
    pmH = np.where(rth_seen, on_hi, np.nan)
    pmL = np.where(rth_seen, on_lo, np.nan)
    in_or = is_rth & (hm >= 930) & (hm < 930 + p.or_minutes)
    or_hi = pd.Series(np.where(in_or, h, np.nan)).groupby(day_id).cummax().groupby(day_id).ffill().to_numpy()
    or_lo = pd.Series(np.where(in_or, l, np.nan)).groupby(day_id).cummin().groupby(day_id).ffill().to_numpy()
    or5H = np.where(is_rth & ~in_or, or_hi, np.nan)
    or5L = np.where(is_rth & ~in_or, or_lo, np.nan)

    # indicators
    cs = pd.Series(c)
    emaF = cs.ewm(span=p.ema_len, adjust=False).mean().to_numpy()
    smaC = cs.rolling(p.sma_len).mean().to_numpy()
    bbMid = cs.rolling(p.bb_len).mean().to_numpy()
    bbSd = cs.rolling(p.bb_len).std(ddof=0).to_numpy()
    bbUp, bbLo = bbMid + p.bb_mult * bbSd, bbMid - p.bb_mult * bbSd

    hlc3 = (h + l + c) / 3
    g = pd.DataFrame({"pv": hlc3 * v, "v": v, "pv2": hlc3 ** 2 * v}).groupby(day_id).cumsum()
    with np.errstate(invalid="ignore", divide="ignore"):
        vw = np.where(g["v"] > 0, g["pv"] / g["v"], np.nan)
        vwSd = np.sqrt(np.maximum(np.where(g["v"] > 0, g["pv2"] / g["v"], np.nan) - vw ** 2, 0))
    vwUp, vwLo = vw + p.vw_mult * vwSd, vw - p.vw_mult * vwSd

    # higher timeframe: SMA of COMPLETED HTF bars (ToS Average(close(period)[1], len))
    def htf_map(hb, length):
        sma = hb["close"].shift(1).rolling(length).mean()
        prev_close = hb["close"].shift(1)
        frame = pd.DataFrame({"sma": sma, "pc": prev_close}, index=hb.index)
        m = frame.reindex(idx, method="ffill")
        return m["sma"].to_numpy(), m["pc"].to_numpy()

    h1b, h4b = bars_1h(m1), bars_4h(m1)
    htf1, htf1Close = htf_map(h1b, p.htf1_len)
    htf2, htf2Close = htf_map(h4b, p.htf2_len)
    htf3, _ = htf_map(h4b, p.htf3_len)
    htfBear = lt(htf1Close, htf1) & lt(htf2Close, htf2)
    htfBull = gt(htf1Close, htf1) & gt(htf2Close, htf2)

    day = bars_day(m1)
    prev_day = day.shift(1)
    pdH = prev_day["high"].reindex(tday).to_numpy()
    pdL = prev_day["low"].reindex(tday).to_numpy()
    wk = day.index - pd.to_timedelta(day.index.weekday, unit="D")
    week = day.groupby(wk).agg(high=("high", "max"), low=("low", "min"))
    prev_week = week.shift(1)
    tday_wk = tday - pd.to_timedelta(tday.weekday, unit="D")
    pwH = prev_week["high"].reindex(tday_wk).to_numpy()
    pwL = prev_week["low"].reindex(tday_wk).to_numpy()

    rUp = np.ceil(c / p.round_step) * p.round_step
    rDn = np.floor(c / p.round_step) * p.round_step

    if p.va_source == "profile":
        from vprofile import developing_profile
        vp = developing_profile(m1, p.va_pct).reindex(idx)
        poc, vah, val = (vp[k].to_numpy() for k in ("poc", "vah", "val"))
    else:
        poc, vah, val = vw, vw + vwSd, vw - vwSd
    if p.indicators != "all":
        none = np.full(n, np.nan)
        smaC = bbUp = bbLo = bbMid = htf1 = htf2 = htf3 = rUp = rDn = none
        htfBear = htfBull = np.ones(n, dtype=bool)  # no HTF trend source: bias filter off
        if p.indicators == "core":
            pdH = pdL = pwH = pwL = pmH = pmL = or5H = or5L = none
    pPOC = pd.Series(np.where(new_day, shift(poc), np.nan)).ffill().to_numpy()

    rng = h - l
    if p.delta_source == "clv5":
        barDelta = np.where(rng > 0, v * ((c - l) - (h - c)) / np.where(rng > 0, rng, 1), 0.0)
    else:
        src = real_delta(m1) if p.delta_source == "real" else minute_delta(m1, p.delta_source)
        barDelta = src.reindex(idx).fillna(0).to_numpy()
    cvd = pd.Series(barDelta).groupby(day_id).cumsum().to_numpy()
    cvdUp = (barDelta > 0) & gt(cvd, shift(cvd, p.cvd_look))
    cvdDn = (barDelta < 0) & lt(cvd, shift(cvd, p.cvd_look))

    hh3, ll3 = rmax(h, p.sweep_look), rmin(l, p.sweep_look)
    hc3, lc3 = rmax(c, p.sweep_look), rmin(c, p.sweep_look)

    def sw(lvl, short):
        if short:
            touch = ge(h, lvl - p.lvl_tol) & lt(c, lvl)
            swept = ge(hh3, lvl - p.lvl_tol) & le(hc3, lvl + p.accept_tol) & lt(c, lvl)
        else:
            touch = le(l, lvl + p.lvl_tol) & gt(c, lvl)
            swept = le(ll3, lvl + p.lvl_tol) & ge(lc3, lvl - p.accept_tol) & gt(c, lvl)
        t_start = touch & ~np.r_[False, touch[:-1]]
        touches = rsum(t_start, p.touch_look)
        return np.where(swept, np.maximum(touches, 1), 0)

    levels = {"PDH": pdH, "PDL": pdL, "PWH": pwH, "PWL": pwL, "PMH": pmH, "PML": pmL, "OR5H": or5H,
              "OR5L": or5L, "POC": poc, "VAH": vah, "VAL": val, "pPOC": pPOC, "VWAP": vw, "SMA": smaC,
              "H1": htf1, "H2": htf2, "H3": htf3, "RU": rUp, "RD": rDn}
    s_sw = {k: sw(lv, True) for k, lv in levels.items()}
    l_sw = {k: sw(lv, False) for k, lv in levels.items()}
    sConf = sum((s_sw[k] > 0).astype(int) for k in levels)
    lConf = sum((l_sw[k] > 0).astype(int) for k in levels)
    sTouch = np.max(np.vstack(list(s_sw.values())), axis=0)
    lTouch = np.max(np.vstack(list(l_sw.values())), axis=0)
    sAtHtf = np.any(np.vstack([s_sw[k] > 0 for k in ("PDH", "PWH", "H1", "H2", "H3", "RU", "RD")]), axis=0)
    lAtHtf = np.any(np.vstack([l_sw[k] > 0 for k in ("PDL", "PWL", "H1", "H2", "H3", "RU", "RD")]), axis=0)

    def roll_ge0(x, nn):
        r = pd.Series(x).rolling(nn, min_periods=1).max().to_numpy()
        return ge(r, 0)

    def roll_le0(x, nn):
        r = pd.Series(x).rolling(nn, min_periods=1).min().to_numpy()
        return le(r, 0)

    upVAH, upVW, upBB = roll_ge0(h - vah, p.stretch_look), roll_ge0(h - vwUp, p.stretch_look), roll_ge0(h - bbUp, p.stretch_look)
    dnVAL, dnVW, dnBB = roll_le0(l - val, p.stretch_look), roll_le0(l - vwLo, p.stretch_look), roll_le0(l - bbLo, p.stretch_look)
    bonusS = np.minimum(np.maximum(sTouch - 1, 0), p.touch_bonus_cap)
    bonusL = np.minimum(np.maximum(lTouch - 1, 0), p.touch_bonus_cap)
    sScore = sConf + bonusS + upVAH + upVW + upBB + cvdDn
    lScore = lConf + bonusL + dnVAL + dnVW + dnBB + cvdUp
    sBiasOK = htfBear | sAtHtf
    lBiasOK = htfBull | lAtHtf

    def tgt(stop, short, mags):
        risk = stop - c if short else c - stop
        need = np.maximum(p.min_tgt, p.min_rr * risk)
        d = nearest(c, mags, short, need)
        with np.errstate(invalid="ignore", divide="ignore"):
            rr = np.where((d < INF) & (risk > 0), d / np.where(risk > 0, risk, 1), 0)
        return risk, d, rr

    raw, stops, risks, tgts = {}, {}, {}, {}

    # 1) sweep short / 2) sweep long
    stops[1] = hh3 + p.stop_buf
    risks[1], tgts[1], rr = tgt(stops[1], True, [poc, vw, val, pPOC, bbMid, vwLo, pdL, pmL])
    raw[1] = (in_win & (sConf > 0) & sBiasOK & (c < o) & ((not p.short_need_ema) | lt(c, emaF)) & ((not p.need_cvd) | cvdDn)
              & (sScore >= p.min_score) & (rr >= p.min_rr) & (risks[1] <= p.max_stop))
    stops[3] = ll3 - p.stop_buf
    risks[3], tgts[3], rr = tgt(stops[3], False, [poc, vw, vah, pPOC, bbMid, emaF, vwUp, pdH, pmH])
    raw[3] = (in_win & (lConf > 0) & lBiasOK & (c > o) & ((not p.long_need_ema) | gt(c, emaF)) & ((not p.need_cvd) | cvdUp)
              & (lScore >= p.min_score) & (rr >= p.min_rr) & (risks[3] <= p.max_stop))

    # 4) VAL flip long / VAH flip short
    flLow = rmin(l, p.flip_look)
    flushDn = rmax(h, p.flush_look) - flLow >= p.flush_pts
    flFromValue = le(rmax(h, p.flush_look), vah + p.lvl_tol)
    flDepth = val - flLow
    flBelow = gt(flDepth, p.lvl_tol) & le(flDepth, p.flip_max_beyond)
    flPrevNear = le(np.fmin(shift(c) - shift(val), shift(c, 2) - shift(val, 2)), p.lvl_tol)
    flStrong = (c > o) & (c - l >= 0.6 * (h - l))
    stops[6] = flLow - p.stop_buf
    risks[6], tgts[6], rr = tgt(stops[6], False, [poc, vw, pPOC, bbMid, vah])
    raw[6] = (p.use_flip & in_win & ((not p.flip_need_bias) | lBiasOK) & gt(c, val) & flPrevNear & flBelow & flushDn
              & flFromValue & (dnVW | dnBB) & flStrong & (barDelta > 0) & (rr >= p.min_rr) & (risks[6] <= p.max_stop))
    fsHigh = rmax(h, p.flip_look)
    flushUp = fsHigh - rmin(l, p.flush_look) >= p.flush_pts
    fsFromValue = ge(rmin(l, p.flush_look), val - p.lvl_tol)
    fsDepth = fsHigh - vah
    fsAbove = gt(fsDepth, p.lvl_tol) & le(fsDepth, p.flip_max_beyond)
    fsPrevNear = ge(np.fmax(shift(c) - shift(vah), shift(c, 2) - shift(vah, 2)), -p.lvl_tol)
    fsStrong = (c < o) & (h - c >= 0.6 * (h - l))
    stops[5] = fsHigh + p.stop_buf
    risks[5], tgts[5], rr = tgt(stops[5], True, [poc, vw, pPOC, bbMid, val])
    raw[5] = (p.use_flip & in_win & ((not p.flip_need_bias) | sBiasOK) & lt(c, vah) & fsPrevNear & fsAbove & flushUp
              & fsFromValue & (upVW | upBB) & fsStrong & (barDelta < 0) & (rr >= p.min_rr) & (risks[5] <= p.max_stop))

    # 5) HTF level test
    def htf_rej(L, short):
        nanL = np.isnan(L)
        zone = ge(h, L - p.htf_tol) & le(l, L + p.htf_tol)
        if short:
            side_close = gt(c, L)
            cancel = gt(c, L + p.cancel_pts)
            swept = ge(hh3, L - p.htf_tol)
            back = lt(c, L)
        else:
            side_close = lt(c, L)
            cancel = lt(c, L - p.cancel_pts)
            swept = le(ll3, L + p.htf_tol)
            back = gt(c, L)
        prior_side = shift(rsum(side_close, p.first_look), p.sweep_look)
        prior_touch = shift(rsum(zone, p.first_look), p.sweep_look)
        accepted = rsum(cancel, p.cancel_look) >= 2
        ok = ~nanL & swept & (prior_side == 0) & ~accepted & back
        return np.where(ok, np.where(prior_touch == 0, 2, 1), 0)

    hS = [htf_rej(L, True) for L in (htf3, htf2, htf1)]
    hL = [htf_rej(L, False) for L in (htf3, htf2, htf1)]
    hSelS = np.select([hS[0] > 0, hS[1] > 0, hS[2] > 0], [3, 2, 1], 0)
    hSelL = np.select([hL[0] > 0, hL[1] > 0, hL[2] > 0], [3, 2, 1], 0)
    hLvlS = np.select([hSelS == 3, hSelS == 2, hSelS == 1], [htf3, htf2, htf1], np.nan)
    hLvlL = np.select([hSelL == 3, hSelL == 2, hSelL == 1], [htf3, htf2, htf1], np.nan)
    hFirstS = np.select([hSelS == 3, hSelS == 2], [hS[0], hS[1]], hS[2]) == 2
    hFirstL = np.select([hSelL == 3, hSelL == 2], [hL[0], hL[1]], hL[2]) == 2
    hsScore = 3 + 2 * hFirstS + upVAH + upVW + upBB + cvdDn + sConf
    hlScore = 3 + 2 * hFirstL + dnVAL + dnVW + dnBB + cvdUp + lConf
    stops[7] = np.fmax(hh3, hLvlS) + p.stop_buf
    stops[7] = np.where(np.isnan(hLvlS), np.nan, stops[7])
    risks[7], tgts[7], rr = tgt(stops[7], True, [vah, poc, vw, bbMid, val])
    raw[7] = p.use_htf & in_win & (hSelS > 0) & (c < o) & ((not p.short_need_ema) | lt(c, emaF)) & (rr >= p.min_rr) & le(risks[7], p.max_stop)
    stops[8] = np.where(np.isnan(hLvlL), np.nan, np.fmin(ll3, hLvlL) - p.stop_buf)
    risks[8], tgts[8], rr = tgt(stops[8], False, [val, poc, vw, bbMid, vah])
    raw[8] = p.use_htf & in_win & (hSelL > 0) & (c > o) & ((not p.long_need_ema) | gt(c, emaF)) & (rr >= p.min_rr) & le(risks[8], p.max_stop)

    # 6) failed breakout / breakdown
    def fbo(L, short):
        acc_hit = gt(c, L + p.cancel_pts) if short else lt(c, L - p.cancel_pts)
        accepted = shift(rsum(acc_hit, p.fbo_look), 1) >= 2
        if short:
            cross = lt(c, L) & ge(shift(c), shift(L))
        else:
            cross = gt(c, L) & le(shift(c), shift(L))
        return accepted & cross

    fbS = [fbo(L, True) for L in (htf3, htf2, htf1)]
    fbL = [fbo(L, False) for L in (htf3, htf2, htf1)]
    fbSelS = np.select(fbS, [3, 2, 1], 0)
    fbSelL = np.select(fbL, [3, 2, 1], 0)
    stops[9] = hh3 + p.stop_buf
    risks[9], tgts[9], rr = tgt(stops[9], True, [vah, poc, vw, bbMid, val])
    raw[9] = p.use_fbo & fbo_win & (fbSelS > 0) & (c < o) & lt(c, emaF) & (rr >= p.min_rr) & (risks[9] <= p.max_stop)
    stops[10] = ll3 - p.stop_buf
    risks[10], tgts[10], rr = tgt(stops[10], False, [val, poc, vw, bbMid, vah])
    raw[10] = p.use_fbo & fbo_win & (fbSelL > 0) & (c > o) & gt(c, emaF) & (rr >= p.min_rr) & (risks[10] <= p.max_stop)

    # chop (raw; the hold part is recursive and done in the loop)
    ema_side = c > emaF
    ema_cross = np.r_[False, ema_side[1:] != ema_side[:-1]]
    chopN = rsum(ema_cross, p.chop_look)
    chopHiRaw, chopLoRaw = rmax(h, p.chop_look), rmin(l, p.chop_look)
    isChopRaw = p.use_chop & (chopN >= p.chop_crosses) & (chopHiRaw - chopLoRaw <= p.chop_range)

    # trend filter / band walk / magnet
    slope = emaF - shift(emaF, p.trend_slope_bars)
    trendDn = lt(slope, -p.trend_slope_pts) & lt(c, vw)
    trendUp = gt(slope, p.trend_slope_pts) & gt(c, vw)
    trendBlockL = p.use_trend_filter & trendDn & (c <= emaF)
    trendBlockS = p.use_trend_filter & trendUp & (c >= emaF)
    width = bbUp - bbLo
    expand = gt(width, shift(width, 3))
    walkUpN = rsum(ge(c, bbUp - p.walk_tol), p.walk_look)
    walkDnN = rsum(le(c, bbLo + p.walk_tol), p.walk_look)
    walkBlockS = p.use_band_walk & expand & (walkUpN >= p.walk_count) & gt(c, bbMid)
    walkBlockL = p.use_band_walk & expand & (walkDnN >= p.walk_count) & lt(c, bbMid)

    zoneTopS = rmax(h, p.flip_look) + p.stop_buf + p.magnet_pad
    zoneBotL = rmin(l, p.flip_look) - p.stop_buf - p.magnet_pad
    zoneTopS1 = zoneTopS + p.magnet_pad_t1 - p.magnet_pad
    zoneBotL1 = zoneBotL - p.magnet_pad_t1 + p.magnet_pad
    hiM, loM = rmax(h, p.magnet_look), rmin(l, p.magnet_look)

    def mag_s(L, zone):
        ok = gt(L, c) & le(L, zone) & lt(hiM, L - p.lvl_tol)
        return np.where(ok, L, INF)

    def mag_l(L, zone):
        ok = lt(L, c) & ge(L, zone) & gt(loM, L + p.lvl_tol)
        return np.where(ok, L, -INF)

    magS = np.minimum.reduce([mag_s(htf3, zoneTopS1), mag_s(htf2, zoneTopS1), mag_s(htf1, zoneTopS), mag_s(pdH, zoneTopS),
                              mag_s(pwH, zoneTopS1), mag_s(pmH, zoneTopS), mag_s(rUp, zoneTopS)])
    magL = np.maximum.reduce([mag_l(htf3, zoneBotL1), mag_l(htf2, zoneBotL1), mag_l(htf1, zoneBotL), mag_l(pdL, zoneBotL),
                              mag_l(pwL, zoneBotL1), mag_l(pmL, zoneBotL), mag_l(rDn, zoneBotL)])
    magBlockS = p.use_magnet_check & (magS < INF)
    magBlockL = p.use_magnet_check & (magL > -INF)
    fadeBlockS = trendBlockS | walkBlockS | magBlockS
    fadeBlockL = trendBlockL | walkBlockL | magBlockL

    # 7) BB FAIL
    def tagged(L):
        return ge(rmax(h, p.bb_fail_look), L - p.lvl_tol) & le(rmin(l, p.bb_fail_look), L + p.lvl_tol)

    keyS = np.any(np.vstack([tagged(L) for L in (htf3, htf2, htf1, pdH, pwH, pmH, rUp, vah)]), axis=0)
    keyL = np.any(np.vstack([tagged(L) for L in (htf3, htf2, htf1, pdL, pwL, pmL, rDn, val)]), axis=0)
    bandTagUp = roll_ge0(h - bbUp, 3)
    bandTagDn = roll_le0(l - bbLo, 3)
    stops[11] = hh3 + p.stop_buf
    risks[11], tgts[11], rr = tgt(stops[11], True, [bbMid, vw, poc, vah, val])
    xsReal = (not p.use_strict_trigger) | lt(c, emaF) | (lt(h, shift(rmax(h, 3))) & lt(c, shift(l)))
    raw[11] = (p.use_magnet_check & in_win & keyS & bandTagUp & lt(c, bbUp) & (c < o) & xsReal
               & (rr >= p.min_rr) & (risks[11] <= p.max_stop))
    stops[12] = ll3 - p.stop_buf
    risks[12], tgts[12], rr = tgt(stops[12], False, [bbMid, vw, poc, val, vah])
    xlReal = (not p.use_strict_trigger) | gt(c, emaF) | (gt(l, shift(rmin(l, 3))) & gt(c, shift(h)))
    raw[12] = (p.use_magnet_check & in_win & keyL & bandTagDn & gt(c, bbLo) & (c > o) & xlReal
               & (rr >= p.min_rr) & (risks[12] <= p.max_stop))

    # front-run: cap T1 before the first obstacle (HTF SMAs + previous day/week H/L); no cap with the trend
    obsS = nearest(c, [htf1, htf2, htf3, pdH, pdL, pwH, pwL], True, p.front_min)
    obsL = nearest(c, [htf1, htf2, htf3, pdH, pdL, pwH, pwL], False, p.front_min)
    roomS = np.where(p.use_front_run & (obsS < INF) & ~trendDn, obsS - p.front_pad, INF)
    roomL = np.where(p.use_front_run & (obsL < INF) & ~trendUp, obsL - p.front_pad, INF)

    # CVD divergence at the level (fades only)
    prevHi = shift(rmax(h, p.div_look - p.sweep_look), p.sweep_look)
    prevLo = shift(rmin(l, p.div_look - p.sweep_look), p.sweep_look)
    prevCvdHi = shift(rmax(cvd, p.div_look - p.sweep_look), p.sweep_look)
    prevCvdLo = shift(rmin(cvd, p.div_look - p.sweep_look), p.sweep_look)
    bearDiv = ge(hh3, prevHi) & lt(rmax(cvd, p.sweep_look), prevCvdHi)
    bullDiv = le(ll3, prevLo) & gt(rmin(cvd, p.sweep_look), prevCvdLo)

    # CVD flip: 3-bar CVD change turns negative (short) / positive (long) on this candle
    d3 = cvd - shift(cvd, p.cvd_look)
    flipDnNow = lt(d3, 0) & ge(shift(d3), 0)
    flipUpNow = gt(d3, 0) & le(shift(d3), 0)
    flipDn = roll_ge0(np.where(flipDnNow, 0.0, -1.0), p.flip_within)
    flipUp = roll_ge0(np.where(flipUpNow, 0.0, -1.0), p.flip_within)

    # absorption: big delta into the extreme with a small range
    # normalised over RTH bars only: overnight bars are much quieter and would make every RTH bar look large
    rth_i = np.flatnonzero(is_rth)
    absD, medR = np.full(n, np.nan), np.full(n, np.nan)
    absD[rth_i] = pd.Series(np.abs(barDelta[rth_i])).rolling(p.abs_norm_look, min_periods=12).mean().to_numpy()
    medR[rth_i] = pd.Series(rng[rth_i]).rolling(p.abs_norm_look, min_periods=12).median().to_numpy()
    small = le(rng, p.abs_range_mult * medR)
    absBuy = small & ge(barDelta, p.abs_delta_mult * absD) & (barDelta > 0)
    absSell = small & le(barDelta, -p.abs_delta_mult * absD) & (barDelta < 0)
    absS = roll_ge0(np.where(absBuy & ge(h, hh3 - p.lvl_tol), 0.0, -1.0), p.sweep_look)
    absL = roll_ge0(np.where(absSell & le(l, ll3 + p.lvl_tol), 0.0, -1.0), p.sweep_look)

    skip = {int(x) for x in p.gate_skip.split(",") if x.strip()}
    short_types = (1, 5, 7, 9, 11)
    ok, t1 = {}, {}
    for k in raw:
        short = k in short_types
        room = roomS if short else roomL
        t1[k] = np.where(tgts[k] >= INF, INF, np.minimum(tgts[k], room))
        risk = risks[k]
        with np.errstate(invalid="ignore", divide="ignore"):
            rrc = np.where((t1[k] < INF) & (risk > 0), t1[k] / np.where(risk > 0, risk, 1), 0)
        block = fadeBlockS if short else fadeBlockL
        ok[k] = np.nan_to_num(raw[k], nan=0).astype(bool) & ~block & (rrc >= p.front_min_rr)
        if k not in skip:
            if p.use_cvd_div:
                ok[k] &= bearDiv if short else bullDiv
            if p.use_cvd_flip:
                ok[k] &= flipDn if short else flipUp
            if p.use_absorption:
                ok[k] &= absS if short else absL
        # chop is applied in the loop (it has a recursive hold)

    f.update(dict(index=idx, o=o, h=h, l=l, c=c, is_rth=is_rth, new_day=new_day, ok=ok, t1=t1, stops=stops,
                  isChopRaw=isChopRaw, chopHiRaw=chopHiRaw, chopLoRaw=chopLoRaw, htfBear=htfBear, htfBull=htfBull,
                  scoreS=sScore, scoreL=lScore, hsScore=hsScore, hlScore=hlScore,
                  t2magsS=[poc, vw, val, vah, bbMid, pdL, pmL, pPOC], t2magsL=[poc, vw, val, vah, bbMid, pdH, pmH, pPOC]))
    return f


def minute_delta(m1, source):
    """Signed volume per 5m bar built from 1-minute bars."""
    h, l, c, v = (m1[k].to_numpy(float) for k in ("high", "low", "close", "volume"))
    if source == "clv1":
        rng = h - l
        d = np.where(rng > 0, v * ((c - l) - (h - c)) / np.where(rng > 0, rng, 1), 0.0)
    elif source == "bvc1":
        import math
        dp = np.diff(c, prepend=c[0])
        sd = pd.Series(dp).rolling(390, min_periods=30).std().to_numpy()
        z = np.where(sd > 0, dp / np.where(sd > 0, sd, 1), 0.0)
        phi = 0.5 * (1 + np.vectorize(math.erf)(z / math.sqrt(2)))
        d = v * (2 * phi - 1)
    else:
        raise ValueError(source)
    ser = pd.Series(d, index=m1.index)
    return ser.resample("5min", label="left", closed="left").sum()


def real_delta(m1):
    """Aggressor buy - sell volume per 5m bar from data/trades_1m/, for the contract load_1m() uses that minute.
    NaN where the trades files have no data."""
    import glob
    import io
    import os
    from data import DATA_DIR, TZ
    from zstd_io import read_zst

    files = sorted(glob.glob(os.path.join(DATA_DIR, "trades_1m", "es_trades_1m_*.csv.zst")))
    if not files:
        raise SystemExit("No data/trades_1m files: run backtest/fetch_trades.py first")
    tr = pd.concat([pd.read_csv(io.BytesIO(read_zst(f))) for f in files], ignore_index=True)
    tr["ts"] = pd.to_datetime(tr["ts"], utc=True).dt.tz_convert(TZ)
    tr["delta"] = tr["buy_vol"] - tr["sell_vol"]
    front = pd.DataFrame({"ts": m1.index, "symbol": m1["symbol"].to_numpy()})
    tr = tr.merge(front, on=["ts", "symbol"], how="inner")
    d = tr.set_index("ts")["delta"].sort_index()
    out = d.resample("5min", label="left", closed="left").sum(min_count=1)
    return out


def rt(x):
    return np.round(x / TICK) * TICK


# ---------- sequential gates + one-trade-at-a-time tracker ----------
def run(m1, p: Params = Params(), feats=None):
    f = feats if feats is not None else compute(m1, p)
    idx, h, l, c, is_rth = f["index"], f["h"], f["l"], f["c"], f["is_rth"]
    ok, t1, stops = f["ok"], f["t1"], f["stops"]
    n = len(c)
    m1_high = m1["high"] if p.intrabar else None
    m1_low = m1["low"] if p.intrabar else None

    off = {int(x) for x in p.disabled.split(",") if x.strip()}
    S_ORDER = (7, 9, 11, 5, 1)    # HTF, failed breakout, BB fail, flip, sweep
    L_ORDER = (8, 10, 12, 6, 3)
    trades = []
    # chop hold
    chop_hi = chop_lo = np.nan
    chop_until = -1
    # opposite-flip block
    lastLpre = lastSpre = -100000
    lStopVal = sStopVal = np.nan
    lStopped = sStopped = False
    # cooldown
    lastS = lastL = -100000
    lastLoss = -100000
    # tracked trade
    o_dir = 0
    o_ent = o_tgt = o_stp = 0.0
    o_bar = 0
    o_type = 0
    o_info = None
    # T2 runner
    t2_dir, t2_lvl, t2_stp, t2_bar = 0, 0.0, 0.0, 0
    t2_hits = t2_total = 0

    for i in range(n):
        # chop with hold
        if f["isChopRaw"][i]:
            chop_hi, chop_lo, chop_until = f["chopHiRaw"][i], f["chopLoRaw"][i], i + p.chop_hold_bars
        held = (p.use_chop and not np.isnan(chop_hi) and i <= chop_until
                and chop_lo - p.chop_break <= c[i] <= chop_hi + p.chop_break)
        is_chop = bool(f["isChopRaw"][i]) or held

        okS = {k: bool(ok[k][i]) and not is_chop and k not in off for k in S_ORDER}
        okL = {k: bool(ok[k][i]) and not is_chop and k not in off for k in L_ORDER}

        # resolve the tracked trade (from the previous candle's levels)
        open_prev = o_dir != 0
        hitT = hitS = tOut = False
        if open_prev:
            if o_dir < 0:
                hitT, hitS = l[i] <= o_tgt, h[i] >= o_stp
            else:
                hitT, hitS = h[i] >= o_tgt, l[i] <= o_stp
            if hitT and hitS and p.intrabar:
                hitT, hitS = _intrabar_order(idx[i], o_dir, o_tgt, o_stp, m1_high, m1_low)
            tOut = not hitT and not hitS and (i - o_bar >= p.max_hold_bars or not is_rth[i])
            if p.be_trigger > 0 and not (hitT or hitS or tOut):
                fav = (o_ent - l[i]) if o_dir < 0 else (h[i] - o_ent)
                if fav >= p.be_trigger:
                    o_stp = min(o_stp, o_ent) if o_dir < 0 else max(o_stp, o_ent)
        resolved = hitT or hitS or tOut
        if resolved:
            if hitT and not hitS:
                res, px = "T1", o_tgt
            elif hitS:
                res, px = "Stop", o_stp
            else:
                res, px = "Time", c[i]
            pts = (px - o_ent) * o_dir
            trades.append({**o_info, "exit_time": idx[i], "exit": px, "result": res, "pts": pts})
            if hitS:
                lastLoss = i
            o_dir = 0

        # T2 runner state
        t2_open = t2_dir != 0
        t2_hit = t2_fail = False
        if t2_open:
            t2_hit = (l[i] <= t2_lvl) if t2_dir < 0 else (h[i] >= t2_lvl)
            stop_hit = (h[i] >= t2_stp) if t2_dir < 0 else (l[i] <= t2_stp)
            t2_fail = not t2_hit and (stop_hit or i - t2_bar >= 2 * p.max_hold_bars or not is_rth[i])
            if t2_hit:
                t2_hits += 1
            if t2_hit or t2_fail:
                t2_dir = 0
        trade_live = open_prev and not resolved
        runner_s = t2_open and not t2_hit and not t2_fail and t2_dir < 0
        runner_l = t2_open and not t2_hit and not t2_fail and t2_dir > 0
        block_s = p.use_one_direction and (trade_live or runner_l)
        block_l = p.use_one_direction and (trade_live or runner_s)

        # opposite-flip block (flips only)
        anyLpre = any(okL.values())
        anySpre = any(okS.values())
        if anyLpre:
            k = next(k for k in L_ORDER if okL[k])
            lastLpre, lStopVal, lStopped = i, stops[k][i], False
        elif not np.isnan(lStopVal) and l[i] <= lStopVal:
            lStopped = True
        if anySpre:
            k = next(k for k in S_ORDER if okS[k])
            lastSpre, sStopVal, sStopped = i, stops[k][i], False
        elif not np.isnan(sStopVal) and h[i] >= sStopVal:
            sStopped = True
        if okS[5] and i - lastLpre <= p.opp_block_bars and not lStopped:
            okS[5] = False
        if okL[6] and i - lastSpre <= p.opp_block_bars and not sStopped:
            okL[6] = False

        # cooldown + priority
        fired_s = fired_l = 0
        if any(okS.values()) and not block_s and (i - lastS > p.cooldown or (p.use_cooldown_reset and lastLoss > lastS)):
            lastS = i
            fired_s = next(k for k in S_ORDER if okS[k])
        if any(okL.values()) and not block_l and (i - lastL > p.cooldown or (p.use_cooldown_reset and lastLoss > lastL)):
            lastL = i
            fired_l = next(k for k in L_ORDER if okL[k])

        sig = fired_s or fired_l  # a short wins if both fire on one candle (as in ToS)
        if sig and (not open_prev or resolved):
            d = -1 if fired_s else 1
            tg, st = rt(c[i] + d * min(t1[sig][i], p.t1_cap)), rt(stops[sig][i])
            if np.isnan(tg) or np.isnan(st):
                continue
            o_dir, o_ent, o_tgt, o_stp, o_bar, o_type = d, c[i], tg, st, i, sig
            score = {1: f["scoreS"], 3: f["scoreL"], 7: f["hsScore"], 8: f["hlScore"]}.get(sig)
            o_info = {"entry_time": idx[i], "setup": SETUPS[sig], "side": "S" if d < 0 else "L", "entry": c[i],
                      "target": tg, "stop": st, "risk": abs(c[i] - st),
                      "aligned": bool(f["htfBear"][i] if d < 0 else f["htfBull"][i]),
                      "score": float(score[i]) if score is not None else np.nan}
            # T2 runner
            mags = f["t2magsS"] if d < 0 else f["t2magsL"]
            need = t1[sig][i] + p.min_tgt
            ds = [(c[i] - m[i]) if d < 0 else (m[i] - c[i]) for m in mags]
            ds = [x for x in ds if not np.isnan(x) and x >= need]
            if ds:
                t2_dir, t2_lvl, t2_stp, t2_bar = d, rt(c[i] + d * min(ds)), st, i
                t2_total += 1

    df = pd.DataFrame(trades)
    df.attrs["t2"] = (t2_hits, t2_total)
    return df


def _intrabar_order(bar_start, d, tgt, stp, m1h, m1l):
    """Both T1 and the stop were touched inside one 5m candle: use the 1-minute bars to see which came first."""
    end = bar_start + pd.Timedelta(minutes=5)
    hh, ll = m1h[bar_start:end - pd.Timedelta(seconds=1)], m1l[bar_start:end - pd.Timedelta(seconds=1)]
    for hv, lv in zip(hh.to_numpy(), ll.to_numpy()):
        t_hit = lv <= tgt if d < 0 else hv >= tgt
        s_hit = hv >= stp if d < 0 else lv <= stp
        if t_hit and s_hit:
            return False, True   # same minute: still unknown -> loss
        if t_hit:
            return True, False
        if s_hit:
            return False, True
    return False, True


def with_params(**kw):
    return replace(Params(), **kw)

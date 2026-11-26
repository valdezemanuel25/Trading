## TJ trigger TSLA (xyz:TSLA) at 13:48 ET, 2026-11-25

Last 380.25 vs trigger 379.19 (PMH 379.19, HOD before this bar 379.00); LOD 357.64. Broke: yes, holds: yes.
5m (last completed bar 13:40): close 378.80, VWAP 365.48, 8 EMA 375.82, 21 EMA 372.13 -> video 5 confirm: yes (logged, not required).
RVOL: premarket 1.03, intraday 1.04 (14 days).
- A: TJL-report: window 10:00-15:30 ok, PM RVOL > 1.5 ok
- B: TJL-bot: window 10:05-15:30 ok, RVOL >= 2.0 (14d, same time) NO

**Trade: A: TJL-report, grade Normal**
- A: Liquid entry ~380.8, stop 358.16 (5.95%), 1R 22.64, $4,205 at 2x (margin $2,102), qty 11.04, risk $250; partials 3.68 at 403.44 (+1.0R), 3.68 at 426.09 (+2.0R)

Orders for approval (paper):
1 entry + stop (suggest_order, then execute_order): `{'asset': 'xyz:TSLA', 'side': 'long', 'orderType': 'market', 'size': 4204.95, 'leverage': 2, 'stopLoss': 358.16, 'markPrice': 380.8, 'reasoning': 'TJL A: TJL-report Normal paper: break of 379.19'}`
2 partial 1: reduce-only limit sell at +1.0R: `{'symbol': 'xyz:TSLA', 'side': 'sell', 'type': 'limit', 'price': 403.44, 'quantity': 3.68, 'reduceOnly': True, 'timeInForce': 'gtc', 'reasoning': 'TJL partial 1 at +1.0R'}`
3 partial 2: reduce-only limit sell at +2.0R: `{'symbol': 'xyz:TSLA', 'side': 'sell', 'type': 'limit', 'price': 426.09, 'quantity': 3.68, 'reduceOnly': True, 'timeInForce': 'gtc', 'reasoning': 'TJL partial 2 at +2.0R'}`
Management A: after both partials, exit the last third on a 5m close below the 21 EMA; flat by 15:51.

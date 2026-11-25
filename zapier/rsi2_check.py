# RSI(2) pullback daily check - paste into a "Code by Zapier" (Run Python) step.
# Runs each weekday at ~15:50 ET on Zapier's servers. Downloads daily closes for the S&P 500 and Nasdaq 100
# indexes from Yahoo Finance (today's close = the live price at 15:50), then reports per market:
#   action = LONG SETUP  (close > 200-day SMA and RSI(2) < 10)   -> buy at the close
#            EXIT        (close > 5-day SMA)                      -> sell at the close if long
#            NONE
# Later Zap steps: Filter (only continue if any_signal is true) -> Notion "RSI2 Signals" row -> email / push.
# Same rules as research/rsi2.py and thinkorswim/RSI2PullbackAlert.ts. Index prices stand in for /MES and /MNQ.
import requests

RSI_ENTRY = 10          # 30 = about twice as many trades
MARKETS = {"MES": "%5EGSPC", "MNQ": "%5ENDX"}   # Liquid: xyz:SP500, xyz:XYZ100


def closes(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=2y&interval=1d"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    r.raise_for_status()
    q = r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"]
    return [c for c in q if c is not None]


def rsi2(c):
    up = dn = 0.0
    for i in range(1, len(c)):          # Wilder smoothing, length 2 (same as ToS RSI(2))
        d = c[i] - c[i - 1]
        up = 0.5 * up + 0.5 * max(d, 0)
        dn = 0.5 * dn + 0.5 * max(-d, 0)
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def check(c):
    last, sma5, sma200 = c[-1], sum(c[-5:]) / 5, sum(c[-200:]) / 200
    r = rsi2(c)
    if last > sma200 and r < RSI_ENTRY:
        action = "LONG SETUP"
    elif last > sma5:
        action = "EXIT"
    else:
        action = "NONE"
    return dict(action=action, price=round(last, 2), rsi2=round(r, 1), sma5=round(sma5, 2),
                sma200=round(sma200, 2), above_200=last > sma200)


output = {}
lines = []
for market, ticker in MARKETS.items():
    res = check(closes(ticker))
    for k, v in res.items():
        output[f"{market}_{k}"] = v
    if res["action"] != "NONE":
        lines.append(f"RSI2 | {res['action']} | {market} | price {res['price']} | RSI(2) {res['rsi2']}")
output["any_signal"] = bool(lines)
output["message"] = "\n".join(lines) or "RSI2 | no signal"

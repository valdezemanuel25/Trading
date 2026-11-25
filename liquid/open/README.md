Open paper positions, one JSON per market, mirrored from the dashboard store data/rsi2/open/<KEY>.
Fields: market, symbol, strategy ("RSI2" or "TR"), entry_date (candle date, YYYY-MM-DD), entry_px, notional.
Written after an approved order fills; deleted after the close fills. Empty = no open positions.

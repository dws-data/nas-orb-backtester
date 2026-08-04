# Data Sources

## Alpaca — QQQ ETF (Active)

- **Instrument:** QQQ (Invesco QQQ Trust, Nasdaq-100 ETF)
- **Provider:** Alpaca Market Data v2 — `https://data.alpaca.markets/v2/stocks/bars`
- **Feed:** `sip` (full consolidated tape; requires a paid Alpaca market-data plan — the free plan serves `iex` only)
- **Adjustment:** `split` — split-adjusted, not dividend-adjusted
- **Timeframe:** `1Min`
- **Range:** 2016-01-01 → present (Alpaca's SIP history starts 2016)
- **Cache:** `data/cache/QQQ_1m.parquet` (UTC bar-open index; extended-hours bars retained)
- **API key:** env `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`, or `data/alpaca_api_key.txt` (key id line 1, secret line 2)
- **Download script:** `data/fetcher.py` — run `python -m data.fetcher` to refresh (incremental; only fetches what the cache is missing)
- **Resampled parquets:** `python -m scripts.build_resampled_parquets` writes `QQQ_{15m,1h,4h,1d}.parquet` for the swing tracker
- **Fields:** open, high, low, close, volume
- **Bar filter:** non-positive OHLC, `high < low`, and duplicate timestamps dropped at load time in `data/fetcher.py`
- **Notes:** Bars are only emitted for minutes that traded, so overnight/pre-market coverage is sparse. Because `adjustment=split` restates the whole history, re-download with `--refresh` after any QQQ split rather than appending.

## Superseded for this branch: Databento — NQ E-mini Futures

- **Instrument:** NQ E-mini futures, continuous front-month contract
- **Symbol:** `NQ.v.0` (volume-based roll, raw prices — not back-adjusted)
- **Dataset:** `GLBX.MDP3`
- **Schema:** `ohlcv-1m`
- **Range:** 2016-03-10 → 2026-04-06
- **Cache:** `data/cache/NQ_continuous_1m.parquet` (3,520,920 bars)
- **API key:** `data/databento_api_key.txt`
- **Download script:** `data/download_continuous.py` — run `python -m data.download_continuous` to refresh
- **Fields:** open, high, low, close, volume
- **Roll method:** Volume crossover — continuous contract automatically selects front-month
- **Price notes:** Raw (not back-adjusted). Roll-day price gaps are intraday and don't affect the 09:30–10:00 ORB window.
- **Corrupt bar filter:** Bars with close < 1000 dropped at load time in `data/fetcher.py`

## Superseded: yfinance / FMP / MT5 (No longer used)

These were explored before Databento was set up. yfinance was used for early prototyping (~44 days of ^NDX 5m data). All superseded by the Databento NQ 1m continuous contract.

- yfinance: free, ^NDX index, 5m bars, 60-day lookback — insufficient history, wrong instrument
- FMP: API key in `.env`, Starter plan (no intraday) — never used for backtest
- MT5 broker scraping: planned but never needed — Databento solved the history problem

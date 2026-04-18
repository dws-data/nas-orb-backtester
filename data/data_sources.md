# Data Sources

## Current: Databento — NQ E-mini Futures (Active)

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

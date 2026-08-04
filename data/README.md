# data

Price data on this branch is sourced from **Alpaca** — QQQ, SIP feed, split-adjusted, 1m OHLCV bars, 2016–present. The original dataset was **Databento** NQ E-mini futures (continuous front contract, NQ.v.0).

The data files are not included in this repository. See `data_sources.md` for details on both datasets and how to obtain them.

```bash
export APCA_API_KEY_ID=...  APCA_API_SECRET_KEY=...
python -m data.fetcher --symbol QQQ --start 2016-01-01
```

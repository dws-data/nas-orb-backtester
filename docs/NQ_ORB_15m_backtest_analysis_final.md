# NAS100 ORB Retrace — 15m ORB Window Analysis

**ORB window:** 09:30–09:45 ET (15 bars)
**Post-ORB trade window:** 09:46–15:40 ET (no delay)
**Long variant:** `10pct_vah_orb_close` — entry VAH, stop ORB low, 10% threshold, bar close confirmation
**Short variant:** `30pct_poc_orb_close` — entry POC, stop ORB high, 30% threshold, bar close confirmation
**Target:** 1:1 R
**Data:** NQ.v.0 continuous contract, 1m bars, Databento, 2021–2026

---

## 1. Full Variant Sweep (2021+)

18 variants per direction tested: 3 thresholds × 3 entry levels × 2 stop types.

### Longs — sorted by expectancy

| Variant | Trades | WR | Exp | Total R | Max DD |
|---|---|---|---|---|---|
| **10pct_vah_orb** | **484** | **53.5%** | **+0.063R** | **+30.7R** | **-14.9R** |
| 10pct_poc_orb | 397 | 52.4% | +0.044R | +17.3R | -14.3R |
| 20pct_vah_orb | 414 | 52.4% | +0.036R | +14.8R | -20.4R |
| 20pct_poc_orb | 335 | 51.0% | +0.021R | +8.0R  | -16.9R |
| 30pct_vah_orb | 339 | 51.6% | +0.019R | +6.6R  | -23.3R |
| 30pct_poc_orb | 276 | 50.0% | +0.000R | +1.0R  | -16.4R |
| 10pct_vah_vp_extreme | 484 | 50.6% | +0.010R | +4.7R  | -26.6R |
| 20pct_vah_vp_extreme | 414 | 48.6% | -0.035R | -14.5R | -32.0R |
| 30pct_vah_vp_extreme | 339 | 48.4% | -0.040R | -13.7R | -38.6R |
| 20pct_poc_vp_extreme | 335 | 47.2% | -0.052R | -17.5R | -24.7R |
| 20pct_val_orb | 274 | 47.8% | -0.049R | -13.4R | -26.5R |
| 30pct_val_orb | 226 | 46.9% | -0.071R | -16.1R | -29.8R |
| 10pct_val_orb | 318 | 46.5% | -0.074R | -23.4R | -36.4R |
| 10pct_poc_vp_extreme | 397 | 45.6% | -0.083R | -32.8R | -42.8R |
| 30pct_poc_vp_extreme | 276 | 44.6% | -0.104R | -28.8R | -35.0R |
| 20pct_val_vp_extreme | 274 | 13.1% | -0.737R | -202R  | -201R  |
| 30pct_val_vp_extreme | 226 | 12.8% | -0.743R | -168R  | -167R  |
| 10pct_val_vp_extreme | 318 | 11.6% | -0.767R | -244R  | -243R  |

**Long findings:** VAH entry dominates. Only orb-stop VAH/POC variants are positive. VAL entry and vp_extreme stop are losing across the board. `val_vp_extreme` variants are catastrophic (~12% WR).

### Shorts — sorted by expectancy

| Variant | Trades | WR | Exp | Total R | Max DD |
|---|---|---|---|---|---|
| **30pct_poc_orb** | **288** | **55.2%** | **+0.094R** | **+27.1R** | **-11.7R** |
| 20pct_poc_orb | 334 | 55.1% | +0.090R | +29.9R | -12.2R |
| 20pct_val_orb | 394 | 54.6% | +0.065R | +25.5R | -10.0R |
| 10pct_poc_orb | 395 | 53.9% | +0.065R | +25.7R | -11.0R |
| 30pct_val_orb | 352 | 54.5% | +0.062R | +21.9R | -16.0R |
| 10pct_val_orb | 468 | 54.1% | +0.061R | +28.5R | -11.1R |
| 30pct_val_vp_extreme | 352 | 52.8% | +0.040R | +14.0R | -18.3R |
| 30pct_poc_vp_extreme | 288 | 51.7% | +0.039R | +11.2R | -10.2R |
| 10pct_poc_vp_extreme | 395 | 51.9% | +0.036R | +14.3R | -12.2R |
| 20pct_poc_vp_extreme | 334 | 51.2% | +0.024R | +8.2R  | -14.6R |
| 20pct_val_vp_extreme | 394 | 51.5% | +0.018R | +6.9R  | -13.8R |
| 10pct_val_vp_extreme | 468 | 50.9% | +0.010R | +4.7R  | -16.0R |
| 30pct_vah_orb | 213 | 48.4% | -0.029R | -6.2R  | -13.2R |
| 20pct_vah_orb | 258 | 47.3% | -0.053R | -13.6R | -22.6R |
| 10pct_vah_orb | 307 | 46.3% | -0.074R | -22.6R | -32.6R |
| 30pct_vah_vp_extreme | 213 | 16.4% | -0.671R | -143R  | -143R  |
| 20pct_vah_vp_extreme | 258 | 17.1% | -0.659R | -170R  | -170R  |
| 10pct_vah_vp_extreme | 307 | 16.3% | -0.674R | -207R  | -207R  |

**Short findings:** POC and VAL entry with orb stop all positive (+0.061–0.094R). VAH entry is consistently negative. vp_extreme stop (stop at VAH) for POC/VAL entries is also positive but weaker than orb stop. `vah_vp_extreme` shorts are catastrophic (~17% WR — stop and entry at same level).

**Canonical short: `30pct_poc_orb` — highest per-trade expectancy (+0.094R), ~55/yr. Note `10pct_poc_orb` has higher frequency (~76/yr) at lower expectancy (+0.065R).**

---

## 2. 2021+ Baseline

| Direction | Variant | Trades | Freq | WR | Exp | Total R | Max DD |
|---|---|---|---|---|---|---|---|
| Long  | 10pct_vah_orb_close | 484 | ~93/yr | 53.5% | +0.063R | +30.7R | -14.9R |
| Short | 30pct_poc_orb_close | 288 | ~55/yr | 55.2% | +0.094R | +27.1R | -11.7R |

---

## 3. Year-by-Year (2021+)

### Longs
| Year | Trades | WR | Exp | Total R |
|---|---|---|---|---|
| 2021 | 83  | 57.8% | +0.121R | +10.1R |
| 2022 | 97  | 54.6% | +0.099R | +9.6R  |
| 2023 | 100 | 48.0% | -0.040R | -4.0R  |
| 2024 | 85  | 50.6% | +0.035R | +3.0R  |
| 2025 | 93  | 54.8% | +0.077R | +7.2R  |
| 2026 | 26  | 61.5% | +0.188R | +4.9R  |

### Shorts
| Year | Trades | WR | Exp | Total R |
|---|---|---|---|---|
| 2021 | 45 | 55.6% | +0.083R | +3.7R  |
| 2022 | 59 | 62.7% | +0.255R | +15.1R |
| 2023 | 55 | 45.5% | -0.118R | -6.5R  |
| 2024 | 68 | 47.1% | -0.055R | -3.7R  |
| 2025 | 52 | 63.5% | +0.261R | +13.6R |
| 2026 |  9 | 77.8% | +0.556R | +5.0R  |

**Observations:**
- Longs: only 2023 negative. More consistent distribution than 30m longs which were heavily 2021-dependent.
- Shorts: 2021 and 2023 negative. 2025 exceptional (+13.6R). Edge is real but choppy.

---

## 4. Directional Filter — Multi-Timeframe Structure (2021+)

Structure direction at entry time classified as bullish or bearish using swing highs/lows on each timeframe. "Aligned" = trade direction matches structure (long + bullish, short + bearish).

### Longs (`10pct_vah_orb_close`)
| TF | Regime | Trades | WR | Exp | Total R |
|---|---|---|---|---|---|
| —   | All (unfiltered)           | 484 | 53.5% | +0.063R     | +30.7R |
| 15m | bearish (counter-trend)   | 102 | 52.9% | +0.075R     | +7.6R  |
| 15m | bullish (trend-follow)    | 382 | 53.7% | +0.060R     | +23.1R |
| 1h  | bearish (counter-trend)   | 148 | 56.8% | **+0.147R** | +21.7R |
| 1h  | bullish (trend-follow)    | 336 | 52.1% | +0.027R     | +9.0R  |
| 4h  | bearish (counter-trend)   | 195 | 54.9% | +0.096R     | +18.8R |
| 4h  | bullish (trend-follow)    | 289 | 52.6% | +0.041R     | +12.0R |
| 1d  | bearish (counter-trend)   | 206 | 52.4% | +0.040R     | +8.2R  |
| 1d  | bullish (trend-follow)    | 278 | 54.3% | +0.081R     | +22.5R |

### Shorts (`30pct_poc_orb_close`)
| TF | Regime | Trades | WR | Exp | Total R |
|---|---|---|---|---|---|
| —   | All (unfiltered)           | 288 | 55.2% | +0.094R     | +27.1R |
| 15m | bearish (trend-follow)    | 211 | 54.5% | +0.100R     | +21.1R |
| 15m | bullish (counter-trend)   |  77 | 57.1% | +0.078R     | +6.0R  |
| 1h  | bearish (trend-follow)    | 203 | 58.1% | **+0.147R** | +29.9R |
| 1h  | bullish (counter-trend)   |  85 | 48.2% | -0.033R     | -2.8R  |
| 4h  | bearish (trend-follow)    | 155 | 59.4% | **+0.166R** | +25.7R |
| 4h  | bullish (counter-trend)   | 133 | 50.4% | +0.011R     | +1.4R  |
| 1d  | bearish (trend-follow)    | 148 | 54.7% | +0.078R     | +11.6R |
| 1d  | bullish (counter-trend)   | 140 | 55.7% | +0.111R     | +15.5R |

---

### 15m structure

No meaningful discriminating power for either direction. Long 15m buckets are almost identical (+0.075R vs +0.060R) — the 15m structure at entry is essentially noise relative to the ORB setup, which itself forms on the 15m timeframe. Short 15m buckets are both solidly positive (+0.100R vs +0.078R). No useful filter.

### 1h structure

The sharpest single filter across all timeframes for both directions.

**Longs:** 1h bearish (counter-trend) produces +0.147R — 2.3× the unfiltered expectancy — on 148 trades (~28/yr). WR jumps to 56.8%. The 1h bullish bucket is still positive (+0.027R, 336 trades) but weak, making 1h a quality-over-quantity filter rather than a hard exclude.

**Shorts:** The clearest two-way split of any timeframe. 1h bearish (trend-follow) hits +0.147R on 203 trades (~39/yr). The 1h bullish bucket is the **only negative bucket across all timeframes and directions** (-0.033R, 85 trades). Excluding 1h bullish would drop ~30% of short trades while eliminating the only losing cohort.

### 4h structure

Strong for shorts; moderate for longs. The previously confirmed finding holds.

**Longs:** Both buckets positive — 4h bearish +0.096R (195 trades), 4h bullish +0.041R (289 trades). A quality improvement when filtering to 4h bearish but the edge doesn't disappear in the bullish regime. Less decisive than the 1h filter.

**Shorts:** 4h bearish (trend-follow) has the highest single-bucket expectancy of any filter (+0.166R, 155 trades, 59.4% WR). The 4h bullish bucket is near breakeven (+0.011R). Clear regime dependence — but 4h bearish gives fewer trades than 1h bearish (155 vs 203) at only marginally higher expectancy.

### 1d structure

Inverts the pattern seen at 1h and 4h — the "wrong" direction on the daily is often better.

**Longs:** 1d bullish (trend-follow) outperforms 1d bearish (+0.081R vs +0.040R). The ORB counter-trend retracement long works better when the daily trend is also up — possibly because pullbacks are shallower and cleaner in a bullish daily regime.

**Shorts:** 1d bullish (counter-trend) outperforms 1d bearish (+0.111R vs +0.078R). Shorting intraday ORB retracements against the daily trend actually produces better edge than shorting with it. This is the opposite of what 1h and 4h show, and likely reflects mean-reversion dynamics on extended daily moves — when the daily is stretched bullish, intraday fade setups are more reliable.

The 1d filter does not cleanly separate good from bad regimes for either direction; it reorders them. Not a useful exclude filter.

---

### Summary

| TF | Best long bucket | Best short bucket | Any negative bucket? |
|---|---|---|---|
| 15m | +0.075R (bearish) | +0.100R (bearish) | No |
| 1h  | **+0.147R (bearish)** | **+0.147R (bearish)** | Yes — short 1h bullish (-0.033R) |
| 4h  | +0.096R (bearish) | **+0.166R (bearish)** | No (short bullish ~breakeven) |
| 1d  | +0.081R (bullish) | +0.111R (bullish) | No |

**1h is the most actionable filter** — highest quality signal in both directions, and the only timeframe that produces a clearly losing bucket (short 1h bullish) worth excluding. 4h bearish gives the highest single expectancy for shorts (+0.166R) but with fewer trades. Combining 1h + 4h bearish for shorts would concentrate edge further but reduce frequency significantly — worth testing.


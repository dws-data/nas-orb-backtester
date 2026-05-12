import pandas as pd
import numpy as np
from pathlib import Path
from strategies.orb_retrace import build_day_context, run_variant, CONFIRMATION_TYPES
from backtest.swing_tracker import build_structure_lookup, get_live_structure

_CACHE_DIR     = Path("data/cache")
_STRUCTURE_TFS = ["15m", "1h", "4h", "1d"]
_ALIGNED       = {"long": "bullish", "short": "bearish"}


def _build_adr_lookup(df_full: pd.DataFrame, cfg, window: int = 30) -> dict:
    """
    Build a date-keyed ADR lookup with both absolute (pts) and normalised (% of price) values.

    RTH range  : orb_start → session_end in instrument TZ (e.g. 09:30–16:00 ET for NQ).
    Full range : midnight-to-midnight in instrument TZ.

    _pct variants divide each day's range by the previous RTH session close before averaging,
    making the metric comparable across different price levels / years.

    All values use a rolling `window`-day mean shifted 1 day — no lookahead.
    df_full must already be in instrument timezone.
    """
    # RTH: orb_start to session_end
    rth_bars  = df_full.between_time(cfg.orb_start, cfg.session_end)
    rth_daily = rth_bars.groupby(rth_bars.index.date).agg(
        high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    rth_daily["range"] = rth_daily["high"] - rth_daily["low"]

    # Full: midnight-to-midnight in instrument TZ, reindexed to RTH trading days
    # so prev_close aligns correctly (non-RTH dates would produce NaN range_pct).
    full_daily_raw = df_full.groupby(df_full.index.date).agg(
        high=("high", "max"), low=("low", "min")
    )
    full_daily = full_daily_raw.reindex(rth_daily.index)
    full_daily["range"] = full_daily["high"] - full_daily["low"]

    # Normalise ranges by previous RTH close (shift(1) on the close series)
    prev_close           = rth_daily["close"].shift(1)
    rth_daily["range_pct"]  = rth_daily["range"]  / prev_close * 100
    full_daily["range_pct"] = full_daily["range"]  / prev_close * 100

    rth_adr      = rth_daily["range"].rolling(window, min_periods=window).mean().shift(1)
    full_adr     = full_daily["range"].rolling(window, min_periods=window).mean().shift(1)
    rth_adr_pct  = rth_daily["range_pct"].rolling(window, min_periods=window).mean().shift(1)
    full_adr_pct = full_daily["range_pct"].rolling(window, min_periods=window).mean().shift(1)

    lookup = {}
    for date in rth_adr.index:
        rth_val      = rth_adr.loc[date]
        full_val     = full_adr.loc[date]
        rth_pct_val  = rth_adr_pct.loc[date]
        full_pct_val = full_adr_pct.loc[date]
        if pd.notna(rth_val) and pd.notna(full_val):
            lookup[date] = {
                "adr_30_rth":       round(float(rth_val),      2),
                "adr_30_full":      round(float(full_val),     2),
                "adr_30_rth_pct":   round(float(rth_pct_val),  3) if pd.notna(rth_pct_val)  else None,
                "adr_30_full_pct":  round(float(full_pct_val), 3) if pd.notna(full_pct_val) else None,
            }

    return lookup


def _build_gap_lookup(df_full: pd.DataFrame, cfg) -> dict:
    """
    Build a date-keyed overnight gap lookup.
    gap_pct = abs(session_open - prior_session_close) / prior_session_close * 100.
    session_open  = open of first bar at cfg.orb_start on trade date.
    prior_close   = close of last bar at cfg.session_end on previous session.
    """
    session_bars = df_full.between_time(cfg.orb_start, cfg.session_end)
    daily_close  = session_bars.groupby(session_bars.index.date)["close"].last()
    daily_open   = session_bars.groupby(session_bars.index.date)["open"].first()

    daily = pd.DataFrame({"open": daily_open, "prior_close": daily_close.shift(1)})
    daily["gap_pct"] = ((daily["open"] - daily["prior_close"]) / daily["prior_close"] * 100).abs()

    return {
        date: round(float(row["gap_pct"]), 3)
        for date, row in daily.iterrows()
        if pd.notna(row["gap_pct"])
    }


def _build_nr7_lookup(df_full: pd.DataFrame, cfg) -> dict:
    """
    Build a date-keyed NR7 lookup. A day is NR7 if its RTH range is the
    narrowest of the last 7 trading days (Crabel volatility compression signal).
    nr7_prior is shifted 1 day — the flag on trade date T means T-1 was NR7.
    """
    rth_bars  = df_full.between_time(cfg.orb_start, cfg.session_end)
    rth_daily = rth_bars.groupby(rth_bars.index.date).agg(
        high=("high", "max"), low=("low", "min")
    )
    rth_daily["range"]    = rth_daily["high"] - rth_daily["low"]
    rth_daily["nr7"]      = rth_daily["range"] == rth_daily["range"].rolling(7, min_periods=7).min()
    rth_daily["nr7_prior"] = rth_daily["nr7"].shift(1)

    return {
        date: bool(row["nr7_prior"])
        for date, row in rth_daily.iterrows()
        if pd.notna(row["nr7_prior"])
    }


def run(
    df: pd.DataFrame,
    cfg,
    orb_window_mins: int = 15,
    cache_dir: Path = _CACHE_DIR,
    adr_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run all ORB retracement variants over a full OHLCV DataFrame.

    Pre-filters to ET session hours and groups by ET date so overnight
    futures bars don't bleed into the wrong trading day.

    Returns
    -------
    days_df   : one row per trading day with ORB, VP, and breakout/retrace flags
    trades_df : one row per (day × variant) where a trade fired
    """
    if df.index.tz is None:
        df = df.tz_localize("UTC")

    # Convert to instrument timezone — keep full unfiltered copy for partial-bar structure lookups
    print("Filtering to session hours...", flush=True)
    df_full = df.tz_convert(cfg.tz)
    df_et   = df_full.between_time(cfg.session_start, cfg.session_end)

    # Materialise groups upfront — lazy groupby iteration over 1.1M rows stalls
    # because pandas re-slices on each step. list() forces all group computation once.
    day_keys = df_et.index.normalize()
    print("Materialising day groups...", flush=True)
    groups   = list(df_et.groupby(day_keys))
    total    = len(groups)
    print(f"Running engine on {total} days...", flush=True)

    print("Loading market structure...", flush=True)
    structure_lookup = build_structure_lookup(cache_dir, cfg)
    print(f"  Structure loaded for {len(structure_lookup['1h'])} 1h bars", flush=True)

    print("Building ADR lookup...", flush=True)
    # Use full unfiltered data if supplied — avoids NaN warmup on early backtest dates.
    adr_source = adr_df.tz_convert(cfg.tz) if adr_df is not None else df_full
    adr_lookup = _build_adr_lookup(adr_source, cfg)
    print(f"  ADR lookup built for {len(adr_lookup)} days", flush=True)

    print("Building NR7 lookup...", flush=True)
    nr7_lookup = _build_nr7_lookup(df_full, cfg)
    print(f"  NR7 lookup built for {len(nr7_lookup)} days", flush=True)

    print("Building gap lookup...", flush=True)
    gap_lookup = _build_gap_lookup(df_full, cfg)
    print(f"  Gap lookup built for {len(gap_lookup)} days", flush=True)

    day_records   = []
    trade_records = []

    for i, (_, day_df) in enumerate(groups, 1):
        if i % 100 == 0:
            print(f"  {i}/{total} days...", flush=True)
        for confirm_by in CONFIRMATION_TYPES:
            ctx = build_day_context(day_df, cfg, orb_window_mins, confirm_by=confirm_by)
            if ctx is None:
                continue

            # Strip private keys for the day record
            day_record = {k: v for k, v in ctx.items() if not k.startswith("_")}
            day_records.append(day_record)

            direction = ctx.get("direction")
            if direction == "long":
                variants    = cfg.long_variants
                target_mult = cfg.target_mult_long
            elif direction == "short":
                variants    = cfg.short_variants
                target_mult = cfg.target_mult_short
            else:
                variants    = []
                target_mult = None

            for threshold, entry_level, sl_type in variants:
                # Skip invalid combos where entry and stop are the same VP level
                if direction == "long"  and entry_level == "val" and sl_type == "vp_extreme":
                    continue
                if direction == "short" and entry_level == "vah" and sl_type == "vp_extreme":
                    continue
                trade = run_variant(ctx, threshold, entry_level, sl_type, cfg, target_mult=target_mult)
                if trade is not None:
                    trade["variant_id"] = f"{threshold}pct_{entry_level}_{sl_type}_{confirm_by}"
                    trade["instrument"]      = cfg.name
                    trade["orb_window_mins"] = orb_window_mins
                    trade["tz"]              = cfg.tz
                    trade["orb_start"]       = cfg.orb_start
                    trade["session_start"]   = cfg.session_start
                    trade["session_end"]     = cfg.session_end
                    # Tag alignment with live market structure at entry time.
                    # get_live_structure checks whether the current partial bar
                    # has already broken the swing levels mid-candle — matching
                    # what a live trader would see on their chart.
                    expected = _ALIGNED.get(trade["direction"])
                    entry_time = trade["entry_time"]
                    for tf in _STRUCTURE_TFS:
                        struct = get_live_structure(
                            structure_lookup[tf], df_full, entry_time, tf
                        )
                        trade[f"dir_{tf}"]     = struct                  # absolute: 'bullish' or 'bearish'
                        trade[f"aligned_{tf}"] = (struct == expected)    # relative: True = with trend
                    # Structure at ORB close — for 15m/1h where at-entry vs at-ORB can differ.
                    # 4h/1d rarely flip intraday so not computed here.
                    orb_end_time = (
                        pd.Timestamp(entry_time.strftime("%Y-%m-%d") + " " + cfg.orb_start, tz=cfg.tz)
                        + pd.Timedelta(minutes=orb_window_mins)
                    )
                    for tf in ["15m", "1h"]:
                        struct_at_orb = get_live_structure(
                            structure_lookup[tf], df_full, orb_end_time, tf
                        )
                        trade[f"dir_{tf}_at_orb"] = struct_at_orb
                    adr = adr_lookup.get(trade["date"], {})
                    trade["adr_30_rth"]      = adr.get("adr_30_rth")
                    trade["adr_30_full"]     = adr.get("adr_30_full")
                    trade["adr_30_rth_pct"]  = adr.get("adr_30_rth_pct")
                    trade["adr_30_full_pct"] = adr.get("adr_30_full_pct")
                    orb_size = trade["orb_size"]
                    trade["orb_adr_pct_rth"]  = round(orb_size / adr["adr_30_rth"]  * 100, 1) if adr.get("adr_30_rth")  else None
                    trade["orb_adr_pct_full"] = round(orb_size / adr["adr_30_full"] * 100, 1) if adr.get("adr_30_full") else None
                    trade["nr7_prior"] = nr7_lookup.get(trade["date"], None)
                    trade["gap_pct"]   = gap_lookup.get(trade["date"], None)
                    trade_records.append(trade)

    days_df   = pd.DataFrame(day_records)   if day_records   else pd.DataFrame()
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame()

    return days_df, trades_df

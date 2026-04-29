import sys
import pandas as pd
from pathlib import Path
from strategies.orb_retrace import build_day_context, run_variant, LONG_VARIANTS, SHORT_VARIANTS, CONFIRMATION_TYPES
from backtest.swing_tracker import build_structure_lookup, get_live_structure

# ET session window to pre-filter — keeps only bars relevant to the strategy.
# ORB starts 09:30, force-close is 15:40. Small buffer either side.
_SESSION_START = "09:00"
_SESSION_END   = "16:00"
_SESSION_TZ    = "America/New_York"

_CACHE_DIR = Path("data/cache")
_STRUCTURE_TFS = ["15m", "1h", "4h", "1d"]

# Alignment: trade direction → expected structure direction
_ALIGNED = {"long": "bullish", "short": "bearish"}


def run(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
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

    # Convert to ET — keep full unfiltered copy for partial-bar structure lookups
    print("Filtering to session hours...", flush=True)
    df_et_full = df.tz_convert(_SESSION_TZ)
    df_et = df_et_full.between_time(_SESSION_START, _SESSION_END)

    # Materialise groups upfront — lazy groupby iteration over 1.1M rows stalls
    # because pandas re-slices on each step. list() forces all group computation once.
    day_keys = df_et.index.normalize()
    print("Materialising day groups...", flush=True)
    groups   = list(df_et.groupby(day_keys))
    total    = len(groups)
    print(f"Running engine on {total} days...", flush=True)

    print("Loading market structure...", flush=True)
    structure_lookup = build_structure_lookup(_CACHE_DIR)
    print(f"  Structure loaded for {len(structure_lookup['1h'])} 1h bars", flush=True)

    day_records   = []
    trade_records = []

    for i, (_, day_df) in enumerate(groups, 1):
        if i % 100 == 0:
            print(f"  {i}/{total} days...", flush=True)
        for confirm_by in CONFIRMATION_TYPES:
            ctx = build_day_context(day_df, confirm_by=confirm_by)
            if ctx is None:
                continue

            # Strip private keys for the day record
            day_record = {k: v for k, v in ctx.items() if not k.startswith("_")}
            day_records.append(day_record)

            # Apply direction-appropriate variant list
            direction = ctx.get("direction")
            if direction == "long":
                variants = LONG_VARIANTS
            elif direction == "short":
                variants = SHORT_VARIANTS
            else:
                variants = []

            for threshold, entry_level, sl_type in variants:
                # Skip invalid combos where entry and stop are the same VP level
                if direction == "long"  and entry_level == "val" and sl_type == "vp_extreme":
                    continue
                if direction == "short" and entry_level == "vah" and sl_type == "vp_extreme":
                    continue
                trade = run_variant(ctx, threshold, entry_level, sl_type)
                if trade is not None:
                    trade["variant_id"] = f"{threshold}pct_{entry_level}_{sl_type}_{confirm_by}"
                    # Tag alignment with live market structure at entry time.
                    # get_live_structure checks whether the current partial bar
                    # has already broken the swing levels mid-candle — matching
                    # what a live trader would see on their chart.
                    expected = _ALIGNED.get(trade["direction"])
                    entry_time = trade["entry_time"]
                    for tf in _STRUCTURE_TFS:
                        struct = get_live_structure(
                            structure_lookup[tf], df_et_full, entry_time, tf
                        )
                        trade[f"dir_{tf}"]     = struct                  # absolute: 'bullish' or 'bearish'
                        trade[f"aligned_{tf}"] = (struct == expected)    # relative: True = with trend
                    trade_records.append(trade)

    days_df   = pd.DataFrame(day_records)   if day_records   else pd.DataFrame()
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame()

    return days_df, trades_df

"""
GT Recent High/Low swing tracker — directional structure filter.

Tracks a matched pair (Recent High, Recent Low) using the same logic as the
GT Recent High Low TradingView indicator:

  - New high breaks out → direction = bullish
    Recent High updates to bar's high.
    Recent Low resets to the highest interior low (lowest low of all interior bars),
    UNLESS an inside bar (H < H_prev AND L > L_prev) was seen in the interior run,
    in which case the most recent inside bar's low is used instead.

  - New low breaks out → direction = bearish
    Recent Low updates to bar's low.
    Recent High resets using the same logic (highest high of interior bars, or most
    recent inside bar's high if any inside bar was seen).

  - Interior bar (neither new high nor new low) → direction and levels unchanged.

  - Both broken on same bar → tiebreak by close: bullish if close >= open, else bearish.

Direction at index i = market structure AFTER bar i has closed.

Usage
-----
    from backtest.swing_tracker import build_structure_lookup, get_live_structure
    from pathlib import Path

    lookup = build_structure_lookup(Path("data/cache"))
    # lookup is a dict: tf -> pd.DataFrame indexed by bar CLOSE time
    # columns: direction, recent_high, recent_low

    # Get live structure at entry_time (accounts for partial current bar):
    struct = get_live_structure(lookup["4h"], bars_1m_et, entry_time, "4h")
    # returns 'bullish' or 'bearish'
"""

import numpy as np
import pandas as pd
from pathlib import Path

_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
_TZ = "America/New_York"

_PARQUET_NAMES = {
    "15m": "NQ_continuous_15m.parquet",
    "1h":  "NQ_continuous_1h.parquet",
    "4h":  "NQ_continuous_4h.parquet",
    "1d":  "NQ_continuous_1d.parquet",
}

_BAR_DURATIONS = {
    "15m": pd.Timedelta("15min"),
    "1h":  pd.Timedelta("1h"),
    "4h":  pd.Timedelta("4h"),
    "1d":  pd.Timedelta("1D"),
}


def build_structure_lookup(cache_dir: Path) -> dict[str, pd.DataFrame]:
    """
    Build point-in-time structure lookup from pre-built resampled parquets.

    Loads NQ_continuous_{tf}.parquet for each timeframe from cache_dir,
    runs the swing tracker, then re-indexes each result by bar CLOSE time.

    Parameters
    ----------
    cache_dir : Path to folder containing NQ_continuous_*.parquet files
                (built by scripts/build_resampled_parquets.py)

    Returns
    -------
    dict[str, pd.DataFrame] — one DataFrame per timeframe, indexed by bar close
    time (ET), columns: direction ('bullish'|'bearish'), recent_high, recent_low.

    Use get_live_structure() rather than .asof() directly — it accounts for
    mid-bar structural flips using the 1m data.
    """
    cache_dir = Path(cache_dir)
    result: dict[str, pd.DataFrame] = {}

    for tf in _TIMEFRAMES:
        path = cache_dir / _PARQUET_NAMES[tf]
        bars = pd.read_parquet(path)
        if bars.index.tz is None:
            bars = bars.tz_localize("UTC")
        bars = bars.tz_convert(_TZ)

        if bars.empty:
            result[tf] = pd.DataFrame(columns=["direction", "recent_high", "recent_low"])
            continue

        tracker = _run_tracker(bars)
        # Re-index by close time so lookups return the last fully-closed bar's state
        close_index = tracker.index + _BAR_DURATIONS[tf]
        result[tf] = pd.DataFrame({
            "direction":   tracker["direction"].values,
            "recent_high": tracker["recent_high"].values,
            "recent_low":  tracker["recent_low"].values,
        }, index=close_index)

    return result


def get_live_structure(
    levels: pd.DataFrame,
    bars_1m: pd.DataFrame,
    entry_time: pd.Timestamp,
    tf: str,
) -> str:
    """
    Return the live market structure at entry_time, accounting for mid-bar
    structural flips that closed-bar-only lookups would miss.

    Logic:
    1. Get the last completed bar's swing levels (recent_high, recent_low)
       via asof(entry_time).
    2. Compute the current partial bar's high/low from 1m bars between
       the bar's open and entry_time.
    3. If the partial bar's high exceeds recent_high → bullish now.
       If the partial bar's low breaks recent_low → bearish now.
       Otherwise → unchanged from the last completed bar.

    Parameters
    ----------
    levels    : DataFrame from build_structure_lookup()[tf]
    bars_1m   : Full 1m OHLCV DataFrame in ET (unfiltered by session)
    entry_time: Timezone-aware entry timestamp in ET
    tf        : Timeframe string — '15m', '1h', '4h', or '1d'

    Returns
    -------
    'bullish' or 'bearish'
    """
    dur = _BAR_DURATIONS[tf]

    # Last completed bar's state
    last_direction   = levels["direction"].asof(entry_time)
    last_recent_high = levels["recent_high"].asof(entry_time)
    last_recent_low  = levels["recent_low"].asof(entry_time)

    if pd.isna(last_direction):
        return "bearish"  # no history yet

    # Current bar's open time and the 1m bars within it
    bar_start    = entry_time.floor(dur)
    partial_bars = bars_1m.loc[
        (bars_1m.index >= bar_start) & (bars_1m.index <= entry_time)
    ]

    if partial_bars.empty:
        return str(last_direction)

    partial_high = partial_bars["high"].max()
    partial_low  = partial_bars["low"].min()

    if partial_high > last_recent_high:
        return "bullish"
    elif partial_low < last_recent_low:
        return "bearish"
    else:
        return str(last_direction)


def _run_tracker(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Run the GT Recent High/Low swing tracker on OHLCV bars.

    Returns pd.DataFrame indexed by bar open time (same index as `bars`),
    columns: direction ('bullish'|'bearish'), recent_high, recent_low —
    all reflecting the state AFTER that bar has closed.

    Rule (confirmed vs TradingView 2026-04-14):
    - On breakout, the opposite level resets to the highest high (or lowest low)
      among all interior bars since the last pivot — UNLESS any of those bars is
      an inside bar (H < H_prev AND L > L_prev), in which case the most recent
      inside bar's value takes priority.
    """
    highs  = bars["high"].values.astype(float)
    lows   = bars["low"].values.astype(float)
    opens  = bars["open"].values.astype(float)
    closes = bars["close"].values.astype(float)
    n = len(highs)

    if n == 0:
        return pd.DataFrame(
            columns=["direction", "recent_high", "recent_low"],
            index=bars.index,
        )

    directions  = np.empty(n, dtype="U8")
    rec_highs   = np.empty(n, dtype=float)
    rec_lows    = np.empty(n, dtype=float)

    direction       = "bullish" if closes[0] >= opens[0] else "bearish"
    recent_high     = highs[0]
    recent_low      = lows[0]
    interior_seen   = False
    interim_high    = highs[0]
    interim_low     = lows[0]
    inside_bar_high = None
    inside_bar_low  = None
    prev_high       = highs[0]
    prev_low        = lows[0]
    directions[0]   = direction
    rec_highs[0]    = recent_high
    rec_lows[0]     = recent_low

    for i in range(1, n):
        new_high = highs[i] > recent_high
        new_low  = lows[i]  < recent_low

        if new_high and not new_low:
            if interior_seen:
                recent_low = inside_bar_low if inside_bar_low is not None else interim_low
            recent_high     = highs[i]
            direction       = "bullish"
            interior_seen   = False
            interim_high    = highs[i]
            interim_low     = lows[i]
            inside_bar_high = None
            inside_bar_low  = None

        elif new_low and not new_high:
            if interior_seen:
                recent_high = inside_bar_high if inside_bar_high is not None else interim_high
            recent_low      = lows[i]
            direction       = "bearish"
            interior_seen   = False
            interim_high    = highs[i]
            interim_low     = lows[i]
            inside_bar_high = None
            inside_bar_low  = None

        elif new_high and new_low:
            if closes[i] >= opens[i]:
                if interior_seen:
                    recent_low = inside_bar_low if inside_bar_low is not None else interim_low
                recent_high = highs[i]
                direction   = "bullish"
            else:
                if interior_seen:
                    recent_high = inside_bar_high if inside_bar_high is not None else interim_high
                recent_low  = lows[i]
                direction   = "bearish"
            interior_seen   = False
            interim_high    = highs[i]
            interim_low     = lows[i]
            inside_bar_high = None
            inside_bar_low  = None

        else:
            # Interior bar — within current swing structure
            interior_seen = True
            interim_high  = max(interim_high, highs[i])
            interim_low   = min(interim_low,  lows[i])
            if highs[i] < prev_high and lows[i] > prev_low:
                inside_bar_high = highs[i]
                inside_bar_low  = lows[i]

        prev_high     = highs[i]
        prev_low      = lows[i]
        directions[i] = direction
        rec_highs[i]  = recent_high
        rec_lows[i]   = recent_low

    return pd.DataFrame({
        "direction":   directions,
        "recent_high": rec_highs,
        "recent_low":  rec_lows,
    }, index=bars.index)

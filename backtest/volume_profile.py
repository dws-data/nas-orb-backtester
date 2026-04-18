import numpy as np
import pandas as pd


def calculate(bars: pd.DataFrame, num_rows: int = 24) -> dict:
    """
    Calculate Volume Profile from a set of OHLCV bars.

    Volume is distributed evenly across price buckets within each bar's
    high/low range. This is an approximation — tick data would be more accurate.

    Bucket size is dynamic: (high - low) / num_rows, matching TradingView's
    Fixed Range Volume Profile with Row Size = 24.

    Parameters
    ----------
    bars : pd.DataFrame
        OHLCV bars (must have high, low, volume columns).
    num_rows : int
        Number of price rows to divide the range into. Default 24 (matches TV).

    Returns
    -------
    dict with keys:
        poc : float  — Point of Control (highest volume price level)
        vah : float  — Value Area High (upper bound of 70% volume zone)
        val : float  — Value Area Low  (lower bound of 70% volume zone)
        profile : pd.Series — full volume profile indexed by price level
    """
    if bars.empty:
        raise ValueError("No bars provided to volume profile calculator")

    lows    = bars["low"].values
    highs   = bars["high"].values
    volumes = bars["volume"].values

    low_floor   = lows.min()
    high_ceil   = highs.max()
    bucket_size = (high_ceil - low_floor) / num_rows
    buckets     = np.array([low_floor + i * bucket_size for i in range(num_rows + 1)])
    n_buckets   = num_rows
    volume_arr  = np.zeros(n_buckets)

    for i in range(len(lows)):
        if highs[i] <= lows[i] or volumes[i] <= 0:
            continue
        lo_idx = int(np.floor((lows[i] - low_floor) / bucket_size))
        hi_idx = int(np.floor((highs[i] - low_floor) / bucket_size))
        lo_idx = max(0, lo_idx)
        hi_idx = min(n_buckets - 1, hi_idx)
        if lo_idx > hi_idx:
            continue
        volume_arr[lo_idx : hi_idx + 1] += volumes[i] / (hi_idx - lo_idx + 1)

    poc_idx       = int(np.argmax(volume_arr))
    lower_idx, upper_idx = _value_area(volume_arr, poc_idx)

    # Report midpoint of each bucket (matches TradingView's display)
    poc = float(buckets[poc_idx]   + bucket_size / 2)
    vah = float(buckets[upper_idx] + bucket_size / 2)
    val = float(buckets[lower_idx] + bucket_size / 2)

    return {"poc": poc, "vah": vah, "val": val, "profile": pd.Series(volume_arr, index=buckets[:n_buckets])}


def _value_area(volume_arr: np.ndarray, poc_idx: int, value_area_pct: float = 0.70) -> tuple[int, int]:
    """
    Expand outward from POC until value_area_pct of total volume is captured.
    Works entirely with numpy integer indices — no pandas label lookups in the loop.

    Returns (lower_idx, upper_idx) as integer positions into volume_arr.
    """
    total_volume = volume_arr.sum()
    if total_volume == 0:
        return poc_idx, poc_idx

    target      = total_volume * value_area_pct
    upper       = poc_idx
    lower       = poc_idx
    accumulated = volume_arr[poc_idx]
    n           = len(volume_arr)

    while accumulated < target:
        can_go_up   = upper < n - 1
        can_go_down = lower > 0

        if not can_go_up and not can_go_down:
            break

        next_up   = volume_arr[upper + 1] if can_go_up   else 0.0
        next_down = volume_arr[lower - 1] if can_go_down else 0.0

        if can_go_up and (not can_go_down or next_up >= next_down):
            upper       += 1
            accumulated += next_up
        else:
            lower       -= 1
            accumulated += next_down

    return lower, upper

import numpy as np
import pandas as pd
from backtest.volume_profile import calculate as calc_vp

SPREAD_PCT         = 0.010        # fraction of ORB size added to entry/exit trigger
STOP_BUFFER_PCT    = 0.030        # fraction of ORB size beyond stop level to ensure fill
# At a typical 2026 ORB of ~180pts: spread=1.8pts, buffer=5.4pts
# At a 2017 ORB of ~16pts:          spread=0.16pts, buffer=0.48pts
LONG_THRESHOLDS    = [10, 20, 30]
SHORT_THRESHOLDS   = [10, 20, 25, 30]
THRESHOLDS         = [10, 20, 25, 30]
CONFIRMATION_TYPES = ["close"]

# All times in US/Eastern (America/New_York) — handles EST/EDT automatically.
ORB_WINDOW_MINS = 15         # ← change to 15 or 30 to switch ORB window

ORB_START    = "09:30"
ORB_END      = "09:45" if ORB_WINDOW_MINS == 15 else "10:00"
TRADE_START  = "09:46" if ORB_WINDOW_MINS == 15 else "10:01"
ORB_MIN_BARS = 10      if ORB_WINDOW_MINS == 15 else 20
ENTRY_CUTOFF = "14:59"
FORCE_CLOSE  = "15:40"
TZ           = "America/New_York"

# Target mode:
#   "fib" — ORB extreme + FIB_TARGET × ORB size  (default)
#   "1r"  — entry + stop_dist (true 1:1R)
TARGET_MODE = "fib"

# Fib target: ORB extreme + FIB_TARGET × ORB size.
# 1.272 — chosen 2026-04-19 based on full regime analysis (see experimental/fib_tp/compare_05_1272_2026-04-19.md).
# Switch to 0.5 if ORB% drops below ~0.35% for a sustained period (low-vol regime).
FIB_TARGET = 1.272

# Valid (threshold, entry_level, sl_type) combinations — separated by direction.
#
# entry_level : "vah" | "poc" | "val"
# sl_type     : "orb"        → ORB extreme (orb_low for long, orb_high for short)
#               "vp_extreme" → opposite VP boundary (val for long, vah for short)
#               "poc"        → Point of Control
#
# INVALID combinations (entry == stop level — near-zero win rate, do not generate):
#   Long:  entry_level="val" + sl_type="vp_extreme"  → stop IS val (same level as entry)
#   Short: entry_level="vah" + sl_type="vp_extreme"  → stop IS vah (same level as entry)

# Canonical variants — 15m ORB window, 1.272x fib target.
# Long:  10pct_poc_orb — 397 trades, 36.8% WR, +0.167R, +66.46R, -20.22R DD (updated 2026-04-20, POC beats VAH in 3/4 1h+4h regime combos)
# Short: 25pct_poc_orb — 308 trades, 39.9% WR, +0.217R, +66.76R, -19.66R DD (updated 2026-04-20, 0 neg years vs 1 for 30pct)
LONG_VARIANTS  = [(10, "poc", "orb")]
SHORT_VARIANTS = [(25, "poc", "orb")]


def _first_true(mask: np.ndarray) -> int:
    """Return index of first True in mask, or len(mask) if none."""
    if len(mask) == 0:
        return 0
    idx = mask.argmax()
    return int(idx) if mask[idx] else len(mask)


def build_day_context(day_df: pd.DataFrame, confirm_by: str = "close") -> dict | None:
    """
    Compute ORB, VP, direction, max breakout %, and retrace flags for one day.
    All bar-scanning is vectorised with numpy — no iterrows().

    Returns a context dict used by run_variant. Private keys (prefixed '_')
    carry raw arrays for variant evaluation and should be stripped before
    writing to the day-level record.

    Returns None if the day has insufficient data.
    """
    if day_df.index.tz is None:
        day_df = day_df.tz_localize("UTC")
    df = day_df.tz_convert(TZ)  # tz_convert always returns a new DataFrame — no copy needed

    # --- ORB: 09:30–10:00 ET ---
    orb_bars = df.between_time(ORB_START, ORB_END)
    if len(orb_bars) < ORB_MIN_BARS:
        return None

    orb_high = float(orb_bars["high"].max())
    orb_low  = float(orb_bars["low"].min())
    orb_size = orb_high - orb_low
    if orb_size <= 0:
        return None

    try:
        vp = calc_vp(orb_bars)
    except Exception:
        return None

    vah = float(min(vp["vah"], orb_high))
    poc = float(max(orb_low, min(vp["poc"], orb_high)))
    val = float(max(vp["val"], orb_low))

    # Post-ORB bars: 10:05–15:40 ET — extract numpy arrays once
    post_orb = df.between_time(TRADE_START, FORCE_CLOSE)
    if post_orb.empty:
        return None

    date       = df.index[0].date()
    po_close   = post_orb["close"].values
    po_high    = post_orb["high"].values
    po_low     = post_orb["low"].values
    po_volume  = post_orb["volume"].values
    po_times   = post_orb.index

    # Precompute for confirmation types that need extra data
    avg_orb_volume = float(orb_bars["volume"].mean()) if "volume" in orb_bars.columns else 0.0

    _5m_bar_dur_ns = int(pd.Timedelta("5min").value)
    post_orb_5m    = post_orb.resample("5min", closed="left", label="left").agg({"close": "last"}).dropna()
    po_5m_close    = post_orb_5m["close"].values
    po_5m_times_ns = post_orb_5m.index.asi8

    # Legacy: po_confirm kept for any future confirm_by that maps 1:1 to a column
    po_confirm = po_close

    # --- Direction: first bar to close beyond ORB ---
    long_idx  = _first_true(po_close > orb_high)
    short_idx = _first_true(po_close < orb_low)
    n = len(po_close)

    if long_idx == n and short_idx == n:
        direction = None
    elif long_idx <= short_idx:
        direction = "long"
    else:
        direction = "short"

    # --- Base context ---
    ctx = {
        "date":         date,
        "confirm_by":   confirm_by,
        "direction":    direction,
        "orb_high":     round(orb_high, 2),
        "orb_low":      round(orb_low,  2),
        "orb_size":     round(orb_size, 2),
        "vah":          round(vah, 2),
        "poc":          round(poc, 2),
        "val":          round(val, 2),
        "breakout_pct": 0.0,
    }
    for t in THRESHOLDS:
        ctx[f"threshold_{t}_confirmed"]   = False
        ctx[f"threshold_{t}_retrace_vah"] = False
        ctx[f"threshold_{t}_retrace_poc"] = False
        ctx[f"threshold_{t}_retrace_val"] = False

    # Pre-compute cutoff/force_close as int64 ns — avoids repeated Timestamp
    # construction and expensive DatetimeIndex comparisons inside run_variant.
    _cutoff_ns      = pd.Timestamp(f"{date} {ENTRY_CUTOFF}", tz=TZ).value
    _force_close_ns = pd.Timestamp(f"{date} {FORCE_CLOSE}", tz=TZ).value

    # Store raw arrays for run_variant (stripped before writing day record)
    ctx["_post_orb"]        = post_orb
    ctx["_po_low"]          = po_low
    ctx["_po_high"]         = po_high
    ctx["_po_close"]        = po_close
    ctx["_po_volume"]       = po_volume
    ctx["_po_times"]        = po_times
    ctx["_po_times_ns"]     = po_times.asi8          # int64 ns for fast comparison
    ctx["_cutoff_ns"]       = _cutoff_ns
    ctx["_force_close_ns"]  = _force_close_ns
    ctx["_avg_orb_volume"]  = avg_orb_volume
    ctx["_po_5m_close"]     = po_5m_close
    ctx["_po_5m_times_ns"]  = po_5m_times_ns
    ctx["_5m_bar_dur_ns"]   = _5m_bar_dur_ns
    ctx["_orb_close_ns"]    = pd.Timestamp(f"{date} {ORB_END}", tz=TZ).value
    ctx["_threshold_data"]  = {}

    if direction is None:
        return ctx

    # Max breakout %
    if direction == "long":
        max_ext = float((po_close - orb_high).max())
    else:
        max_ext = float((orb_low - po_close).max())
    ctx["breakout_pct"] = round(max(max_ext, 0) / orb_size * 100, 1)

    # --- Per-threshold: confirmation + retrace flags ---
    po_times_ns    = po_times.asi8
    n_5m           = len(po_5m_close)

    for t in THRESHOLDS:
        thresh_pts = orb_size * t / 100

        if confirm_by == "close":
            if direction == "long":
                conf_mask = po_close >= orb_high + thresh_pts
            else:
                conf_mask = po_close <= orb_low - thresh_pts
            confirmed_idx = _first_true(conf_mask)
            confirmed     = confirmed_idx < n

        elif confirm_by == "high":
            if direction == "long":
                conf_mask = po_high >= orb_high + thresh_pts
            else:
                conf_mask = po_low <= orb_low - thresh_pts
            confirmed_idx = _first_true(conf_mask)
            confirmed     = confirmed_idx < n

        elif confirm_by == "2close":
            if direction == "long":
                single = po_close >= orb_high + thresh_pts
            else:
                single = po_close <= orb_low - thresh_pts
            # Both bar i and bar i-1 must be beyond threshold
            double        = single & np.concatenate([[False], single[:-1]])
            confirmed_idx = _first_true(double)
            confirmed     = confirmed_idx < n

        elif confirm_by == "vol_close":
            if direction == "long":
                price_ok = po_close >= orb_high + thresh_pts
            else:
                price_ok = po_close <= orb_low - thresh_pts
            vol_ok        = po_volume >= avg_orb_volume
            conf_mask     = price_ok & vol_ok
            confirmed_idx = _first_true(conf_mask)
            confirmed     = confirmed_idx < n

        elif confirm_by == "5m_close":
            if direction == "long":
                conf_5m = po_5m_close >= orb_high + thresh_pts
            else:
                conf_5m = po_5m_close <= orb_low - thresh_pts
            idx_5m = _first_true(conf_5m)
            if idx_5m < n_5m:
                # Map to 1m: last bar whose open time < end of confirming 5m bar
                bar_end_ns    = po_5m_times_ns[idx_5m] + _5m_bar_dur_ns
                confirmed_idx = int(np.searchsorted(po_times_ns, bar_end_ns, side="left")) - 1
                confirmed     = 0 <= confirmed_idx < n
            else:
                confirmed     = False
                confirmed_idx = n

        else:
            confirmed     = False
            confirmed_idx = n

        if confirmed:
            ctx[f"threshold_{t}_confirmed"] = True
            # Retrace check: any bar AFTER confirmation bar
            after_low  = po_low[confirmed_idx + 1:]
            after_high = po_high[confirmed_idx + 1:]

            if direction == "long":
                ctx[f"threshold_{t}_retrace_vah"] = bool((after_low <= vah).any())
                ctx[f"threshold_{t}_retrace_poc"] = bool((after_low <= poc).any())
                ctx[f"threshold_{t}_retrace_val"] = bool((after_low <= val).any())
            else:
                ctx[f"threshold_{t}_retrace_val"] = bool((after_high >= val).any())
                ctx[f"threshold_{t}_retrace_poc"] = bool((after_high >= poc).any())
                ctx[f"threshold_{t}_retrace_vah"] = bool((after_high >= vah).any())

        # Persistence: consecutive 1m closes that stayed beyond the ORB extreme
        # after the confirmation bar, before first close back inside the range.
        if confirmed:
            if direction == "long":
                persist_closes = po_close[confirmed_idx:]
                persist_mask   = persist_closes >= orb_high
            else:
                persist_closes = po_close[confirmed_idx:]
                persist_mask   = persist_closes <= orb_low
            # argmax on negation finds first False; if all True, argmax returns 0
            first_back = int((~persist_mask).argmax())
            persistence = first_back if not persist_mask.all() else len(persist_mask)
        else:
            persistence = 0

        ctx["_threshold_data"][t] = {
            "confirmed":     confirmed,
            "confirmed_idx": confirmed_idx if confirmed else None,
            "persistence":   persistence,
        }

    return ctx


def run_variant(ctx: dict, threshold_pct: int, entry_level: str, sl_type: str) -> dict | None:
    """
    Evaluate a single variant on a pre-built day context.
    All bar-scanning is vectorised — no iterrows().
    """
    if ctx is None or ctx["direction"] is None:
        return None

    tdata = ctx["_threshold_data"].get(threshold_pct)
    if not tdata or not tdata["confirmed"]:
        return None

    if not ctx.get(f"threshold_{threshold_pct}_retrace_{entry_level}"):
        return None

    direction         = ctx["direction"]
    vah, poc, val     = ctx["vah"], ctx["poc"], ctx["val"]
    orb_high, orb_low = ctx["orb_high"], ctx["orb_low"]
    orb_size          = ctx["orb_size"]

    spread      = orb_size * SPREAD_PCT
    stop_buffer = orb_size * STOP_BUFFER_PCT

    level_price  = {"vah": vah, "poc": poc, "val": val}[entry_level]
    entry_price  = round(level_price + spread if direction == "long" else level_price - spread, 2)

    if direction == "long":
        stop_level = {"orb": orb_low, "vp_extreme": val, "poc": poc}[sl_type]
        stop_clean = stop_level - stop_buffer
    else:
        stop_level = {"orb": orb_high, "vp_extreme": vah, "poc": poc}[sl_type]
        stop_clean = stop_level + stop_buffer

    stop_dist = (entry_price - stop_clean) if direction == "long" else (stop_clean - entry_price)
    if stop_dist <= 0:
        return None

    orb_extreme  = orb_high if direction == "long" else orb_low
    if TARGET_MODE == "1r":
        target_clean = (entry_price + stop_dist) if direction == "long" else (entry_price - stop_dist)
    else:
        fib_dist     = FIB_TARGET * orb_size
        target_clean = (orb_extreme + fib_dist) if direction == "long" else (orb_extreme - fib_dist)

    # Pull pre-extracted arrays from context
    po_low      = ctx["_po_low"]
    po_high     = ctx["_po_high"]
    po_close    = ctx["_po_close"]
    po_times    = ctx["_po_times"]
    po_times_ns = ctx["_po_times_ns"]   # int64 nanoseconds — fast numpy comparison
    cutoff_ns      = ctx["_cutoff_ns"]
    force_close_ns = ctx["_force_close_ns"]
    n           = len(po_low)

    confirmed_idx = tdata["confirmed_idx"]   # integer position in post_orb arrays

    # --- Entry window: bars after confirmation, before cutoff ---
    after_start      = confirmed_idx + 1
    after_times_ns   = po_times_ns[after_start:]
    after_low        = po_low[after_start:]
    after_high       = po_high[after_start:]

    # searchsorted on sorted int64 array — avoids DatetimeIndex comparison overhead
    cutoff_pos   = int(np.searchsorted(after_times_ns, cutoff_ns, side="left"))
    window_low   = after_low[:cutoff_pos]
    window_high  = after_high[:cutoff_pos]

    if direction == "long":
        entry_mask = window_low <= level_price
    else:
        entry_mask = window_high >= level_price

    entry_pos = _first_true(entry_mask)
    if entry_pos >= cutoff_pos:
        return None

    entry_time = po_times[after_start + entry_pos]

    # Max extension from ORB extreme during the breakout-and-retrace phase only
    # (confirmation bar through entry bar inclusive). This is the "initial breakout
    # size" before price pulled back to the entry level.
    pre_slice = slice(confirmed_idx, after_start + entry_pos + 1)
    if direction == "long":
        pre_entry_breakout_pct = round(
            max(0.0, float(po_high[pre_slice].max()) - orb_high) / orb_size * 100, 1
        )
    else:
        pre_entry_breakout_pct = round(
            max(0.0, orb_low - float(po_low[pre_slice].min())) / orb_size * 100, 1
        )

    # --- Exit scan: from entry bar onward ---
    exit_start     = after_start + entry_pos
    exit_low       = po_low[exit_start:]
    exit_high      = po_high[exit_start:]
    exit_close     = po_close[exit_start:]
    exit_times     = po_times[exit_start:]
    exit_times_ns  = po_times_ns[exit_start:]

    if direction == "long":
        stop_mask   = exit_low   <= stop_clean   + spread
        target_mask = exit_high  >= target_clean          # price tags fib level → limit order at target_clean - spread fills
    else:
        stop_mask   = exit_high  >= stop_clean   - spread
        target_mask = exit_low   <= target_clean          # price tags fib level → limit order at target_clean + spread fills

    # Entry bar (index 0): target cannot fire on the same bar entry was taken.
    # For retracement entries the favourable level may have been breached
    # before the entry fill within that bar — we cannot determine intra-bar
    # order from OHLCV. Conservative: only stop is valid on bar 0.
    if len(target_mask) > 0:
        target_mask = target_mask.copy()
        target_mask[0] = False

    # searchsorted for EOD — avoids DatetimeIndex comparison overhead
    eod_pos    = int(np.searchsorted(exit_times_ns, force_close_ns, side="left"))
    stop_pos   = _first_true(stop_mask)
    target_pos = _first_true(target_mask)
    m          = len(exit_low)

    # Priority: stop ≥ target > eod (stop wins ties with target; both win ties with eod)
    first_trade = min(stop_pos, target_pos)
    if first_trade < eod_pos:
        # A trade exit fires before EOD
        if stop_pos <= target_pos:
            exit_reason = "stop"
            exit_price  = stop_clean
            exit_time   = exit_times[stop_pos]
            exit_pos    = stop_pos
        else:
            exit_reason = "target"
            exit_price  = target_clean - spread if direction == "long" else target_clean + spread
            exit_time   = exit_times[target_pos]
            exit_pos    = target_pos
    elif eod_pos < m:
        exit_reason = "eod"
        exit_price  = float(exit_close[eod_pos])
        exit_time   = exit_times[eod_pos]
        exit_pos    = eod_pos
    else:
        # Fallback — should not normally occur
        exit_reason = "eod"
        exit_price  = float(exit_close[-1])
        exit_time   = exit_times[-1]
        exit_pos    = m - 1

    pnl   = round((exit_price - entry_price) if direction == "long" else (entry_price - exit_price), 2)
    pnl_r = round(pnl / stop_dist, 3) if stop_dist > 0 else 0.0

    # MFE / MAE — measured over bars from entry to exit (inclusive)
    trade_high = exit_high[:exit_pos + 1]
    trade_low  = exit_low[:exit_pos + 1]
    if direction == "long":
        mfe_r = round((trade_high.max() - entry_price) / stop_dist, 3)
        mae_r = round((trade_low.min()  - entry_price) / stop_dist, 3)
        mfe_bar = int(trade_high.argmax())
        mae_bar = int(trade_low.argmin())
    else:
        mfe_r = round((entry_price - trade_low.min())  / stop_dist, 3)
        mae_r = round((entry_price - trade_high.max()) / stop_dist, 3)
        mfe_bar = int(trade_low.argmin())
        mae_bar = int(trade_high.argmax())

    # Did the trade go positive (MFE > 0) before it went maximally negative?
    mfe_before_mae = bool(mfe_bar < mae_bar) if mfe_r > 0 else False

    # Durations
    trade_duration_mins = int((exit_time.value - entry_time.value) // 60_000_000_000)
    entry_delay_mins    = int((entry_time.value - ctx["_orb_close_ns"]) // 60_000_000_000)

    return {
        "date":         ctx["date"],
        "confirm_by":   ctx["confirm_by"],
        "direction":    direction,
        "threshold":    threshold_pct,
        "entry_level":  entry_level,
        "sl_type":      sl_type,
        "orb_high":     ctx["orb_high"],
        "orb_low":      ctx["orb_low"],
        "orb_size":     ctx["orb_size"],
        "vah":          ctx["vah"],
        "poc":          ctx["poc"],
        "val":          ctx["val"],
        "entry_price":  entry_price,
        "stop_clean":   round(stop_clean,   2),
        "target_clean": round(target_clean, 2),
        "stop_dist":    round(stop_dist,    2),
        "entry_time":   entry_time,
        "exit_price":   exit_price,
        "exit_time":    exit_time,
        "exit_reason":  exit_reason,
        "pnl":                   pnl,
        "pnl_r":                 pnl_r,
        "mfe_r":                 mfe_r,
        "mae_r":                 mae_r,
        "mfe_before_mae":        mfe_before_mae,
        "trade_duration_mins":   trade_duration_mins,
        "entry_delay_mins":         entry_delay_mins,
        "breakout_persistence":     tdata["persistence"],
        "pre_entry_breakout_pct":   pre_entry_breakout_pct,
    }

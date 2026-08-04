"""
ORB retracement trade viewer.

    .venv/bin/streamlit run app.py

Reads what `run.py` wrote — results/{SYMBOL}/trades_{N}m.csv — plus the 1m
parquet cache, and renders each session's entries and exits on a TradingView
chart. It never calls Alpaca and never re-runs the engine, so it starts
instantly and works offline; re-run `run.py` when you want fresh numbers.

The engine evaluates the whole variant grid, so a single day can carry dozens
of trades. Filter down to the variants you care about in the sidebar first —
the session chart draws everything that survives the filter.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backtest import metrics  # noqa: E402
from data import fetcher  # noqa: E402
from instruments import config as instrument_config  # noqa: E402
from viz.tvchart import session_html  # noqa: E402

st.set_page_config(page_title="ORB retrace — trade viewer", layout="wide")

_TIME_COLS = ["entry_time", "exit_time"]


@st.cache_data(show_spinner=False)
def load_trades(path: str, tz: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in _TIME_COLS:
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601").dt.tz_convert(tz)
    return df


@st.cache_data(show_spinner=False)
def load_bars(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def results_files(out_root: Path, symbol: str) -> list[Path]:
    return sorted((out_root / symbol).glob("trades_*m.csv"))


# ---------------------------------------------------------------- sidebar ---
sb = st.sidebar
sb.header("Data")

# Defaults come from the environment so the viewer can be pointed at another
# dataset — a second symbol, an archived run — without retyping paths on every
# rerun: ORB_SYMBOL / ORB_RESULTS_DIR / ORB_CACHE_DIR.
symbol = sb.text_input("Symbol", os.environ.get("ORB_SYMBOL", "QQQ")).upper()
out_root = Path(sb.text_input("Results dir", os.environ.get("ORB_RESULTS_DIR", "results")))
cache_dir = Path(sb.text_input("Cache dir", os.environ.get("ORB_CACHE_DIR", "data/cache")))

try:
    cfg = instrument_config.get(symbol)
except KeyError as exc:
    st.error(str(exc))
    st.stop()

available = results_files(out_root, symbol)
if not available:
    st.title("No results yet")
    st.markdown(
        f"Nothing in `{out_root / symbol}/`. Run the backtest first:\n\n"
        "```bash\n.venv/bin/python run.py --symbol " + symbol + "\n```"
    )
    st.stop()

trades_path = sb.selectbox(
    "Trades file", available, format_func=lambda p: p.name,
    index=len(available) - 1,
)
orb_window = int(trades_path.stem.split("_")[-1].rstrip("m"))

bars_path = fetcher.cache_path(cfg.parquet_prefix, cache_dir)
if not bars_path.exists():
    st.error(f"No 1m cache at `{bars_path}`. Run `python -m data.fetcher --symbol {symbol}`.")
    st.stop()

trades = load_trades(str(trades_path), cfg.tz)
bars = load_bars(str(bars_path))

if trades.empty:
    st.warning("The trades file is empty.")
    st.stop()

# ---------------------------------------------------------------- filters ---
sb.header("Filter variants")


def multi(label: str, col: str, fmt=str):
    opts = sorted(trades[col].dropna().unique())
    picked = sb.multiselect(label, opts, default=[], format_func=fmt)
    return picked or opts


thresholds  = multi("Threshold %", "threshold", lambda v: f"{v}%")
entry_levs  = multi("Entry level", "entry_level", str.upper)
sl_types    = multi("Stop type", "sl_type")
directions  = multi("Direction", "direction")
exit_reasons = multi("Exit reason", "exit_reason")

sb.header("Filter days")
lo, hi = trades["date"].min(), trades["date"].max()
date_range = sb.date_input("Date range", (lo, hi), min_value=lo, max_value=hi)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = lo, hi

align_tf = sb.selectbox(
    "Structure alignment", ["any", "15m", "1h", "4h", "1d"],
    help="Keep only trades taken with the higher-timeframe trend on that timeframe.",
)

mask = (
    trades["threshold"].isin(thresholds)
    & trades["entry_level"].isin(entry_levs)
    & trades["sl_type"].isin(sl_types)
    & trades["direction"].isin(directions)
    & trades["exit_reason"].isin(exit_reasons)
    & (trades["date"] >= start_date)
    & (trades["date"] <= end_date)
)
if align_tf != "any":
    mask &= trades[f"aligned_{align_tf}"].astype(bool)

sel = trades[mask].sort_values("entry_time")

# ------------------------------------------------------------------ header ---
st.title(f"{symbol} — ORB {orb_window}m retracement")
st.caption(
    f"{len(sel):,} of {len(trades):,} trades   ·   "
    f"{sel['variant_id'].nunique() if not sel.empty else 0} variant(s)   ·   "
    f"{start_date} → {end_date}   ·   session {cfg.session_start}–{cfg.session_end} {cfg.tz}"
)

if sel.empty:
    st.warning("No trades match these filters.")
    st.stop()

s = metrics.summary(sel, print_results=False)
r1 = st.columns(4)
r1[0].metric("Trades", f"{s['trades']:,}")
r1[1].metric("Win rate", s["win_rate"])
r1[2].metric("Expectancy", f"{s['expectancy_r']:+.3f} R")
r1[3].metric("Total R", f"{s['total_r']:+.2f}")
r2 = st.columns(4)
r2[0].metric("Max DD", f"{s['max_dd_r']:.2f} R")
r2[1].metric("Target / Stop / EOD", f"{s['exit_target']} / {s['exit_stop']} / {s['exit_eod']}")
r2[2].metric("Avg win", f"{s['avg_win_r']:+.3f} R")
r2[3].metric("Avg loss", f"{s['avg_loss_r']:+.3f} R")

# Views are selected rather than tabbed. st.dataframe renders onto a canvas
# sized from its container, and inside an inactive st.tabs pane that container
# measures zero width — the grid then draws only its index column and never
# recovers on tab activation (a resize is the only thing that fixes it).
# Rendering one view per rerun sidesteps that, and avoids building the full
# trades grid every time an unrelated filter changes.
view = st.radio(
    "View", ["Session chart", "Trades", "Variants", "Equity"],
    horizontal=True, label_visibility="collapsed",
)

# ----------------------------------------------------------- session chart ---
if view == "Session chart":
    per_day = sel.groupby("date").agg(n=("pnl_r", "size"), r=("pnl_r", "sum"))
    days = list(per_day.index)
    labels = {d: f"{d}   ({int(row.n)} trade(s), {row.r:+.2f}R)"
              for d, row in per_day.iterrows()}

    left, right = st.columns([4, 1])
    pick = left.selectbox(
        "Session", days, index=len(days) - 1, format_func=lambda d: labels[d]
    )
    zoom = right.checkbox("Zoom to trade", value=True, help="Off shows the whole session.")

    try:
        html = session_html(bars, sel, pick, cfg, orb_window, height=520,
                            zoom_to_trades=zoom)
        st.components.v1.html(html, height=620, scrolling=False)
    except ValueError as exc:
        st.error(str(exc))

    st.caption(
        "drag the chart to scroll · drag the price axis to scale price · "
        "drag the time axis to scale time · scroll to zoom · "
        "double-click an axis to auto-scale · hover between an entry and its exit "
        "for that trade's full detail"
    )

    day_trades = sel[sel["date"] == pick]
    st.dataframe(
        day_trades[[
            "variant_id", "direction", "entry_time", "entry_price", "entry_level",
            "stop_clean", "target_clean", "exit_time", "exit_price", "exit_reason",
            "pnl_r", "mfe_r", "mae_r", "trade_duration_mins",
        ]],
        width="stretch", hide_index=True,
    )

# ------------------------------------------------------------------ trades ---
elif view == "Trades":
    st.dataframe(sel, width="stretch", hide_index=True)
    st.download_button(
        "Download filtered trades.csv", sel.to_csv(index=False),
        f"{symbol}_trades_{orb_window}m_filtered.csv", "text/csv",
    )

# ---------------------------------------------------------------- variants ---
elif view == "Variants":
    grouped = sel.groupby("variant_id")
    table = pd.DataFrame({
        "trades":       grouped.size(),
        "direction":    grouped["direction"].first(),
        "win_rate_%":   grouped["pnl_r"].apply(lambda x: (x > 0).mean() * 100).round(1),
        "expectancy_r": grouped["pnl_r"].mean().round(3),
        "total_r":      grouped["pnl_r"].sum().round(2),
        "avg_mfe_r":    grouped["mfe_r"].mean().round(2),
        "avg_mae_r":    grouped["mae_r"].mean().round(2),
    }).sort_values("total_r", ascending=False)
    st.dataframe(table, width="stretch")

# ------------------------------------------------------------------ equity ---
elif view == "Equity":
    st.caption(
        "Cumulative R over the filtered set, in entry-time order. With several "
        "variants selected this stacks concurrent positions — filter to one "
        "variant for a curve you could actually have traded."
    )
    curve = sel.set_index("entry_time")["pnl_r"].cumsum().rename("cumulative R")
    st.line_chart(curve)

    by_year = sel.assign(year=pd.to_datetime(sel["date"]).dt.year).groupby("year")
    st.dataframe(
        pd.DataFrame({
            "trades":     by_year.size(),
            "win_rate_%": by_year["pnl_r"].apply(lambda x: (x > 0).mean() * 100).round(1),
            "total_r":    by_year["pnl_r"].sum().round(2),
        }),
        width="stretch",
    )

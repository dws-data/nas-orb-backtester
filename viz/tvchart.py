"""
Session charts built on TradingView's Lightweight Charts.

Same approach as the ORB Sniper viewer: the library is vendored under `assets/`
(Apache-2.0) and inlined into the page, so charts render with no network access
and the interactions are the ones muscle memory expects:

  * drag the chart body   -> scroll through time
  * drag the price axis   -> stretch / compress the price scale
  * drag the time axis    -> stretch / compress the time scale
  * scroll wheel          -> zoom
  * double-click an axis  -> back to auto scale

What this module draws that the ORB Sniper chart does not: the opening range's
volume-profile levels (VAH / POC / VAL), which are where this strategy's
retracement entries actually fill.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

ASSET = Path(__file__).resolve().parents[1] / "assets" / "lightweight-charts.standalone.production.js"

UP    = "#26a69a"
DOWN  = "#ef5350"
ORB_C = "#4a87f3"   # ORB high / low
VAH_C = "#b388ff"   # value area high
POC_C = "#f5c542"   # point of control
VAL_C = "#b388ff"   # value area low
SL_C  = "#ef5350"
TP_C  = "#26a69a"

_LEVEL_COLORS = {"vah": VAH_C, "poc": POC_C, "val": VAL_C}


@lru_cache(maxsize=1)
def _library() -> str:
    if not ASSET.exists():
        raise FileNotFoundError(
            f"{ASSET} is missing. Re-download it with:\n"
            "  curl -sfL -o assets/lightweight-charts.standalone.production.js \\\n"
            "    https://unpkg.com/lightweight-charts@4.2.3/dist/"
            "lightweight-charts.standalone.production.js"
        )
    return ASSET.read_text()


def _epoch(ts: pd.DatetimeIndex | pd.Timestamp):
    """Seconds since epoch, shifted by the UTC offset.

    Lightweight Charts always renders times in UTC. Adding the offset makes the
    axis read in exchange-local time, which is what the session actually is.

    The index is converted through datetime64[s] rather than divided down from
    astype("int64"): that integer is in the index's own resolution, which is
    microseconds for anything pandas 3 round-trips through parquet, so a fixed
    //10**9 silently lands every bar in 1970.
    """
    if isinstance(ts, pd.Timestamp):
        return int(ts.timestamp() + ts.utcoffset().total_seconds())
    offs = np.array([t.utcoffset().total_seconds() for t in ts], dtype="int64")
    secs = ts.tz_convert("UTC").tz_localize(None).astype("datetime64[s]").astype("int64")
    return (secs + offs).tolist()


def session_payload(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    day,
    cfg,
    orb_window_mins: int = 15,
    zoom_to_trades: bool = True,
) -> dict:
    """
    Everything one session's chart needs, as plain JSON-ready data.

    Parameters
    ----------
    bars           : full 1m OHLCV frame, tz-aware (any tz — converted to cfg.tz here)
    trades         : trade rows for this instrument; entry_time/exit_time tz-aware,
                     `date` as datetime.date
    day            : the session date to render
    cfg            : InstrumentConfig
    zoom_to_trades : open on the trade window rather than the whole session
    """
    day = pd.Timestamp(day)
    if day.tzinfo is None:
        day = day.tz_localize(cfg.tz)
    day = day.tz_convert(cfg.tz).normalize()

    bars = bars.tz_convert(cfg.tz)
    sd = bars[bars.index.normalize() == day].between_time(cfg.session_start, cfg.session_end)
    if sd.empty:
        raise ValueError(f"no bars for {day.date()} (is it a trading day?)")

    times = _epoch(sd.index)
    o, h, l, c, v = sd["open"], sd["high"], sd["low"], sd["close"], sd["volume"]

    candles = [
        {"time": ti, "open": float(oo), "high": float(hh),
         "low": float(ll), "close": float(cc)}
        for ti, oo, hh, ll, cc in zip(times, o, h, l, c)
    ]
    volume = [
        {"time": ti, "value": float(vv), "color": (UP if cc >= oo else DOWN) + "55"}
        for ti, vv, oo, cc in zip(times, v, o, c)
    ]

    day_trades = trades[trades["date"] == day.date()]

    # ORB window shading, drawn as a band between ORB high and low over the
    # opening-range bars only — makes the range that defines the day obvious.
    orb_h, orb_m = (int(x) for x in cfg.orb_start.split(":"))
    orb_end = (day
               + pd.Timedelta(hours=orb_h, minutes=orb_m)
               + pd.Timedelta(minutes=orb_window_mins))
    orb_bars = sd[sd.index < orb_end]
    orb_times = _epoch(orb_bars.index) if not orb_bars.empty else []

    levels, rails, markers, rows = [], [], [], []

    if not day_trades.empty:
        first = day_trades.iloc[0]
        orb_high, orb_low = float(first["orb_high"]), float(first["orb_low"])
        vah, poc, val = float(first["vah"]), float(first["poc"]), float(first["val"])
        levels = [
            {"name": "ORB high", "price": orb_high, "color": ORB_C, "dashed": False},
            {"name": "ORB low",  "price": orb_low,  "color": ORB_C, "dashed": False},
            {"name": "VAH",      "price": vah,      "color": VAH_C, "dashed": True},
            {"name": "POC",      "price": poc,      "color": POC_C, "dashed": True},
            {"name": "VAL",      "price": val,      "color": VAL_C, "dashed": True},
        ]
        orb_band = [
            {"color": ORB_C + "88", "dashed": False,
             "data": [{"time": ti, "value": price} for ti in orb_times]}
            for price in (orb_high, orb_low)
        ] if orb_times else []
        rails.extend(orb_band)

    for _, tr in day_trades.iterrows():
        is_long = tr["direction"] == "long"
        t0, t1 = _epoch(tr["entry_time"]), _epoch(tr["exit_time"])
        won = tr["pnl_r"] > 0
        label = str(tr["variant_id"])

        markers.append({
            "time": t0, "position": "belowBar" if is_long else "aboveBar",
            "color": UP if is_long else DOWN,
            "shape": "arrowUp" if is_long else "arrowDown",
            "text": f"{'LONG' if is_long else 'SHORT'} @ {tr['entry_price']:.2f}"
                    f" ({tr['entry_level'].upper()})",
        })
        markers.append({
            "time": t1, "position": "aboveBar" if is_long else "belowBar",
            "color": TP_C if won else SL_C, "shape": "circle",
            "text": f"{tr['exit_reason']} {tr['exit_price']:.2f} ({tr['pnl_r']:+.2f}R)",
        })

        def seg(price):
            return [{"time": t0, "value": float(price)}, {"time": t1, "value": float(price)}]

        rails.append({"color": SL_C, "dashed": True,  "data": seg(tr["stop_clean"])})
        rails.append({"color": TP_C, "dashed": True,  "data": seg(tr["target_clean"])})
        rails.append({"color": UP if is_long else DOWN, "dashed": False,
                      "data": seg(tr["entry_price"])})

        rows.append({
            "t0": t0, "t1": t1,
            "text": (f"{label} — {tr['direction'].upper()} entry {tr['entry_price']:.2f} "
                     f"→ exit {tr['exit_price']:.2f} ({tr['exit_reason']}) · "
                     f"SL {tr['stop_clean']:.2f} TP {tr['target_clean']:.2f} · "
                     f"MFE {tr['mfe_r']:+.2f}R MAE {tr['mae_r']:+.2f}R · "
                     f"{tr['trade_duration_mins']:.0f} min · {tr['pnl_r']:+.3f}R"),
        })

    total_r = float(day_trades["pnl_r"].sum()) if not day_trades.empty else 0.0
    title = (f"{cfg.name} — {day:%Y-%m-%d}   {len(day_trades)} trade(s), "
             f"{total_r:+.2f}R   [{orb_window_mins}m ORB from {cfg.orb_start}]")

    # Default viewport: the trade window with 20 minutes of air on either side.
    # Fitting the whole 6.5-hour session squeezes a typical 10-40 minute trade
    # into a slice too narrow to read the markers on. The ORB and VP levels are
    # price lines spanning the full width, so they stay visible when zoomed.
    focus = None
    if zoom_to_trades and not day_trades.empty:
        pad = 20 * 60
        t_first = min(_epoch(t) for t in day_trades["entry_time"])
        t_last = max(_epoch(t) for t in day_trades["exit_time"])
        focus = {
            "from": max(times[0], t_first - pad),
            "to": min(times[-1], t_last + pad),
        }

    return {
        "candles": candles, "volume": volume, "levels": levels,
        "rails": rails, "markers": markers, "trades": rows, "title": title,
        "focus": focus,
    }


_TEMPLATE = """
<div id="wrap" style="font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#d1d4dc">
  <div id="title" style="padding:2px 4px 6px;font-weight:500"></div>
  <div id="chart" style="position:relative;height:__HEIGHT__px"></div>
  <div id="legend" style="padding:6px 4px;min-height:46px;color:#9aa0aa;font-size:12px"></div>
</div>
<script>__LIB__</script>
<script>
(function(){
  const D = __DATA__;
  document.getElementById('title').textContent = D.title;
  const el = document.getElementById('chart');
  const chart = LightweightCharts.createChart(el, {
    layout: { background:{type:'solid',color:'transparent'}, textColor:'#9aa0aa' },
    grid: { vertLines:{color:'rgba(120,120,130,0.12)'}, horzLines:{color:'rgba(120,120,130,0.12)'} },
    rightPriceScale: { borderColor:'rgba(120,120,130,0.35)', scaleMargins:{top:0.08,bottom:0.28} },
    timeScale: { borderColor:'rgba(120,120,130,0.35)', timeVisible:true, secondsVisible:false, rightOffset:4 },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    handleScroll: { mouseWheel:true, pressedMouseMove:true, horzTouchDrag:true, vertTouchDrag:true },
    handleScale: {
      mouseWheel:true, pinch:true,
      axisPressedMouseMove: { time:true, price:true },
      axisDoubleClickReset: { time:true, price:true }
    },
    autoSize: true
  });

  const candles = chart.addCandlestickSeries({
    upColor:'#26a69a', downColor:'#ef5350', borderVisible:false,
    wickUpColor:'#26a69a', wickDownColor:'#ef5350'
  });
  candles.setData(D.candles);

  const vol = chart.addHistogramSeries({ priceFormat:{type:'volume'}, priceScaleId:'vol' });
  chart.priceScale('vol').applyOptions({ scaleMargins:{top:0.8,bottom:0} });
  vol.setData(D.volume);

  D.rails.forEach(function(R){
    const s = chart.addLineSeries({
      color:R.color, lineWidth:1, priceLineVisible:false, lastValueVisible:false,
      crosshairMarkerVisible:false,
      lineStyle: R.dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Dotted
    });
    s.setData(R.data);
  });

  D.levels.forEach(function(L){
    candles.createPriceLine({
      price:L.price, color:L.color, lineWidth:1,
      lineStyle: L.dashed ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
      axisLabelVisible:true, title:L.name
    });
  });

  candles.setMarkers(D.markers);

  const legend = document.getElementById('legend');
  function ohlc(bar){
    if (!bar) return '';
    const col = bar.close >= bar.open ? '#26a69a' : '#ef5350';
    return '<span style="color:'+col+'">O '+bar.open.toFixed(2)+'  H '+bar.high.toFixed(2)+
           '  L '+bar.low.toFixed(2)+'  C '+bar.close.toFixed(2)+'</span>';
  }
  function levelTags(){
    return D.levels.map(function(L){
      return '<span style="color:'+L.color+';margin-left:14px">'+L.name+' '+L.price.toFixed(2)+'</span>';
    }).join('');
  }
  legend.innerHTML = ohlc(D.candles[D.candles.length-1]) + levelTags();

  chart.subscribeCrosshairMove(function(param){
    if (!param.time) {
      legend.innerHTML = ohlc(D.candles[D.candles.length-1]) + levelTags();
      return;
    }
    let s = ohlc(param.seriesData.get(candles)) + levelTags();
    D.trades.forEach(function(tr){
      if (param.time >= tr.t0 && param.time <= tr.t1)
        s += '<div style="margin-top:4px;color:#d1d4dc">'+tr.text+'</div>';
    });
    legend.innerHTML = s;
  });

  chart.timeScale().fitContent();
  if (D.focus) chart.timeScale().setVisibleRange(D.focus);
  // exposed so the chart can be driven/inspected from tests and the console
  window.__orb = { chart: chart, candles: candles, data: D };
})();
</script>
"""


def session_html(bars, trades, day, cfg, orb_window_mins: int = 15,
                 height: int = 520, zoom_to_trades: bool = True) -> str:
    """Self-contained HTML for one session, library inlined."""
    payload = session_payload(bars, trades, day, cfg, orb_window_mins, zoom_to_trades)
    return (_TEMPLATE
            .replace("__LIB__", _library())
            .replace("__DATA__", json.dumps(payload))
            .replace("__HEIGHT__", str(height)))


def write_session(bars, trades, day, cfg, path: Path, orb_window_mins: int = 15,
                  height: int = 620, zoom_to_trades: bool = True) -> Path:
    """Write a standalone page for one session."""
    path = Path(path)
    body = session_html(bars, trades, day, cfg, orb_window_mins,
                        height=height, zoom_to_trades=zoom_to_trades)
    path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{cfg.name} {pd.Timestamp(day):%Y-%m-%d}</title></head>"
        "<body style='margin:0;padding:12px;background:#14161a'>"
        f"{body}</body></html>"
    )
    return path

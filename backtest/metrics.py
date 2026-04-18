import pandas as pd


def summary(trades: pd.DataFrame, print_results: bool = True) -> dict:
    """
    Compute key performance metrics for the full trade set (all exits included).
    EOD exits are counted with their actual pnl_r; exit_eod column shows how many.
    All figures in R.
    """
    if trades.empty:
        return {"error": "No trades"}

    stats = _calc(trades)

    if print_results:
        _print(stats)

    return stats


def _calc(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {k: "n/a" for k in [
            "trades", "wins", "losses", "win_rate",
            "avg_win_r", "avg_loss_r", "expectancy_r",
            "total_r", "max_dd_r", "exit_target", "exit_stop", "exit_eod",
            "long_trades", "short_trades", "long_wr", "short_wr",
        ]}

    total    = len(trades)
    wins     = (trades["pnl_r"] > 0).sum()
    losses   = (trades["pnl_r"] < 0).sum()
    win_rate = wins / total * 100

    avg_win_r  = trades.loc[trades["pnl_r"] > 0, "pnl_r"].mean() if wins   else 0.0
    avg_loss_r = trades.loc[trades["pnl_r"] < 0, "pnl_r"].mean() if losses else 0.0
    expectancy_r = (win_rate / 100 * avg_win_r) + ((1 - win_rate / 100) * avg_loss_r)

    cum_r        = trades["pnl_r"].cumsum()
    max_dd_r     = _max_drawdown(cum_r)
    exit_counts  = trades["exit_reason"].value_counts().to_dict()
    eod_trades   = trades[trades["exit_reason"] == "eod"]
    avg_eod_r    = round(eod_trades["pnl_r"].mean(), 3) if not eod_trades.empty else "n/a"

    longs  = trades[trades["direction"] == "long"]
    shorts = trades[trades["direction"] == "short"]

    return {
        "trades":       total,
        "wins":         int(wins),
        "losses":       int(losses),
        "win_rate":     f"{win_rate:.1f}%",
        "avg_win_r":    round(avg_win_r,    3),
        "avg_loss_r":   round(avg_loss_r,   3),
        "expectancy_r": round(expectancy_r, 3),
        "total_r":      round(trades["pnl_r"].sum(), 2),
        "max_dd_r":     round(max_dd_r,     2),
        "exit_target":  exit_counts.get("target", 0),
        "exit_stop":    exit_counts.get("stop",   0),
        "exit_eod":     exit_counts.get("eod",    0),
        "avg_eod_r":    avg_eod_r,
        "long_trades":  len(longs),
        "short_trades": len(shorts),
        "long_wr":      f"{(longs['pnl_r'] > 0).mean() * 100:.1f}%" if len(longs)  else "n/a",
        "short_wr":     f"{(shorts['pnl_r'] > 0).mean() * 100:.1f}%" if len(shorts) else "n/a",
    }


def _max_drawdown(cumulative: pd.Series) -> float:
    if cumulative.empty:
        return 0.0
    peak     = cumulative.cummax()
    drawdown = cumulative - peak
    return drawdown.min()


def _print(stats: dict):
    print("\n--- Backtest Results ---")
    for k, v in stats.items():
        print(f"  {k:<15} {v}")
    print("------------------------\n")

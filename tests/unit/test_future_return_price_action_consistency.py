"""
Test de acuerdo cruzado: para el mismo conjunto de eventos condicionados,
Future Return Metrics (N+/N-) y Price Action (Win/Loss) deben coincidir
exactamente, en ambos modos (inside_event y holding). Este es el contrato que
motivó backend/core/future_returns.py — antes cada uno recalculaba su propio
signo por evento con una referencia de precio distinta y divergían.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.core.future_returns import compute_future_return_signs
from backend.core.price_action.builder import compute_price_action
from backend.core.probabilistic_pipeline import build_future_return_metrics


def _make_ohlcv(n: int = 40, base_close: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-03", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(42)
    close = base_close * np.cumprod(1 + rng.normal(0.001, 0.015, n))
    open_ = close * rng.uniform(0.99, 1.01, n)
    high  = close * rng.uniform(1.001, 1.02, n)
    low   = close * rng.uniform(0.98, 0.999, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


def _make_events_df(ohlcv: pd.DataFrame, indices: list[int]) -> pd.DataFrame:
    return pd.DataFrame([{"date": ohlcv.index[i]} for i in indices])


def _make_event_tf_bars(event_dates: list[pd.Timestamp], bars_per_day: int = 13) -> pd.DataFrame:
    """Barras de 30min sinteticas para los dias de evento (requerido por el
    modo inside_event de compute_price_action, incluso cuando el signo de
    win/loss ahora viene de event_signs y no de estas barras)."""
    rows = []
    idx = []
    rng = np.random.default_rng(7)
    for dt in event_dates:
        base = dt.normalize().replace(hour=9, minute=30)
        close_ref = 100.0
        for b in range(bars_per_day):
            ts = base + pd.Timedelta(minutes=30 * b)
            c = close_ref * (1 + rng.normal(0.0002, 0.005))
            rows.append({"open": c * 0.999, "high": c * 1.005, "low": c * 0.994, "close": c, "volume": 500_000.0})
            idx.append(ts)
            close_ref = c
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx, tz="UTC")).sort_index()


@pytest.mark.unit
@pytest.mark.parametrize(
    "price_action_mode,n_periods",
    [("inside_event", 0), ("holding", 5)],
)
def test_win_loss_matches_future_return_counts(price_action_mode, n_periods):
    ohlcv = _make_ohlcv(40)
    events = _make_events_df(ohlcv, list(range(2, 30)))

    future = build_future_return_metrics(
        conditioned_df=events, ohlcv_df=ohlcv, n_total_events=len(events),
        n_periods=n_periods, price_action_mode=price_action_mode,
    )
    event_signs = compute_future_return_signs(
        conditioned_df=events, ohlcv_df=ohlcv,
        n_periods=n_periods, price_action_mode=price_action_mode,
    )
    intraday = _make_event_tf_bars(list(events["date"])) if price_action_mode == "inside_event" else None
    price_action = compute_price_action(
        events_df=events, ohlcv_outer_df=ohlcv, ohlcv_event_tf=intraday,
        n_periods=n_periods, event_signs=event_signs, include_bands=False,
        outer_timeframe="1d",
    )

    assert future.return_count_positive == price_action.n_events_win
    assert future.return_count_negative == price_action.n_events_loss

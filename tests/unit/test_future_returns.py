"""
Tests unitarios para backend/core/future_returns.py — fuente única de signo
por evento, compartida entre build_future_return_metrics (N+/N-) y
compute_price_action (Win/Loss).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backend.core.future_returns import compute_future_return_signs
from backend.core.utc import to_utc_ts


def _make_daily_ohlcv(n: int = 30, base_close: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-03", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(0)
    close = base_close * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    open_ = close * rng.uniform(0.995, 1.005, n)
    high  = close * rng.uniform(1.001, 1.015, n)
    low   = close * rng.uniform(0.985, 0.999, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


def _make_events_df(ohlcv: pd.DataFrame, indices: list[int]) -> pd.DataFrame:
    return pd.DataFrame([{"date": ohlcv.index[i]} for i in indices])


@pytest.mark.unit
def test_signs_length_matches_conditioned_events():
    """Cada evento de conditioned_df tiene una entrada en el dict (1:1),
    incluso cuando el retorno no se puede calcular (None), a diferencia del
    comportamiento previo que descartaba esos eventos en silencio."""
    ohlcv = _make_daily_ohlcv(10)
    events = _make_events_df(ohlcv, [0, 3, 9])  # el índice 9 es el último bar
    signs = compute_future_return_signs(events, ohlcv, n_periods=3, price_action_mode="holding")
    assert len(signs) == 3
    last_ts = to_utc_ts(ohlcv.index[9])
    assert signs[last_ts] is None  # sin suficientes barras futuras


@pytest.mark.unit
def test_in_event_mode_uses_p0_open_to_close():
    ohlcv = _make_daily_ohlcv(10)
    events = _make_events_df(ohlcv, [4])
    signs = compute_future_return_signs(events, ohlcv, n_periods=0, price_action_mode="in_event")
    ts = to_utc_ts(ohlcv.index[4])
    expected = (ohlcv.iloc[4]["close"] - ohlcv.iloc[4]["open"]) / ohlcv.iloc[4]["open"]
    assert math.isclose(signs[ts], expected, rel_tol=1e-9)


@pytest.mark.unit
def test_holding_mode_uses_p1_open_to_pn_close():
    ohlcv = _make_daily_ohlcv(15)
    events = _make_events_df(ohlcv, [2])
    n_periods = 4
    signs = compute_future_return_signs(events, ohlcv, n_periods=n_periods, price_action_mode="holding")
    ts = to_utc_ts(ohlcv.index[2])
    expected = (ohlcv.iloc[2 + n_periods]["close"] - ohlcv.iloc[3]["open"]) / ohlcv.iloc[3]["open"]
    assert math.isclose(signs[ts], expected, rel_tol=1e-9)


@pytest.mark.unit
def test_empty_conditioned_df_returns_empty_dict():
    ohlcv = _make_daily_ohlcv(5)
    events = pd.DataFrame(columns=["date"])
    signs = compute_future_return_signs(events, ohlcv, n_periods=3, price_action_mode="holding")
    assert signs == {}

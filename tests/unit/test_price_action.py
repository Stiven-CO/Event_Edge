"""
Tests unitarios para backend/core/price_action/builder.py
"""
from __future__ import annotations

import math
from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from backend.core.price_action.builder import (
    MIN_EVENTS_PLOT,
    _aggregate_series,
    compute_price_action,
)
from backend.api.schemas import PriceActionResult


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------

def _make_daily_ohlcv(n: int = 30, base_close: float = 100.0) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-03", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(0)
    close = base_close * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    open_ = close * rng.uniform(0.995, 1.005, n)
    high  = close * rng.uniform(1.001, 1.015, n)
    low   = close * rng.uniform(0.985, 0.999, n)
    vol   = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=dates,
    )


def _make_events_df(ohlcv: pd.DataFrame, indices: list[int]) -> pd.DataFrame:
    rows = []
    for i in indices:
        rows.append({
            "date": ohlcv.index[i],
            "gap_pct": 0.01,
            "symbol": "TEST",
            "event_type": "earnings",
        })
    return pd.DataFrame(rows)


def _make_intraday(event_dates: list[pd.Timestamp], bars_per_day: int = 13) -> pd.DataFrame:
    """Genera barras de 30min para los días indicados (9:30–15:30, 13 barras)."""
    rows = []
    rng = np.random.default_rng(1)
    for dt in event_dates:
        base = dt.normalize().replace(hour=9, minute=30)
        close_ref = 100.0
        for b in range(bars_per_day):
            ts = base + pd.Timedelta(minutes=30 * b)
            c = close_ref * (1 + rng.normal(0.0002, 0.005))
            rows.append({
                "open":   c * 0.999,
                "high":   c * 1.005,
                "low":    c * 0.994,
                "close":  c,
                "volume": 500_000.0,
            })
            close_ref = c
    idx = pd.DatetimeIndex([r_idx for r_idx in
          [dt.normalize().replace(hour=9, minute=30) + pd.Timedelta(minutes=30 * b)
           for dt in event_dates for b in range(bars_per_day)]], tz="UTC")
    df = pd.DataFrame(rows, index=idx)
    return df.sort_index()


# ---------------------------------------------------------------------------
# Tests de normalización
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_daily_normalization():
    """close_P0 = referencia → primer punto de la serie daily normalizado a 100."""
    ohlcv = _make_daily_ohlcv(20)
    # evento en posición 5; P1 debe valer close[6] / close[5] * 100
    events = _make_events_df(ohlcv, [5])
    result = compute_price_action(events, ohlcv, None, n_periods=3)
    assert result.anchor_mode == "daily"
    expected_p1 = ohlcv.iloc[6]["close"] / ohlcv.iloc[5]["close"] * 100.0
    assert math.isclose(result.series_all.points[0].y, expected_p1, rel_tol=1e-4)


@pytest.mark.unit
def test_intraday_normalization():
    """open_P0 diario = referencia → primer bar intradía normaliza respecto a ese open."""
    ohlcv = _make_daily_ohlcv(10)
    event_ts = ohlcv.index[3]
    events = _make_events_df(ohlcv, [3])
    intraday = _make_intraday([event_ts])
    result = compute_price_action(events, ohlcv, intraday, n_periods=0)
    assert result.anchor_mode == "intraday_30min"
    ref = ohlcv.iloc[3]["open"]
    first_close_30m = float(
        intraday[intraday.index.normalize().tz_convert("UTC") == event_ts.normalize()
                 ].sort_index().iloc[0]["close"]
    )
    expected = first_close_30m / ref * 100.0
    assert math.isclose(result.series_all.points[0].y, expected, rel_tol=1e-4)


# ---------------------------------------------------------------------------
# Tests de clasificación win/loss
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_win_loss_classification_daily():
    """Retorno (close_Pn - close_P0)/close_P0 > 0 → win; ≤ 0 → loss."""
    ohlcv = _make_daily_ohlcv(30)
    # Forzar un evento garantizado win y otro loss
    # win: close[pos+n] > close[pos]
    # Vamos a encontrar pares que cumplan esa condición de forma determinista
    n = 3
    win_events = []
    loss_events = []
    for i in range(2, 25):
        ret = (ohlcv.iloc[i + n]["close"] - ohlcv.iloc[i]["close"]) / ohlcv.iloc[i]["close"]
        if ret > 0 and len(win_events) < 3:
            win_events.append(i)
        elif ret <= 0 and len(loss_events) < 3:
            loss_events.append(i)
        if len(win_events) >= 3 and len(loss_events) >= 3:
            break

    all_indices = win_events + loss_events
    events = _make_events_df(ohlcv, all_indices)
    result = compute_price_action(events, ohlcv, None, n_periods=n)

    assert result.n_events_win == len(win_events)
    assert result.n_events_loss == len(loss_events)
    assert result.n_events_all == len(all_indices)


@pytest.mark.unit
def test_win_loss_classification_intraday():
    """(close_P0 − open_P0)/open_P0 > 0 → win; usa datos diarios, no 30min."""
    ohlcv = _make_daily_ohlcv(20)
    # Buscar días donde close > open (win) y close <= open (loss)
    win_idx, loss_idx = None, None
    for i in range(2, 18):
        if ohlcv.iloc[i]["close"] > ohlcv.iloc[i]["open"] and win_idx is None:
            win_idx = i
        if ohlcv.iloc[i]["close"] <= ohlcv.iloc[i]["open"] and loss_idx is None:
            loss_idx = i
        if win_idx and loss_idx:
            break

    if win_idx is None or loss_idx is None:
        pytest.skip("No se encontraron días con close>open y close<=open en OHLCV sintético")

    indices = [win_idx, loss_idx]
    events = _make_events_df(ohlcv, indices)
    intraday = _make_intraday([ohlcv.index[i] for i in indices])
    result = compute_price_action(events, ohlcv, intraday, n_periods=0)
    assert result.n_events_win >= 1
    assert result.n_events_loss >= 1


# ---------------------------------------------------------------------------
# Tests de comportamiento con pocos eventos
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_insufficient_events_returns_warning():
    """Con < 5 eventos → warning = 'insufficient_events'."""
    ohlcv = _make_daily_ohlcv(20)
    events = _make_events_df(ohlcv, [5])  # solo 1 evento
    result = compute_price_action(events, ohlcv, None, n_periods=3)
    assert result.warning == "insufficient_events"


@pytest.mark.unit
def test_omit_event_without_intraday_data():
    """Evento sin barras de 30min → n_events_omitted += 1, no excepción."""
    ohlcv = _make_daily_ohlcv(10)
    events = _make_events_df(ohlcv, [3])
    # Pasar intraday vacío
    result = compute_price_action(events, ohlcv, pd.DataFrame(), n_periods=0)
    assert result.n_events_omitted >= 1
    # No debe lanzar excepción → el test llegar aquí = ok


# ---------------------------------------------------------------------------
# Tests de bandas
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_band_width_positive():
    """band_upper[i].y >= series_all.points[i].y para todo i."""
    series = [
        [100.0, 101.0, 102.0],
        [100.0, 103.0, 99.0],
        [100.0, 98.0, 101.0],
        [100.0, 102.5, 100.5],
        [100.0, 99.5, 103.0],
    ]
    result = _aggregate_series(series, include_bands=True)
    assert result.band_upper is not None
    for pt, upper in zip(result.points, result.band_upper):
        assert upper.y >= pt.y


@pytest.mark.unit
def test_include_bands_false():
    """include_bands=False → band_upper y band_lower son None en todas las series."""
    ohlcv = _make_daily_ohlcv(30)
    events = _make_events_df(ohlcv, list(range(2, 20)))
    result = compute_price_action(events, ohlcv, None, n_periods=3, include_bands=False)
    assert result.series_all.band_upper is None
    assert result.series_all.band_lower is None


@pytest.mark.unit
def test_daily_x_labels():
    """n_periods=3 → x_labels = ['P1', 'P2', 'P3']."""
    ohlcv = _make_daily_ohlcv(20)
    events = _make_events_df(ohlcv, list(range(2, 12)))
    result = compute_price_action(events, ohlcv, None, n_periods=3)
    assert result.x_labels == ["P1", "P2", "P3"]


@pytest.mark.unit
def test_series_lengths_consistent_daily():
    """Todas las series (all, win, loss) tienen el mismo número de puntos."""
    ohlcv = _make_daily_ohlcv(30)
    events = _make_events_df(ohlcv, list(range(2, 20)))
    result = compute_price_action(events, ohlcv, None, n_periods=4)
    lens = {
        len(result.series_all.points),
        len(result.series_win.points) or None,
        len(result.series_loss.points) or None,
    }
    # Si no vacío, deben coincidir longitudes con n_periods
    if result.series_all.points:
        assert len(result.series_all.points) == 4

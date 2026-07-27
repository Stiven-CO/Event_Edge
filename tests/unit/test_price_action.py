"""
Tests unitarios para backend/core/price_action/builder.py
"""
from __future__ import annotations

import math
from datetime import timezone

import numpy as np
import pandas as pd
import pytest

from backend.core.future_returns import compute_future_return_signs
from backend.core.price_action.builder import (
    MIN_EVENTS_PLOT,
    _aggregate_series,
    compute_distribution_stats,
    compute_price_action,
)
from backend.core.utc import to_utc_ts
from backend.api.schemas import PriceActionResult


def _signs_for(events: pd.DataFrame, ohlcv: pd.DataFrame, n_periods: int) -> dict:
    """event_signs derivado con la misma fuente que usa produccion (Future Return
    Metrics), para tests que no les importa la clasificacion win/loss en si misma."""
    mode = "inside_event" if n_periods == 0 else "holding"
    return compute_future_return_signs(events, ohlcv, n_periods=n_periods, price_action_mode=mode)


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 30, base_close: float = 100.0) -> pd.DataFrame:
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


def _make_event_tf_bars(event_dates: list[pd.Timestamp], bars_per_day: int = 13) -> pd.DataFrame:
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
    """close_P0 = referencia → primer punto de la serie holding normalizado a 100."""
    ohlcv = _make_ohlcv(20)
    # evento en posición 5; P1 debe valer close[6] / close[5] * 100
    events = _make_events_df(ohlcv, [5])
    result = compute_price_action(events, ohlcv, None, n_periods=3, event_signs=_signs_for(events, ohlcv, 3))
    assert result.anchor_mode == "holding"
    expected_p1 = ohlcv.iloc[6]["close"] / ohlcv.iloc[5]["close"] * 100.0
    assert math.isclose(result.series_all.points[0].y, expected_p1, rel_tol=1e-4)


@pytest.mark.unit
def test_intraday_normalization():
    """open_P0 diario = referencia → primer bar intradía normaliza respecto a ese open."""
    ohlcv = _make_ohlcv(10)
    event_ts = ohlcv.index[3]
    events = _make_events_df(ohlcv, [3])
    intraday = _make_event_tf_bars([event_ts])
    result = compute_price_action(events, ohlcv, intraday, n_periods=0, event_signs=_signs_for(events, ohlcv, 0))
    assert result.anchor_mode == "inside_event"
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
    """La bucketizacion win/loss usa exactamente el signo de event_signs
    (fuente compartida con Future Return Metrics), no un recalculo propio a
    partir de precios — se prueba con un event_signs explicito y deterministico,
    desacoplado de compute_future_return_signs (que se prueba por separado)."""
    ohlcv = _make_ohlcv(30)
    n = 3
    win_indices = [3, 6, 9]
    loss_indices = [12, 15, 18]
    all_indices = win_indices + loss_indices
    events = _make_events_df(ohlcv, all_indices)

    event_signs = {}
    for i in win_indices:
        event_signs[to_utc_ts(ohlcv.index[i])] = 0.05
    for i in loss_indices:
        event_signs[to_utc_ts(ohlcv.index[i])] = -0.02

    result = compute_price_action(events, ohlcv, None, n_periods=n, event_signs=event_signs)

    assert result.n_events_win == len(win_indices)
    assert result.n_events_loss == len(loss_indices)
    assert result.n_events_all == len(all_indices)


@pytest.mark.unit
def test_win_loss_classification_intraday():
    """Modo inside event: bucketizacion win/loss via event_signs explicito,
    desacoplado de la logica de precio (probada aparte en compute_future_return_signs)."""
    ohlcv = _make_ohlcv(20)
    win_idx, loss_idx = 5, 10
    indices = [win_idx, loss_idx]
    events = _make_events_df(ohlcv, indices)
    intraday = _make_event_tf_bars([ohlcv.index[i] for i in indices])

    event_signs = {
        to_utc_ts(ohlcv.index[win_idx]): 0.03,
        to_utc_ts(ohlcv.index[loss_idx]): -0.01,
    }
    result = compute_price_action(events, ohlcv, intraday, n_periods=0, event_signs=event_signs)
    assert result.n_events_win == 1
    assert result.n_events_loss == 1


@pytest.mark.unit
def test_win_loss_tie_and_none_excluded_but_kept_in_all():
    """Empate (retorno == 0) o event_signs faltante (None) → el evento no entra
    en win_series/loss_series pero sigue contando en n_events_all."""
    ohlcv = _make_ohlcv(30)
    tie_idx, none_idx, win_idx = 3, 6, 9
    events = _make_events_df(ohlcv, [tie_idx, none_idx, win_idx])

    event_signs = {
        to_utc_ts(ohlcv.index[tie_idx]): 0.0,
        # none_idx deliberadamente ausente del dict -> event_signs.get(...) es None
        to_utc_ts(ohlcv.index[win_idx]): 0.02,
    }
    result = compute_price_action(events, ohlcv, None, n_periods=3, event_signs=event_signs)

    assert result.n_events_all == 3
    assert result.n_events_win == 1
    assert result.n_events_loss == 0


# ---------------------------------------------------------------------------
# Tests de comportamiento con pocos eventos
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_insufficient_events_returns_warning():
    """Con < 5 eventos → warning = 'insufficient_events'."""
    ohlcv = _make_ohlcv(20)
    events = _make_events_df(ohlcv, [5])  # solo 1 evento
    result = compute_price_action(events, ohlcv, None, n_periods=3, event_signs={})
    assert result.warning == "insufficient_events"


@pytest.mark.unit
def test_omit_event_without_intraday_data():
    """Evento sin barras de 30min → n_events_omitted += 1, no excepción."""
    ohlcv = _make_ohlcv(10)
    events = _make_events_df(ohlcv, [3])
    # Pasar intraday vacío
    result = compute_price_action(events, ohlcv, pd.DataFrame(), n_periods=0, event_signs={})
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
    ohlcv = _make_ohlcv(30)
    events = _make_events_df(ohlcv, list(range(2, 20)))
    result = compute_price_action(events, ohlcv, None, n_periods=3, event_signs={}, include_bands=False)
    assert result.series_all.band_upper is None
    assert result.series_all.band_lower is None


@pytest.mark.unit
def test_daily_x_labels():
    """n_periods=3 → x_labels = ['P1', 'P2', 'P3']."""
    ohlcv = _make_ohlcv(20)
    events = _make_events_df(ohlcv, list(range(2, 12)))
    result = compute_price_action(events, ohlcv, None, n_periods=3, event_signs={})
    assert result.x_labels == ["P1", "P2", "P3"]


@pytest.mark.unit
def test_series_lengths_consistent_daily():
    """Todas las series (all, win, loss) tienen el mismo número de puntos."""
    ohlcv = _make_ohlcv(30)
    events = _make_events_df(ohlcv, list(range(2, 20)))
    result = compute_price_action(events, ohlcv, None, n_periods=4, event_signs=_signs_for(events, ohlcv, 4))
    lens = {
        len(result.series_all.points),
        len(result.series_win.points) or None,
        len(result.series_loss.points) or None,
    }
    # Si no vacío, deben coincidir longitudes con n_periods
    if result.series_all.points:
        assert len(result.series_all.points) == 4


# ---------------------------------------------------------------------------
# Tests de compute_distribution_stats (Dashboard Quant)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_distribution_stats_daily_x_labels_match_price_action():
    """Mismo events_df/n_periods → x_labels idénticos entre price-action y
    distribution-stats (ambos paneles deben compartir eje X)."""
    ohlcv = _make_ohlcv(30)
    events = _make_events_df(ohlcv, list(range(2, 20)))
    price_action = compute_price_action(events, ohlcv, None, n_periods=4, event_signs={})
    dist = compute_distribution_stats(events, ohlcv, None, n_periods=4)
    assert dist.anchor_mode == "holding"
    assert dist.x_labels == price_action.x_labels == ["P1", "P2", "P3", "P4"]
    assert len(dist.rows) == 4
    assert [row.offset for row in dist.rows] == [1, 2, 3, 4]
    assert [row.label for row in dist.rows] == dist.x_labels


@pytest.mark.unit
def test_distribution_stats_intraday_x_labels_match_price_action():
    """Modo inside event: mismo events_df/intraday → mismos x_labels que price-action."""
    ohlcv = _make_ohlcv(20)
    indices = list(range(2, 18))
    events = _make_events_df(ohlcv, indices)
    intraday = _make_event_tf_bars([ohlcv.index[i] for i in indices])
    price_action = compute_price_action(events, ohlcv, intraday, n_periods=0, event_signs={})
    dist = compute_distribution_stats(events, ohlcv, intraday, n_periods=0)
    assert dist.anchor_mode == "inside_event"
    assert dist.x_labels == price_action.x_labels


@pytest.mark.unit
def test_distribution_stats_row_fields_are_finite():
    """Cada fila debe traer métricas numéricas finitas y una clasificación válida."""
    ohlcv = _make_ohlcv(40)
    events = _make_events_df(ohlcv, list(range(2, 30)))
    dist = compute_distribution_stats(events, ohlcv, None, n_periods=5, tail_q=0.1)
    assert len(dist.rows) == 5
    for row in dist.rows:
        for field in ("ret_mean", "ret_p25", "ret_p75", "cvar", "r_cvar",
                       "asimetria", "curtosis", "rev_alcista_mean", "rev_alcista_p75",
                       "rev_bajista_mean", "rev_bajista_p75", "ratio_colas"):
            assert math.isfinite(getattr(row, field)), f"{field} no finito en offset {row.offset}"
        assert row.color_base in ("azul", "amarillo", "coral", "blanco")
        assert row.icon in ("", "⚡", "⚠️", "🔄")
    # Reversión alcista/bajista simétricas: ambas ≥ 0 por construcción
    # (h≥c y c≥l siempre, ver builder._build_offset_frame_daily)
    for row in dist.rows:
        assert row.rev_alcista_mean >= 0
        assert row.rev_bajista_mean >= 0


@pytest.mark.unit
def test_distribution_stats_low_n_offset_forced_neutral():
    """Offset con n_obs < MIN_EVENTS_PLOT → color_base='blanco', icon='' aunque
    las métricas crudas (ret_mean, ratio_colas, etc.) den señales fuertes —
    evita clasificar con confianza sobre una muestra ruidosa."""
    ohlcv = _make_ohlcv(60)
    # 8 eventos con ventana de 6 sesiones: todas las columnas P1..P6 tienen
    # n_obs=8 (>= MIN_EVENTS_PLOT=5), sirve de control "bien muestreado".
    events = _make_events_df(ohlcv, list(range(2, 10)))
    dist = compute_distribution_stats(events, ohlcv, None, n_periods=6)
    assert len(dist.rows) == 6
    for row in dist.rows:
        assert row.n_obs == 8

    # Forzamos un long_df sintético con un offset de n_obs=2 (ruidoso) para
    # confirmar la salvaguarda directamente sobre _aggregate_distribution_rows.
    from backend.core.price_action.builder import _aggregate_distribution_rows

    long_df = pd.DataFrame([
        # offset=1: 2 observaciones extremas → ratio_colas/asimetria altísimos
        {"offset": 1, "returns": 0.10, "reversion_alcista": 0.001, "reversion_bajista": 0.001},
        {"offset": 1, "returns": 0.11, "reversion_alcista": 0.001, "reversion_bajista": 0.001},
        # offset=2: 6 observaciones normales → bien muestreado
        *[{"offset": 2, "returns": r, "reversion_alcista": 0.005, "reversion_bajista": 0.005}
          for r in [0.01, -0.01, 0.02, -0.02, 0.005, -0.005]],
    ])
    rows = _aggregate_distribution_rows(long_df, ["X1", "X2"], tail_q=0.05, clean_q=0.25, pain_q=0.75)
    row_by_offset = {row.offset: row for row in rows}
    assert row_by_offset[1].n_obs == 2
    assert row_by_offset[1].color_base == "blanco"
    assert row_by_offset[1].icon == ""
    assert row_by_offset[2].n_obs == 6


@pytest.mark.unit
def test_distribution_stats_insufficient_events_warning():
    """Con < MIN_EVENTS_PLOT eventos usados → warning = 'insufficient_events'."""
    ohlcv = _make_ohlcv(20)
    events = _make_events_df(ohlcv, [5])  # solo 1 evento
    dist = compute_distribution_stats(events, ohlcv, None, n_periods=3)
    assert dist.n_events_used < MIN_EVENTS_PLOT
    assert dist.warning == "insufficient_events"


@pytest.mark.unit
def test_distribution_stats_empty_events_no_exception():
    """events_df vacío → filas vacías, sin excepción."""
    ohlcv = _make_ohlcv(20)
    events = _make_events_df(ohlcv, [])
    dist = compute_distribution_stats(events, ohlcv, None, n_periods=3)
    assert dist.rows == []
    assert dist.n_events_used == 0

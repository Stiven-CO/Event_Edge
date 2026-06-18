"""
Métricas informativas en dos niveles:

  compute_global_metrics   — línea base estadística del activo (sin eventos).
  compute_informative_metrics — estadísticas sobre un conjunto de eventos detectados.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from backend.api.schemas import (
    EventRecord,
    GlobalInformativeMetrics,
    InformativeMetrics,
    QQPlotData,
    ReturnHistogram,
    RollingVolPoint,
)


def compute_informative_metrics(
    ohlcv_df: pd.DataFrame,
    events: list[EventRecord],
    periods: list[int],
    data_source: str,
    data_source_detail: str | None = None,
) -> InformativeMetrics:
    """
    Calcula métricas informativas sobre todos los eventos.

    Args:
        ohlcv_df: DataFrame OHLCV con index DatetimeIndex UTC
        events: Lista de EventRecord detectados (sin filtrar)
        periods: Lista de períodos a calcular, ej. [1, 3, 5, 10]
        data_source: "mdh" o "yfinance"

    Returns:
        InformativeMetrics con estadísticas descriptivas.
    """
    if not events:
        from backend.api.schemas import EventType  # noqa: PLC0415
        return InformativeMetrics(
            symbol="",
            event_type=EventType.earnings,
            n_total_events=0,
            frequency_per_year=0.0,
            frequency_per_quarter=0.0,
            avg_movement_range={n: {"mean": 0.0, "std": 0.0} for n in periods},
            avg_candle_range={n: {"mean": 0.0, "std": 0.0} for n in periods},
            gap_mean=None,
            gap_std=None,
            data_source=data_source,
            data_source_detail=data_source_detail,
        )

    # Símbolo y tipo de evento de la muestra
    symbol = events[0].symbol
    event_type = events[0].event_type

    df = ohlcv_df.sort_index()
    trading_dates = df.index  # DatetimeIndex UTC

    # Frecuencia temporal
    n_years = _calc_n_years(df)
    freq_per_year = len(events) / n_years if n_years > 0 else 0.0
    freq_per_quarter = freq_per_year / 4.0

    # ── P0 stats (día del evento) ────────────────────────────────────────────
    event_day_ranges: list[float] = []
    event_day_volumes: list[float] = []
    event_day_returns: list[float] = []
    _has_volume = "volume" in df.columns

    for event in events:
        ts = pd.Timestamp(event.date).tz_convert("UTC")
        pos = _find_position(trading_dates, ts)
        if pos is None:
            continue
        open_p0 = float(df["open"].iloc[pos])
        close_p0 = float(df["close"].iloc[pos])
        high_p0 = float(df["high"].iloc[pos])
        low_p0 = float(df["low"].iloc[pos])
        if open_p0 == 0 or pd.isna(open_p0) or close_p0 == 0 or pd.isna(close_p0):
            continue
        event_day_ranges.append((high_p0 - low_p0) / close_p0)
        event_day_returns.append((close_p0 - open_p0) / open_p0)
        if _has_volume:
            vol = df["volume"].iloc[pos]
            if not pd.isna(vol):
                event_day_volumes.append(float(vol))

    # ── Construir arrays de métricas por período ─────────────────────────────
    avg_movement_range: dict[int, dict] = {}
    avg_candle_range: dict[int, dict] = {}
    avg_forward_return: dict[int, dict] = {}

    for n in periods:
        movements: list[float] = []
        candles: list[float] = []
        fwd_rets: list[float] = []

        for event in events:
            ts = pd.Timestamp(event.date).tz_convert("UTC")
            # Buscar posición de P0 en el índice
            pos = _find_position(trading_dates, ts)
            if pos is None:
                continue

            close_p0 = df["close"].iloc[pos]
            if close_p0 == 0 or pd.isna(close_p0):
                continue

            # P0..Pn requiere n sesiones posteriores: índices pos..pos+n inclusive
            end_pos = pos + n
            if end_pos >= len(df):
                # No hay n sesiones completas → excluir de este período
                continue

            # movement_range_n = (max(high[P0..Pn]) - min(low[P0..Pn])) / close_P0
            window_high = df["high"].iloc[pos : end_pos + 1]
            window_low = df["low"].iloc[pos : end_pos + 1]
            movement = (window_high.max() - window_low.min()) / close_p0
            movements.append(float(movement))

            # candle_range_n = (high_Pn - low_Pn) / close_P0
            high_pn = df["high"].iloc[end_pos]
            low_pn = df["low"].iloc[end_pos]
            candle = (high_pn - low_pn) / close_p0
            candles.append(float(candle))

            # forward_return_n = (close_Pn - open_P1) / open_P1
            # Garantizado: end_pos >= pos+1 (n>=1) y end_pos < len(df)
            open_p1 = float(df["open"].iloc[pos + 1])
            close_pn = float(df["close"].iloc[end_pos])
            if open_p1 != 0 and not pd.isna(open_p1) and not pd.isna(close_pn):
                fwd_rets.append((close_pn - open_p1) / open_p1)

        avg_movement_range[n] = _stats(movements)
        avg_candle_range[n] = _stats(candles)
        avg_forward_return[n] = _stats(fwd_rets)

    # Gap statistics (solo eventos con gap_pct != 0)
    gap_values = [
        e.gap_pct
        for e in events
        if e.gap_pct is not None and e.gap_pct != 0.0
    ]
    if gap_values:
        arr = np.array(gap_values, dtype=float)
        gap_mean: float | None = float(np.mean(arr))
        gap_std: float | None = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    else:
        gap_mean = None
        gap_std = None

    return InformativeMetrics(
        symbol=symbol,
        event_type=event_type,
        n_total_events=len(events),
        frequency_per_year=freq_per_year,
        frequency_per_quarter=freq_per_quarter,
        avg_movement_range=avg_movement_range,
        avg_candle_range=avg_candle_range,
        gap_mean=gap_mean,
        gap_std=gap_std,
        data_source=data_source,
        data_source_detail=data_source_detail,
        event_day_range_mean=_stats(event_day_ranges)["mean"] if event_day_ranges else None,
        event_day_range_std=_stats(event_day_ranges)["std"] if event_day_ranges else None,
        event_day_volume_mean=_stats(event_day_volumes)["mean"] if event_day_volumes else None,
        event_day_volume_std=_stats(event_day_volumes)["std"] if event_day_volumes else None,
        event_day_return_mean=_stats(event_day_returns)["mean"] if event_day_returns else None,
        event_day_return_std=_stats(event_day_returns)["std"] if event_day_returns else None,
        avg_forward_return=avg_forward_return,
    )


# ---------------------------------------------------------------------------
# Métricas globales del activo (sin eventos, sin condicionamiento)
# ---------------------------------------------------------------------------

def compute_global_metrics(
    ohlcv_df: pd.DataFrame,
    symbol: str,
    data_source: str,
    data_source_detail: str | None = None,
) -> GlobalInformativeMetrics:
    """
    Calcula la línea base estadística del activo sobre el historial completo.

    Requiere al menos 20 observaciones para producir estadísticas fiables.
    Los cálculos de Hurst y autocorrelación degradan a None / 0.0 con pocos datos.
    """
    df = ohlcv_df.sort_index().copy()
    returns = df["close"].pct_change().dropna()

    n = len(returns)
    ret_arr = returns.to_numpy(dtype=float)

    date_start = df.index.min().strftime("%Y-%m-%d") if not df.empty else ""
    date_end   = df.index.max().strftime("%Y-%m-%d") if not df.empty else ""

    # ── A: Histograma de retornos ─────────────────────────────────────────────
    n_bins = min(50, max(10, n // 20))
    hist_counts, hist_edges = np.histogram(ret_arr, bins=n_bins)
    return_histogram = ReturnHistogram(
        edges=[float(e) for e in hist_edges],
        counts=[int(c) for c in hist_counts],
    )

    # ── A: Q-Q plot (cuantiles teóricos normales vs muestrales) ───────────────
    if n >= 4:
        (theoretical_q, sample_q), _ = scipy_stats.probplot(ret_arr, dist="norm")
        qqplot_data = QQPlotData(
            theoretical=[float(v) for v in theoretical_q],
            sample=[float(v) for v in sample_q],
        )
    else:
        qqplot_data = QQPlotData(theoretical=[], sample=[])

    # ── B: Estadística descriptiva ────────────────────────────────────────────
    return_mean   = float(np.mean(ret_arr))  if n > 0 else 0.0
    return_median = float(np.median(ret_arr)) if n > 0 else 0.0
    return_std    = float(np.std(ret_arr, ddof=1)) if n > 1 else 0.0
    return_skewness = float(scipy_stats.skew(ret_arr)) if n >= 3 else 0.0
    return_kurtosis = float(scipy_stats.kurtosis(ret_arr)) if n >= 4 else 0.0  # excess
    return_min    = float(np.min(ret_arr)) if n > 0 else 0.0
    return_max    = float(np.max(ret_arr)) if n > 0 else 0.0

    # ── C: Volatilidad anualizada ─────────────────────────────────────────────
    annualized_vol = return_std * np.sqrt(252)

    # ── C: ATR(14) ────────────────────────────────────────────────────────────
    atr_series = _compute_atr(df, period=14)
    atr_mean   = float(atr_series.mean()) if not atr_series.empty else 0.0

    # ── C: Rolling vol 30 días (ventana de 30 sesiones, anualizada) ───────────
    rolling_std = returns.rolling(30).std().dropna()
    rolling_vol_ann = rolling_std * np.sqrt(252)
    # Limitar a 500 puntos más recientes para mantener payload razonable
    rolling_tail = rolling_vol_ann.tail(500)
    rolling_vol_30d = [
        RollingVolPoint(
            date=ts.strftime("%Y-%m-%d"),
            vol=float(vol),
        )
        for ts, vol in rolling_tail.items()
        if not np.isnan(vol)
    ]

    # ── D: Hurst exponent (R/S method) ───────────────────────────────────────
    hurst_exponent = _hurst_exponent_rs(ret_arr) if n >= 50 else None

    # ── D: Autocorrelación en lags 1, 5, 10 ──────────────────────────────────
    autocorr_lag1  = float(returns.autocorr(lag=1))  if n > 1  else 0.0
    autocorr_lag5  = float(returns.autocorr(lag=5))  if n > 5  else 0.0
    autocorr_lag10 = float(returns.autocorr(lag=10)) if n > 10 else 0.0

    # Protección contra NaN en autocorrelación
    autocorr_lag1  = 0.0 if np.isnan(autocorr_lag1)  else autocorr_lag1
    autocorr_lag5  = 0.0 if np.isnan(autocorr_lag5)  else autocorr_lag5
    autocorr_lag10 = 0.0 if np.isnan(autocorr_lag10) else autocorr_lag10

    return GlobalInformativeMetrics(
        symbol=symbol,
        data_source=data_source,
        data_source_detail=data_source_detail,
        n_observations=n,
        date_start=date_start,
        date_end=date_end,
        return_histogram=return_histogram,
        qqplot_data=qqplot_data,
        return_mean=return_mean,
        return_median=return_median,
        return_std=return_std,
        return_skewness=return_skewness,
        return_kurtosis=return_kurtosis,
        return_min=return_min,
        return_max=return_max,
        annualized_vol=annualized_vol,
        atr_mean=atr_mean,
        rolling_vol_30d=rolling_vol_30d,
        hurst_exponent=hurst_exponent,
        autocorr_lag1=autocorr_lag1,
        autocorr_lag5=autocorr_lag5,
        autocorr_lag10=autocorr_lag10,
    )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range usando EWM con span=period."""
    high_low  = df["high"] - df["low"]
    high_pc   = (df["high"] - df["close"].shift(1)).abs()
    low_pc    = (df["low"]  - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _hurst_exponent_rs(returns: np.ndarray) -> float | None:
    """
    Estima el exponente de Hurst por el método R/S clásico.
    H < 0.5 → reversión a media | H ≈ 0.5 → random walk | H > 0.5 → tendencial
    """
    n = len(returns)
    max_lag = n // 4
    if max_lag < 10:
        return None

    # Construir ~20 puntos de escala logarítmicamente distribuidos
    n_steps = 20
    step = max(1, (max_lag - 10) // n_steps)
    lags = list(range(10, max_lag + 1, step))

    rs_points: list[tuple[float, float]] = []
    for lag in lags:
        sub_rs: list[float] = []
        for start in range(0, n - lag + 1, lag):
            sub = returns[start : start + lag]
            if len(sub) < 2:
                continue
            mean_sub  = sub.mean()
            cumdev    = np.cumsum(sub - mean_sub)
            r         = cumdev.max() - cumdev.min()
            s         = sub.std(ddof=1)
            if s > 0:
                sub_rs.append(r / s)
        if sub_rs:
            rs_points.append((np.log(lag), np.log(float(np.mean(sub_rs)))))

    if len(rs_points) < 3:
        return None

    log_n_arr, log_rs_arr = zip(*rs_points)
    slope, _ = np.polyfit(log_n_arr, log_rs_arr, 1)
    return float(np.clip(slope, 0.0, 1.0))


def _calc_n_years(df: pd.DataFrame) -> float:
    """Años calendarios cubiertos por el DataFrame OHLCV."""
    if df.empty:
        return 0.0
    delta = (df.index.max() - df.index.min()).days
    return delta / 365.25


def _find_position(index: pd.DatetimeIndex, ts: pd.Timestamp) -> int | None:
    """Retorna el índice entero de ts en index, o None si no existe."""
    loc_arr = index.get_indexer([ts], method="nearest")
    if loc_arr[0] < 0:
        return None
    # Verificar que el match sea exacto (mismo día normalizado)
    found_ts = index[loc_arr[0]].normalize()
    if found_ts != ts.normalize():
        return None
    return int(loc_arr[0])


def _stats(values: list[float]) -> dict:
    """Devuelve {mean, std} de la lista; 0.0 si está vacía."""
    if not values:
        return {"mean": 0.0, "std": 0.0}
    arr = np.array(values, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
    }

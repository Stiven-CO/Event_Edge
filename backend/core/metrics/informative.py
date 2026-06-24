"""
Métricas globales del activo (línea base estadística, sin eventos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from backend.api.schemas import (
    GlobalInformativeMetrics,
    QQPlotData,
    ReturnHistogram,
    RollingVolPoint,
)


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

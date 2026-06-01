"""
Métricas informativas: estadísticas descriptivas sobre el universo completo
de eventos detectados. Sin condicionamiento, sin modelos estadísticos.

No hay look-ahead: todos los cálculos usan datos posteriores al open del evento.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.api.schemas import EventRecord, InformativeMetrics


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
# Helpers internos
# ---------------------------------------------------------------------------

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

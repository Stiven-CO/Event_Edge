"""
Lógica de alineación, normalización y agregación para el Price Action Plot.

Reglas de diseño:
    - n_periods == 0 → modo intraday (barras de 30 min del día del evento)
    - n_periods  > 0 → modo daily (sesiones P1 → Pn; P0 excluido)
    - Normalización: precio(t) / referencia × 100  (referencia = 100)
    - Clasificación win/loss usa siempre datos DIARIOS
    - Eventos sin datos intradía → omitidos silenciosamente (n_events_omitted)
    - Umbral mínimo MIN_EVENTS_PLOT = 5 (igual que MIN_SAMPLES probabilístico)
"""
from __future__ import annotations

import math
import logging

import numpy as np
import pandas as pd

from backend.api.schemas import (
    PriceActionPoint,
    PriceActionResult,
    PriceActionSeries,
)

logger = logging.getLogger(__name__)

MIN_EVENTS_PLOT = 5


def _to_utc(v) -> pd.Timestamp:
    ts = pd.Timestamp(v)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def compute_price_action(
    events_df: pd.DataFrame,
    ohlcv_daily_df: pd.DataFrame,
    ohlcv_intraday_df: pd.DataFrame | None,
    n_periods: int,
    include_bands: bool = True,
) -> PriceActionResult:
    """
    Construye el PriceActionResult a partir de los eventos ya condicionados.

    Args:
        events_df:         DataFrame de eventos filtrados (columnas: date, gap_pct …).
        ohlcv_daily_df:    OHLCV diario con DatetimeIndex UTC.
        ohlcv_intraday_df: OHLCV 30min con DatetimeIndex UTC; None si n_periods > 0.
        n_periods:         Horizonte (0 = intraday, >0 = daily).
        include_bands:     Si False, no calcular std; devolver band_upper/lower = None.
    """
    if n_periods == 0:
        intraday = ohlcv_intraday_df if ohlcv_intraday_df is not None else pd.DataFrame()
        return _build_intraday(events_df, ohlcv_daily_df, intraday, include_bands)
    return _build_daily(events_df, ohlcv_daily_df, n_periods, include_bands)


# ---------------------------------------------------------------------------
# Modo intraday (n=0)
# ---------------------------------------------------------------------------

def _build_intraday(
    events_df: pd.DataFrame,
    ohlcv_daily: pd.DataFrame,
    ohlcv_30min: pd.DataFrame,
    include_bands: bool,
) -> PriceActionResult:
    daily_idx = ohlcv_daily.sort_index()
    daily_by_date_intraday = {ts.normalize(): ts for ts in daily_idx.index}

    # Construir índice de fechas disponibles en 30min
    if ohlcv_30min.empty:
        available_dates: set[str] = set()
    else:
        available_dates = {
            str(pd.Timestamp(ts).normalize().date())
            for ts in ohlcv_30min.index
        }

    all_series: list[list[float]] = []
    win_series: list[list[float]] = []
    loss_series: list[list[float]] = []
    n_omitted = 0

    for _, row in events_df.iterrows():
        event_ts = _to_utc(row["date"])
        event_date_str = str(event_ts.normalize().date())

        # Verificar datos diarios para referencia (lookup por fecha normalizada)
        daily_key = daily_by_date_intraday.get(event_ts.normalize())
        if daily_key is None:
            n_omitted += 1
            logger.warning("[_build_intraday] Evento %s no encontrado en OHLCV diario; omitido", event_date_str)
            continue

        # Referencia: open diario de P0
        ref = float(daily_idx.loc[daily_key, "open"])
        if math.isnan(ref) or ref == 0:
            n_omitted += 1
            logger.warning("[_build_intraday] Evento %s tiene open diario inválido (%.4f); omitido", event_date_str, ref)
            continue

        # Clasificar win/loss con datos diarios
        close_p0 = float(daily_idx.loc[daily_key, "close"])
        is_win = (close_p0 - ref) / ref > 0

        # Verificar disponibilidad de datos intradía
        if event_date_str not in available_dates:
            n_omitted += 1
            logger.warning(
                "[_build_intraday] Evento %s sin datos 30min en DataFrame (available_dates=%d); omitido",
                event_date_str, len(available_dates),
            )
            continue

        # Extraer barras del día del evento
        bars = ohlcv_30min[
            ohlcv_30min.index.normalize().tz_convert("UTC") == event_ts.normalize()
        ].sort_index()

        if bars.empty:
            n_omitted += 1
            continue

        # Normalizar cierre de cada barra
        norm = [float(c) / ref * 100.0 for c in bars["close"].tolist()]
        all_series.append(norm)
        if is_win:
            win_series.append(norm)
        else:
            loss_series.append(norm)

    logger.info(
        "[_build_intraday] Resultado: %d eventos procesados, %d omitidos (30min vacíos)",
        len(all_series), n_omitted,
    )

    # Alinear al máximo largo; series cortas se rellenan con NaN.
    # np.nanmean/nanstd ignoran NaN automáticamente en _aggregate_series.
    n_bars = _max_length(all_series)
    all_series  = _pad_to(all_series,  n_bars)
    win_series  = _pad_to(win_series,  n_bars)
    loss_series = _pad_to(loss_series, n_bars)

    # Construir x_labels con timestamps representativos (si hay datos)
    x_labels = _intraday_labels(ohlcv_30min, events_df, n_bars)

    return PriceActionResult(
        anchor_mode="intraday_30min",
        n_periods=0,
        x_labels=x_labels,
        series_all=_aggregate_series(all_series, include_bands),
        series_win=_aggregate_series(win_series, include_bands),
        series_loss=_aggregate_series(loss_series, include_bands),
        n_events_all=len(all_series),
        n_events_win=len(win_series),
        n_events_loss=len(loss_series),
        n_events_omitted=n_omitted,
        warning=_build_warning(
            len(all_series), len(win_series), len(loss_series), n_omitted
        ),
    )


# ---------------------------------------------------------------------------
# Modo daily (n>0)
# ---------------------------------------------------------------------------

def _build_daily(
    events_df: pd.DataFrame,
    ohlcv_daily: pd.DataFrame,
    n_periods: int,
    include_bands: bool,
) -> PriceActionResult:
    daily = ohlcv_daily.sort_index()
    daily_by_date = {ts.normalize(): i for i, ts in enumerate(daily.index)}

    all_series: list[list[float]] = []
    win_series: list[list[float]] = []
    loss_series: list[list[float]] = []

    for _, row in events_df.iterrows():
        event_ts = _to_utc(row["date"])
        pos = daily_by_date.get(event_ts.normalize())
        if pos is None:
            continue

        end_pos = pos + n_periods
        if end_pos >= len(daily):
            continue  # sin suficientes sesiones futuras

        # Referencia: close de P0
        ref = float(daily.iloc[pos]["close"])
        if math.isnan(ref) or ref == 0:
            continue

        # Clasificar win/loss: retorno (close_Pn - close_P0) / close_P0
        close_pn = float(daily.iloc[end_pos]["close"])
        is_win = (close_pn - ref) / ref > 0

        # Normalizar P1 → Pn (P0 excluido)
        norm: list[float] = []
        for offset in range(1, n_periods + 1):
            c = float(daily.iloc[pos + offset]["close"])
            norm.append(c / ref * 100.0)

        all_series.append(norm)
        if is_win:
            win_series.append(norm)
        else:
            loss_series.append(norm)

    x_labels = [f"P{i}" for i in range(1, n_periods + 1)]

    return PriceActionResult(
        anchor_mode="daily",
        n_periods=n_periods,
        x_labels=x_labels,
        series_all=_aggregate_series(all_series, include_bands),
        series_win=_aggregate_series(win_series, include_bands),
        series_loss=_aggregate_series(loss_series, include_bands),
        n_events_all=len(all_series),
        n_events_win=len(win_series),
        n_events_loss=len(loss_series),
        n_events_omitted=0,
        warning=_build_warning(len(all_series), len(win_series), len(loss_series), 0),
    )


# ---------------------------------------------------------------------------
# Helpers de agregación
# ---------------------------------------------------------------------------

def _aggregate_series(series: list[list[float]], include_bands: bool) -> PriceActionSeries:
    """Calcula media(t) y opcionalmente ±1σ sobre una lista de series de igual largo."""
    if not series:
        return PriceActionSeries(points=[], band_upper=None, band_lower=None)

    n_bars = len(series[0])
    mat = np.array(series, dtype=float)  # shape: (n_events, n_bars)

    mean_arr = np.nanmean(mat, axis=0)
    points = [PriceActionPoint(x=i, y=round(float(mean_arr[i]), 4)) for i in range(n_bars)]

    if not include_bands or len(series) < 2:
        return PriceActionSeries(points=points, band_upper=None, band_lower=None)

    std_arr = np.nanstd(mat, axis=0, ddof=1)
    upper = [PriceActionPoint(x=i, y=round(float(mean_arr[i] + std_arr[i]), 4)) for i in range(n_bars)]
    lower = [PriceActionPoint(x=i, y=round(float(mean_arr[i] - std_arr[i]), 4)) for i in range(n_bars)]

    return PriceActionSeries(points=points, band_upper=upper, band_lower=lower)


def _min_length(series: list[list[float]]) -> int:
    """Retorna el mínimo largo de todas las series; 0 si la lista está vacía."""
    if not series:
        return 0
    return min(len(s) for s in series)


def _max_length(series: list[list[float]]) -> int:
    """Retorna el máximo largo de todas las series; 0 si la lista está vacía."""
    if not series:
        return 0
    return max(len(s) for s in series)


def _pad_to(series: list[list[float]], n: int) -> list[list[float]]:
    """Rellena cada serie hasta largo n con float('nan')."""
    return [s + [float("nan")] * (n - len(s)) for s in series]


def _build_warning(
    n_all: int,
    n_win: int,
    n_loss: int,
    n_omitted: int,
) -> str | None:
    if n_all < MIN_EVENTS_PLOT:
        return "insufficient_events"
    if n_omitted > 0:
        return "some_events_omitted"
    return None


def _intraday_labels(
    ohlcv_30min: pd.DataFrame,
    events_df: pd.DataFrame,
    n_bars: int,
) -> list[str]:
    """
    Genera etiquetas de tiempo para las barras de 30min.
    Usa el evento con MÁS barras disponibles como referencia para garantizar
    que el rango completo quede representado en el eje x.
    """
    if ohlcv_30min.empty or events_df.empty or n_bars == 0:
        return [str(i) for i in range(n_bars)]

    best_bars: pd.DataFrame | None = None
    for _, row in events_df.iterrows():
        event_ts = _to_utc(row["date"])
        bars = ohlcv_30min[
            ohlcv_30min.index.normalize().tz_convert("UTC") == event_ts.normalize()
        ].sort_index()
        if not bars.empty and (best_bars is None or len(bars) > len(best_bars)):
            best_bars = bars

    if best_bars is not None:
        labels = [ts.strftime("%H:%M") for ts in best_bars.index[:n_bars]]
        while len(labels) < n_bars:
            labels.append(str(len(labels)))
        return labels

    return [str(i) for i in range(n_bars)]

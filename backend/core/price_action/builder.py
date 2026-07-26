"""
Lógica de alineación, normalización y agregación para el Price Action Plot.

Reglas de diseño:
    - n_periods == 0 → modo intraday (barras de TF intra event)
    - n_periods  > 0 → modo holgind (sesiones P1 → Pn; P0 excluido)
    - Normalización: precio(t) / referencia × 100  (referencia = 100)
    - Clasificación win/loss NO se recalcula aquí: se recibe como `event_signs`
      (dict event_ts -> retorno firmado | None), calculado por
      backend.core.future_returns.compute_future_return_signs — la misma fuente
      que usa build_future_return_metrics (N+/N-) — para que ambos paneles de la
      UI coincidan siempre. Empate (retorno == 0) o sign None → el evento queda
      fuera de win_series/loss_series pero sigue en all_series.
    - Eventos sin datos intradía → omitidos silenciosamente (n_events_omitted)
    - Umbral mínimo MIN_EVENTS_PLOT = 5 (igual que MIN_SAMPLES probabilístico)
"""
from __future__ import annotations

import math
import logging

import numpy as np
import pandas as pd

from backend.api.schemas import (
    DistributionStatsResult,
    DistributionStatsRow,
    PriceActionPoint,
    PriceActionResult,
    PriceActionSeries,
)
from backend.core.utc import to_utc_ts

logger = logging.getLogger(__name__)

MIN_EVENTS_PLOT = 5
MULTI_DAY_TFS = {"1w", "1mo", "3mo", "6mo", "1y"}


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def _get_event_window(
    event_ts: pd.Timestamp,
    outer_timeframe: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Retorna (window_start, window_end) para el período del evento según el outer TF."""
    ts = event_ts.normalize()
    if outer_timeframe == "1mo":
        start = ts.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if outer_timeframe == "1w":
        start = ts - pd.Timedelta(days=ts.dayofweek)  # lunes de la semana
        return start, start + pd.Timedelta(days=7)
    # Para 1d, 4h, 1h, 30m, etc. → ventana = solo el día del evento
    return ts, ts + pd.Timedelta(days=1)


def compute_price_action(
    events_df: pd.DataFrame,
    ohlcv_outer_df: pd.DataFrame,
    ohlcv_event_tf: pd.DataFrame | None,
    n_periods: int,
    event_signs: dict[pd.Timestamp, float | None],
    include_bands: bool = True,
    outer_timeframe: str = "1d",
) -> PriceActionResult:
    """
    Construye el PriceActionResult a partir de los eventos ya condicionados.

    Args:
        events_df:         DataFrame de eventos filtrados (columnas: date, gap_pct …).
        ohlcv_outer_df:    OHLCV diario con DatetimeIndex UTC.
        ohlcv_event_tf: OHLCV del TF del evento con DatetimeIndex UTC; None si n_periods > 0.
        n_periods:         Horizonte (0 = inside event, >0 = holding holding).
        event_signs:       dict event_ts (UTC) -> retorno firmado | None, de
                           backend.core.future_returns.compute_future_return_signs —
                           fuente única de win/loss, compartida con Future Return Metrics.
        include_bands:     Si False, no calcular std; devolver band_upper/lower = None.
        outer_timeframe:   TF del análisis condicionado (ej. "1d", "1mo"). Determina la
                           ventana de barras a extraer en modo inside event.
    """
    if n_periods == 0:
        intraday = ohlcv_event_tf if ohlcv_event_tf is not None else pd.DataFrame()
        return _build_inside_event(events_df, ohlcv_outer_df, intraday, include_bands,
                               event_signs=event_signs, outer_timeframe=outer_timeframe)
    return _build_holding(events_df, ohlcv_outer_df, n_periods, include_bands, event_signs=event_signs)


# ---------------------------------------------------------------------------
#  Modo inside_event (n=0)
# ---------------------------------------------------------------------------

def _build_inside_event(
    events_df: pd.DataFrame,
    ohlcv_outer: pd.DataFrame,
    ohlcv_event_tf: pd.DataFrame,
    include_bands: bool,
    event_signs: dict[pd.Timestamp, float | None],
    outer_timeframe: str = "1d",
) -> PriceActionResult:
    is_multi_day = outer_timeframe in MULTI_DAY_TFS

    outer_idx = ohlcv_outer.sort_index()
    outer_by_date_ts = {ts.normalize(): ts for ts in outer_idx.index}

    # Construir índice de fechas disponibles (solo usado en modo single-day)
    if ohlcv_event_tf.empty:
        event_tf_available_dates: set[str] = set()
    else:
        event_tf_available_dates = {
            str(pd.Timestamp(ts).normalize().date())
            for ts in ohlcv_event_tf.index
        }

    all_series: list[list[float]] = []
    win_series: list[list[float]] = []
    loss_series: list[list[float]] = []
    n_omitted = 0

    for _, row in events_df.iterrows():
        event_ts = to_utc_ts(row["date"])
        event_date_str = str(event_ts.normalize().date())

        if is_multi_day:
            # Ventana completa del período (p.ej. todo el mes para outer=1mo)
            window_start, window_end = _get_event_window(event_ts, outer_timeframe)
            bars = ohlcv_event_tf[
                (ohlcv_event_tf.index >= window_start) &
                (ohlcv_event_tf.index < window_end)
            ].sort_index()

            if bars.empty:
                n_omitted += 1
                logger.warning(
                    "[_build_inside_event] Evento %s sin barras %s en ventana %s→%s; omitido",
                    event_date_str, outer_timeframe,
                    window_start.date(), window_end.date(),
                )
                continue

            # Ref = open del primer día del período
            ref = float(bars["open"].iloc[0])
            if math.isnan(ref) or ref == 0:
                n_omitted += 1
                continue

        else:
            # Caso original: ventana = exactamente el día del evento (30m, etc.)
            daily_key = outer_by_date_ts.get(event_ts.normalize())
            if daily_key is None:
                n_omitted += 1
                logger.warning("[_build_inside_event] Evento %s no encontrado en OHLCV diario; omitido", event_date_str)
                continue

            ref = float(outer_idx.loc[daily_key, "open"])
            if math.isnan(ref) or ref == 0:
                n_omitted += 1
                logger.warning("[_build_inside_event] Evento %s tiene open diario inválido (%.4f); omitido", event_date_str, ref)
                continue

            if event_date_str not in event_tf_available_dates:
                n_omitted += 1
                logger.warning(
                    "[_build_inside_event] Evento %s sin datos 30min en DataFrame (event_tf_available_dates=%d); omitido",
                    event_date_str, len(event_tf_available_dates),
                )
                continue

            bars = ohlcv_event_tf[
                ohlcv_event_tf.index.normalize().tz_convert("UTC") == event_ts.normalize()
            ].sort_index()

            if bars.empty:
                n_omitted += 1
                continue

        norm = [float(c) / ref * 100.0 for c in bars["close"].tolist()]
        all_series.append(norm)
        sign = event_signs.get(event_ts)
        if sign is not None and sign > 0:
            win_series.append(norm)
        elif sign is not None and sign < 0:
            loss_series.append(norm)
        # sign is None (sin dato) o == 0 (empate) → queda solo en all_series

    logger.info(
        "[_build_inside_event] outer_tf=%s | %d eventos procesados, %d omitidos",
        outer_timeframe, len(all_series), n_omitted,
    )

    n_bars = _max_length(all_series)
    all_series  = _pad_to(all_series,  n_bars)
    win_series  = _pad_to(win_series,  n_bars)
    loss_series = _pad_to(loss_series, n_bars)

    x_labels = _inside_event_labels(ohlcv_event_tf, events_df, n_bars, outer_timeframe)

    return PriceActionResult(
        anchor_mode="inside_event",
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
#  Modo holding (n>0)
# ---------------------------------------------------------------------------

def _build_holding(
    events_df: pd.DataFrame,
    ohlcv_outer: pd.DataFrame,
    n_periods: int,
    include_bands: bool,
    event_signs: dict[pd.Timestamp, float | None],
) -> PriceActionResult:
    holding = ohlcv_outer.sort_index()
    outer_by_date_pos = {ts.normalize(): i for i, ts in enumerate(holding.index)}

    all_series: list[list[float]] = []
    win_series: list[list[float]] = []
    loss_series: list[list[float]] = []

    for _, row in events_df.iterrows():
        event_ts = to_utc_ts(row["date"])
        pos = outer_by_date_pos.get(event_ts.normalize())
        if pos is None:
            continue

        end_pos = pos + n_periods
        if end_pos >= len(holding):
            continue  # sin suficientes sesiones futuras

        # Referencia: close de P0
        ref = float(holding.iloc[pos]["close"])
        if math.isnan(ref) or ref == 0:
            continue

        # Normalizar P1 → Pn (P0 excluido)
        norm: list[float] = []
        for offset in range(1, n_periods + 1):
            c = float(holding.iloc[pos + offset]["close"])
            norm.append(c / ref * 100.0)

        all_series.append(norm)
        sign = event_signs.get(event_ts)
        if sign is not None and sign > 0:
            win_series.append(norm)
        elif sign is not None and sign < 0:
            loss_series.append(norm)
        # sign is None (sin dato) o == 0 (empate) → queda solo en all_series

    x_labels = [f"P{i}" for i in range(1, n_periods + 1)]

    return PriceActionResult(
        anchor_mode="holding",
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


def _inside_event_labels(
    ohlcv_event_tf: pd.DataFrame,
    events_df: pd.DataFrame,
    n_bars: int,
    outer_timeframe: str = "1d",
) -> list[str]:
    """
    Genera etiquetas de eje X para el plot inside event.
    - outer_timeframe en ("1w","1mo",...): "D1", "D2", ... (días de trading del período)
    - outer_timeframe == "1d" u otros sub-diarios: "%H:%M" (barras del día)
    """
    # Ventanas multi-día → etiquetas de día
    if outer_timeframe in MULTI_DAY_TFS:
        return [f"D{i + 1}" for i in range(n_bars)]

    # Ventana del día → etiquetas horarias (comportamiento original)
    if ohlcv_event_tf.empty or events_df.empty or n_bars == 0:
        return [str(i) for i in range(n_bars)]

    best_bars: pd.DataFrame | None = None
    for _, row in events_df.iterrows():
        event_ts = to_utc_ts(row["date"])
        bars = ohlcv_event_tf[
            ohlcv_event_tf.index.normalize().tz_convert("UTC") == event_ts.normalize()
        ].sort_index()
        if not bars.empty and (best_bars is None or len(bars) > len(best_bars)):
            best_bars = bars

    if best_bars is not None:
        labels = [ts.strftime("%H:%M") for ts in best_bars.index[:n_bars]]
        while len(labels) < n_bars:
            labels.append(str(len(labels)))
        return labels

    return [str(i) for i in range(n_bars)]


# ---------------------------------------------------------------------------
# Distribución por offset ("Dashboard Quant") — complementa el price action
# ---------------------------------------------------------------------------
#
# Mismos eventos/OHLC y mismo despacho holding/inside-event que
# compute_price_action, pero en vez de agregar una ruta de precio normalizada
# (mean ± 1σ), agrupa por offset la distribución de retornos (percentiles,
# CVaR, skew/kurtosis, reversión alcista/bajista) y clasifica cada offset en
# una fila de tabla con color e ícono. Validado primero en notebook
# (logi_interna.ipynb / complemento.py) antes de portarlo aquí.

DEFAULT_TAIL_Q = 0.05
DEFAULT_CLEAN_Q = 0.25
DEFAULT_PAIN_Q = 0.75


def compute_distribution_stats(
    events_df: pd.DataFrame,
    ohlcv_outer_df: pd.DataFrame,
    ohlcv_event_tf: pd.DataFrame | None,
    n_periods: int,
    outer_timeframe: str = "1d",
    tail_q: float = DEFAULT_TAIL_Q,
    clean_q: float = DEFAULT_CLEAN_Q,
    pain_q: float = DEFAULT_PAIN_Q,
) -> DistributionStatsResult:
    """
    Construye el DistributionStatsResult ("Dashboard Quant") a partir de los mismos
    eventos condicionados que usa compute_price_action.

    Args:
        events_df, ohlcv_outer_df, ohlcv_event_tf, n_periods, outer_timeframe:
            mismo significado que en compute_price_action.
        tail_q:  nivel de cola para CVaR/r_CVaR (0.05 = percentil 5 / 95).
        clean_q, pain_q: cuantiles usados para clasificar los íconos ⚡/⚠️ de forma
            dinámica, sobre la magnitud de las métricas de reversión de cada offset.
    """
    if n_periods == 0:
        intraday = ohlcv_event_tf if ohlcv_event_tf is not None else pd.DataFrame()
        long_df, x_labels, n_omitted = _build_offset_frame_inside_event(
            events_df, ohlcv_outer_df, intraday, outer_timeframe=outer_timeframe
        )
        anchor_mode = "inside_event"
    else:
        long_df, x_labels, n_omitted =_build_offset_frame_holding(
            events_df, ohlcv_outer_df, n_periods
        )
        anchor_mode = "holding"

    n_events_used = max(len(events_df) - n_omitted, 0)
    rows = _aggregate_distribution_rows(long_df, x_labels, tail_q, clean_q, pain_q)

    return DistributionStatsResult(
        anchor_mode=anchor_mode,
        n_periods=n_periods,
        x_labels=x_labels,
        rows=rows,
        n_events_used=n_events_used,
        n_events_omitted=n_omitted,
        warning=_build_warning(n_events_used, n_events_used, 0, n_omitted),
    )


def _build_offset_frame_holding(
    events_df: pd.DataFrame,
    ohlcv_outer: pd.DataFrame,
    n_periods: int,
) -> tuple[pd.DataFrame, list[str], int]:
    """Modo holding: por cada evento, extrae el OHLC crudo (sin normalizar a 100,
    a diferencia de _build_holding) de las sesiones P1→Pn siguientes y calcula sus
    features por-barra en forma larga (una fila por evento×offset)."""
    holding = ohlcv_outer.sort_index()
    outer_by_date_pos = {ts.normalize(): i for i, ts in enumerate(holding.index)}

    rows: list[dict] = []
    n_omitted = 0
    for _, row in events_df.iterrows():
        event_ts = to_utc_ts(row["date"])
        pos = outer_by_date_pos.get(event_ts.normalize())
        if pos is None or pos + n_periods >= len(holding):
            n_omitted += 1
            continue
        for offset in range(1, n_periods + 1):
            bar = holding.iloc[pos + offset]
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            if math.isnan(o) or o == 0:
                continue
            rows.append({
                "offset": offset,
                "returns": (c - o) / o,
                "reversion_alcista": (h - c) / o,
                "reversion_bajista": (c - l) / o,
            })

    x_labels = [f"P{i}" for i in range(1, n_periods + 1)]
    return pd.DataFrame(rows), x_labels, n_omitted


def _build_offset_frame_inside_event(
    events_df: pd.DataFrame,
    ohlcv_outer: pd.DataFrame,
    ohlcv_event_tf: pd.DataFrame,
    outer_timeframe: str = "1d",
) -> tuple[pd.DataFrame, list[str], int]:
    """Modo inside event: por cada evento, recorta las barras dentro de la ventana
    (_get_event_window, igual que _build_inside_event) y calcula las features de cada
    barra individual (sin normalizar a 100), en forma larga (evento×posición)."""
    is_multi_day = outer_timeframe in MULTI_DAY_TFS
    outer_idx = ohlcv_outer.sort_index()
    outer_by_date_pos = {ts.normalize(): ts for ts in outer_idx.index}
    event_tf_available_dates = (
        {str(pd.Timestamp(ts).normalize().date()) for ts in ohlcv_event_tf.index}
        if not ohlcv_event_tf.empty else set()
    )

    bar_windows: list[pd.DataFrame] = []
    n_omitted = 0

    for _, row in events_df.iterrows():
        event_ts = to_utc_ts(row["date"])
        event_date_str = str(event_ts.normalize().date())

        if is_multi_day:
            window_start, window_end = _get_event_window(event_ts, outer_timeframe)
            bars = ohlcv_event_tf[
                (ohlcv_event_tf.index >= window_start) & (ohlcv_event_tf.index < window_end)
            ].sort_index()
            if bars.empty:
                n_omitted += 1
                continue
        else:
            daily_key = outer_by_date_pos.get(event_ts.normalize())
            if daily_key is None or event_date_str not in event_tf_available_dates:
                n_omitted += 1
                continue
            bars = ohlcv_event_tf[
                ohlcv_event_tf.index.normalize().tz_convert("UTC") == event_ts.normalize()
            ].sort_index()
            if bars.empty:
                n_omitted += 1
                continue

        bar_windows.append(bars)

    n_bars = max((len(bars) for bars in bar_windows), default=0)

    rows: list[dict] = []
    for bars in bar_windows:
        for position, (_, bar) in enumerate(bars.iterrows()):
            o, h, l, c = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            if math.isnan(o) or o == 0:
                continue
            rows.append({
                "offset": position + 1,
                "returns": (c - o) / o,
                "reversion_alcista": (h - c) / o,
                "reversion_bajista": (c - l) / o,
            })

    x_labels = _inside_event_labels(ohlcv_event_tf, events_df, n_bars, outer_timeframe)
    return pd.DataFrame(rows), x_labels, n_omitted


def _aggregate_distribution_rows(
    long_df: pd.DataFrame,
    x_labels: list[str],
    tail_q: float,
    clean_q: float,
    pain_q: float,
) -> list[DistributionStatsRow]:
    """Agrupa long_df por offset y produce una fila por offset con percentiles,
    CVaR, skew/kurtosis, reversión, y clasificación de color/ícono. Los umbrales
    de ícono son dinámicos (cuantiles clean_q/pain_q de la magnitud de la
    reversión), no valores fijos — se auto-adaptan a la escala real de los datos."""
    if long_df.empty:
        return []

    def _q(p: float):
        return lambda x: x.quantile(p)

    def _cvar_low(q: float):
        def f(x: pd.Series) -> float:
            thresh = x.quantile(q)
            return x[x < thresh].mean()
        return f

    def _cvar_high(q: float):
        def f(x: pd.Series) -> float:
            thresh = x.quantile(1 - q)
            return x[x > thresh].mean()
        return f

    stats = long_df.groupby("offset").agg(
        n_obs=("returns", "size"),
        ret_mean=("returns", "mean"),
        ret_p25=("returns", _q(0.25)),
        ret_p75=("returns", _q(0.75)),
        cvar=("returns", _cvar_low(tail_q)),
        r_cvar=("returns", _cvar_high(tail_q)),
        asimetria=("returns", "skew"),
        curtosis=("returns", lambda x: x.kurtosis()),
        rev_alcista_mean=("reversion_alcista", "mean"),
        rev_alcista_p75=("reversion_alcista", _q(0.75)),
        rev_bajista_mean=("reversion_bajista", "mean"),
        rev_bajista_p25=("reversion_bajista", _q(0.25)),
    )
    cvar_safe = np.where(stats["cvar"] == 0, 1e-9, stats["cvar"])
    stats["ratio_colas"] = np.abs(stats["r_cvar"]) / np.abs(cvar_safe)

    # Umbrales dinámicos calculados solo sobre offsets con muestra suficiente,
    # para que un par de columnas ruidosas (n_obs bajo) no distorsionen el
    # corte ⚡/⚠️ del resto de la tabla.
    well_sampled = stats[stats["n_obs"] >= MIN_EVENTS_PLOT]
    mag_bajista = (well_sampled["rev_bajista_p25"] if not well_sampled.empty else stats["rev_bajista_p25"]).abs()
    mag_alcista = (well_sampled["rev_alcista_p75"] if not well_sampled.empty else stats["rev_alcista_p75"]).abs()
    umbral_limpio_bajista = mag_bajista.quantile(clean_q)
    umbral_dolor_bajista = mag_bajista.quantile(pain_q)
    umbral_limpio_alcista = mag_alcista.quantile(clean_q)
    umbral_dolor_alcista = mag_alcista.quantile(pain_q)

    rows: list[DistributionStatsRow] = []
    for offset in stats.index:
        n_obs = int(stats.loc[offset, "n_obs"])
        ret_mean = float(stats.loc[offset, "ret_mean"])
        ret_p25 = float(stats.loc[offset, "ret_p25"])
        ret_p75 = float(stats.loc[offset, "ret_p75"])
        ratio = float(stats.loc[offset, "ratio_colas"])
        asim = float(stats.loc[offset, "asimetria"])
        rev_bajista_p25 = float(stats.loc[offset, "rev_bajista_p25"])
        rev_alcista_p75 = float(stats.loc[offset, "rev_alcista_p75"])

        # Con menos de MIN_EVENTS_PLOT observaciones, percentiles/CVaR/skew son
        # ruido (ver ejemplo real: ratio_colas disparado por un CVaR casi-cero
        # calculado sobre 2-3 puntos) — no clasificar con confianza ese offset.
        if n_obs < MIN_EVENTS_PLOT:
            color_base, icon = "blanco", ""
        else:
            color_base = _classify_color(ret_mean, ret_p25, ret_p75, ratio, asim)
            icon = _classify_icon(
                color_base, rev_bajista_p25, rev_alcista_p75,
                umbral_limpio_bajista, umbral_dolor_bajista,
                umbral_limpio_alcista, umbral_dolor_alcista,
            )
        label = x_labels[offset - 1] if 1 <= offset <= len(x_labels) else str(offset)

        rows.append(DistributionStatsRow(
            offset=int(offset),
            label=label,
            n_obs=n_obs,
            ret_mean=ret_mean,
            ret_p25=ret_p25,
            ret_p75=ret_p75,
            cvar=float(stats.loc[offset, "cvar"]),
            r_cvar=float(stats.loc[offset, "r_cvar"]),
            asimetria=asim,
            curtosis=float(stats.loc[offset, "curtosis"]),
            rev_alcista_mean=float(stats.loc[offset, "rev_alcista_mean"]),
            rev_alcista_p75=rev_alcista_p75,
            rev_bajista_mean=float(stats.loc[offset, "rev_bajista_mean"]),
            rev_bajista_p25=rev_bajista_p25,
            ratio_colas=ratio,
            color_base=color_base,
            icon=icon,
        ))
    return rows


def _classify_color(
    ret_mean: float, ret_p25: float, ret_p75: float, ratio: float, asim: float,
) -> str:
    """Clasificación direccional/riesgo de cola de un offset (azul/amarillo/coral/blanco)."""
    if ret_mean > 0 and ratio > 1.2 and asim > 0:
        return "azul"
    if ret_mean < 0 and ratio < 0.83 and asim < 0:
        return "amarillo"
    if ((ret_mean > 0 or ret_p25 > 0) and ratio < 0.83) or ((ret_mean < 0 or ret_p75 < 0) and ratio > 1.2):
        return "coral"
    return "blanco"


def _classify_icon(
    color_base: str,
    rev_bajista_p25: float,
    rev_alcista_p75: float,
    umbral_limpio_bajista: float,
    umbral_dolor_bajista: float,
    umbral_limpio_alcista: float,
    umbral_dolor_alcista: float,
) -> str:
    """Ícono de ejecución (⚡ limpio / ⚠️ doloroso / 🔄 choppy) según la magnitud
    de la reversión relevante al color base, contra los umbrales dinámicos."""
    if color_base == "azul":
        if abs(rev_bajista_p25) <= umbral_limpio_bajista:
            return "⚡"
        if abs(rev_bajista_p25) >= umbral_dolor_bajista:
            return "⚠️"
    elif color_base == "amarillo":
        if abs(rev_alcista_p75) <= umbral_limpio_alcista:
            return "⚡"
        if abs(rev_alcista_p75) >= umbral_dolor_alcista:
            return "⚠️"
    elif color_base == "blanco":
        if abs(rev_alcista_p75) >= umbral_dolor_alcista and abs(rev_bajista_p25) >= umbral_dolor_bajista:
            return "🔄"
    return ""

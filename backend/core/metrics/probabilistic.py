"""
Métricas probabilísticas: calcula las familias de escenarios usando
el modelo estadístico seleccionado.

Assumptions:
    - events_df ya está filtrado por condicionamiento (responsabilidad del router)
    - events_df tiene columnas de retorno forward calculadas aquí o por el caller
    - Eventos al final de la serie sin N sesiones completas -> excluidos de n_samples_used
    - n_samples_used se reporta por familia (puede diferir en gap_fill)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.api.schemas import ModelType, ProbabilisticFamily, ProbabilisticResult
from backend.core.statistical_models.base import BaseEventModel


def compute_probabilistic_metrics(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    model: BaseEventModel,
    model_type: ModelType,
    n_periods: int,
    bins: list[float],
    symbol: str,
    data_source: str,
    data_source_detail: str | None = None,
) -> ProbabilisticResult:
    """
    Calcula ProbabilisticResult con familias de métricas.

    Flujo:
        1. Calcular columnas de retorno forward para n_periods sobre ohlcv_df + events_df
        2. Excluir eventos sin n sesiones completas disponibles
        3. Ajustar modelo con eventos válidos
        4. Predecir cada familia
        5. Construir ProbabilisticResult con las ProbabilisticFamily

    Retorna siempre exactamente 2 familias en el orden:
        ["close_return", "gap_fill"]
    """
    enriched = _build_forward_returns(events_df, ohlcv_df, n_periods)
    gap_fill_col = _compute_gap_fill_column(enriched, ohlcv_df, n_periods)
    enriched = enriched.copy()
    enriched[f"gap_fill_p{n_periods}"] = gap_fill_col
    # Para reutilizar modelos existentes en gap_fill, se expone también como retorno continuo 0/1.
    enriched[f"ret_gap_fill_p{n_periods}"] = gap_fill_col

    n_total_events = len(enriched)

    valid_for_fit = enriched[
        enriched[[f"ret_close_p{n_periods}", f"ret_gap_fill_p{n_periods}"]]
        .notna()
        .any(axis=1)
    ].copy()

    model.fit(valid_for_fit)

    close_scenarios = model.predict_close_scenarios(n_periods=n_periods, bins=bins)
    gap_fill_scenarios = model.predict_gap_fill_scenarios(
        n_periods=n_periods,
        bins=[0.5],
    )

    n_close = int(enriched[f"ret_close_p{n_periods}"].notna().sum())
    n_gap = int(enriched[f"ret_gap_fill_p{n_periods}"].notna().sum())
    has_any_gap_event = bool((enriched["gap_pct"].fillna(0.0) != 0.0).any())

    close_warning = model._check_insufficient_samples(n_close)

    # Prioridad requerida: insufficient_samples > no_gap_events
    gap_warning = model._check_insufficient_samples(n_gap)
    if gap_warning is None and not has_any_gap_event:
        gap_warning = "no_gap_events"

    families = [
        ProbabilisticFamily(
            family="close_return",
            n_periods=n_periods,
            n_samples_used=n_close,
            n_total_events=n_total_events,
            warning=close_warning,
            scenarios=close_scenarios,
        ),
        ProbabilisticFamily(
            family="gap_fill",
            n_periods=n_periods,
            n_samples_used=n_gap,
            n_total_events=n_total_events,
            warning=gap_warning,
            scenarios=gap_fill_scenarios,
        ),
    ]

    return ProbabilisticResult(
        symbol=symbol,
        model=model_type,
        data_source=data_source,
        data_source_detail=data_source_detail,
        families=families,
    )


def _build_forward_returns(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_periods: int,
) -> pd.DataFrame:
    """
    Agrega columnas de retorno forward a events_df:
        ret_close_p{n_periods}:
            - n_periods == 0 -> (close_P0 - open_P0) / open_P0
            - n_periods > 0  -> (close_Pn - close_P0) / close_P0
        open_p0: open de la sesión del evento
        close_p0: close de la sesión del evento
        prev_close: close_{T-1} (para gap_fill)

    Filas sin n sesiones completas disponibles -> NaN en columnas de retorno.
    No modifica events_df (retorna copia con columnas adicionales).
    """
    out = events_df.copy()
    out = out.reset_index(drop=True)

    ret_close_col = f"ret_close_p{n_periods}"
    out[ret_close_col] = np.nan
    out["open_p0"] = np.nan
    out["close_p0"] = np.nan
    out["prev_close"] = np.nan

    if out.empty or ohlcv_df.empty or "date" not in out.columns:
        return out

    df = ohlcv_df.sort_index()
    date_to_pos = _build_date_position_map(df.index)

    for i, event_row in out.iterrows():
        ts = pd.Timestamp(event_row["date"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        pos = date_to_pos.get(ts.normalize())
        if pos is None:
            continue

        if pos == 0:
            continue

        end_pos = pos + n_periods
        if end_pos >= len(df):
            continue

        open_p0 = float(df["open"].iloc[pos])
        close_p0 = float(df["close"].iloc[pos])
        close_pn = float(df["close"].iloc[end_pos])
        prev_close = float(df["close"].iloc[pos - 1])

        if open_p0 == 0.0:
            continue
        if n_periods > 0 and close_p0 == 0.0:
            continue

        out.at[i, "open_p0"] = open_p0
        out.at[i, "close_p0"] = close_p0
        out.at[i, "prev_close"] = prev_close
        if n_periods == 0:
            out.at[i, ret_close_col] = (close_pn - open_p0) / open_p0
        else:
            out.at[i, ret_close_col] = (close_pn - close_p0) / close_p0

    return out


def _compute_gap_fill_column(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_periods: int,
) -> pd.Series:
    """
    Para cada evento con gap_pct != 0, determina si el precio llenó el gap.

    Definición de gap fill:
        El gap queda abierto entre prev_close (close de P-1) y el open de P0.
        Se considera llenado cuando el precio alcanza el nivel de prev_close,
        ya sea intraday (via low/high) o al cierre.

    Condición de llenado por signo de gap:
        Gap UP   (gap_pct > 0): low <= prev_close  ó  close <= prev_close
        Gap DOWN (gap_pct < 0): high >= prev_close ó  close >= prev_close

    Ventana evaluada:
        n_periods == 0 → sólo P0 (¿cerró el gap el mismo día?)
        n_periods >  0 → P0..Pn inclusive (cualquier sesión del horizonte)

    gap_fill = NaN si gap_pct == 0 o sin sesiones disponibles.
    Retorna Serie de float (0.0 / 1.0 / NaN) indexada como events_df.
    """
    result = pd.Series(np.nan, index=events_df.index, dtype=float)

    if events_df.empty or ohlcv_df.empty or "date" not in events_df.columns:
        return result

    df = ohlcv_df.sort_index()
    date_to_pos = _build_date_position_map(df.index)

    for i, event_row in events_df.iterrows():
        gap_pct = event_row.get("gap_pct")
        if gap_pct is None or pd.isna(gap_pct) or float(gap_pct) == 0.0:
            continue

        ts = pd.Timestamp(event_row["date"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")

        pos = date_to_pos.get(ts.normalize())
        if pos is None or pos == 0:
            continue

        end_pos = pos + n_periods
        if end_pos >= len(df):
            continue

        prev_close = float(df["close"].iloc[pos - 1])
        if prev_close == 0.0:
            continue

        # n_periods=0 → verificar si el gap cierra dentro de la misma sesión (P0)
        # n_periods>0 → verificar sesiones P1..Pn (post-evento)
        if n_periods == 0:
            window = df.iloc[pos : pos + 1]
        else:
            window = df.iloc[pos + 1 : end_pos + 1]

        if window.empty:
            continue

        gap_is_up = float(gap_pct) > 0.0
        if gap_is_up:
            # Gap UP: llenado si el precio baja hasta prev_close (via low o close)
            filled = bool(
                (window["low"] <= prev_close).any()
                or (window["close"] <= prev_close).any()
            )
        else:
            # Gap DOWN: llenado si el precio sube hasta prev_close (via high o close)
            filled = bool(
                (window["high"] >= prev_close).any()
                or (window["close"] >= prev_close).any()
            )

        result.at[i] = 1.0 if filled else 0.0

    return result


def _build_date_position_map(index: pd.DatetimeIndex) -> dict[pd.Timestamp, int]:
    """Mapa fecha-normalizada-UTC -> posición en índice OHLCV."""
    pos_map: dict[pd.Timestamp, int] = {}
    for i, ts in enumerate(index):
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        pos_map[ts.normalize()] = i
    return pos_map

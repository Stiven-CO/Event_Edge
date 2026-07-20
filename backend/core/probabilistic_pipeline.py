"""
Pipeline 3 — Aplicación de modelos.

Recibe datasets ya construidos y condicionados (por Pipeline 2) y produce las
métricas probabilísticas — no carga datos ni construye features. Movido desde
backend/api/routers/analysis.py (vivía en un router por accidente histórico;
persistence.py llegó a importar la función del router directamente para
reutilizar esta lógica, un antipatrón que este módulo elimina).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
from fastapi import HTTPException
from scipy import stats as scipy_stats

from backend.api.schemas import (
    AnalysisRequest,
    ConditionedBar,
    ConditionedSummary,
    EventType,
    FutureReturnMetrics,
    ModelType,
    ProbabilisticResult,
)
from backend.config import Settings
from backend.core import data_pipeline
from backend.core.utc import to_utc_ts
from backend.core.conditioning_pipeline import build_conditioned_dataset
from backend.core.metrics import compute_probabilistic_metrics
from backend.core.statistical_models import (
    BaseEventModel,
    BayesianModel,
    BootstrapModel,
    FrequentistModel,
    KDEModel,
)

logger = logging.getLogger(__name__)


def build_model(model_type: ModelType) -> BaseEventModel:
    if model_type == ModelType.frequentist:
        return FrequentistModel()
    if model_type == ModelType.bootstrap:
        return BootstrapModel()
    if model_type == ModelType.kde:
        return KDEModel()
    if model_type == ModelType.bayesian:
        return BayesianModel()
    return BootstrapModel()


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def _enum_val(v) -> str | None:
    if v is None:
        return None
    return getattr(v, "value", str(v)) if v is not None else None


def _safe_int(v) -> int | None:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def row_to_bar(row) -> ConditionedBar:
    te = row.get("take_earnings")
    return ConditionedBar(
        # Identidad
        date=str(row.get("date", ""))[:10],
        event_type=_enum_val(row.get("event_type")),
        symbol=str(row.get("symbol")) if row.get("symbol") is not None else None,
        # Base cruda (OHLCV)
        open=_safe_float(row.get("open")),
        high=_safe_float(row.get("high")),
        low=_safe_float(row.get("low")),
        close=_safe_float(row.get("close")),
        volume=_safe_float(row.get("volume")),
        # Base cruda (Earnings)
        eps_actual=_safe_float(row.get("eps_actual")),
        eps_estimate=_safe_float(row.get("eps_estimate")),
        surprise_pct=_safe_float(row.get("surprise_pct")),
        revenue_actual=_safe_float(row.get("revenue_actual")),
        revenue_estimate=_safe_float(row.get("revenue_estimate")),
        # F - Posicionamiento
        gap_pct=_safe_float(row.get("gap_pct")),
        # A - Tendencia
        ema5_vs_ema20_ratio=_safe_float(row.get("ema5_vs_ema20_ratio")),
        price_vs_ema50_pct=_safe_float(row.get("price_vs_ema50_pct")),
        trend_direction=_enum_val(row.get("trend_direction")),
        # B - Momentum
        return_5p=_safe_float(row.get("return_5p")),
        return_20p=_safe_float(row.get("return_20p")),
        rsi14=_safe_float(row.get("rsi14")),
        # C - Sobreextensión
        bb_position=_enum_val(row.get("bb_position")),
        bb_width_pct=_safe_float(row.get("bb_width_pct")),
        rsi14_zone=_enum_val(row.get("rsi14_zone")),
        # D - Volatilidad
        hist_vol_10d=_safe_float(row.get("hist_vol_10d")),
        vol_ratio_10_30=_safe_float(row.get("vol_ratio_10_30")),
        atr_pct=_safe_float(row.get("atr_pct")),
        vol_regime=_enum_val(row.get("vol_regime")),
        # E - Fundamental
        take_earnings=bool(te) if te is not None else None,
        eps_surprise_pct=_safe_float(row.get("eps_surprise_pct")),
        # E - Fundamental expandido (backward/forward-fill)
        eps_actual_ffill=_safe_float(row.get("eps_actual_ffill")),
        reported_eps_trend=_safe_int(row.get("reported_eps_trend")),
        eps_estimate_ffill=_safe_float(row.get("eps_estimate_ffill")),
        eps_estimate_trend=_safe_int(row.get("eps_estimate_trend")),
        eps_surprise_pct_ffill=_safe_float(row.get("eps_surprise_pct_ffill")),
        # G - Estacionalidad
        day_of_week=_enum_val(row.get("day_of_week")),
        month=_enum_val(row.get("month")),
        quarter=_enum_val(row.get("quarter")),
        earnings_season=_enum_val(row.get("earnings_season")),
    )


def _s(arr: list[float]) -> tuple[float | None, float | None]:
    """Media y desvío estándar (ddof=1) de una lista de floats; (None, None) si vacía."""
    if not arr:
        return None, None
    a = np.array(arr, dtype=float)
    return float(np.mean(a)), float(np.std(a, ddof=1)) if len(a) > 1 else 0.0


def _extended_stats(arr: list[float]) -> dict:
    if not arr:
        return {
            "max": None, "min": None,
            "avg_positive": None, "avg_negative": None,
            "count_positive": 0, "count_negative": 0,
            "skewness": None, "kurtosis": None,
        }
    a = np.array(arr, dtype=float)
    pos = a[a > 0]
    neg = a[a < 0]
    return {
        "max": float(np.max(a)),
        "min": float(np.min(a)),
        "avg_positive": float(np.mean(pos)) if pos.size > 0 else None,
        "avg_negative": float(np.mean(neg)) if neg.size > 0 else None,
        "count_positive": int(pos.size),
        "count_negative": int(neg.size),
        "skewness": float(scipy_stats.skew(a)) if a.size >= 3 else None,
        "kurtosis": float(scipy_stats.kurtosis(a)) if a.size >= 4 else None,
    }


def build_conditioned_summary(
    conditioned_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_total_events: int,
    n_periods: int,
) -> ConditionedSummary:
    """
    Construye ConditionedSummary — estadísticas del EVENTO condicionado (día P0):
    frecuencia, gap, comportamiento del propio día del evento.

    No incluye métricas de retorno posterior (P1→Pn) — ver build_future_return_metrics.
    No accede a fuentes externas. Deriva todo de conditioned_df + ohlcv_df.
    """
    n_cond = len(conditioned_df)

    if n_total_events == 0 or n_cond == 0:
        return ConditionedSummary(
            n_conditioned_events=n_cond,
            n_total_events=n_total_events,
            filter_rate=0.0,
            frequency_per_year=0.0,
            frequency_per_quarter=0.0,
            gap_mean=None, gap_std=None,
            event_day_range_mean=None, event_day_range_std=None,
            event_day_volume_mean=None, event_day_volume_std=None,
            event_day_return_mean=None, event_day_return_std=None,
            return_samples_gap=[],
        )

    filter_rate = n_cond / n_total_events if n_total_events > 0 else 0.0

    # Frecuencia
    delta_days = (ohlcv_df.index.max() - ohlcv_df.index.min()).days
    n_years = delta_days / 365.25 if delta_days > 0 else 1.0
    frequency_per_year    = n_cond / n_years
    frequency_per_quarter = frequency_per_year / 4.0

    # Gap stats
    gap_vals = conditioned_df["gap_pct"].dropna().tolist()
    gap_vals = [float(v) for v in gap_vals if v != 0.0]
    gap_mean = float(np.mean(gap_vals)) if gap_vals else None
    gap_std  = float(np.std(gap_vals, ddof=1)) if len(gap_vals) > 1 else None

    # Estadísticas del día del evento (P0) — derivadas de ohlcv
    df = ohlcv_df.sort_index()
    trading_dates = df.index
    _has_volume = "volume" in df.columns

    ranges: list[float] = []
    volumes: list[float] = []
    ev_returns: list[float] = []

    for ts in conditioned_df["date"]:
        ts_utc = to_utc_ts(ts)
        loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
        if loc < 0:
            continue
        found = trading_dates[loc].normalize()
        if found != ts_utc.normalize():
            continue
        row_high  = float(df["high"].iloc[loc])
        row_low   = float(df["low"].iloc[loc])
        row_open  = float(df["open"].iloc[loc])
        row_close = float(df["close"].iloc[loc])
        if row_close > 0 and not (np.isnan(row_close) or np.isnan(row_open)):
            ranges.append((row_high - row_low) / row_close)
            ev_returns.append((row_close - row_open) / row_open)
        if _has_volume:
            vol = df["volume"].iloc[loc]
            if not np.isnan(float(vol)):
                volumes.append(float(vol))

    range_mean, range_std   = _s(ranges)
    vol_mean, vol_std       = _s(volumes)
    ret_mean, ret_std       = _s(ev_returns)

    return_samples_gap = [float(v) for v in conditioned_df["gap_pct"].dropna() if v != 0.0]

    return ConditionedSummary(
        n_conditioned_events=n_cond,
        n_total_events=n_total_events,
        filter_rate=filter_rate,
        frequency_per_year=frequency_per_year,
        frequency_per_quarter=frequency_per_quarter,
        gap_mean=gap_mean,
        gap_std=gap_std,
        event_day_range_mean=range_mean,
        event_day_range_std=range_std,
        event_day_volume_mean=vol_mean,
        event_day_volume_std=vol_std,
        event_day_return_mean=ret_mean,
        event_day_return_std=ret_std,
        return_samples_gap=return_samples_gap,
    )


def build_future_return_metrics(
    conditioned_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_total_events: int,
    n_periods: int,
    price_action_mode: str = "holding",
) -> FutureReturnMetrics:
    """
    Construye FutureReturnMetrics.

    Modo `holding`: estadísticas del RETORNO POSTERIOR al evento condicionado
    (P1-open → Pn-close, al período elegido por el usuario) — hay un "futuro"
    real que medir.

    Modo `in_event`: no existe un retorno posterior con sentido (el análisis
    vive dentro del propio día del evento) — las estadísticas extendidas y las
    muestras crudas se calculan sobre el retorno del propio día del evento
    (P0 open → close), misma referencia que
    ConditionedSummary.event_day_return_mean/std.

    En ambos modos, `avg_forward_return` (tabla de períodos fijos 1/3/5/10)
    se calcula igual — es una referencia informativa independiente del modo.

    No incluye información del evento en sí (día P0) — ver build_conditioned_summary.
    No accede a fuentes externas. Deriva todo de conditioned_df + ohlcv_df.
    """
    n_cond = len(conditioned_df)

    if n_total_events == 0 or n_cond == 0:
        return FutureReturnMetrics(
            n_periods=n_periods,
            avg_forward_return={},
            return_max=None, return_min=None,
            return_avg_positive=None, return_avg_negative=None,
            return_count_positive=0, return_count_negative=0,
            return_skewness=None, return_kurtosis=None,
            return_samples_close=[],
        )

    df = ohlcv_df.sort_index()
    trading_dates = df.index

    # Forward returns condicionados — períodos fijos [1, 3, 5, 10] (igual en ambos modos)
    fixed_periods = [1, 3, 5, 10]
    avg_forward_return: dict[int, dict] = {}
    for per in fixed_periods:
        fwd: list[float] = []
        for ts in conditioned_df["date"]:
            ts_utc = to_utc_ts(ts)
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0 or loc + per >= len(df):
                continue
            open_p1  = float(df["open"].iloc[loc + 1])
            close_pn = float(df["close"].iloc[loc + per])
            if open_p1 > 0 and not (np.isnan(open_p1) or np.isnan(close_pn)):
                fwd.append((close_pn - open_p1) / open_p1)
        fwd_mean, fwd_std = _s(fwd)
        avg_forward_return[per] = {"mean": fwd_mean or 0.0, "std": fwd_std or 0.0}

    return_samples: list[float] = []
    if price_action_mode == "in_event":
        # Retorno del propio día del evento (P0 open → close) — no hay "futuro" en este modo
        for ts in conditioned_df["date"]:
            ts_utc = to_utc_ts(ts)
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0:
                continue
            found = trading_dates[loc].normalize()
            if found != ts_utc.normalize():
                continue
            row_open  = float(df["open"].iloc[loc])
            row_close = float(df["close"].iloc[loc])
            if row_open > 0 and not (np.isnan(row_open) or np.isnan(row_close)):
                return_samples.append((row_close - row_open) / row_open)
    else:
        # holding: retorno posterior P1-open → Pn-close, al período elegido
        actual_period = max(1, n_periods)
        for ts in conditioned_df["date"]:
            ts_utc = to_utc_ts(ts)
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0 or loc + actual_period >= len(df):
                continue
            open_p1  = float(df["open"].iloc[loc + 1])
            close_pn = float(df["close"].iloc[loc + actual_period])
            if open_p1 > 0 and not (np.isnan(open_p1) or np.isnan(close_pn)):
                return_samples.append((close_pn - open_p1) / open_p1)

    ext = _extended_stats(return_samples)

    return FutureReturnMetrics(
        n_periods=n_periods,
        avg_forward_return=avg_forward_return,
        return_max=ext["max"],
        return_min=ext["min"],
        return_avg_positive=ext["avg_positive"],
        return_avg_negative=ext["avg_negative"],
        return_count_positive=ext["count_positive"],
        return_count_negative=ext["count_negative"],
        return_skewness=ext["skewness"],
        return_kurtosis=ext["kurtosis"],
        return_samples_close=return_samples,
    )


def run_probabilistic_analysis(req: AnalysisRequest, settings: Settings) -> ProbabilisticResult:
    """
    Orquesta Pipeline 1 (carga) → Pipeline 2 (features+condicionamiento) →
    Pipeline 3 (modelo+métricas) para producir un ProbabilisticResult completo.

    Único punto de esta orquestación — usado por el endpoint
    POST /analysis/probabilistic y por persistence.py (save_edge), que antes
    llamaba directamente a la función del router (antipatrón).

    Lanza HTTPException(404) si no hay OHLCV disponible en el lake.
    """
    ohlcv_df, source_used = data_pipeline.load_ohlcv(
        settings=settings,
        symbol=req.symbol,
        source=req.source,
        asset_class=req.asset_class,
        date_start=req.date_range_start,
        date_end=req.date_range_end,
        ohlcv_source=req.ohlcv_source,
        timeframe=req.timeframe,
    )
    if ohlcv_df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No OHLCV data available for {req.symbol}",
        )

    is_fundamental = (req.event_type == EventType.earnings)
    earnings_df = None
    if is_fundamental:
        earnings_df, earnings_info = data_pipeline.fetch_earnings_safe(settings, req.symbol, req.source)
        logger.info("[probabilistic] %s | OHLCV: %d barras | %s", req.symbol, len(ohlcv_df), earnings_info)

    conditioned_df, n_total, _ = build_conditioned_dataset(
        ohlcv_df=ohlcv_df,
        earnings_df=earnings_df,
        event_type=req.event_type,
        conditioning=req.conditioning,
        symbol=req.symbol,
        timeframe=req.timeframe,
        date_start=req.date_range_start,
        date_end=req.date_range_end,
    )
    logger.info("[probabilistic] %s | condicionados: %d / %d", req.symbol, len(conditioned_df), n_total)

    model = build_model(req.model)
    result = compute_probabilistic_metrics(
        events_df=conditioned_df,
        ohlcv_df=ohlcv_df,
        model=model,
        model_type=req.model,
        n_periods=req.n_periods,
        bins=req.bins,
        symbol=req.symbol,
        data_source=source_used,
        data_source_detail=None,
    )

    result.conditioned_summary = build_conditioned_summary(
        conditioned_df=conditioned_df,
        ohlcv_df=ohlcv_df,
        n_total_events=n_total,
        n_periods=req.n_periods,
    )
    result.future_return_metrics = build_future_return_metrics(
        conditioned_df=conditioned_df,
        ohlcv_df=ohlcv_df,
        n_total_events=n_total,
        n_periods=req.n_periods,
        price_action_mode=req.price_action_mode,
    )
    return result

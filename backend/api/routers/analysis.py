from __future__ import annotations

import logging
import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

import numpy as np

logger = logging.getLogger(__name__)
from backend.api.schemas import (
    AnalysisRequest,
    ConditionedBar,
    ConditionedSummary,
    ConditioningCountRequest,
    ConditioningCountResult,
    ConditioningParams,
    EventType,
    GlobalInformativeMetrics,
    GlobalInformativeRequest,
    ModelType,
    ProbabilisticResult,
)
from backend.config import Settings, get_settings
from backend.core.feature_builder import FeatureBuilder
from backend.core.metrics import compute_global_metrics, compute_probabilistic_metrics
from backend.core.statistical_models import (
    BaseEventModel,
    BayesianModel,
    BootstrapModel,
    FrequentistModel,
    KDEModel,
)
from backend.data import MdhClient, MdhUnavailableError, MdhValidationError, empty_earnings_df

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
    return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.post(
    "/informative",
    response_model=GlobalInformativeMetrics,
    summary="Línea base estadística del activo",
    description=(
        "Calcula métricas globales del activo sobre el historial completo: "
        "distribución de retornos, estadística descriptiva, volatilidad, "
        "Hurst exponent y autocorrelaciones. No requiere eventos."
    ),
)
async def informative_analysis(
    req: GlobalInformativeRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> GlobalInformativeMetrics:
    try:
        ohlcv_df, source_used = await _load_ohlcv(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            mdh_client=mdh_client,
            ohlcv_source=req.ohlcv_source,
        )
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        return compute_global_metrics(
            ohlcv_df=ohlcv_df,
            symbol=req.symbol,
            data_source=source_used,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en informative_analysis [%s]", req.symbol)
        if settings.debug:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/probabilistic",
    response_model=ProbabilisticResult,
    summary="Métricas probabilísticas",
    description="Calcula escenarios probabilísticos para close_return y gap_fill.",
)
async def probabilistic_analysis(
    req: AnalysisRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> ProbabilisticResult:
    feature_builder = FeatureBuilder()

    try:
        ohlcv_df, source_used = await _load_ohlcv(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            mdh_client=mdh_client,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
            ohlcv_source=req.ohlcv_source,
            credentials_account=req.credentials_account,
        )
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        # Path fundamental: carga OHLCV + earnings, construye dataset completo con máscara take_earnings
        # Path OHLCV-all-bars: construye features para todas las barras; condicionamiento define los eventos
        is_fundamental = (req.event_type == EventType.earnings)

        if is_fundamental:
            earnings_df, earnings_info = await _fetch_earnings_safe(req.symbol, mdh_client)
            logger.info("[probabilistic] %s | OHLCV: %d barras | %s", req.symbol, len(ohlcv_df), earnings_info)
            features_df = feature_builder.build_from_fundamental_context(
                ohlcv_df, earnings_df, symbol=req.symbol
            )
            features_df = _filter_features_by_date(features_df, req.date_range_start, req.date_range_end)
            n_total = len(features_df)
            n_earning_days = int(features_df["take_earnings"].sum()) if not features_df.empty else 0
            logger.info("[probabilistic] %s | features: %d filas | earning days: %d", req.symbol, n_total, n_earning_days)
        else:
            features_df = feature_builder.build_all_bars(ohlcv_df, symbol=req.symbol)
            n_total = len(features_df)

        conditioned_df = apply_conditioning(features_df, req.conditioning)
        logger.info("[probabilistic] %s | condicionados: %d / %d", req.symbol, len(conditioned_df), n_total)

        model = _build_model(req.model)
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

        result.conditioned_summary = _build_conditioned_summary(
            conditioned_df=conditioned_df,
            ohlcv_df=ohlcv_df,
            n_total_events=n_total,
            n_periods=req.n_periods,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en probabilistic_analysis [%s, %s]", req.symbol, req.event_type)
        if settings.debug:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/conditioning-count",
    response_model=ConditioningCountResult,
    summary="Conteo de barras condicionadas",
    description=(
        "Carga OHLCV, construye la matriz de features y aplica los filtros de "
        "condicionamiento. Retorna cuántas barras pasan los filtros sobre el total."
    ),
)
async def conditioning_count(
    req: ConditioningCountRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> ConditioningCountResult:
    feature_builder = FeatureBuilder()
    try:
        ohlcv_df, _ = await _load_ohlcv(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            mdh_client=mdh_client,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
            ohlcv_source=req.ohlcv_source,
            credentials_account=req.credentials_account,
        )
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        is_fundamental = (req.event_type == EventType.earnings)
        fundamental_load_info: str | None = None
        if is_fundamental:
            earnings_df, earnings_info = await _fetch_earnings_safe(req.symbol, mdh_client)
            logger.info("[conditioning-count] %s | OHLCV: %d barras | %s", req.symbol, len(ohlcv_df), earnings_info)
            features_df = feature_builder.build_from_fundamental_context(
                ohlcv_df, earnings_df, symbol=req.symbol
            )
            features_df = _filter_features_by_date(features_df, req.date_range_start, req.date_range_end)
            n_earning_days = int(features_df["take_earnings"].sum()) if not features_df.empty else 0
            fundamental_load_info = (
                f"OHLCV: {len(ohlcv_df)} barras · {earnings_info} · "
                f"{n_earning_days} eventos detectados"
            )
            logger.info("[conditioning-count] %s | features: %d filas | earning days: %d", req.symbol, len(features_df), n_earning_days)
        else:
            features_df = feature_builder.build_all_bars(ohlcv_df, symbol=req.symbol)

        conditioned_df = apply_conditioning(features_df, req.conditioning)
        logger.info("[conditioning-count] %s | condicionados: %d / %d", req.symbol, len(conditioned_df), len(features_df))
        rows = [_row_to_bar(row) for _, row in conditioned_df.iterrows()]
        return ConditioningCountResult(
            n_conditioned=len(conditioned_df),
            n_total=len(features_df),
            rows=rows,
            fundamental_load_info=fundamental_load_info,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en conditioning_count [%s, %s]", req.symbol, req.event_type)
        if settings.debug:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")


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


def _row_to_bar(row) -> ConditionedBar:
    te = row.get("take_earnings")
    return ConditionedBar(
        # Identidad
        date=str(row.get("date", ""))[:10],
        event_type=_enum_val(row.get("event_type")),
        symbol=str(row.get("symbol")) if row.get("symbol") is not None else None,
        # F - Posicionamiento
        gap_pct=_safe_float(row.get("gap_pct")),
        # A - Tendencia
        ema5_vs_ema20_ratio=_safe_float(row.get("ema5_vs_ema20_ratio")),
        price_vs_ema50_pct=_safe_float(row.get("price_vs_ema50_pct")),
        trend_direction=_enum_val(row.get("trend_direction")),
        # B - Momentum
        return_5d=_safe_float(row.get("return_5d")),
        return_20d=_safe_float(row.get("return_20d")),
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
        guidance=_enum_val(row.get("guidance")),
        # G - Estacionalidad
        day_of_week=_enum_val(row.get("day_of_week")),
        month=_enum_val(row.get("month")),
        quarter=_enum_val(row.get("quarter")),
        earnings_season=_enum_val(row.get("earnings_season")),
    )


def _build_conditioned_summary(
    conditioned_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_total_events: int,
    n_periods: int,
) -> ConditionedSummary:
    """
    Construye ConditionedSummary a partir del DataFrame de features condicionados.

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
            avg_forward_return={},
            return_samples_close=[],
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
        ts_utc = pd.Timestamp(ts).tz_convert("UTC") if getattr(ts, "tzinfo", None) else pd.Timestamp(ts, tz="UTC")
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

    def _s(arr: list[float]) -> tuple[float | None, float | None]:
        if not arr:
            return None, None
        a = np.array(arr, dtype=float)
        return float(np.mean(a)), float(np.std(a, ddof=1)) if len(a) > 1 else 0.0

    range_mean, range_std   = _s(ranges)
    vol_mean, vol_std       = _s(volumes)
    ret_mean, ret_std       = _s(ev_returns)

    # Forward returns condicionados — períodos fijos [1, 3, 5, 10]
    fixed_periods = [1, 3, 5, 10]
    avg_forward_return: dict[int, dict] = {}
    for per in fixed_periods:
        fwd: list[float] = []
        for ts in conditioned_df["date"]:
            ts_utc = pd.Timestamp(ts).tz_convert("UTC") if getattr(ts, "tzinfo", None) else pd.Timestamp(ts, tz="UTC")
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0 or loc + per >= len(df):
                continue
            open_p1  = float(df["open"].iloc[loc + 1])
            close_pn = float(df["close"].iloc[loc + per])
            if open_p1 > 0 and not (np.isnan(open_p1) or np.isnan(close_pn)):
                fwd.append((close_pn - open_p1) / open_p1)
        fwd_mean, fwd_std = _s(fwd)
        avg_forward_return[per] = {"mean": fwd_mean or 0.0, "std": fwd_std or 0.0}

    # Return samples para KDE — forward returns al período del análisis
    return_samples_close: list[float] = []
    actual_period = max(1, n_periods)
    for ts in conditioned_df["date"]:
        ts_utc = pd.Timestamp(ts).tz_convert("UTC") if getattr(ts, "tzinfo", None) else pd.Timestamp(ts, tz="UTC")
        loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
        if loc < 0 or loc + actual_period >= len(df):
            continue
        open_p1  = float(df["open"].iloc[loc + 1])
        close_pn = float(df["close"].iloc[loc + actual_period])
        if open_p1 > 0 and not (np.isnan(open_p1) or np.isnan(close_pn)):
            return_samples_close.append((close_pn - open_p1) / open_p1)

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
        avg_forward_return=avg_forward_return,
        return_samples_close=return_samples_close,
        return_samples_gap=return_samples_gap,
    )


def apply_conditioning(df: pd.DataFrame, cond: ConditioningParams) -> pd.DataFrame:
    """Filtra df aplicando solo los campos no-None de ConditioningParams (7 clusters)."""
    f = df.copy()

    # ── A: Tendencia ─────────────────────────────────────────────────────────
    if cond.ema5_vs_ema20_ratio_min is not None:
        f = f[f["ema5_vs_ema20_ratio"] >= cond.ema5_vs_ema20_ratio_min]
    if cond.ema5_vs_ema20_ratio_max is not None:
        f = f[f["ema5_vs_ema20_ratio"] <= cond.ema5_vs_ema20_ratio_max]
    if cond.price_vs_ema50_pct_min is not None:
        f = f[f["price_vs_ema50_pct"] >= cond.price_vs_ema50_pct_min]
    if cond.price_vs_ema50_pct_max is not None:
        f = f[f["price_vs_ema50_pct"] <= cond.price_vs_ema50_pct_max]
    if cond.trend_directions:
        allowed = {d.value for d in cond.trend_directions}
        f = f[f["trend_direction"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── B: Momentum ───────────────────────────────────────────────────────────
    if cond.return_5d_min is not None:
        f = f[f["return_5d"] >= cond.return_5d_min]
    if cond.return_5d_max is not None:
        f = f[f["return_5d"] <= cond.return_5d_max]
    if cond.return_20d_min is not None:
        f = f[f["return_20d"] >= cond.return_20d_min]
    if cond.return_20d_max is not None:
        f = f[f["return_20d"] <= cond.return_20d_max]
    if cond.rsi14_min is not None:
        f = f[f["rsi14"] >= cond.rsi14_min]
    if cond.rsi14_max is not None:
        f = f[f["rsi14"] <= cond.rsi14_max]

    # ── C: Sobreextensión ─────────────────────────────────────────────────────
    if cond.bb_positions:
        allowed = {p.value for p in cond.bb_positions}
        f = f[f["bb_position"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.bb_width_pct_min is not None:
        f = f[f["bb_width_pct"] >= cond.bb_width_pct_min]
    if cond.bb_width_pct_max is not None:
        f = f[f["bb_width_pct"] <= cond.bb_width_pct_max]
    if cond.rsi14_zones:
        allowed = {z.value for z in cond.rsi14_zones}
        f = f[f["rsi14_zone"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── D: Volatilidad ────────────────────────────────────────────────────────
    if cond.hist_vol_10d_min is not None:
        f = f[f["hist_vol_10d"] >= cond.hist_vol_10d_min]
    if cond.hist_vol_10d_max is not None:
        f = f[f["hist_vol_10d"] <= cond.hist_vol_10d_max]
    if cond.vol_ratio_min is not None:
        f = f[f["vol_ratio_10_30"] >= cond.vol_ratio_min]
    if cond.vol_ratio_max is not None:
        f = f[f["vol_ratio_10_30"] <= cond.vol_ratio_max]
    if cond.atr_pct_min is not None:
        f = f[f["atr_pct"] >= cond.atr_pct_min]
    if cond.atr_pct_max is not None:
        f = f[f["atr_pct"] <= cond.atr_pct_max]
    if cond.vol_regimes:
        allowed = {r.value for r in cond.vol_regimes}
        f = f[f["vol_regime"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── E: Fundamental ────────────────────────────────────────────────────────
    if cond.take_earnings is True:
        f = f[f["take_earnings"] == True]  # noqa: E712
    if cond.eps_surprise_pct_min is not None:
        f = f[f["eps_surprise_pct"] >= cond.eps_surprise_pct_min]
    if cond.eps_surprise_pct_max is not None:
        f = f[f["eps_surprise_pct"] <= cond.eps_surprise_pct_max]
    if cond.guidance_directions:
        allowed = {g.value for g in cond.guidance_directions}
        f = f[f["guidance"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── F: Posicionamiento ────────────────────────────────────────────────────
    if cond.gap_pct_min is not None:
        f = f[f["gap_pct"] >= cond.gap_pct_min]
    if cond.gap_pct_max is not None:
        f = f[f["gap_pct"] <= cond.gap_pct_max]
    if cond.gap_direction == "positive":
        f = f[f["gap_pct"] > 0]
    elif cond.gap_direction == "negative":
        f = f[f["gap_pct"] < 0]

    # ── G: Estacionalidad ─────────────────────────────────────────────────────
    if cond.days_of_week:
        allowed = {d.value for d in cond.days_of_week}
        f = f[f["day_of_week"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.months:
        allowed = {m.value for m in cond.months}
        f = f[f["month"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.quarters:
        allowed = {q.value for q in cond.quarters}
        f = f[f["quarter"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.earnings_seasons:
        allowed = {s.value for s in cond.earnings_seasons}
        f = f[f["earnings_season"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    return f


def _build_model(model_type: ModelType) -> BaseEventModel:
    if model_type == ModelType.frequentist:
        return FrequentistModel()
    if model_type == ModelType.bootstrap:
        return BootstrapModel()
    if model_type == ModelType.kde:
        return KDEModel()
    if model_type == ModelType.bayesian:
        return BayesianModel()
    return BootstrapModel()


async def _load_ohlcv(
    symbol: str,
    source: str,
    asset_class: str,
    mdh_client: MdhClient,
    date_start: pd.Timestamp | None = None,
    date_end: pd.Timestamp | None = None,
    ohlcv_source: str | None = None,
    credentials_account: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    Carga OHLCV completo exclusivamente via MDH (layer=curated, complete_historical).

    Si el dataset no existe en el lake, dispara un job de ingesta sincrónico en MDH
    y re-consulta el lake tras completar. Nunca accede a fuentes externas directamente.

    Cuando ohlcv_source está presente (modo fundamental), lo usa como fuente de datos
    OHLCV y fuerza asset_class="equity" para acceder al path correcto del lake.

    Lanza HTTPException 503 si MDH no está disponible o la ingesta falla.
    """
    resolved_source = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class

    # 1. Consultar lake (MDH curated)
    try:
        df = await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            start=date_start,
            end=date_end,
        )
        if not df.empty:
            return df, resolved_source
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"MDH no disponible: {exc}")

    # 2. Dataset ausente → disparar ingesta en MDH
    try:
        await mdh_client.trigger_ingest(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            type_saved="complete_historical",
            credentials_account=credentials_account,
        )
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo ingestar {symbol} vía {resolved_source}: {exc}",
        )

    # 3. Re-consultar tras ingesta exitosa
    try:
        df = await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            start=date_start,
            end=date_end,
        )
        return df, resolved_source
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error al re-consultar {symbol} tras ingesta: {exc}",
        )


async def _fetch_earnings_safe(
    symbol: str,
    mdh_client: MdhClient,
) -> tuple[pd.DataFrame, str]:
    """Carga earnings desde MDH. Retorna (df, info_text) sin lanzar excepción."""
    try:
        df = await mdh_client.fetch_earnings_dates(symbol)
        if df.empty:
            return df, "Earnings MDH: sin datos disponibles"
        return df, f"Earnings MDH: {len(df)} reportes"
    except MdhUnavailableError:
        return empty_earnings_df(), "Earnings MDH: servicio no disponible"


def _to_utc(ts: object) -> pd.Timestamp:
    """Convierte a Timestamp UTC tolerando tanto tz-aware como tz-naive."""
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def _filter_features_by_date(
    features_df: pd.DataFrame,
    date_start: object,
    date_end: object,
) -> pd.DataFrame:
    """Filtra el DataFrame de features por rango de fechas usando la columna 'date'."""
    if features_df.empty:
        return features_df
    f = features_df.copy()
    if date_start is not None:
        f = f[f["date"] >= _to_utc(date_start)]
    if date_end is not None:
        f = f[f["date"] <= _to_utc(date_end)]
    return f




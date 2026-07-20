from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import (
    AnalysisRequest,
    ConditioningCountRequest,
    ConditioningCountResult,
    EventType,
    GlobalInformativeMetrics,
    GlobalInformativeRequest,
    ProbabilisticResult,
)
from backend.config import Settings, get_settings
from backend.core import data_pipeline, probabilistic_pipeline
from backend.core.conditioning_pipeline import build_conditioned_dataset
from backend.core.metrics import compute_global_metrics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


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
) -> GlobalInformativeMetrics:
    try:
        ohlcv_df, source_used = data_pipeline.load_ohlcv(
            settings=settings,
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            ohlcv_source=req.ohlcv_source,
            timeframe=req.timeframe,
        )
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        return compute_global_metrics(
            ohlcv_df=ohlcv_df,
            symbol=req.symbol,
            timeframe=req.timeframe,
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
) -> ProbabilisticResult:
    try:
        return probabilistic_pipeline.run_probabilistic_analysis(req, settings)
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
) -> ConditioningCountResult:
    try:
        ohlcv_df, _ = data_pipeline.load_ohlcv(
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
        fundamental_load_info: str | None = None
        if is_fundamental:
            earnings_df, earnings_info = data_pipeline.fetch_earnings_safe(settings, req.symbol, req.source)
            logger.info("[conditioning-count] %s | OHLCV: %d barras | %s", req.symbol, len(ohlcv_df), earnings_info)

        conditioned_df, n_total, features_df = build_conditioned_dataset(
            ohlcv_df=ohlcv_df,
            earnings_df=earnings_df,
            event_type=req.event_type,
            conditioning=req.conditioning,
            symbol=req.symbol,
            timeframe=req.timeframe,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
        )
        if is_fundamental:
            n_earning_days = int(features_df["take_earnings"].sum()) if not features_df.empty else 0
            fundamental_load_info = (
                f"OHLCV: {len(ohlcv_df)} barras · {earnings_info} · "
                f"{n_earning_days} eventos detectados"
            )
        logger.info("[conditioning-count] %s | condicionados: %d / %d", req.symbol, len(conditioned_df), n_total)
        rows = [probabilistic_pipeline.row_to_bar(row) for _, row in conditioned_df.iterrows()]
        return ConditioningCountResult(
            n_conditioned=len(conditioned_df),
            n_total=n_total,
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

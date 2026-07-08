from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.api.routers.analysis import get_mdh_client, probabilistic_analysis
from backend.api.routers.price_action import price_action_analysis
from backend.api.schemas import (
    AnalysisRequest,
    PriceActionRequest,
    SaveEdgeRequest,
    SaveEdgeResponse,
)
from backend.config import Settings, get_settings
from backend.core.edge import EdgeEnvelope, FilesystemEdgeStore, assemble_edge_payload
from backend.data import MdhClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post(
    "/save",
    response_model=SaveEdgeResponse,
    status_code=201,
    summary="Guardar análisis (objeto Edge + plots)",
    description=(
        "Recalcula el análisis probabilístico y de price action para los parámetros "
        "dados, ensambla el objeto Edge (con las métricas del Análisis Condicionado "
        "y los plots asociados) y lo persiste en el filesystem bajo "
        "data/{symbol}/{timeframe}/{run_id}/."
    ),
)
async def save_edge(
    req: SaveEdgeRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> SaveEdgeResponse:
    try:
        analysis_req = AnalysisRequest(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            ohlcv_source=req.ohlcv_source,
            timeframe=req.timeframe,
            event_type=req.event_type,
            gap_threshold_pct=req.gap_threshold_pct,
            include_earnings_days=req.include_earnings_days,
            n_periods=req.n_periods,
            model=req.model,
            bins=req.bins,
            conditioning=req.conditioning,
            date_range_start=req.date_range_start,
            date_range_end=req.date_range_end,
            credentials_account=req.credentials_account,
        )
        price_action_req = PriceActionRequest(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            ohlcv_source=req.ohlcv_source,
            timeframe=req.timeframe,
            event_type=req.event_type,
            gap_threshold_pct=req.gap_threshold_pct,
            include_earnings_days=req.include_earnings_days,
            n_periods=req.n_periods,
            include_bands=req.include_bands,
            price_action_mode=req.price_action_mode,
            event_timeframe=req.event_timeframe,
            conditioning=req.conditioning,
            date_range_start=req.date_range_start,
            date_range_end=req.date_range_end,
            credentials_account=req.credentials_account,
        )

        probabilistic_result = await probabilistic_analysis(
            analysis_req, settings=settings, mdh_client=mdh_client
        )
        price_action_result = await price_action_analysis(
            price_action_req, settings=settings, mdh_client=mdh_client
        )

        edge_payload, plots = assemble_edge_payload(
            symbol=req.symbol,
            timeframe=req.timeframe,
            n_periods=req.n_periods,
            probabilistic_result=probabilistic_result,
            price_action_result=price_action_result,
        )

        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        plot_rel_paths = {name: f"{name}.png" for name in plots}

        envelope = EdgeEnvelope(
            run_id=run_id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            created_at=created_at,
            conditioning_params=req.conditioning.model_dump(),
            plots=plot_rel_paths,
            edge=edge_payload,
        )

        store = FilesystemEdgeStore(settings.storage_root)
        store.save(
            run_id=run_id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            edge_payload=envelope.model_dump(mode="json"),
            plots=plots,
        )

        return SaveEdgeResponse(
            run_id=run_id,
            symbol=req.symbol,
            timeframe=req.timeframe,
            created_at=created_at,
            plots=plot_rel_paths,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error en save_edge [%s]", req.symbol)
        if settings.debug:
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error")

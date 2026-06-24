from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import DetectEventsRequest, EventRecord, EventType
from backend.config import Settings, get_settings
from backend.core.event_detector import EventDetector
from backend.data import MdhClient, MdhUnavailableError, MdhValidationError, empty_earnings_df

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
    return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.post(
    "/detect",
    response_model=list[EventRecord],
    summary="Detectar eventos",
    description="Detecta eventos de earnings o gaps usando OHLCV del Data Lake vía MDH.",
)
async def detect_events(
    req: DetectEventsRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> list[EventRecord]:
    detector = EventDetector()

    try:
        ohlcv_df = await _load_ohlcv(req, mdh_client)
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        try:
            earnings_df = await mdh_client.fetch_earnings_dates(req.symbol)
        except MdhUnavailableError as exc:
            if req.event_type == EventType.earnings:
                raise HTTPException(
                    status_code=503,
                    detail=f"MDH no disponible para earnings dates de {req.symbol}: {exc}",
                )
            earnings_df = empty_earnings_df()

        if req.event_type == EventType.earnings:
            events = detector.detect_earnings(ohlcv_df, earnings_df)
        else:
            earnings_dates = None
            if req.include_earnings_days is not True:
                earnings_dates = earnings_df.index.to_pydatetime().tolist()
            events = detector.detect_gaps(
                ohlcv_df,
                threshold_pct=req.gap_threshold_pct,
                earnings_dates=earnings_dates,
            )

        events = [e.model_copy(update={"symbol": req.symbol}) for e in events]
        events = _filter_events_by_date(events, req.date_range_start, req.date_range_end)
        return events
    except HTTPException:
        raise
    except Exception:
        if settings.debug:
            raise
        raise HTTPException(status_code=500, detail="Internal server error")


async def _load_ohlcv(
    req: DetectEventsRequest,
    mdh_client: MdhClient,
) -> pd.DataFrame:
    """
    Carga OHLCV via MDH. Dispara ingesta si el dataset no existe.
    Cuando req.ohlcv_source está presente (modo fundamental), lo usa como fuente
    y fuerza asset_class="equity" para el path OHLCV correcto.
    Lanza HTTPException 503 si MDH no está disponible.
    """
    resolved_source = (req.ohlcv_source or req.source or "yfinance").lower()
    resolved_asset_class = "equity" if req.ohlcv_source else req.asset_class

    # 1. Consultar lake
    try:
        df = await mdh_client.query_ohlcv(
            symbol=req.symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            start=req.date_range_start,
            end=req.date_range_end,
        )
        if not df.empty:
            return df
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"MDH no disponible: {exc}")

    # 2. Dataset ausente → disparar ingesta
    try:
        await mdh_client.trigger_ingest(
            symbol=req.symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            type_saved="complete_historical",
            credentials_account=req.credentials_account,
        )
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo ingestar {req.symbol} vía {resolved_source}: {exc}",
        )

    # 3. Re-consultar tras ingesta
    try:
        return await mdh_client.query_ohlcv(
            symbol=req.symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            start=req.date_range_start,
            end=req.date_range_end,
        )
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error al re-consultar {req.symbol} tras ingesta: {exc}",
        )


def _to_utc(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _filter_events_by_date(
    events: list[EventRecord],
    start: datetime | None,
    end: datetime | None,
) -> list[EventRecord]:
    out = events
    if start is not None:
        start_ts = _to_utc(pd.Timestamp(start))
        out = [e for e in out if _to_utc(pd.Timestamp(e.date)) >= start_ts]
    if end is not None:
        end_ts = _to_utc(pd.Timestamp(end))
        out = [e for e in out if _to_utc(pd.Timestamp(e.date)) <= end_ts]
    return out

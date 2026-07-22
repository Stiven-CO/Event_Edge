from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import DetectEventsRequest, EventRecord
from backend.config import Settings, get_settings
from backend.core import cache
from backend.core.conditioning_pipeline import select_raw_events

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.post(
    "/detect",
    response_model=list[EventRecord],
    summary="Detectar eventos",
    description="Detecta eventos de earnings o gaps usando OHLCV/earnings leídos directamente del Data Lake.",
)
async def detect_events(
    req: DetectEventsRequest,
    settings: Settings = Depends(get_settings),
) -> list[EventRecord]:
    try:
        resolved_source = (req.ohlcv_source or req.source or "yfinance").lower()
        resolved_asset_class = "equity" if req.ohlcv_source else req.asset_class

        ohlcv_df, _ = cache.cached_load_ohlcv(
            settings=settings,
            symbol=req.symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
            timeframe="1d",
        )
        if ohlcv_df.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        earnings_source = (req.source or "yfinance").lower()
        earnings_df, _ = cache.cached_fetch_earnings_safe(settings, req.symbol, earnings_source)

        events = select_raw_events(
            ohlcv_df=ohlcv_df,
            earnings_df=earnings_df,
            event_type=req.event_type,
            symbol=req.symbol,
            gap_threshold_pct=req.gap_threshold_pct,
            include_earnings_days=req.include_earnings_days,
        )
        return events
    except HTTPException:
        raise
    except Exception:
        if settings.debug:
            raise
        raise HTTPException(status_code=500, detail="Internal server error")

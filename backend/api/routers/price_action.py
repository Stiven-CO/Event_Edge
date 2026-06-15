from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import PriceActionRequest, PriceActionResult, EventType
from backend.api.routers.analysis import apply_conditioning
from backend.config import Settings, get_settings
from backend.core.event_detector import EventDetector
from backend.core.feature_builder import FeatureBuilder
from backend.core.price_action import compute_price_action
from backend.data import MdhClient, MdhUnavailableError

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
    return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.post(
    "/price-action",
    response_model=PriceActionResult,
    summary="Price Action Plot",
    description=(
        "Devuelve el comportamiento promedio del precio normalizado (índice 100) "
        "por grupo all/win/loss con bandas ±1σ opcionales. "
        "n_periods=0 → barras de 30min del día del evento; "
        "n_periods>0 → sesiones diarias P1→Pn."
    ),
)
async def price_action_analysis(
    req: PriceActionRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> PriceActionResult:
    detector = EventDetector()
    feature_builder = FeatureBuilder()

    try:
        # 1. OHLCV diario — siempre vía MDH (con ingest si no existe)
        ohlcv_daily = await _load_ohlcv_daily(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            mdh_client=mdh_client,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
        )
        if ohlcv_daily.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        # 2. Earnings dates vía MDH — graceful degradation si no disponibles
        try:
            earnings_df = await mdh_client.fetch_earnings_dates(req.symbol)
        except MdhUnavailableError as exc:
            if req.event_type == EventType.earnings:
                raise HTTPException(
                    status_code=503,
                    detail=f"MDH no disponible para earnings dates de {req.symbol}: {exc}",
                )
            earnings_df = _empty_earnings_df()

        # 3. Detectar y condicionar eventos
        if req.event_type == EventType.earnings:
            events = detector.detect_earnings(ohlcv_daily, earnings_df)
        else:
            earnings_dates = None
            if req.include_earnings_days is not True:
                earnings_dates = earnings_df.index.to_pydatetime().tolist()
            events = detector.detect_gaps(
                ohlcv_daily,
                threshold_pct=req.gap_threshold_pct,
                earnings_dates=earnings_dates,
            )
        events = [e.model_copy(update={"symbol": req.symbol}) for e in events]

        features_df = feature_builder.build(ohlcv_daily, events)
        conditioned_df = apply_conditioning(features_df, req.conditioning)

        # 4. Si horizonte intraday, cargar 30min solo para días de eventos condicionados
        ohlcv_intraday: pd.DataFrame | None = None
        if req.n_periods == 0 and not conditioned_df.empty:
            event_dates = sorted(set(
                pd.Timestamp(row["date"]).tz_convert("UTC").date()
                for _, row in conditioned_df.iterrows()
            ))
            ohlcv_intraday = await _load_ohlcv_intraday(
                symbol=req.symbol,
                source=req.source,
                asset_class=req.asset_class,
                mdh_client=mdh_client,
                event_dates=event_dates,
            )

        # 5. Calcular price action
        return compute_price_action(
            events_df=conditioned_df,
            ohlcv_daily_df=ohlcv_daily,
            ohlcv_intraday_df=ohlcv_intraday,
            n_periods=req.n_periods,
            include_bands=req.include_bands,
        )

    except HTTPException:
        raise
    except Exception:
        if settings.debug:
            raise
        raise HTTPException(status_code=500, detail="Internal server error")


async def _load_ohlcv_daily(
    symbol: str,
    source: str,
    asset_class: str,
    mdh_client: MdhClient,
    date_start: pd.Timestamp | None = None,
    date_end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Carga OHLCV diario vía MDH. Dispara ingesta si el dataset no existe.
    Lanza HTTPException 503 si MDH no está disponible.
    """
    resolved_source = (source or "yfinance").lower()

    # 1. Consultar lake
    try:
        df = await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=asset_class,
            timeframe="1d",
            start=date_start,
            end=date_end,
        )
        if not df.empty:
            return df
    except MdhUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"MDH no disponible: {exc}")

    # 2. Dataset ausente → disparar ingesta
    try:
        await mdh_client.trigger_ingest(
            symbol=symbol,
            source=resolved_source,
            asset_class=asset_class,
            timeframe="1d",
            type_saved="complete_historical",
        )
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo ingestar {symbol} vía {resolved_source}: {exc}",
        )

    # 3. Re-consultar
    try:
        return await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=asset_class,
            timeframe="1d",
            start=date_start,
            end=date_end,
        )
    except MdhUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error al re-consultar {symbol} tras ingesta: {exc}",
        )


async def _load_ohlcv_intraday(
    symbol: str,
    source: str,
    asset_class: str,
    mdh_client: MdhClient,
    event_dates: list | None = None,
) -> pd.DataFrame:
    """
    Carga OHLCV 30min solo para los días de eventos condicionados via MDH
    (estrategia specific_event, query-by-dates).
    Retorna DataFrame vacío si MDH no puede proveer los datos.
    """
    if not event_dates:
        return pd.DataFrame()

    resolved_source = (source or "yfinance").lower()
    date_strs = [d.isoformat() for d in event_dates]

    try:
        return await mdh_client.query_ohlcv_for_event_dates(
            symbol=symbol,
            source=resolved_source,
            asset_class=asset_class,
            timeframe="30m",
            event_dates=date_strs,
        )
    except MdhUnavailableError:
        return pd.DataFrame()


def _empty_earnings_df() -> pd.DataFrame:
    df = pd.DataFrame(columns=["eps_actual", "eps_estimate", "revenue_actual", "revenue_estimate"])
    df.index = pd.DatetimeIndex([], tz="UTC", name="date")
    return df

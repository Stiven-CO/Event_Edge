from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

from backend.api.schemas import PriceActionRequest, PriceActionResult, EventType
from backend.api.routers.analysis import apply_conditioning
from backend.config import Settings, get_settings
from backend.core.feature_builder import FeatureBuilder
from backend.core.price_action import compute_price_action
from backend.core.price_action.builder import _to_utc
from backend.data import MdhClient, MdhUnavailableError, MdhValidationError, empty_earnings_df

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
            ohlcv_source=req.ohlcv_source,
            credentials_account=req.credentials_account,
        )
        if ohlcv_daily.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        # 2. Bifurcación: path earnings (fundamental) vs OHLCV-all-bars
        is_fundamental = (req.event_type == EventType.earnings)

        if is_fundamental:
            try:
                earnings_df = await mdh_client.fetch_earnings_dates(req.symbol)
            except MdhUnavailableError:
                earnings_df = empty_earnings_df()
            features_df = feature_builder.build_from_fundamental_context(
                ohlcv_daily, earnings_df, symbol=req.symbol
            )
        else:
            features_df = feature_builder.build_all_bars(ohlcv_daily, symbol=req.symbol)

        conditioned_df = apply_conditioning(features_df, req.conditioning)

        # 3. Si horizonte intraday (n_periods=0), cargar 30min para barras condicionadas
        ohlcv_intraday: pd.DataFrame | None = None
        intraday_error: str | None = None
        if req.n_periods == 0 and not conditioned_df.empty:
            event_dates = sorted(set(
                _to_utc(row["date"]).date()
                for _, row in conditioned_df.iterrows()
            ))
            logger.info(
                "[price-action] %s | intraday 30m | fuente=%s | ohlcv_source=%s | eventos=%d | fechas=%s",
                req.symbol, req.source, req.ohlcv_source, len(event_dates),
                [d.isoformat() for d in event_dates[:5]],
            )
            ohlcv_intraday, intraday_error = await _load_ohlcv_intraday(
                symbol=req.symbol,
                source=req.source,
                asset_class=req.asset_class,
                mdh_client=mdh_client,
                event_dates=event_dates,
                ohlcv_source=req.ohlcv_source,
            )
            logger.info(
                "[price-action] %s | intraday recibido: %d barras%s",
                req.symbol, len(ohlcv_intraday) if ohlcv_intraday is not None else 0,
                f" | error={intraday_error}" if intraday_error else "",
            )

        # 4. Calcular price action
        result = compute_price_action(
            events_df=conditioned_df,
            ohlcv_daily_df=ohlcv_daily,
            ohlcv_intraday_df=ohlcv_intraday,
            n_periods=req.n_periods,
            include_bands=req.include_bands,
        )
        result.intraday_source_error = intraday_error
        return result

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
    ohlcv_source: str | None = None,
    credentials_account: str | None = None,
) -> pd.DataFrame:
    """
    Carga OHLCV diario vía MDH. Dispara ingesta si el dataset no existe.
    Cuando ohlcv_source está presente (modo fundamental), lo usa como fuente
    y fuerza asset_class="equity" para el path OHLCV correcto.
    Lanza HTTPException 503 si MDH no está disponible.
    """
    resolved_source = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class

    # 1. Consultar lake
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
            return df
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MdhUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"MDH no disponible: {exc}")

    # 2. Dataset ausente → disparar ingesta
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

    # 3. Re-consultar
    try:
        return await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="1d",
            start=date_start,
            end=date_end,
        )
    except MdhValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
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
    ohlcv_source: str | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Carga OHLCV 30min solo para los días de eventos condicionados via MDH
    (estrategia specific_event, query-by-dates).
    Retorna (DataFrame, None) en éxito o (DataFrame vacío, msg_error) si MDH falla.
    Cuando ohlcv_source está presente (modo fundamental), lo usa como fuente
    y fuerza asset_class="equity" para el path OHLCV correcto.
    """
    if not event_dates:
        return pd.DataFrame(), None

    resolved_source = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class
    date_strs = [d.isoformat() for d in event_dates]

    logger.info(
        "[_load_ohlcv_intraday] %s | source=%s asset_class=%s tf=30m | %d fechas",
        symbol, resolved_source, resolved_asset_class, len(date_strs),
    )

    try:
        df = await mdh_client.query_ohlcv_for_event_dates(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe="30m",
            event_dates=date_strs,
        )
        logger.info(
            "[_load_ohlcv_intraday] %s | MDH OK → %d barras",
            symbol, len(df),
        )
        return df, None
    except MdhUnavailableError as exc:
        error_msg = str(exc)
        logger.warning(
            "[_load_ohlcv_intraday] %s | MDH error (source=%s): %s",
            symbol, resolved_source, error_msg,
        )
        return pd.DataFrame(), error_msg



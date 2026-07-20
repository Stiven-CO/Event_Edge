from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

from backend.api.schemas import PriceActionRequest, PriceActionResult, EventType
from backend.config import Settings, get_settings
from backend.core import data_pipeline
from backend.core.conditioning_pipeline import build_conditioned_dataset
from backend.core.price_action import compute_price_action
from backend.core.price_action.builder import MULTI_DAY_TFS, _to_utc
from backend.data import MdhClient, MdhUnavailableError, MdhValidationError

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_INTRADAY_TFS = {"1m", "5m", "15m", "30m", "1h", "4h"}


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
    try:
        # 1. OHLCV base — vía MDH (con ingest si no existe)
        ohlcv_daily = await _load_ohlcv_daily(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            mdh_client=mdh_client,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
            ohlcv_source=req.ohlcv_source,
            credentials_account=req.credentials_account,
            timeframe=req.timeframe,
        )
        if ohlcv_daily.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        # 2. Fechas de evento condicionadas — vía Pipeline 1 (lake) + Pipeline 2,
        #    la misma definición de "evento" usada por /events/detect y
        #    /analysis/probabilistic. Solo se usan las FECHAS resultantes; el
        #    precio que efectivamente se grafica sigue viniendo de ohlcv_daily
        #    (MDH, con auto-ingesta) — Price Action nunca expone datos
        #    fundamentales, solo los usa como filtro de fechas (ver builder.py,
        #    que solo lee row["date"] de events_df).
        is_fundamental = (req.event_type == EventType.earnings)

        lake_ohlcv_df, _ = data_pipeline.load_ohlcv(
            settings=settings,
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
            ohlcv_source=req.ohlcv_source,
            timeframe=req.timeframe,
        )
        lake_earnings_df = None
        if is_fundamental:
            lake_earnings_df, _ = data_pipeline.fetch_earnings_safe(settings, req.symbol, req.source)

        conditioned_df, _, _ = build_conditioned_dataset(
            ohlcv_df=lake_ohlcv_df,
            earnings_df=lake_earnings_df,
            event_type=req.event_type,
            conditioning=req.conditioning,
            symbol=req.symbol,
            timeframe=req.timeframe,
            date_start=req.date_range_start,
            date_end=req.date_range_end,
        )

        # 3. Si modo "in_event", cargar barras del TF del evento para las fechas condicionadas
        use_intraday = req.price_action_mode == "in_event"
        ohlcv_intraday: pd.DataFrame | None = None
        intraday_error: str | None = None
        if use_intraday and not conditioned_df.empty:
            event_dates = sorted(set(
                _to_utc(row["date"]).date()
                for _, row in conditioned_df.iterrows()
            ))
            logger.info(
                "[price-action] %s | in_event tf=%s | fuente=%s | ohlcv_source=%s | eventos=%d | fechas=%s",
                req.symbol, req.event_timeframe, req.source, req.ohlcv_source, len(event_dates),
                [d.isoformat() for d in event_dates[:5]],
            )
            ohlcv_intraday, intraday_error = await _load_ohlcv_intraday(
                symbol=req.symbol,
                source=req.source,
                asset_class=req.asset_class,
                mdh_client=mdh_client,
                event_dates=event_dates,
                ohlcv_source=req.ohlcv_source,
                timeframe=req.event_timeframe,
                outer_timeframe=req.timeframe,
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
            outer_timeframe=req.timeframe,
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
    timeframe: str = "1d",
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
            timeframe=timeframe,
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
            timeframe=timeframe,
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
            timeframe=timeframe,
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
    timeframe: str = "30m",
    outer_timeframe: str = "1d",
) -> tuple[pd.DataFrame, str | None]:
    """
    Carga barras del TF del evento para los días de eventos condicionados.

    Estrategia:
    1. Intenta cargar complete_historical para el TF y filtrar por fechas de evento.
    2. Si no existe o no hay datos en esas fechas, usa query_ohlcv_for_event_dates.

    Cuando outer_timeframe es multi-día (1w/1mo/…), no se restringe el resultado
    a los días exactos de evento: se conserva el rango completo cargado para que
    el builder pueda recortar la ventana completa (mes/semana) de cada evento.

    Retorna (DataFrame, None) en éxito o (DataFrame vacío, msg_error) si ambos fallan.
    """
    if not event_dates:
        return pd.DataFrame(), None

    resolved_source      = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class
    date_strs            = [d.isoformat() for d in event_dates]
    event_date_set       = set(date_strs)

    # ── Paso 1: complete_historical ──────────────────────────────────────
    start_dt = datetime(min(event_dates).year, min(event_dates).month, min(event_dates).day)
    end_dt   = datetime(max(event_dates).year, max(event_dates).month, max(event_dates).day) + timedelta(days=35)

    try:
        df_complete = await mdh_client.query_ohlcv(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe=timeframe,
            start=start_dt,
            end=end_dt,
        )
        if not df_complete.empty:
            if outer_timeframe in MULTI_DAY_TFS:
                filtered = df_complete
            else:
                mask     = pd.Index(df_complete.index.strftime("%Y-%m-%d")).isin(event_date_set)
                filtered = df_complete[mask]
            if not filtered.empty:
                logger.info(
                    "[_load_ohlcv_intraday] %s | complete_historical tf=%s → %d barras en %d fechas",
                    symbol, timeframe, len(filtered), len(event_date_set),
                )
                return filtered, None
            logger.info(
                "[_load_ohlcv_intraday] %s | complete_historical tf=%s existe pero sin barras en fechas de evento → fallback",
                symbol, timeframe,
            )
    except MdhUnavailableError:
        logger.warning(
            "[_load_ohlcv_intraday] %s | MDH no disponible al consultar complete_historical tf=%s → fallback",
            symbol, timeframe,
        )

    # ── Paso 2: fallback a query_ohlcv_for_event_dates ──────────────────
    logger.info(
        "[_load_ohlcv_intraday] %s | query_ohlcv_for_event_dates tf=%s | %d fechas",
        symbol, timeframe, len(date_strs),
    )
    try:
        df = await mdh_client.query_ohlcv_for_event_dates(
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe=timeframe,
            event_dates=date_strs,
        )
        logger.info(
            "[_load_ohlcv_intraday] %s | fallback OK → %d barras",
            symbol, len(df),
        )
        return df, None
    except MdhUnavailableError as exc:
        error_msg = str(exc)
        logger.warning(
            "[_load_ohlcv_intraday] %s | ambos paths fallaron (source=%s): %s",
            symbol, resolved_source, error_msg,
        )
        return pd.DataFrame(), error_msg



from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import PriceActionRequest, PriceActionResult, EventType
from backend.api.routers.analysis import apply_conditioning
from backend.config import Settings, get_settings
from backend.core.event_detector import EventDetector
from backend.core.feature_builder import FeatureBuilder
from backend.core.price_action import compute_price_action
from backend.data import EarningsLoader, MdhClient, MdhUnavailableError

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
    loader = EarningsLoader()
    detector = EventDetector()
    feature_builder = FeatureBuilder()

    try:
        # 1. Cargar OHLCV diario
        ohlcv_daily, _ = await _load_ohlcv_daily(
            symbol=req.symbol,
            source=req.source,
            asset_class=req.asset_class,
            settings=settings,
            mdh_client=mdh_client,
            loader=loader,
        )
        if ohlcv_daily.empty:
            raise HTTPException(
                status_code=404,
                detail=f"No OHLCV data available for {req.symbol}",
            )

        # 2. Si horizonte intraday, cargar OHLCV 30min
        ohlcv_intraday: pd.DataFrame | None = None
        if req.n_periods == 0:
            ohlcv_intraday, _ = await _load_ohlcv_intraday(
                symbol=req.symbol,
                source=req.source,
                asset_class=req.asset_class,
                settings=settings,
                mdh_client=mdh_client,
                loader=loader,
            )

        # 3. Detectar eventos
        earnings_df = loader.fetch_earnings_dates(req.symbol)
        if req.event_type == EventType.earnings:
            events = detector.detect_earnings(ohlcv_daily, earnings_df)
        else:
            earnings_dates = earnings_df.index.to_pydatetime().tolist()
            events = detector.detect_gaps(
                ohlcv_daily,
                threshold_pct=req.gap_threshold_pct,
                earnings_dates=earnings_dates,
            )
        events = [e.model_copy(update={"symbol": req.symbol}) for e in events]

        # 4. Construir features + conditioning
        features_df = feature_builder.build(ohlcv_daily, events)
        conditioned_df = apply_conditioning(features_df, req.conditioning)

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
    settings: Settings,
    mdh_client: MdhClient,
    loader: EarningsLoader,
) -> tuple[pd.DataFrame, str]:
    """Carga OHLCV diario: MDH si disponible, fallback yfinance."""
    if settings.mdh_enabled:
        try:
            df = await mdh_client.query_ohlcv(
                symbol=symbol,
                source=source,
                asset_class=asset_class,
                timeframe="1d",
            )
            return df, "mdh"
        except MdhUnavailableError:
            pass
    return loader.fetch_ohlcv(symbol, period="5y", interval="1d"), "yfinance"


async def _load_ohlcv_intraday(
    symbol: str,
    source: str,
    asset_class: str,
    settings: Settings,
    mdh_client: MdhClient,
    loader: EarningsLoader,
) -> tuple[pd.DataFrame, str]:
    """
    Carga OHLCV 30min: MDH si disponible, fallback yfinance.
    yfinance limita historial de 30min a ~60 días.
    Retorna (DataFrame vacío, source) si no hay datos.
    """
    if settings.mdh_enabled:
        try:
            df = await mdh_client.query_ohlcv(
                symbol=symbol,
                source=source,
                asset_class=asset_class,
                timeframe="30m",
            )
            return df, "mdh"
        except MdhUnavailableError:
            pass

    try:
        df = loader.fetch_ohlcv(symbol, period="60d", interval="30m")
        return df, "yfinance"
    except Exception:
        return pd.DataFrame(), "yfinance"

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import BrokerStatus
from backend.config import Settings, get_settings
from backend.core import cache
from backend.data import MdhClient

router = APIRouter(prefix="/api/v1/control", tags=["control"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
    return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.get(
    "/health",
    summary="Health check del servicio",
    description="Retorna estado básico del backend Event Edge.",
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/broker-status",
    response_model=list[BrokerStatus],
    summary="Estado de fuentes de datos",
    description=(
        "Verifica disponibilidad de MDH y sus conectores (mt5, tws, yfinance). "
        "El estado de yfinance se obtiene del propio MDH, no de EE directamente."
    ),
)
async def broker_status(
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> list[BrokerStatus]:
    mdh_mode = "primary" if settings.mdh_enabled else "disabled"
    mdh_alive = False
    connectors: dict[str, bool] = {}

    if settings.mdh_enabled:
        mdh_alive = await mdh_client.health_check()
        if mdh_alive:
            try:
                connectors = await mdh_client.connector_status()
            except Exception:
                connectors = {}

    mt5_alive = bool(connectors.get("mt5", False))
    tws_alive = bool(connectors.get("tws", False))
    yfinance_alive = bool(connectors.get("yfinance", False))

    return [
        BrokerStatus(source="mdh",      alive=mdh_alive,      mode=mdh_mode),
        BrokerStatus(source="mt5",      alive=mt5_alive,      mode="proxy"),
        BrokerStatus(source="tws",      alive=tws_alive,      mode="proxy"),
        BrokerStatus(source="yfinance", alive=yfinance_alive, mode="proxy"),
    ]


@router.get(
    "/cache/stats",
    summary="Estadísticas del caché de pipelines",
    description="Hits/misses/tamaño de los cachés de lectura de lake (L1) y features (L2).",
)
async def cache_stats(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "lake_cache": cache.get_lake_cache(settings).stats(),
        "feature_cache": cache.get_feature_cache(settings).stats(),
    }


@router.post(
    "/cache/clear",
    summary="Limpia los cachés de pipelines",
    description="Escape hatch manual — vacía los cachés L1 (lake) y L2 (features).",
)
async def cache_clear() -> dict[str, str]:
    cache.get_lake_cache().clear()
    cache.get_feature_cache().clear()
    return {"status": "cleared"}

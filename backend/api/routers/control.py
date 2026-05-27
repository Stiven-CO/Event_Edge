from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.schemas import BrokerStatus
from backend.config import Settings, get_settings
from backend.data import EarningsLoader, MdhClient

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
	description="Verifica disponibilidad de MDH, MT5, TWS y yfinance sin exponer credenciales.",
)
async def broker_status(
	settings: Settings = Depends(get_settings),
	mdh_client: MdhClient = Depends(get_mdh_client),
) -> list[BrokerStatus]:
	mdh_mode = "primary" if settings.mdh_enabled else "disabled"
	mdh_alive = await mdh_client.health_check() if settings.mdh_enabled else False

	mt5_enabled = settings.mt5_login > 0 and settings.mt5_server != ""
	mt5_mode = "primary" if mt5_enabled else "disabled"

	tws_enabled = settings.tws_api_key != ""
	tws_mode = "primary" if tws_enabled else "disabled"

	yfinance_mode = "fallback" if settings.mdh_enabled else "primary"
	yfinance_alive = EarningsLoader().is_available()

	return [
		BrokerStatus(source="mdh", alive=mdh_alive, mode=mdh_mode),
		BrokerStatus(source="mt5", alive=mt5_enabled, mode=mt5_mode),
		BrokerStatus(source="tws", alive=tws_enabled, mode=tws_mode),
		BrokerStatus(source="yfinance", alive=yfinance_alive, mode=yfinance_mode),
	]

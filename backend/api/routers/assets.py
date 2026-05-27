from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from backend.api.schemas import AssetInfo
from backend.config import Settings, get_settings
from backend.data import MdhClient, MdhUnavailableError

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


class AssetBasicInfo(BaseModel):
    symbol: str
    short_name: str
    long_name: str
    sector: str
    industry: str


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
	return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.get(
	"",
	response_model=list[AssetInfo],
	summary="Lista de activos disponibles",
	description="Consulta activos en MDH; si no está disponible, retorna lista vacía con fuente yfinance.",
)
async def list_assets(
	response: Response,
	asset_class: str = Query("equity"),
	settings: Settings = Depends(get_settings),
	mdh_client: MdhClient = Depends(get_mdh_client),
) -> list[AssetInfo]:
	if not settings.mdh_enabled:
		response.headers["X-Data-Source"] = "yfinance"
		return []

	try:
		assets = await mdh_client.list_assets(asset_class=asset_class)
		response.headers["X-Data-Source"] = "mdh"
		return [AssetInfo(**a) for a in assets]
	except MdhUnavailableError:
		response.headers["X-Data-Source"] = "yfinance"
		return []


@router.get(
	"/{symbol}/info",
	response_model=AssetBasicInfo,
	summary="Información básica del activo",
	description="Retorna nombre, sector e industria del activo vía yfinance.",
)
async def get_asset_info(symbol: str) -> AssetBasicInfo:
	import yfinance as yf  # noqa: PLC0415

	info = yf.Ticker(symbol).info
	return AssetBasicInfo(
		symbol=symbol.upper(),
		short_name=info.get("shortName", ""),
		long_name=info.get("longName", ""),
		sector=info.get("sector", ""),
		industry=info.get("industry", ""),
	)

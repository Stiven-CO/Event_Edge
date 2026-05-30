from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import DetectEventsRequest, EventRecord, EventType
from backend.config import Settings, get_settings
from backend.core.event_detector import EventDetector
from backend.data import EarningsLoader, MdhClient, MdhUnavailableError

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
	return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.post(
	"/detect",
	response_model=list[EventRecord],
	summary="Detectar eventos",
	description="Detecta eventos de earnings o gaps usando OHLCV de MDH con fallback a yfinance.",
)
async def detect_events(
	req: DetectEventsRequest,
	settings: Settings = Depends(get_settings),
	mdh_client: MdhClient = Depends(get_mdh_client),
) -> list[EventRecord]:
	loader = EarningsLoader()
	detector = EventDetector()

	try:
		ohlcv_df = await _load_ohlcv(req, settings, mdh_client, loader)
		if ohlcv_df.empty:
			raise HTTPException(
				status_code=404,
				detail=f"No OHLCV data available for {req.symbol}",
			)

		if req.event_type == EventType.earnings:
			earnings_df = loader.fetch_earnings_dates(req.symbol)
			events = detector.detect_earnings(ohlcv_df, earnings_df)
		else:
			earnings_dates = loader.fetch_earnings_dates(req.symbol).index.to_pydatetime().tolist()
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
	settings: Settings,
	mdh_client: MdhClient,
	loader: EarningsLoader,
) -> pd.DataFrame:
	selected_source = (req.source or "yfinance").lower()

	# yfinance se consulta directo.
	if selected_source == "yfinance":
		return loader.fetch_ohlcv(req.symbol, period="5y", interval="1d")

	if settings.mdh_enabled:
		try:
			return await mdh_client.query_ohlcv(
				symbol=req.symbol,
				source=selected_source,
				asset_class=req.asset_class,
				timeframe="1d",
				start=req.date_range_start,
				end=req.date_range_end,
			)
		except MdhUnavailableError:
			pass

	# Fallback a yfinance si MT5/TWS fallan.
	return loader.fetch_ohlcv(req.symbol, period="5y", interval="1d")


def _to_utc(ts: pd.Timestamp) -> pd.Timestamp:
	"""Convierte un Timestamp a UTC, localizando primero si es naive."""
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

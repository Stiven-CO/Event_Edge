"""
Cliente HTTP asíncrono para market_data_hub.

Retorna DataFrame OHLCV con columnas:
    date (DatetimeIndex UTC), open, high, low, close, volume (float)

Errores:
    MdhUnavailableError — cuando MDH no responde o retorna error 5xx
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pandas as pd

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class MdhUnavailableError(Exception):
    """MDH no está disponible o retornó un error inesperado."""


class MdhClient:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def health_check(self) -> bool:
        """Retorna True si MDH responde 200, False en cualquier otro caso."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/control/health",
                    headers=self._headers,
                )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    async def connector_status(self) -> dict[str, bool]:
        """
        Retorna el estado de conectores reportado por MDH /control/health.
        Ejemplo: {"mt5": False, "tws": True, "fred": False}
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/control/health",
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
            raise MdhUnavailableError("MDH no disponible para consultar conectores") from exc

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} al consultar conectores"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} al consultar conectores: {response.text[:200]}"
            )

        payload = response.json()
        connectors = payload.get("connectors", [])
        out: dict[str, bool] = {}
        for c in connectors:
            name = str(c.get("name", "")).lower()
            if name:
                out[name] = bool(c.get("alive", False))
        return out

    async def query_ohlcv(
        self,
        symbol: str,
        source: str,
        asset_class: str,
        timeframe: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
        layer: str = "curated",
    ) -> pd.DataFrame:
        """
        Llama POST /api/v1/data/query en MDH.
        Retorna DataFrame con index DatetimeIndex UTC y columnas
        [open, high, low, close, volume].
        Lanza MdhUnavailableError si el servicio no responde.
        """
        payload: dict[str, Any] = {
            "symbol": symbol,
            "source": source,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "layer": layer,
        }
        if start is not None:
            payload["start"] = start.isoformat()
        if end is not None:
            payload["end"] = end.isoformat()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._base_url}/data/query",
                    json=payload,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                f"MDH no disponible para {symbol}: conexión fallida"
            ) from exc

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} para {symbol}"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} para {symbol}: {response.text[:200]}"
            )

        records: list[dict[str, Any]] = response.json()
        if not records:
            return pd.DataFrame(columns=["date"] + _OHLCV_COLUMNS)

        df = pd.DataFrame(records)

        missing = [c for c in _OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise MdhUnavailableError(
                f"Respuesta de MDH no contiene columnas requeridas: {missing}"
            )

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.set_index("date")
        df = df[_OHLCV_COLUMNS].astype(float)
        df.index = df.index.tz_convert("UTC")
        df.sort_index(inplace=True)
        return df

    async def query_ohlcv_for_event_dates(
        self,
        symbol: str,
        source: str,
        asset_class: str,
        timeframe: str,
        event_dates: list[str],
    ) -> pd.DataFrame:
        """
        Llama POST /api/v1/data/query-by-dates en MDH.
        `event_dates` debe ser lista de strings "YYYY-MM-DD".
        Retorna DataFrame con DatetimeIndex UTC y columnas [open, high, low, close, volume].
        Lanza MdhUnavailableError si el servicio no responde.
        """
        payload: dict[str, Any] = {
            "symbol": symbol,
            "source": source,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "event_dates": event_dates,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/data/query-by-dates",
                    json=payload,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                f"MDH no disponible para {symbol}: conexión fallida"
            ) from exc

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} para {symbol}"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} para {symbol}: {response.text[:200]}"
            )

        records: list[dict[str, Any]] = response.json()
        if not records:
            return pd.DataFrame(columns=["date"] + _OHLCV_COLUMNS)

        df = pd.DataFrame(records)
        missing = [c for c in _OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise MdhUnavailableError(
                f"Respuesta de MDH no contiene columnas requeridas: {missing}"
            )

        df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
        df = df.dropna(subset=["date"])
        df = df.set_index("date")
        df = df[_OHLCV_COLUMNS].astype(float)
        df.index = df.index.tz_convert("UTC")
        df.sort_index(inplace=True)
        return df

    async def list_assets(
        self, asset_class: str = "equity"
    ) -> list[dict[str, Any]]:
        """
        Retorna lista de activos disponibles en MDH.
        Cada dict incluye: symbol, source, asset_class, timeframe.
        """
        params = {"asset_class": asset_class}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._base_url}/data/datasets",
                    params=params,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                "MDH no disponible al listar activos: conexión fallida"
            ) from exc

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} al listar activos"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} al listar activos: {response.text[:200]}"
            )

        datasets: list[dict[str, Any]] = response.json()
        return [
            {
                "symbol": d.get("symbol", ""),
                "source": d.get("source", ""),
                "asset_class": d.get("asset_class", asset_class),
                "timeframe": d.get("timeframe", ""),
            }
            for d in datasets
        ]

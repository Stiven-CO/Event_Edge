"""
Cliente HTTP asíncrono para market_data_hub (MDH).

Responsabilidades:
  - query_ohlcv       → POST /api/v1/data/query          (lee lake curated)
  - trigger_ingest    → POST /api/v1/data/ingest          (descarga + persiste)
  - fetch_earnings_dates → GET /api/v1/data/earnings-dates
  - query_ohlcv_for_event_dates → POST /api/v1/data/query-by-dates
  - connector_status  → GET  /api/v1/control/health
  - list_assets       → GET  /api/v1/data/datasets

Toda la lógica de acceso a fuentes externas (yfinance, MT5, TWS) vive en MDH.
EE nunca importa ni conecta con fuentes de datos directamente.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pandas as pd

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_EARNINGS_COLUMNS = ["eps_actual", "eps_estimate", "revenue_actual", "revenue_estimate"]


class MdhUnavailableError(Exception):
    """MDH no está disponible o retornó un error inesperado (5xx / conexión)."""


class MdhValidationError(Exception):
    """MDH rechazó la petición por configuración o validación incorrecta (4xx)."""


def _empty_earnings_df() -> pd.DataFrame:
    df = pd.DataFrame(columns=_EARNINGS_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="date")
    return df


class MdhClient:
    def __init__(self, base_url: str, api_key: str = "") -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}

    # ──────────────────────────────────────────────────────────────────────────
    # Control
    # ──────────────────────────────────────────────────────────────────────────

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
        Ejemplo: {"mt5": False, "tws": True, "yfinance": True, "fred": False}
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
        return {
            str(c.get("name", "")).lower(): bool(c.get("alive", False))
            for c in connectors
            if c.get("name")
        }

    # ──────────────────────────────────────────────────────────────────────────
    # OHLCV — lectura del lake
    # ──────────────────────────────────────────────────────────────────────────

    async def query_ohlcv(
        self,
        symbol: str,
        source: str,
        asset_class: str,
        timeframe: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """
        Llama POST /api/v1/data/query en MDH (layer=curated, complete_historical).

        Retorna DataFrame con index DatetimeIndex UTC y columnas
        [open, high, low, close, volume].
        Lanza MdhUnavailableError si el servicio no responde o retorna error 5xx.
        Retorna DataFrame vacío si MDH responde 404 (dataset no existe aún).
        """
        payload: dict[str, Any] = {
            "symbol": symbol,
            "source": source,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "layer": "curated",
            "type_data": "ohlcv",
            "type_saved": "complete_historical",
        }
        if start is not None:
            payload["start"] = start.isoformat()
        if end is not None:
            payload["end"] = end.isoformat()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/data/query",
                    json=payload,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                f"MDH no disponible para {symbol}: conexión fallida"
            ) from exc

        if response.status_code == 404:
            return pd.DataFrame(columns=["date"] + _OHLCV_COLUMNS)

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} para {symbol}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} para {symbol} "
                f"(source={source}): {response.text[:300]}"
            )

        records: list[dict[str, Any]] = response.json()
        if not records:
            return pd.DataFrame(columns=["date"] + _OHLCV_COLUMNS)

        return _parse_ohlcv_records(records, symbol)

    async def trigger_ingest(
        self,
        symbol: str,
        source: str,
        asset_class: str,
        timeframe: str = "1d",
        type_saved: str = "complete_historical",
        credentials_account: str | None = None,
    ) -> dict[str, Any]:
        """
        Llama POST /api/v1/data/ingest en MDH.

        MDH ejecuta la ingesta de forma sincrónica (extract → normalize →
        validate → write lake). Usa timeout extendido (300 s) para downloads
        lentos (yfinance "max", MT5 histórico completo).

        Retorna el dict de resultado del job:
            {job_id, status, rows_stored, lake_path, ...}
        Lanza MdhUnavailableError si falla la conexión o MDH responde 4xx/5xx.
        """
        ingest_config: dict[str, Any] = {
            "symbol": symbol,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "type_data": "ohlcv",
            "type_saved": type_saved,
        }
        if credentials_account is not None:
            ingest_config["account_key"] = credentials_account

        payload: dict[str, Any] = {
            "source": source,
            "config": ingest_config,
        }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self._base_url}/data/ingest",
                    json=payload,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                f"MDH no disponible para ingestar {symbol} vía {source}: conexión fallida"
            ) from exc

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} al ingestar {symbol}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise MdhValidationError(
                f"MDH retornó {response.status_code} al ingestar {symbol} "
                f"(source={source}): {response.text[:400]}"
            )

        return response.json()

    # ──────────────────────────────────────────────────────────────────────────
    # Earnings dates
    # ──────────────────────────────────────────────────────────────────────────

    async def fetch_earnings_dates(
        self,
        symbol: str,
        limit: int = 40,
    ) -> pd.DataFrame:
        """
        Llama GET /api/v1/data/earnings-dates en MDH.

        Retorna DataFrame con index DatetimeIndex UTC y columnas
        [eps_actual, eps_estimate, revenue_actual, revenue_estimate].
        Retorna DataFrame vacío si el símbolo no tiene earnings o MDH responde 404.
        Lanza MdhUnavailableError si falla la conexión o MDH responde 5xx.
        """
        params = {"symbol": symbol, "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/data/earnings-dates",
                    params=params,
                    headers=self._headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise MdhUnavailableError(
                f"MDH no disponible para earnings dates de {symbol}: conexión fallida"
            ) from exc

        if response.status_code == 404:
            return _empty_earnings_df()

        if response.status_code >= 500:
            raise MdhUnavailableError(
                f"MDH retornó error {response.status_code} para earnings de {symbol}"
            )
        if response.status_code >= 400:
            return _empty_earnings_df()

        payload = response.json()
        records: list[dict[str, Any]] = payload.get("records", [])
        if not records:
            return _empty_earnings_df()

        rows = []
        for rec in records:
            date = pd.to_datetime(rec.get("date"), utc=True, errors="coerce")
            if pd.isna(date):
                continue
            rows.append({
                "date": date,
                "eps_actual": rec.get("eps_actual"),
                "eps_estimate": rec.get("eps_estimate"),
                "revenue_actual": rec.get("revenue_actual"),
                "revenue_estimate": rec.get("revenue_estimate"),
            })

        if not rows:
            return _empty_earnings_df()

        df = pd.DataFrame(rows).set_index("date")
        df.index.name = "date"
        df = df[_EARNINGS_COLUMNS]
        df.sort_index(ascending=False, inplace=True)
        return df

    # ──────────────────────────────────────────────────────────────────────────
    # OHLCV intraday por fechas de evento específicas (30m)
    # ──────────────────────────────────────────────────────────────────────────

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
        """
        payload: dict[str, Any] = {
            "symbol": symbol,
            "source": source,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "event_dates": event_dates,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
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
                f"MDH retornó error {response.status_code} para {symbol}: {response.text[:300]}"
            )
        if response.status_code >= 400:
            raise MdhUnavailableError(
                f"MDH retornó {response.status_code} para {symbol} "
                f"(source={source}): {response.text[:300]}"
            )

        records: list[dict[str, Any]] = response.json()
        if not records:
            return pd.DataFrame(columns=["date"] + _OHLCV_COLUMNS)

        return _parse_ohlcv_records(records, symbol)

    # ──────────────────────────────────────────────────────────────────────────
    # Catálogo de activos
    # ──────────────────────────────────────────────────────────────────────────

    async def list_assets(
        self, asset_class: str = "equity"
    ) -> list[dict[str, Any]]:
        """Retorna lista de activos disponibles en el lake de MDH."""
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


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _parse_ohlcv_records(
    records: list[dict[str, Any]], symbol: str
) -> pd.DataFrame:
    """Convierte lista de records JSON a DataFrame OHLCV con DatetimeIndex UTC."""
    df = pd.DataFrame(records)

    missing = [c for c in _OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise MdhUnavailableError(
            f"Respuesta de MDH no contiene columnas requeridas para {symbol}: {missing}"
        )

    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df = df.dropna(subset=["date"])
    df = df.set_index("date")
    df = df[_OHLCV_COLUMNS].astype(float)
    df.index = df.index.tz_convert("UTC")
    df.sort_index(inplace=True)
    return df

---
mode: agent
description: >
  Fase 3 — Capa de datos de Event Edge: implementa MdhClient (HTTP a market_data_hub)
  y EarningsLoader (wrapper yfinance). Sin lógica de core ni routers.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - grep_search
---

# Fase 3 — Capa de Datos

## Prerrequisitos

- Fases 1 y 2 completadas: schemas y app existen
- Leer antes de implementar:
  - `market_data_hub/api/routers/consumption.py` → contrato `POST /api/v1/data/query`
  - `market_data_hub/api/models/` → ver qué campos acepta la query de MDH
  - `Event_Edge/.github/instructions/global.instructions.md` → convenciones de fuentes de datos

## Objetivo

Crear la capa `backend/data/` con dos clientes desacoplados:
1. `MdhClient` — consulta market_data_hub vía HTTP
2. `EarningsLoader` — consulta yfinance para earnings y OHLCV fallback

**Regla de capa**: `data/` no importa nada de `core/` ni `api/`.

## Archivos a crear

### `Event_Edge/backend/data/__init__.py`
Exportar `MdhClient`, `MdhUnavailableError`, `EarningsLoader`.

### `Event_Edge/backend/data/mdh_client.py`

```python
"""
Cliente HTTP asíncrono para market_data_hub.

Retorna DataFrame OHLCV con columnas:
    date (DatetimeIndex UTC), open, high, low, close, volume (float)

Errores:
    MdhUnavailableError — cuando MDH no responde o retorna error 5xx
"""
from __future__ import annotations
import pandas as pd
from datetime import datetime
import httpx

class MdhUnavailableError(Exception):
    """MDH no está disponible o retornó un error inesperado."""

class MdhClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def health_check(self) -> bool:
        """Retorna True si MDH responde 200, False en cualquier otro caso."""
        ...

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
        Llama POST /api/v1/data/query en MDH.
        Retorna DataFrame con index DatetimeIndex UTC y columnas
        [open, high, low, close, volume].
        Lanza MdhUnavailableError si el servicio no responde.
        """
        ...

    async def list_assets(
        self, asset_class: str = "equity"
    ) -> list[dict]:
        """
        Retorna lista de activos disponibles en MDH.
        Cada dict incluye: symbol, source, asset_class, timeframe.
        """
        ...
```

**Detalles de implementación**:
- Timeout en todas las peticiones: `httpx.AsyncClient(timeout=10.0)`
- `health_check()`: `GET {base_url}/health` → `True` si status 200
- `query_ohlcv()`: convierte la respuesta JSON a DataFrame; valida que las columnas
  `[open, high, low, close, volume]` existan antes de retornar
- Si `httpx.ConnectError`, `httpx.TimeoutException` o status >= 500 → lanzar `MdhUnavailableError`
- Nunca loguear `_headers` completo (puede contener API key)

### `Event_Edge/backend/data/earnings_loader.py`

```python
"""
Wrapper de yfinance para earnings metadata y OHLCV fallback.

Maneja rate limits y errores de yfinance de forma explícita.
No usa cache en disco; cada llamada es fresca (yfinance maneja su propio cache).
"""
from __future__ import annotations
import pandas as pd

class EarningsLoader:
    def fetch_earnings_dates(
        self, symbol: str, limit: int = 40
    ) -> pd.DataFrame:
        """
        Retorna DataFrame con columnas:
            date (DatetimeIndex UTC), eps_actual, eps_estimate,
            revenue_actual, revenue_estimate

        Usa yfinance: ticker.earnings_dates + ticker.calendar.
        Si yfinance no retorna datos → DataFrame vacío con las columnas correctas.
        """
        ...

    def fetch_ohlcv(
        self,
        symbol: str,
        period: str = "5y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fallback OHLCV cuando MDH no está disponible.
        Retorna DataFrame con columnas [open, high, low, close, volume]
        e index DatetimeIndex UTC.
        """
        ...

    def is_available(self) -> bool:
        """
        Verifica que yfinance esté importable y funcional.
        Retorna True en condiciones normales (sin conexión no se puede verificar).
        """
        ...
```

**Detalles de implementación**:
- `fetch_earnings_dates()`:
  - Usar `yf.Ticker(symbol).earnings_dates` (DataFrame con EPS y revenue)
  - Normalizar el index a UTC
  - Truncar a `limit` filas más recientes
  - Si `AttributeError` o resultado None → retornar DataFrame vacío
- `fetch_ohlcv()`:
  - Usar `yf.download(symbol, period=period, interval=interval, auto_adjust=True)`
  - Renombrar columnas a lowercase
  - Normalizar index a UTC
  - Validar que el DataFrame no esté vacío; si está vacío → levantar `ValueError(f"No OHLCV data for {symbol}")`
- `is_available()` → intentar `import yfinance`; retornar `True`/`False`

## Criterios de aceptación

```python
# Test manual (requiere conexión a internet):
import asyncio
from backend.data.earnings_loader import EarningsLoader

loader = EarningsLoader()
assert loader.is_available()

df = loader.fetch_earnings_dates("AAPL", limit=5)
assert not df.empty
assert "eps_actual" in df.columns

ohlcv = loader.fetch_ohlcv("AAPL", period="1y")
assert len(ohlcv) > 200
assert list(ohlcv.columns) == ["open", "high", "low", "close", "volume"]
assert ohlcv.index.tz is not None   # UTC-aware

# Test MdhClient con MDH offline:
from backend.data.mdh_client import MdhClient, MdhUnavailableError

client = MdhClient(base_url="http://localhost:9999")  # puerto inexistente
result = asyncio.run(client.health_check())
assert result == False  # no lanza, retorna False

try:
    asyncio.run(client.query_ohlcv("AAPL", "yfinance", "equity"))
    assert False, "Debe lanzar MdhUnavailableError"
except MdhUnavailableError:
    pass

print("Capa de datos OK")
```

## Restricciones

- `MdhClient` no importa de `core/` ni `api/`
- `EarningsLoader` no importa de `core/` ni `api/`
- Timeout siempre explícito en peticiones HTTP — sin `httpx` sin timeout
- `symbol` no se valida con regex aquí; se valida en schemas Pydantic (Fase 2)
- El API key de MDH nunca aparece en logs, trazas de error ni mensajes de excepción

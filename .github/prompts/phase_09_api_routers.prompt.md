---
mode: agent
description: >
  Fase 9 — API Routers de Event Edge: implementa los 4 routers FastAPI
  (control, assets, events, analysis) conectando la capa core con la API HTTP.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - grep_search
---

# Fase 9 — API Routers

## Prerrequisitos

- Fases 1-8 completadas: todos los módulos de core y data existen
- Leer antes de implementar:
  - `market_data_hub/api/routers/consumption.py` → patrón FastAPI router con Depends
  - `Event_Edge/backend/api/schemas.py` → contratos de request/response
  - `Event_Edge/.github/instructions/global.instructions.md` → seguridad y convenciones

## Objetivo

Implementar los 4 routers con sus endpoints completos.
Al finalizar, `curl` puede llamar todos los endpoints y obtener respuestas válidas
con datos reales de yfinance (sin MDH corriendo).

## Router 1: `backend/api/routers/control.py`

```
GET  /api/v1/control/health        → {"status": "ok"}
GET  /api/v1/control/broker-status → list[BrokerStatus]
```

### `GET /api/v1/control/health`
Respuesta: `{"status": "ok"}` — siempre 200.

### `GET /api/v1/control/broker-status`
Verifica disponibilidad de cada fuente y retorna `list[BrokerStatus]`:

| source | alive | mode | Lógica de verificación |
|--------|-------|------|------------------------|
| `mdh` | bool | `"primary"` si `mdh_enabled` else `"disabled"` | `await MdhClient.health_check()` |
| `mt5` | bool | `"disabled"` si `mt5_login == 0` | `mt5_login > 0 and mt5_server != ""` |
| `tws` | bool | `"disabled"` si `tws_api_key == ""` | `tws_api_key != ""` |
| `yfinance` | `True` siempre | `"fallback"` si `mdh_enabled` else `"primary"` | `EarningsLoader().is_available()` |

**Importante**: nunca incluir credenciales en el campo `detail`.

---

## Router 2: `backend/api/routers/assets.py`

```
GET  /api/v1/assets                → list[AssetInfo]
```

### `GET /api/v1/assets`
Parámetros de query: `asset_class: str = "equity"`

- Si `settings.mdh_enabled = True` y MDH responde: retornar assets de MDH
- Si MDH no disponible o `mdh_enabled = False`: retornar lista vacía con header
  `X-Data-Source: yfinance` y body `[]`

`AssetInfo` (schema inline o en schemas.py):
```python
class AssetInfo(BaseModel):
    symbol: str
    source: str
    asset_class: str
    timeframe: str
```

---

## Router 3: `backend/api/routers/events.py`

```
POST /api/v1/events/detect         → list[EventRecord]
```

### `POST /api/v1/events/detect`
Body:
```python
class DetectEventsRequest(BaseModel):
    symbol: str                    # [A-Z]{1,5}
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(ge=0.1, le=20.0, default=1.0)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
```

**Flujo**:
1. Obtener OHLCV: intentar MDH → si falla, usar `EarningsLoader.fetch_ohlcv()`
2. Si `event_type = earnings`: obtener earnings con `EarningsLoader.fetch_earnings_dates()`
3. Llamar `EventDetector.detect_earnings()` o `detect_gaps()` según `event_type`
4. Si `date_range_start/end` provistos → filtrar resultado
5. Retornar lista de `EventRecord`

**Errores**:
- `symbol` inválido → 422 (manejado por Pydantic)
- OHLCV vacío → 404 con `{"detail": "No OHLCV data available for {symbol}"}`
- Error inesperado → 500 con mensaje genérico (sin stack trace en producción)

---

## Router 4: `backend/api/routers/analysis.py`

```
POST /api/v1/analysis/informative     → InformativeMetrics
POST /api/v1/analysis/probabilistic   → ProbabilisticResult
```

### `POST /api/v1/analysis/informative`
Body:
```python
class InformativeRequest(BaseModel):
    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(ge=0.1, le=20.0, default=1.0)
    periods: list[int] = [1, 3, 5, 10]
```

**Flujo**:
1. Obtener OHLCV (MDH → yfinance fallback)
2. Detectar eventos
3. Llamar `compute_informative_metrics()`
4. Retornar `InformativeMetrics`

### `POST /api/v1/analysis/probabilistic`
Body: `AnalysisRequest` (del schemas.py)

**Flujo**:
1. Obtener OHLCV
2. Detectar eventos
3. Construir features con `FeatureBuilder`
4. Aplicar condicionamiento: filtrar `features_df` según `request.conditioning`
5. Instanciar modelo según `request.model`
6. Llamar `compute_probabilistic_metrics()`
7. Retornar `ProbabilisticResult`

**Lógica de condicionamiento** (aplicar en el router, no en el modelo):
```python
def apply_conditioning(df: pd.DataFrame, cond: ConditioningParams) -> pd.DataFrame:
    """Filtra df aplicando solo los campos no-None de ConditioningParams."""
    filtered = df.copy()
    if cond.ema5_range_pct_min is not None:
        filtered = filtered[filtered["ema5_range_pct"] >= cond.ema5_range_pct_min]
    # ... aplicar cada campo de ConditioningParams
    return filtered
```

## Inyección de dependencias

Usar `FastAPI.Depends` para settings y clientes:
```python
from fastapi import Depends
from backend.config import get_settings, Settings

def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
    return MdhClient(settings.mdh_base_url, settings.mdh_api_key)
```

## Criterios de aceptación

```bash
# Servidor corriendo en puerto 8100:

# 1. Health
curl -s http://localhost:8100/api/v1/control/health
# → {"status":"ok"}

# 2. Broker status
curl -s http://localhost:8100/api/v1/control/broker-status
# → [{"source":"mdh","alive":false,...}, {"source":"yfinance","alive":true,...}]

# 3. Detectar earnings AAPL (modo yfinance)
curl -s -X POST http://localhost:8100/api/v1/events/detect \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","source":"yfinance","event_type":"earnings"}'
# → lista de EventRecord con fechas de earnings

# 4. Métricas informativas
curl -s -X POST http://localhost:8100/api/v1/analysis/informative \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","source":"yfinance","event_type":"earnings","periods":[1,3,5]}'
# → InformativeMetrics con n_total_events > 0

# 5. Análisis probabilístico con bins custom
curl -s -X POST http://localhost:8100/api/v1/analysis/probabilistic \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","source":"yfinance","event_type":"earnings","model":"bootstrap","n_periods":5,"bins":[-0.08,-0.02,0.02,0.08]}'
# → ProbabilisticResult con 3 familias; probabilities suman ~1.0

# 6. Symbol inválido → 422
curl -s -X POST http://localhost:8100/api/v1/events/detect \
  -H "Content-Type: application/json" \
  -d '{"symbol":"aapl","source":"yfinance","event_type":"earnings"}'
# → 422 Unprocessable Entity
```

## Restricciones

- Sin credenciales en respuestas ni en logs de nivel INFO o superior
- `MdhUnavailableError` nunca propagada al cliente como 500; se captura y usa fallback
- Stack traces solo en `debug=True`; en producción mensaje genérico
- Todos los endpoints documentados con `summary` y `description` en el decorador FastAPI
- `apply_conditioning()` es función pura, no método de clase — definida en `routers/analysis.py`

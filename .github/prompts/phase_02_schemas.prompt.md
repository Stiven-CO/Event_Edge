---
mode: agent
description: >
  Fase 2 — Contratos Pydantic de Event Edge: define todos los schemas,
  enums y modelos de request/response en backend/api/schemas.py.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 2 — Contratos Pydantic

## Prerrequisitos

- Fase 1 completada: `backend/api/app.py` existe y el servidor arranca
- Leer `Event_Edge/.github/instructions/global.instructions.md` → contratos de datos

## Objetivo

Crear `backend/api/schemas.py` con todos los modelos Pydantic tipados explícitamente.
Este archivo es la única fuente de verdad para los contratos de la API.
Al finalizar:
- Todos los tipos importan sin error
- Los enums cubren todos los valores del dominio
- Los schemas satisfacen las restricciones de seguridad (bins validados, symbol con regex)

## Archivos a crear / modificar

### `Event_Edge/backend/api/schemas.py`

Implementar los siguientes modelos en orden (dependencias primero):

#### Enums
```python
from enum import Enum

class EventType(str, Enum):
    earnings = "earnings"
    gap = "gap"

class ModelType(str, Enum):
    frequentist = "frequentist"
    bootstrap = "bootstrap"
    kde = "kde"
    bayesian = "bayesian"

class GuidanceDirection(str, Enum):
    raised = "raised"
    maintained = "maintained"
    lowered = "lowered"
    not_available = "not_available"

class BBPosition(str, Enum):
    below_lower = "below_lower"
    in_lower = "in_lower"
    middle = "middle"
    in_upper = "in_upper"
    above_upper = "above_upper"
```

#### EventRecord
Representa un evento detectado (earnings o gap):
```python
class EventRecord(BaseModel):
    date: datetime                          # UTC, timezone-aware
    event_type: EventType
    symbol: str
    gap_pct: float | None                   # None si no aplica
    eps_actual: float | None
    eps_estimate: float | None
    eps_surprise_pct: float | None
    revenue_actual: float | None
    revenue_estimate: float | None
    revenue_surprise_pct: float | None
    guidance: GuidanceDirection
```

#### ConditioningParams
Filtros opcionales; `None` en cualquier campo = sin filtro para esa variable:
```python
class ConditioningParams(BaseModel):
    ema5_range_pct_min: float | None = None
    ema5_range_pct_max: float | None = None
    ema20_range_pct_min: float | None = None
    ema20_range_pct_max: float | None = None
    open_vs_prev_close_pct_min: float | None = None
    open_vs_prev_close_pct_max: float | None = None
    bb_positions: list[BBPosition] | None = None
    gap_pct_min: float | None = None
    gap_pct_max: float | None = None
    gap_direction: Literal["positive", "negative", "any"] = "any"
    eps_surprise_pct_min: float | None = None
    eps_surprise_pct_max: float | None = None
    guidance_directions: list[GuidanceDirection] | None = None
```

#### AnalysisRequest
Body para `POST /api/v1/analysis/probabilistic`:
```python
class AnalysisRequest(BaseModel):
    symbol: str                            # validar: [A-Z]{1,5}
    source: str = "yfinance"              # "mt5" | "tws" | "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = 1.0
    n_periods: int = Field(ge=1, le=60, default=5)
    model: ModelType = ModelType.bootstrap
    bins: list[float] = [-0.05, -0.01, 0.01, 0.05]
    conditioning: ConditioningParams = ConditioningParams()
```

#### InformativeMetrics
Respuesta para `POST /api/v1/analysis/informative`:
```python
class InformativeMetrics(BaseModel):
    symbol: str
    event_type: EventType
    n_total_events: int
    frequency_per_year: float
    frequency_per_quarter: float
    avg_movement_range: dict[int, dict]    # {n_period: {mean: float, std: float}}
    avg_candle_range: dict[int, dict]      # {n_period: {mean: float, std: float}}
    gap_mean: float | None
    gap_std: float | None
    data_source: str                       # "mdh" | "yfinance"
```

#### ScenarioBin y familia probabilística
```python
class ScenarioBin(BaseModel):
    label: str                             # ej. "< -5%" | "-5% a -1%" | "> +5%"
    lower: float | None                    # None = -∞
    upper: float | None                    # None = +∞
    probability: float
    ci_lower: float
    ci_upper: float
    event_count: int

class ProbabilisticFamily(BaseModel):
    family: str                            # "close_return" | "close_vs_event" | "gap_fill"
    n_periods: int
    n_samples_used: int
    n_total_events: int
    warning: str | None                    # "insufficient_samples" | "no_gap_events" | None
    scenarios: list[ScenarioBin]

class ProbabilisticResult(BaseModel):
    symbol: str
    model: ModelType
    data_source: str
    families: list[ProbabilisticFamily]    # siempre 3 elementos
```

#### BrokerStatus
```python
class BrokerStatus(BaseModel):
    source: str                            # "mdh" | "mt5" | "tws" | "yfinance"
    alive: bool
    mode: str                              # "primary" | "fallback" | "disabled"
    detail: str | None
```

### Validaciones requeridas con `@field_validator`

1. **`AnalysisRequest.symbol`**: solo `[A-Z]{1,5}` — rechazar con `ValueError` si no cumple
2. **`AnalysisRequest.bins`**:
   - Mínimo 2 elementos
   - Todos entre -1.0 y 1.0
   - Ordenados estrictamente de menor a mayor
   - Rechazar con `ValueError` descriptivo si alguna condición falla
3. **`AnalysisRequest.gap_threshold_pct`**: `ge=0.1, le=20.0`

## Criterios de aceptación

```python
# Verificar en REPL o test rápido:
from backend.api.schemas import AnalysisRequest, EventType, ModelType, ConditioningParams

# Caso válido
req = AnalysisRequest(symbol="AAPL", event_type=EventType.earnings)
assert req.bins == [-0.05, -0.01, 0.01, 0.05]
assert req.n_periods == 5

# Symbol inválido
try:
    AnalysisRequest(symbol="aapl", event_type=EventType.earnings)
    assert False, "Debe fallar"
except ValueError:
    pass

# Bins desordenados
try:
    AnalysisRequest(symbol="AAPL", event_type=EventType.earnings, bins=[0.05, -0.05])
    assert False, "Debe fallar"
except ValueError:
    pass

# Bins fuera de rango
try:
    AnalysisRequest(symbol="AAPL", event_type=EventType.earnings, bins=[-2.0, 2.0])
    assert False, "Debe fallar"
except ValueError:
    pass

print("Todos los contratos válidos")
```

## Restricciones

- Sin imports de `core/` ni `data/` — schemas es agnóstico de implementación
- `GuidanceDirection.not_available` es el valor por defecto para `EventRecord.guidance`
  cuando la info no está disponible
- Usar `from __future__ import annotations` para compatibilidad de tipos forward
- `datetime` siempre timezone-aware (tzinfo no None) — documentar en docstring del modelo

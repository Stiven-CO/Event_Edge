---
mode: agent
description: >
  Construye Event Edge — herramienta de estudio estadístico de eventos
  (Earnings & Gap) para acciones americanas. Proyecto independiente con
  backend FastAPI + frontend React/Vite/Tailwind. Lee este archivo completo
  antes de escribir cualquier código.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - run_in_terminal
  - grep_search
  - file_search
---

# Event Edge — Build Prompt

## Contexto del ecosistema

Event Edge es un proyecto independiente dentro del ecosistema EdgeStocks.
Vive en `EdgeStocks_sistem/Event_Edge/` junto a `Backtest_Forge/`, `LiveEdge/` y `market_data_hub/`.

Proyectos de referencia para patrones y convenciones:
- `Backtest_Forge/` → estructura de proyecto independiente (pyproject.toml, FastAPI, frontend Vite)
- `market_data_hub/` → patrones de API (routers, schemas Pydantic, client HTTP frontend)
- `EdgeStocks/modules/` → modelos estadísticos existentes (HMM, RandomForest, feature engineering)

**Siempre leer antes de implementar**:
- `Backtest_Forge/pyproject.toml` → patrón de dependencias
- `market_data_hub/api/routers/consumption.py` → patrón FastAPI router
- `market_data_hub/frontend/src/api/client.ts` → patrón cliente HTTP tipado

---

## Decisiones de arquitectura

| Decisión | Valor |
|---|---|
| Ubicación | `EdgeStocks_sistem/Event_Edge/` |
| Backend | FastAPI + Python 3.11 + pydantic-settings v2 (prefijo `EE_`) |
| Frontend | React 18 + Vite 5 + TypeScript 5 + TailwindCSS 3 |
| OHLCV primaria | market_data_hub API (`POST /api/v1/data/query`) |
| OHLCV fallback | yfinance cuando `EE_MDH_ENABLED=false` o MDH no responde |
| Earnings metadata | yfinance siempre (`ticker.earnings_dates`, `ticker.calendar`) |
| Modelos estadísticos | Frequentist, Bootstrap, KDE, Bayesian — todos disponibles en menú |
| P(n) | Sesiones de trading configurables por el usuario (`int >= 1`) |
| Bins de escenarios | Configurables por el usuario desde la UI (no hardcodeados) |
| Volume profile | Solo stub documentado en v1; implementación en v2 |

### Autenticación de fuentes

- **MT5**: `EE_MT5_LOGIN`, `EE_MT5_PASSWORD`, `EE_MT5_SERVER` — solo en backend, nunca en frontend
  - `password` nunca en logs ni localStorage; solo `login` y `server` pueden mostrarse
- **TWS**: `EE_TWS_API_KEY` — sin key → error 403 explícito (no fallback silencioso)
- **yfinance**: sin credenciales

### Estado de MDH en UI

- La UI muestra un badge de estado para MDH: verde (`alive`) / rojo (no disponible)
- El header del panel de resultados muestra la fuente activa: `"Fuente: MDH"` o `"Fuente: yfinance (dev)"`
- `GET /api/v1/control/broker-status` retorna disponibilidad de cada fuente

---

## Estructura de archivos a crear

```
Event_Edge/
├── .github/
│   ├── instructions/
│   │   └── global.instructions.md      ← ya existe, NO tocar
│   └── prompts/
│       └── event_edge_build.prompt.md  ← este archivo
├── pyproject.toml
├── README.md
├── start_server.ps1
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── schemas.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── control.py          ← broker-status, health
│   │       ├── assets.py           ← listar activos disponibles
│   │       ├── events.py           ← detectar earnings/gap events
│   │       └── analysis.py         ← métricas informativas + probabilísticas
│   ├── core/
│   │   ├── __init__.py
│   │   ├── event_detector.py
│   │   ├── feature_builder.py
│   │   ├── statistical_models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── frequentist.py
│   │   │   ├── bootstrap.py
│   │   │   ├── kde.py
│   │   │   └── bayesian.py
│   │   ├── metrics/
│   │   │   ├── __init__.py
│   │   │   ├── informative.py
│   │   │   └── probabilistic.py
│   │   └── volume_profile/
│   │       └── __init__.py         ← stub documentado, sin implementación
│   └── data/
│       ├── __init__.py
│       ├── mdh_client.py
│       └── earnings_loader.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── postcss.config.js
│   ├── tailwind.config.ts
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/
│       │   ├── client.ts
│       │   ├── types.ts
│       │   └── endpoints.ts
│       ├── pages/
│       │   └── EventStudyPage.tsx
│       ├── components/
│       │   ├── BrokerStatusBadge.tsx
│       │   ├── AssetSelector.tsx
│       │   ├── EventTypeTabs.tsx
│       │   ├── ModelSelector.tsx
│       │   ├── PeriodSelector.tsx
│       │   ├── BinEditor.tsx
│       │   ├── ConditioningPanel.tsx
│       │   ├── MetricsInfoPanel.tsx
│       │   ├── ProbabilityPanel.tsx
│       │   └── EarningsTable.tsx
│       ├── hooks/
│       │   ├── useEvents.ts
│       │   └── useAnalysis.ts
│       └── store/
│           └── eventEdgeStore.ts
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── test_event_detector.py
    │   ├── test_feature_builder.py
    │   ├── test_statistical_models.py
    │   └── test_metrics.py
    └── integration/
        └── test_api.py
```

---

## Implementación por fases

### Fase 1 — Scaffolding

#### `pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "event-edge"
version = "0.1.0"
description = "Herramienta de estudio probabilístico de eventos Earnings & Gap para acciones americanas"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "numpy>=1.26",
    "scipy>=1.12",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "httpx>=0.27",
    "yfinance>=0.2.38",
    "pandas-ta>=0.3.14",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: tests sin conexión real",
    "integration: tests que requieren servicios externos",
    "smoke: prueba rápida de smoke",
]
```

#### `backend/config.py`
```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # MDH
    mdh_base_url: str = "http://localhost:8000/api/v1"
    mdh_api_key: str = ""
    mdh_enabled: bool = True          # False → yfinance fallback

    # MT5
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""

    # TWS
    tws_api_key: str = ""             # vacío → 403 en endpoints TWS

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_prefix="EE_", env_file=".env", extra="ignore")

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

#### `backend/api/app.py`
```python
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routers import control, assets, events, analysis
from backend.config import get_settings

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Event Edge API",
        description="Estudio probabilístico de eventos Earnings & Gap",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(control.router)
    app.include_router(assets.router)
    app.include_router(events.router)
    app.include_router(analysis.router)

    @app.get("/")
    async def root():
        return {"service": "Event Edge", "version": "0.1.0", "docs": "/docs"}

    return app

app = create_app()
```

---

### Fase 2 — Contratos Pydantic (`backend/api/schemas.py`)

Definir los siguientes modelos Pydantic con tipos explícitos:

```python
# Enums
class EventType(str, Enum): earnings = "earnings"; gap = "gap"
class ModelType(str, Enum): frequentist = "frequentist"; bootstrap = "bootstrap"; kde = "kde"; bayesian = "bayesian"
class GuidanceDirection(str, Enum): raised = "raised"; maintained = "maintained"; lowered = "lowered"; not_available = "not_available"
class BBPosition(str, Enum): below_lower = "below_lower"; in_lower = "in_lower"; middle = "middle"; in_upper = "in_upper"; above_upper = "above_upper"

# Evento detectado
class EventRecord(BaseModel):
    date: datetime
    event_type: EventType
    symbol: str
    gap_pct: float | None          # None si no aplica (earnings sin gap)
    eps_actual: float | None
    eps_estimate: float | None
    eps_surprise_pct: float | None
    revenue_actual: float | None
    revenue_estimate: float | None
    revenue_surprise_pct: float | None
    guidance: GuidanceDirection

# Condicionamiento (todos los campos son None = sin filtro)
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

# Request para análisis
class AnalysisRequest(BaseModel):
    symbol: str
    source: str = "mt5"            # "mt5" | "tws" | "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = 1.0
    n_periods: int = Field(ge=1, le=60, default=5)
    model: ModelType = ModelType.bootstrap
    bins: list[float] = [-0.05, -0.01, 0.01, 0.05]  # thresholds en decimal
    conditioning: ConditioningParams = ConditioningParams()

# Respuesta métricas informativas
class InformativeMetrics(BaseModel):
    symbol: str
    event_type: EventType
    n_total_events: int
    frequency_per_year: float
    frequency_per_quarter: float
    avg_movement_range: dict[int, dict]  # {n_period: {mean, std}}
    avg_candle_range: dict[int, dict]    # {n_period: {mean, std}}
    gap_mean: float | None
    gap_std: float | None
    data_source: str                     # "mdh" | "yfinance"

# Respuesta escenario probabilístico
class ScenarioBin(BaseModel):
    label: str
    lower: float | None
    upper: float | None
    probability: float
    ci_lower: float
    ci_upper: float
    event_count: int

class ProbabilisticFamily(BaseModel):
    family: str       # "close_return" | "close_vs_event" | "gap_fill"
    n_periods: int
    n_samples_used: int
    n_total_events: int
    warning: str | None    # "insufficient_samples" si n < 5
    scenarios: list[ScenarioBin]

class ProbabilisticResult(BaseModel):
    symbol: str
    model: ModelType
    data_source: str
    families: list[ProbabilisticFamily]   # siempre 3 elementos

# Control
class BrokerStatus(BaseModel):
    source: str
    alive: bool
    mode: str          # "primary" | "fallback" | "disabled"
    detail: str | None
```

---

### Fase 3 — Capa de Datos

#### `backend/data/mdh_client.py`
```python
"""
Cliente HTTP para market_data_hub.
Retorna DataFrame OHLCV con columnas: date, open, high, low, close, volume.
Si MDH no está disponible lanza MdhUnavailableError.
"""
class MdhUnavailableError(Exception): ...

class MdhClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self._base_url = base_url
        self._headers = {"X-API-Key": api_key} if api_key else {}

    async def health_check(self) -> bool: ...
    
    async def query_ohlcv(
        self,
        symbol: str,
        source: str,
        asset_class: str,
        timeframe: str = "1d",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame: ...
    
    async def list_assets(self, asset_class: str = "equity") -> list[dict]: ...
```

#### `backend/data/earnings_loader.py`
```python
"""
Wrapper de yfinance para earnings y OHLCV fallback.
Maneja rate limits y errores de yfinance de forma explícita.
"""
class EarningsLoader:
    def fetch_earnings_dates(self, symbol: str, limit: int = 40) -> pd.DataFrame:
        """Retorna DataFrame con: date, eps_actual, eps_estimate, revenue_actual, revenue_estimate"""
        ...
    
    def fetch_ohlcv(self, symbol: str, period: str = "5y", interval: str = "1d") -> pd.DataFrame:
        """Fallback OHLCV cuando MDH no está disponible."""
        ...
    
    def is_available(self) -> bool: ...
```

---

### Fase 4 — Detección de Eventos (`backend/core/event_detector.py`)

```python
class EventDetector:
    """
    Detecta eventos earnings y gap en series OHLCV.
    
    Inputs:
        ohlcv_df: DataFrame con columnas date, open, high, low, close, volume
                  index=DatetimeIndex UTC, sin gaps, timeframe diario
    
    Outputs:
        list[EventRecord]
    
    Assumptions:
        - OHLCV ajustado (precios post-split)
        - Días de mercado cerrado ya excluidos del DataFrame
        - Un evento por fecha (si earnings y gap coinciden, se prioriza earnings)
    """
    
    def detect_earnings(
        self,
        ohlcv_df: pd.DataFrame,
        earnings_df: pd.DataFrame,
    ) -> list[EventRecord]:
        """
        Alinea fechas de earnings con OHLCV.
        Calcula gap_pct = (open - prev_close) / prev_close para la sesión del evento.
        """
        ...
    
    def detect_gaps(
        self,
        ohlcv_df: pd.DataFrame,
        threshold_pct: float = 1.0,
    ) -> list[EventRecord]:
        """
        Detecta todas las sesiones donde |gap_pct| > threshold_pct.
        Excluye fechas de earnings para evitar duplicados.
        """
        ...
```

---

### Fase 5 — Feature Builder (`backend/core/feature_builder.py`)

```python
class FeatureBuilder:
    """
    Construye features de condicionamiento para cada EventRecord.
    
    Inputs:
        ohlcv_df: DataFrame OHLCV diario
        events: list[EventRecord]
    
    Outputs:
        pd.DataFrame con columnas adicionales de condicionamiento
    
    Assumptions:
        - EMA(5) = EMA semanal, EMA(20) = EMA mensual
        - Bollinger Bands(20, 2) calculados con pandas-ta
        - Features calculados ANTES del open del evento (no look-ahead)
    """
    
    def build(self, ohlcv_df: pd.DataFrame, events: list[EventRecord]) -> pd.DataFrame:
        """
        Retorna DataFrame con una fila por evento y columnas:
            date, event_type, gap_pct,
            ema5_range_pct, ema20_range_pct,
            open_vs_prev_close_pct,
            bb_position (BBPosition enum),
            eps_surprise_pct, revenue_surprise_pct, guidance
        """
        ...
    
    def _calc_ema_range_pct(self, ohlcv_df: pd.DataFrame, period: int) -> pd.Series:
        """(close - ema_N) / ema_N * 100 usando el close del día ANTERIOR al evento."""
        ...
    
    def _calc_bb_position(self, ohlcv_df: pd.DataFrame) -> pd.Series:
        """Clasifica el open del evento respecto a las bandas del día anterior."""
        ...
```

---

### Fase 6 — Modelos Estadísticos

#### `backend/core/statistical_models/base.py`
```python
from abc import ABC, abstractmethod

class BaseEventModel(ABC):
    """
    Interfaz para modelos estadísticos de análisis de eventos.
    
    Inputs:
        events_df: DataFrame con una fila por evento (output de FeatureBuilder)
                   + columnas de retornos forward: ret_p1, ret_p2, ..., ret_pN
    
    Outputs:
        list[ScenarioBin] por familia de métricas
    
    Assumptions:
        - events_df ya está filtrado por condicionamiento
        - Retornos en decimal (no porcentaje)
        - Si len(events_df) < 5 → ScenarioBin con warning
    """
    
    @abstractmethod
    def fit(self, events_df: pd.DataFrame) -> None: ...
    
    @abstractmethod
    def predict_close_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]: ...
    
    @abstractmethod
    def predict_close_vs_event_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]: ...
    
    @abstractmethod
    def predict_gap_fill_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]: ...
```

#### Implementaciones

**`frequentist.py`**: cuenta directa de frecuencias en cada bin. CI = Wilson interval.

**`bootstrap.py`**: resamplea eventos con reemplazo (n_iter=1000). Para cada bin calcula frecuencia en cada muestra. CI = percentiles 2.5 y 97.5.

**`kde.py`**: `scipy.stats.gaussian_kde` sobre retornos. Probabilidad por bin = integral de la KDE en el intervalo. CI = bootstrap de la KDE (n_iter=500).

**`bayesian.py`**: prior = distribución beta ajustada al histórico completo. Likelihood = frecuencias en el subconjunto condicionado. Posterior = Beta(α_prior + k_conditioned, β_prior + n-k_conditioned). CI = HDI (highest density interval) del posterior.

---

### Fase 7 — Métricas Informativas (`backend/core/metrics/informative.py`)

```python
def compute_informative_metrics(
    ohlcv_df: pd.DataFrame,
    events: list[EventRecord],
    periods: list[int],         # ej. [1, 3, 5, 10]
) -> InformativeMetrics:
    """
    Calcula métricas informativas para todos los eventos (sin condicionamiento).
    
    Para avg_movement_range(n): max(high[P0..Pn]) - min(low[P0..Pn]) normalizado por close_P0
    Para avg_candle_range(n): (high_Pn - low_Pn) / close_P0
    Para gap_stats: mean y std de abs(gap_pct) para eventos con gap != 0
    
    No hay look-ahead: todos los cálculos son posteriores al open del evento.
    """
    ...
```

---

### Fase 8 — Métricas Probabilísticas (`backend/core/metrics/probabilistic.py`)

```python
def compute_probabilistic_metrics(
    events_df: pd.DataFrame,          # output de FeatureBuilder, ya condicionado
    ohlcv_df: pd.DataFrame,
    model: BaseEventModel,
    n_periods: int,
    bins: list[float],
) -> ProbabilisticResult:
    """
    Calcula las 3 familias de métricas probabilísticas.
    
    Familia 1 — 'close_return':
        ret = (close_Pn - open_P0) / open_P0
        Escenarios: %, hit rate por bin
    
    Familia 2 — 'close_vs_event':
        ret = (close_Pn - close_P0) / close_P0
        Base = close de la sesión del evento (no open)
    
    Familia 3 — 'gap_fill':
        Para cada evento con gap_pct != 0:
          gap_fill = precio toca el nivel del prev_close dentro de [P0:Pn]
        Retorna: P(gap fill en N sesiones)
        Si ningún evento tiene gap → warning = "no_gap_events"
    
    Assumptions:
        - Datos OHLCV disponibles para N sesiones posteriores al evento
        - Eventos al final de la serie sin N sesiones completas → excluidos
        - n_samples_used = eventos con N sesiones completas disponibles
    """
    ...
```

---

### Fase 9 — API Routers

#### `routers/control.py`
```
GET  /api/v1/control/health          → {"status": "ok"}
GET  /api/v1/control/broker-status   → list[BrokerStatus]
```
El endpoint `broker-status` verifica: MDH (health check HTTP), MT5 (credenciales configuradas), TWS (API key configurada), yfinance (siempre disponible).

#### `routers/assets.py`
```
GET  /api/v1/assets                  → list[{symbol, source, asset_class, timeframe}]
```
Consulta MDH si está habilitado; si no, retorna lista vacía con `source: "yfinance"` y aviso de modo dev.

#### `routers/events.py`
```
POST /api/v1/events/detect           → list[EventRecord]
Body: {symbol, source, asset_class, event_type, gap_threshold_pct, date_range?}
```

#### `routers/analysis.py`
```
POST /api/v1/analysis/informative    → InformativeMetrics
Body: {symbol, source, asset_class, event_type, gap_threshold_pct, periods: list[int]}

POST /api/v1/analysis/probabilistic  → ProbabilisticResult
Body: AnalysisRequest (incluye model, n_periods, bins, conditioning)
```

---

### Fase 10 — Frontend

#### Layout `EventStudyPage.tsx`
```
┌─────────────────────────────────────────────────────────────────┐
│  Event Edge  │  [BrokerStatusBadge MDH] [BrokerStatusBadge MT5] │
├──────────────┬──────────────────────────┬───────────────────────┤
│ LEFT PANEL   │ CENTER PANEL             │ RIGHT PANEL           │
│ AssetSelector│ MetricsInfoPanel         │ ProbabilityPanel      │
│              │  - Frequency chart       │  - Scenarios bar      │
│ EventTypeTabs│  - Movement range chart  │  - Distribution KDE   │
│              │  - Gap distribution      │  - Gap fill prob      │
│ ModelSelector│ EarningsTable            │                       │
│ PeriodSelector                          │                       │
│ BinEditor    │                          │                       │
│ ConditioningPanel                       │                       │
└──────────────┴──────────────────────────┴───────────────────────┘
```

#### `BrokerStatusBadge.tsx`
```tsx
// Hace polling a GET /api/v1/control/broker-status cada 30s
// Muestra: punto verde + "MDH" si alive, punto rojo + "MDH (off)" si no
// Tooltip muestra mode: "primary" | "fallback" | "disabled"
```

#### `BinEditor.tsx`
```tsx
// Lista editable de thresholds en porcentaje
// Input: bins: number[] (en decimal, ej. [-0.05, -0.01, 0.01, 0.05])
// Muestra como porcentaje: "-5%, -1%, +1%, +5%"
// Botón reset a defaults
// Validación: mínimo 2 bins, ordenados de menor a mayor, entre -1 y 1
```

#### `ConditioningPanel.tsx`
```tsx
// Controles por variable:
// - ema5_range_pct: RangeSlider min/max (-20% a +20%)
// - ema20_range_pct: RangeSlider
// - open_vs_prev_close_pct: RangeSlider (-10% a +10%)
// - bb_position: CheckboxGroup (below_lower, in_lower, middle, in_upper, above_upper)
// - gap_direction: RadioGroup (any, positive, negative)
// - gap_pct: RangeSlider (0% a 15%)
// - eps_surprise_pct: RangeSlider (solo activo si event_type = earnings)
// - guidance: CheckboxGroup (solo activo si event_type = earnings)
// Botón "Aplicar filtros" → dispara POST /api/v1/analysis/probabilistic
// Contador: "N eventos condicionados / M totales"
```

#### `api/client.ts` — mismo patrón que `market_data_hub/frontend/src/api/client.ts`
```typescript
const BASE_URL = import.meta.env.VITE_EE_API_BASE ?? "/api/v1";
// Sin API key en frontend — el backend maneja autenticación con brokers
```

---

### Fase 11 — Volume Profile stub

#### `backend/core/volume_profile/__init__.py`
```python
"""
Volume Profile Calculator — STUB v1

Interfaz planificada para v2. Sin implementación en v1.

Descripción:
    Calcula el perfil de volumen por rango de precio (VPVR) para una ventana
    de sesiones y reporta la probabilidad de que el precio alcance cada nivel
    basándose en la distribución de volumen histórico.

Interfaz planificada:
    class VolumeProfileCalculator:
        def compute(
            self,
            ohlcv_df: pd.DataFrame,
            n_bins: int = 50,
            lookback_sessions: int = 20,
        ) -> VPVRResult:
            '''
            Retorna VPVRResult con:
              - price_levels: list[float]  — niveles de precio
              - volume_at_level: list[float]  — volumen en cada nivel
              - poc: float  — Point of Control (nivel de mayor volumen)
              - value_area_high: float  — 70% del volumen superior
              - value_area_low: float   — 70% del volumen inferior
              - prob_reach_level: dict[float, float]  — P(precio alcanza nivel)
            '''
            raise NotImplementedError("Volume Profile disponible en v2")

Dependencias previstas:
    - OHLCV con timeframe intraday (1m/5m) para mayor precisión
    - Puede funcionar con 1d pero con menor granularidad
    - Integración con ProbabilityPanel para overlay visual

Para implementar en v2:
    1. Calcular distribución de volumen por bins de precio (histograma ponderado)
    2. Calcular POC, VAH, VAL
    3. Modelar P(reach level) como función empírica del volumen relativo
    4. Exponer vía GET /api/v1/analysis/volume-profile
"""

__all__: list[str] = []
```

---

### Fase 12 — Tests

#### `tests/conftest.py`
```python
# Fixtures reutilizables:
# - synthetic_ohlcv_df: 500 sesiones de datos OHLCV sintéticos para AAPL
# - synthetic_earnings: 10 fechas de earnings con EPS y revenue
# - sample_events: list[EventRecord] basados en los datos sintéticos
# - built_features_df: output de FeatureBuilder sobre los datos anteriores
# - test_client: httpx.AsyncClient contra app de FastAPI con settings de test
```

#### `tests/unit/test_event_detector.py`
```python
# Casos a cubrir:
# - detect_earnings: fechas alineadas correctamente con OHLCV
# - detect_earnings: fecha de earnings en fin de semana → mapea al siguiente trading day
# - detect_earnings: earnings fuera del rango OHLCV → excluido sin error
# - detect_gaps: gap positivo detectado correctamente
# - detect_gaps: gap negativo detectado correctamente
# - detect_gaps: gap menor al threshold → no detectado
# - detect_gaps: fecha de earnings excluida del resultado
```

#### `tests/unit/test_statistical_models.py`
```python
# Para cada modelo (frequentist, bootstrap, kde, bayesian):
# - probabilidades suman 1.0 (tolerancia 1e-6)
# - CI: ci_lower <= probability <= ci_upper
# - n_samples_used == len(events_df_filtrado)
# - warning == "insufficient_samples" cuando n < 5
# - familia gap_fill: warning == "no_gap_events" cuando ningún evento tiene gap
```

#### `tests/integration/test_api.py`
```python
# - GET /api/v1/control/health → 200
# - GET /api/v1/control/broker-status → 200, list de BrokerStatus
# - POST /api/v1/events/detect → 200, list[EventRecord] validado con schema
# - POST /api/v1/analysis/informative → 200, InformativeMetrics validado
# - POST /api/v1/analysis/probabilistic → 200, ProbabilisticResult con 3 familias
# - POST /api/v1/analysis/probabilistic con conditioning activo → n_samples_used <= n_total
# - POST /api/v1/analysis/probabilistic con bins custom → response refleja los bins
```

---

## Verificación final

```bash
# 1. Tests sin conexión real
pytest tests/unit/ -v --no-cov

# 2. Iniciar backend
uvicorn backend.main:app --reload --port 8100

# 3. Smoke test
curl -s http://localhost:8100/api/v1/control/health
curl -s http://localhost:8100/api/v1/control/broker-status

# 4. Detectar earnings AAPL (modo yfinance)
curl -s -X POST http://localhost:8100/api/v1/events/detect \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","source":"yfinance","event_type":"earnings"}'

# 5. Análisis probabilístico con bins custom
curl -s -X POST http://localhost:8100/api/v1/analysis/probabilistic \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","source":"yfinance","event_type":"earnings","model":"bootstrap","n_periods":5,"bins":[-0.08,-0.02,0.02,0.08]}'

# 6. Frontend
cd frontend && npm install && npm run dev
# → abrir http://localhost:5173
# → verificar BrokerStatusBadge: MDH rojo (no corriendo), yfinance verde
# → seleccionar AAPL, detectar earnings, verificar plots
# → editar bins en BinEditor → probabilidades se recalculan
# → aplicar condicionamiento EMA range → n_samples_used se reduce
```

---

## Consideraciones de seguridad (OWASP)

- Todos los inputs del usuario (symbol, bins, thresholds) validados con Pydantic antes de procesarlos
- `symbol` acepta solo `[A-Z]{1,5}` — validar con regex en schema
- `bins` validados: lista ordenada, entre -1.0 y 1.0, mínimo 2 elementos
- `n_periods` bounded: `Field(ge=1, le=60)`
- Credenciales MT5/TWS nunca en respuestas API ni en logs
- CORS restringido a `cors_origins` configurable (no `*` en producción)
- Sin SQL raw — no hay queries de usuario a base de datos en v1

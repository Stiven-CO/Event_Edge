# Phase 13 — Price Action Plot

## Objetivo

Agregar un plot opcional de **comportamiento promedio del precio** por debajo del panel de probabilidades.
El usuario activa el plot con un botón. El plot analiza cómo evoluciona el precio de forma promedio
en todos los eventos filtrados, con segmentación win/loss y bandas de ±1σ opcionales.

---

## Contrato de diseño

### Casos según horizonte

| Horizonte | Frecuencia | Rango del plot | Referencia (= 100) |
|-----------|-----------|----------------|--------------------|
| `n=0`     | 30 min    | P0: primer bar – último bar del día del evento | `open` diario de P0 |
| `n>0`     | Diario    | P1 → Pn (P0 **excluido** intencionalmente) | `close` de P0 |

**Por qué se excluye P0 en n>0:** el cierre del día del evento ya está incorporado en las métricas
de `close_return`; el plot quiere mostrar el comportamiento posterior al evento.

### Clasificación Win / Loss

| Horizonte | Win | Loss |
|-----------|-----|------|
| `n=0` | `(close_P0 − open_P0) / open_P0 > 0` (datos diarios) | ≤ 0 |
| `n>0` | `(close_Pn − close_P0) / close_P0 > 0` | ≤ 0 |

Ambas clasificaciones usan datos **diarios** como fuente de verdad. El retorno intradía de 30 min
no interviene en la clasificación.

### Normalización del eje Y

Todos los precios se re-expresan como índice relativo a la referencia:

```
precio_normalizado(t) = precio(t) / referencia × 100
```

- `referencia = open_P0` (datos diarios) para `n=0`
- `referencia = close_P0` (datos diarios) para `n>0`

La referencia siempre vale **100** en el eje Y.
Para `n=0` el primer bar de 30 min del día del evento abrirá ≈100; puede separarse ligeramente
por gap intradía.

### Banda ±1σ

```
banda_sup(t) = media(t) + std(t)
banda_inf(t) = media(t) − std(t)
```

`std(t)` se calcula sobre los `n_events` precios normalizados de la misma posición `t`.
La banda es **opcional** (toggle en la UI) y no diferencia win/loss (aplica solo al grupo activo).

### Umbral mínimo

`MIN_EVENTS_PLOT = 5` (igual que `MIN_SAMPLES` del módulo probabilístico).
Si un grupo (win o loss) tiene < 5 eventos se muestra advertencia y se deshabilita ese filtro.

### Datos intradía

- Fuente primaria: MDH cuando `EE_MDH_ENABLED=true`; fallback: yfinance.
- yfinance limita historial de 30 min a ≈60 días.  
  Si un evento no tiene barras de 30 min disponibles:  
  → se omite **silenciosamente** del plot (no del análisis probabilístico).  
  → se contabiliza en `n_events_omitted`.  
  → si `n_events_omitted > 0` se muestra advertencia no bloqueante en el footer del plot.

---

## Arquitectura

```
data/ → core/price_action/ → api/routers/price_action.py
```

### Capa `core/price_action/`

Crear módulo nuevo `backend/core/price_action/`:

```
backend/core/price_action/
    __init__.py          # exporta compute_price_action
    builder.py           # lógica de alineación, normalización y agregación
```

#### `builder.py` — función principal

```python
def compute_price_action(
    events_df: pd.DataFrame,      # eventos ya filtrados por conditioning
    ohlcv_daily_df: pd.DataFrame, # OHLCV diario
    ohlcv_intraday_df: pd.DataFrame | None,  # OHLCV 30min; None si n_periods > 0
    n_periods: int,
) -> PriceActionResult:
    ...
```

Flujo interno:

```
1. Seleccionar modo: intraday (n=0) vs daily (n>0)
2. Clasificar cada evento como win/loss usando datos DIARIOS
3. Para cada evento:
   a. Extraer serie de precios del rango correspondiente
   b. Normalizar a referencia = 100
   c. Alinear por posición (índice de barra o sesión)
4. Agregar series por grupo (all, win, loss): media(t), std(t)
5. Construir PriceActionSeries para cada grupo
6. Retornar PriceActionResult
```

**Manejo de barras faltantes (intraday):**

```python
if ts_event not in intraday_index:
    n_events_omitted += 1
    continue  # no RuntimeError, omisión silenciosa
```

**Alineación:**

- `n=0`: ordenar barras del día del evento por timestamp; índice 0 = primera barra (market open).
  Usar sólo barras del mismo día calendario del evento.  
  Número de barras = mínimo entre todas las series válidas para garantizar mismo largo de array.

- `n>0`: índice 1 = P1, índice 2 = P2, …, índice n = Pn.  
  Referencia de normalización = `close_P0` del OHLCV diario.  
  Si un evento no tiene `end_pos = pos + n_periods < len(df)`, se omite (igual que en `probabilistic.py`).

### Schemas (`backend/api/schemas.py`)

Agregar al final de la sección de responses:

```python
class PriceActionPoint(BaseModel):
    x: int            # índice de barra (intraday) o sesión (P1, P2 …)
    y: float          # precio normalizado (100 = referencia)

class PriceActionSeries(BaseModel):
    points: list[PriceActionPoint]
    band_upper: list[PriceActionPoint] | None  # None si toggle off en request
    band_lower: list[PriceActionPoint] | None

class PriceActionResult(BaseModel):
    """Respuesta para POST /api/v1/analysis/price-action."""
    anchor_mode: Literal["intraday_30min", "daily"]
    n_periods: int
    x_labels: list[str]           # "09:30"…"16:00" ó "P1"…"Pn"
    series_all:  PriceActionSeries
    series_win:  PriceActionSeries
    series_loss: PriceActionSeries
    n_events_all:     int
    n_events_win:     int
    n_events_loss:    int
    n_events_omitted: int         # sólo relevante en modo intraday
    warning: str | None           # "insufficient_events" | "some_events_omitted" | None
```

### Request schema

```python
class PriceActionRequest(BaseModel):
    """Body para POST /api/v1/analysis/price-action."""
    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    n_periods: int = Field(default=5, ge=0, le=60)
    include_bands: bool = True
    conditioning: ConditioningParams = Field(default_factory=ConditioningParams)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str: ...  # igual que AnalysisRequest
```

### Router (`backend/api/routers/price_action.py`)

```python
@router.post(
    "/price-action",
    response_model=PriceActionResult,
    summary="Price Action Plot",
    description="Precio promedio normalizado (índice 100) por grupo win/loss."
)
async def price_action_analysis(
    req: PriceActionRequest,
    settings: Settings = Depends(get_settings),
    mdh_client: MdhClient = Depends(get_mdh_client),
) -> PriceActionResult:
    ...
```

Flujo del router:

```
1. Cargar OHLCV diario (igual que probabilistic_analysis)
2. Si n_periods == 0: cargar OHLCV 30min (nuevo helper _load_ohlcv_intraday)
3. Detectar eventos + FeatureBuilder + conditioning (igual que en analysis.py)
4. Llamar compute_price_action(...)
5. Retornar PriceActionResult
```

Registrar en `backend/api/app.py`:

```python
from backend.api.routers import price_action as price_action_router
app.include_router(price_action_router.router, prefix="/api/v1/analysis")
```

#### Helper `_load_ohlcv_intraday`

```python
async def _load_ohlcv_intraday(
    symbol: str,
    source: str,
    settings: Settings,
    mdh_client: MdhClient,
    loader: EarningsLoader,
) -> tuple[pd.DataFrame, str]:
    """
    Igual que _load_ohlcv pero con intervalo 30min.
    Retorna (df_30min, source_used).
    Si no hay datos: retorna (DataFrame vacío, source_used).
    """
```

---

## Frontend

### Tipos (`frontend/src/api/types.ts`)

```typescript
export interface PriceActionPoint { x: number; y: number; }

export interface PriceActionSeries {
  points: PriceActionPoint[];
  band_upper: PriceActionPoint[] | null;
  band_lower: PriceActionPoint[] | null;
}

export interface PriceActionResult {
  anchor_mode: "intraday_30min" | "daily";
  n_periods: number;
  x_labels: string[];
  series_all:  PriceActionSeries;
  series_win:  PriceActionSeries;
  series_loss: PriceActionSeries;
  n_events_all:     number;
  n_events_win:     number;
  n_events_loss:    number;
  n_events_omitted: number;
  warning: "insufficient_events" | "some_events_omitted" | null;
}

export interface PriceActionRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  event_type: EventType;
  gap_threshold_pct?: number;
  n_periods: number;
  include_bands: boolean;
  conditioning: ConditioningParams;
}
```

### Store (`frontend/src/store/eventEdgeStore.ts`)

Nuevos campos de estado:

```typescript
priceActionResult: PriceActionResult | null;
isLoadingPriceAction: boolean;

// Acción
fetchPriceAction: () => Promise<void>;
```

### Endpoint (`frontend/src/api/endpoints.ts`)

```typescript
getPriceAction: (body: PriceActionRequest): Promise<PriceActionResult>
// POST /api/v1/analysis/price-action
```

### Hook (`frontend/src/hooks/usePriceAction.ts`)

```typescript
export function usePriceAction() {
  const { run, isLoading } = ...  // patrón igual que useAnalysis
}
```

### Componente `PriceActionPanel.tsx`

Ubicación en layout: **debajo de `ProbabilityPanel`**, inicialmente colapsado/oculto.

#### Estado interno del componente

```typescript
type FilterKey = "all" | "win" | "loss";
const [filter, setFilter] = useState<FilterKey>("all");
const [showBands, setShowBands] = useState(false);
```

#### Botón de activación

En `EventStudyPage.tsx` (o donde vivan los paneles de resultados):

```tsx
{probabilisticResult && (
  <button
    type="button"
    className="btn-ghost w-full text-sm"
    disabled={isLoadingPriceAction}
    onClick={() => fetchPriceAction()}
  >
    {isLoadingPriceAction ? "Cargando Price Action…" : "📈 Ver Price Action"}
  </button>
)}
{priceActionResult && <PriceActionPanel />}
```

#### Layout del panel

```
┌─────────────────────────────────────────────────────┐
│ Price Action          [insuffcient_events? badge]   │
│ Todos | Win | Loss      ☑ Banda ±1σ                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│   [Recharts ComposedChart — línea + área de banda]  │
│   Y: precio indexado (100 = referencia)             │
│   X: time labels ("09:30"…"16:00" ó "P1"…"Pn")     │
│                                                     │
├─────────────────────────────────────────────────────┤
│ N eventos: all / win / loss  | X omitidos [warn?]   │
└─────────────────────────────────────────────────────┘
```

#### Gráfico Recharts

Usar `ComposedChart` con:

- `<Line>` para la serie promedio (`dataKey="y"`)
- `<Area>` para la banda (cuando `showBands && band_upper !== null`):  
  `dataKey` = banda superior; segunda `<Area>` invertida para banda inferior

Colores:

| Filtro | Línea | Banda (fill) |
|--------|-------|--------------|
| `all`  | `#00d2c8` (accent) | `#00d2c8` al 15% opacidad |
| `win`  | `#22c55e` (green-500) | `#22c55e` al 15% |
| `loss` | `#ef4444` (red-500)   | `#ef4444` al 15% |

Eje Y: `tickFormatter={(v) => v.toFixed(0)}` con línea de referencia en `y=100` (`<ReferenceLine>`).  
Eje X: etiquetas de `x_labels` rotadas 45° si > 10 puntos.

---

## Tests

### Unitarios (`tests/unit/test_price_action.py`)

```python
@pytest.mark.unit
def test_daily_normalization():
    """close_P0 = referencia → primer punto normalizado = 100."""

@pytest.mark.unit
def test_intraday_normalization():
    """open_P0 diario = referencia → primer bar normalizado ≈ 100."""

@pytest.mark.unit
def test_win_loss_classification_daily():
    """Retorno P1:Pn > 0 → win; ≤ 0 → loss."""

@pytest.mark.unit
def test_win_loss_classification_intraday():
    """(close_P0 − open_P0)/open_P0 > 0 → win."""

@pytest.mark.unit
def test_insufficient_events_returns_warning():
    """< 5 eventos → warning = 'insufficient_events'."""

@pytest.mark.unit
def test_omit_event_without_intraday_data():
    """Evento sin barras de 30min → n_events_omitted += 1, no excepción."""

@pytest.mark.unit
def test_band_width_positive():
    """band_upper[i] >= series_all.points[i].y para todo i."""
```

### Integración (`tests/integration/test_api.py`)

```python
@pytest.mark.integration
async def test_price_action_daily(test_client):
    """n_periods=5 → anchor_mode='daily', x_labels=['P1','P2','P3','P4','P5']."""

@pytest.mark.integration
async def test_price_action_intraday_omits_old_events(test_client):
    """Con datos 30min vacíos → n_events_omitted > 0, warning='some_events_omitted'."""
```

---

## Consideraciones de implementación

1. **Alineación de largo de series:** garantizar que todas las listas de puntos tengan
   exactamente el mismo largo. En `n>0` siempre `n_periods` puntos (P1…Pn).
   En `n=0` = mínimo número de barras completas compartidas por todos los eventos válidos.

2. **Grupos vacíos:** si `n_events_win < MIN_EVENTS_PLOT`, retornar `series_win` con
   `points=[]` y `band_upper=None`; el frontend deshabilitará el botón "Win".

3. **No duplicar carga OHLCV:** en el router reutilizar los helpers `_load_ohlcv` y
   `_detect_events` ya existentes en `analysis.py` — moverlos a un módulo compartido
   `backend/api/routers/_common.py` si aún no existe.

4. **MDH intraday:** el helper `_load_ohlcv_intraday` debe pasar `interval="30m"` al cliente
   MDH/yfinance. Mantener la misma firma de fallback que `_load_ohlcv`.

5. **Performance:** la agregación de precios puede hacerse con `np.nanmean` y `np.nanstd`
   sobre una matriz `(n_events × n_bars)` para eficiencia.

6. **include_bands=False en request:** el backend devuelve `band_upper=None` y `band_lower=None`
   en todas las series. No calcular std si no se requiere.

---

## Orden de implementación sugerido

```
1. backend/api/schemas.py                  (PriceActionPoint, PriceActionSeries, PriceActionResult, PriceActionRequest)
2. backend/core/price_action/builder.py    (lógica core)
3. backend/api/routers/price_action.py     (endpoint + _load_ohlcv_intraday)
4. backend/api/app.py                      (registrar router)
5. tests/unit/test_price_action.py
6. frontend/src/api/types.ts               (nuevos tipos)
7. frontend/src/api/endpoints.ts           (getPriceAction)
8. frontend/src/store/eventEdgeStore.ts    (priceActionResult, fetchPriceAction)
9. frontend/src/hooks/usePriceAction.ts
10. frontend/src/components/PriceActionPanel.tsx
11. EventStudyPage.tsx                     (botón + render condicional)
12. tests/integration/test_api.py          (nuevos casos)
```

---
mode: agent
description: >
  Fase 10 — Frontend de Event Edge: scaffolding Vite/React/Tailwind,
  cliente HTTP tipado y todos los componentes UI de la herramienta de estudio de eventos.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - run_in_terminal
  - file_search
---

# Fase 10 — Frontend

## Prerrequisitos

- Fase 9 completada: todos los endpoints de la API están funcionando
- Leer antes de implementar:
  - `market_data_hub/frontend/src/api/client.ts` → patrón de cliente HTTP tipado
  - `Backtest_Forge/frontend/package.json` → versiones de dependencias React/Vite/Tailwind
  - `Event_Edge/.github/instructions/global.instructions.md` → convenciones frontend

## Objetivo

Crear el frontend completo en `Event_Edge/frontend/`.
Al finalizar:
- `npm run dev` arranca en `localhost:5173` sin errores de TypeScript
- El layout de 3 paneles se visualiza correctamente
- `BrokerStatusBadge` muestra estado real del backend
- El flujo completo funciona: seleccionar activo → detectar eventos → ver probabilidades

## Archivos de configuración

### `Event_Edge/frontend/package.json`
```json
{
  "name": "event-edge-ui",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "zustand": "^4.5.0",
    "recharts": "^2.12.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.3",
    "typescript": "^5.4.5",
    "vite": "^5.2.11"
  }
}
```

### `Event_Edge/frontend/vite.config.ts`
Proxy `/api` → `http://localhost:8100` para desarrollo.

### `Event_Edge/frontend/tailwind.config.ts`
Configurar `content` para `./src/**/*.{ts,tsx}`.

### `Event_Edge/frontend/tsconfig.json` y `tsconfig.node.json`
Mismo patrón que `Backtest_Forge/frontend/tsconfig.json`.

### `Event_Edge/frontend/postcss.config.js`
Tailwind + autoprefixer.

---

## Capa de API

### `Event_Edge/frontend/src/api/client.ts`
```typescript
/**
 * Cliente HTTP base para Event Edge API.
 * Patrón: mismo que market_data_hub/frontend/src/api/client.ts
 * Sin API key en frontend — el backend maneja autenticación con brokers.
 */
const BASE_URL = import.meta.env.VITE_EE_API_BASE ?? "/api/v1";

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = { request };
```

### `Event_Edge/frontend/src/api/types.ts`
Tipos TypeScript espejo de `backend/api/schemas.py`:
```typescript
export type EventType = "earnings" | "gap";
export type ModelType = "frequentist" | "bootstrap" | "kde" | "bayesian";
export type GuidanceDirection = "raised" | "maintained" | "lowered" | "not_available";
export type BBPosition = "below_lower" | "in_lower" | "middle" | "in_upper" | "above_upper";

export interface BrokerStatus { source: string; alive: boolean; mode: string; detail: string | null; }
export interface EventRecord { date: string; event_type: EventType; symbol: string; gap_pct: number | null; /* ... */ }
export interface ScenarioBin { label: string; lower: number | null; upper: number | null; probability: number; ci_lower: number; ci_upper: number; event_count: number; }
export interface ProbabilisticFamily { family: string; n_periods: number; n_samples_used: number; n_total_events: number; warning: string | null; scenarios: ScenarioBin[]; }
export interface ProbabilisticResult { symbol: string; model: ModelType; data_source: string; families: ProbabilisticFamily[]; }
export interface InformativeMetrics { symbol: string; event_type: EventType; n_total_events: number; frequency_per_year: number; /* ... */ }
export interface ConditioningParams { /* todos opcionales, espejo de Python */ }
export interface AnalysisRequest { symbol: string; source: string; event_type: EventType; model: ModelType; n_periods: number; bins: number[]; conditioning: ConditioningParams; }
```

### `Event_Edge/frontend/src/api/endpoints.ts`
Funciones tipadas para cada endpoint:
```typescript
import { api } from "./client";
import type { BrokerStatus, EventRecord, InformativeMetrics, ProbabilisticResult, AnalysisRequest } from "./types";

export const endpoints = {
  getBrokerStatus: () => api.request<BrokerStatus[]>("/control/broker-status"),
  getAssets: (assetClass = "equity") => api.request<AssetInfo[]>(`/assets?asset_class=${assetClass}`),
  detectEvents: (body: DetectEventsRequest) => api.request<EventRecord[]>("/events/detect", { method: "POST", body: JSON.stringify(body) }),
  getInformativeMetrics: (body: InformativeRequest) => api.request<InformativeMetrics>("/analysis/informative", { method: "POST", body: JSON.stringify(body) }),
  getProbabilisticMetrics: (body: AnalysisRequest) => api.request<ProbabilisticResult>("/analysis/probabilistic", { method: "POST", body: JSON.stringify(body) }),
};
```

---

## Store global (Zustand)

### `Event_Edge/frontend/src/store/eventEdgeStore.ts`
```typescript
interface EventEdgeState {
  // Selección
  symbol: string;
  eventType: EventType;
  model: ModelType;
  nPeriods: number;
  bins: number[];
  conditioning: ConditioningParams;

  // Resultados
  events: EventRecord[];
  informativeMetrics: InformativeMetrics | null;
  probabilisticResult: ProbabilisticResult | null;
  brokerStatuses: BrokerStatus[];

  // Estado de carga
  isLoadingEvents: boolean;
  isLoadingMetrics: boolean;
  error: string | null;

  // Acciones
  setSymbol: (s: string) => void;
  setEventType: (t: EventType) => void;
  setModel: (m: ModelType) => void;
  setNPeriods: (n: number) => void;
  setBins: (b: number[]) => void;
  setConditioning: (c: ConditioningParams) => void;
  fetchBrokerStatus: () => Promise<void>;
  fetchEvents: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
}
```

---

## Hooks

### `Event_Edge/frontend/src/hooks/useEvents.ts`
Hook que lee `symbol`, `eventType` del store y llama `endpoints.detectEvents()`.
Actualiza `events`, `isLoadingEvents` y `error` en el store.

### `Event_Edge/frontend/src/hooks/useAnalysis.ts`
Hook que llama `endpoints.getInformativeMetrics()` y `endpoints.getProbabilisticMetrics()`
en paralelo. Actualiza el store.

---

## Componentes

### `BrokerStatusBadge.tsx`
```tsx
// Props: source: "mdh" | "mt5" | "tws" | "yfinance"
// Polling a GET /api/v1/control/broker-status cada 30 segundos
// Muestra: punto verde + nombre si alive, punto rojo + "(off)" si no
// Tooltip: mode (primary / fallback / disabled)
```

### `AssetSelector.tsx`
```tsx
// Input text con validación: solo [A-Z]{1,5}
// Botón "Buscar" → dispara fetchEvents
// Muestra el símbolo activo en el store
```

### `EventTypeTabs.tsx`
```tsx
// Tabs: "Earnings" | "Gap"
// Al cambiar → actualiza eventType en store y limpia resultados
```

### `ModelSelector.tsx`
```tsx
// Select: Frequentist | Bootstrap | KDE | Bayesian
// Tooltip con descripción breve de cada modelo
```

### `PeriodSelector.tsx`
```tsx
// Slider o input numérico: 1-60 sesiones
// Label: "N sesiones de trading"
```

### `BinEditor.tsx`
```tsx
// Lista editable de thresholds
// Input: bins: number[] en decimal (ej. [-0.05, -0.01, 0.01, 0.05])
// Muestra como porcentaje: "-5%, -1%, +1%, +5%"
// Botón "Reset" → restaurar [-0.05, -0.01, 0.01, 0.05]
// Validación:
//   - Mínimo 2 elementos
//   - Ordenados de menor a mayor
//   - Todos entre -1.0 y 1.0
// Mostrar error inline si validación falla; no permite aplicar si hay error
```

### `ConditioningPanel.tsx`
```tsx
// Controles por variable:
// - ema5_range_pct: RangeSlider [-20, +20]%
// - ema20_range_pct: RangeSlider [-20, +20]%
// - open_vs_prev_close_pct: RangeSlider [-10, +10]%
// - bb_position: CheckboxGroup (5 opciones)
// - gap_direction: RadioGroup (any | positive | negative)
// - gap_pct: RangeSlider [0, 15]%
// - eps_surprise_pct: RangeSlider (visible solo si eventType = earnings)
// - guidance: CheckboxGroup (visible solo si eventType = earnings)
// Contador visible: "N condicionados / M totales"
// Botón "Aplicar" → llama fetchMetrics()
// Botón "Limpiar filtros" → resetea ConditioningParams a defaults
```

### `MetricsInfoPanel.tsx`
```tsx
// Muestra InformativeMetrics:
// - Número total de eventos y frecuencias
// - Gráfico de barras: avg_movement_range por período (usando recharts)
// - Gráfico de barras: avg_candle_range por período
// - Stats del gap: mean ± std (si disponible)
// Header: "Fuente: MDH" o "Fuente: yfinance (dev)"
```

### `ProbabilityPanel.tsx`
```tsx
// Muestra ProbabilisticResult:
// - Selector de familia: close_return | close_vs_event | gap_fill
// - Gráfico de barras horizontales: probability + CI por ScenarioBin (recharts)
// - Footer: "n_samples_used / n_total_events eventos"
// - Badge warning si present (insufficient_samples, no_gap_events)
```

### `EarningsTable.tsx`
```tsx
// Tabla de EventRecord (solo earnings):
// Columnas: Fecha | Gap% | EPS Actual | EPS Estimado | Sorpresa% | Guidance
// Ordenable por fecha (desc por defecto)
// Sin paginación en v1 (scroll)
```

### Layout `EventStudyPage.tsx`
```
┌────────────────────────────────────────────────────────────────┐
│  Event Edge  │  BrokerStatusBadge(mdh) BrokerStatusBadge(yf)  │
├──────────────┬─────────────────────────┬───────────────────────┤
│ LEFT (w-64)  │ CENTER (flex-1)         │ RIGHT (w-80)          │
│ AssetSelector│ MetricsInfoPanel        │ ProbabilityPanel      │
│ EventTypeTabs│ EarningsTable           │                       │
│ ModelSelector│                         │                       │
│ PeriodSelect │                         │                       │
│ BinEditor    │                         │                       │
│ Conditioning │                         │                       │
└──────────────┴─────────────────────────┴───────────────────────┘
```

---

## Criterios de aceptación

```bash
# Desde Event_Edge/frontend/
npm install
npm run build     # sin errores TypeScript

npm run dev
# → abrir http://localhost:5173
```

Checklist visual:
- [ ] Layout 3 paneles visible, responsive a pantalla ancha
- [ ] `BrokerStatusBadge` muestra MDH rojo (no corre) y yfinance verde
- [ ] AssetSelector: escribir "AAPL" → click Buscar → eventos cargados
- [ ] EarningsTable muestra fechas y EPS
- [ ] MetricsInfoPanel muestra gráficos de rango
- [ ] ProbabilityPanel muestra probabilidades con CI
- [ ] BinEditor: editar bins → probabilidades se recalculan al Aplicar
- [ ] ConditioningPanel: activar filtro EMA → contador se reduce
- [ ] "aapl" minúsculas → error de validación visible, no dispara request

## Restricciones

- Nunca guardar credenciales en `localStorage`
- `VITE_EE_API_BASE` como variable de entorno — sin URL hardcodeada en código
- Sin `console.log` de datos de precios en producción
- `BinEditor` muestra error inline pero no bloquea otros controles del panel

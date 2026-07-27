# Event Edge — Coding Standards & Convenciones

## Lenguaje y entorno

- Python 3.11+ / conda env dedicado `envs/event_edge`
- FastAPI + pydantic-settings v2 (prefijo `EE_`)
- React 18 + Vite 5 + TypeScript 5 + TailwindCSS 3 (frontend)
- yfinance para earnings metadata y OHLCV en modo dev
- scipy, numpy, pandas para cálculos estadísticos

## Arquitectura de capas

```
data/ → core/ → api/
  mdh_client         event_detector     routers/
  earnings_loader    feature_builder      assets
                     statistical_models   events
                     metrics              analysis
                     volume_profile (v2)
```

- Desacoplamiento estricto entre capas: `data → core → api`
- `core/` no importa nada de `api/`; `data/` no importa nada de `core/` ni `api/`
- Cada función de cálculo es pura cuando es posible (sin side-effects implícitos)

## Fuentes de datos

- **OHLCV primaria**: market_data_hub (MDH) vía HTTP `POST /api/v1/data/query`
- **OHLCV fallback**: yfinance cuando `EE_MDH_ENABLED=false` o MDH no responde
- **Earnings metadata**: siempre yfinance (`ticker.earnings_dates`, `ticker.calendar`)
- La UI muestra el estado de MDH con indicador visual verde/rojo
- Nunca mezclar fuentes para el mismo activo en un mismo cálculo

## Autenticación de fuentes de datos

- **MT5**: credenciales `login`, `password`, `server` — leídas de variables de entorno `EE_MT5_*`
  - Nunca persistir `password` en localStorage ni en logs
  - Solo `login` y `server` pueden mostrarse en UI
- **TWS**: requiere `EE_TWS_API_KEY` como variable de entorno
  - Sin API key = error explícito, no fallback silencioso
- **yfinance**: sin credenciales, uso público
- El endpoint `/api/v1/control/broker-status` reporta disponibilidad de cada fuente

## Convenciones Python

- `snake_case` para funciones y variables
- `PascalCase` para clases
- Tipos explícitos en todas las firmas públicas
- Sin estado global; dependencias inyectadas via FastAPI `Depends`
- `get_settings()` usa variable de módulo `_settings`; reset con `_settings = None` en tests
- Fechas: siempre UTC; tipo `datetime` con `tzinfo` — nunca naive
- P(n): número de sesiones de trading configurado por el usuario; siempre `int >= 1`

## Contratos de datos

- `EventRecord`: unidad mínima de evento con campos `date`, `event_type`, `gap_pct`, `eps_surprise_pct`, `eps_actual`, `eps_estimate`, `revenue_surprise_pct`
- `ConditioningParams`: filtros opcionales; `None` = sin condicionamiento
- `ScenarioBins`: lista de floats configurada por el usuario (ej. `[-0.05, -0.02, 0, 0.02, 0.05]`), nunca hardcodeada en el backend
- `ProbabilisticResult`: siempre incluye `n_samples_used` y `n_total_events`

## Bins de escenarios

- Los bins son configurables por el usuario desde la UI
- El backend acepta `bins: list[float]` — nunca usa bins fijos en lógica de negocio
- Default sugerido desde frontend: `[-0.05, -0.02, 0, 0.02, 0.05]`
- Si `n_samples_used < 5` la respuesta incluye `warning: "insufficient_samples"`

## Frontend

- Estado MDH: componente `<BrokerStatusBadge source="mdh" />` — verde si `alive`, rojo si no
- Bins editables: componente `<BinEditor />` — lista editable de thresholds en porcentaje
- Fuente activa mostrada en header del panel de resultados: "Fuente: MDH" | "Fuente: yfinance (dev)"
- Nunca hardcodear URLs; usar `VITE_EE_API_BASE` con default `/api/v1`
- Contraseñas/API keys nunca van a `localStorage`; solo `login` y `server` MT5 pueden persistirse

## Tests

- pytest + httpx; fixtures en `conftest.py`
- Marcadores: `unit`, `integration`, `smoke`
- Tests sin conexión real a broker/MDH: usar fixtures de eventos sintéticos
- `--no-cov` para ejecución rápida
- Un test que requiera yfinance real debe marcarse `@pytest.mark.integration`

## Seguridad

- Sin credenciales en código fuente ni en logs
- `EE_TWS_API_KEY` vacío → error 403 explícito en endpoints que usan TWS
- CORS configurado solo para orígenes locales en desarrollo
- Inputs del usuario (bins, thresholds, symbols) validados con Pydantic antes de procesarlos

# Métricas de Event Edge — fórmulas y ubicación de cálculo

Referencia técnica de cada métrica que produce el backend: fórmula, dónde se calcula, y con qué datos. Pensada tanto para mantenimiento propio como para que Risk Engine sepa exactamente qué representa cada campo que consume del objeto Edge.

---

## 1. Métricas globales (línea base del activo)

Módulo: `backend/core/metrics/informative.py::compute_global_metrics`. Endpoint: `POST /api/v1/analysis/informative`. Se calculan sobre el historial completo de OHLCV del símbolo (`ohlcv_df["close"].pct_change()`), sin condicionamiento por eventos.

| Métrica | Fórmula | Función |
|---|---|---|
| `return_mean`, `return_median`, `return_std` | media / mediana / desvío estándar (ddof=1) de los retornos diarios | `compute_global_metrics` |
| `return_skewness` | `scipy.stats.skew(returns)` (requiere n≥3) | `compute_global_metrics` |
| `return_kurtosis` | `scipy.stats.kurtosis(returns)` (excess, Fisher; requiere n≥4) | `compute_global_metrics` |
| `return_min`, `return_max` | `np.min`/`np.max` de los retornos diarios | `compute_global_metrics` |
| `annualized_vol` | `return_std * sqrt(252)` | `compute_global_metrics` |
| `atr_mean` | ATR(14) vía EWM(span=14) sobre `max(high-low, |high-close_prev|, |low-close_prev|)` | `_compute_atr` |
| `rolling_vol_30d` | desvío estándar rolling de 30 sesiones, anualizado (`*sqrt(252)`), últimos 500 puntos | `compute_global_metrics` |
| `hurst_exponent` | exponente de Hurst por método R/S clásico (pendiente log-log de R/S vs. lag); `None` si n<50 | `_hurst_exponent_rs` |
| `autocorr_lag1/5/10` | autocorrelación de los retornos en lags 1, 5 y 10 sesiones | `compute_global_metrics` |
| `return_histogram`, `qqplot_data` | histograma (10–50 bins según n) y cuantiles teóricos-vs-muestrales normales, para plots del frontend | `compute_global_metrics` |

---

## 2. Análisis Condicionado (`ConditionedSummary`)

Módulo: `backend/api/routers/analysis.py::_build_conditioned_summary`. Endpoint: `POST /api/v1/analysis/probabilistic` (campo `conditioned_summary`). Se calcula sobre `conditioned_df` (eventos que pasan los filtros de condicionamiento — `apply_conditioning`) + `ohlcv_df` diario.

### 2.1 — Frecuencia y estadísticas del día del evento (P0)

| Métrica | Fórmula | Referencia de precio |
|---|---|---|
| `filter_rate` | `n_conditioned_events / n_total_events` | — |
| `frequency_per_year` / `frequency_per_quarter` | `n_conditioned_events / años_cubiertos_por_ohlcv` (y ÷4) | — |
| `gap_mean` / `gap_std` | media/std de `gap_pct` (excluyendo ceros) | — |
| `event_day_range_mean/std` | media/std de `(high - low) / close` en P0 | día del evento (P0) |
| `event_day_volume_mean/std` | media/std del volumen en P0 | día del evento (P0) |
| `event_day_return_mean/std` | media/std de `(close - open) / open` en P0 | apertura→cierre de P0 |

### 2.2 — Tabla de forward returns fijos (`avg_forward_return`)

Períodos fijos `[1, 3, 5, 10]` sesiones. Usa `P1-open → Pn-close`: el retorno desde la apertura de la sesión siguiente al evento hasta el cierre de la sesión `n`.

### 2.3 — Estadísticas extendidas del retorno (sobre `return_samples_close`)

`return_samples_close` es el retorno `P1-open → Pn-close` de cada evento condicionado al período `n_periods` elegido por el usuario (misma convención que la tabla de la sección 2.2). Todas estas métricas se calculan sobre esa serie. Función: `_extended_stats` en `analysis.py`.

| Métrica | Fórmula | Condición mínima |
|---|---|---|
| `return_max` / `return_min` | `np.max` / `np.min` de `return_samples_close` | n≥1 |
| `return_avg_positive` | media de los valores `> 0` | al menos 1 valor positivo |
| `return_avg_negative` | media de los valores `< 0` | al menos 1 valor negativo |
| `return_count_positive` / `return_count_negative` | conteo de valores `>0` / `<0` (los ceros exactos no cuentan en ninguno) | siempre definido (puede ser 0) |
| `return_skewness` | `scipy.stats.skew(return_samples_close)` | n≥3, si no `None` |
| `return_kurtosis` | `scipy.stats.kurtosis(return_samples_close)` (excess) | n≥4, si no `None` |

**Nota de fiabilidad**: `return_skewness`/`return_kurtosis` son estadísticamente poco confiables con muestras pequeñas (n<10-20) aunque scipy los calcule desde n=3/4. La UI muestra `n_conditioned_events` junto a estas métricas para que el usuario juzgue la confiabilidad.

**Nota conocida — divergencia con Price Action**: `return_count_positive`/`return_count_negative` (mostrado como "N+ / N−" en la UI) usa siempre la referencia `P1-open → Pn-close`. El panel de Price Action (`backend/core/price_action/builder.py`) clasifica win/loss con una referencia distinta según el modo (`P0-close → Pn-close` en modo `holding`; ventana intradía del evento en modo `inside_event` — ver sección 5). Por eso ambos conteos **pueden no coincidir** para el mismo símbolo/condicionamiento: son dos métricas con metodologías de cálculo diferentes, no un bug. Unificar ambas referencias fue evaluado y revertido en esta fase por decisión del usuario (cambio de mayor alcance, pendiente para una iteración futura si se decide abordarlo).

---

## 3. Escenario-bins probabilísticos (`ProbabilisticFamily`)

Módulo: `backend/core/metrics/probabilistic.py::compute_probabilistic_metrics`. Endpoint: `POST /api/v1/analysis/probabilistic` (campo `families`, siempre 2: `close_return` y `gap_fill`).

- Construye columnas de retorno forward (`ret_close_p{n}`) y de gap-fill (`gap_fill_p{n}`) sobre `events_df` para el `n_periods` elegido (misma convención `P1-open → Pn-close`).
- Ajusta el modelo estadístico seleccionado (`frequentist` | `bootstrap` | `kde` | `bayesian`, `backend/core/statistical_models/`) con los eventos válidos.
- El modelo predice la probabilidad de que el retorno caiga en cada bin (`bins` del request) para `close_return`, y la probabilidad de gap-fill (bin único en 0.5) para `gap_fill`.
- `warning` es `"insufficient_samples"` si `n_samples_used` es muy bajo, o `"no_gap_events"` si no hubo eventos con gap.

---

## 4. Price Action Plot (`PriceActionResult`)

Módulo: `backend/core/price_action/builder.py::compute_price_action`. Endpoint: `POST /api/v1/analysis/price-action`.

- Clasifica cada evento condicionado en `win`/`loss` según el modo activo:
  - `holding` (n_periods>0): referencia `close(P0) → close(Pn)` — `_build_holding`.
  - `inside_event` (n_periods=0), ventana de un día: referencia `open(P0) → close(P0)` — `_build_inside_event`.
  - `inside_event`, ventana multi-día (`outer_timeframe` en `{"1w","1mo","3mo","6mo","1y"}`): referencia `open` de la primera barra de la ventana → `close` de la última barra.
- Normaliza el precio de cada evento a índice 100 en el punto de referencia, y agrega media + bandas ±1σ por grupo (`all`/`win`/`loss`) vía `_aggregate_series`.
- `n_events_omitted` cuenta eventos sin datos intradía disponibles (solo relevante en modo `inside_event`).
- `warning` es `"insufficient_events"` si `n_events_all < MIN_EVENTS_PLOT` (5), o `"some_events_omitted"` si hubo eventos omitidos.

---

## 5. Objeto Edge persistido

Endpoint: `POST /api/v1/analysis/save`. Módulo: `backend/core/edge/assembler.py::assemble_edge_payload`. Persistencia: `backend/core/edge/store.py::FilesystemEdgeStore`.

- El Edge **recalcula** `/probabilistic` con los parámetros recibidos (no confía en un resultado previo del cliente), para garantizar que lo persistido refleje un cómputo real y reproducible.
- `edge.json` contiene: `ConditionedSummary` completo **sin** `return_samples_close` (secciones 2.1–2.3 de este documento), `risk_metrics` (`win_rate`, `payoff_ratio`, `expectancy` — ver fórmulas abajo, calculadas solo al momento de persistir, no forman parte de `ConditionedSummary` ni de la respuesta de `/probabilistic`), y `families` (sección 3).
- `return_samples.parquet` contiene las muestras crudas de `return_samples_close` (columna `return_close`) — se guarda aparte por ser mucho más económico que un array de miles de floats embebido en JSON. Necesario para que Risk Engine pueda hacer bootstrap/resampling no paramétrico sobre la distribución real, en vez de depender solo de los momentos (mean/std/skew/kurtosis) ya presentes en `edge.json`.
- Estructura en disco: `data/{symbol}/{timeframe}/{run_id}/edge.json` + `data/{symbol}/{timeframe}/{run_id}/return_samples.parquet`.
- No se generan ni persisten imágenes (plots) — los gráficos son responsabilidad exclusiva del frontend (Recharts), a partir de los datos ya devueltos por los endpoints de análisis.

### 5.1 — `risk_metrics` (`win_rate`, `payoff_ratio`, `expectancy`)

Calculadas en `backend/core/edge/assembler.py::_derive_risk_metrics`, a partir de los campos de `ConditionedSummary` ya descritos en la sección 2.3 (`return_count_positive/negative`, `return_avg_positive/negative`):

| Métrica | Fórmula | Condición |
|---|---|---|
| `win_rate` | `count_positive / (count_positive + count_negative)` | al menos 1 evento clasificado |
| `payoff_ratio` | `avg_positive / abs(avg_negative)` | requiere ambos definidos y `avg_negative != 0` |
| `expectancy` | `win_rate * avg_positive + (1 - win_rate) * avg_negative` | requiere `win_rate` definido |

Estas 3 métricas **solo existen en el objeto Edge persistido** — no se exponen en `/probabilistic` ni en la UI en esta fase (evaluado y revertido; ver nota de la sección 2.3).

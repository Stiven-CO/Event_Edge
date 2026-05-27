---
mode: agent
description: >
  Fase 7 — Métricas informativas de Event Edge: implementa compute_informative_metrics
  para calcular estadísticas descriptivas de eventos sin condicionamiento.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 7 — Métricas Informativas

## Prerrequisitos

- Fases 1-6 completadas: schemas (`InformativeMetrics`, `EventRecord`, `EventType`) existen
- Leer `Event_Edge/.github/instructions/global.instructions.md` → convenciones de cálculo

## Objetivo

Implementar `compute_informative_metrics()` en `backend/core/metrics/informative.py`.
Esta función responde a `POST /api/v1/analysis/informative` y NO aplica condicionamiento;
trabaja sobre todos los eventos detectados.

**Sin look-ahead**: todos los cálculos son posteriores al open del evento.

## Archivos a crear

### `Event_Edge/backend/core/metrics/__init__.py`
Exportar `compute_informative_metrics`, `compute_probabilistic_metrics`.

### `Event_Edge/backend/core/metrics/informative.py`

```python
"""
Métricas informativas: estadísticas descriptivas sobre el universo completo
de eventos detectados. Sin condicionamiento, sin modelos estadísticos.

No hay look-ahead: todos los cálculos usan datos posteriores al open del evento.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from backend.api.schemas import EventRecord, EventType, InformativeMetrics


def compute_informative_metrics(
    ohlcv_df: pd.DataFrame,
    events: list[EventRecord],
    periods: list[int],
    data_source: str,
) -> InformativeMetrics:
    """
    Calcula métricas informativas sobre todos los eventos.

    Args:
        ohlcv_df: DataFrame OHLCV con index DatetimeIndex UTC
        events: Lista de EventRecord detectados (sin filtrar)
        periods: Lista de períodos a calcular, ej. [1, 3, 5, 10]
        data_source: "mdh" o "yfinance"

    Returns:
        InformativeMetrics con:
            - n_total_events: número de eventos
            - frequency_per_year: promedio de eventos por año calendario
            - frequency_per_quarter: promedio de eventos por trimestre
            - avg_movement_range: {n: {mean, std}} para cada período en periods
            - avg_candle_range: {n: {mean, std}} para cada período en periods
            - gap_mean, gap_std: estadísticas del gap_pct (solo eventos con gap != 0)
    """
    ...
```

## Definición de métricas

### `avg_movement_range[n]`
```
movement_range_n = (max(high[P0..Pn]) - min(low[P0..Pn])) / close_P0
```
- `P0` = sesión del evento
- `Pn` = n-ésima sesión posterior al evento
- Si no hay n sesiones posteriores disponibles → excluir ese evento del cálculo

### `avg_candle_range[n]`
```
candle_range_n = (high_Pn - low_Pn) / close_P0
```
- Solo la vela de la sesión Pn (no el rango acumulado)

### `frequency_per_year`
```python
n_years = (ohlcv_df.index.max() - ohlcv_df.index.min()).days / 365.25
frequency_per_year = len(events) / n_years  # si n_years > 0
```

### `frequency_per_quarter`
```python
frequency_per_quarter = frequency_per_year / 4
```

### `gap_mean` y `gap_std`
- Usar solo eventos donde `gap_pct is not None and gap_pct != 0`
- Si ningún evento tiene gap → `gap_mean = None`, `gap_std = None`

## Criterios de aceptación

```python
# Validación mínima (usa datos sintéticos de conftest Fase 12)

from backend.core.metrics.informative import compute_informative_metrics
from backend.api.schemas import EventRecord, EventType, GuidanceDirection
from datetime import datetime, timezone
import pandas as pd
import numpy as np

# Crear OHLCV sintético: 500 días
dates = pd.bdate_range("2022-01-01", periods=500, freq="B", tz="UTC")
np.random.seed(42)
close = 100 * np.cumprod(1 + np.random.normal(0, 0.01, 500))
ohlcv = pd.DataFrame({
    "open": close * np.random.uniform(0.99, 1.01, 500),
    "high": close * np.random.uniform(1.00, 1.02, 500),
    "low":  close * np.random.uniform(0.98, 1.00, 500),
    "close": close,
    "volume": np.random.randint(1_000_000, 5_000_000, 500).astype(float),
}, index=dates)

# Crear 5 eventos en fechas conocidas
events = [
    EventRecord(
        date=dates[50], event_type=EventType.earnings, symbol="AAPL",
        gap_pct=0.03, eps_actual=1.5, eps_estimate=1.4,
        eps_surprise_pct=0.07, revenue_actual=None, revenue_estimate=None,
        revenue_surprise_pct=None, guidance="not_available",
    ),
    # ... más eventos
]

metrics = compute_informative_metrics(ohlcv, events, periods=[1, 3, 5], data_source="yfinance")

assert metrics.n_total_events == len(events)
assert metrics.frequency_per_year > 0
assert 1 in metrics.avg_movement_range
assert "mean" in metrics.avg_movement_range[1]
assert "std" in metrics.avg_movement_range[1]
assert metrics.avg_movement_range[1]["mean"] > 0  # rango siempre positivo
print("Métricas informativas OK")
```

## Restricciones

- Sin imports de `api/routers/` ni de `data/`
- Eventos al final de la serie sin N sesiones completas → excluir del cálculo de ese período
  (no excluir el evento completo, solo del promedio del período N)
- Si `len(events) == 0` → retornar `InformativeMetrics` con todos los campos numéricos en 0
  o None según corresponda; sin excepción
- No modificar `ohlcv_df` ni `events`
- `movement_range` siempre >= 0 (es un rango de precios)

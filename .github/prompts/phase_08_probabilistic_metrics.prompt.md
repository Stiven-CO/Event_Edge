---
mode: agent
description: >
  Fase 8 — Métricas probabilísticas de Event Edge: implementa compute_probabilistic_metrics
  orquestando las 3 familias de retornos con el modelo estadístico seleccionado.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 8 — Métricas Probabilísticas

## Prerrequisitos

- Fases 1-7 completadas: schemas, modelos estadísticos y métricas informativas existen
- Revisar `backend/core/statistical_models/base.py` → contrato de `BaseEventModel`
- Revisar `backend/api/schemas.py` → `ProbabilisticResult`, `ProbabilisticFamily`, `ScenarioBin`

## Objetivo

Implementar `compute_probabilistic_metrics()` en `backend/core/metrics/probabilistic.py`.
Orquesta las 3 familias de análisis usando el modelo estadístico indicado:
1. `close_return` — retorno del close respecto al open del evento
2. `close_vs_event` — retorno del close respecto al close del evento
3. `gap_fill` — probabilidad de que el gap se cierre en N sesiones

## Archivos a crear / modificar

### `Event_Edge/backend/core/metrics/probabilistic.py`

```python
"""
Métricas probabilísticas: calcula las 3 familias de escenarios usando
el modelo estadístico seleccionado.

Assumptions:
    - events_df ya está filtrado por condicionamiento (responsabilidad del router)
    - events_df tiene columnas de retorno forward calculadas aquí o por el caller
    - Eventos al final de la serie sin N sesiones completas → excluidos de n_samples_used
    - n_samples_used se reporta por familia (puede diferir en gap_fill)
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from backend.api.schemas import (
    ProbabilisticResult, ProbabilisticFamily, ModelType
)
from backend.core.statistical_models.base import BaseEventModel


def compute_probabilistic_metrics(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    model: BaseEventModel,
    model_type: ModelType,
    n_periods: int,
    bins: list[float],
    symbol: str,
    data_source: str,
) -> ProbabilisticResult:
    """
    Calcula ProbabilisticResult con 3 familias de métricas.

    Flujo:
        1. Calcular columnas de retorno forward para n_periods sobre ohlcv_df + events_df
        2. Excluir eventos sin n sesiones completas disponibles
        3. Ajustar modelo con eventos válidos
        4. Predecir cada familia
        5. Construir ProbabilisticResult con las 3 ProbabilisticFamily

    Retorna siempre exactamente 3 familias en el orden:
        ["close_return", "close_vs_event", "gap_fill"]
    """
    ...


def _build_forward_returns(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_periods: int,
) -> pd.DataFrame:
    """
    Agrega columnas de retorno forward a events_df:
        ret_close_p{n_periods}: (close_Pn - open_P0) / open_P0
        ret_event_p{n_periods}: (close_Pn - close_P0) / close_P0
        open_p0: open de la sesión del evento
        close_p0: close de la sesión del evento
        prev_close: close_{T-1} (para gap_fill)

    Filas sin n sesiones completas disponibles → NaN en columnas de retorno.
    No modifica events_df (retorna copia con columnas adicionales).
    """
    ...


def _compute_gap_fill_column(
    events_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_periods: int,
) -> pd.Series:
    """
    Para cada evento con gap_pct != 0:
        gap_fill = True si el precio toca el nivel prev_close dentro de las n_periods
                   sesiones siguientes (usando el rango high-low de cada sesión)
        gap_fill = NaN si gap_pct == 0 o sin n sesiones disponibles

    Retorna Serie de bool/NaN indexada como events_df.
    """
    ...
```

## Lógica de cada familia

### Familia 1: `close_return`
```
ret = (close_Pn - open_P0) / open_P0
```
- `P0` = sesión del evento (open del día del evento)
- `Pn` = n-ésima sesión de trading posterior

### Familia 2: `close_vs_event`
```
ret = (close_Pn - close_P0) / close_P0
```
- Base = close de la sesión del evento (no el open)

### Familia 3: `gap_fill`
```
gap definido: gap_pct = (open_P0 - prev_close) / prev_close

gap alcista (gap_pct > 0):
    fill = any(low_Pi <= prev_close for i in [1..n_periods])

gap bajista (gap_pct < 0):
    fill = any(high_Pi >= prev_close for i in [1..n_periods])
```
- Bins para gap_fill: ignorar los bins de AnalysisRequest; usar `[0.5]` como umbral
  (probabilidad de llenar o no llenar)
- Si ningún evento tiene `gap_pct != 0` → `warning = "no_gap_events"`

## Criterios de aceptación

```python
from backend.core.metrics.probabilistic import compute_probabilistic_metrics
from backend.core.statistical_models import BootstrapModel
from backend.api.schemas import ModelType

# Con eventos sintéticos de Fase 7
model = BootstrapModel()
result = compute_probabilistic_metrics(
    events_df=built_features_df,   # output de FeatureBuilder
    ohlcv_df=ohlcv,
    model=model,
    model_type=ModelType.bootstrap,
    n_periods=5,
    bins=[-0.05, -0.01, 0.01, 0.05],
    symbol="AAPL",
    data_source="yfinance",
)

# Exactamente 3 familias
assert len(result.families) == 3
families = {f.family for f in result.families}
assert families == {"close_return", "close_vs_event", "gap_fill"}

# Cada familia válida
for fam in result.families:
    if fam.warning != "no_gap_events":
        probs = [b.probability for b in fam.scenarios]
        assert abs(sum(probs) - 1.0) < 1e-3, f"Familia {fam.family} no suma 1"
    assert fam.n_samples_used <= fam.n_total_events

print("Métricas probabilísticas OK")
```

## Restricciones

- `events_df` llega ya filtrado por condicionamiento — esta función NO filtra
- Eventos sin N sesiones completas disponibles → excluidos de `n_samples_used`,
  pero `n_total_events` refleja el total antes de excluir
- Sin modificación de `ohlcv_df` ni `events_df`
- `model.fit()` se llama una sola vez por llamada a `compute_probabilistic_metrics`
- Para gap_fill, si `n_samples_used < 5` → `warning = "insufficient_samples"` (tiene prioridad sobre "no_gap_events")

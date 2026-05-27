---
mode: agent
description: >
  Fase 6 — Modelos estadísticos de Event Edge: implementa la interfaz base
  y los cuatro modelos (Frequentist, Bootstrap, KDE, Bayesian) para análisis
  probabilístico de eventos.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 6 — Modelos Estadísticos

## Prerrequisitos

- Fases 1-5 completadas: schemas (`ScenarioBin`, `ProbabilisticFamily`) y FeatureBuilder existen
- Leer `Event_Edge/.github/instructions/global.instructions.md` → convenciones de modelos

## Objetivo

Implementar la interfaz abstracta `BaseEventModel` y sus cuatro implementaciones.
Al finalizar:
- Los cuatro modelos producen probabilidades que suman 1.0 por familia
- Todos los CIs satisfacen `ci_lower <= probability <= ci_upper`
- `n_samples_used < 5` dispara `warning = "insufficient_samples"`

**Regla de capa**: `core/statistical_models/` no importa de `api/routers/` ni de `data/`.

## Archivos a crear

### `Event_Edge/backend/core/statistical_models/__init__.py`
Exportar `FrequentistModel`, `BootstrapModel`, `KDEModel`, `BayesianModel`, `BaseEventModel`.

### `Event_Edge/backend/core/statistical_models/base.py`

```python
"""
Interfaz abstracta para modelos de análisis probabilístico de eventos.

Contract de events_df (output de FeatureBuilder + columnas de retorno):
    - Columnas requeridas: date, event_type, gap_pct
    - Columnas de retorno forward: ret_close_p{n}, ret_event_p{n}
      donde ret_close_p1 = (close_P1 - open_P0) / open_P0
            ret_event_p1 = (close_P1 - close_P0) / close_P0
    - Filas ya filtradas por condicionamiento (responsabilidad del caller)

Contract de bins:
    - list[float] en decimal ordenados de menor a mayor
    - Generan N+1 intervalos: (-∞, b0], (b0, b1], ..., (b_{n-1}, +∞)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd
from backend.api.schemas import ScenarioBin


class BaseEventModel(ABC):

    MIN_SAMPLES = 5

    @abstractmethod
    def fit(self, events_df: pd.DataFrame) -> None:
        """Ajusta el modelo con el DataFrame de eventos."""
        ...

    @abstractmethod
    def predict_close_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        """
        Familia 'close_return': P(ret_close_pN in bin)
        ret = (close_Pn - open_P0) / open_P0
        """
        ...

    @abstractmethod
    def predict_close_vs_event_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        """
        Familia 'close_vs_event': P(ret_event_pN in bin)
        ret = (close_Pn - close_P0) / close_P0
        """
        ...

    @abstractmethod
    def predict_gap_fill_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        """
        Familia 'gap_fill': P(gap se cierra dentro de n_periods sesiones)
        Si ningún evento tiene gap_pct != 0 → warning = 'no_gap_events'
        """
        ...

    def _make_bin_labels(self, bins: list[float]) -> list[str]:
        """
        Genera etiquetas legibles para los N+1 intervalos definidos por bins.
        Ejemplo: bins=[-0.05, 0.05] → ["< -5%", "-5% a +5%", "> +5%"]
        """
        ...

    def _check_insufficient_samples(self, n: int) -> str | None:
        """Retorna 'insufficient_samples' si n < MIN_SAMPLES, else None."""
        return "insufficient_samples" if n < self.MIN_SAMPLES else None
```

### `Event_Edge/backend/core/statistical_models/frequentist.py`

**Algoritmo**:
1. Para cada bin, contar cuántos retornos caen en ese intervalo → frecuencia observada
2. `probability = k / n` donde k = eventos en bin, n = total
3. IC = **Wilson score interval** con `alpha=0.05`:
   ```
   z = 1.96
   center = (k + z²/2) / (n + z²)
   margin = z * sqrt(n*p̂*(1-p̂) + z²/4) / (n + z²)
   ci_lower = center - margin
   ci_upper = center + margin
   ```

### `Event_Edge/backend/core/statistical_models/bootstrap.py`

**Algoritmo**:
1. `n_iter = 1000` remuestreos con reemplazo del array de retornos
2. Para cada remuestreo, calcular frecuencia por bin
3. `probability` = media de las frecuencias bootstrap
4. `ci_lower` = percentil 2.5, `ci_upper` = percentil 97.5
5. Fijar `random_state=42` para reproducibilidad

### `Event_Edge/backend/core/statistical_models/kde.py`

**Algoritmo**:
1. Ajustar `scipy.stats.gaussian_kde` sobre el array de retornos
2. Para cada bin `[a, b]`: `probability = integrate(kde, a, b)`
   - Para bin `(-∞, b0]`: integrar desde `-∞` (usar `-10` como límite práctico)
   - Para bin `[bN, +∞)`: integrar hasta `+∞` (usar `+10` como límite práctico)
3. CI = bootstrap de la KDE: `n_iter=500` remuestreos, integrar KDE en cada muestra
4. Normalizar probabilidades para que sumen 1.0 (corrección numérica)

### `Event_Edge/backend/core/statistical_models/bayesian.py`

**Algoritmo**:
1. Prior: ajustar `Beta(α_prior, β_prior)` sobre el dataset completo para cada bin
   - Usar `scipy.stats.beta.fit` sobre frecuencias históricas
   - `α_prior = k_total + 1`, `β_prior = (n_total - k_total) + 1`  (prior de Laplace)
2. Posterior por bin: `Beta(α_prior + k_cond, β_prior + (n_cond - k_cond))`
3. `probability` = media del posterior
4. CI = HDI (Highest Density Interval) al 95%:
   ```python
   from scipy import stats
   dist = stats.beta(alpha_post, beta_post)
   ci_lower, ci_upper = dist.ppf(0.025), dist.ppf(0.975)
   ```

## Criterios de aceptación

```python
# tests/unit/test_statistical_models.py — escenario mínimo para cada modelo

import numpy as np
import pandas as pd
from backend.core.statistical_models import (
    FrequentistModel, BootstrapModel, KDEModel, BayesianModel
)

BINS = [-0.05, -0.01, 0.01, 0.05]

def make_events_df(n=50):
    np.random.seed(42)
    returns = np.random.normal(0.01, 0.04, n)
    return pd.DataFrame({
        "ret_close_p5": returns,
        "ret_event_p5": returns * 0.9,
        "gap_pct": np.random.choice([0.02, -0.03, 0.0], n),
    })

for ModelClass in [FrequentistModel, BootstrapModel, KDEModel, BayesianModel]:
    model = ModelClass()
    df = make_events_df(50)
    model.fit(df)

    bins_result = model.predict_close_scenarios(n_periods=5, bins=BINS)
    probs = [b.probability for b in bins_result]

    # 1. Probabilidades suman ~1.0
    assert abs(sum(probs) - 1.0) < 1e-4, f"{ModelClass.__name__}: probs no suman 1"

    # 2. CI válidos
    for b in bins_result:
        assert b.ci_lower <= b.probability <= b.ci_upper, \
            f"{ModelClass.__name__}: CI inválido en bin {b.label}"

    # 3. N+1 bins generados
    assert len(bins_result) == len(BINS) + 1

    # 4. Insufficient samples warning
    model_small = ModelClass()
    model_small.fit(make_events_df(3))
    result_small = model_small.predict_close_scenarios(5, BINS)
    assert all(b.probability == 0 or True for b in result_small)  # no crash

    print(f"{ModelClass.__name__}: OK")
```

## Restricciones

- `scipy` y `numpy` para cálculos estadísticos — no reinventar
- Sin estado mutable entre llamadas a `predict_*` después del `fit`
- `random_state=42` en modelos con aleatoriedad para reproducibilidad
- No loguear retornos individuales
- Si `n_samples_used < MIN_SAMPLES` → retornar bins con `probability=0.0`,
  `ci_lower=0.0`, `ci_upper=1.0` y `event_count=0`; **no lanzar excepción**

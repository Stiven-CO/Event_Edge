---
mode: agent
description: >
  Fase 4 — Detección de eventos de Event Edge: implementa EventDetector
  para detectar earnings y gaps sobre series OHLCV diarias.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 4 — Detección de Eventos

## Prerrequisitos

- Fases 1-3 completadas: schemas (`EventRecord`, `EventType`, `GuidanceDirection`) y capa de datos existen
- Leer `Event_Edge/.github/instructions/global.instructions.md` → contratos de datos y convenciones de fechas

## Objetivo

Implementar `EventDetector` en `backend/core/event_detector.py`.
Al finalizar:
- `detect_earnings()` alinea fechas de earnings con OHLCV y calcula `gap_pct` de apertura
- `detect_gaps()` detecta todas las sesiones con gap > threshold, excluyendo earnings
- Las fechas siempre son UTC timezone-aware

**Regla de capa**: `core/` no importa nada de `api/`; puede importar de `data/` solo tipos, no instancias.

## Archivos a crear

### `Event_Edge/backend/core/__init__.py`
Vacío.

### `Event_Edge/backend/core/event_detector.py`

```python
"""
Detecta eventos earnings y gap en series OHLCV diarias.

Assumptions:
    - ohlcv_df tiene index DatetimeIndex UTC, sin gaps de trading days
    - Columnas: open, high, low, close, volume (float)
    - OHLCV ajustado (precios post-split)
    - earnings_df tiene index DatetimeIndex UTC y columnas:
        eps_actual, eps_estimate, revenue_actual, revenue_estimate
    - Un evento por fecha: si earnings y gap coinciden, se registra earnings
"""
from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone
from backend.api.schemas import EventRecord, EventType, GuidanceDirection


class EventDetector:

    def detect_earnings(
        self,
        ohlcv_df: pd.DataFrame,
        earnings_df: pd.DataFrame,
    ) -> list[EventRecord]:
        """
        Alinea fechas de earnings con el DataFrame OHLCV.

        Lógica de alineación:
            1. Para cada fecha en earnings_df, buscar la fecha de trading más cercana
               en ohlcv_df que sea >= a la fecha de earnings (forward-fill).
            2. Si la fecha mapeada ya fue usada por otro earnings → usar la siguiente
               fecha disponible (evitar duplicados).
            3. Calcular gap_pct = (open_T - close_{T-1}) / close_{T-1}
               donde T es la sesión del evento.
            4. Si no hay sesión previa disponible → excluir el evento.
            5. Earnings fuera del rango de ohlcv_df → excluir sin error.

        Retorna lista de EventRecord con event_type=earnings, ordenada por date asc.
        """
        ...

    def detect_gaps(
        self,
        ohlcv_df: pd.DataFrame,
        threshold_pct: float = 1.0,
        earnings_dates: list[datetime] | None = None,
    ) -> list[EventRecord]:
        """
        Detecta sesiones donde |gap_pct| > threshold_pct.

        Lógica:
            1. gap_pct = (open_T - close_{T-1}) / close_{T-1} * 100  para cada sesión T
            2. Seleccionar filas donde |gap_pct| > threshold_pct
            3. Excluir fechas presentes en earnings_dates (si se proporciona)
            4. Crear EventRecord con event_type=gap, eps_* = None, guidance=not_available

        Retorna lista ordenada por date asc.
        """
        ...
```

## Lógica de `gap_pct`

```
gap_pct = (open_T - close_{T-1}) / close_{T-1}
```

- `gap_pct > 0` → gap alcista (abrió por encima del cierre previo)
- `gap_pct < 0` → gap bajista
- El valor se almacena en decimal, NO en porcentaje: 0.03 = 3%

## Casos edge a manejar

| Caso | Comportamiento esperado |
|------|------------------------|
| Earnings en fin de semana | Mapear al siguiente día de trading en ohlcv_df |
| Earnings antes del primer dato OHLCV | Excluir silenciosamente |
| Earnings después del último dato OHLCV | Excluir silenciosamente |
| Dos earnings en la misma fecha OHLCV | Usar la más reciente; ignorar la otra con `logging.warning` |
| ohlcv_df vacío | Retornar lista vacía |
| earnings_df vacío | Retornar lista vacía |
| Primera sesión de ohlcv_df (sin T-1) | Excluir — sin prev_close disponible |

## Criterios de aceptación

```python
# tests/unit/test_event_detector.py — casos a implementar en Fase 12

def test_detect_earnings_alignment():
    # earnings_date = sábado → debe mapear al lunes siguiente en ohlcv
    ...

def test_detect_earnings_gap_calculation():
    # gap_pct = (open_T - close_{T-1}) / close_{T-1} correcto
    ...

def test_detect_earnings_out_of_range():
    # earnings fuera del OHLCV → lista vacía, sin error
    ...

def test_detect_gaps_positive():
    # gap positivo > threshold → detectado
    ...

def test_detect_gaps_negative():
    # gap negativo > threshold → detectado
    ...

def test_detect_gaps_below_threshold():
    # gap < threshold → no detectado
    ...

def test_detect_gaps_excludes_earnings():
    # fecha de earnings NO aparece en resultado de detect_gaps
    ...

def test_detect_gaps_empty_ohlcv():
    # ohlcv_df vacío → []
    ...
```

## Restricciones

- Sin imports de `api/` ni de instancias de `data/`
- Todas las fechas comparadas y retornadas deben ser `datetime` con `tzinfo=timezone.utc`
- `guidance` siempre `GuidanceDirection.not_available` — se enriquece en capa superior si es necesario
- No se modifica `ohlcv_df` ni `earnings_df` (no `inplace`)
- Loguear eventos excluidos con `logging.debug`, no con `print`

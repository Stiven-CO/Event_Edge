---
mode: agent
description: >
  Fase 5 — Feature Builder de Event Edge: construye features de condicionamiento
  (EMA, Bollinger Bands, open vs prev close) para cada EventRecord sin look-ahead.
tools:
  - read_file
  - create_file
  - replace_string_in_file
---

# Fase 5 — Feature Builder

## Prerrequisitos

- Fases 1-4 completadas: schemas, capa de datos y EventDetector existen
- Leer `Event_Edge/.github/instructions/global.instructions.md` → convenciones de features

## Objetivo

Implementar `FeatureBuilder` en `backend/core/feature_builder.py`.
Al finalizar:
- Recibe un `ohlcv_df` y una `list[EventRecord]`
- Retorna un DataFrame con una fila por evento y sus features de condicionamiento
- **Sin look-ahead**: todos los features se calculan con datos anteriores al open del evento

## Archivos a crear

### `Event_Edge/backend/core/feature_builder.py`

```python
"""
Construye features de condicionamiento para cada EventRecord.

Regla anti-look-ahead:
    Para el evento en fecha T, todos los indicadores se calculan usando
    datos hasta T-1 inclusive (cierre previo). El open de T NO se usa
    para calcular indicadores (sí para open_vs_prev_close_pct).

Dependencias:
    - pandas-ta para EMA y Bollinger Bands
    - No importa de api/ ni instancias de data/
"""
from __future__ import annotations
import pandas as pd
from backend.api.schemas import EventRecord, BBPosition


class FeatureBuilder:

    def build(
        self,
        ohlcv_df: pd.DataFrame,
        events: list[EventRecord],
    ) -> pd.DataFrame:
        """
        Retorna DataFrame con columnas:
            date, event_type, symbol, gap_pct,
            ema5_range_pct, ema20_range_pct,
            open_vs_prev_close_pct,
            bb_position,
            eps_surprise_pct, revenue_surprise_pct, guidance

        Una fila por evento. Eventos sin datos suficientes → fila con NaN
        en features (NO se excluyen silenciosamente; el filtrado es
        responsabilidad del router/modelo).
        """
        ...

    def _calc_ema_range_pct(
        self, ohlcv_df: pd.DataFrame, period: int
    ) -> pd.Series:
        """
        (close_T-1 - ema_N_{T-1}) / ema_N_{T-1} * 100

        - EMA calculada sobre la serie de close completa con pandas-ta
        - Se usa el valor del día ANTERIOR al evento (shift(1) desde perspectiva del evento)
        - Retorna Serie indexada por fecha del evento
        """
        ...

    def _calc_bb_position(self, ohlcv_df: pd.DataFrame) -> pd.Series:
        """
        Clasifica el open del evento respecto a las Bollinger Bands del día anterior.

        Bandas calculadas con: pandas-ta BB(20, 2) sobre close
        Se usa bb_lower_{T-1} y bb_upper_{T-1} para clasificar open_T.

        Clasificación:
            open < bb_lower  → BBPosition.below_lower
            bb_lower <= open < bb_lower + 0.33*(bb_upper-bb_lower) → BBPosition.in_lower
            bb_lower + 0.33*range <= open < bb_upper - 0.33*range  → BBPosition.middle
            bb_upper - 0.33*range <= open <= bb_upper              → BBPosition.in_upper
            open > bb_upper  → BBPosition.above_upper

        Retorna Serie de BBPosition indexada por fecha del evento.
        """
        ...

    def _calc_open_vs_prev_close_pct(
        self, ohlcv_df: pd.DataFrame, event_dates: pd.DatetimeIndex
    ) -> pd.Series:
        """
        (open_T - close_{T-1}) / close_{T-1} * 100

        Equivalente al gap_pct del EventRecord pero en porcentaje para comparación.
        """
        ...
```

## Definición de features

| Feature | Fórmula | Período de referencia |
|---------|---------|----------------------|
| `ema5_range_pct` | `(close_{T-1} - EMA5_{T-1}) / EMA5_{T-1} × 100` | Día anterior al evento |
| `ema20_range_pct` | `(close_{T-1} - EMA20_{T-1}) / EMA20_{T-1} × 100` | Día anterior al evento |
| `open_vs_prev_close_pct` | `(open_T - close_{T-1}) / close_{T-1} × 100` | Open del día del evento vs cierre previo |
| `bb_position` | Clasificación de open_T vs bandas de T-1 | Ver tabla BB arriba |
| `eps_surprise_pct` | Del EventRecord — ya calculado en EarningsLoader | — |
| `revenue_surprise_pct` | Del EventRecord — ya calculado en EarningsLoader | — |
| `guidance` | Del EventRecord | — |

## Criterios de aceptación

```python
# tests/unit/test_feature_builder.py — casos a implementar en Fase 12

def test_build_returns_correct_columns():
    # El DataFrame resultado tiene exactamente las columnas especificadas
    ...

def test_no_lookahead():
    # Para el primer evento, los features usan solo datos previos
    # Manipular ohlcv para que T-1 sea distinto a T y verificar que se usa T-1
    ...

def test_bb_position_below_lower():
    # open < bb_lower_{T-1} → BBPosition.below_lower
    ...

def test_bb_position_above_upper():
    # open > bb_upper_{T-1} → BBPosition.above_upper
    ...

def test_ema5_range_pct_positive():
    # close > EMA5 → ema5_range_pct > 0
    ...

def test_insufficient_history_returns_nan():
    # Evento con menos de 20 sesiones previas → ema20_range_pct = NaN (no excepción)
    ...
```

## Restricciones

- pandas-ta para todos los indicadores técnicos — no reimplementar EMA ni BB
- EMA con `pandas_ta.ema(close, length=N)` — length exacto: 5 y 20
- BB con `pandas_ta.bbands(close, length=20, std=2.0)` — parámetros fijos
- El método `build()` no modifica `ohlcv_df` ni la lista `events`
- Sin `print` ni `logging.debug` con datos de precio en claro
- Eventos cuya fecha no está en `ohlcv_df` → fila con `NaN` en todos los features técnicos

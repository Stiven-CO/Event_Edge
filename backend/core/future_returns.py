"""
Fuente unica del signo de retorno por evento.

Compartida por probabilistic_pipeline.py (Metricas de Retorno Futuro, N+/N-)
y price_action/builder.py (clasificacion Win/Loss), para que ambos paneles
de la UI reflejen siempre el mismo signo por evento. Antes cada uno recalculaba
su propio "retorno" con una referencia de precio distinta (ver commit que
introdujo este modulo) y las cuentas divergian para el mismo conjunto de
eventos condicionados.

Vive en un modulo propio (en vez de que price_action importe de
probabilistic_pipeline o viceversa) para evitar un cross-import entre un
router y un modulo de pipeline hermano — el mismo antipatron que
persistence.py ya tuvo que corregir en el pasado (ver docstring de
run_probabilistic_analysis).
"""
from __future__ import annotations

import pandas as pd

from backend.core.utc import to_utc_ts


def compute_future_return_signs(
    conditioned_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
    n_periods: int,
    price_action_mode: str = "holding",
) -> dict[pd.Timestamp, float | None]:
    """Retorna, keyed por evento (to_utc_ts(row['date'])), el retorno firmado
    por evento, usando la misma referencia de precio en ambos modos:

    - in_event:  P0 open -> close (misma barra del timeframe exterior).
    - holding:   P1-open -> Pn-close (periodo elegido por el usuario).

    None cuando el lookup de la barra correspondiente falla (evento sin
    barra encontrada, o sin suficientes barras futuras) — se preserva una
    entrada por cada evento de conditioned_df en vez de omitirlo en
    silencio, para que el join por timestamp con otros consumidores sea 1:1.
    """
    signs: dict[pd.Timestamp, float | None] = {}
    if conditioned_df.empty:
        return signs

    df = ohlcv_df.sort_index()
    trading_dates = df.index

    if price_action_mode == "in_event":
        for ts in conditioned_df["date"]:
            ts_utc = to_utc_ts(ts)
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0:
                signs[ts_utc] = None
                continue
            found = trading_dates[loc].normalize()
            if found != ts_utc.normalize():
                signs[ts_utc] = None
                continue
            row_open = float(df["open"].iloc[loc])
            row_close = float(df["close"].iloc[loc])
            if row_open > 0 and not (pd.isna(row_open) or pd.isna(row_close)):
                signs[ts_utc] = (row_close - row_open) / row_open
            else:
                signs[ts_utc] = None
    else:
        actual_period = max(1, n_periods)
        for ts in conditioned_df["date"]:
            ts_utc = to_utc_ts(ts)
            loc = trading_dates.get_indexer([ts_utc], method="nearest")[0]
            if loc < 0 or loc + actual_period >= len(df):
                signs[ts_utc] = None
                continue
            open_p1 = float(df["open"].iloc[loc + 1])
            close_pn = float(df["close"].iloc[loc + actual_period])
            if open_p1 > 0 and not (pd.isna(open_p1) or pd.isna(close_pn)):
                signs[ts_utc] = (close_pn - open_p1) / open_p1
            else:
                signs[ts_utc] = None

    return signs

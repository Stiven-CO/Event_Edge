"""
Normalización a UTC-aware — única fuente de verdad para todo el backend.

Reemplaza las ~6 reimplementaciones locales del mismo idioma
("tz_localize si es naive, si no tz_convert") que existían dispersas en
lake_reader.py, conditioning_pipeline.py, probabilistic_pipeline.py,
feature_builder.py, event_detector.py y price_action/builder.py.
"""
from __future__ import annotations

import pandas as pd


def to_utc_ts(ts: object) -> pd.Timestamp:
    """Convierte un valor escalar a pd.Timestamp UTC-aware, tolerando tz-naive y tz-aware."""
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def to_utc_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Convierte un DatetimeIndex a UTC-aware, tolerando tz-naive y tz-aware."""
    if index.tz is None:
        return index.tz_localize("UTC")
    return index.tz_convert("UTC")

"""
Pipeline 1 — Carga y preprocesado.

Único punto de entrada para leer OHLCV/earnings directamente del Data Lake
curated (sin HTTP a MDH) para todos los flujos excepto Price Action, que
sigue dependiendo de MdhClient (auto-ingesta) en price_action.py.

Reemplaza las copias de `_load_ohlcv`/`_fetch_earnings_safe` que existían
por separado en events.py y analysis.py.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import HTTPException

from backend.config import Settings
from backend.data import lake_reader
from backend.data.lake_reader import LakeDatasetNotFoundError


def load_ohlcv(
    settings: Settings,
    symbol: str,
    source: str,
    asset_class: str,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    ohlcv_source: str | None = None,
    timeframe: str = "1d",
) -> tuple[pd.DataFrame, str]:
    """
    Lee OHLCV completo directamente del Data Lake curated (sin MDH).

    Cuando ohlcv_source está presente (modo fundamental), lo usa como fuente de datos
    OHLCV y fuerza asset_class="equity" para acceder al path correcto del lake.

    Lanza HTTPException 404 si el dataset no existe en el lake — el usuario debe
    descargarlo primero vía MDH.
    """
    resolved_source = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class

    try:
        df = lake_reader.read_ohlcv(
            settings.mdh_lake_root,
            symbol=symbol,
            source=resolved_source,
            asset_class=resolved_asset_class,
            timeframe=timeframe,
            start=date_start,
            end=date_end,
        )
        return df, resolved_source
    except LakeDatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def fetch_earnings_safe(
    settings: Settings,
    symbol: str,
    source: str,
) -> tuple[pd.DataFrame, str]:
    """
    Lee earnings directamente del lake. Retorna (df, info_text) sin lanzar excepción.

    Earnings siempre usa `source` (la fuente fundamental elegida en el Menu Datos,
    ej. alphavantage) — nunca `ohlcv_source`, que gobierna únicamente el OHLCV.
    """
    earnings_source = (source or "yfinance").lower()
    df = lake_reader.read_earnings(
        settings.mdh_lake_root,
        symbol=symbol,
        source=earnings_source,
        asset_class="equity",
    )
    if df.empty:
        return df, "Earnings: sin datos disponibles en el lake"
    return df, f"Earnings: {len(df)} reportes"

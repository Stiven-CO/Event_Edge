"""
Caché de proceso para Pipeline 1 (lectura de lake) y Pipeline 2 (features).

Evita releer parquet del Data Lake y recomputar FeatureBuilder cuando los
mismos parámetros ya se resolvieron antes. Envuelve funciones existentes de
data_pipeline.py/conditioning_pipeline.py sin modificar sus firmas ni cuerpos.

L1 (lake): invalidado por mtime del parquet resuelto — única señal de
frescura disponible, ya que market_data_hub reescribe el archivo al reingerir
y no existe metadata de "última ingesta" expuesta a Event_Edge.
L2 (features): keyed sobre el fingerprint de L1 (clave+mtime), no sobre el
contenido del DataFrame — evita hashear DataFrames grandes.

Diseño para un único proceso (uvicorn sin --workers, ver start.ps1); si el
despliegue pasa a multi-worker/multi-réplica, este módulo es el punto de
reemplazo por un backend compartido (p.ej. Redis) detrás de la misma interfaz
CacheStore.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backend.api.schemas import EventType
from backend.config import Settings
from backend.core import data_pipeline
from backend.core import conditioning_pipeline
from backend.data import lake_reader

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    source_mtime: float | None = None


class CacheStore:
    """LRU acotado, thread-safe. get_valid() aplica TTL + chequeo de mtime."""

    def __init__(self, max_entries: int, ttl_seconds: float | None) -> None:
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._data: OrderedDict[str, CacheEntry] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get_valid(self, key: str, *, expected_mtime: float | None = None) -> CacheEntry | None:
        import time

        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if self._ttl_seconds is not None and (time.time() - entry.created_at) > self._ttl_seconds:
                del self._data[key]
                return None
            if entry.source_mtime != expected_mtime:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return entry

    def set(self, key: str, value: Any, *, source_mtime: float | None = None) -> None:
        import time

        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self._max_entries:
                self._data.popitem(last=False)
            self._data[key] = CacheEntry(value=value, created_at=time.time(), source_mtime=source_mtime)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": (self.hits / total) if total else 0.0,
                "size": len(self._data),
                "max_entries": self._max_entries,
            }


def make_cache_key(*parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_lake_cache: CacheStore | None = None
_feature_cache: CacheStore | None = None


def get_lake_cache(settings: Settings | None = None) -> CacheStore:
    global _lake_cache
    if _lake_cache is None:
        max_entries = settings.cache_lake_max_entries if settings else 256
        ttl_seconds = settings.cache_lake_ttl_seconds if settings else 1800.0
        _lake_cache = CacheStore(max_entries=max_entries, ttl_seconds=ttl_seconds)
    return _lake_cache


def get_feature_cache(settings: Settings | None = None) -> CacheStore:
    global _feature_cache
    if _feature_cache is None:
        max_entries = settings.cache_feature_max_entries if settings else 128
        ttl_seconds = settings.cache_feature_ttl_seconds if settings else 1800.0
        _feature_cache = CacheStore(max_entries=max_entries, ttl_seconds=ttl_seconds)
    return _feature_cache


def reset_caches() -> None:
    """Hook de test/admin — mismo patrón que backend.config._settings=None."""
    global _lake_cache, _feature_cache
    _lake_cache = None
    _feature_cache = None


def _ohlcv_key(symbol: str, resolved_source: str, resolved_asset_class: str,
               timeframe: str, date_start: datetime | None, date_end: datetime | None) -> str:
    return make_cache_key(
        "ohlcv", symbol.upper(), resolved_source, resolved_asset_class, timeframe.lower(),
        str(date_start) if date_start else None, str(date_end) if date_end else None,
    )


def _earnings_key(symbol: str, source: str) -> str:
    return make_cache_key("earnings", symbol.upper(), source.lower())


def load_ohlcv_with_fingerprint(
    settings: Settings,
    symbol: str,
    source: str,
    asset_class: str,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    ohlcv_source: str | None = None,
    timeframe: str = "1d",
) -> tuple[pd.DataFrame, str, str]:
    """Como data_pipeline.load_ohlcv, pero cacheado y devolviendo además un
    fingerprint (clave L1 + mtime) para alimentar el caché de features (L2)."""
    resolved_source = (ohlcv_source or source or "yfinance").lower()
    resolved_asset_class = "equity" if ohlcv_source else asset_class

    path = lake_reader.resolve_ohlcv_path(
        settings.mdh_lake_root, symbol, resolved_source, resolved_asset_class, timeframe
    )
    mtime = path.stat().st_mtime if path is not None else None
    key = _ohlcv_key(symbol, resolved_source, resolved_asset_class, timeframe, date_start, date_end)
    fingerprint = f"{key}:{mtime}"

    cache = get_lake_cache(settings)
    entry = cache.get_valid(key, expected_mtime=mtime)
    if entry is not None:
        cache.hits += 1
        df, resolved = entry.value
        return df.copy(), resolved, fingerprint

    cache.misses += 1
    result = data_pipeline.load_ohlcv(
        settings, symbol, source, asset_class, date_start, date_end, ohlcv_source, timeframe
    )
    cache.set(key, result, source_mtime=mtime)
    df, resolved = result
    return df.copy(), resolved, fingerprint


def cached_load_ohlcv(
    settings: Settings,
    symbol: str,
    source: str,
    asset_class: str,
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    ohlcv_source: str | None = None,
    timeframe: str = "1d",
) -> tuple[pd.DataFrame, str]:
    """Drop-in cacheado de data_pipeline.load_ohlcv (mismo signature/retorno)."""
    df, resolved, _ = load_ohlcv_with_fingerprint(
        settings, symbol, source, asset_class, date_start, date_end, ohlcv_source, timeframe
    )
    return df, resolved


def fetch_earnings_safe_with_fingerprint(
    settings: Settings,
    symbol: str,
    source: str,
) -> tuple[pd.DataFrame, str, str]:
    """Como data_pipeline.fetch_earnings_safe, pero cacheado y con fingerprint."""
    earnings_source = (source or "yfinance").lower()
    path = lake_reader.resolve_earnings_path(settings.mdh_lake_root, symbol, earnings_source)
    mtime = path.stat().st_mtime if path is not None else None
    key = _earnings_key(symbol, earnings_source)
    fingerprint = f"{key}:{mtime}"

    cache = get_lake_cache(settings)
    entry = cache.get_valid(key, expected_mtime=mtime)
    if entry is not None:
        cache.hits += 1
        df, info = entry.value
        return df.copy(), info, fingerprint

    cache.misses += 1
    result = data_pipeline.fetch_earnings_safe(settings, symbol, source)
    cache.set(key, result, source_mtime=mtime)
    df, info = result
    return df.copy(), info, fingerprint


def cached_fetch_earnings_safe(
    settings: Settings,
    symbol: str,
    source: str,
) -> tuple[pd.DataFrame, str]:
    """Drop-in cacheado de data_pipeline.fetch_earnings_safe."""
    df, info, _ = fetch_earnings_safe_with_fingerprint(settings, symbol, source)
    return df, info


def cached_build_features(
    ohlcv_df: pd.DataFrame,
    earnings_df: pd.DataFrame | None,
    event_type: EventType | None,
    symbol: str = "",
    timeframe: str = "1d",
    *,
    ohlcv_fingerprint: str,
    earnings_fingerprint: str | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Drop-in cacheado de conditioning_pipeline.build_features. Requiere el
    fingerprint L1 de ohlcv (y de earnings si aplica) para derivar la clave —
    evita hashear el contenido del DataFrame."""
    event_type_val = getattr(event_type, "value", event_type)
    key = make_cache_key(
        "features", ohlcv_fingerprint, earnings_fingerprint, event_type_val,
        symbol.upper(), timeframe.lower(),
    )
    cache = get_feature_cache(settings)
    entry = cache.get_valid(key)
    if entry is not None:
        cache.hits += 1
        return entry.value.copy()

    cache.misses += 1
    result = conditioning_pipeline.build_features(ohlcv_df, earnings_df, event_type, symbol, timeframe)
    cache.set(key, result)
    return result.copy()


def cached_build_conditioned_dataset(
    ohlcv_df: pd.DataFrame,
    earnings_df: pd.DataFrame | None,
    event_type: EventType | None,
    conditioning,
    symbol: str = "",
    timeframe: str = "1d",
    date_start: datetime | None = None,
    date_end: datetime | None = None,
    *,
    ohlcv_fingerprint: str,
    earnings_fingerprint: str | None = None,
    settings: Settings | None = None,
) -> tuple[pd.DataFrame, int, pd.DataFrame]:
    """Drop-in cacheado de conditioning_pipeline.build_conditioned_dataset.
    Solo cachea la etapa de features (la más costosa); el filtro de fecha y
    el condicionamiento se recalculan siempre (baratos, cambian más seguido)."""
    features_df = cached_build_features(
        ohlcv_df, earnings_df, event_type, symbol, timeframe,
        ohlcv_fingerprint=ohlcv_fingerprint, earnings_fingerprint=earnings_fingerprint,
        settings=settings,
    )
    features_df = conditioning_pipeline._filter_features_by_date(features_df, date_start, date_end)
    n_total = len(features_df)
    conditioned_df = conditioning_pipeline.apply_conditioning(features_df, conditioning)
    return conditioned_df, n_total, features_df

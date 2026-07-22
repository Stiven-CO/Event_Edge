from __future__ import annotations

import os
import time

import pandas as pd
import pytest

from backend.core.cache import CacheStore, make_cache_key


pytestmark = pytest.mark.unit


def test_make_cache_key_is_deterministic():
    k1 = make_cache_key("ohlcv", "AAPL", "yfinance", "equity", "1d", None, None)
    k2 = make_cache_key("ohlcv", "AAPL", "yfinance", "equity", "1d", None, None)
    assert k1 == k2


def test_make_cache_key_differs_on_date_range():
    k1 = make_cache_key("ohlcv", "AAPL", "yfinance", "equity", "1d", "2022-01-01", None)
    k2 = make_cache_key("ohlcv", "AAPL", "yfinance", "equity", "1d", "2022-06-01", None)
    assert k1 != k2


def test_cache_store_hit_on_matching_mtime():
    store = CacheStore(max_entries=8, ttl_seconds=None)
    store.set("k", "value", source_mtime=100.0)
    entry = store.get_valid("k", expected_mtime=100.0)
    assert entry is not None
    assert entry.value == "value"


def test_cache_store_miss_on_mtime_mismatch():
    """Simula que el parquet fue reescrito (mtime cambió) -> debe invalidar."""
    store = CacheStore(max_entries=8, ttl_seconds=None)
    store.set("k", "value", source_mtime=100.0)
    entry = store.get_valid("k", expected_mtime=200.0)
    assert entry is None
    # La entrada obsoleta se evict al detectar el mismatch
    assert store.get_valid("k", expected_mtime=100.0) is None


def test_cache_store_ttl_expiry():
    store = CacheStore(max_entries=8, ttl_seconds=0.05)
    store.set("k", "value", source_mtime=None)
    assert store.get_valid("k", expected_mtime=None) is not None
    time.sleep(0.08)
    assert store.get_valid("k", expected_mtime=None) is None


def test_cache_store_lru_eviction():
    store = CacheStore(max_entries=2, ttl_seconds=None)
    store.set("a", 1, source_mtime=None)
    store.set("b", 2, source_mtime=None)
    store.set("c", 3, source_mtime=None)  # evicts "a" (least recently used)
    assert store.get_valid("a", expected_mtime=None) is None
    assert store.get_valid("b", expected_mtime=None) is not None
    assert store.get_valid("c", expected_mtime=None) is not None


def test_cache_store_stats_hit_miss():
    store = CacheStore(max_entries=8, ttl_seconds=None)
    store.set("k", "value", source_mtime=None)
    store.misses += 1
    entry = store.get_valid("k", expected_mtime=None)
    assert entry is not None
    store.hits += 1
    stats = store.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5
    assert stats["size"] == 1


def test_cache_store_clear_resets_stats_and_entries():
    store = CacheStore(max_entries=8, ttl_seconds=None)
    store.set("k", "value", source_mtime=None)
    store.hits = 3
    store.misses = 2
    store.clear()
    assert store.stats() == {"hits": 0, "misses": 0, "hit_rate": 0.0, "size": 0, "max_entries": 8}

from __future__ import annotations

import os

import pandas as pd
import pytest
from httpx import AsyncClient

from backend.data import lake_reader


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
def lake_root(tmp_path, synthetic_ohlcv_df: pd.DataFrame):
    """Lake curated con un único parquet OHLCV real para AAPL/yfinance/equity/1d."""
    dest_dir = tmp_path / "curated" / "yfinance" / "ohlcv" / "equity" / "AAPL" / "1d" / "complete_historical"
    dest_dir.mkdir(parents=True)
    df = synthetic_ohlcv_df.reset_index().rename(columns={"index": "date"})
    df.to_parquet(dest_dir / "df.parquet")
    os.environ["EE_MDH_LAKE_ROOT"] = str(tmp_path)
    yield tmp_path, dest_dir / "df.parquet"
    os.environ.pop("EE_MDH_LAKE_ROOT", None)


async def test_repeated_probabilistic_requests_hit_lake_once(
    lake_root, test_client: AsyncClient, monkeypatch
):
    """Dos requests idénticos a /analysis/probabilistic solo deben leer el lake una vez."""
    _, parquet_path = lake_root
    call_count = {"n": 0}
    original_read_ohlcv = lake_reader.read_ohlcv

    def counting_read_ohlcv(*args, **kwargs):
        call_count["n"] += 1
        return original_read_ohlcv(*args, **kwargs)

    monkeypatch.setattr(lake_reader, "read_ohlcv", counting_read_ohlcv)

    payload = {
        "symbol": "AAPL",
        "source": "yfinance",
        "model": "bootstrap",
        "n_periods": 5,
        "bins": [-0.05, 0.05],
    }

    r1 = await test_client.post("/api/v1/analysis/probabilistic", json=payload)
    assert r1.status_code == 200
    r2 = await test_client.post("/api/v1/analysis/probabilistic", json=payload)
    assert r2.status_code == 200

    assert call_count["n"] == 1

    # Simula que market_data_hub reescribió el parquet (nuevo mtime) -> debe recomputar
    os.utime(parquet_path, None)
    r3 = await test_client.post("/api/v1/analysis/probabilistic", json=payload)
    assert r3.status_code == 200
    assert call_count["n"] == 2


async def test_different_symbol_misses_cache(lake_root, test_client: AsyncClient, monkeypatch):
    _, _ = lake_root
    call_count = {"n": 0}
    original_read_ohlcv = lake_reader.read_ohlcv

    def counting_read_ohlcv(*args, **kwargs):
        call_count["n"] += 1
        return original_read_ohlcv(*args, **kwargs)

    monkeypatch.setattr(lake_reader, "read_ohlcv", counting_read_ohlcv)

    base_payload = {"symbol": "AAPL", "source": "yfinance", "model": "bootstrap", "n_periods": 5, "bins": [-0.05, 0.05]}
    r1 = await test_client.post("/api/v1/analysis/probabilistic", json=base_payload)
    assert r1.status_code == 200

    other_payload = {**base_payload, "symbol": "MSFT"}
    r2 = await test_client.post("/api/v1/analysis/probabilistic", json=other_payload)
    # MSFT no existe en el lake de prueba -> 404, pero igual debe intentar leer (miss real)
    assert r2.status_code == 404

    assert call_count["n"] == 2

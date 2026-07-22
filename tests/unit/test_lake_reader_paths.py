from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.data import lake_reader


pytestmark = pytest.mark.unit


def test_resolve_ohlcv_path_none_when_absent(tmp_path):
    assert lake_reader.resolve_ohlcv_path(str(tmp_path), "AAPL", "yfinance", "equity", "1d") is None


def test_resolve_ohlcv_path_found(tmp_path):
    dest_dir = tmp_path / "curated" / "yfinance" / "ohlcv" / "equity" / "AAPL" / "1d" / "complete_historical"
    dest_dir.mkdir(parents=True)
    pd.DataFrame({"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}).to_parquet(
        dest_dir / "df.parquet"
    )

    resolved = lake_reader.resolve_ohlcv_path(str(tmp_path), "AAPL", "yfinance", "equity", "1d")
    assert resolved == dest_dir / "df.parquet"


def test_resolve_earnings_path_none_when_absent(tmp_path):
    assert lake_reader.resolve_earnings_path(str(tmp_path), "AAPL", "yfinance") is None


def test_resolve_earnings_path_found(tmp_path):
    dest_dir = tmp_path / "curated" / "alphavantage" / "fundamental" / "earnings" / "equity" / "AAPL" / "quarterly" / "complete_historical"
    dest_dir.mkdir(parents=True)
    pd.DataFrame({"date": []}).to_parquet(dest_dir / "df.parquet")

    resolved = lake_reader.resolve_earnings_path(str(tmp_path), "AAPL", "alphavantage")
    assert resolved == dest_dir / "df.parquet"

"""
Fixtures compartidas para toda la suite de tests de Event Edge.
Sin conexión real a brokers ni a MDH — todos los datos son sintéticos.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import backend.config as config_module
from backend.api.app import create_app
from backend.api.schemas import EventRecord


@pytest.fixture(autouse=True)
def reset_settings():
    """Resetea el singleton de settings antes de cada test."""
    config_module._settings = None
    yield
    config_module._settings = None


@pytest.fixture
def synthetic_ohlcv_df() -> pd.DataFrame:
    """
    500 sesiones de datos OHLCV sintéticos para AAPL.
    Index: DatetimeIndex UTC, Business Days desde 2022-01-03.
    """
    n = 500
    dates = pd.bdate_range("2022-01-03", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(42)

    log_returns = rng.normal(0.0002, 0.015, n)
    close = 150.0 * np.cumprod(np.exp(log_returns))
    high = close * rng.uniform(1.001, 1.02, n)
    low = close * rng.uniform(0.98, 0.999, n)
    open_ = close * rng.uniform(0.995, 1.005, n)
    volume = rng.integers(5_000_000, 20_000_000, n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


@pytest.fixture
def synthetic_earnings(synthetic_ohlcv_df: pd.DataFrame) -> pd.DataFrame:
    """
    10 fechas de earnings distribuidas trimestralmente en el OHLCV sintético.
    Columnas: eps_actual, eps_estimate, revenue_actual, revenue_estimate.
    """
    dates = synthetic_ohlcv_df.index[::50][:10]
    rng = np.random.default_rng(7)

    eps_estimate = rng.uniform(1.0, 2.5, 10)
    eps_actual = eps_estimate * rng.uniform(0.9, 1.15, 10)
    rev_estimate = rng.uniform(80e9, 120e9, 10)
    rev_actual = rev_estimate * rng.uniform(0.95, 1.10, 10)

    return pd.DataFrame(
        {
            "eps_actual": eps_actual,
            "eps_estimate": eps_estimate,
            "revenue_actual": rev_actual,
            "revenue_estimate": rev_estimate,
        },
        index=dates,
    )


@pytest.fixture
def sample_events(
    synthetic_ohlcv_df: pd.DataFrame,
    synthetic_earnings: pd.DataFrame,
) -> list[EventRecord]:
    """
    list[EventRecord] construida sobre los datos sintéticos.
    Usa EventDetector para garantizar coherencia con OHLCV.
    """
    from backend.core.event_detector import EventDetector

    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, synthetic_earnings)
    return [e.model_copy(update={"symbol": "AAPL"}) for e in events]


@pytest.fixture
def built_features_df(
    synthetic_ohlcv_df: pd.DataFrame,
    sample_events: list[EventRecord],
) -> pd.DataFrame:
    """Output de FeatureBuilder sobre los datos sintéticos."""
    from backend.core.feature_builder import FeatureBuilder

    builder = FeatureBuilder()
    return builder.build(synthetic_ohlcv_df, sample_events)


@pytest_asyncio.fixture
async def test_client():
    """
    httpx.AsyncClient contra la app FastAPI con settings de test.
    MDH deshabilitado; usa yfinance como fuente.
    """
    os.environ["EE_MDH_ENABLED"] = "false"
    os.environ["EE_DEBUG"] = "true"

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    os.environ.pop("EE_MDH_ENABLED", None)
    os.environ.pop("EE_DEBUG", None)


@pytest.fixture
def synthetic_events_api_payload(
    synthetic_ohlcv_df: pd.DataFrame,
    synthetic_earnings: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pair de OHLCV y earnings sintéticos para monkeypatch en tests API."""
    return synthetic_ohlcv_df.copy(), synthetic_earnings.copy()

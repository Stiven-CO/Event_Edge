from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.fixture(autouse=True)
def patch_data_sources(monkeypatch, synthetic_events_api_payload):
    """Evita conexión a red en integración parcheando EarningsLoader y OHLCV."""
    ohlcv_df, earnings_df = synthetic_events_api_payload

    from backend.data.earnings_loader import EarningsLoader

    monkeypatch.setattr(EarningsLoader, "is_available", lambda self: True)
    monkeypatch.setattr(EarningsLoader, "fetch_ohlcv", lambda self, symbol, period="5y", interval="1d": ohlcv_df.copy())
    monkeypatch.setattr(EarningsLoader, "fetch_earnings_dates", lambda self, symbol, limit=40: earnings_df.copy())


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health(test_client: AsyncClient):
    r = await test_client.get("/api/v1/control/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_broker_status(test_client: AsyncClient):
    r = await test_client.get("/api/v1/control/broker-status")
    assert r.status_code == 200
    sources = {s["source"] for s in r.json()}
    assert "yfinance" in sources


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_events_invalid_symbol(test_client: AsyncClient):
    """Symbol en minúsculas -> 422."""
    r = await test_client.post(
        "/api/v1/events/detect",
        json={"symbol": "aapl", "source": "yfinance", "event_type": "earnings"},
    )
    assert r.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_probabilistic_custom_bins(test_client: AsyncClient):
    """Bins custom reflejados en la respuesta."""
    custom_bins = [-0.08, -0.02, 0.02, 0.08]
    r = await test_client.post(
        "/api/v1/analysis/probabilistic",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "model": "bootstrap",
            "n_periods": 5,
            "bins": custom_bins,
        },
    )
    assert r.status_code == 200

    data = r.json()
    assert len(data["families"]) == 2

    for family in data["families"]:
        if family["warning"] not in ["no_gap_events", "insufficient_samples"]:
            if family["family"] == "gap_fill":
                assert len(family["scenarios"]) == 2
            else:
                assert len(family["scenarios"]) == len(custom_bins) + 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conditioning_reduces_samples(test_client: AsyncClient):
    """Conditioning activo -> n_samples_used <= n_total_events."""
    r = await test_client.post(
        "/api/v1/analysis/probabilistic",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "model": "bootstrap",
            "n_periods": 5,
            "bins": [-0.05, 0.05],
            "conditioning": {
                "eps_surprise_pct_min": 0.05,
            },
        },
    )
    assert r.status_code == 200

    for family in r.json()["families"]:
        assert family["n_samples_used"] <= family["n_total_events"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_assets_fallback_header(test_client: AsyncClient):
    """Con MDH deshabilitado, assets responde [] con source fallback en header."""
    r = await test_client.get("/api/v1/assets")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert r.headers.get("X-Data-Source") == "yfinance"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_root_endpoint(test_client: AsyncClient):
    """GET / responde con metadata del servicio."""
    r = await test_client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "Event Edge"
    assert "docs" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_events_earnings(test_client: AsyncClient):
    """POST /events/detect con símbolo válido y event_type earnings retorna lista."""
    r = await test_client.post(
        "/api/v1/events/detect",
        json={"symbol": "AAPL", "source": "yfinance", "event_type": "earnings"},
    )
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    if events:
        first = events[0]
        assert first["event_type"] == "earnings"
        assert first["symbol"] == "AAPL"
        assert "date" in first


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_events_gaps(test_client: AsyncClient):
    """POST /events/detect con event_type gap retorna lista de gaps."""
    r = await test_client.post(
        "/api/v1/events/detect",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "gap",
            "gap_threshold_pct": 0.5,
        },
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_informative_analysis(test_client: AsyncClient):
    """POST /analysis/informative retorna métricas descriptivas."""
    r = await test_client.post(
        "/api/v1/analysis/informative",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "periods": [1, 5],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["event_type"] == "earnings"
    assert "n_total_events" in data
    assert "frequency_per_year" in data
    assert "avg_movement_range" in data
    assert "avg_candle_range" in data
    assert data["data_source"] in ("mdh", "yfinance")

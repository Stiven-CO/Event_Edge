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


# ---------------------------------------------------------------------------
# Phase 13 — Price Action Plot
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_price_action_daily(test_client: AsyncClient):
    """n_periods=5 → anchor_mode='holding', x_labels=['P1','P2','P3','P4','P5']."""
    r = await test_client.post(
        "/api/v1/analysis/price-action",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "n_periods": 5,
            "include_bands": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["anchor_mode"] == "holding"
    assert data["n_periods"] == 5
    assert data["x_labels"] == ["P1", "P2", "P3", "P4", "P5"]
    assert "series_all" in data
    assert "series_win" in data
    assert "series_loss" in data
    assert "n_events_all" in data
    assert "n_events_omitted" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_price_action_intraday_omits_old_events(test_client: AsyncClient, monkeypatch):
    """n_periods=0 con datos 30min vacíos → n_events_omitted > 0, warning presente."""
    from backend.data.earnings_loader import EarningsLoader

    # Parchear fetch_ohlcv para que al llamar con interval="30m" retorne vacío
    original_fetch = EarningsLoader.fetch_ohlcv

    def patched_fetch(self, symbol, period="5y", interval="1d"):
        if interval == "30m":
            import pandas as pd
            return pd.DataFrame()
        return original_fetch(self, symbol, period=period, interval=interval)

    monkeypatch.setattr(EarningsLoader, "fetch_ohlcv", patched_fetch)

    r = await test_client.post(
        "/api/v1/analysis/price-action",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "n_periods": 0,
            "include_bands": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["anchor_mode"] == "inside_event"
    assert data["n_events_omitted"] > 0
    assert data["warning"] in ("insufficient_events", "some_events_omitted")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_price_action_include_bands_false(test_client: AsyncClient):
    """include_bands=False → band_upper y band_lower deben ser null en series_all."""
    r = await test_client.post(
        "/api/v1/analysis/price-action",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "n_periods": 3,
            "include_bands": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["series_all"]["band_upper"] is None
    assert data["series_all"]["band_lower"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conditioning_count_no_filters_returns_full_dataset_with_raw_columns(
    test_client: AsyncClient,
):
    """Sin filtros de condicionamiento, retorna el dataset completo con columnas base crudas."""
    r = await test_client.post(
        "/api/v1/analysis/conditioning-count",
        json={
            "symbol": "AAPL",
            "source": "yfinance",
            "event_type": "earnings",
            "conditioning": {},
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["n_conditioned"] == data["n_total"]
    assert data["rows"]

    first = data["rows"][0]
    assert first["open"] is not None
    assert first["high"] is not None
    assert first["low"] is not None
    assert first["close"] is not None
    assert first["volume"] is not None

    earning_rows = [row for row in data["rows"] if row["take_earnings"]]
    non_earning_rows = [row for row in data["rows"] if not row["take_earnings"]]
    assert any(row["eps_actual"] is not None for row in earning_rows)
    assert all(row["eps_actual"] is None for row in non_earning_rows)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_price_action_invalid_symbol(test_client: AsyncClient):
    """Symbol inválido → 422."""
    r = await test_client.post(
        "/api/v1/analysis/price-action",
        json={
            "symbol": "aapl",
            "source": "yfinance",
            "event_type": "earnings",
            "n_periods": 5,
        },
    )
    assert r.status_code == 422

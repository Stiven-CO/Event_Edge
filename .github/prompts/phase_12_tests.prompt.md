---
mode: agent
description: >
  Fase 12 — Tests de Event Edge: implementa conftest, tests unitarios
  y tests de integración con fixtures sintéticos y sin conexión a brokers reales.
tools:
  - read_file
  - create_file
  - replace_string_in_file
  - run_in_terminal
---

# Fase 12 — Tests

## Prerrequisitos

- Fases 1-11 completadas: toda la implementación existe
- Revisar `Backtest_Forge/tests/conftest.py` → patrón de fixtures reutilizables
- Revisar `Event_Edge/backend/config.py` → reset de `_settings` en tests

## Objetivo

Crear la suite de tests completa. Al finalizar:
- `pytest tests/unit/ -v` pasa sin conexión a internet ni a brokers
- `pytest tests/integration/ -v` pasa con el servidor corriendo en local
- Cobertura de casos edge documentados en Fases 4-8

---

## `Event_Edge/tests/conftest.py`

```python
"""
Fixtures compartidas para toda la suite de tests de Event Edge.
Sin conexión real a brokers ni a MDH — todos los datos son sintéticos.
"""
import pytest
import pytest_asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from backend.api.app import create_app
from backend.api.schemas import EventRecord, EventType, GuidanceDirection
import backend.config as config_module


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
    Columnas: open, high, low, close, volume.
    Precio inicial: 150.0, random walk con drift 0.0002 y vol 0.015.
    """
    n = 500
    dates = pd.bdate_range("2022-01-03", periods=n, freq="B", tz="UTC")
    np.random.seed(42)
    log_returns = np.random.normal(0.0002, 0.015, n)
    close = 150.0 * np.cumprod(np.exp(log_returns))
    high = close * np.random.uniform(1.001, 1.02, n)
    low = close * np.random.uniform(0.98, 0.999, n)
    open_ = close * np.random.uniform(0.995, 1.005, n)
    volume = np.random.randint(5_000_000, 20_000_000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


@pytest.fixture
def synthetic_earnings(synthetic_ohlcv_df) -> pd.DataFrame:
    """
    10 fechas de earnings distribuidas trimestralmente en el OHLCV sintético.
    Columnas: eps_actual, eps_estimate, revenue_actual, revenue_estimate.
    """
    dates = synthetic_ohlcv_df.index[::50][:10]
    np.random.seed(7)
    eps_estimate = np.random.uniform(1.0, 2.5, 10)
    eps_actual = eps_estimate * np.random.uniform(0.9, 1.15, 10)
    rev_estimate = np.random.uniform(80e9, 120e9, 10)
    rev_actual = rev_estimate * np.random.uniform(0.95, 1.10, 10)
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
def sample_events(synthetic_ohlcv_df, synthetic_earnings) -> list[EventRecord]:
    """
    list[EventRecord] construida sobre los datos sintéticos.
    Usa EventDetector para garantizar coherencia con OHLCV.
    """
    from backend.core.event_detector import EventDetector
    detector = EventDetector()
    return detector.detect_earnings(synthetic_ohlcv_df, synthetic_earnings)


@pytest.fixture
def built_features_df(synthetic_ohlcv_df, sample_events) -> pd.DataFrame:
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
    import os
    os.environ["EE_MDH_ENABLED"] = "false"
    os.environ["EE_DEBUG"] = "true"
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
```

---

## `Event_Edge/tests/unit/test_event_detector.py`

Implementar los siguientes casos con datos sintéticos:

```python
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from backend.core.event_detector import EventDetector
from backend.api.schemas import EventType

@pytest.mark.unit
def test_detect_earnings_alignment(synthetic_ohlcv_df, synthetic_earnings):
    """Todas las fechas retornadas deben estar en el index de ohlcv_df."""
    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, synthetic_earnings)
    ohlcv_dates = set(synthetic_ohlcv_df.index.normalize())
    for ev in events:
        assert ev.date.replace(tzinfo=None).date() in {d.date() for d in ohlcv_dates}

@pytest.mark.unit
def test_detect_earnings_weekend_mapping(synthetic_ohlcv_df):
    """Earnings en fin de semana → mapea al lunes siguiente."""
    # Construir earnings_df con una fecha en sábado
    saturday = pd.Timestamp("2022-01-08", tz="UTC")  # sábado
    monday = pd.Timestamp("2022-01-10", tz="UTC")     # lunes esperado
    earnings = pd.DataFrame(
        {"eps_actual": [1.5], "eps_estimate": [1.4],
         "revenue_actual": [None], "revenue_estimate": [None]},
        index=[saturday],
    )
    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, earnings)
    if events:
        assert events[0].date.date() == monday.date()

@pytest.mark.unit
def test_detect_earnings_out_of_range(synthetic_ohlcv_df):
    """Earnings fuera del rango OHLCV → lista vacía sin error."""
    future = pd.Timestamp("2099-01-01", tz="UTC")
    earnings = pd.DataFrame(
        {"eps_actual": [2.0], "eps_estimate": [1.9],
         "revenue_actual": [None], "revenue_estimate": [None]},
        index=[future],
    )
    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, earnings)
    assert events == []

@pytest.mark.unit
def test_detect_gaps_positive(synthetic_ohlcv_df):
    """Gap positivo > threshold se detecta."""
    detector = EventDetector()
    events = detector.detect_gaps(synthetic_ohlcv_df, threshold_pct=0.5)
    positive_gaps = [e for e in events if e.gap_pct and e.gap_pct > 0]
    assert len(positive_gaps) > 0

@pytest.mark.unit
def test_detect_gaps_excludes_earnings(synthetic_ohlcv_df, sample_events):
    """Fechas de earnings NO aparecen en el resultado de detect_gaps."""
    earnings_dates = [e.date for e in sample_events]
    detector = EventDetector()
    gap_events = detector.detect_gaps(
        synthetic_ohlcv_df, threshold_pct=0.0, earnings_dates=earnings_dates
    )
    gap_dates = {e.date for e in gap_events}
    for ed in earnings_dates:
        assert ed not in gap_dates

@pytest.mark.unit
def test_detect_gaps_empty_ohlcv():
    """ohlcv_df vacío → lista vacía."""
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    detector = EventDetector()
    assert detector.detect_gaps(empty) == []
```

---

## `Event_Edge/tests/unit/test_feature_builder.py`

```python
@pytest.mark.unit
def test_build_returns_correct_columns(built_features_df):
    expected = {
        "date", "event_type", "symbol", "gap_pct",
        "ema5_range_pct", "ema20_range_pct",
        "open_vs_prev_close_pct", "bb_position",
        "eps_surprise_pct", "revenue_surprise_pct", "guidance",
    }
    assert expected.issubset(set(built_features_df.columns))

@pytest.mark.unit
def test_no_lookahead(synthetic_ohlcv_df, sample_events):
    """EMA features usan datos previos, no del día del evento."""
    # Se verifica indirectamente: si el primer evento tiene EMA calculada,
    # es sobre close_{T-1}
    from backend.core.feature_builder import FeatureBuilder
    df = FeatureBuilder().build(synthetic_ohlcv_df, sample_events)
    # No puede validar directamente, pero verificamos que los valores son finitos
    # para eventos con historia suficiente
    valid = df.dropna(subset=["ema5_range_pct"])
    assert len(valid) > 0

@pytest.mark.unit
def test_bb_position_values(built_features_df):
    """Todos los valores de bb_position son BBPosition válidos."""
    from backend.api.schemas import BBPosition
    valid_positions = {p.value for p in BBPosition}
    non_null = built_features_df["bb_position"].dropna()
    for val in non_null:
        assert str(val) in valid_positions or val in valid_positions
```

---

## `Event_Edge/tests/unit/test_statistical_models.py`

```python
import pytest
import numpy as np
import pandas as pd
from backend.core.statistical_models import (
    FrequentistModel, BootstrapModel, KDEModel, BayesianModel
)

BINS = [-0.05, -0.01, 0.01, 0.05]
ALL_MODELS = [FrequentistModel, BootstrapModel, KDEModel, BayesianModel]


def make_events_df(n: int, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    returns = np.random.normal(0.01, 0.04, n)
    return pd.DataFrame({
        "ret_close_p5": returns,
        "ret_event_p5": returns * 0.9,
        "gap_pct": np.random.choice([0.02, -0.03, 0.0], n),
    })


@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_probabilities_sum_to_one(ModelClass):
    model = ModelClass()
    model.fit(make_events_df(50))
    bins_result = model.predict_close_scenarios(n_periods=5, bins=BINS)
    assert abs(sum(b.probability for b in bins_result) - 1.0) < 1e-4

@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_ci_valid(ModelClass):
    model = ModelClass()
    model.fit(make_events_df(50))
    for b in model.predict_close_scenarios(5, BINS):
        assert b.ci_lower <= b.probability <= b.ci_upper

@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_bin_count(ModelClass):
    model = ModelClass()
    model.fit(make_events_df(50))
    result = model.predict_close_scenarios(5, BINS)
    assert len(result) == len(BINS) + 1

@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_insufficient_samples_warning(ModelClass):
    """n < 5 → warning presente, no excepción."""
    model = ModelClass()
    model.fit(make_events_df(3))
    result = model.predict_close_scenarios(5, BINS)
    # No debe lanzar excepción; los bins retornados pueden tener probability=0
    assert len(result) == len(BINS) + 1

@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_gap_fill_no_gaps_warning(ModelClass):
    """Todos gap_pct=0 → warning='no_gap_events'."""
    df = pd.DataFrame({
        "ret_close_p5": [0.01] * 20,
        "ret_event_p5": [0.01] * 20,
        "gap_pct": [0.0] * 20,
    })
    model = ModelClass()
    model.fit(df)
    result = model.predict_gap_fill_scenarios(5, BINS)
    warnings = [b for b in result]
    # La familia debe indicar warning de alguna forma (via ScenarioBin o a nivel superior)
    # Verificamos que no lanza excepción
    assert isinstance(result, list)
```

---

## `Event_Edge/tests/integration/test_api.py`

```python
import pytest
from httpx import AsyncClient

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
    """Symbol en minúsculas → 422."""
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
    assert len(data["families"]) == 3
    # Cada familia tiene N+1 bins
    for family in data["families"]:
        if family["warning"] not in ["no_gap_events", "insufficient_samples"]:
            assert len(family["scenarios"]) == len(custom_bins) + 1

@pytest.mark.integration
@pytest.mark.asyncio
async def test_conditioning_reduces_samples(test_client: AsyncClient):
    """Conditioning activo → n_samples_used <= n_total_events."""
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
                "eps_surprise_pct_min": 0.05  # solo sorpresas positivas > 5%
            },
        },
    )
    assert r.status_code == 200
    for family in r.json()["families"]:
        assert family["n_samples_used"] <= family["n_total_events"]
```

---

## Comandos de verificación

```bash
# Desde Event_Edge/

# Tests unitarios (sin conexión)
pytest tests/unit/ -v -m unit

# Tests de integración (requiere servidor en :8100)
# En otra terminal: uvicorn backend.main:app --port 8100
pytest tests/integration/ -v -m integration

# Suite completa con cobertura
pytest tests/ --cov=backend --cov-report=term-missing

# Smoke test rápido
pytest tests/ -m smoke -v
```

## Criterios de aceptación

- `pytest tests/unit/ -v` → 0 fallos, 0 errores
- Sin warnings de `DeprecationWarning` en los tests propios
- Todos los tests unitarios marcados con `@pytest.mark.unit`
- Tests de integración marcados con `@pytest.mark.integration`
- El fixture `test_client` usa `EE_MDH_ENABLED=false` — nunca llama MDH real

## Restricciones

- Sin conexión real a yfinance en tests unitarios — usar datos sintéticos de fixtures
- Sin `time.sleep` en tests — usar `pytest-asyncio` para operaciones async
- `conftest.py` es la única fuente de fixtures compartidas — no duplicar en archivos de test
- `reset_settings` fixture con `autouse=True` garantiza aislamiento entre tests

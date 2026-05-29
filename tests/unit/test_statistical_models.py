from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.core.metrics.probabilistic import _compute_gap_fill_column
from backend.core.statistical_models import (
    BayesianModel,
    BootstrapModel,
    FrequentistModel,
    KDEModel,
)

BINS = [-0.05, -0.01, 0.01, 0.05]
ALL_MODELS = [FrequentistModel, BootstrapModel, KDEModel, BayesianModel]


def make_events_df(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.01, 0.04, n)
    return pd.DataFrame(
        {
            "ret_close_p5": returns,
            "ret_gap_fill_p5": rng.choice([0.0, 1.0], n),
            "gap_pct": rng.choice([0.02, -0.03, 0.0], n),
        }
    )


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
    """n < 5 -> warning presente, no excepción."""
    model = ModelClass()
    model.fit(make_events_df(3))
    result = model.predict_close_scenarios(5, BINS)
    assert len(result) == len(BINS) + 1


@pytest.mark.unit
@pytest.mark.parametrize("ModelClass", ALL_MODELS)
def test_gap_fill_no_gaps_warning(ModelClass):
    """Todos gap_pct=0 -> no excepción en gap_fill."""
    df = pd.DataFrame(
        {
            "ret_close_p5": [0.01] * 20,
            "ret_gap_fill_p5": [0.0, 1.0] * 10,
            "gap_pct": [0.0] * 20,
        }
    )
    model = ModelClass()
    model.fit(df)
    result = model.predict_gap_fill_scenarios(5, [0.5])
    assert isinstance(result, list)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests de regresión: _compute_gap_fill_column
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 20, seed: int = 0) -> pd.DataFrame:
    """OHLCV diario sintético con DatetimeIndex UTC."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2023-01-02", periods=n, freq="B", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2, n)
    low = close - rng.uniform(0.5, 2, n)
    open_ = close + rng.normal(0, 0.5, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=dates)


@pytest.mark.unit
def test_gap_fill_n0_filled_via_low():
    """n_periods=0, gap UP: llenado porque low de P0 <= prev_close."""
    ohlcv = _make_ohlcv(20)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])
    ohlcv.at[event_date, "low"] = prev_close - 0.5   # low cruza nivel
    ohlcv.at[event_date, "close"] = prev_close + 1.0  # close NO llena

    events = pd.DataFrame({"date": [event_date], "gap_pct": [0.02]})
    result = _compute_gap_fill_column(events, ohlcv, n_periods=0)

    assert result.notna().any(), "n_periods=0 no debe producir solo NaN"
    assert result.iloc[0] == 1.0


@pytest.mark.unit
def test_gap_fill_n0_filled_via_close():
    """n_periods=0, gap UP: llenado porque close de P0 <= prev_close (aunque low no)."""
    ohlcv = _make_ohlcv(20, seed=3)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])
    ohlcv.at[event_date, "low"] = prev_close + 0.1    # low NO llena
    ohlcv.at[event_date, "close"] = prev_close - 0.2  # close SÍ llena

    events = pd.DataFrame({"date": [event_date], "gap_pct": [0.02]})
    result = _compute_gap_fill_column(events, ohlcv, n_periods=0)

    assert result.notna().any()
    assert result.iloc[0] == 1.0


@pytest.mark.unit
def test_gap_fill_n0_not_filled():
    """n_periods=0, gap UP: ni low ni close alcanzan prev_close → no llenado."""
    ohlcv = _make_ohlcv(20, seed=7)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])
    ohlcv.at[event_date, "low"] = prev_close + 1.0    # low por encima
    ohlcv.at[event_date, "high"] = prev_close + 3.0
    ohlcv.at[event_date, "close"] = prev_close + 1.5  # close también por encima

    events = pd.DataFrame({"date": [event_date], "gap_pct": [0.02]})
    result = _compute_gap_fill_column(events, ohlcv, n_periods=0)

    assert result.notna().any()
    assert result.iloc[0] == 0.0


@pytest.mark.unit
def test_gap_fill_n_positive_excludes_p0():
    """n_periods>0: la ventana es P1..Pn; P0 NO cuenta aunque llene el gap."""
    ohlcv = _make_ohlcv(20, seed=1)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])

    # P0 llenaría el gap (low <= prev_close), pero NO debe contar
    ohlcv.at[event_date, "low"] = prev_close - 0.5
    ohlcv.at[event_date, "close"] = prev_close - 0.2
    # P1..P3 no llenan el gap
    for j in range(1, 4):
        d = ohlcv.index[5 + j]
        ohlcv.at[d, "low"] = prev_close + 1.0
        ohlcv.at[d, "close"] = prev_close + 1.0
        ohlcv.at[d, "high"] = prev_close + 3.0

    events = pd.DataFrame({"date": [event_date], "gap_pct": [0.02]})
    result = _compute_gap_fill_column(events, ohlcv, n_periods=3)

    assert result.notna().any()
    assert result.iloc[0] == 0.0, "P0 no debe contar cuando n_periods>0"


@pytest.mark.unit
def test_gap_fill_n_positive_filled_in_p1():
    """n_periods>0: se llena el gap en P1 (dentro de la ventana P1..Pn)."""
    ohlcv = _make_ohlcv(20, seed=5)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])

    # P0 NO llena el gap
    ohlcv.at[event_date, "low"] = prev_close + 1.0
    ohlcv.at[event_date, "close"] = prev_close + 1.0
    # P1 SÍ llena el gap (low <= prev_close)
    d_p1 = ohlcv.index[6]
    ohlcv.at[d_p1, "low"] = prev_close - 0.5

    events = pd.DataFrame({"date": [event_date], "gap_pct": [0.02]})
    result = _compute_gap_fill_column(events, ohlcv, n_periods=3)

    assert result.notna().any()
    assert result.iloc[0] == 1.0, "Gap debe llenarse en P1"


@pytest.mark.unit
def test_gap_fill_down_via_high():
    """Gap DOWN: llenado porque high de P0 >= prev_close."""
    ohlcv = _make_ohlcv(20, seed=2)
    event_date = ohlcv.index[5]
    prev_close = float(ohlcv["close"].iloc[4])
    ohlcv.at[event_date, "high"] = prev_close + 0.5   # high supera nivel
    ohlcv.at[event_date, "close"] = prev_close - 1.0  # close no llena

    events = pd.DataFrame({"date": [event_date], "gap_pct": [-0.02]})  # gap DOWN
    result = _compute_gap_fill_column(events, ohlcv, n_periods=0)

    assert result.notna().any()
    assert result.iloc[0] == 1.0

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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

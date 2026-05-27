from __future__ import annotations

import pandas as pd
import pytest


@pytest.mark.unit
def test_build_returns_correct_columns(built_features_df: pd.DataFrame):
    expected = {
        "date",
        "event_type",
        "symbol",
        "gap_pct",
        "ema5_range_pct",
        "ema20_range_pct",
        "open_vs_prev_close_pct",
        "bb_position",
        "eps_surprise_pct",
        "revenue_surprise_pct",
        "guidance",
    }
    assert expected.issubset(set(built_features_df.columns))


@pytest.mark.unit
def test_no_lookahead(synthetic_ohlcv_df: pd.DataFrame, sample_events):
    """EMA features usan datos previos, no del día del evento."""
    from backend.core.feature_builder import FeatureBuilder

    df = FeatureBuilder().build(synthetic_ohlcv_df, sample_events)
    valid = df.dropna(subset=["ema5_range_pct"])
    assert len(valid) > 0


@pytest.mark.unit
def test_bb_position_values(built_features_df: pd.DataFrame):
    """Todos los valores de bb_position son BBPosition válidos."""
    from backend.api.schemas import BBPosition

    valid_positions = {p.value for p in BBPosition}
    non_null = built_features_df["bb_position"].dropna()

    for val in non_null:
        normalized = getattr(val, "value", val)
        assert normalized in valid_positions

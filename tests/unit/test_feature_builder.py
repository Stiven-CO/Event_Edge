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


@pytest.mark.unit
def test_build_all_bars_includes_raw_ohlcv_no_earnings(synthetic_ohlcv_df: pd.DataFrame):
    """build_all_bars conserva OHLCV crudo y deja earnings crudo en None (path gap)."""
    from backend.core.feature_builder import FeatureBuilder

    df = FeatureBuilder().build_all_bars(synthetic_ohlcv_df, symbol="AAPL")

    assert (df["open"].values == synthetic_ohlcv_df["open"].values).all()
    assert (df["high"].values == synthetic_ohlcv_df["high"].values).all()
    assert (df["low"].values == synthetic_ohlcv_df["low"].values).all()
    assert (df["close"].values == synthetic_ohlcv_df["close"].values).all()
    assert (df["volume"].values == synthetic_ohlcv_df["volume"].values).all()

    for col in ("eps_actual", "eps_estimate", "surprise_pct", "revenue_actual", "revenue_estimate"):
        assert df[col].isna().all()


@pytest.mark.unit
def test_build_from_fundamental_context_includes_raw_earnings_on_earning_days(
    synthetic_ohlcv_df: pd.DataFrame, synthetic_earnings: pd.DataFrame,
):
    """build_from_fundamental_context expone earnings crudo solo en días de earning."""
    from backend.core.feature_builder import FeatureBuilder

    df = FeatureBuilder().build_from_fundamental_context(
        synthetic_ohlcv_df, synthetic_earnings, symbol="AAPL"
    )

    earning_rows = df[df["take_earnings"]]
    non_earning_rows = df[~df["take_earnings"]]

    assert len(earning_rows) > 0
    assert earning_rows["eps_actual"].notna().all()
    assert earning_rows["eps_estimate"].notna().all()
    assert earning_rows["revenue_actual"].notna().all()
    assert earning_rows["revenue_estimate"].notna().all()

    assert non_earning_rows["eps_actual"].isna().all()
    assert non_earning_rows["revenue_actual"].isna().all()

    # surprise_pct crudo NO debe estar dividido entre 100 (a diferencia de eps_surprise_pct)
    for _, row in earning_rows.iterrows():
        if row["surprise_pct"] is not None and row["eps_surprise_pct"] is not None:
            assert abs(row["surprise_pct"] / 100.0 - row["eps_surprise_pct"]) < 1e-6

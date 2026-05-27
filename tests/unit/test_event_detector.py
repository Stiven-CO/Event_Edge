from __future__ import annotations

import pandas as pd
import pytest

from backend.core.event_detector import EventDetector


@pytest.mark.unit
def test_detect_earnings_alignment(
    synthetic_ohlcv_df: pd.DataFrame,
    synthetic_earnings: pd.DataFrame,
):
    """Todas las fechas retornadas deben estar en el index de ohlcv_df."""
    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, synthetic_earnings)

    ohlcv_days = {ts.date() for ts in synthetic_ohlcv_df.index.normalize()}
    for ev in events:
        assert ev.date.date() in ohlcv_days


@pytest.mark.unit
def test_detect_earnings_weekend_mapping(synthetic_ohlcv_df: pd.DataFrame):
    """Earnings en fin de semana -> mapea al lunes siguiente."""
    saturday = pd.Timestamp("2022-01-08", tz="UTC")
    monday = pd.Timestamp("2022-01-10", tz="UTC")

    earnings = pd.DataFrame(
        {
            "eps_actual": [1.5],
            "eps_estimate": [1.4],
            "revenue_actual": [None],
            "revenue_estimate": [None],
        },
        index=[saturday],
    )

    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, earnings)

    if events:
        assert events[0].date.date() == monday.date()


@pytest.mark.unit
def test_detect_earnings_out_of_range(synthetic_ohlcv_df: pd.DataFrame):
    """Earnings fuera del rango OHLCV -> lista vacía sin error."""
    future = pd.Timestamp("2099-01-01", tz="UTC")
    earnings = pd.DataFrame(
        {
            "eps_actual": [2.0],
            "eps_estimate": [1.9],
            "revenue_actual": [None],
            "revenue_estimate": [None],
        },
        index=[future],
    )

    detector = EventDetector()
    events = detector.detect_earnings(synthetic_ohlcv_df, earnings)
    assert events == []


@pytest.mark.unit
def test_detect_gaps_positive(synthetic_ohlcv_df: pd.DataFrame):
    """Gap positivo > threshold se detecta."""
    detector = EventDetector()
    events = detector.detect_gaps(synthetic_ohlcv_df, threshold_pct=0.5)
    positive_gaps = [e for e in events if e.gap_pct is not None and e.gap_pct > 0]
    assert len(positive_gaps) > 0


@pytest.mark.unit
def test_detect_gaps_excludes_earnings(
    synthetic_ohlcv_df: pd.DataFrame,
    sample_events,
):
    """Fechas de earnings NO aparecen en el resultado de detect_gaps."""
    earnings_dates = [e.date for e in sample_events]

    detector = EventDetector()
    gap_events = detector.detect_gaps(
        synthetic_ohlcv_df,
        threshold_pct=0.0,
        earnings_dates=earnings_dates,
    )
    gap_dates = {e.date for e in gap_events}

    for ed in earnings_dates:
        assert ed not in gap_dates


@pytest.mark.unit
def test_detect_gaps_empty_ohlcv():
    """ohlcv_df vacío -> lista vacía."""
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    detector = EventDetector()
    assert detector.detect_gaps(empty) == []

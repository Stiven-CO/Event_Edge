from __future__ import annotations

import pandas as pd
import pytest

from backend.api.schemas import EventType
from backend.core.conditioning_pipeline import select_raw_events


@pytest.mark.unit
def test_select_raw_events_earnings_alignment(
    synthetic_ohlcv_df: pd.DataFrame,
    synthetic_earnings: pd.DataFrame,
):
    """Todas las fechas retornadas deben estar en el index de ohlcv_df."""
    events = select_raw_events(
        synthetic_ohlcv_df, synthetic_earnings, event_type=EventType.earnings, symbol="AAPL",
    )

    ohlcv_days = {ts.date() for ts in synthetic_ohlcv_df.index.normalize()}
    for ev in events:
        assert ev.date.date() in ohlcv_days


@pytest.mark.unit
def test_select_raw_events_earnings_weekend_mapping(synthetic_ohlcv_df: pd.DataFrame):
    """Earnings en fin de semana -> mapea al siguiente día hábil."""
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

    events = select_raw_events(
        synthetic_ohlcv_df, earnings, event_type=EventType.earnings, symbol="AAPL",
    )

    if events:
        assert events[0].date.date() == monday.date()


@pytest.mark.unit
def test_select_raw_events_earnings_out_of_range(synthetic_ohlcv_df: pd.DataFrame):
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

    events = select_raw_events(
        synthetic_ohlcv_df, earnings, event_type=EventType.earnings, symbol="AAPL",
    )
    assert events == []


@pytest.mark.unit
def test_fetch_earnings_dates_maps_reported_eps_to_eps_actual(monkeypatch):
    """Los datos de yfinance con Reported EPS deben mapearse a eps_actual."""
    from backend.data.earnings_loader import EarningsLoader

    fake_df = pd.DataFrame(
        {
            "Reported EPS": [1.23],
            "EPS Estimate": [1.10],
            "Revenue Actual": [None],
            "Revenue Estimate": [None],
        },
        index=[pd.Timestamp("2024-06-10", tz="UTC")],
    )

    class FakeTicker:
        earnings_dates = fake_df

    fake_yfinance = type("yf", (), {"Ticker": lambda symbol: FakeTicker()})
    import sys

    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    loader = EarningsLoader()
    df = loader.fetch_earnings_dates("AAPL")

    assert "eps_actual" in df.columns
    assert df.loc[pd.Timestamp("2024-06-10", tz="UTC"), "eps_actual"] == 1.23
    assert df.loc[pd.Timestamp("2024-06-10", tz="UTC"), "eps_estimate"] == 1.10


@pytest.mark.unit
def test_select_raw_events_gap_positive(synthetic_ohlcv_df: pd.DataFrame):
    """Gap positivo > threshold se detecta."""
    events = select_raw_events(
        synthetic_ohlcv_df,
        pd.DataFrame(),
        event_type=EventType.gap,
        symbol="AAPL",
        gap_threshold_pct=0.5,
    )
    positive_gaps = [e for e in events if e.gap_pct is not None and e.gap_pct > 0]
    assert len(positive_gaps) > 0


@pytest.mark.unit
def test_select_raw_events_gap_excludes_earnings(
    synthetic_ohlcv_df: pd.DataFrame,
    synthetic_earnings: pd.DataFrame,
):
    """Fechas de earnings NO aparecen en el resultado de detección de gaps por defecto."""
    gap_events = select_raw_events(
        synthetic_ohlcv_df,
        synthetic_earnings,
        event_type=EventType.gap,
        symbol="AAPL",
        gap_threshold_pct=0.0,
    )
    earnings_events = select_raw_events(
        synthetic_ohlcv_df,
        synthetic_earnings,
        event_type=EventType.earnings,
        symbol="AAPL",
    )

    earnings_dates = {e.date.date() for e in earnings_events}
    gap_dates = {e.date.date() for e in gap_events}
    assert not (earnings_dates & gap_dates)


@pytest.mark.unit
def test_select_raw_events_empty_ohlcv():
    """ohlcv_df vacío -> lista vacía."""
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    events = select_raw_events(empty, pd.DataFrame(), event_type=EventType.gap, symbol="AAPL")
    assert events == []

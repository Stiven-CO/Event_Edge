"""
Modelo frecuentista: probabilidad como frecuencia observada con Wilson score CI.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from backend.api.schemas import ScenarioBin
from backend.core.statistical_models.base import BaseEventModel

_Z = 1.96  # z-score para CI 95%


def _wilson_ci(k: int, n: int) -> tuple[float, float]:
    """Wilson score interval para una proporción k/n."""
    if n == 0:
        return 0.0, 1.0
    p_hat = k / n
    z2 = _Z * _Z
    center = (k + z2 / 2) / (n + z2)
    margin = _Z * math.sqrt(n * p_hat * (1 - p_hat) + z2 / 4) / (n + z2)
    return max(0.0, center - margin), min(1.0, center + margin)


class FrequentistModel(BaseEventModel):
    """Probabilidades como frecuencias observadas con Wilson score CI al 95%."""

    def __init__(self) -> None:
        self._events_df: pd.DataFrame = pd.DataFrame()

    def fit(self, events_df: pd.DataFrame) -> None:
        self._events_df = events_df.copy()

    def _predict(self, col: str, n_periods: int, bins: list[float]) -> list[ScenarioBin]:
        returns = self._extract_returns(self._events_df, f"{col}_p{n_periods}")
        n = len(returns)
        if n < self.MIN_SAMPLES:
            return self._insufficient_bins(bins)

        indices = self._digitize_returns(returns, bins)
        n_bins = len(bins) + 1
        probs = np.zeros(n_bins)
        ci_lo = np.zeros(n_bins)
        ci_hi = np.zeros(n_bins)

        for i in range(n_bins):
            k = int(np.sum(indices == i))
            probs[i] = k / n
            ci_lo[i], ci_hi[i] = _wilson_ci(k, n)

        return self._build_scenario_bins(returns, bins, probs, ci_lo, ci_hi)

    def predict_close_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        return self._predict("ret_close", n_periods, bins)

    def predict_gap_fill_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        gap_fill_returns = self._extract_returns(self._events_df, f"ret_gap_fill_p{n_periods}")
        n = len(gap_fill_returns)
        if n < self.MIN_SAMPLES:
            return self._insufficient_bins(bins)
        return self._predict("ret_gap_fill", n_periods, bins)

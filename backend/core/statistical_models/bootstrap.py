"""
Modelo Bootstrap: probabilidades y CI por remuestreo con reemplazo (1000 iteraciones).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.api.schemas import ScenarioBin
from backend.core.statistical_models.base import BaseEventModel

_N_ITER = 1000
_RNG_SEED = 42


class BootstrapModel(BaseEventModel):
    """Probabilidades bootstrap con CI por percentiles 2.5 y 97.5."""

    def __init__(self) -> None:
        self._events_df: pd.DataFrame = pd.DataFrame()

    def fit(self, events_df: pd.DataFrame) -> None:
        self._events_df = events_df.copy()

    def _predict(self, col: str, n_periods: int, bins: list[float]) -> list[ScenarioBin]:
        returns = self._extract_returns(self._events_df, f"{col}_p{n_periods}")
        n = len(returns)
        if n < self.MIN_SAMPLES:
            return self._insufficient_bins(bins)

        rng = np.random.default_rng(_RNG_SEED)
        n_bins = len(bins) + 1
        boot_freqs = np.zeros((_N_ITER, n_bins))

        for it in range(_N_ITER):
            sample = rng.choice(returns, size=n, replace=True)
            indices = self._digitize_returns(sample, bins)
            for i in range(n_bins):
                boot_freqs[it, i] = np.sum(indices == i) / n

        probs = boot_freqs.mean(axis=0)
        ci_lo = np.percentile(boot_freqs, 2.5, axis=0)
        ci_hi = np.percentile(boot_freqs, 97.5, axis=0)

        # Asegurar ci_lower <= probability <= ci_upper
        ci_lo = np.minimum(ci_lo, probs)
        ci_hi = np.maximum(ci_hi, probs)

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

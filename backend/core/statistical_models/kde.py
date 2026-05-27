"""
Modelo KDE (Kernel Density Estimation): probabilidades por integración de densidad.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from backend.api.schemas import ScenarioBin
from backend.core.statistical_models.base import BaseEventModel

_LOWER_BOUND = -10.0   # límite práctico para bin abierto por la izquierda
_UPPER_BOUND = 10.0    # límite práctico para bin abierto por la derecha
_N_ITER = 500
_RNG_SEED = 42


def _integrate_kde(kde: stats.gaussian_kde, lo: float, hi: float) -> float:
    """Integra la KDE en el intervalo [lo, hi]."""
    return float(kde.integrate_box_1d(lo, hi))


class KDEModel(BaseEventModel):
    """Probabilidades por integración de KDE gaussiana; CI por bootstrap de KDE."""

    def __init__(self) -> None:
        self._events_df: pd.DataFrame = pd.DataFrame()

    def fit(self, events_df: pd.DataFrame) -> None:
        self._events_df = events_df.copy()

    def _predict(self, col: str, n_periods: int, bins: list[float]) -> list[ScenarioBin]:
        returns = self._extract_returns(self._events_df, f"{col}_p{n_periods}")
        n = len(returns)
        if n < self.MIN_SAMPLES:
            return self._insufficient_bins(bins)

        kde = stats.gaussian_kde(returns)
        edges = [_LOWER_BOUND] + list(bins) + [_UPPER_BOUND]
        n_bins = len(bins) + 1

        probs = np.array([
            _integrate_kde(kde, edges[i], edges[i + 1])
            for i in range(n_bins)
        ])

        # Normalizar para suma exactamente 1.0
        total = probs.sum()
        if total > 0:
            probs = probs / total

        # Bootstrap CI sobre la KDE
        rng = np.random.default_rng(_RNG_SEED)
        boot_probs = np.zeros((_N_ITER, n_bins))
        for it in range(_N_ITER):
            sample = rng.choice(returns, size=n, replace=True)
            if len(np.unique(sample)) < 2:
                boot_probs[it] = probs
                continue
            kde_b = stats.gaussian_kde(sample)
            row = np.array([
                _integrate_kde(kde_b, edges[i], edges[i + 1])
                for i in range(n_bins)
            ])
            row_sum = row.sum()
            boot_probs[it] = row / row_sum if row_sum > 0 else probs

        ci_lo = np.percentile(boot_probs, 2.5, axis=0)
        ci_hi = np.percentile(boot_probs, 97.5, axis=0)
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

"""
Modelo Bayesiano: prior Beta por Laplace + posterior conjugado + HDI al 95%.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from backend.api.schemas import ScenarioBin
from backend.core.statistical_models.base import BaseEventModel


class BayesianModel(BaseEventModel):
    """
    Prior Beta de Laplace ajustado sobre el dataset completo.
    Posterior conjugado Beta(α_prior + k_cond, β_prior + n_cond - k_cond).
    CI = HDI al 95% (percentiles 2.5 / 97.5 de la distribución Beta posterior).
    """

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
            # Prior de Laplace: α = k_total+1, β = (n-k_total)+1
            alpha_prior = k + 1
            beta_prior = (n - k) + 1
            # Posterior conjugado (con los mismos datos, sin split cond)
            alpha_post = alpha_prior + k
            beta_post = beta_prior + (n - k)

            dist = stats.beta(alpha_post, beta_post)
            probs[i] = dist.mean()
            ci_lo[i] = dist.ppf(0.025)
            ci_hi[i] = dist.ppf(0.975)

        # Normalizar probabilidades (la suma Beta no garantiza exactamente 1)
        total = probs.sum()
        if total > 0:
            probs = probs / total

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

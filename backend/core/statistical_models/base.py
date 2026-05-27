"""
Interfaz abstracta para modelos de análisis probabilístico de eventos.

Contract de events_df (output de FeatureBuilder + columnas de retorno):
    - Columnas requeridas: date, event_type, gap_pct
        - Columnas de retorno forward: ret_close_p{n}
            donde ret_close_p0 = (close_P0 - open_P0) / open_P0
                        ret_close_pN = (close_PN - close_P0) / close_P0 para N > 0
    - Filas ya filtradas por condicionamiento (responsabilidad del caller)

Contract de bins:
    - list[float] en decimal ordenados de menor a mayor
    - Generan N+1 intervalos: (-∞, b0], (b0, b1], ..., (b_{n-1}, +∞)
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from backend.api.schemas import ScenarioBin


class BaseEventModel(ABC):

    MIN_SAMPLES = 5

    @abstractmethod
    def fit(self, events_df: pd.DataFrame) -> None:
        """Ajusta el modelo con el DataFrame de eventos."""
        ...

    @abstractmethod
    def predict_close_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        """
        Familia 'close_return': P(ret_close_pN in bin)
        ret = (close_P0 - open_P0) / open_P0 si N=0,
              (close_PN - close_P0) / close_P0 si N>0
        """
        ...

    @abstractmethod
    def predict_gap_fill_scenarios(
        self, n_periods: int, bins: list[float]
    ) -> list[ScenarioBin]:
        """
        Familia 'gap_fill': P(gap se cierra dentro de n_periods sesiones)
        Si ningún evento tiene gap_pct != 0 → warning = 'no_gap_events'
        """
        ...

    def _make_bin_labels(self, bins: list[float]) -> list[str]:
        """
        Genera etiquetas legibles para los N+1 intervalos definidos por bins.
        Ejemplo: bins=[-0.05, 0.05] → ["< -5%", "-5% a +5%", "> +5%"]
        """
        def pct(v: float) -> str:
            return f"{v * 100:+.0f}%" if v != 0 else "0%"

        labels: list[str] = []
        for i, b in enumerate(bins):
            if i == 0:
                labels.append(f"< {pct(b)}")
            else:
                labels.append(f"{pct(bins[i - 1])} a {pct(b)}")
        labels.append(f"> {pct(bins[-1])}")
        return labels

    def _check_insufficient_samples(self, n: int) -> str | None:
        """Retorna 'insufficient_samples' si n < MIN_SAMPLES, else None."""
        return "insufficient_samples" if n < self.MIN_SAMPLES else None

    def _insufficient_bins(self, bins: list[float]) -> list[ScenarioBin]:
        """Retorna bins vacíos cuando n_samples < MIN_SAMPLES."""
        labels = self._make_bin_labels(bins)
        edges = [None] + list(bins) + [None]
        return [
            ScenarioBin(
                label=labels[i],
                lower=edges[i],
                upper=edges[i + 1],
                probability=0.0,
                ci_lower=0.0,
                ci_upper=1.0,
                event_count=0,
            )
            for i in range(len(labels))
        ]

    def _extract_returns(self, events_df: pd.DataFrame, col: str) -> np.ndarray:
        """Extrae array de retornos de la columna dada, eliminando NaN."""
        if col not in events_df.columns:
            return np.array([])
        return events_df[col].dropna().to_numpy(dtype=float)

    def _build_scenario_bins(
        self,
        returns: np.ndarray,
        bins: list[float],
        probs: np.ndarray,
        ci_lowers: np.ndarray,
        ci_uppers: np.ndarray,
    ) -> list[ScenarioBin]:
        """Construye lista de ScenarioBin con los arrays calculados."""
        labels = self._make_bin_labels(bins)
        edges = [None] + list(bins) + [None]
        result: list[ScenarioBin] = []
        for i, label in enumerate(labels):
            lo_edge = edges[i]
            hi_edge = edges[i + 1]
            if lo_edge is None and hi_edge is None:
                count = len(returns)
            elif lo_edge is None:
                count = int(np.sum(returns <= hi_edge))
            elif hi_edge is None:
                count = int(np.sum(returns > lo_edge))
            else:
                count = int(np.sum((returns > lo_edge) & (returns <= hi_edge)))

            result.append(
                ScenarioBin(
                    label=label,
                    lower=lo_edge,
                    upper=hi_edge,
                    probability=float(probs[i]),
                    ci_lower=float(ci_lowers[i]),
                    ci_upper=float(ci_uppers[i]),
                    event_count=count,
                )
            )
        return result

    def _digitize_returns(self, returns: np.ndarray, bins: list[float]) -> np.ndarray:
        """
        Asigna cada retorno a un bin index (0-based, 0 = primero = -∞ a bins[0]).
        """
        return np.digitize(returns, bins=bins, right=True)

"""
Ensambla el payload del objeto Edge a partir de los resultados en memoria de
un análisis (ProbabilisticResult).

Contenido estadístico definido en el plan ("Contenido estadístico del Edge
para Risk Engine"): ConditionedSummary (info del evento, P0) +
FutureReturnMetrics (info del retorno posterior, P1→Pn) completos, 3 métricas
derivadas de uso interno para Risk Engine (win_rate, payoff_ratio,
expectancy), y las families (escenario-bins) de close_return/gap_fill. El
resto de la forma final del objeto Edge queda abierto para fase posterior.

`return_samples_close` se excluye del JSON y se devuelve por separado — se
persiste en un archivo Parquet aparte (backend/core/edge/store.py) por ser
mucho más económico que embeberlo como array de floats en el JSON.
"""
from __future__ import annotations

from typing import Any

from backend.api.schemas import FutureReturnMetrics, ProbabilisticResult


def _derive_risk_metrics(future: FutureReturnMetrics) -> dict[str, float | None]:
    """
    3 métricas derivadas triviales, de uso interno del Edge (no expuestas en
    el schema de /probabilistic): win_rate, payoff_ratio, expectancy.
    """
    n_pos = future.return_count_positive
    n_neg = future.return_count_negative
    n_total = n_pos + n_neg

    win_rate = (n_pos / n_total) if n_total > 0 else None

    payoff_ratio: float | None = None
    if future.return_avg_negative not in (None, 0.0) and future.return_avg_positive is not None:
        payoff_ratio = future.return_avg_positive / abs(future.return_avg_negative)

    expectancy: float | None = None
    if win_rate is not None:
        avg_pos = future.return_avg_positive or 0.0
        avg_neg = future.return_avg_negative or 0.0
        expectancy = win_rate * avg_pos + (1 - win_rate) * avg_neg

    return {
        "win_rate": win_rate,
        "payoff_ratio": payoff_ratio,
        "expectancy": expectancy,
    }


def assemble_edge_payload(
    symbol: str,
    timeframe: str,
    n_periods: int,
    probabilistic_result: ProbabilisticResult,
) -> tuple[dict[str, Any], list[float]]:
    """
    Devuelve (edge_payload, return_samples_close) donde:
      - edge_payload es el dict JSON-serializable a persistir en `edge.json`
        (campo `edge` del EdgeEnvelope), sin `return_samples_close`.
      - return_samples_close son las muestras crudas de retorno al período
        analizado, a persistir aparte en `return_samples.parquet`.
    """
    summary = probabilistic_result.conditioned_summary
    future = probabilistic_result.future_return_metrics
    if summary is None or future is None:
        raise ValueError(
            "probabilistic_result.conditioned_summary y future_return_metrics son "
            "requeridos para ensamblar el Edge"
        )

    edge_payload: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "n_periods": n_periods,
        "conditioned_summary": summary.model_dump(),
        "future_return_metrics": future.model_dump(exclude={"return_samples_close"}),
        "risk_metrics": _derive_risk_metrics(future),
        "families": [f.model_dump() for f in probabilistic_result.families],
    }

    return edge_payload, future.return_samples_close

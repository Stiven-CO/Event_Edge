"""
Ensambla el payload del objeto Edge y sus plots PNG a partir de los
resultados en memoria de un análisis (ProbabilisticResult + PriceActionResult).

Contenido estadístico definido en el plan ("Contenido estadístico del Edge
para Risk Engine"): el ConditionedSummary completo, 3 métricas derivadas de
uso interno para Risk Engine (win_rate, payoff_ratio, expectancy), n_periods,
y las families (escenario-bins) de close_return/gap_fill. El resto de la
forma final del objeto Edge queda abierto para fase posterior.
"""
from __future__ import annotations

from typing import Any

from backend.api.schemas import ConditionedSummary, PriceActionResult, ProbabilisticResult
from backend.core.edge.plotting import (
    render_close_return_plot,
    render_gap_fill_plot,
    render_price_action_plot,
)


def _derive_risk_metrics(summary: ConditionedSummary) -> dict[str, float | None]:
    """
    3 métricas derivadas triviales, de uso interno del Edge (no expuestas en
    el schema de /probabilistic): win_rate, payoff_ratio, expectancy.
    """
    n_pos = summary.return_count_positive
    n_neg = summary.return_count_negative
    n_total = n_pos + n_neg

    win_rate = (n_pos / n_total) if n_total > 0 else None

    payoff_ratio: float | None = None
    if summary.return_avg_negative not in (None, 0.0) and summary.return_avg_positive is not None:
        payoff_ratio = summary.return_avg_positive / abs(summary.return_avg_negative)

    expectancy: float | None = None
    if win_rate is not None:
        avg_pos = summary.return_avg_positive or 0.0
        avg_neg = summary.return_avg_negative or 0.0
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
    price_action_result: PriceActionResult,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """
    Devuelve (edge_payload, plots) donde:
      - edge_payload es el dict JSON-serializable a persistir en `edge.json` (campo `edge` del EdgeEnvelope).
      - plots es {nombre_logico: bytes_png} para close_return, gap_fill, price_action.
    """
    summary = probabilistic_result.conditioned_summary
    if summary is None:
        raise ValueError("probabilistic_result.conditioned_summary es requerido para ensamblar el Edge")

    families_by_name = {f.family: f for f in probabilistic_result.families}
    close_return_family = families_by_name.get("close_return")
    gap_fill_family = families_by_name.get("gap_fill")

    edge_payload: dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "n_periods": n_periods,
        "conditioned_summary": summary.model_dump(),
        "risk_metrics": _derive_risk_metrics(summary),
        "families": [f.model_dump() for f in probabilistic_result.families],
    }

    plots: dict[str, bytes] = {}
    if close_return_family is not None:
        plots["close_return"] = render_close_return_plot(close_return_family)
    if gap_fill_family is not None:
        plots["gap_fill"] = render_gap_fill_plot(gap_fill_family)
    plots["price_action"] = render_price_action_plot(price_action_result)

    return edge_payload, plots

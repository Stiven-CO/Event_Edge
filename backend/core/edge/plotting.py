"""
Renderizado server-side de los plots persistidos junto al objeto Edge.

Usa matplotlib con backend no interactivo (Agg) y escribe a buffers en
memoria — el store se encarga de la escritura a disco. La lógica visual
(bins de escenarios, bandas ±1σ) replica lo que el usuario ve en
ProbabilityPanel.tsx / PriceActionPanel.tsx en el frontend.
"""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from backend.api.schemas import ProbabilisticFamily, PriceActionResult  # noqa: E402

_FIGSIZE = (7, 4)
_DPI = 110
_BAR_COLOR = "#00d2c8"


def _fig_to_png_bytes(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _render_scenario_family_plot(family: ProbabilisticFamily, title: str) -> bytes:
    """Bar chart horizontal de probabilidad por bin de escenario (bins de la familia)."""
    fig, ax = plt.subplots(figsize=_FIGSIZE)

    if not family.scenarios:
        ax.text(0.5, 0.5, "Sin datos suficientes", ha="center", va="center", transform=ax.transAxes)
    else:
        labels = [s.label for s in family.scenarios]
        probs = [s.probability * 100 for s in family.scenarios]
        y_pos = range(len(labels))
        ax.barh(y_pos, probs, color=_BAR_COLOR)
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(labels)
        ax.invert_yaxis()
        ax.set_xlabel("Probabilidad (%)")
        for y, p in zip(y_pos, probs):
            ax.text(p, y, f" {p:.1f}%", va="center", fontsize=8)

    ax.set_title(f"{title} (n={family.n_samples_used}/{family.n_total_events})")
    fig.tight_layout()
    return _fig_to_png_bytes(fig)


def render_close_return_plot(family: ProbabilisticFamily) -> bytes:
    return _render_scenario_family_plot(family, "Probabilidad — Close Return")


def render_gap_fill_plot(family: ProbabilisticFamily) -> bytes:
    return _render_scenario_family_plot(family, "Probabilidad — Gap Fill")


def render_price_action_plot(result: PriceActionResult) -> bytes:
    """Serie normalizada (índice 100) para all/win/loss con bandas ±1σ si están disponibles."""
    fig, ax = plt.subplots(figsize=_FIGSIZE)

    series_map = {
        "Todos": (result.series_all, "#8a8fa3"),
        "Ganadores": (result.series_win, "#2ecc71"),
        "Perdedores": (result.series_loss, "#e74c3c"),
    }

    for label, (series, color) in series_map.items():
        if not series.points:
            continue
        xs = [p.x for p in series.points]
        ys = [p.y for p in series.points]
        ax.plot(xs, ys, label=label, color=color, linewidth=1.5)
        if series.band_upper and series.band_lower:
            upper = [p.y for p in series.band_upper]
            lower = [p.y for p in series.band_lower]
            ax.fill_between(xs, lower, upper, color=color, alpha=0.12)

    ax.axhline(100, color="#888888", linewidth=0.8, linestyle="--")
    if result.x_labels:
        tick_count = min(len(result.x_labels), 10)
        step = max(1, len(result.x_labels) // tick_count)
        ax.set_xticks(range(1, len(result.x_labels) + 1, step))
        ax.set_xticklabels(result.x_labels[::step], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Precio indexado (100 = evento)")
    ax.set_title(
        f"Price Action ({result.anchor_mode}) — "
        f"n={result.n_events_all} (win={result.n_events_win}, loss={result.n_events_loss})"
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    return _fig_to_png_bytes(fig)

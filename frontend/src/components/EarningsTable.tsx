import { useMemo, useState } from "react";

import type { ConditionedBar, ConditioningParams } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

// ── Conditioning summary helper ───────────────────────────────────────────────

function formatConditioningSummary(c: ConditioningParams): string | null {
  const parts: string[] = [];

  // A — Tendencia
  if (c.trend_directions?.length) parts.push(`Tendencia: ${c.trend_directions.join(", ")}`);
  if (c.ema5_vs_ema20_ratio_min != null || c.ema5_vs_ema20_ratio_max != null)
    parts.push(`EMA5/20: ${c.ema5_vs_ema20_ratio_min ?? "–"} a ${c.ema5_vs_ema20_ratio_max ?? "–"}`);
  if (c.price_vs_ema50_pct_min != null || c.price_vs_ema50_pct_max != null)
    parts.push(`Precio vs EMA50: ${c.price_vs_ema50_pct_min ?? "–"} a ${c.price_vs_ema50_pct_max ?? "–"}%`);

  // B — Momentum
  if (c.rsi14_min != null || c.rsi14_max != null)
    parts.push(`RSI(14): ${c.rsi14_min ?? "–"}–${c.rsi14_max ?? "–"}`);
  if (c.return_5d_min != null || c.return_5d_max != null)
    parts.push(`Ret.5d: ${c.return_5d_min ?? "–"} a ${c.return_5d_max ?? "–"}%`);
  if (c.return_20d_min != null || c.return_20d_max != null)
    parts.push(`Ret.20d: ${c.return_20d_min ?? "–"} a ${c.return_20d_max ?? "–"}%`);

  // C — Sobreextensión
  if (c.bb_positions?.length) parts.push(`BB pos: ${c.bb_positions.join(", ")}`);
  if (c.rsi14_zones?.length) parts.push(`RSI zona: ${c.rsi14_zones.join(", ")}`);

  // D — Volatilidad
  if (c.vol_regimes?.length) parts.push(`Vol: ${c.vol_regimes.join(", ")}`);
  if (c.atr_pct_min != null || c.atr_pct_max != null)
    parts.push(`ATR%: ${c.atr_pct_min ?? "–"}–${c.atr_pct_max ?? "–"}`);

  // E — Fundamental
  if (c.guidance_directions?.length) parts.push(`Guidance: ${c.guidance_directions.join(", ")}`);
  if (c.eps_surprise_pct_min != null || c.eps_surprise_pct_max != null)
    parts.push(`EPS sorpresa: ${c.eps_surprise_pct_min ?? "–"} a ${c.eps_surprise_pct_max ?? "–"}%`);

  // F — Posicionamiento
  if (c.gap_direction && c.gap_direction !== "any") parts.push(`Gap: ${c.gap_direction}`);
  if (c.gap_pct_min != null || c.gap_pct_max != null)
    parts.push(`Gap%: ${c.gap_pct_min ?? "–"} a ${c.gap_pct_max ?? "–"}`);

  // G — Estacionalidad
  if (c.days_of_week?.length) parts.push(`Días: ${c.days_of_week.join(", ")}`);
  if (c.months?.length) parts.push(`Meses: ${c.months.join(", ")}`);
  if (c.quarters?.length) parts.push(`Trimestres: ${c.quarters.join(", ")}`);
  if (c.earnings_seasons?.length) parts.push(`Temporada: ${c.earnings_seasons.join(", ")}`);

  return parts.length > 0 ? parts.join(" · ") : null;
}

// ── Cell formatters ───────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 2): string {
  if (v == null) return "–";
  const pct = v * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(decimals)}%`;
}

function fmtNum(v: number | null, decimals = 1): string {
  if (v == null) return "–";
  return v.toFixed(decimals);
}

// ── Component ─────────────────────────────────────────────────────────────────

export function EarningsTable() {
  const conditioningCount = useEventEdgeStore((s) => s.conditioningCount);
  const conditioning      = useEventEdgeStore((s) => s.conditioning);
  const [desc, setDesc]   = useState(true);

  const rows: ConditionedBar[] = useMemo(() => {
    const source = conditioningCount?.rows ?? [];
    return [...source].sort((a, b) => {
      const delta = new Date(a.date).getTime() - new Date(b.date).getTime();
      return desc ? -delta : delta;
    });
  }, [conditioningCount, desc]);

  const summary = formatConditioningSummary(conditioning);

  return (
    <section className="panel mt-4 p-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h3 className="font-display text-lg font-semibold">Events</h3>
          <p className="mt-0.5 text-xs text-ink-muted">
            {summary ?? "Sin filtros activos"}
          </p>
        </div>
        <button type="button" className="button-ghost" onClick={() => setDesc((v) => !v)}>
          Fecha {desc ? "desc" : "asc"}
        </button>
      </div>

      <div className="max-h-[360px] overflow-auto rounded-xl border border-surface-border bg-surface-raised">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-overlay text-ink-secondary">
            <tr>
              <th className="px-3 py-2 text-left">Fecha</th>
              <th className="px-3 py-2 text-left">Gap%</th>
              <th className="px-3 py-2 text-left">Tendencia</th>
              <th className="px-3 py-2 text-left">RSI(14)</th>
              <th className="px-3 py-2 text-left">Día</th>
              <th className="px-3 py-2 text-left">Ret.5d</th>
              <th className="px-3 py-2 text-left">Régimen Vol.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                className="border-t border-surface-border/60 text-ink-primary hover:bg-surface-overlay/40"
              >
                <td className="px-3 py-2">{new Date(r.date).toLocaleDateString()}</td>
                <td className="px-3 py-2">
                  <span className={r.gap_pct != null && r.gap_pct >= 0 ? "text-status-success" : "text-status-error"}>
                    {fmtPct(r.gap_pct)}
                  </span>
                </td>
                <td className="px-3 py-2 capitalize">{r.trend_direction ?? "–"}</td>
                <td className="px-3 py-2">{fmtNum(r.rsi14)}</td>
                <td className="px-3 py-2 capitalize">{r.day_of_week ?? "–"}</td>
                <td className="px-3 py-2">
                  {r.return_5d == null ? "–" : (
                    <span className={r.return_5d >= 0 ? "text-status-success" : "text-status-error"}>
                      {fmtPct(r.return_5d)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 capitalize">{r.vol_regime ?? "–"}</td>
              </tr>
            ))}

            {conditioningCount === null && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-ink-muted">
                  Aplica un condicionamiento para ver las filas del dataset.
                </td>
              </tr>
            )}
            {conditioningCount !== null && rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-ink-muted">
                  Ninguna barra cumple los filtros activos.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

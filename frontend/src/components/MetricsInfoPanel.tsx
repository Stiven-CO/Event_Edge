import { useMemo } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtPct(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "n/a";
  return `${(v * 100).toFixed(decimals)}%`;
}

function fmtVol(v: number): string {
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000)     return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)         return `${(v / 1_000).toFixed(1)}K`;
  return v.toFixed(0);
}

// ── StatCard ──────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-overlay p-3">
      <p className="text-xs text-ink-muted">{label}</p>
      <div className="flex items-baseline gap-2 flex-wrap">
        <p className="font-mono text-sm font-semibold text-ink-primary leading-snug">{value}</p>
        {sub && <p className="font-mono text-sm text-ink-muted leading-snug">{sub}</p>}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function MetricsInfoPanel() {
  const probabilisticResult = useEventEdgeStore((s) => s.probabilisticResult);
  const companyName         = useEventEdgeStore((s) => s.companyName);

  const summary = probabilisticResult?.conditioned_summary ?? null;

  const sortedPeriods = useMemo(
    () =>
      summary?.avg_forward_return
        ? Object.keys(summary.avg_forward_return).map(Number).sort((a, b) => a - b)
        : [],
    [summary],
  );

  const filterRatePct = summary ? `${(summary.filter_rate * 100).toFixed(1)}%` : "n/a";

  return (
    <section className="card p-4 mb-4">
      {/* Header */}
      <div className="mb-4 flex flex-col gap-0.5 border-b border-surface-border pb-3">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold text-ink-primary">Análisis Condicionado</h3>
          {summary && (
            <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-xs text-ink-muted">
              {summary.n_conditioned_events} / {summary.n_total_events} eventos ({filterRatePct})
            </span>
          )}
        </div>
        {companyName && (
          <p className="text-sm font-medium text-accent">{companyName}</p>
        )}
      </div>

      {!summary ? (
        <p className="text-sm text-ink-muted">Calcula el análisis condicionado para ver estas métricas.</p>
      ) : (
        <div className="space-y-5">

          {/* ── Fila 1: frecuencia + retorno P0 ── */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Eventos cond." value={String(summary.n_conditioned_events)} />
            <StatCard label="Por año"        value={summary.frequency_per_year.toFixed(2)} />
            <StatCard label="Por trimestre"  value={summary.frequency_per_quarter.toFixed(2)} />
            <StatCard
              label="Retorno P0 μ±σ"
              value={fmtPct(summary.event_day_return_mean)}
              sub={summary.event_day_return_mean == null ? undefined : `±σ ${fmtPct(summary.event_day_return_std)}`}
            />
          </div>

          {/* ── Fila 2: métricas del día del evento ── */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard
              label="Gap μ±σ"
              value={summary.gap_mean == null ? "n/a" : fmtPct(summary.gap_mean)}
              sub={summary.gap_mean == null ? undefined : `±σ ${fmtPct(summary.gap_std)}`}
            />
            <StatCard
              label="Rango P0 μ±σ"
              value={fmtPct(summary.event_day_range_mean)}
              sub={summary.event_day_range_mean == null ? undefined : `±σ ${fmtPct(summary.event_day_range_std)}`}
            />
            <StatCard
              label="Vol. P0 μ±σ"
              value={summary.event_day_volume_mean == null ? "n/a" : fmtVol(summary.event_day_volume_mean)}
              sub={summary.event_day_volume_mean == null ? undefined : `±σ ${fmtVol(summary.event_day_volume_std ?? 0)}`}
            />
            <StatCard
              label="Vol. CV%"
              value={
                summary.event_day_volume_mean == null || summary.event_day_volume_mean === 0
                  ? "n/a"
                  : `${(((summary.event_day_volume_std ?? 0) / summary.event_day_volume_mean) * 100).toFixed(1)}%`
              }
              sub="dispersión entre eventos"
            />
          </div>

          {/* ── Tabla: rendimiento promedio condicionado ── */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-secondary">
              Rendimiento promedio condicionado
            </p>
            <div className="overflow-hidden rounded-lg border border-surface-border">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Período</th>
                    <th>Referencia de cálculo</th>
                    <th className="text-right">μ (%)</th>
                    <th className="text-right">σ (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPeriods.map((n) => {
                    const fwd = summary.avg_forward_return[n];
                    return (
                      <tr key={n}>
                        <td className="font-mono font-medium text-accent">P{n}</td>
                        <td className="text-xs text-ink-muted">P1-Open → P{n}-Close</td>
                        <td className="text-right font-mono">
                          {fwd ? (fwd.mean * 100).toFixed(2) : "—"}
                        </td>
                        <td className="text-right font-mono text-ink-muted">
                          {fwd ? (fwd.std * 100).toFixed(2) : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      )}
    </section>
  );
}

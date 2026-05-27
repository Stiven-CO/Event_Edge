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
  const metrics     = useEventEdgeStore((s) => s.informativeMetrics);
  const companyName = useEventEdgeStore((s) => s.companyName);
  const events      = useEventEdgeStore((s) => s.events);

  const dateRange = useMemo(() => {
    if (events.length === 0) return null;
    const dates = events.map((e) => e.date).sort();
    return { start: dates[0], end: dates[dates.length - 1] };
  }, [events]);

  const sortedPeriods = useMemo(
    () =>
      metrics?.avg_forward_return
        ? Object.keys(metrics.avg_forward_return).map(Number).sort((a, b) => a - b)
        : [],
    [metrics],
  );

  return (
    <section className="card p-4 mb-4">
      {/* Header */}
      <div className="mb-4 flex flex-col gap-0.5 border-b border-surface-border pb-3">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold text-ink-primary">Métricas Informativas</h3>
          <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-xs text-ink-muted">
            {metrics?.data_source === "mdh" ? "MDH" : "yfinance"}
          </span>
        </div>
        {companyName && (
          <p className="text-sm font-medium text-accent">{companyName}</p>
        )}
        {dateRange && (
          <p className="text-xs text-ink-muted font-mono">
            {dateRange.start} → {dateRange.end}
          </p>
        )}
      </div>

      {!metrics ? (
        <p className="text-sm text-ink-muted">Aún no hay métricas calculadas.</p>
      ) : (
        <div className="space-y-5">

          {/* ── Fila 1: frecuencia + retorno P0 ── */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard label="Eventos"      value={String(metrics.n_total_events)} />
            <StatCard label="Por año"       value={metrics.frequency_per_year.toFixed(2)} />
            <StatCard label="Por trimestre" value={metrics.frequency_per_quarter.toFixed(2)} />
            <StatCard
              label="Retorno P0 μ±σ"
              value={fmtPct(metrics.event_day_return_mean)}
              sub={metrics.event_day_return_mean == null ? undefined : `±σ ${fmtPct(metrics.event_day_return_std)}`}
            />
          </div>

          {/* ── Fila 2: métricas del día del evento ── */}
          <div className="grid grid-cols-4 gap-3">
            <StatCard
              label="Gap μ±σ"
              value={metrics.gap_mean == null ? "n/a" : fmtPct(metrics.gap_mean)}
              sub={metrics.gap_mean == null ? undefined : `±σ ${fmtPct(metrics.gap_std)}`}
            />
            <StatCard
              label="Rango P0 μ±σ"
              value={fmtPct(metrics.event_day_range_mean)}
              sub={metrics.event_day_range_mean == null ? undefined : `±σ ${fmtPct(metrics.event_day_range_std)}`}
            />
            <StatCard
              label="Vol. P0 μ±σ"
              value={metrics.event_day_volume_mean == null ? "n/a" : fmtVol(metrics.event_day_volume_mean)}
              sub={metrics.event_day_volume_mean == null ? undefined : `±σ ${fmtVol(metrics.event_day_volume_std ?? 0)}`}
            />
            <StatCard
              label="Vol. CV%"
              value={
                metrics.event_day_volume_mean == null || metrics.event_day_volume_mean === 0
                  ? "n/a"
                  : `${(((metrics.event_day_volume_std ?? 0) / metrics.event_day_volume_mean) * 100).toFixed(1)}%`
              }
              sub="dispersión entre eventos"
            />
          </div>

          {/* ── Tabla única: rendimiento promedio y desviaciones ── */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-secondary">
              Rendimiento promedio y desviaciones
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
                  {/* Pn: P1-Open → Pn-Close */}
                  {sortedPeriods.map((n) => {
                    const fwd = metrics.avg_forward_return?.[n];
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


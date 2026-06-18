import { useEventEdgeStore } from "@/store/eventEdgeStore";

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtPct(v: number, decimals = 2): string {
  return `${(v * 100).toFixed(decimals)}%`;
}

function fmtN(v: number, decimals = 4): string {
  return v.toFixed(decimals);
}

// ── StatCard ──────────────────────────────────────────────────────────────────
function StatCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        highlight
          ? "border-accent/40 bg-accent/5"
          : "border-surface-border bg-surface-overlay"
      }`}
    >
      <p className="text-xs text-ink-muted">{label}</p>
      <div className="flex items-baseline gap-2 flex-wrap">
        <p className="font-mono text-sm font-semibold text-ink-primary leading-snug">{value}</p>
        {sub && <p className="font-mono text-xs text-ink-muted leading-snug">{sub}</p>}
      </div>
    </div>
  );
}

function hurstLabel(h: number | null): string {
  if (h == null) return "n/a";
  if (h < 0.45) return `${h.toFixed(3)} (reversión)`;
  if (h > 0.55) return `${h.toFixed(3)} (tendencial)`;
  return `${h.toFixed(3)} (random walk)`;
}

// ── Main component ────────────────────────────────────────────────────────────
export function GlobalMetricsPanel() {
  const globalMetrics  = useEventEdgeStore((s) => s.globalMetrics);
  const isLoadingGlobal = useEventEdgeStore((s) => s.isLoadingGlobal);
  const companyName    = useEventEdgeStore((s) => s.companyName);

  if (isLoadingGlobal) {
    return (
      <section className="card p-4 mb-4 animate-pulse">
        <div className="h-5 w-40 rounded bg-surface-overlay" />
        <div className="mt-3 grid grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-surface-overlay" />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="card p-4 mb-4">
      {/* Header */}
      <div className="mb-4 flex flex-col gap-0.5 border-b border-surface-border pb-3">
        <div className="flex items-center justify-between">
          <h3 className="font-display text-lg font-semibold text-ink-primary">Línea Base del Activo</h3>
          {globalMetrics && (
            <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-xs text-ink-muted">
              {globalMetrics.n_observations.toLocaleString()} obs · {globalMetrics.date_start} → {globalMetrics.date_end}
            </span>
          )}
        </div>
        {companyName && (
          <p className="text-sm font-medium text-accent">{companyName}</p>
        )}
      </div>

      {!globalMetrics ? (
        <p className="text-sm text-ink-muted">
          Presiona <span className="font-medium text-ink-secondary">"Calcular Línea Base"</span> para ver las estadísticas globales del activo.
        </p>
      ) : (
        <div className="space-y-5">

          {/* ── A: Estadística descriptiva de retornos ── */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-secondary">
              Distribución de retornos diarios
            </p>
            <div className="grid grid-cols-4 gap-3">
              <StatCard label="Media"     value={fmtPct(globalMetrics.return_mean, 3)} />
              <StatCard label="Mediana"   value={fmtPct(globalMetrics.return_median, 3)} />
              <StatCard label="Desv. std" value={fmtPct(globalMetrics.return_std, 3)} />
              <StatCard label="Asimetría" value={fmtN(globalMetrics.return_skewness, 3)} />
            </div>
            <div className="mt-3 grid grid-cols-4 gap-3">
              <StatCard label="Curtosis (excess)" value={fmtN(globalMetrics.return_kurtosis, 3)} />
              <StatCard label="Mínimo"  value={fmtPct(globalMetrics.return_min, 2)} />
              <StatCard label="Máximo"  value={fmtPct(globalMetrics.return_max, 2)} />
              <StatCard label="Rango"   value={fmtPct(globalMetrics.return_max - globalMetrics.return_min, 2)} />
            </div>
          </div>

          {/* ── B: Volatilidad ── */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-secondary">
              Perfil de volatilidad
            </p>
            <div className="grid grid-cols-3 gap-3">
              <StatCard
                label="Vol. anualizada"
                value={fmtPct(globalMetrics.annualized_vol)}
                highlight
              />
              <StatCard
                label="ATR(14) promedio"
                value={`$${globalMetrics.atr_mean.toFixed(2)}`}
              />
              <StatCard
                label="Puntos rolling vol 30d"
                value={String(globalMetrics.rolling_vol_30d.length)}
                sub="últimas 500 sesiones"
              />
            </div>
          </div>

          {/* ── C: Persistencia ── */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-secondary">
              Persistencia y memoria del precio
            </p>
            <div className="grid grid-cols-4 gap-3">
              <StatCard
                label="Hurst (R/S)"
                value={hurstLabel(globalMetrics.hurst_exponent)}
                highlight={globalMetrics.hurst_exponent != null}
              />
              <StatCard label="Autocorr. lag 1"  value={fmtN(globalMetrics.autocorr_lag1, 4)} />
              <StatCard label="Autocorr. lag 5"  value={fmtN(globalMetrics.autocorr_lag5, 4)} />
              <StatCard label="Autocorr. lag 10" value={fmtN(globalMetrics.autocorr_lag10, 4)} />
            </div>
          </div>

        </div>
      )}
    </section>
  );
}

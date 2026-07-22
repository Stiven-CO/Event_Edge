import { AlertTriangle, Table2 } from "lucide-react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";
import type { DistributionColorBase, DistributionStatsRow } from "@/api/types";

// ---------------------------------------------------------------------------
// Definición de filas (métricas) mostradas en la tabla transpuesta
// ---------------------------------------------------------------------------

interface RowDef {
  key: keyof DistributionStatsRow;
  label: string;
  format: (v: number) => string;
}

const fmtPct = (v: number) => `${(v * 100).toFixed(2)}%`;
const fmtNum = (v: number) => v.toFixed(2);

const ROW_DEFS: RowDef[] = [
  { key: "ret_mean", label: "Retorno medio", format: fmtPct },
  { key: "ret_p25", label: "Retorno P25", format: fmtPct },
  { key: "ret_p75", label: "Retorno P75", format: fmtPct },
  { key: "cvar", label: "CVaR", format: fmtPct },
  { key: "r_cvar", label: "r-CVaR", format: fmtPct },
  { key: "ratio_colas", label: "Ratio colas", format: fmtNum },
  { key: "asimetria", label: "Asimetría", format: fmtNum },
  { key: "curtosis", label: "Curtosis", format: fmtNum },
  { key: "rev_alcista_mean", label: "Reversión alcista (media)", format: fmtPct },
  { key: "rev_alcista_p75", label: "Reversión alcista (P75)", format: fmtPct },
  { key: "rev_bajista_mean", label: "Reversión bajista (media)", format: fmtPct },
  { key: "rev_bajista_p25", label: "Reversión bajista (P25)", format: fmtPct },
];

// Mapea la clasificación del backend a los design tokens de Tailwind del
// proyecto (frontend/tailwind.config.ts) — sin hex arbitrarios.
const CELL_COLOR_STYLES: Record<DistributionColorBase, string> = {
  azul: "bg-status-info/15 text-status-info",
  amarillo: "bg-gold/15 text-gold",
  coral: "bg-coral/15 text-coral",
  blanco: "bg-surface-overlay text-ink-muted",
};

const HEADER_COLOR_STYLES: Record<DistributionColorBase, string> = {
  azul: "bg-status-info/25 text-status-info",
  amarillo: "bg-gold/25 text-gold",
  coral: "bg-coral/25 text-coral",
  blanco: "bg-surface-overlay text-ink-secondary",
};

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function DashboardQuantTable() {
  const result = useEventEdgeStore((s) => s.distributionStatsResult);

  if (!result) return null;

  const { rows, warning, n_events_used, n_events_omitted, intraday_source_error } = result;
  const isInsufficient = warning === "insufficient_events";

  return (
    <div className="mt-4 rounded-xl border border-surface-border bg-surface-raised/60">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Table2 className="h-4 w-4 text-accent" />
          <span className="font-display text-sm font-semibold text-ink-primary">Dashboard Quant</span>
          <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-[10px] text-ink-muted">
            Distribución por offset
          </span>
          {isInsufficient && (
            <span className="flex items-center gap-1 rounded-full bg-status-warning/15 px-2 py-0.5 text-[10px] text-status-warning">
              <AlertTriangle className="h-3 w-3" />
              Datos insuficientes
            </span>
          )}
        </div>
      </div>

      {/* Tabla (transpuesta: columnas = offsets, filas = métricas) */}
      {rows.length > 0 ? (
        <div className="overflow-x-auto px-2 py-3">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-surface-raised px-3 py-2 text-left font-semibold text-ink-secondary">
                  Métrica
                </th>
                {rows.map((row) => (
                  <th
                    key={row.offset}
                    className={`whitespace-nowrap px-3 py-2 text-center font-semibold ${HEADER_COLOR_STYLES[row.color_base]}`}
                  >
                    {row.label}{row.icon ? ` ${row.icon}` : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROW_DEFS.map((rowDef) => (
                <tr key={rowDef.key} className="border-t border-surface-border">
                  <td className="sticky left-0 z-10 whitespace-nowrap bg-surface-raised px-3 py-1.5 text-left text-ink-secondary">
                    {rowDef.label}
                  </td>
                  {rows.map((row) => (
                    <td
                      key={row.offset}
                      className={`px-3 py-1.5 text-center ${CELL_COLOR_STYLES[row.color_base]}`}
                    >
                      {rowDef.format(row[rowDef.key] as number)}
                    </td>
                  ))}
                </tr>
              ))}
              <tr className="border-t-2 border-surface-border">
                <td className="sticky left-0 z-10 whitespace-nowrap bg-surface-raised px-3 py-1.5 text-left italic text-ink-muted">
                  n (eventos)
                </td>
                {rows.map((row) => (
                  <td key={row.offset} className="px-3 py-1.5 text-center italic text-ink-muted">
                    {row.n_obs}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex items-center justify-center py-12 text-xs text-ink-muted">
          Sin datos para mostrar
        </div>
      )}

      {/* Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border px-4 py-2 text-[10px] text-ink-muted">
        <span>
          Eventos usados: <strong className="text-ink-secondary">{n_events_used}</strong>
        </span>
        {n_events_omitted > 0 && (
          <span className="flex items-center gap-1 text-status-warning">
            <AlertTriangle className="h-3 w-3" />
            {n_events_omitted} evento{n_events_omitted > 1 ? "s" : ""} omitido{n_events_omitted > 1 ? "s" : ""}
          </span>
        )}
        {intraday_source_error && (
          <span className="flex max-w-lg items-center gap-1 truncate text-[10px] text-red-400" title={intraday_source_error}>
            <AlertTriangle className="h-3 w-3 shrink-0" />
            MDH: {intraday_source_error}
          </span>
        )}
      </div>
    </div>
  );
}

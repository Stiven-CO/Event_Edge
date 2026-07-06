import { useEffect, useRef, useState, useMemo } from "react";

import type { ConditionedBar, ConditioningParams } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

// ── Column definitions ────────────────────────────────────────────────────────

type ColDef = {
  key: keyof ConditionedBar;
  label: string;
  cluster: string;
  format: (v: unknown) => string;
  colorize?: (v: unknown) => "positive" | "negative" | null;
};

function fmtPct(v: unknown, decimals = 2): string {
  if (v == null) return "–";
  const n = v as number;
  const pct = n * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(decimals)}%`;
}

// Para columnas que el backend ya calcula en escala porcentual (×100 aplicado
// en feature_builder.py) — a diferencia de gap_pct/eps_surprise_pct, que se
// guardan como fracción decimal y sí requieren el ×100 de fmtPct.
function fmtPctRaw(v: unknown, decimals = 2): string {
  if (v == null) return "–";
  const n = v as number;
  return `${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%`;
}

function fmtNum(v: unknown, decimals = 4): string {
  if (v == null) return "–";
  return (v as number).toFixed(decimals);
}

function fmtStr(v: unknown): string {
  if (v == null) return "–";
  return String(v);
}

function fmtBool(v: unknown): string {
  if (v == null) return "–";
  return v ? "Sí" : "No";
}

const ALL_COLUMNS: ColDef[] = [
  // ── Identidad
  { key: "date",              label: "Fecha",            cluster: "Identidad",     format: (v) => v ? new Date(v as string).toLocaleDateString(undefined, { timeZone: "UTC" }) : "–" },
  { key: "event_type",        label: "Tipo Evento",      cluster: "Identidad",     format: fmtStr },
  { key: "symbol",            label: "Símbolo",          cluster: "Identidad",     format: fmtStr },
  // ── Base cruda (OHLCV + Earnings)
  { key: "open",              label: "Open",             cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "high",              label: "High",             cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "low",               label: "Low",              cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "close",             label: "Close",            cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "volume",            label: "Volumen",          cluster: "Base",          format: (v) => v == null ? "–" : Number(v).toLocaleString() },
  { key: "eps_actual",        label: "EPS Actual",       cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "eps_estimate",      label: "EPS Estimado",     cluster: "Base",          format: (v) => fmtNum(v, 2) },
  { key: "surprise_pct",      label: "Sorpresa % (raw)", cluster: "Base",          format: (v) => v == null ? "–" : `${(v as number).toFixed(2)}%` },
  { key: "revenue_actual",    label: "Revenue Actual",   cluster: "Base",          format: (v) => v == null ? "–" : Number(v).toLocaleString() },
  { key: "revenue_estimate",  label: "Revenue Estimado", cluster: "Base",          format: (v) => v == null ? "–" : Number(v).toLocaleString() },
  // ── F - Posicionamiento
  { key: "gap_pct",           label: "Gap%",             cluster: "F · Posición",  format: (v) => fmtPct(v),
    colorize: (v) => v == null ? null : (v as number) >= 0 ? "positive" : "negative" },
  // ── A - Tendencia
  { key: "ema5_vs_ema20_ratio",  label: "EMA5/EMA20",   cluster: "A · Tendencia", format: (v) => fmtNum(v, 4) },
  { key: "price_vs_ema50_pct",   label: "Precio/EMA50%",cluster: "A · Tendencia", format: (v) => fmtPctRaw(v),
    colorize: (v) => v == null ? null : (v as number) >= 0 ? "positive" : "negative" },
  { key: "trend_direction",   label: "Tendencia",        cluster: "A · Tendencia", format: fmtStr },
  // ── B - Momentum
  { key: "return_5d",         label: "Ret. 5d",          cluster: "B · Momentum",  format: (v) => fmtPctRaw(v),
    colorize: (v) => v == null ? null : (v as number) >= 0 ? "positive" : "negative" },
  { key: "return_20d",        label: "Ret. 20d",         cluster: "B · Momentum",  format: (v) => fmtPctRaw(v),
    colorize: (v) => v == null ? null : (v as number) >= 0 ? "positive" : "negative" },
  { key: "rsi14",             label: "RSI(14)",          cluster: "B · Momentum",  format: (v) => fmtNum(v, 1) },
  // ── C - Sobreextensión
  { key: "bb_position",       label: "Pos. BB",          cluster: "C · Sobreext.", format: fmtStr },
  { key: "bb_width_pct",      label: "Ancho BB%",        cluster: "C · Sobreext.", format: (v) => fmtPctRaw(v) },
  { key: "rsi14_zone",        label: "Zona RSI",         cluster: "C · Sobreext.", format: fmtStr },
  // ── D - Volatilidad
  { key: "hist_vol_10d",      label: "Vol.Hist 10d",     cluster: "D · Volatilidad", format: (v) => fmtPctRaw(v) },
  { key: "vol_ratio_10_30",   label: "Ratio Vol 10/30",  cluster: "D · Volatilidad", format: (v) => fmtNum(v, 2) },
  { key: "atr_pct",           label: "ATR%",             cluster: "D · Volatilidad", format: (v) => fmtPctRaw(v) },
  { key: "vol_regime",        label: "Régimen Vol.",     cluster: "D · Volatilidad", format: fmtStr },
  // ── E - Fundamental
  { key: "take_earnings",     label: "Día Earnings",     cluster: "E · Fundamental", format: fmtBool },
  { key: "eps_surprise_pct",  label: "EPS Sorpresa%",    cluster: "E · Fundamental", format: (v) => fmtPct(v),
    colorize: (v) => v == null ? null : (v as number) >= 0 ? "positive" : "negative" },
  { key: "guidance",          label: "Guidance",         cluster: "E · Fundamental", format: fmtStr },
  // ── G - Estacionalidad
  { key: "day_of_week",       label: "Día semana",       cluster: "G · Estacionalidad", format: fmtStr },
  { key: "month",             label: "Mes",              cluster: "G · Estacionalidad", format: fmtStr },
  { key: "quarter",           label: "Trimestre",        cluster: "G · Estacionalidad", format: fmtStr },
  { key: "earnings_season",   label: "Temporada",        cluster: "G · Estacionalidad", format: fmtStr },
];

const DEFAULT_VISIBLE = new Set<string>([
  "date", "gap_pct", "trend_direction", "rsi14", "day_of_week", "return_5d", "vol_regime",
]);

// ── Conditioning summary helper ───────────────────────────────────────────────

function formatConditioningSummary(c: ConditioningParams): string | null {
  const parts: string[] = [];

  if (c.trend_directions?.length) parts.push(`Tendencia: ${c.trend_directions.join(", ")}`);
  if (c.ema5_vs_ema20_ratio_min != null || c.ema5_vs_ema20_ratio_max != null)
    parts.push(`EMA5/20: ${c.ema5_vs_ema20_ratio_min ?? "–"} a ${c.ema5_vs_ema20_ratio_max ?? "–"}`);
  if (c.price_vs_ema50_pct_min != null || c.price_vs_ema50_pct_max != null)
    parts.push(`Precio vs EMA50: ${c.price_vs_ema50_pct_min ?? "–"} a ${c.price_vs_ema50_pct_max ?? "–"}%`);
  if (c.rsi14_min != null || c.rsi14_max != null)
    parts.push(`RSI(14): ${c.rsi14_min ?? "–"}–${c.rsi14_max ?? "–"}`);
  if (c.return_5d_min != null || c.return_5d_max != null)
    parts.push(`Ret.5d: ${c.return_5d_min ?? "–"} a ${c.return_5d_max ?? "–"}%`);
  if (c.return_20d_min != null || c.return_20d_max != null)
    parts.push(`Ret.20d: ${c.return_20d_min ?? "–"} a ${c.return_20d_max ?? "–"}%`);
  if (c.bb_positions?.length) parts.push(`BB pos: ${c.bb_positions.join(", ")}`);
  if (c.rsi14_zones?.length) parts.push(`RSI zona: ${c.rsi14_zones.join(", ")}`);
  if (c.vol_regimes?.length) parts.push(`Vol: ${c.vol_regimes.join(", ")}`);
  if (c.atr_pct_min != null || c.atr_pct_max != null)
    parts.push(`ATR%: ${c.atr_pct_min ?? "–"}–${c.atr_pct_max ?? "–"}`);
  if (c.guidance_directions?.length) parts.push(`Guidance: ${c.guidance_directions.join(", ")}`);
  if (c.eps_surprise_pct_min != null || c.eps_surprise_pct_max != null)
    parts.push(`EPS sorpresa: ${c.eps_surprise_pct_min ?? "–"} a ${c.eps_surprise_pct_max ?? "–"}%`);
  if (c.gap_direction && c.gap_direction !== "any") parts.push(`Gap: ${c.gap_direction}`);
  if (c.gap_pct_min != null || c.gap_pct_max != null)
    parts.push(`Gap%: ${c.gap_pct_min ?? "–"} a ${c.gap_pct_max ?? "–"}`);
  if (c.days_of_week?.length) parts.push(`Días: ${c.days_of_week.join(", ")}`);
  if (c.months?.length) parts.push(`Meses: ${c.months.join(", ")}`);
  if (c.quarters?.length) parts.push(`Trimestres: ${c.quarters.join(", ")}`);
  if (c.earnings_seasons?.length) parts.push(`Temporada: ${c.earnings_seasons.join(", ")}`);

  return parts.length > 0 ? parts.join(" · ") : null;
}

// ── Column selector dropdown ──────────────────────────────────────────────────

function ColumnSelector({
  visibleCols,
  onChange,
}: {
  visibleCols: Set<string>;
  onChange: (cols: Set<string>) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const clusters = useMemo(() => {
    const map = new Map<string, ColDef[]>();
    for (const col of ALL_COLUMNS) {
      if (!map.has(col.cluster)) map.set(col.cluster, []);
      map.get(col.cluster)!.push(col);
    }
    return map;
  }, []);

  function toggle(key: string) {
    const next = new Set(visibleCols);
    if (next.has(key)) {
      if (next.size > 1) next.delete(key);
    } else {
      next.add(key);
    }
    onChange(next);
  }

  function toggleCluster(clusterCols: ColDef[], allVisible: boolean) {
    const next = new Set(visibleCols);
    if (allVisible) {
      for (const col of clusterCols) {
        if (next.size > 1) next.delete(col.key);
      }
    } else {
      for (const col of clusterCols) next.add(col.key);
    }
    onChange(next);
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className="button-ghost flex items-center gap-1 text-xs"
        onClick={() => setOpen((v) => !v)}
        title="Seleccionar columnas visibles"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="size-3.5" viewBox="0 0 20 20" fill="currentColor">
          <path d="M5 4a1 1 0 0 0 0 2h10a1 1 0 1 0 0-2H5zM3 9a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1zm2 4a1 1 0 1 0 0 2h10a1 1 0 1 0 0-2H5z" />
        </svg>
        Columnas ({visibleCols.size})
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 max-h-96 w-60 overflow-y-auto rounded-xl border border-surface-border bg-surface-raised shadow-lg">
          {Array.from(clusters.entries()).map(([cluster, cols]) => {
            const allVisible = cols.every((c) => visibleCols.has(c.key));
            return (
              <div key={cluster} className="border-b border-surface-border/50 last:border-0">
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs font-semibold text-ink-secondary hover:bg-surface-overlay/40"
                  onClick={() => toggleCluster(cols, allVisible)}
                >
                  <span className={`size-3 rounded-sm border ${allVisible ? "border-accent bg-accent" : "border-surface-border bg-transparent"}`} />
                  {cluster}
                </button>
                {cols.map((col) => (
                  <label
                    key={col.key}
                    className="flex cursor-pointer items-center gap-2 px-4 py-1 text-xs text-ink-primary hover:bg-surface-overlay/40"
                  >
                    <input
                      type="checkbox"
                      className="accent-accent"
                      checked={visibleCols.has(col.key)}
                      onChange={() => toggle(col.key)}
                    />
                    {col.label}
                  </label>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Date search helper ────────────────────────────────────────────────────────

function findNearestDate(rows: ConditionedBar[], target: string): string | null {
  if (!rows.length || !target) return null;
  const targetMs = new Date(target).getTime();
  if (Number.isNaN(targetMs)) return null;

  let best = rows[0].date;
  let bestDelta = Infinity;
  for (const r of rows) {
    const delta = Math.abs(new Date(r.date).getTime() - targetMs);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = r.date;
    }
  }
  return best;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function EarningsTable() {
  const conditioningCount = useEventEdgeStore((s) => s.conditioningCount);
  const conditioning      = useEventEdgeStore((s) => s.conditioning);
  const [desc, setDesc]   = useState(true);
  const [visibleCols, setVisibleCols] = useState<Set<string>>(DEFAULT_VISIBLE);
  const [searchDate, setSearchDate]     = useState("");
  const [highlightDate, setHighlightDate] = useState<string | null>(null);
  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  const rows: ConditionedBar[] = useMemo(() => {
    const source = conditioningCount?.rows ?? [];
    return [...source].sort((a, b) => {
      const delta = new Date(a.date).getTime() - new Date(b.date).getTime();
      return desc ? -delta : delta;
    });
  }, [conditioningCount, desc]);

  function handleSearch() {
    const nearest = findNearestDate(rows, searchDate);
    setHighlightDate(nearest);
    if (nearest) {
      rowRefs.current.get(nearest)?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  const summary = formatConditioningSummary(conditioning);
  const activeCols = ALL_COLUMNS.filter((c) => visibleCols.has(c.key));
  const colSpan = activeCols.length;

  return (
    <section className="panel mt-4 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-lg font-semibold">Events</h3>
          <p className="mt-0.5 truncate text-xs text-ink-muted">
            {summary ?? "Sin filtros activos — vista de preview del dataset completo"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <input
            type="date"
            className="input h-7 text-xs"
            value={searchDate}
            onChange={(e) => setSearchDate(e.target.value)}
            title="Buscar por fecha (usa la barra hábil más cercana)"
          />
          <button type="button" className="button-ghost text-xs" onClick={handleSearch}>
            Buscar
          </button>
          <ColumnSelector visibleCols={visibleCols} onChange={setVisibleCols} />
          <button type="button" className="button-ghost text-xs" onClick={() => setDesc((v) => !v)}>
            Fecha {desc ? "↓" : "↑"}
          </button>
        </div>
      </div>

      <div className="max-h-[360px] overflow-auto rounded-xl border border-surface-border bg-surface-raised">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-surface-overlay text-ink-secondary">
            <tr>
              {activeCols.map((col) => (
                <th key={col.key} className="whitespace-nowrap px-3 py-2 text-left text-xs font-medium">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.date}
                ref={(el) => {
                  if (el) rowRefs.current.set(r.date, el);
                  else rowRefs.current.delete(r.date);
                }}
                className={`border-t border-surface-border/60 text-ink-primary hover:bg-surface-overlay/40 ${
                  r.date === highlightDate ? "bg-accent/20" : ""
                }`}
              >
                {activeCols.map((col) => {
                  const raw = r[col.key];
                  const text = col.format(raw);
                  const color = col.colorize ? col.colorize(raw) : null;
                  return (
                    <td key={col.key} className="whitespace-nowrap px-3 py-1.5">
                      {color ? (
                        <span className={color === "positive" ? "text-status-success" : "text-status-error"}>
                          {text}
                        </span>
                      ) : (
                        <span className="capitalize">{text}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}

            {conditioningCount === null && (
              <tr>
                <td colSpan={colSpan} className="px-3 py-6 text-center text-ink-muted">
                  Pulsa "Aplicar Condicionamiento" (sin filtros) para ver el dataset completo, o define filtros para condicionar.
                </td>
              </tr>
            )}
            {conditioningCount !== null && rows.length === 0 && (
              <tr>
                <td colSpan={colSpan} className="px-3 py-6 text-center text-ink-muted">
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

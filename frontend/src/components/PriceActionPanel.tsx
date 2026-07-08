import { AlertTriangle, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  ComposedChart,
  Customized,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useEventEdgeStore } from "@/store/eventEdgeStore";
import type { PriceActionSeries } from "@/api/types";

// ---------------------------------------------------------------------------
// Tipos internos
// ---------------------------------------------------------------------------

type FilterKey = "all" | "win" | "loss";

interface ColorConfig {
  stroke: string;
  fill: string;
  label: string;
}

const COLOR_MAP: Record<FilterKey, ColorConfig> = {
  all:  { stroke: "#00d2c8", fill: "rgba(0,210,200,0.15)",  label: "Todos" },
  win:  { stroke: "#22c55e", fill: "rgba(34,197,94,0.15)",  label: "Win"   },
  loss: { stroke: "#ef4444", fill: "rgba(239,68,68,0.15)",  label: "Loss"  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildChartData(
  series: PriceActionSeries,
  xLabels: string[],
  showBands: boolean,
) {
  return series.points.map((pt, i) => {
    const entry: Record<string, number | string> = {
      x: xLabels[i] ?? String(pt.x),
      y: pt.y,
    };
    if (showBands && series.band_upper && series.band_lower) {
      entry.band_upper = series.band_upper[i]?.y ?? pt.y;
      entry.band_lower = series.band_lower[i]?.y ?? pt.y;
    }

    return entry;
  });
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function PriceActionPanel() {
  const result                = useEventEdgeStore((s) => s.priceActionResult);
  const priceActionMode       = useEventEdgeStore((s) => s.priceActionMode);
  const priceActionEventTF    = useEventEdgeStore((s) => s.priceActionEventTF);
  const setPriceActionEventTF = useEventEdgeStore((s) => s.setPriceActionEventTF);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [showBands, setShowBands] = useState(false);

  if (!result) return null;

  const { series_all, series_win, series_loss, x_labels, n_events_all, n_events_win, n_events_loss, n_events_omitted, warning, n_periods, intraday_source_error } = result;

  const seriesMap: Record<FilterKey, PriceActionSeries> = {
    all:  series_all,
    win:  series_win,
    loss: series_loss,
  };

  const activeSeries = seriesMap[filter];
  const config = COLOR_MAP[filter];
  const hasBands = !!(activeSeries.band_upper && activeSeries.band_lower);
  const isInsufficient = warning === "insufficient_events";
  const tickAngle = x_labels.length > 10 ? -45 : 0;

  const chartData = useMemo(
    () => buildChartData(activeSeries, x_labels, showBands && hasBands),
    [activeSeries, x_labels, showBands, hasBands],
  );

  const yDomain = useMemo<[number, number]>(() => {
    if (chartData.length === 0) return [0, 100];

    const values: number[] = [];
    for (const row of chartData) {
      const y = Number(row.y);
      if (Number.isFinite(y)) values.push(y);

      if (showBands && hasBands) {
        const lower = Number(row.band_lower);
        const upper = Number(row.band_upper);
        if (Number.isFinite(lower)) values.push(lower);
        if (Number.isFinite(upper)) values.push(upper);
      }
    }

    if (values.length === 0) return [0, 100];

    let min = Math.min(...values);
    let max = Math.max(...values);

    if (min === max) {
      const delta = Math.max(Math.abs(min) * 0.01, 0.5);
      return [min - delta, max + delta];
    }

    const pad = Math.max((max - min) * 0.08, 0.15);
    min -= pad;
    max += pad;
    return [min, max];
  }, [chartData, showBands, hasBands]);

  const nForFilter: Record<FilterKey, number> = {
    all:  n_events_all,
    win:  n_events_win,
    loss: n_events_loss,
  };

  const modeLabel = priceActionMode === "in_event"
    ? `Inside Event (${priceActionEventTF})`
    : `Holding P1–P${n_periods}`;

  return (
    <div className="mt-4 rounded-xl border border-surface-border bg-surface-raised/60">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-border px-4 py-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-accent" />
          <span className="font-display text-sm font-semibold text-ink-primary">Price Action</span>
          <span className="rounded-full bg-surface-overlay px-2 py-0.5 text-[10px] text-ink-muted">{modeLabel}</span>
          {isInsufficient && (
            <span className="flex items-center gap-1 rounded-full bg-status-warning/15 px-2 py-0.5 text-[10px] text-status-warning">
              <AlertTriangle className="h-3 w-3" />
              Datos insuficientes
            </span>
          )}
          {intraday_source_error && (
            <span className="flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] text-red-400" title={intraday_source_error}>
              <AlertTriangle className="h-3 w-3" />
              Error MDH intraday
            </span>
          )}
        </div>

        {/* Controles */}
        <div className="flex items-center gap-3">
          {/* TF selector — solo en modo in_event */}
          {priceActionMode === "in_event" && (
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-ink-muted">TF evento:</span>
              <select
                className="rounded border border-surface-border bg-surface-overlay px-2 py-0.5 text-xs text-ink-primary"
                value={priceActionEventTF}
                onChange={(e) => setPriceActionEventTF(e.target.value)}
              >
                {["30m", "1d"].map((tf) => (
                  <option key={tf} value={tf}>{tf}</option>
                ))}
              </select>
            </div>
          )}

          {/* Toggle All / Win / Loss */}
          <div className="flex rounded-lg border border-surface-border overflow-hidden text-xs">
            {(["all", "win", "loss"] as FilterKey[]).map((key) => {
              const n = nForFilter[key];
              const disabled = n < 5;
              return (
                <button
                  key={key}
                  type="button"
                  disabled={disabled}
                  onClick={() => setFilter(key)}
                  className={`px-3 py-1 transition disabled:opacity-40 disabled:cursor-not-allowed ${
                    filter === key
                      ? "bg-accent/20 text-accent font-semibold"
                      : "text-ink-secondary hover:bg-surface-overlay hover:text-ink-primary"
                  }`}
                >
                  {COLOR_MAP[key].label} ({n})
                </button>
              );
            })}
          </div>

          {/* Toggle banda */}
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-ink-secondary select-none">
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-accent"
              checked={showBands}
              onChange={(e) => setShowBands(e.target.checked)}
              disabled={!hasBands}
            />
            Banda ±1σ
          </label>
        </div>
      </div>

      {/* Gráfico */}
      {chartData.length > 0 ? (
        <div className="px-2 py-3">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: tickAngle !== 0 ? 20 : 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis
                dataKey="x"
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                angle={tickAngle}
                textAnchor={tickAngle !== 0 ? "end" : "middle"}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#9ca3af" }}
                tickFormatter={(v: number) => v.toFixed(2)}
                domain={yDomain}
              />
              <ReferenceLine y={100} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" label={{ value: "100", fill: "#9ca3af", fontSize: 9 }} />
              <Tooltip
                contentStyle={{ background: "#1e2432", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "#e5e7eb" }}
                formatter={(value: number) => [`${value.toFixed(2)}`, "Precio"]}
              />

              {/* Banda ±1σ — polígono SVG usando escalas del eje para máxima fiabilidad */}
              {showBands && hasBands && (
                <Customized
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  component={(cProps: any) => {
                    const xAxisMap = cProps.xAxisMap as Record<string, { scale: (v: string) => number; bandwidth?: () => number }>;
                    const yAxisMap = cProps.yAxisMap as Record<string, { scale: (v: number) => number }>;
                    const rows = cProps.data as typeof chartData;
                    if (!xAxisMap || !yAxisMap || !rows?.length) return null;

                    const xScale = Object.values(xAxisMap)[0]?.scale;
                    const yScale = Object.values(yAxisMap)[0]?.scale;
                    if (!xScale || !yScale) return null;

                    const bw = (Object.values(xAxisMap)[0]?.bandwidth?.() ?? 0) / 2;

                    type Pt = [number, number];
                    const upper: Pt[] = [];
                    const lower: Pt[] = [];
                    for (const row of rows) {
                      if (row.band_upper === undefined || row.band_lower === undefined) continue;
                      const px = xScale(row.x as string) + bw;
                      upper.push([px, yScale(row.band_upper as number)]);
                      lower.push([px, yScale(row.band_lower as number)]);
                    }
                    if (upper.length < 2) return null;

                    const toPath = (pts: Pt[]) =>
                      pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

                    const fillD = toPath(upper) + " " + toPath([...lower].reverse()) + " Z";

                    return (
                      <g>
                        <path d={fillD} fill={config.fill} fillOpacity={1} stroke="none" />
                        <path d={toPath(upper)} fill="none" stroke={config.stroke} strokeOpacity={0.45} strokeWidth={1} />
                        <path d={toPath(lower)} fill="none" stroke={config.stroke} strokeOpacity={0.45} strokeWidth={1} />
                      </g>
                    );
                  }}
                />
              )}

              {/* Línea promedio */}
              <Line
                type="monotone"
                dataKey="y"
                stroke={config.stroke}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: config.stroke }}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex items-center justify-center py-12 text-xs text-ink-muted">
          Sin datos para el grupo seleccionado
        </div>
      )}

      {/* Footer */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-surface-border px-4 py-2 text-[10px] text-ink-muted">
        <span>
          Eventos — Todos: <strong className="text-ink-secondary">{n_events_all}</strong> &nbsp;|&nbsp;
          Win: <strong className="text-green-400">{n_events_win}</strong> &nbsp;|&nbsp;
          Loss: <strong className="text-red-400">{n_events_loss}</strong>
        </span>
        {n_events_omitted > 0 && (
          <span className="flex items-center gap-1 text-status-warning">
            <AlertTriangle className="h-3 w-3" />
            {n_events_omitted} evento{n_events_omitted > 1 ? "s" : ""} omitido{n_events_omitted > 1 ? "s" : ""} (sin datos 30min)
          </span>
        )}
        {intraday_source_error && (
          <span className="flex items-center gap-1 text-red-400 text-[10px] max-w-lg truncate" title={intraday_source_error}>
            <AlertTriangle className="h-3 w-3 shrink-0" />
            MDH: {intraday_source_error}
          </span>
        )}
      </div>
    </div>
  );
}

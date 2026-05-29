import { AlertTriangle, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
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
      const bandUpper = series.band_upper[i]?.y ?? pt.y;
      const bandLower = series.band_lower[i]?.y ?? pt.y;
      entry.band_upper = bandUpper;
      entry.band_lower = bandLower;
      entry.band_range = Math.max(0, bandUpper - bandLower);
    }
    return entry;
  });
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export function PriceActionPanel() {
  const result = useEventEdgeStore((s) => s.priceActionResult);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [showBands, setShowBands] = useState(false);

  if (!result) return null;

  const { series_all, series_win, series_loss, x_labels, n_events_all, n_events_win, n_events_loss, n_events_omitted, warning, anchor_mode, n_periods } = result;

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

  const nForFilter: Record<FilterKey, number> = {
    all:  n_events_all,
    win:  n_events_win,
    loss: n_events_loss,
  };

  const modeLabel = anchor_mode === "intraday_30min"
    ? "Intradía 30min (P0)"
    : `Diario P1–P${n_periods}`;

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
        </div>

        {/* Controles */}
        <div className="flex items-center gap-3">
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
                domain={["auto", "auto"]}
              />
              <ReferenceLine y={100} stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" label={{ value: "100", fill: "#9ca3af", fontSize: 9 }} />
              <Tooltip
                contentStyle={{ background: "#1e2432", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: "#e5e7eb" }}
                formatter={(value: number) => [`${value.toFixed(2)}`, "Precio"]}
              />

              {/* Banda ±1σ: base en límite inferior + rango apilado */}
              {showBands && hasBands && (
                <Area
                  type="monotone"
                  dataKey="band_lower"
                  stackId="sigma"
                  stroke="none"
                  fill="transparent"
                  fillOpacity={0}
                  legendType="none"
                  isAnimationActive={false}
                />
              )}
              {showBands && hasBands && (
                <Area
                  type="monotone"
                  dataKey="band_range"
                  stackId="sigma"
                  stroke={"none"}
                  fill={config.fill}
                  fillOpacity={1}
                  legendType="none"
                  isAnimationActive={false}
                />
              )}

              {showBands && hasBands && (
                <Line
                  type="monotone"
                  dataKey="band_upper"
                  stroke={config.stroke}
                  strokeOpacity={0.55}
                  strokeWidth={1}
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                />
              )}

              {showBands && hasBands && (
                <Line
                  type="monotone"
                  dataKey="band_lower"
                  stroke={config.stroke}
                  strokeOpacity={0.55}
                  strokeWidth={1}
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
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
      </div>
    </div>
  );
}

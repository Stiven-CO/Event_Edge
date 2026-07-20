import { ChevronDown, ChevronUp, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

type FamilyKey = "close_return" | "gap_fill";

// ── Descripciones de cada característica de estudio ──────────────────────────
function getCloseReturnInfo(mode: "holding" | "in_event") {
  if (mode === "in_event") {
    return {
      label: "Close Return",
      formula: "(close_P0 − open_P0) / open_P0",
      description:
        "Retorno acumulado desde el open del día del evento (P0) hasta el cierre del evento. Pide el retorno en el día del evento.",
    };
  }
  return {
    label: "Close Return",
    formula: "(close_Pn − close_P0) / close_P0",
    description:
      "Retorno acumulado desde el cierre del día del evento (P0) hasta el cierre de la sesión Pn. Excluye el gap de apertura y retorno del evento en sección regular, mide el movimiento post-evento.",
  };
}

function getGapFillInfo(mode: "holding" | "in_event") {
  if (mode === "in_event") {
    return {
      label: "Gap Fill",
      formula: 'P(precio toca prev_close dentro de P0 "El evento")',
      description:
        "Probabilidad de que el precio regrese a cerrar el gap del evento dentro del periodo del evento P0. El gap se considera cerrado cuando el precio (high o low) toca o supera el cierre previo (prev_close).",
    };
  }
  return {
    label: "Gap Fill",
    formula: "P(precio toca prev_close dentro de Pn sesiones)",
    description:
      "Probabilidad de que el precio regrese a cerrar el gap del evento dentro de N sesiones. El gap se considera cerrado cuando el precio toca o supera el cierre previo (prev_close).",
  };
}

// ── InfoBox colapsable ────────────────────────────────────────────────────────
function FamilyInfoBox({ family, mode }: { family: FamilyKey; mode: "holding" | "in_event" }) {
  const [open, setOpen] = useState(false);
  const info = family === "close_return" ? getCloseReturnInfo(mode) : getGapFillInfo(mode);

  return (
    <div className="rounded-lg border border-surface-border bg-surface-overlay/50">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-ink-secondary hover:text-ink-primary transition"
        onClick={() => setOpen((v) => !v)}
      >
        <Info className="h-3.5 w-3.5 text-accent/70 shrink-0" />
        <span className="flex-1 text-left">¿Cómo se calcula {info.label}?</span>
        {open ? (
          <ChevronUp className="h-3.5 w-3.5 text-ink-muted" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-ink-muted" />
        )}
      </button>
      {open && (
        <div className="border-t border-surface-border px-3 pb-3 pt-2 animate-fade-in space-y-1.5">
          <p className="font-mono text-xs text-accent">{info.formula}</p>
          <p className="text-xs text-ink-secondary leading-relaxed">{info.description}</p>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function ProbabilityPanel() {
  const result          = useEventEdgeStore((s) => s.probabilisticResult);
  const priceActionMode = useEventEdgeStore((s) => s.priceActionMode);
  const [selected, setSelected] = useState<FamilyKey>("close_return");

  const family = useMemo(
    () => result?.families.find((f) => f.family === selected),
    [result, selected],
  );

  const data = useMemo(() => {
    if (!family) return [];
    const mapped = family.scenarios.map((s, i) => {
      // gap_fill tiene 2 bins (No/Sí): el backend genera "< +50%" y "> +50%"
      // porque el threshold es 0.5 sobre datos binarios 0/1 — se mapean aquí.
      let label = s.label;
      if (selected === "gap_fill" && family.scenarios.length === 2) {
        label = i === 0 ? "No" : "Sí";
      }
      return {
        label,
        probability: s.probability * 100,
        ci:          `${(s.ci_lower * 100).toFixed(1)}%–${(s.ci_upper * 100).toFixed(1)}%`,
      };
    });
    // El backend ordena los bins ascendente (más negativo primero, contrato de
    // BaseEventModel). Recharts dibuja el primer elemento del array arriba, así
    // que para close_return se invierte para mostrar positivos arriba / negativos abajo.
    return selected === "close_return" ? mapped.reverse() : mapped;
  }, [family, selected]);

  return (
    <section className="card flex flex-col p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between border-b border-surface-border pb-3">
        <h3 className="font-display text-lg font-semibold text-ink-primary">Probabilidades</h3>
        {family?.warning && (
          <span className="badge-warning">{family.warning}</span>
        )}
      </div>

      {/* Selector de familia */}
      <div className="mb-3 flex flex-wrap gap-2">
        {(["close_return", "gap_fill"] as const).map((f) => (
          <button
            key={f}
            type="button"
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
              selected === f
                ? "border-accent bg-accent/15 text-accent"
                : "border-surface-border text-ink-muted hover:border-accent/40 hover:text-ink-secondary"
            }`}
            onClick={() => setSelected(f)}
          >
            {f === "close_return" ? getCloseReturnInfo(priceActionMode).label : getGapFillInfo(priceActionMode).label}
          </button>
        ))}
      </div>

      {/* Info box colapsable */}
      <div className="mb-4">
        <FamilyInfoBox family={selected} mode={priceActionMode} />
      </div>

      {/* Contenido */}
      {!family ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-ink-muted">Calcula métricas para visualizar los escenarios.</p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col">
          {/* Gráfico */}
          <div className="rounded-lg border border-surface-border bg-surface-overlay/40 p-2">
            <ResponsiveContainer width="100%" height={420}>
              <BarChart data={data} layout="vertical" margin={{ left: 10, right: 60, top: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e2d4f" />
                <XAxis
                  type="number"
                  tickFormatter={(v) => `${v.toFixed(0)}%`}
                  tick={{ fill: "#8ea3c3", fontSize: 11 }}
                  axisLine={{ stroke: "#1e2d4f" }}
                  tickLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={100}
                  tick={{ fill: "#8ea3c3", fontSize: 11 }}
                  axisLine={{ stroke: "#1e2d4f" }}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#141c35",
                    border: "1px solid #1e2d4f",
                    borderRadius: "8px",
                    color: "#e8edf5",
                    fontSize: 12,
                  }}
                  formatter={(v: number) => [`${v.toFixed(2)}%`, "Probabilidad"]}
                />
                <Bar dataKey="probability" fill="#00d2c8" radius={[0, 6, 6, 0]} opacity={0.85}>
                  <LabelList
                    dataKey="ci"
                    position="right"
                    style={{ fontSize: 10, fill: "#4a6080" }}
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Footer */}
          <p className="mt-2 text-xs text-ink-muted font-mono">
            {family.n_samples_used} / {family.n_total_events} eventos usados
          </p>
        </div>
      )}
    </section>
  );
}

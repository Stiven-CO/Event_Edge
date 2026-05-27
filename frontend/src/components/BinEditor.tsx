import { useMemo, useState } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

const defaultBins = [-0.05, -0.01, 0.01, 0.05];

function validateBins(values: number[]): string | null {
  if (values.length < 2) {
    return "Se requieren al menos 2 bins";
  }
  if (values.some((v) => Number.isNaN(v) || v < -1 || v > 1)) {
    return "Todos los bins deben estar entre -1.0 y 1.0";
  }
  for (let i = 1; i < values.length; i += 1) {
    if (!(values[i] > values[i - 1])) {
      return "Los bins deben estar ordenados de menor a mayor";
    }
  }
  return null;
}

export function BinEditor() {
  const bins = useEventEdgeStore((s) => s.bins);
  const setBins = useEventEdgeStore((s) => s.setBins);
  const [draft, setDraft] = useState(bins.join(", "));

  const parsed = useMemo(() => {
    return draft
      .split(",")
      .map((v) => Number(v.trim()))
      .filter((v) => !Number.isNaN(v));
  }, [draft]);

  const error = validateBins(parsed);

  return (
    <section className="panel p-4">
      <h3 className="mb-3 font-display text-lg font-semibold">Bins</h3>
      <p className="mb-2 text-xs text-slate">Valores decimales, ejemplo: -0.05, -0.01, 0.01, 0.05</p>
      <textarea
        className="input min-h-[90px]"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : (
        <p className="mt-1 text-xs text-slate">
          Vista: {parsed.map((v) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`).join(", ")}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="button-primary"
          disabled={Boolean(error)}
          onClick={() => {
            if (!error) {
              setBins(parsed);
            }
          }}
        >
          Aplicar bins
        </button>
        <button
          type="button"
          className="button-ghost"
          onClick={() => {
            setDraft(defaultBins.join(", "));
            setBins(defaultBins);
          }}
        >
          Reset
        </button>
      </div>
    </section>
  );
}

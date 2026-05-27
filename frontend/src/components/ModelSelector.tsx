import type { ModelType } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

const modelDescriptions: Record<ModelType, string> = {
  frequentist: "Frecuencias observadas con intervalo Wilson.",
  bootstrap: "Re-muestreo robusto con intervalos por percentiles.",
  kde: "Densidad suavizada para colas continuas.",
  bayesian: "Posterior Beta con prior de Laplace.",
};

export function ModelSelector() {
  const model = useEventEdgeStore((s) => s.model);
  const setModel = useEventEdgeStore((s) => s.setModel);

  return (
    <section className="panel p-4">
      <h3 className="mb-3 font-display text-lg font-semibold">Modelo</h3>
      <select
        className="input"
        value={model}
        onChange={(e) => setModel(e.target.value as ModelType)}
      >
        <option value="frequentist">Frequentist</option>
        <option value="bootstrap">Bootstrap</option>
        <option value="kde">KDE</option>
        <option value="bayesian">Bayesian</option>
      </select>
      <p className="mt-2 text-xs text-slate">{modelDescriptions[model]}</p>
    </section>
  );
}

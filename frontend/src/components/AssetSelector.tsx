import { useMemo, useState } from "react";

import { useEvents } from "@/hooks/useEvents";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

const symbolRe = /^[A-Z]{1,5}$/;

export function AssetSelector() {
  const symbol = useEventEdgeStore((s) => s.symbol);
  const companyName = useEventEdgeStore((s) => s.companyName);
  const setSymbol = useEventEdgeStore((s) => s.setSymbol);
  const { run, isLoadingEvents } = useEvents();
  const [draft, setDraft] = useState(symbol);

  const error = useMemo(() => {
    if (draft.length === 0) {
      return "Ingresa un símbolo";
    }
    return symbolRe.test(draft) ? null : "Usa solo 1-5 letras mayúsculas";
  }, [draft]);

  return (
    <section className="panel p-4">
      <h3 className="mb-3 font-display text-lg font-semibold">Activo</h3>
      <label className="label">Símbolo</label>
      <input
        className="input mt-1"
        value={draft}
        onChange={(e) => setDraft(e.target.value.toUpperCase())}
        placeholder="AAPL"
        maxLength={5}
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      {companyName && (
        <p className="mt-1 truncate text-sm font-medium text-ink" title={companyName}>
          {companyName}
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          className="button-primary"
          disabled={Boolean(error) || isLoadingEvents}
          onClick={async () => {
            if (error) {
              return;
            }
            setSymbol(draft);
            await run();
          }}
        >
          {isLoadingEvents ? "Buscando..." : "Buscar"}
        </button>
        <span className="text-xs text-slate">Activo: {symbol}</span>
      </div>
    </section>
  );
}

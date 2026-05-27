import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function PeriodSelector() {
  const nPeriods = useEventEdgeStore((s) => s.nPeriods);
  const setNPeriods = useEventEdgeStore((s) => s.setNPeriods);

  return (
    <section className="panel p-4">
      <h3 className="mb-3 font-display text-lg font-semibold">Horizonte</h3>
      <label className="label">N sesiones de trading</label>
      <div className="mt-2 flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={60}
          value={nPeriods}
          onChange={(e) => setNPeriods(Number(e.target.value))}
          className="w-full accent-sea"
        />
        <input
          type="number"
          min={0}
          max={60}
          value={nPeriods}
          onChange={(e) => setNPeriods(Math.max(0, Math.min(60, Number(e.target.value) || 0)))}
          className="input w-20"
        />
      </div>
    </section>
  );
}

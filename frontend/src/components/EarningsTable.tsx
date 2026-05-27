import { useMemo, useState } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function EarningsTable() {
  const events = useEventEdgeStore((s) => s.events);
  const eventType = useEventEdgeStore((s) => s.eventType);
  const [desc, setDesc] = useState(true);

  const rows = useMemo(() => {
    const filtered = events.filter((e) => e.event_type === eventType);
    return [...filtered].sort((a, b) => {
      const delta = new Date(a.date).getTime() - new Date(b.date).getTime();
      return desc ? -delta : delta;
    });
  }, [events, eventType, desc]);

  const isEarnings = eventType === "earnings";
  const title = isEarnings ? "Earnings Events" : "Gap Events";
  const colSpan = isEarnings ? 6 : 3;

  return (
    <section className="panel mt-4 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold">{title}</h3>
        <button type="button" className="button-ghost" onClick={() => setDesc((v) => !v)}>
          Fecha {desc ? "desc" : "asc"}
        </button>
      </div>
      <div className="max-h-[360px] overflow-auto rounded-xl border border-surface-border bg-surface-raised">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-overlay text-ink-secondary">
            {isEarnings ? (
              <tr>
                <th className="px-3 py-2 text-left">Fecha</th>
                <th className="px-3 py-2 text-left">Gap%</th>
                <th className="px-3 py-2 text-left">EPS Actual</th>
                <th className="px-3 py-2 text-left">EPS Estimado</th>
                <th className="px-3 py-2 text-left">Sorpresa%</th>
                <th className="px-3 py-2 text-left">Guidance</th>
              </tr>
            ) : (
              <tr>
                <th className="px-3 py-2 text-left">Fecha</th>
                <th className="px-3 py-2 text-left">Gap%</th>
                <th className="px-3 py-2 text-left">Dirección</th>
              </tr>
            )}
          </thead>
          <tbody>
            {rows.map((r) =>
              isEarnings ? (
                <tr key={r.date} className="border-t border-surface-border/60 text-ink-primary hover:bg-surface-overlay/40">
                  <td className="px-3 py-2">{new Date(r.date).toLocaleDateString()}</td>
                  <td className="px-3 py-2">{r.gap_pct == null ? "-" : `${(r.gap_pct * 100).toFixed(2)}%`}</td>
                  <td className="px-3 py-2">{r.eps_actual ?? "-"}</td>
                  <td className="px-3 py-2">{r.eps_estimate ?? "-"}</td>
                  <td className="px-3 py-2">{r.eps_surprise_pct == null ? "-" : `${(r.eps_surprise_pct * 100).toFixed(2)}%`}</td>
                  <td className="px-3 py-2">{r.guidance}</td>
                </tr>
              ) : (
                <tr key={r.date} className="border-t border-surface-border/60 text-ink-primary hover:bg-surface-overlay/40">
                  <td className="px-3 py-2">{new Date(r.date).toLocaleDateString()}</td>
                  <td className="px-3 py-2">
                    <span className={r.gap_pct != null && r.gap_pct >= 0 ? "text-status-success" : "text-status-error"}>
                      {r.gap_pct == null ? "-" : `${(r.gap_pct * 100).toFixed(2)}%`}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {r.gap_pct == null ? "-" : r.gap_pct >= 0 ? "▲ Alcista" : "▼ Bajista"}
                  </td>
                </tr>
              )
            )}
            {rows.length === 0 && (
              <tr>
                <td colSpan={colSpan} className="px-3 py-6 text-center text-ink-muted">
                  Sin eventos cargados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

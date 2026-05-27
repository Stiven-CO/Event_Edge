import type { EventType } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

const tabs: Array<{ key: EventType; label: string }> = [
  { key: "earnings", label: "Earnings" },
  { key: "gap", label: "Gap" },
];

export function EventTypeTabs() {
  const eventType = useEventEdgeStore((s) => s.eventType);
  const setEventType = useEventEdgeStore((s) => s.setEventType);
  const clearResults = useEventEdgeStore((s) => s.clearResults);

  return (
    <section className="panel p-4">
      <h3 className="mb-3 font-display text-lg font-semibold">Tipo de Evento</h3>
      <div className="grid grid-cols-2 gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={`rounded-xl border px-3 py-2 text-sm font-semibold transition ${
              eventType === tab.key
                ? "border-sea bg-sea text-white"
                : "border-border bg-white text-ink hover:bg-paper"
            }`}
            onClick={() => {
              setEventType(tab.key);
              clearResults();
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </section>
  );
}

import type { BrokerStatus } from "@/api/types";
import type { DataSource } from "@/store/eventEdgeStore";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

interface BrokerStatusBadgeProps {
  source: DataSource;
  selected?: boolean;
  onSelect?: () => void;
}

const sourceLabel: Record<DataSource, string> = {
  mt5: "MT5",
  tws: "TWS",
  yfinance: "YFinance",
};

function findStatus(statuses: BrokerStatus[], source: DataSource) {
  return statuses.find((s) => s.source === source);
}

export function BrokerStatusBadge({ source, selected = false, onSelect }: BrokerStatusBadgeProps) {
  const statuses = useEventEdgeStore((s) => s.brokerStatuses);

  const status = findStatus(statuses, source);
  const alive = Boolean(status?.alive);
  const mode = status?.mode ?? "unknown";

  return (
    <button
      type="button"
      title={`Modo: ${mode}${onSelect ? " — clic para seleccionar" : ""}`}
      onClick={onSelect}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold transition ${
        selected
          ? "border-accent bg-accent/10 text-accent ring-1 ring-accent"
          : "border-surface-border bg-surface-overlay text-ink-primary hover:border-accent/50"
      } ${onSelect ? "cursor-pointer" : "cursor-default"}`}
    >
      <span
        className={`h-2.5 w-2.5 rounded-full ${alive ? "bg-status-success" : "bg-status-error"}`}
      />
      <span>{sourceLabel[source]}</span>
      {!alive && <span className="text-ink-muted">(off)</span>}
    </button>
  );
}

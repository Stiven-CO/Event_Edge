import type { BrokerStatus } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

const SOURCE_LABEL: Record<string, string> = {
  mdh:      "MDH",
  mt5:      "MT5",
  tws:      "TWS",
  yfinance: "YFinance",
};

function findStatus(statuses: BrokerStatus[], source: string) {
  return statuses.find((s) => s.source === source);
}

interface BrokerStatusBadgeProps {
  source: string;
}

export function BrokerStatusBadge({ source }: BrokerStatusBadgeProps) {
  const statuses = useEventEdgeStore((s) => s.brokerStatuses);

  const status = findStatus(statuses, source);
  const alive  = Boolean(status?.alive);
  const mode   = status?.mode ?? "unknown";
  const label  = SOURCE_LABEL[source] ?? source.toUpperCase();

  return (
    <span
      title={`${label} · modo: ${mode}`}
      className="inline-flex items-center gap-1.5 rounded-full border border-surface-border bg-surface-overlay px-3 py-1 text-xs font-semibold text-ink-primary"
    >
      <span
        className={`h-2 w-2 rounded-full ${alive ? "bg-status-success" : "bg-status-error"}`}
      />
      {label}
      {!alive && <span className="font-normal text-ink-muted">(off)</span>}
    </span>
  );
}

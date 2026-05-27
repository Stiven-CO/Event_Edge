import type { BrokerStatus } from "@/api/types";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

interface BrokerStatusBadgeProps {
  source: "mdh" | "mt5" | "tws" | "yfinance";
}

const sourceLabel: Record<BrokerStatusBadgeProps["source"], string> = {
  mdh: "MDH",
  mt5: "MT5",
  tws: "TWS",
  yfinance: "YFinance",
};

function findStatus(statuses: BrokerStatus[], source: BrokerStatusBadgeProps["source"]) {
  return statuses.find((s) => s.source === source);
}

export function BrokerStatusBadge({ source }: BrokerStatusBadgeProps) {
  const statuses = useEventEdgeStore((s) => s.brokerStatuses);

  const status = findStatus(statuses, source);
  const alive = Boolean(status?.alive);
  const mode = status?.mode ?? "unknown";

  return (
    <div
      title={`Modo: ${mode}`}
      className="inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface-overlay px-3 py-1 text-xs font-semibold text-ink-primary"
    >
      <span
        className={`h-2.5 w-2.5 rounded-full ${alive ? "bg-status-success" : "bg-status-error"}`}
      />
      <span>{sourceLabel[source]}</span>
      {!alive && <span className="text-ink-muted">(off)</span>}
    </div>
  );
}

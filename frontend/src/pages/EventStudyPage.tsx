import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";

import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { EarningsTable } from "@/components/EarningsTable";
import { MetricsInfoPanel } from "@/components/MetricsInfoPanel";
import { ProbabilityPanel } from "@/components/ProbabilityPanel";
import { SidebarMenu } from "@/components/SidebarMenu";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function EventStudyPage() {
  const fetchBrokerStatus = useEventEdgeStore((s) => s.fetchBrokerStatus);
  const error = useEventEdgeStore((s) => s.error);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    void fetchBrokerStatus();
    const id = window.setInterval(() => void fetchBrokerStatus(), 30_000);
    return () => window.clearInterval(id);
  }, [fetchBrokerStatus]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface-base">
      {/* ── Header ── */}
      <header className="shrink-0 border-b border-surface-border bg-surface-raised/80 px-5 py-3 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-xl font-bold text-ink-primary">Event Edge</h1>
            <p className="text-xs text-ink-muted">Estudio probabilístico de eventos earnings y gaps</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <BrokerStatusBadge source="mdh" />
            <BrokerStatusBadge source="yfinance" />
            <BrokerStatusBadge source="mt5" />
            <BrokerStatusBadge source="tws" />
          </div>
        </div>
      </header>

      {error && (
        <div className="shrink-0 border-b border-status-error/30 bg-status-error/10 px-5 py-2 text-sm text-status-error">
          {error}
        </div>
      )}

      {/* ── Layout: sidebar fijo | centro scroll | probabilidades dominante ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Sidebar colapsable */}
        <aside
          className={`shrink-0 border-r border-surface-border bg-surface-raised/60 overflow-y-auto transition-all duration-200 ${
            sidebarOpen ? "w-72" : "w-10"
          }`}
        >
          {/* Toggle icon — siempre visible en la cabecera del sidebar */}
          <div className={`flex items-center border-b border-surface-border px-2 py-2 ${
            sidebarOpen ? "justify-end" : "justify-center"
          }`}>
            <button
              type="button"
              title={sidebarOpen ? "Ocultar menú" : "Mostrar menú"}
              className="rounded-md p-1 text-ink-muted transition hover:bg-surface-overlay hover:text-accent"
              onClick={() => setSidebarOpen((v) => !v)}
            >
              {sidebarOpen
                ? <PanelLeftClose className="h-4 w-4" />
                : <PanelLeftOpen  className="h-4 w-4" />}
            </button>
          </div>

          {/* Contenido — solo visible cuando está abierto */}
          {sidebarOpen && <SidebarMenu />}
        </aside>

        {/* Centro: métricas informativas + tabla de eventos */}
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4">
          <MetricsInfoPanel />
          <EarningsTable />
        </main>

        {/* Probabilidades: sección dominante, más ancha que el centro */}
        <section className="w-[55%] max-w-4xl shrink-0 border-l border-surface-border overflow-y-auto p-4">
          <ProbabilityPanel />
        </section>

      </div>
    </div>
  );
}

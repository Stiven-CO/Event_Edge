import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";

import { BrokerStatusBadge } from "@/components/BrokerStatusBadge";
import { DashboardQuantTable } from "@/components/DashboardQuantTable";
import { EarningsTable } from "@/components/EarningsTable";
import { GlobalMetricsPanel } from "@/components/GlobalMetricsPanel";
import { MetricsInfoPanel } from "@/components/MetricsInfoPanel";
import { PriceActionPanel } from "@/components/PriceActionPanel";
import { ProbabilityPanel } from "@/components/ProbabilityPanel";
import { SidebarMenu } from "@/components/SidebarMenu";
import { useDistributionStats } from "@/hooks/useDistributionStats";
import { usePriceAction } from "@/hooks/usePriceAction";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function EventStudyPage() {
  const fetchBrokerStatus     = useEventEdgeStore((s) => s.fetchBrokerStatus);
  const probabilisticResult   = useEventEdgeStore((s) => s.probabilisticResult);
  const priceActionResult     = useEventEdgeStore((s) => s.priceActionResult);
  const distributionStatsResult = useEventEdgeStore((s) => s.distributionStatsResult);
  const priceActionMode       = useEventEdgeStore((s) => s.priceActionMode);
  const priceActionEventTF    = useEventEdgeStore((s) => s.priceActionEventTF);
  const setPriceActionEventTF = useEventEdgeStore((s) => s.setPriceActionEventTF);
  const saveEdge               = useEventEdgeStore((s) => s.saveEdge);
  const isSavingEdge           = useEventEdgeStore((s) => s.isSavingEdge);
  const error                 = useEventEdgeStore((s) => s.error);
  const infoMessage           = useEventEdgeStore((s) => s.infoMessage);
  const { run: runPriceAction, isLoadingPriceAction } = usePriceAction();
  const { run: runDistributionStats, isLoadingDistributionStats } = useDistributionStats();
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
            <p className="text-xs text-ink-muted">
              Estudio probabilístico de eventos earnings y gaps
            </p>
          </div>

          {/* Estado de conectividad (solo lectura, sin selector de fuente) */}
          <div className="flex items-center gap-2">
            <BrokerStatusBadge source="mdh" />
          </div>
        </div>
      </header>

      {/* ── Banners de estado ── */}
      {error && (
        <div className="shrink-0 border-b border-status-error/30 bg-status-error/10 px-5 py-2 text-sm text-status-error">
          {error}
        </div>
      )}
      {infoMessage && !error && (
        <div className="shrink-0 border-b border-amber-400/30 bg-amber-50 px-5 py-2 text-sm text-amber-800">
          {infoMessage}
        </div>
      )}

      {/* ── Layout ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Sidebar colapsable */}
        <aside
          className={`shrink-0 border-r border-surface-border bg-surface-raised/60 overflow-y-auto transition-all duration-200 ${
            sidebarOpen ? "w-72" : "w-10"
          }`}
        >
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
          {sidebarOpen && <SidebarMenu />}
        </aside>

        {/* Centro: línea base global + tabla de eventos */}
        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-4">
          <GlobalMetricsPanel />
          <EarningsTable />
        </main>

        {/* Derecha: probabilidades + métricas condicionadas */}
        <section className="w-[55%] max-w-4xl shrink-0 border-l border-surface-border overflow-y-auto p-4">
          <ProbabilityPanel />
          <MetricsInfoPanel />

          {probabilisticResult && (
            <div className="mt-3 flex flex-col gap-2">
              {priceActionMode === "in_event" && (
                <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-overlay/20 px-3 py-2 text-xs">
                  <span className="text-ink-muted">Timeframe del evento:</span>
                  <select
                    className="rounded border border-surface-border bg-surface-overlay px-2 py-0.5 text-xs text-ink-primary"
                    value={priceActionEventTF}
                    onChange={(e) => setPriceActionEventTF(e.target.value)}
                  >
                    {["30m", "1d"].map((tf) => (
                      <option key={tf} value={tf}>{tf}</option>
                    ))}
                  </select>
                  <span className="ml-auto text-[10px] text-ink-muted/60">
                    30m · intradía del evento &nbsp;·&nbsp; 1d · sesión completa
                  </span>
                </div>
              )}
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-surface-border bg-surface-overlay/40 py-2 text-sm text-ink-secondary transition hover:border-accent/40 hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoadingPriceAction}
                onClick={() => void runPriceAction()}
              >
                {isLoadingPriceAction ? "Cargando Price Action…" : "📈 Ver Price Action"}
              </button>
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-surface-border bg-surface-overlay/40 py-2 text-sm text-ink-secondary transition hover:border-accent/40 hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoadingDistributionStats}
                onClick={() => void runDistributionStats()}
              >
                {isLoadingDistributionStats ? "Cargando Dashboard Quant…" : "🧮 Ver Dashboard Quant"}
              </button>
              <button
                type="button"
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-surface-border bg-surface-overlay/40 py-2 text-sm text-ink-secondary transition hover:border-accent/40 hover:bg-accent/10 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isSavingEdge}
                onClick={() => void saveEdge()}
              >
                {isSavingEdge ? "Guardando…" : "💾 Guardar análisis"}
              </button>
            </div>
          )}

          {priceActionResult && <PriceActionPanel />}
          {distributionStatsResult && <DashboardQuantTable />}
        </section>

      </div>
    </div>
  );
}

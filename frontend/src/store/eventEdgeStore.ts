import { create } from "zustand";

import { endpoints } from "@/api/endpoints";
import type {
  AnalysisRequest,
  BrokerStatus,
  ConditioningParams,
  EventRecord,
  EventType,
  InformativeMetrics,
  ModelType,
  PriceActionResult,
  ProbabilisticResult,
} from "@/api/types";

export type DataSource = "yfinance" | "mt5" | "tws";

interface EventEdgeState {
  symbol: string;
  companyName: string;
  eventType: EventType;
  model: ModelType;
  nPeriods: number;
  gapThreshold: number;
  bins: number[];
  periods: number[];
  conditioning: ConditioningParams;
  dateStart: string;
  dateEnd: string;
  dataSource: DataSource;

  events: EventRecord[];
  informativeMetrics: InformativeMetrics | null;
  probabilisticResult: ProbabilisticResult | null;
  priceActionResult: PriceActionResult | null;
  brokerStatuses: BrokerStatus[];

  isLoadingEvents: boolean;
  isLoadingMetrics: boolean;
  isLoadingBrokerStatus: boolean;
  isLoadingPriceAction: boolean;
  error: string | null;
  infoMessage: string | null;

  setSymbol: (s: string) => void;
  setEventType: (t: EventType) => void;
  setModel: (m: ModelType) => void;
  setNPeriods: (n: number) => void;
  setGapThreshold: (t: number) => void;
  setBins: (b: number[]) => void;
  setPeriods: (p: number[]) => void;
  setConditioning: (c: ConditioningParams) => void;
  resetConditioning: () => void;
  clearResults: () => void;
  setDateStart: (d: string) => void;
  setDateEnd: (d: string) => void;
  setDataSource: (s: DataSource) => void;

  fetchBrokerStatus: () => Promise<void>;
  fetchEvents: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
  fetchPriceAction: () => Promise<void>;
}

const defaultConditioning: ConditioningParams = {
  gap_direction: "any",
};

const sourceLabel: Record<DataSource, string> = {
  yfinance: "YFinance",
  mt5: "MT5",
  tws: "TWS",
};

function fallbackMessage(
  selectedSource: DataSource,
  usedSource: string | null | undefined,
  detail?: string | null,
): string | null {
  if ((selectedSource === "mt5" || selectedSource === "tws") && usedSource === "yfinance") {
    return detail ?? `No fue posible usar ${sourceLabel[selectedSource]}. Se usó YFinance como respaldo.`;
  }
  return null;
}

function unavailableMessage(selectedSource: DataSource, statuses: BrokerStatus[]): string | null {
  if (selectedSource !== "mt5" && selectedSource !== "tws") {
    return null;
  }

  const selected = statuses.find((s) => s.source === selectedSource);
  if (selected && !selected.alive) {
    return `${sourceLabel[selectedSource]} no está disponible en este momento. Se intentará usar YFinance como respaldo.`;
  }
  return null;
}

export const useEventEdgeStore = create<EventEdgeState>((set, get) => ({
  symbol: "AAPL",
  companyName: "",
  eventType: "earnings",
  model: "bootstrap",
  nPeriods: 5,
  gapThreshold: 1.0,
  bins: [-0.05, -0.01, 0.01, 0.05],
  periods: [1, 3, 5, 10],
  conditioning: defaultConditioning,
  dateStart: "",
  dateEnd: "",
  dataSource: "yfinance",

  events: [],
  informativeMetrics: null,
  probabilisticResult: null,
  priceActionResult: null,
  brokerStatuses: [],

  isLoadingEvents: false,
  isLoadingMetrics: false,
  isLoadingBrokerStatus: false,
  isLoadingPriceAction: false,
  error: null,
  infoMessage: null,

  setSymbol: (symbol) => set({ symbol, error: null, infoMessage: null }),
  setEventType: (eventType) => set({ eventType, informativeMetrics: null, probabilisticResult: null, error: null, infoMessage: null }),
  setModel: (model) => set({ model }),
  setNPeriods: (nPeriods) => set({ nPeriods: Math.max(0, Math.min(60, Math.trunc(nPeriods))) }),
  setGapThreshold: (gapThreshold) => set({ gapThreshold: Math.max(0.1, Math.min(20, Number.isFinite(gapThreshold) ? gapThreshold : 1.0)) }),
  setBins: (bins) => set({ bins }),
  setPeriods: (periods) => set({ periods }),
  setConditioning: (conditioning) => set({ conditioning }),
  resetConditioning: () => set({ conditioning: defaultConditioning }),
  clearResults: () => set({ events: [], informativeMetrics: null, probabilisticResult: null, priceActionResult: null, error: null }),
  setDateStart: (dateStart) => set({ dateStart }),
  setDateEnd: (dateEnd) => set({ dateEnd }),
  setDataSource: (dataSource) => set({ dataSource, infoMessage: null }),

  fetchBrokerStatus: async () => {
    set({ isLoadingBrokerStatus: true });
    try {
      const brokerStatuses = await endpoints.getBrokerStatus();
      set({ brokerStatuses, isLoadingBrokerStatus: false });
    } catch {
      set({ isLoadingBrokerStatus: false });
    }
  },

  fetchEvents: async () => {
    const { symbol, eventType, dateStart, dateEnd, gapThreshold } = get();
    set({ isLoadingEvents: true, error: null, infoMessage: null });
    try {
      const { dataSource, brokerStatuses } = get();
      const [events, assetInfo] = await Promise.allSettled([
        endpoints.detectEvents({
          symbol,
          source: dataSource,
          asset_class: "equity",
          event_type: eventType,
          gap_threshold_pct: gapThreshold,
          ...(dateStart ? { date_range_start: dateStart } : {}),
          ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
        }),
        endpoints.getAssetInfo(symbol),
      ]);
      const resolvedEvents = events.status === "fulfilled" ? events.value : [];
      const companyName =
        assetInfo.status === "fulfilled" ? (assetInfo.value.short_name || "") : "";
      set({
        events: resolvedEvents,
        companyName,
        isLoadingEvents: false,
        informativeMetrics: null,
        probabilisticResult: null,
        infoMessage: unavailableMessage(dataSource, brokerStatuses),
      });
    } catch (error) {
      set({
        isLoadingEvents: false,
        error: error instanceof Error ? error.message : "No se pudo cargar eventos",
      });
    }
  },

  fetchMetrics: async () => {
    const { symbol, eventType, model, nPeriods, gapThreshold, bins, conditioning, periods, dateStart, dateEnd, dataSource } = get();
    set({ isLoadingMetrics: true, error: null, infoMessage: null });

    try {
      const informativePromise = endpoints.getInformativeMetrics({
        symbol,
        source: dataSource,
        asset_class: "equity",
        event_type: eventType,
        gap_threshold_pct: gapThreshold,
        periods,
      });

      const probabilisticBody: AnalysisRequest = {
        symbol,
        source: dataSource,
        asset_class: "equity",
        event_type: eventType,
        model,
        n_periods: nPeriods,
        bins,
        gap_threshold_pct: gapThreshold,
        conditioning,
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
      };
      const probabilisticPromise = endpoints.getProbabilisticMetrics(probabilisticBody);

      const [informativeMetrics, probabilisticResult] = await Promise.all([
        informativePromise,
        probabilisticPromise,
      ]);

      set({
        informativeMetrics,
        probabilisticResult,
        isLoadingMetrics: false,
        infoMessage: fallbackMessage(dataSource, informativeMetrics.data_source, informativeMetrics.data_source_detail),
      });
    } catch (error) {
      set({
        isLoadingMetrics: false,
        error: error instanceof Error ? error.message : "No se pudo calcular métricas",
      });
    }
  },

  fetchPriceAction: async () => {
    const { symbol, eventType, nPeriods, conditioning, gapThreshold, dateStart, dateEnd, dataSource, brokerStatuses } = get();
    set({ isLoadingPriceAction: true, infoMessage: null });
    try {
      const result = await endpoints.getPriceAction({
        symbol,
        source: dataSource,
        asset_class: "equity",
        event_type: eventType,
        gap_threshold_pct: gapThreshold,
        n_periods: nPeriods,
        include_bands: true,
        conditioning,
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd ? { date_range_end: dateEnd } : {}),
      });
      set({
        priceActionResult: result,
        isLoadingPriceAction: false,
        infoMessage: unavailableMessage(dataSource, brokerStatuses),
      });
    } catch (error) {
      set({
        isLoadingPriceAction: false,
        error: error instanceof Error ? error.message : "No se pudo cargar Price Action",
      });
    }
  },
}));

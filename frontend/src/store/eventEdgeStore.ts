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
  ProbabilisticResult,
} from "@/api/types";

interface EventEdgeState {
  symbol: string;
  companyName: string;
  eventType: EventType;
  model: ModelType;
  nPeriods: number;
  bins: number[];
  periods: number[];
  conditioning: ConditioningParams;
  dateStart: string;
  dateEnd: string;

  events: EventRecord[];
  informativeMetrics: InformativeMetrics | null;
  probabilisticResult: ProbabilisticResult | null;
  brokerStatuses: BrokerStatus[];

  isLoadingEvents: boolean;
  isLoadingMetrics: boolean;
  isLoadingBrokerStatus: boolean;
  error: string | null;

  setSymbol: (s: string) => void;
  setEventType: (t: EventType) => void;
  setModel: (m: ModelType) => void;
  setNPeriods: (n: number) => void;
  setBins: (b: number[]) => void;
  setPeriods: (p: number[]) => void;
  setConditioning: (c: ConditioningParams) => void;
  resetConditioning: () => void;
  clearResults: () => void;
  setDateStart: (d: string) => void;
  setDateEnd: (d: string) => void;

  fetchBrokerStatus: () => Promise<void>;
  fetchEvents: () => Promise<void>;
  fetchMetrics: () => Promise<void>;
}

const defaultConditioning: ConditioningParams = {
  gap_direction: "any",
};

export const useEventEdgeStore = create<EventEdgeState>((set, get) => ({
  symbol: "AAPL",
  companyName: "",
  eventType: "earnings",
  model: "bootstrap",
  nPeriods: 5,
  bins: [-0.05, -0.01, 0.01, 0.05],
  periods: [1, 3, 5, 10],
  conditioning: defaultConditioning,
  dateStart: "",
  dateEnd: "",

  events: [],
  informativeMetrics: null,
  probabilisticResult: null,
  brokerStatuses: [],

  isLoadingEvents: false,
  isLoadingMetrics: false,
  isLoadingBrokerStatus: false,
  error: null,

  setSymbol: (symbol) => set({ symbol, error: null }),
  setEventType: (eventType) => set({ eventType, informativeMetrics: null, probabilisticResult: null, error: null }),
  setModel: (model) => set({ model }),
  setNPeriods: (nPeriods) => set({ nPeriods: Math.max(0, Math.min(60, Math.trunc(nPeriods))) }),
  setBins: (bins) => set({ bins }),
  setPeriods: (periods) => set({ periods }),
  setConditioning: (conditioning) => set({ conditioning }),
  resetConditioning: () => set({ conditioning: defaultConditioning }),
  clearResults: () => set({ events: [], informativeMetrics: null, probabilisticResult: null, error: null }),
  setDateStart: (dateStart) => set({ dateStart }),
  setDateEnd: (dateEnd) => set({ dateEnd }),

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
    const { symbol, eventType } = get();
    set({ isLoadingEvents: true, error: null });
    try {
      const [events, assetInfo] = await Promise.allSettled([
        endpoints.detectEvents({
          symbol,
          source: "yfinance",
          asset_class: "equity",
          event_type: eventType,
        }),
        endpoints.getAssetInfo(symbol),
      ]);
      const resolvedEvents = events.status === "fulfilled" ? events.value : [];
      const companyName =
        assetInfo.status === "fulfilled" ? (assetInfo.value.short_name || "") : "";
      set({ events: resolvedEvents, companyName, isLoadingEvents: false, informativeMetrics: null, probabilisticResult: null });
    } catch (error) {
      set({
        isLoadingEvents: false,
        error: error instanceof Error ? error.message : "No se pudo cargar eventos",
      });
    }
  },

  fetchMetrics: async () => {
    const { symbol, eventType, model, nPeriods, bins, conditioning, periods } = get();
    set({ isLoadingMetrics: true, error: null });

    try {
      const informativePromise = endpoints.getInformativeMetrics({
        symbol,
        source: "yfinance",
        asset_class: "equity",
        event_type: eventType,
        periods,
      });

      const probabilisticBody: AnalysisRequest = {
        symbol,
        source: "yfinance",
        asset_class: "equity",
        event_type: eventType,
        model,
        n_periods: nPeriods,
        bins,
        gap_threshold_pct: 1.0,
        conditioning,
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
      });
    } catch (error) {
      set({
        isLoadingMetrics: false,
        error: error instanceof Error ? error.message : "No se pudo calcular métricas",
      });
    }
  },
}));

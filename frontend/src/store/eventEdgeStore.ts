import { create } from "zustand";

import { endpoints } from "@/api/endpoints";
import type {
  AnalysisRequest,
  BrokerStatus,
  ConditioningCountResult,
  ConditioningParams,
  EventRecord,
  EventType,
  GlobalInformativeMetrics,
  ModelType,
  PriceActionResult,
  ProbabilisticResult,
  SaveEdgeRequest,
} from "@/api/types";

// ---------------------------------------------------------------------------
// Lake parameter types
// ---------------------------------------------------------------------------

export type TypeData  = "ohlcv" | "fundamental" | "macro";
export type TypeSaved = "complete_historical" | "specific_event";

export const ASSET_CLASS_OPTIONS: Record<TypeData, string[]> = {
  ohlcv:       ["equity", "forex", "crypto", "index", "commodities"],
  fundamental: ["earnings"],
  macro:       ["economics"],
};

export const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"] as const;

export const SOURCE_OPTIONS = ["yfinance", "mt5", "alpha_vantage"] as const;
export type DataSource = typeof SOURCE_OPTIONS[number];

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _normalizeConditioning(conditioning: ConditioningParams): ConditioningParams {
  return {
    ...conditioning,
    eps_surprise_pct_min:
      conditioning.eps_surprise_pct_min != null
        ? conditioning.eps_surprise_pct_min / 100
        : undefined,
    eps_surprise_pct_max:
      conditioning.eps_surprise_pct_max != null
        ? conditioning.eps_surprise_pct_max / 100
        : undefined,
  };
}

// ---------------------------------------------------------------------------
// Store interface
// ---------------------------------------------------------------------------

interface EventEdgeState {
  // ── Query params ──────────────────────────────────────────────────────────
  symbol: string;
  companyName: string;
  source: DataSource;
  mt5Account: string;
  ohlcvSource: DataSource;
  typeData: TypeData;
  assetClass: string;
  timeframe: string;
  typeSaved: TypeSaved;
  // ── Analysis params ───────────────────────────────────────────────────────
  eventType: EventType;
  model: ModelType;
  nPeriods: number;
  // ── Price Action params ───────────────────────────────────────────────────
  priceActionMode: "holding" | "in_event";
  priceActionEventTF: string;
  gapThreshold: number;
  includeEarningsDays: boolean | null;
  bins: number[];
  conditioning: ConditioningParams;
  dateStart: string;
  dateEnd: string;
  // ── Results ───────────────────────────────────────────────────────────────
  events: EventRecord[];
  globalMetrics: GlobalInformativeMetrics | null;
  probabilisticResult: ProbabilisticResult | null;
  priceActionResult: PriceActionResult | null;
  brokerStatuses: BrokerStatus[];
  conditioningCount: ConditioningCountResult | null;
  // ── Loading / error ───────────────────────────────────────────────────────
  isLoadingEvents: boolean;
  isLoadingGlobal: boolean;
  isLoadingMetrics: boolean;
  isLoadingBrokerStatus: boolean;
  isLoadingPriceAction: boolean;
  isLoadingConditioningCount: boolean;
  isSavingEdge: boolean;
  lastSavedRunId: string | null;
  error: string | null;
  infoMessage: string | null;
  // ── Setters ───────────────────────────────────────────────────────────────
  setSymbol: (s: string) => void;
  setSource: (s: DataSource) => void;
  setMt5Account: (k: string) => void;
  setOhlcvSource: (s: DataSource) => void;
  setTypeData: (t: TypeData) => void;
  setAssetClass: (c: string) => void;
  setTimeframe: (f: string) => void;
  setTypeSaved: (s: TypeSaved) => void;
  setEventType: (t: EventType) => void;
  setModel: (m: ModelType) => void;
  setNPeriods: (n: number) => void;
  setPriceActionMode: (m: "holding" | "in_event") => void;
  setPriceActionEventTF: (tf: string) => void;
  setGapThreshold: (t: number) => void;
  setIncludeEarningsDays: (v: boolean | null) => void;
  setBins: (b: number[]) => void;
  setConditioning: (c: ConditioningParams) => void;
  resetConditioning: () => void;
  clearResults: () => void;
  setDateStart: (d: string) => void;
  setDateEnd: (d: string) => void;
  // ── Actions ───────────────────────────────────────────────────────────────
  fetchBrokerStatus: () => Promise<void>;
  fetchEvents: () => Promise<void>;
  fetchGlobalMetrics: () => Promise<void>;
  fetchConditionedAnalysis: () => Promise<void>;
  fetchPriceAction: () => Promise<void>;
  fetchConditioningCount: () => Promise<void>;
  saveEdge: () => Promise<void>;
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const defaultConditioning: ConditioningParams = { gap_direction: "any" };

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useEventEdgeStore = create<EventEdgeState>((set, get) => ({
  // ── Query params ──────────────────────────────────────────────────────────
  symbol: "AAPL",
  companyName: "",
  source: "yfinance",
  mt5Account: "darwinex_XKLN",
  ohlcvSource: "yfinance",
  typeData: "ohlcv",
  assetClass: "equity",
  timeframe: "1d",
  typeSaved: "complete_historical",
  // ── Analysis params ───────────────────────────────────────────────────────
  eventType: "earnings",
  model: "bootstrap",
  nPeriods: 5,
  priceActionMode: "holding",
  priceActionEventTF: "30m",
  gapThreshold: 1.0,
  includeEarningsDays: null,
  bins: [-0.05, -0.01, 0.01, 0.05],
  conditioning: defaultConditioning,
  dateStart: "",
  dateEnd: "",
  // ── Results ───────────────────────────────────────────────────────────────
  events: [],
  globalMetrics: null,
  probabilisticResult: null,
  priceActionResult: null,
  brokerStatuses: [],
  conditioningCount: null,
  // ── Loading / error ───────────────────────────────────────────────────────
  isLoadingEvents: false,
  isLoadingGlobal: false,
  isLoadingMetrics: false,
  isLoadingBrokerStatus: false,
  isLoadingPriceAction: false,
  isLoadingConditioningCount: false,
  isSavingEdge: false,
  lastSavedRunId: null,
  error: null,
  infoMessage: null,

  // ── Setters ───────────────────────────────────────────────────────────────
  setSymbol: (symbol) => set({ symbol, error: null, infoMessage: null }),
  setSource: (source) => set({ source, events: [], globalMetrics: null, probabilisticResult: null, conditioningCount: null }),
  setMt5Account: (mt5Account) => set({ mt5Account }),
  setOhlcvSource: (ohlcvSource) => set({ ohlcvSource }),
  setTypeData: (typeData) => {
    const firstClass = ASSET_CLASS_OPTIONS[typeData][0];
    const autoEventType = typeData === "fundamental" ? ("earnings" as EventType) : get().eventType;
    set({ typeData, assetClass: firstClass, eventType: autoEventType,
          events: [], globalMetrics: null, probabilisticResult: null,
          conditioningCount: null, infoMessage: null });
  },
  setAssetClass: (assetClass) => set({ assetClass }),
  setTimeframe: (timeframe) => set({ timeframe }),
  setTypeSaved: (typeSaved) => set({ typeSaved }),
  setEventType: (eventType) => set({ eventType, globalMetrics: null, probabilisticResult: null, error: null, infoMessage: null }),
  setModel: (model) => set({ model }),
  setNPeriods: (nPeriods) => set({ nPeriods: Math.max(0, Math.min(60, Math.trunc(nPeriods))) }),
  setPriceActionMode: (priceActionMode) => set({ priceActionMode }),
  setPriceActionEventTF: (priceActionEventTF) => set({ priceActionEventTF }),
  setGapThreshold: (gapThreshold) => set({ gapThreshold: Math.max(0.1, Math.min(20, Number.isFinite(gapThreshold) ? gapThreshold : 1.0)) }),
  setIncludeEarningsDays: (includeEarningsDays) => set({ includeEarningsDays }),
  setBins: (bins) => set({ bins }),
  setConditioning: (conditioning) => set({ conditioning }),
  resetConditioning: () => set({ conditioning: defaultConditioning }),
  clearResults: () => set({ events: [], globalMetrics: null, probabilisticResult: null, priceActionResult: null, conditioningCount: null, error: null }),
  setDateStart: (dateStart) => set({ dateStart }),
  setDateEnd: (dateEnd) => set({ dateEnd }),

  // ── Actions ───────────────────────────────────────────────────────────────
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
    const { symbol, source, mt5Account, ohlcvSource, typeData, eventType, dateStart, dateEnd, gapThreshold, includeEarningsDays, assetClass } = get();
    set({ isLoadingEvents: true, error: null, infoMessage: null });
    try {
      if (typeData !== "fundamental") {
        const assetInfo = await endpoints.getAssetInfo(symbol).catch(() => null);
        set({
          events: [],
          companyName: assetInfo?.short_name || "",
          isLoadingEvents: false,
          globalMetrics: null,
          probabilisticResult: null,
        });
        return;
      }
      const [events, assetInfo] = await Promise.allSettled([
        endpoints.detectEvents({
          symbol,
          source,
          asset_class: assetClass,
          ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
          event_type: eventType,
          gap_threshold_pct: gapThreshold,
          include_earnings_days: eventType === "gap" ? includeEarningsDays : null,
          ...(dateStart ? { date_range_start: dateStart } : {}),
          ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
          ...((source === "mt5" || ohlcvSource === "mt5") ? { credentials_account: mt5Account } : {}),
        }),
        endpoints.getAssetInfo(symbol),
      ]);
      set({
        events:      events.status === "fulfilled" ? events.value : [],
        companyName: assetInfo.status === "fulfilled" ? (assetInfo.value.short_name || "") : "",
        isLoadingEvents: false,
        globalMetrics: null,
        probabilisticResult: null,
      });
    } catch (error) {
      set({
        isLoadingEvents: false,
        error: error instanceof Error ? error.message : "No se pudo cargar eventos",
      });
    }
  },

  fetchGlobalMetrics: async () => {
    const { symbol, source, ohlcvSource, typeData, assetClass, timeframe } = get();
    set({ isLoadingGlobal: true, error: null, infoMessage: null });
    try {
      const globalMetrics = await endpoints.getGlobalMetrics({
        symbol,
        source,
        asset_class: assetClass,
        timeframe,
        ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
      });
      set({ globalMetrics, isLoadingGlobal: false });
    } catch (error) {
      set({
        isLoadingGlobal: false,
        error: error instanceof Error ? error.message : "No se pudo calcular línea base",
      });
    }
  },

  fetchConditionedAnalysis: async () => {
    const { symbol, source, mt5Account, ohlcvSource, typeData, eventType, model, nPeriods, priceActionMode, gapThreshold, includeEarningsDays, bins, conditioning, dateStart, dateEnd, assetClass, timeframe } = get();
    set({ isLoadingMetrics: true, error: null, infoMessage: null });
    // Path OHLCV-all-bars cuando typeData !== "fundamental"; path earnings solo en fundamental
    const resolvedEventType = typeData === "fundamental" ? eventType : null;
    try {
      const body: AnalysisRequest = {
        symbol,
        source,
        asset_class: assetClass,
        timeframe,
        ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
        event_type: resolvedEventType,
        model,
        n_periods: priceActionMode === "holding" ? nPeriods : 0,
        bins,
        gap_threshold_pct: gapThreshold,
        include_earnings_days: resolvedEventType === "gap" ? includeEarningsDays : null,
        conditioning: _normalizeConditioning(conditioning),
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
        ...((source === "mt5" || ohlcvSource === "mt5") ? { credentials_account: mt5Account } : {}),
      };
      const probabilisticResult = await endpoints.getProbabilisticMetrics(body);
      set({ probabilisticResult, isLoadingMetrics: false });
    } catch (error) {
      set({
        isLoadingMetrics: false,
        error: error instanceof Error ? error.message : "No se pudo calcular análisis condicionado",
      });
    }
  },

  fetchConditioningCount: async () => {
    const { symbol, source, mt5Account, ohlcvSource, typeData, eventType, gapThreshold, includeEarningsDays, conditioning, dateStart, dateEnd, assetClass, timeframe } = get();
    set({ isLoadingConditioningCount: true, error: null, infoMessage: null });
    const resolvedEventType = typeData === "fundamental" ? eventType : null;
    try {
      const result = await endpoints.getConditioningCount({
        symbol,
        source,
        asset_class: assetClass,
        timeframe,
        ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
        event_type: resolvedEventType,
        gap_threshold_pct: gapThreshold,
        include_earnings_days: resolvedEventType === "gap" ? includeEarningsDays : null,
        conditioning: _normalizeConditioning(conditioning),
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
        ...((source === "mt5" || ohlcvSource === "mt5") ? { credentials_account: mt5Account } : {}),
      });
      set({
        conditioningCount: result,
        isLoadingConditioningCount: false,
        infoMessage: result.fundamental_load_info ?? null,
      });
    } catch (error) {
      set({
        isLoadingConditioningCount: false,
        error: error instanceof Error ? error.message : "No se pudo calcular condicionamiento",
      });
    }
  },

  fetchPriceAction: async () => {
    const { symbol, source, mt5Account, ohlcvSource, typeData, eventType, conditioning, gapThreshold, includeEarningsDays, dateStart, dateEnd, assetClass, timeframe, nPeriods, priceActionMode, priceActionEventTF } = get();
    set({ isLoadingPriceAction: true, infoMessage: null });
    const resolvedEventType = typeData === "fundamental" ? eventType : null;
    try {
      const result = await endpoints.getPriceAction({
        symbol,
        source,
        asset_class: assetClass,
        timeframe,
        ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
        event_type: resolvedEventType,
        gap_threshold_pct: gapThreshold,
        include_earnings_days: resolvedEventType === "gap" ? includeEarningsDays : null,
        n_periods: priceActionMode === "holding" ? nPeriods : 0,
        price_action_mode: priceActionMode,
        event_timeframe: priceActionEventTF,
        include_bands: true,
        conditioning: _normalizeConditioning(conditioning),
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
        ...((source === "mt5" || ohlcvSource === "mt5") ? { credentials_account: mt5Account } : {}),
      });
      set({ priceActionResult: result, isLoadingPriceAction: false });
    } catch (error) {
      set({
        isLoadingPriceAction: false,
        error: error instanceof Error ? error.message : "No se pudo cargar Price Action",
      });
    }
  },

  saveEdge: async () => {
    const { symbol, source, mt5Account, ohlcvSource, typeData, eventType, model, nPeriods, priceActionMode,
             gapThreshold, includeEarningsDays, bins, conditioning, dateStart, dateEnd,
             assetClass, timeframe } = get();
    set({ isSavingEdge: true, error: null, infoMessage: null });
    const resolvedEventType = typeData === "fundamental" ? eventType : null;
    try {
      const body: SaveEdgeRequest = {
        symbol,
        source,
        asset_class: assetClass,
        timeframe,
        ...(typeData === "fundamental" ? { ohlcv_source: ohlcvSource } : {}),
        event_type: resolvedEventType,
        model,
        n_periods: priceActionMode === "holding" ? nPeriods : 0,
        bins,
        gap_threshold_pct: gapThreshold,
        include_earnings_days: resolvedEventType === "gap" ? includeEarningsDays : null,
        conditioning: _normalizeConditioning(conditioning),
        ...(dateStart ? { date_range_start: dateStart } : {}),
        ...(dateEnd   ? { date_range_end:   dateEnd   } : {}),
        ...((source === "mt5" || ohlcvSource === "mt5") ? { credentials_account: mt5Account } : {}),
      };
      const result = await endpoints.saveEdge(body);
      set({
        isSavingEdge: false,
        lastSavedRunId: result.run_id,
        infoMessage: `Análisis guardado · ${result.symbol}/${result.timeframe} · run_id: ${result.run_id}`,
      });
    } catch (error) {
      set({
        isSavingEdge: false,
        error: error instanceof Error ? error.message : "No se pudo guardar el análisis",
      });
    }
  },
}));

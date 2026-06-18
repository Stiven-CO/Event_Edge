import { api } from "@/api/client";
import type {
  AnalysisRequest,
  AssetBasicInfo,
  AssetInfo,
  BrokerStatus,
  ConditioningCountRequest,
  ConditioningCountResult,
  DetectEventsRequest,
  EventRecord,
  GlobalInformativeMetrics,
  GlobalInformativeRequest,
  PriceActionRequest,
  PriceActionResult,
  ProbabilisticResult,
} from "@/api/types";

export const endpoints = {
  getBrokerStatus: () => api.request<BrokerStatus[]>("/control/broker-status"),
  getAssets: (assetClass = "equity") =>
    api.request<AssetInfo[]>(`/assets?asset_class=${encodeURIComponent(assetClass)}`),
  getAssetInfo: (symbol: string) =>
    api.request<AssetBasicInfo>(`/assets/${encodeURIComponent(symbol)}/info`),
  detectEvents: (body: DetectEventsRequest) =>
    api.request<EventRecord[]>("/events/detect", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getGlobalMetrics: (body: GlobalInformativeRequest) =>
    api.request<GlobalInformativeMetrics>("/analysis/informative", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getProbabilisticMetrics: (body: AnalysisRequest) =>
    api.request<ProbabilisticResult>("/analysis/probabilistic", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getPriceAction: (body: PriceActionRequest) =>
    api.request<PriceActionResult>("/analysis/price-action", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getConditioningCount: (body: ConditioningCountRequest) =>
    api.request<ConditioningCountResult>("/analysis/conditioning-count", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

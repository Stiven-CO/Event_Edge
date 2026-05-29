export type EventType = "earnings" | "gap";
export type ModelType = "frequentist" | "bootstrap" | "kde" | "bayesian";
export type GuidanceDirection = "raised" | "maintained" | "lowered" | "not_available";
export type BBPosition = "below_lower" | "in_lower" | "middle" | "in_upper" | "above_upper";
export type TrendDirection = "bullish" | "sideways" | "bearish";
export type RSIZone = "oversold" | "neutral" | "overbought";
export type VolRegime = "low" | "normal" | "high";
export type DayOfWeek = "monday" | "tuesday" | "wednesday" | "thursday" | "friday";
export type MonthOfYear = "jan" | "feb" | "mar" | "apr" | "may" | "jun" | "jul" | "aug" | "sep" | "oct" | "nov" | "dec";
export type Quarter = "q1" | "q2" | "q3" | "q4";
export type EarningsSeason = "peak" | "off_season";

export interface BrokerStatus {
  source: string;
  alive: boolean;
  mode: string;
  detail: string | null;
}

export interface AssetInfo {
  symbol: string;
  source: string;
  asset_class: string;
  timeframe: string;
}

export interface AssetBasicInfo {
  symbol: string;
  short_name: string;
  long_name: string;
  sector: string;
  industry: string;
}

export interface EventRecord {
  date: string;
  event_type: EventType;
  symbol: string;
  gap_pct: number | null;
  eps_actual: number | null;
  eps_estimate: number | null;
  eps_surprise_pct: number | null;
  revenue_actual: number | null;
  revenue_estimate: number | null;
  revenue_surprise_pct: number | null;
  guidance: GuidanceDirection;
}

export interface ScenarioBin {
  label: string;
  lower: number | null;
  upper: number | null;
  probability: number;
  ci_lower: number;
  ci_upper: number;
  event_count: number;
}

export interface ProbabilisticFamily {
  family: "close_return" | "gap_fill";
  n_periods: number;
  n_samples_used: number;
  n_total_events: number;
  warning: "insufficient_samples" | "no_gap_events" | null;
  scenarios: ScenarioBin[];
}

export interface ProbabilisticResult {
  symbol: string;
  model: ModelType;
  data_source: string;
  families: ProbabilisticFamily[];
}

export interface InformativeMetrics {
  symbol: string;
  event_type: EventType;
  n_total_events: number;
  frequency_per_year: number;
  frequency_per_quarter: number;
  avg_movement_range: Record<number, { mean: number; std: number }>;
  avg_candle_range: Record<number, { mean: number; std: number }>;
  gap_mean: number | null;
  gap_std: number | null;
  data_source: string;
  // P0 (día del evento)
  event_day_range_mean?: number | null;
  event_day_range_std?: number | null;
  event_day_volume_mean?: number | null;
  event_day_volume_std?: number | null;
  event_day_return_mean?: number | null;
  event_day_return_std?: number | null;
  // Forward returns P1-Open → Pn-Close
  avg_forward_return?: Record<number, { mean: number; std: number }>;
}

export interface ConditioningParams {
  // A — Tendencia
  ema5_vs_ema20_ratio_min?: number;
  ema5_vs_ema20_ratio_max?: number;
  price_vs_ema50_pct_min?: number;
  price_vs_ema50_pct_max?: number;
  trend_directions?: TrendDirection[];
  // B — Momentum
  return_5d_min?: number;
  return_5d_max?: number;
  return_20d_min?: number;
  return_20d_max?: number;
  rsi14_min?: number;
  rsi14_max?: number;
  // C — Sobreextensión
  bb_positions?: BBPosition[];
  bb_width_pct_min?: number;
  bb_width_pct_max?: number;
  rsi14_zones?: RSIZone[];
  // D — Volatilidad
  hist_vol_10d_min?: number;
  hist_vol_10d_max?: number;
  vol_ratio_min?: number;
  vol_ratio_max?: number;
  atr_pct_min?: number;
  atr_pct_max?: number;
  vol_regimes?: VolRegime[];
  // E — Fundamental
  eps_surprise_pct_min?: number;
  eps_surprise_pct_max?: number;
  guidance_directions?: GuidanceDirection[];
  // F — Posicionamiento
  gap_pct_min?: number;
  gap_pct_max?: number;
  gap_direction?: "positive" | "negative" | "any";
  // G — Estacionalidad
  days_of_week?: DayOfWeek[];
  months?: MonthOfYear[];
  quarters?: Quarter[];
  earnings_seasons?: EarningsSeason[];
}

export interface DetectEventsRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  event_type: EventType;
  gap_threshold_pct: number;
  date_range_start?: string;
  date_range_end?: string;
}

export interface InformativeRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  event_type: EventType;
  gap_threshold_pct: number;
  periods?: number[];
}

export interface AnalysisRequest {
  symbol: string;
  source: string;
  asset_class: string;
  event_type: EventType;
  gap_threshold_pct: number;
  n_periods: number;
  model: ModelType;
  bins: number[];
  conditioning: ConditioningParams;
  date_range_start?: string;
  date_range_end?: string;
}

// ---------------------------------------------------------------------------
// Price Action Plot — Phase 13
// ---------------------------------------------------------------------------

export interface PriceActionPoint {
  x: number;
  y: number;
}

export interface PriceActionSeries {
  points: PriceActionPoint[];
  band_upper: PriceActionPoint[] | null;
  band_lower: PriceActionPoint[] | null;
}

export interface PriceActionResult {
  anchor_mode: "intraday_30min" | "daily";
  n_periods: number;
  x_labels: string[];
  series_all:  PriceActionSeries;
  series_win:  PriceActionSeries;
  series_loss: PriceActionSeries;
  n_events_all:     number;
  n_events_win:     number;
  n_events_loss:    number;
  n_events_omitted: number;
  warning: "insufficient_events" | "some_events_omitted" | null;
}

export interface PriceActionRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  event_type: EventType;
  gap_threshold_pct: number;
  n_periods: number;
  include_bands: boolean;
  conditioning: ConditioningParams;
}

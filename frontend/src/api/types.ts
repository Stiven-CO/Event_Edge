export type EventType = "earnings" | "gap";
export type ModelType = "frequentist" | "bootstrap" | "kde" | "bayesian";
export type BBPosition = "below_lower" | "in_lower" | "middle" | "in_upper" | "above_upper";
export type TrendDirection = "bullish" | "sideways" | "bearish";
export type RSIZone = "oversold" | "neutral" | "overbought";
export type VolRegime = "low" | "normal" | "high";
export type DayOfWeek = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday";
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

// Estadísticas del EVENTO condicionado (día P0): frecuencia, gap, día del evento.
// No incluye retorno posterior — ver FutureReturnMetrics.
export interface ConditionedSummary {
  n_conditioned_events: number;
  n_total_events: number;
  filter_rate: number;
  frequency_per_year: number;
  frequency_per_quarter: number;
  gap_mean: number | null;
  gap_std: number | null;
  event_day_range_mean: number | null;
  event_day_range_std: number | null;
  event_day_volume_mean: number | null;
  event_day_volume_std: number | null;
  event_day_return_mean: number | null;
  event_day_return_std: number | null;
  return_samples_gap: number[];
}

// Métricas del RETORNO POSTERIOR al evento (P1 → Pn), al período elegido por el usuario.
export interface FutureReturnMetrics {
  n_periods: number;
  avg_forward_return: Record<number, { mean: number; std: number }>;
  return_max: number | null;
  return_min: number | null;
  return_avg_positive: number | null;
  return_avg_negative: number | null;
  return_count_positive: number;
  return_count_negative: number;
  return_skewness: number | null;
  return_kurtosis: number | null;
  return_samples_close: number[];
}

export interface ProbabilisticResult {
  symbol: string;
  model: ModelType;
  data_source: string;
  data_source_detail?: string | null;
  families: ProbabilisticFamily[];
  conditioned_summary?: ConditionedSummary | null;
  future_return_metrics?: FutureReturnMetrics | null;
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
  data_source_detail?: string | null;
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
  return_5p_min?: number;
  return_5p_max?: number;
  return_20p_min?: number;
  return_20p_max?: number;
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
  take_earnings?: boolean;
  // Filtra sobre eps_surprise_pct_ffill (disponible en toda barra), no sobre el
  // valor puntual del día de reporte.
  eps_surprise_pct_min?: number;
  eps_surprise_pct_max?: number;
  // Tendencia EPS (-1/0/1 vs. trimestre anterior) — categórico, selección múltiple.
  // Disponible en toda barra (backward/forward-fill).
  reported_eps_trends?: number[];
  eps_estimate_trends?: number[];
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
  ohlcv_source?: string;
  event_type: EventType;
  gap_threshold_pct: number;
  include_earnings_days?: boolean | null;
  date_range_start?: string;
  date_range_end?: string;
  credentials_account?: string;
}

export interface InformativeRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  event_type: EventType;
  gap_threshold_pct: number;
  include_earnings_days?: boolean | null;
  periods?: number[];
}

// ---------------------------------------------------------------------------
// Global Informative Metrics — Phase 1 (sin eventos)
// ---------------------------------------------------------------------------

export interface GlobalInformativeRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  ohlcv_source?: string;
  timeframe?: string;
}

export interface ReturnHistogram {
  edges: number[];    // len = n_bins + 1
  counts: number[];   // len = n_bins
}

export interface QQPlotData {
  theoretical: number[];
  sample: number[];
}

export interface RollingVolPoint {
  date: string;   // "YYYY-MM-DD"
  vol: number;    // volatilidad anualizada (fracción, ej. 0.25 = 25%)
}

export interface GlobalInformativeMetrics {
  symbol: string;
  data_source: string;
  data_source_detail?: string | null;
  n_observations: number;
  date_start: string;
  date_end: string;
  return_histogram: ReturnHistogram;
  qqplot_data: QQPlotData;
  return_mean: number;
  return_median: number;
  return_std: number;
  return_skewness: number;
  return_kurtosis: number;
  return_min: number;
  return_max: number;
  annualized_vol: number;
  atr_mean: number;
  rolling_vol_30d: RollingVolPoint[];
  hurst_exponent: number | null;
  autocorr_lag1: number;
  autocorr_lag5: number;
  autocorr_lag10: number;
}

export interface AnalysisRequest {
  symbol: string;
  source: string;
  asset_class: string;
  ohlcv_source?: string;
  timeframe?: string;
  event_type: EventType | null;  // null → path OHLCV-all-bars
  gap_threshold_pct: number;
  include_earnings_days?: boolean | null;
  n_periods: number;
  model: ModelType;
  bins: number[];
  conditioning: ConditioningParams;
  date_range_start?: string;
  date_range_end?: string;
  credentials_account?: string;
  // Determina qué representa future_return_metrics: "holding" → retorno
  // posterior al evento (P1→Pn); "in_event" → retorno del propio día del evento.
  price_action_mode?: "holding" | "in_event";
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
  intraday_source_error: string | null;
}

export interface PriceActionRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  ohlcv_source?: string;
  timeframe?: string;
  event_type: EventType | null;  // null → path OHLCV-all-bars
  gap_threshold_pct: number;
  include_earnings_days?: boolean | null;
  n_periods: number;
  include_bands: boolean;
  price_action_mode?: "holding" | "in_event";
  event_timeframe?: string;
  conditioning: ConditioningParams;
  credentials_account?: string;
}

// ---------------------------------------------------------------------------
// Dashboard Quant — distribución por offset (complemento del price action)
// ---------------------------------------------------------------------------

export type DistributionColorBase = "azul" | "amarillo" | "coral" | "blanco";
export type DistributionIcon = "" | "⚡" | "⚠️" | "🔄";

export interface DistributionStatsRow {
  offset: number;
  label: string;
  n_obs: number;

  ret_mean: number;
  ret_p25: number;
  ret_p75: number;
  cvar: number;
  r_cvar: number;
  asimetria: number;
  curtosis: number;

  rev_alcista_mean: number;
  rev_alcista_p75: number;
  rev_bajista_mean: number;
  rev_bajista_p25: number;

  ratio_colas: number;

  color_base: DistributionColorBase;
  icon: DistributionIcon;
}

export interface DistributionStatsResult {
  anchor_mode: "intraday_30min" | "daily";
  n_periods: number;
  x_labels: string[];
  rows: DistributionStatsRow[];
  n_events_used: number;
  n_events_omitted: number;
  warning: "insufficient_events" | "some_events_omitted" | null;
  intraday_source_error: string | null;
}

// ---------------------------------------------------------------------------
// Persistencia — guardar Edge
// ---------------------------------------------------------------------------

export interface SaveEdgeRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  ohlcv_source?: string;
  timeframe?: string;
  event_type: EventType | null;
  gap_threshold_pct: number;
  include_earnings_days?: boolean | null;
  n_periods: number;
  model: ModelType;
  bins: number[];
  conditioning: ConditioningParams;
  date_range_start?: string;
  date_range_end?: string;
  credentials_account?: string;
  price_action_mode?: "holding" | "in_event";
}

export interface SaveEdgeResponse {
  run_id: string;
  symbol: string;
  timeframe: string;
  created_at: string;
  return_samples_file: string;
}

export interface ConditionedBar {
  // Identidad
  date: string;
  event_type: string | null;
  symbol: string | null;
  // Base cruda (OHLCV)
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  // Base cruda (Earnings)
  eps_actual: number | null;
  eps_estimate: number | null;
  surprise_pct: number | null;
  revenue_actual: number | null;
  revenue_estimate: number | null;
  // F - Posicionamiento
  gap_pct: number | null;
  // A - Tendencia
  ema5_vs_ema20_ratio: number | null;
  price_vs_ema50_pct: number | null;
  trend_direction: string | null;
  // B - Momentum
  return_5p: number | null;
  return_20p: number | null;
  rsi14: number | null;
  // C - Sobreextensión
  bb_position: string | null;
  bb_width_pct: number | null;
  rsi14_zone: string | null;
  // D - Volatilidad
  hist_vol_10d: number | null;
  vol_ratio_10_30: number | null;
  atr_pct: number | null;
  vol_regime: string | null;
  // E - Fundamental
  take_earnings: boolean | null;
  eps_surprise_pct: number | null;
  eps_actual_ffill: number | null;
  reported_eps_trend: number | null;
  eps_estimate_ffill: number | null;
  eps_estimate_trend: number | null;
  eps_surprise_pct_ffill: number | null;
  // G - Estacionalidad
  day_of_week: string | null;
  month: string | null;
  quarter: string | null;
  earnings_season: string | null;
}

export interface ConditioningCountRequest {
  symbol: string;
  source?: string;
  asset_class?: string;
  ohlcv_source?: string;
  timeframe?: string;
  event_type?: EventType | null;
  gap_threshold_pct?: number;
  include_earnings_days?: boolean | null;
  conditioning: ConditioningParams;
  date_range_start?: string;
  date_range_end?: string;
  credentials_account?: string;
}

export interface ConditioningCountResult {
  n_conditioned: number;
  n_total: number;
  rows: ConditionedBar[];
  fundamental_load_info?: string | null;
}

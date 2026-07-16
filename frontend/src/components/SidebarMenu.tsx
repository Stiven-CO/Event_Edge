import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";

import type {
  BBPosition, ConditioningParams, DayOfWeek, EarningsSeason,
  ModelType,
  MonthOfYear, Quarter, RSIZone, TrendDirection, VolRegime,
} from "@/api/types";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useEvents } from "@/hooks/useEvents";
import {
  ASSET_CLASS_OPTIONS,
  SOURCE_OPTIONS,
  TIMEFRAME_OPTIONS,
  type DataSource,
  type TypeData,
  useEventEdgeStore,
} from "@/store/eventEdgeStore";

// ── Helpers ───────────────────────────────────────────────────────────────────
const symbolRe = /^[A-Z]{1,5}$/;

const modelDescriptions: Record<ModelType, string> = {
  frequentist: "Frecuencias observadas con intervalo Wilson.",
  bootstrap:   "Re-muestreo robusto con intervalos por percentiles.",
  kde:         "Densidad suavizada para colas continuas.",
  bayesian:    "Posterior Beta con prior de Laplace.",
};

const TYPE_DATA_LABEL: Record<TypeData, string> = {
  ohlcv:       "OHLCV (precio)",
  fundamental: "Fundamental",
  macro:       "Macro / Económico",
};

interface RangeState { min?: number; max?: number }

function updateRange(
  params: ConditioningParams,
  keyMin: keyof ConditioningParams,
  keyMax: keyof ConditioningParams,
  range: RangeState,
): ConditioningParams {
  return { ...params, [keyMin]: range.min, [keyMax]: range.max };
}

function validateBins(values: number[]): string | null {
  if (values.length < 2) return "Se requieren al menos 2 bins";
  if (values.some((v) => Number.isNaN(v) || v < -1 || v > 1))
    return "Todos los bins deben estar entre -1.0 y 1.0";
  for (let i = 1; i < values.length; i++) {
    if (!(values[i] > values[i - 1])) return "Los bins deben estar ordenados de menor a mayor";
  }
  return null;
}

// ── Accordion ─────────────────────────────────────────────────────────────────
function Accordion({
  title, defaultOpen = false, children,
}: {
  title: string; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-surface-border overflow-hidden">
      <button
        type="button"
        className="accordion-btn"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{title}</span>
        {open
          ? <ChevronUp   className="h-4 w-4 text-ink-muted" />
          : <ChevronDown className="h-4 w-4 text-ink-muted" />}
      </button>
      {open && (
        <div className="border-t border-surface-border bg-surface-base/40 px-4 py-4 space-y-3 animate-fade-in">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────
function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="label">{children}</label>;
}

function RangeRow({
  label, min, max, value, onChange,
}: {
  label: string; min: number; max: number;
  value: RangeState; onChange: (r: RangeState) => void;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <div className="grid grid-cols-2 gap-2">
        <input className="input" type="number" placeholder="min" min={min} max={max}
          value={value.min ?? ""}
          onChange={(e) => onChange({ ...value, min: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
        <input className="input" type="number" placeholder="max" min={min} max={max}
          value={value.max ?? ""}
          onChange={(e) => onChange({ ...value, max: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
      </div>
    </div>
  );
}

function CheckboxGroup<T extends string>({
  label, values, selected, onToggle,
}: {
  label: string; values: T[]; selected: T[]; onToggle: (v: T) => void;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <button
            key={v} type="button" onClick={() => onToggle(v)}
            className={`rounded-md border px-2 py-1 text-xs transition ${
              selected.includes(v)
                ? "border-accent bg-accent/15 text-accent"
                : "border-surface-border text-ink-muted hover:border-accent/40 hover:text-ink-secondary"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Main SidebarMenu ──────────────────────────────────────────────────────────
export function SidebarMenu() {
  // ── Store read ───────────────────────────────────────────────────────────────
  const symbol       = useEventEdgeStore((s) => s.symbol);
  const companyName  = useEventEdgeStore((s) => s.companyName);
  const source       = useEventEdgeStore((s) => s.source);
  const mt5Account   = useEventEdgeStore((s) => s.mt5Account);
  const ohlcvSource  = useEventEdgeStore((s) => s.ohlcvSource);
  const error        = useEventEdgeStore((s) => s.error);
  const typeData     = useEventEdgeStore((s) => s.typeData);
  const assetClass   = useEventEdgeStore((s) => s.assetClass);
  const timeframe    = useEventEdgeStore((s) => s.timeframe);
  const eventType    = useEventEdgeStore((s) => s.eventType);
  const model        = useEventEdgeStore((s) => s.model);
  const nPeriods           = useEventEdgeStore((s) => s.nPeriods);
  const priceActionMode    = useEventEdgeStore((s) => s.priceActionMode);
  const bins         = useEventEdgeStore((s) => s.bins);
  const conditioning = useEventEdgeStore((s) => s.conditioning);
  const dateStart    = useEventEdgeStore((s) => s.dateStart);
  const dateEnd      = useEventEdgeStore((s) => s.dateEnd);
  const events         = useEventEdgeStore((s) => s.events);
  const globalMetrics  = useEventEdgeStore((s) => s.globalMetrics);
  const probabilisticResult = useEventEdgeStore((s) => s.probabilisticResult);

  // ── Store write ──────────────────────────────────────────────────────────────
  const setSymbol       = useEventEdgeStore((s) => s.setSymbol);
  const setSource       = useEventEdgeStore((s) => s.setSource);
  const setMt5Account   = useEventEdgeStore((s) => s.setMt5Account);
  const setOhlcvSource  = useEventEdgeStore((s) => s.setOhlcvSource);
  const setTypeData     = useEventEdgeStore((s) => s.setTypeData);
  const setAssetClass   = useEventEdgeStore((s) => s.setAssetClass);
  const setTimeframe    = useEventEdgeStore((s) => s.setTimeframe);
  const setModel              = useEventEdgeStore((s) => s.setModel);
  const setNPeriods           = useEventEdgeStore((s) => s.setNPeriods);
  const setPriceActionMode    = useEventEdgeStore((s) => s.setPriceActionMode);
  const setBins         = useEventEdgeStore((s) => s.setBins);
  const setConditioning = useEventEdgeStore((s) => s.setConditioning);
  const resetConditioning = useEventEdgeStore((s) => s.resetConditioning);
  const setDateStart    = useEventEdgeStore((s) => s.setDateStart);
  const setDateEnd      = useEventEdgeStore((s) => s.setDateEnd);

  // ── Hooks ────────────────────────────────────────────────────────────────────
  const { run: runEvents, isLoadingEvents } = useEvents();
  const {
    runGlobalMetrics,
    runConditionedAnalysis,
    runConditioningCount,
    conditioningCount,
    isLoadingGlobal,
    isLoadingMetrics,
    isLoadingConditioningCount,
  } = useAnalysis();

  // ── Local state ──────────────────────────────────────────────────────────────
  const [symbolDraft, setSymbolDraft] = useState(symbol);
  const [binsDraft, setBinsDraft]     = useState(bins.join(", "));
  const [localCond, setLocalCond]     = useState<ConditioningParams>(conditioning);

  const symbolError = useMemo(() => {
    if (symbolDraft.length === 0) return "Ingresa un símbolo";
    return symbolRe.test(symbolDraft) ? null : "Usa solo 1-5 letras mayúsculas";
  }, [symbolDraft]);

  const parsedBins = useMemo(
    () => binsDraft.split(",").map((v) => Number(v.trim())).filter((v) => !Number.isNaN(v)),
    [binsDraft],
  );
  const binsError = validateBins(parsedBins);

  const assetClassOptions = ASSET_CLASS_OPTIONS[typeData];
  const conditioned = conditioningCount?.n_conditioned ?? 0;
  const total       = conditioningCount?.n_total ?? 0;
  const epsEnabled  = eventType === "earnings";

  function toggleArr<T extends string>(arr: T[] | undefined, v: T): T[] {
    const s = new Set(arr ?? []);
    s.has(v) ? s.delete(v) : s.add(v);
    return Array.from(s);
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <aside className="flex h-full flex-col overflow-y-auto">
      <div className="space-y-2 p-2">

        {/* ══════════════════════════ PASO 1 · DATOS ══════════════════════════ */}
        <Accordion title="Datos" defaultOpen>

          <div>
            <FieldLabel>Símbolo</FieldLabel>
            <input
              className="input mt-1"
              value={symbolDraft}
              onChange={(e) => setSymbolDraft(e.target.value.toUpperCase())}
              placeholder="AAPL"
              maxLength={5}
            />
            {symbolError && <p className="mt-1 text-xs text-status-error">{symbolError}</p>}
            {companyName && (
              <p className="mt-1 truncate text-xs font-medium text-accent" title={companyName}>
                {companyName}
              </p>
            )}
          </div>

          <div>
            <FieldLabel>Fuente</FieldLabel>
            <select
              className="input mt-1"
              value={source}
              onChange={(e) => setSource(e.target.value as DataSource)}
            >
              {SOURCE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {source === "mt5" && (
            <div>
              <FieldLabel>Cuenta MT5</FieldLabel>
              <input
                className="input mt-1"
                value={mt5Account}
                onChange={(e) => setMt5Account(e.target.value)}
                placeholder="main"
              />
              <p className="mt-1 text-xs text-ink-muted">Clave de cuenta en MDH_MT5_ACCOUNTS</p>
            </div>
          )}

          {typeData === "fundamental" && (
            <div>
              <FieldLabel>Fuente OHLCV</FieldLabel>
              <select
                className="input mt-1"
                value={ohlcvSource}
                onChange={(e) => setOhlcvSource(e.target.value as DataSource)}
              >
                {SOURCE_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <p className="mt-1 text-xs text-ink-muted">Fuente para precios OHLCV (equity)</p>
            </div>
          )}

          <div>
            <FieldLabel>Tipo de Data</FieldLabel>
            <select
              className="input mt-1"
              value={typeData}
              onChange={(e) => setTypeData(e.target.value as TypeData)}
            >
              {(["ohlcv", "fundamental", "macro"] as TypeData[]).map((t) => (
                <option key={t} value={t}>{TYPE_DATA_LABEL[t]}</option>
              ))}
            </select>
          </div>

          <div>
            <FieldLabel>Segmento Financiero</FieldLabel>
            <select
              className="input mt-1"
              value={assetClass}
              onChange={(e) => setAssetClass(e.target.value)}
            >
              {assetClassOptions.map((ac) => (
                <option key={ac} value={ac}>{ac}</option>
              ))}
            </select>
          </div>

          <div>
            <FieldLabel>Timeframe</FieldLabel>
            <select
              className="input mt-1"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
            >
              {TIMEFRAME_OPTIONS.map((tf) => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <FieldLabel>Desde</FieldLabel>
              <input type="date" className="input mt-1" value={dateStart}
                onChange={(e) => setDateStart(e.target.value)} />
            </div>
            <div>
              <FieldLabel>Hasta</FieldLabel>
              <input type="date" className="input mt-1" value={dateEnd}
                onChange={(e) => setDateEnd(e.target.value)} />
            </div>
          </div>

          <button
            type="button"
            className="btn-primary w-full"
            disabled={Boolean(symbolError) || isLoadingEvents}
            onClick={async () => {
              if (symbolError) return;
              setSymbol(symbolDraft);
              await runEvents();
            }}
          >
            {isLoadingEvents ? "Buscando..." : "Buscar"}
          </button>

          {typeData === "fundamental" && events.length > 0 && !isLoadingEvents && (
            <div className="rounded border border-status-success/30 bg-status-success/8 p-2 text-xs space-y-0.5">
              <p className="font-semibold text-ink-primary">
                {symbol}{companyName ? ` · ${companyName}` : ""}
              </p>
              <p className="text-ink-muted">{events.length} eventos encontrados</p>
              <p className="font-mono text-ink-muted">
                {events[0].date.slice(0, 10)} → {events[events.length - 1].date.slice(0, 10)}
              </p>
            </div>
          )}
          {typeData !== "fundamental" && globalMetrics != null && !isLoadingGlobal && (
            <div className="rounded border border-status-success/30 bg-status-success/8 p-2 text-xs space-y-0.5">
              <p className="font-semibold text-ink-primary">
                {symbol}{companyName ? ` · ${companyName}` : ""}
              </p>
              <p className="font-mono text-ink-muted">
                {globalMetrics.date_start.slice(0, 10)} → {globalMetrics.date_end.slice(0, 10)}
              </p>
            </div>
          )}
          {error && events.length === 0 && !isLoadingEvents && (
            <p className="text-xs text-status-error">{error}</p>
          )}

          {/* ════════════════ PASO 2 · Cálculo de Estadísticas Globales ════════════════ */}
          <button
            type="button"
            className="btn-primary w-full"
            disabled={Boolean(symbolError) || isLoadingGlobal}
            onClick={async () => { await runGlobalMetrics(); }}
          >
            {isLoadingGlobal ? "Calculando..." : "Calcular Estadisticas Globales"}
          </button>
        </Accordion>

        {/* ════════════════ PASO 3 · CONFIGURACIÓN DE EVENTOS ════════════════ */}
        <Accordion title="Configuración de Eventos">

          <p className="text-xs text-ink-muted">
            {conditioned} condicionados / {total} totales
          </p>

          <Accordion title="A · Tendencia">
            <RangeRow label="EMA5/EMA20 ratio %" min={-20} max={20}
              value={{ min: localCond.ema5_vs_ema20_ratio_min, max: localCond.ema5_vs_ema20_ratio_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "ema5_vs_ema20_ratio_min", "ema5_vs_ema20_ratio_max", r))} />
            <RangeRow label="Precio vs EMA50 %" min={-30} max={30}
              value={{ min: localCond.price_vs_ema50_pct_min, max: localCond.price_vs_ema50_pct_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "price_vs_ema50_pct_min", "price_vs_ema50_pct_max", r))} />
            <CheckboxGroup<TrendDirection>
              label="Dirección de tendencia"
              values={["bullish", "sideways", "bearish"]}
              selected={localCond.trend_directions ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, trend_directions: toggleArr(localCond.trend_directions, v) })} />
          </Accordion>

          <Accordion title="B · Momentum">
            <RangeRow label="Retorno 5 períodos %" min={-30} max={30}
              value={{ min: localCond.return_5p_min, max: localCond.return_5p_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "return_5p_min", "return_5p_max", r))} />
            <RangeRow label="Retorno 20 períodos %" min={-40} max={40}
              value={{ min: localCond.return_20p_min, max: localCond.return_20p_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "return_20p_min", "return_20p_max", r))} />
            <RangeRow label="RSI(14)" min={0} max={100}
              value={{ min: localCond.rsi14_min, max: localCond.rsi14_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "rsi14_min", "rsi14_max", r))} />
          </Accordion>

          <Accordion title="C · Sobreextensión">
            <CheckboxGroup<BBPosition>
              label="Posición en BB(20,2)"
              values={["below_lower", "in_lower", "middle", "in_upper", "above_upper"]}
              selected={localCond.bb_positions ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, bb_positions: toggleArr(localCond.bb_positions, v) })} />
            <RangeRow label="Amplitud de BB %" min={0} max={30}
              value={{ min: localCond.bb_width_pct_min, max: localCond.bb_width_pct_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "bb_width_pct_min", "bb_width_pct_max", r))} />
            <CheckboxGroup<RSIZone>
              label="Zona RSI"
              values={["oversold", "neutral", "overbought"]}
              selected={localCond.rsi14_zones ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, rsi14_zones: toggleArr(localCond.rsi14_zones, v) })} />
          </Accordion>

          <Accordion title="D · Volatilidad">
            <RangeRow label="Vol. histórica 10d (% anual)" min={0} max={200}
              value={{ min: localCond.hist_vol_10d_min, max: localCond.hist_vol_10d_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "hist_vol_10d_min", "hist_vol_10d_max", r))} />
            <RangeRow label="Vol. ratio (10d/30d)" min={0} max={5}
              value={{ min: localCond.vol_ratio_min, max: localCond.vol_ratio_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "vol_ratio_min", "vol_ratio_max", r))} />
            <RangeRow label="ATR(14) / Close %" min={0} max={15}
              value={{ min: localCond.atr_pct_min, max: localCond.atr_pct_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "atr_pct_min", "atr_pct_max", r))} />
            <CheckboxGroup<VolRegime>
              label="Régimen de volatilidad"
              values={["low", "normal", "high"]}
              selected={localCond.vol_regimes ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, vol_regimes: toggleArr(localCond.vol_regimes, v) })} />
          </Accordion>

          {epsEnabled && (
            <Accordion title="E · Fundamental">
              <div className="flex items-center gap-2 py-1 text-xs text-text-secondary">
                <input
                  id="take-earnings-cb"
                  type="checkbox"
                  checked={localCond.take_earnings === true}
                  onChange={(e) => setLocalCond({ ...localCond, take_earnings: e.target.checked ? true : undefined })}
                  className="accent-brand-primary"
                />
                <label htmlFor="take-earnings-cb" className="cursor-pointer select-none">
                  Solo días de reporte de earnings
                </label>
              </div>
              <RangeRow label="EPS surprise %" min={-100} max={100}
                value={{ min: localCond.eps_surprise_pct_min, max: localCond.eps_surprise_pct_max }}
                onChange={(r) => setLocalCond(updateRange(localCond, "eps_surprise_pct_min", "eps_surprise_pct_max", r))} />
              <RangeRow label="Tendencia EPS reportado (-1 baja / 0 igual / 1 sube)" min={-1} max={1}
                value={{ min: localCond.reported_eps_trend_min, max: localCond.reported_eps_trend_max }}
                onChange={(r) => setLocalCond(updateRange(localCond, "reported_eps_trend_min", "reported_eps_trend_max", r))} />
              <RangeRow label="Tendencia EPS estimado (-1 baja / 0 igual / 1 sube)" min={-1} max={1}
                value={{ min: localCond.eps_estimate_trend_min, max: localCond.eps_estimate_trend_max }}
                onChange={(r) => setLocalCond(updateRange(localCond, "eps_estimate_trend_min", "eps_estimate_trend_max", r))} />
            </Accordion>
          )}

          <Accordion title="F · Posicionamiento (Gap)">
            <RangeRow label="Gap apertura %" min={-15} max={15}
              value={{ min: localCond.gap_pct_min, max: localCond.gap_pct_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "gap_pct_min", "gap_pct_max", r))} />
            <div>
              <p className="label mb-1">Dirección del gap</p>
              <div className="flex gap-1.5">
                {(["any", "positive", "negative"] as const).map((dir) => (
                  <button key={dir} type="button"
                    className={`rounded-md border px-2 py-1 text-xs transition ${
                      localCond.gap_direction === dir
                        ? "border-accent bg-accent/15 text-accent"
                        : "border-surface-border text-ink-muted hover:border-accent/40 hover:text-ink-secondary"
                    }`}
                    onClick={() => setLocalCond({ ...localCond, gap_direction: dir })}>
                    {dir}
                  </button>
                ))}
              </div>
            </div>
          </Accordion>

          <Accordion title="G · Estacionalidad">
            <CheckboxGroup<DayOfWeek>
              label="Día de la semana"
              values={["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]}
              selected={localCond.days_of_week ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, days_of_week: toggleArr(localCond.days_of_week, v) })} />
            <CheckboxGroup<Quarter>
              label="Trimestre"
              values={["q1", "q2", "q3", "q4"]}
              selected={localCond.quarters ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, quarters: toggleArr(localCond.quarters, v) })} />
            <CheckboxGroup<MonthOfYear>
              label="Mes"
              values={["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]}
              selected={localCond.months ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, months: toggleArr(localCond.months, v) })} />
            <CheckboxGroup<EarningsSeason>
              label="Temporada de earnings"
              values={["peak", "off_season"]}
              selected={localCond.earnings_seasons ?? []}
              onToggle={(v) => setLocalCond({ ...localCond, earnings_seasons: toggleArr(localCond.earnings_seasons, v) })} />
          </Accordion>

          <button
            type="button"
            className="btn-primary w-full mt-2"
            disabled={Boolean(symbolError) || isLoadingConditioningCount}
            onClick={async () => {
              setConditioning(localCond);
              await runConditioningCount();
            }}
          >
            {isLoadingConditioningCount ? "Aplicando..." : "Aplicar Condicionamiento"}
          </button>

          <button type="button" className="btn-ghost w-full mt-1"
            onClick={() => { resetConditioning(); setLocalCond({ gap_direction: "any" }); }}>
            Limpiar filtros
          </button>
        </Accordion>

        {/* ════════════════ PASO 4 · ANÁLISIS PROBABILÍSTICO ═════════════════ */}
        <Accordion title="Análisis Probabilístico">

          {/* ── Price Action ─────────────────────────────────────────────── */}
          <p className="text-xs font-semibold text-ink-primary uppercase tracking-wide">
            Price Action
          </p>

          <div className="flex gap-1">
            {(["holding", "in_event"] as const).map((m) => (
              <button
                key={m}
                type="button"
                className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
                  priceActionMode === m
                    ? "bg-accent text-white"
                    : "bg-surface-subtle text-ink-muted hover:bg-surface"
                }`}
                onClick={() => setPriceActionMode(m)}
              >
                {m === "holding" ? "Holding" : "Inside Event"}
              </button>
            ))}
          </div>

          {priceActionMode === "holding" && (
            <div>
              <FieldLabel>Horizonte (períodos)</FieldLabel>
              <p className="mt-0.5 text-xs text-ink-muted">Barras forward P1…Pn · usa el timeframe del análisis</p>
              <div className="mt-2 flex items-center gap-2">
                <input type="range" min={1} max={60} value={nPeriods}
                  onChange={(e) => setNPeriods(Number(e.target.value))}
                  className="w-full accent-accent" />
                <input type="number" min={1} max={60} value={nPeriods}
                  onChange={(e) => setNPeriods(Math.max(1, Math.min(60, Number(e.target.value) || 1)))}
                  className="input w-14 text-center" />
              </div>
            </div>
          )}

          {/* ── Probabilístico ───────────────────────────────────────────── */}
          <p className="text-xs font-semibold text-ink-primary uppercase tracking-wide mt-2">
            Probabilístico
          </p>

          <div>
            <FieldLabel>Modelo</FieldLabel>
            <select className="input mt-1" value={model}
              onChange={(e) => setModel(e.target.value as ModelType)}>
              <option value="frequentist">Frequentist</option>
              <option value="bootstrap">Bootstrap</option>
              <option value="kde">KDE</option>
              <option value="bayesian">Bayesian</option>
            </select>
            <p className="mt-1 text-xs text-ink-muted">{modelDescriptions[model]}</p>
          </div>

          <div>
            <FieldLabel>Bins de retorno</FieldLabel>
            <p className="mb-1 text-xs text-ink-muted">Ej: -0.05, -0.01, 0.01, 0.05</p>
            <textarea
              className="input min-h-[72px] font-mono text-xs"
              value={binsDraft}
              onChange={(e) => setBinsDraft(e.target.value)}
            />
            {binsError
              ? <p className="mt-1 text-xs text-status-error">{binsError}</p>
              : <p className="mt-1 text-xs text-ink-muted">
                  {parsedBins.map((v) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`).join(" · ")}
                </p>
            }
            <div className="mt-2 flex gap-2">
              <button type="button" className="btn-primary flex-1" disabled={Boolean(binsError)}
                onClick={() => { if (!binsError) setBins(parsedBins); }}>
                Aplicar bins
              </button>
              <button type="button" className="btn-ghost"
                onClick={() => { setBinsDraft("-0.05, -0.01, 0.01, 0.05"); setBins([-0.05, -0.01, 0.01, 0.05]); }}>
                Reset
              </button>
            </div>
          </div>

          <button
            type="button"
            className="btn-primary w-full"
            disabled={Boolean(symbolError) || Boolean(binsError) || isLoadingMetrics}
            onClick={async () => {
              setConditioning(localCond);
              await runConditionedAnalysis();
            }}
          >
            {isLoadingMetrics ? "Calculando..." : "Calcular Análisis Condicionado"}
          </button>
          {error && !isLoadingMetrics && probabilisticResult === null && (
            <p className="mt-1 text-xs text-status-error">{error}</p>
          )}
        </Accordion>

      </div>
    </aside>
  );
}

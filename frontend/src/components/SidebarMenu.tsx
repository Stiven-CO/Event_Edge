import { ChevronDown, ChevronUp } from "lucide-react";
import { useMemo, useState } from "react";

import type {
  BBPosition, ConditioningParams, DayOfWeek, EarningsSeason,
  EventType, GuidanceDirection, ModelType,
  MonthOfYear, Quarter, RSIZone, TrendDirection, VolRegime,
} from "@/api/types";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useEvents } from "@/hooks/useEvents";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

// ── helpers ──────────────────────────────────────────────────────────────────
const symbolRe = /^[A-Z]{1,5}$/;

const modelDescriptions: Record<ModelType, string> = {
  frequentist: "Frecuencias observadas con intervalo Wilson.",
  bootstrap:   "Re-muestreo robusto con intervalos por percentiles.",
  kde:         "Densidad suavizada para colas continuas.",
  bayesian:    "Posterior Beta con prior de Laplace.",
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

// ── Accordion wrapper ─────────────────────────────────────────────────────────
function Accordion({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
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
        {open ? (
          <ChevronUp className="h-4 w-4 text-ink-muted" />
        ) : (
          <ChevronDown className="h-4 w-4 text-ink-muted" />
        )}
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
function RangeRow({
  label, min, max, value, onChange,
}: {
  label: string; min: number; max: number;
  value: RangeState;
  onChange: (range: RangeState) => void;
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
  label: string; values: T[]; selected: T[];
  onToggle: (v: T) => void;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => onToggle(v)}
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
  // Store selectors
  const symbol       = useEventEdgeStore((s) => s.symbol);
  const companyName  = useEventEdgeStore((s) => s.companyName);
  const eventType    = useEventEdgeStore((s) => s.eventType);
  const gapThreshold = useEventEdgeStore((s) => s.gapThreshold);
  const includeEarningsDays = useEventEdgeStore((s) => s.includeEarningsDays);
  const model        = useEventEdgeStore((s) => s.model);
  const nPeriods     = useEventEdgeStore((s) => s.nPeriods);
  const bins         = useEventEdgeStore((s) => s.bins);
  const periods      = useEventEdgeStore((s) => s.periods);
  const conditioning = useEventEdgeStore((s) => s.conditioning);
  const dateStart    = useEventEdgeStore((s) => s.dateStart);
  const dateEnd      = useEventEdgeStore((s) => s.dateEnd);
  const events       = useEventEdgeStore((s) => s.events);
  const probabilisticResult = useEventEdgeStore((s) => s.probabilisticResult);

  const setSymbol       = useEventEdgeStore((s) => s.setSymbol);
  const setEventType    = useEventEdgeStore((s) => s.setEventType);
  const setGapThreshold = useEventEdgeStore((s) => s.setGapThreshold);
  const setIncludeEarningsDays = useEventEdgeStore((s) => s.setIncludeEarningsDays);
  const clearResults    = useEventEdgeStore((s) => s.clearResults);
  const setModel        = useEventEdgeStore((s) => s.setModel);
  const setNPeriods     = useEventEdgeStore((s) => s.setNPeriods);
  const setBins         = useEventEdgeStore((s) => s.setBins);
  const setPeriods      = useEventEdgeStore((s) => s.setPeriods);
  const setConditioning = useEventEdgeStore((s) => s.setConditioning);
  const resetConditioning = useEventEdgeStore((s) => s.resetConditioning);
  const setDateStart    = useEventEdgeStore((s) => s.setDateStart);
  const setDateEnd      = useEventEdgeStore((s) => s.setDateEnd);

  // Hooks
  const { run: runEvents, isLoadingEvents } = useEvents();
  const { run: runMetrics, isLoadingMetrics } = useAnalysis();

  // Local state
  const [symbolDraft, setSymbolDraft] = useState(symbol);
  const [binsDraft, setBinsDraft] = useState(bins.join(", "));
  const [periodsDraft, setPeriodsDraft] = useState(periods.join(", "));
  const [localCond, setLocalCond] = useState<ConditioningParams>(conditioning);

  const symbolError = useMemo(() => {
    if (symbolDraft.length === 0) return "Ingresa un símbolo";
    return symbolRe.test(symbolDraft) ? null : "Usa solo 1-5 letras mayúsculas";
  }, [symbolDraft]);

  const parsedBins = useMemo(
    () => binsDraft.split(",").map((v) => Number(v.trim())).filter((v) => !Number.isNaN(v)),
    [binsDraft],
  );
  const binsError = validateBins(parsedBins);

  const parsedPeriods = useMemo(
    () => periodsDraft.split(",").map((v) => Number(v.trim())).filter((v) => !Number.isNaN(v)),
    [periodsDraft],
  );
  const periodsError = useMemo(() => {
    if (parsedPeriods.length === 0) return "Ingresa al menos un período";
    if (parsedPeriods.some((v) => !Number.isInteger(v) || v < 1)) return "Enteros ≥ 1 separados por coma";
    return null;
  }, [parsedPeriods]);

  const conditioned = probabilisticResult?.families[0]?.n_total_events ?? 0;
  const total = events.length;

  const epsEnabled = eventType === "earnings";

  function toggleArr<T extends string>(arr: T[] | undefined, v: T): T[] {
    const s = new Set(arr ?? []);
    s.has(v) ? s.delete(v) : s.add(v);
    return Array.from(s);
  }

  return (
    <aside className="flex h-full flex-col overflow-y-auto">
      <div className="space-y-2 p-2">

        {/* ── DATA ── */}
        <Accordion title="Datos" defaultOpen>

          {/* Activo */}
          <div>
            <label className="label">Símbolo</label>
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

          {/* Tipo de evento */}
          <div>
            <label className="label">Tipo de evento</label>
            <select
              className="input mt-1"
              value={eventType}
              onChange={(e) => {
                setEventType(e.target.value as EventType);
                clearResults();
              }}
            >
              <option value="earnings">Earnings</option>
              <option value="gap">Gap</option>
            </select>
          </div>

          {eventType === "gap" && (
            <>
              <div>
                <label className="label">Umbral de detección (%)</label>
                <input
                  type="number"
                  className="input mt-1"
                  min={0.1}
                  max={20}
                  step={0.1}
                  value={Number.isFinite(gapThreshold) ? gapThreshold : 1}
                  onChange={(e) => {
                    const raw = e.target.value;
                    if (raw === "") {
                      setGapThreshold(1);
                      return;
                    }
                    setGapThreshold(Number(raw));
                  }}
                />
              </div>

              <div>
                <label className="label">Incluir earnings days en gaps</label>
                <select
                  className="input mt-1"
                  value={includeEarningsDays === true ? "true" : "none"}
                  onChange={(e) => {
                    const v = e.target.value === "true" ? true : null;
                    setIncludeEarningsDays(v);
                  }}
                >
                  <option value="none">None (excluir earnings days)</option>
                  <option value="true">True (incluir earnings days)</option>
                </select>
              </div>
            </>
          )}

          {/* Rango de fechas */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="label">Desde</label>
              <input type="date" className="input mt-1" value={dateStart}
                onChange={(e) => setDateStart(e.target.value)} />
            </div>
            <div>
              <label className="label">Hasta</label>
              <input type="date" className="input mt-1" value={dateEnd}
                onChange={(e) => setDateEnd(e.target.value)} />
            </div>
          </div>

          {/* Buscar — al fondo del submenu Data */}
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
        </Accordion>

        {/* ── CONDICIONAMIENTO ── */}
        <Accordion title="Condicionamiento">
          <p className="text-xs text-ink-muted">
            {conditioned} condicionados / {total} totales
          </p>

          {/* A — Tendencia */}
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

          {/* B — Momentum */}
          <Accordion title="B · Momentum">
            <RangeRow label="Retorno 5 sesiones %" min={-30} max={30}
              value={{ min: localCond.return_5d_min, max: localCond.return_5d_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "return_5d_min", "return_5d_max", r))} />
            <RangeRow label="Retorno 20 sesiones %" min={-40} max={40}
              value={{ min: localCond.return_20d_min, max: localCond.return_20d_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "return_20d_min", "return_20d_max", r))} />
            <RangeRow label="RSI(14)" min={0} max={100}
              value={{ min: localCond.rsi14_min, max: localCond.rsi14_max }}
              onChange={(r) => setLocalCond(updateRange(localCond, "rsi14_min", "rsi14_max", r))} />
          </Accordion>

          {/* C — Sobreextensión */}
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

          {/* D — Volatilidad */}
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

          {/* E — Fundamental (solo earnings) */}
          {epsEnabled && (
            <Accordion title="E · Fundamental">
              <RangeRow label="EPS surprise %" min={-100} max={100}
                value={{ min: localCond.eps_surprise_pct_min, max: localCond.eps_surprise_pct_max }}
                onChange={(r) => setLocalCond(updateRange(localCond, "eps_surprise_pct_min", "eps_surprise_pct_max", r))} />
              <CheckboxGroup<GuidanceDirection>
                label="Guidance"
                values={["raised", "maintained", "lowered", "not_available"]}
                selected={localCond.guidance_directions ?? []}
                onToggle={(v) => setLocalCond({ ...localCond, guidance_directions: toggleArr(localCond.guidance_directions, v) })} />
            </Accordion>
          )}

          {/* F — Posicionamiento */}
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

          {/* G — Estacionalidad */}
          <Accordion title="G · Estacionalidad">
            <CheckboxGroup<DayOfWeek>
              label="Día de la semana"
              values={["monday", "tuesday", "wednesday", "thursday", "friday"]}
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

          <button type="button" className="btn-ghost w-full mt-1"
            onClick={() => { resetConditioning(); setLocalCond({ gap_direction: "any" }); }}>
            Limpiar filtros
          </button>
        </Accordion>

        {/* ── AJUSTE MÉTRICAS ── */}
        <Accordion title="Ajuste Métricas" defaultOpen>

          {/* Modelo */}
          <div>
            <label className="label">Modelo</label>
            <select className="input mt-1" value={model}
              onChange={(e) => setModel(e.target.value as ModelType)}>
              <option value="frequentist">Frequentist</option>
              <option value="bootstrap">Bootstrap</option>
              <option value="kde">KDE</option>
              <option value="bayesian">Bayesian</option>
            </select>
            <p className="mt-1 text-xs text-ink-muted">{modelDescriptions[model]}</p>
          </div>

          {/* Horizonte */}
          <div>
            <label className="label">Horizonte (sesiones)</label>
            <p className="mt-1 text-xs text-ink-muted">0 = intradía del evento (open P0 → close P0)</p>
            <div className="mt-2 flex items-center gap-2">
              <input type="range" min={0} max={60} value={nPeriods}
                onChange={(e) => setNPeriods(Number(e.target.value))}
                className="w-full accent-accent" />
              <input type="number" min={0} max={60} value={nPeriods}
                onChange={(e) => setNPeriods(Math.max(0, Math.min(60, Number(e.target.value) || 0)))}
                className="input w-16 text-center" />
            </div>
          </div>

          {/* Bins */}
          <div>
            <label className="label">Bins de retorno</label>
            <p className="mb-1 text-xs text-ink-muted">Ej: -0.05, -0.01, 0.01, 0.05</p>
            <textarea
              className="input min-h-[72px] font-mono text-xs"
              value={binsDraft}
              onChange={(e) => setBinsDraft(e.target.value)}
            />
            {binsError ? (
              <p className="mt-1 text-xs text-status-error">{binsError}</p>
            ) : (
              <p className="mt-1 text-xs text-ink-muted">
                {parsedBins.map((v) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}%`).join(" · ")}
              </p>
            )}
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

          {/* Períodos de referencia */}
          <div>
            <label className="label">Períodos (métricas informativas)</label>
            <p className="mb-1 text-xs text-ink-muted">Ej: 1, 3, 5, 10</p>
            <div className="flex gap-2">
              <input
                className="input flex-1 font-mono text-xs"
                value={periodsDraft}
                onChange={(e) => setPeriodsDraft(e.target.value)}
              />
              <button
                type="button"
                className="btn-ghost"
                disabled={Boolean(periodsError)}
                onClick={() => { if (!periodsError) setPeriods(parsedPeriods); }}
              >
                Ok
              </button>
            </div>
            {periodsError
              ? <p className="mt-1 text-xs text-status-error">{periodsError}</p>
              : <p className="mt-1 text-xs text-ink-muted">{parsedPeriods.map((v) => `P${v}`).join(" · ")}</p>
            }
          </div>

          {/* Calcular métricas — aplica conditioning local antes de correr */}
          <button
            type="button"
            className="btn-primary w-full"
            disabled={events.length === 0 || isLoadingMetrics}
            onClick={async () => {
              setConditioning(localCond);
              if (!periodsError && parsedPeriods.length > 0) setPeriods(parsedPeriods);
              await runMetrics();
            }}
          >
            {isLoadingMetrics ? "Calculando..." : "Calcular métricas"}
          </button>
        </Accordion>

      </div>
    </aside>
  );
}

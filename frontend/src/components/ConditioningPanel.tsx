import { useMemo, useState } from "react";

import type { BBPosition, ConditioningParams, GuidanceDirection } from "@/api/types";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useEventEdgeStore } from "@/store/eventEdgeStore";

interface RangeState {
  min?: number;
  max?: number;
}

function updateRange(params: ConditioningParams, keyMin: keyof ConditioningParams, keyMax: keyof ConditioningParams, range: RangeState): ConditioningParams {
  return {
    ...params,
    [keyMin]: range.min,
    [keyMax]: range.max,
  };
}

export function ConditioningPanel() {
  const eventType = useEventEdgeStore((s) => s.eventType);
  const events = useEventEdgeStore((s) => s.events);
  const probabilisticResult = useEventEdgeStore((s) => s.probabilisticResult);
  const conditioning = useEventEdgeStore((s) => s.conditioning);
  const setConditioning = useEventEdgeStore((s) => s.setConditioning);
  const resetConditioning = useEventEdgeStore((s) => s.resetConditioning);
  const { run, isLoadingMetrics } = useAnalysis();

  const [local, setLocal] = useState<ConditioningParams>(conditioning);

  const conditioned = probabilisticResult?.families[0]?.n_total_events ?? 0;
  const total = events.length;

  const bbPositions: BBPosition[] = ["below_lower", "in_lower", "middle", "in_upper", "above_upper"];
  const guidanceDirs: GuidanceDirection[] = ["raised", "maintained", "lowered", "not_available"];

  const epsEnabled = useMemo(() => eventType === "earnings", [eventType]);

  const toggleArrayValue = <T extends string>(arr: T[] | undefined, v: T): T[] => {
    const set = new Set(arr ?? []);
    if (set.has(v)) {
      set.delete(v);
    } else {
      set.add(v);
    }
    return Array.from(set);
  };

  return (
    <section className="panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-display text-lg font-semibold">Condicionamiento</h3>
        <span className="text-xs text-slate">{conditioned} condicionados / {total} totales</span>
      </div>

      <div className="space-y-3 text-sm">
        <RangeRow label="EMA5 %" min={-20} max={20} value={{ min: local.ema5_range_pct_min, max: local.ema5_range_pct_max }} onChange={(r) => setLocal(updateRange(local, "ema5_range_pct_min", "ema5_range_pct_max", r))} />
        <RangeRow label="EMA20 %" min={-20} max={20} value={{ min: local.ema20_range_pct_min, max: local.ema20_range_pct_max }} onChange={(r) => setLocal(updateRange(local, "ema20_range_pct_min", "ema20_range_pct_max", r))} />
        <RangeRow label="Open vs Prev Close %" min={-10} max={10} value={{ min: local.open_vs_prev_close_pct_min, max: local.open_vs_prev_close_pct_max }} onChange={(r) => setLocal(updateRange(local, "open_vs_prev_close_pct_min", "open_vs_prev_close_pct_max", r))} />
        <RangeRow label="Gap %" min={0} max={15} value={{ min: local.gap_pct_min, max: local.gap_pct_max }} onChange={(r) => setLocal(updateRange(local, "gap_pct_min", "gap_pct_max", r))} />

        <div>
          <p className="label mb-1">Gap direction</p>
          <div className="flex gap-2">
            {(["any", "positive", "negative"] as const).map((dir) => (
              <button
                key={dir}
                type="button"
                className={`button-ghost ${local.gap_direction === dir ? "border-sea" : ""}`}
                onClick={() => setLocal({ ...local, gap_direction: dir })}
              >
                {dir}
              </button>
            ))}
          </div>
        </div>

        <CheckboxGroup
          label="BB Position"
          values={bbPositions}
          selected={local.bb_positions ?? []}
          onToggle={(v) => setLocal({ ...local, bb_positions: toggleArrayValue(local.bb_positions, v) })}
        />

        {epsEnabled && (
          <>
            <RangeRow label="EPS surprise %" min={-100} max={100} value={{ min: local.eps_surprise_pct_min, max: local.eps_surprise_pct_max }} onChange={(r) => setLocal(updateRange(local, "eps_surprise_pct_min", "eps_surprise_pct_max", r))} />
            <CheckboxGroup
              label="Guidance"
              values={guidanceDirs}
              selected={local.guidance_directions ?? []}
              onToggle={(v) => setLocal({ ...local, guidance_directions: toggleArrayValue(local.guidance_directions, v) })}
            />
          </>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="button-primary"
          disabled={isLoadingMetrics}
          onClick={async () => {
            setConditioning(local);
            await run();
          }}
        >
          {isLoadingMetrics ? "Aplicando..." : "Aplicar"}
        </button>
        <button
          type="button"
          className="button-ghost"
          onClick={() => {
            resetConditioning();
            setLocal({ gap_direction: "any" });
          }}
        >
          Limpiar filtros
        </button>
      </div>
    </section>
  );
}

function RangeRow({
  label,
  min,
  max,
  value,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  value: RangeState;
  onChange: (range: RangeState) => void;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <div className="grid grid-cols-2 gap-2">
        <input
          className="input"
          type="number"
          placeholder="min"
          min={min}
          max={max}
          value={value.min ?? ""}
          onChange={(e) => onChange({ ...value, min: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
        <input
          className="input"
          type="number"
          placeholder="max"
          min={min}
          max={max}
          value={value.max ?? ""}
          onChange={(e) => onChange({ ...value, max: e.target.value === "" ? undefined : Number(e.target.value) })}
        />
      </div>
    </div>
  );
}

function CheckboxGroup<T extends string>({
  label,
  values,
  selected,
  onToggle,
}: {
  label: string;
  values: T[];
  selected: T[];
  onToggle: (v: T) => void;
}) {
  return (
    <div>
      <p className="label mb-1">{label}</p>
      <div className="flex flex-wrap gap-2">
        {values.map((v) => {
          const active = selected.includes(v);
          return (
            <button
              key={v}
              type="button"
              className={`rounded-full border px-3 py-1 text-xs ${active ? "border-sea bg-sea text-white" : "border-border bg-white text-ink"}`}
              onClick={() => onToggle(v)}
            >
              {v}
            </button>
          );
        })}
      </div>
    </div>
  );
}

import { useCallback } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function useAnalysis() {
  const fetchGlobalMetrics       = useEventEdgeStore((s) => s.fetchGlobalMetrics);
  const fetchConditionedAnalysis = useEventEdgeStore((s) => s.fetchConditionedAnalysis);
  const fetchConditioningCount   = useEventEdgeStore((s) => s.fetchConditioningCount);
  const isLoadingGlobal          = useEventEdgeStore((s) => s.isLoadingGlobal);
  const isLoadingMetrics         = useEventEdgeStore((s) => s.isLoadingMetrics);
  const isLoadingConditioningCount = useEventEdgeStore((s) => s.isLoadingConditioningCount);
  const globalMetrics            = useEventEdgeStore((s) => s.globalMetrics);
  const probabilisticResult      = useEventEdgeStore((s) => s.probabilisticResult);
  const conditioningCount        = useEventEdgeStore((s) => s.conditioningCount);
  const error                    = useEventEdgeStore((s) => s.error);

  const runGlobalMetrics = useCallback(async () => {
    await fetchGlobalMetrics();
  }, [fetchGlobalMetrics]);

  const runConditionedAnalysis = useCallback(async () => {
    await fetchConditionedAnalysis();
  }, [fetchConditionedAnalysis]);

  const runConditioningCount = useCallback(async () => {
    await fetchConditioningCount();
  }, [fetchConditioningCount]);

  return {
    runGlobalMetrics,
    runConditionedAnalysis,
    runConditioningCount,
    globalMetrics,
    probabilisticResult,
    conditioningCount,
    isLoadingGlobal,
    isLoadingMetrics,
    isLoadingConditioningCount,
    error,
  };
}

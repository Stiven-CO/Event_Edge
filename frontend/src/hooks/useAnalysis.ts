import { useCallback } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function useAnalysis() {
  const fetchMetrics = useEventEdgeStore((s) => s.fetchMetrics);
  const isLoadingMetrics = useEventEdgeStore((s) => s.isLoadingMetrics);
  const informativeMetrics = useEventEdgeStore((s) => s.informativeMetrics);
  const probabilisticResult = useEventEdgeStore((s) => s.probabilisticResult);
  const error = useEventEdgeStore((s) => s.error);

  const run = useCallback(async () => {
    await fetchMetrics();
  }, [fetchMetrics]);

  return { run, informativeMetrics, probabilisticResult, isLoadingMetrics, error };
}

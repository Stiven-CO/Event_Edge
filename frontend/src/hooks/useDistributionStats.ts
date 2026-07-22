import { useCallback } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function useDistributionStats() {
  const fetchDistributionStats = useEventEdgeStore((s) => s.fetchDistributionStats);
  const isLoadingDistributionStats = useEventEdgeStore((s) => s.isLoadingDistributionStats);
  const distributionStatsResult = useEventEdgeStore((s) => s.distributionStatsResult);
  const error = useEventEdgeStore((s) => s.error);

  const run = useCallback(async () => {
    await fetchDistributionStats();
  }, [fetchDistributionStats]);

  return { run, distributionStatsResult, isLoadingDistributionStats, error };
}

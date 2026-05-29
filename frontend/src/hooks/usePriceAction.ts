import { useCallback } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function usePriceAction() {
  const fetchPriceAction = useEventEdgeStore((s) => s.fetchPriceAction);
  const isLoadingPriceAction = useEventEdgeStore((s) => s.isLoadingPriceAction);
  const priceActionResult = useEventEdgeStore((s) => s.priceActionResult);
  const error = useEventEdgeStore((s) => s.error);

  const run = useCallback(async () => {
    await fetchPriceAction();
  }, [fetchPriceAction]);

  return { run, priceActionResult, isLoadingPriceAction, error };
}

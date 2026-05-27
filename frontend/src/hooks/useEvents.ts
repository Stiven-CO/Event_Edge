import { useCallback } from "react";

import { useEventEdgeStore } from "@/store/eventEdgeStore";

export function useEvents() {
  const fetchEvents = useEventEdgeStore((s) => s.fetchEvents);
  const isLoadingEvents = useEventEdgeStore((s) => s.isLoadingEvents);
  const events = useEventEdgeStore((s) => s.events);
  const error = useEventEdgeStore((s) => s.error);

  const run = useCallback(async () => {
    await fetchEvents();
  }, [fetchEvents]);

  return { run, events, isLoadingEvents, error };
}

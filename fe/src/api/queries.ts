import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"

// Engagement metadata (status, uptime) changes slowly, so we poll it. Fast,
// per-step topology + activity arrives over SSE (see useEventStream), not here.
const METADATA_POLL_MS = 5000

export function useEngagements() {
  return useQuery({
    queryKey: ["engagements"],
    queryFn: api.listEngagements,
    refetchInterval: METADATA_POLL_MS,
    staleTime: METADATA_POLL_MS,
  })
}

export function useEngagement(id: string | undefined) {
  return useQuery({
    queryKey: ["engagements", id],
    queryFn: () => api.getEngagement(id as string),
    enabled: Boolean(id),
    refetchInterval: METADATA_POLL_MS,
    staleTime: METADATA_POLL_MS,
  })
}

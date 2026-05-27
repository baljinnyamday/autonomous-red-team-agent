import { useQuery } from "@tanstack/react-query"
import { api } from "@/api/client"

export function useEngagements() {
  return useQuery({
    queryKey: ["engagements"],
    queryFn: api.listEngagements,
  })
}

export function useEngagement(id: string | undefined) {
  return useQuery({
    queryKey: ["engagements", id],
    queryFn: () => api.getEngagement(id as string),
    enabled: Boolean(id),
  })
}

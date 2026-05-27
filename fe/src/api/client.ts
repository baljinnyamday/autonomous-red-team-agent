import { USE_MOCKS } from "@/config"
import { mockEngagements } from "@/mocks/data"
import type { Engagement } from "@/types/domain"

/** Thin fetch wrapper. Throws on non-2xx so React Query surfaces errors. */
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    headers: { Accept: "application/json" },
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} on ${path}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  listEngagements: (): Promise<Engagement[]> =>
    USE_MOCKS ? Promise.resolve(mockEngagements) : apiGet("/engagements"),

  getEngagement: (id: string): Promise<Engagement> =>
    USE_MOCKS
      ? Promise.resolve(mockEngagements.find((e) => e.id === id) ?? mockEngagements[0])
      : apiGet(`/engagements/${id}`),
}

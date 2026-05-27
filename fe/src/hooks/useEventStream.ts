import { useEffect, useState } from "react"
import { MOCK_STEP_MS, USE_MOCKS } from "@/config"
import { buildMockTimeline } from "@/mocks/data"
import { applyEvent, initialEngagementState } from "@/state/engagementReducer"
import type { ActivityEvent, EngagementState } from "@/types/domain"

type ConnectionStatus = "connecting" | "open" | "closed"

interface EventStream {
  state: EngagementState
  connection: ConnectionStatus
}

/**
 * Subscribe to engagement updates and expose the reduced state.
 *
 * With USE_MOCKS the hook steps through a scripted timeline of state snapshots
 * (see mocks/data.ts). Otherwise it opens the backend SSE stream and folds each
 * event into state via the reducer. The browser's EventSource auto-reconnects
 * on transient drops; we only manage lifecycle and parsing here.
 */
export function useEventStream(engagementId: string | null): EventStream {
  const [state, setState] = useState<EngagementState>(initialEngagementState)
  const [connection, setConnection] = useState<ConnectionStatus>("closed")

  useEffect(() => {
    if (!engagementId) return

    if (USE_MOCKS) {
      const frames = buildMockTimeline()
      setConnection("open")
      setState(frames[0])
      let i = 0
      const timer = setInterval(() => {
        i += 1
        if (i < frames.length) {
          setState(frames[i])
        } else {
          clearInterval(timer)
        }
      }, MOCK_STEP_MS)
      return () => clearInterval(timer)
    }

    setConnection("connecting")
    setState(initialEngagementState)
    const source = new EventSource(`/api/v1/engagements/${engagementId}/events`)

    source.onopen = () => setConnection("open")

    source.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as ActivityEvent
        setState((prev) => applyEvent(prev, event))
      } catch {
        // Malformed frame — skip it rather than tearing down the stream.
      }
    }

    source.onerror = () => setConnection("connecting") // EventSource retries

    return () => {
      source.close()
      setConnection("closed")
    }
  }, [engagementId])

  return { state, connection }
}

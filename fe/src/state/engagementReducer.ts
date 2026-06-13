import {
  type ActivityEvent,
  type AgentActivity,
  type EngagementState,
  MAX_ACTIVITY_LOG,
  type RedTeamNode,
} from "@/types/domain"

export const initialEngagementState: EngagementState = {
  status: "draft",
  nodes: {},
  edges: {},
  activity: [],
  currentActivity: null,
}

/** Prepend an activity entry, keeping the log capped (immutably). */
function pushActivity(log: AgentActivity[], entry: AgentActivity): AgentActivity[] {
  return [entry, ...log].slice(0, MAX_ACTIVITY_LOG)
}

/**
 * Fold one SSE event into the current state, returning a NEW state object.
 *
 * INVARIANT: never mutate `state` or its members. Always build new objects
 * (spread / map / filter). React re-renders only when references change, so a
 * mutated-in-place node map would silently fail to update the UI.
 *
 * Two cases are implemented as worked examples. Implement the other three.
 */
export function applyEvent(state: EngagementState, event: ActivityEvent): EngagementState {
  switch (event.type) {
    case "engagement.status":
      return { ...state, status: event.status }

    case "agent.step": {
      const entry: AgentActivity = {
        role: event.role,
        action: event.action,
        nodeId: event.nodeId,
        at: event.at,
      }
      return {
        ...state,
        currentActivity: entry,
        activity: pushActivity(state.activity, entry),
      }
    }

    case "node.discovered":
      return { ...state, nodes: { ...state.nodes, [event.node.id]: event.node } }

    case "node.status": {
      const node = state.nodes[event.nodeId]
      if (!node) return state // unknown host — wait for its node.discovered first
      const becameCompromised = event.status === "compromised" && node.status !== "compromised"
      const techniques =
        event.techniques ??
        (event.technique && !node.techniques.includes(event.technique)
          ? [...node.techniques, event.technique]
          : node.techniques)
      const updated: RedTeamNode = {
        ...node,
        status: event.status,
        access: event.access ?? node.access,
        techniques,
        compromisedAt: becameCompromised ? event.at : node.compromisedAt,
      }
      return { ...state, nodes: { ...state.nodes, [event.nodeId]: updated } }
    }

    case "edge.added":
      return { ...state, edges: { ...state.edges, [event.edge.id]: event.edge } }

    default: {
      // Exhaustiveness check: if you add an event type to the union and forget
      // to handle it here, this line becomes a compile error.
      const _exhaustive: never = event
      void _exhaustive
      return state
    }
  }
}

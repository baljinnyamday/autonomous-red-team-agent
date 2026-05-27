import {
  type ActivityEvent,
  type AgentActivity,
  type EngagementState,
  MAX_ACTIVITY_LOG,
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

    // TODO(you): a brand-new host was found. Add it to `state.nodes` keyed by
    // node.id without dropping existing nodes. (Hint: spread the map.)
    case "node.discovered":
      return state

    // TODO(you): an existing node changed. Merge the new status/access/
    // technique onto the existing node. Decide: what if nodeId is unknown —
    // ignore the event, or create a stub node? Also set compromisedAt when
    // status becomes "compromised". Append `technique` to the node's list.
    case "node.status":
      return state

    // TODO(you): record a lateral-movement edge in `state.edges` keyed by
    // edge.id. This is what draws the attack-path graph.
    case "edge.added":
      return state

    default: {
      // Exhaustiveness check: if you add an event type to the union and forget
      // to handle it here, this line becomes a compile error.
      const _exhaustive: never = event
      void _exhaustive
      return state
    }
  }
}

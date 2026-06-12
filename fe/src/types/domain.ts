/**
 * Frontend domain types.
 *
 * These mirror the backend Pydantic models in `be/src/agent_redteam/`
 * (Engagement, agent roles, TargetScope) and additionally define the
 * Node / ActivityEvent contract that the backend will expose over SSE.
 *
 * This file is the source of truth for the FE↔BE API boundary. Keep it
 * in sync with the backend schemas.
 */

// ── Mirrors be/engagements/models.py ────────────────────────────────
export type EngagementStatus = "draft" | "running" | "completed" | "aborted"

export interface Engagement {
  id: string
  operator: string
  targets: string[]
  status: EngagementStatus
  createdAt: string // ISO 8601
}

// ── Mirrors be/agents/roles/* ───────────────────────────────────────
export type AgentRole = "planner" | "executor" | "reporter"

// ── New contract: infiltration state (no BE model yet) ──────────────

/** A single host / VM in the target environment. */
export type NodeStatus =
  | "discovered" // found, not yet touched
  | "scanning" // being enumerated
  | "exploiting" // active exploitation attempt
  | "compromised" // access gained
  | "failed" // exploitation gave up

/** Privilege level obtained on a node. */
export type AccessLevel = "none" | "user" | "root"

export interface RedTeamNode {
  id: string
  hostname: string
  ip: string
  os?: string
  status: NodeStatus
  access: AccessLevel
  techniques: string[] // technique ids applied against this node
  discoveredAt: string
  compromisedAt?: string
}

/** Lateral movement: the agent pivoted from `source` to reach `target`. */
export interface AttackEdge {
  id: string
  source: string // node id pivoted from ("" if external entry point)
  target: string // node id reached
  technique: string
}

/** One human-readable thing an agent did, for the live activity feed. */
export interface AgentActivity {
  role: AgentRole
  action: string // e.g. "Scanning 10.0.0.5 for open services"
  nodeId?: string
  at: string
}

// ── SSE payloads: discriminated union on `type` ─────────────────────
export type ActivityEvent =
  | { type: "agent.step"; role: AgentRole; action: string; nodeId?: string; at: string }
  | { type: "node.discovered"; node: RedTeamNode; at: string }
  | {
      type: "node.status"
      nodeId: string
      status: NodeStatus
      access?: AccessLevel
      technique?: string
      techniques?: string[]
      at: string
    }
  | { type: "edge.added"; edge: AttackEdge; at: string }
  | { type: "engagement.status"; status: EngagementStatus; at: string }

/** Reduced, render-ready state derived from the event stream. */
export interface EngagementState {
  status: EngagementStatus
  nodes: Record<string, RedTeamNode>
  edges: Record<string, AttackEdge>
  activity: AgentActivity[] // most-recent-first, capped
  currentActivity: AgentActivity | null
}

export const MAX_ACTIVITY_LOG = 200

import type {
  AccessLevel,
  AgentRole,
  AttackEdge,
  Engagement,
  EngagementState,
  NodeStatus,
  RedTeamNode,
} from "@/types/domain"

export const mockEngagements: Engagement[] = [
  {
    id: "ENG-2026-001",
    operator: "bd1125",
    targets: ["10.0.0.0/24"],
    status: "running",
    createdAt: "2026-05-27T09:14:00Z",
  },
  {
    id: "ENG-2026-002",
    operator: "bd1125",
    targets: ["192.168.50.0/24"],
    status: "completed",
    createdAt: "2026-05-20T13:02:00Z",
  },
]

function mkNode(
  id: string,
  hostname: string,
  ip: string,
  os: string,
  status: NodeStatus,
  access: AccessLevel = "none",
  techniques: string[] = [],
): RedTeamNode {
  return {
    id,
    hostname,
    ip,
    os,
    status,
    access,
    techniques,
    discoveredAt: new Date().toISOString(),
  }
}

/**
 * Build a sequence of full state snapshots that the mock stream steps through.
 * Each frame is a complete `EngagementState`, so it renders without touching
 * the reducer — which keeps `engagementReducer.ts` free as a learning exercise.
 */
export function buildMockTimeline(): EngagementState[] {
  const frames: EngagementState[] = []
  const state: EngagementState = {
    status: "running",
    nodes: {},
    edges: {},
    activity: [],
    currentActivity: null,
  }

  const step = (role: AgentRole, action: string, nodeId?: string) => {
    const entry = { role, action, nodeId, at: new Date().toISOString() }
    state.currentActivity = entry
    state.activity = [entry, ...state.activity]
  }
  const addNode = (n: RedTeamNode) => {
    state.nodes = { ...state.nodes, [n.id]: n }
  }
  const patchNode = (id: string, patch: Partial<RedTeamNode>) => {
    state.nodes = { ...state.nodes, [id]: { ...state.nodes[id], ...patch } }
  }
  const addEdge = (e: AttackEdge) => {
    state.edges = { ...state.edges, [e.id]: e }
  }
  const snap = () => frames.push(structuredClone(state))

  step("planner", "Planning engagement against 10.0.0.0/24")
  snap()

  addNode(mkNode("n1", "jump-01", "10.0.0.10", "Ubuntu 22.04", "scanning"))
  step("executor", "Scanning 10.0.0.10 for exposed services", "n1")
  snap()

  patchNode("n1", {
    status: "compromised",
    access: "user",
    techniques: ["T1190 Exploit Public-Facing App"],
    compromisedAt: new Date().toISOString(),
  })
  step("executor", "Foothold on jump-01 via vulnerable web app", "n1")
  snap()

  addNode(mkNode("n2", "db-01", "10.0.0.21", "Debian 12", "discovered"))
  addNode(mkNode("n3", "fileshare-01", "10.0.0.30", "Windows Server 2019", "discovered"))
  addEdge({ id: "e1", source: "n1", target: "n2", technique: "T1021 Remote Services" })
  addEdge({ id: "e2", source: "n1", target: "n3", technique: "T1021 Remote Services" })
  step("planner", "Mapped internal hosts from jump-01; selecting targets")
  snap()

  patchNode("n2", { status: "exploiting" })
  step("executor", "Attempting credential reuse against db-01", "n2")
  snap()

  patchNode("n2", {
    status: "compromised",
    access: "root",
    techniques: ["T1078 Valid Accounts", "T1068 Privilege Escalation"],
    compromisedAt: new Date().toISOString(),
  })
  step("executor", "Root on db-01 via privilege escalation", "n2")
  snap()

  patchNode("n3", { status: "exploiting" })
  step("executor", "Relaying captured hash to fileshare-01", "n3")
  snap()

  patchNode("n3", { status: "failed", techniques: ["T1557 Adversary-in-the-Middle"] })
  step("executor", "fileshare-01 rejected relay (SMB signing enforced)", "n3")
  step("reporter", "Drafting findings: 2 hosts compromised, 1 hardened")
  snap()

  return frames
}

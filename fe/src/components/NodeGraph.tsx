import { useMemo } from "react"
import { Background, BackgroundVariant, Controls, type Edge, type Node, ReactFlow } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import type { EngagementState, NodeStatus } from "@/types/domain"

const STATUS_COLOR: Record<NodeStatus, string> = {
  discovered: "#66717f", // muted
  scanning: "#38bdf8", // sky
  exploiting: "#f5a524", // amber
  compromised: "#ef5350", // red
  failed: "#3a4250", // dim
}

/**
 * Lay out discovered nodes on a simple grid and draw lateral-movement edges.
 * A force/dagre layout would be nicer, but a grid keeps this dependency-free
 * and deterministic — easier to reason about in a dissertation write-up.
 */
function toFlow(state: EngagementState): { nodes: Node[]; edges: Edge[] } {
  const ids = Object.keys(state.nodes)
  const cols = Math.ceil(Math.sqrt(ids.length || 1))

  const nodes: Node[] = ids.map((id, i) => {
    const n = state.nodes[id]
    const color = STATUS_COLOR[n.status]
    return {
      id,
      position: { x: (i % cols) * 240, y: Math.floor(i / cols) * 150 },
      data: { label: `${n.hostname}\n${n.ip}` },
      style: {
        borderColor: color,
        borderWidth: 1,
        borderRadius: 4,
        padding: "8px 14px",
        whiteSpace: "pre-line",
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        letterSpacing: "0.02em",
        background: "#0f141c",
        color: "var(--card-foreground)",
        boxShadow: `0 0 0 1px ${color}22, 0 0 16px ${color}33`,
      },
    }
  })

  const edges: Edge[] = Object.values(state.edges).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.technique,
    animated: true,
    style: { stroke: "#5b9dff", strokeWidth: 1.5 },
    labelStyle: { fill: "#8aa9d8", fontFamily: "var(--font-mono)", fontSize: 10 },
    labelBgStyle: { fill: "#0f141c" },
  }))

  return { nodes, edges }
}

export function NodeGraph({ state }: { state: EngagementState }) {
  const { nodes, edges } = useMemo(() => toFlow(state), [state])

  // React Flow's canvas is height:100% and needs a parent with a concrete
  // pixel height. Inside our flex/grid chain that height doesn't reliably
  // propagate, so we anchor an absolutely-positioned fill layer instead.
  return (
    <div className="absolute inset-0">
      {nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center font-mono text-xs text-muted-foreground">
          No nodes discovered yet.
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          proOptions={{ hideAttribution: true }}
          colorMode="dark"
        >
          <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1c2532" />
          <Controls className="!border-border !bg-card" />
        </ReactFlow>
      )}
    </div>
  )
}

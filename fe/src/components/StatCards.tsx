import type { EngagementState } from "@/types/domain"

function summarize(state: EngagementState) {
  const nodes = Object.values(state.nodes)
  return {
    discovered: nodes.length,
    compromised: nodes.filter((n) => n.status === "compromised").length,
    root: nodes.filter((n) => n.access === "root").length,
    hops: Object.keys(state.edges).length,
  }
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="relative overflow-hidden border border-border bg-card px-4 py-3">
      <span
        className={`absolute inset-x-0 top-0 h-px ${accent ? "bg-destructive" : "bg-primary/50"}`}
      />
      <p className="label-mono">{label}</p>
      <p
        className={`mt-2 font-mono text-3xl font-semibold tabular-nums ${accent && value > 0 ? "text-destructive" : "text-foreground"}`}
      >
        {String(value).padStart(2, "0")}
      </p>
    </div>
  )
}

export function StatCards({ state }: { state: EngagementState }) {
  const s = summarize(state)
  return (
    <div className="grid grid-cols-2 gap-px bg-border lg:grid-cols-4">
      <Stat label="Nodes Discovered" value={s.discovered} />
      <Stat label="Compromised" value={s.compromised} accent />
      <Stat label="Root Access" value={s.root} accent />
      <Stat label="Lateral Hops" value={s.hops} />
    </div>
  )
}

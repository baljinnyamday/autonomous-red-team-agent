import { useParams } from "react-router-dom"
import { useEngagement } from "@/api/queries"
import { ActivityFeed } from "@/components/ActivityFeed"
import { NodeGraph } from "@/components/NodeGraph"
import { NodeTable } from "@/components/NodeTable"
import { StatCards } from "@/components/StatCards"
import { Uptime } from "@/components/Uptime"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useEventStream } from "@/hooks/useEventStream"

const CONNECTION_LABEL = {
  connecting: { text: "Connecting", dot: "bg-amber-400" },
  open: { text: "Live", dot: "bg-primary" },
  closed: { text: "Offline", dot: "bg-muted-foreground" },
} as const

function Panel({
  caption,
  children,
  bodyClass = "",
}: {
  caption: string
  children: React.ReactNode
  bodyClass?: string
}) {
  return (
    <section className="flex h-full min-h-0 flex-col border border-border bg-card">
      <header className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="size-1 bg-primary" />
        <span className="label-mono">{caption}</span>
      </header>
      <div className={`min-h-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function Dashboard() {
  const { engagementId } = useParams<{ engagementId: string }>()
  const { state, connection } = useEventStream(engagementId ?? null)
  const { data: engagement } = useEngagement(engagementId)
  const conn = CONNECTION_LABEL[connection]

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      <header className="flex items-end justify-between border-b border-border pb-4">
        <div>
          <p className="label-mono">Active Engagement</p>
          <h1 className="mt-1 font-mono text-2xl font-semibold tracking-tight">{engagementId}</h1>
        </div>
        <div className="flex items-center gap-5">
          <div className="text-right">
            <p className="label-mono">Uptime</p>
            <p className="mt-1">
              <Uptime since={engagement?.createdAt} />
            </p>
          </div>
          <span className="h-8 w-px bg-border" />
          <div className="text-right">
            <p className="label-mono">Status</p>
            <p className="mt-1 font-mono text-sm uppercase tracking-wider text-primary">
              {state.status}
            </p>
          </div>
          <span className="h-8 w-px bg-border" />
          <span className="flex items-center gap-2">
            <span className={`size-2 animate-pulse rounded-full ${conn.dot}`} />
            <span className="label-mono">{conn.text}</span>
          </span>
        </div>
      </header>

      <StatCards state={state} />

      {/* Current agent action — a live "operator console" strip. */}
      <div className="flex items-center gap-3 border border-border bg-card px-4 py-3 font-mono text-sm">
        <span className="text-primary">▸</span>
        {state.currentActivity ? (
          <>
            <span className="uppercase tracking-wider text-primary">
              {state.currentActivity.role}
            </span>
            <span className="text-muted-foreground">::</span>
            <span className="text-foreground">{state.currentActivity.action}</span>
            <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-primary align-middle" />
          </>
        ) : (
          <span className="text-muted-foreground">Awaiting agent step…</span>
        )}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <Tabs defaultValue="graph" className="flex min-h-0 flex-col gap-3">
          <TabsList className="self-start bg-card font-mono">
            <TabsTrigger value="graph">Attack Path</TabsTrigger>
            <TabsTrigger value="table">Nodes</TabsTrigger>
          </TabsList>
          <TabsContent value="graph" className="min-h-0 flex-1">
            <Panel caption="Lateral Movement Graph" bodyClass="relative overflow-hidden">
              <NodeGraph state={state} />
            </Panel>
          </TabsContent>
          <TabsContent value="table" className="min-h-0 flex-1">
            <Panel caption="Discovered Nodes" bodyClass="overflow-auto">
              <NodeTable state={state} />
            </Panel>
          </TabsContent>
        </Tabs>

        <Panel caption="Agent Activity" bodyClass="overflow-hidden">
          <ActivityFeed activity={state.activity} />
        </Panel>
      </div>
    </div>
  )
}

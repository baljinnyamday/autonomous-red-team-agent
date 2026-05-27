import { Link } from "react-router-dom"
import { useEngagements } from "@/api/queries"
import type { EngagementStatus } from "@/types/domain"

const STATUS_DOT: Record<EngagementStatus, string> = {
  draft: "bg-muted-foreground",
  running: "bg-primary",
  completed: "bg-emerald-400",
  aborted: "bg-destructive",
}

export function EngagementList() {
  const { data, isLoading, error } = useEngagements()

  return (
    <div className="p-6">
      <div className="mb-6 border-b border-border pb-4">
        <p className="label-mono">Operations</p>
        <h1 className="mt-1 font-mono text-2xl font-semibold tracking-tight">Engagements</h1>
      </div>

      {isLoading && <p className="font-mono text-xs text-muted-foreground">Loading…</p>}
      {error && (
        <p className="font-mono text-xs text-destructive">
          Could not load engagements ({(error as Error).message}). Is the backend running?
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {data?.map((e) => (
          <Link
            key={e.id}
            to={`/engagements/${e.id}`}
            className="group relative overflow-hidden border border-border bg-card p-4 transition-colors hover:border-primary/60"
          >
            <span className="absolute inset-x-0 top-0 h-px bg-primary/0 transition-colors group-hover:bg-primary" />
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-semibold tracking-tight">{e.id}</span>
              <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <span className={`size-1.5 rounded-full ${STATUS_DOT[e.status]}`} />
                {e.status}
              </span>
            </div>
            <dl className="mt-4 space-y-1.5 font-mono text-xs text-muted-foreground">
              <div className="flex justify-between">
                <dt className="uppercase tracking-wider">Operator</dt>
                <dd className="text-foreground/80">{e.operator}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="uppercase tracking-wider">Targets</dt>
                <dd className="text-foreground/80">{e.targets.join(", ")}</dd>
              </div>
            </dl>
          </Link>
        ))}
      </div>
    </div>
  )
}

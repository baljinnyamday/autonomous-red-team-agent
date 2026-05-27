import { ScrollArea } from "@/components/ui/scroll-area"
import type { AgentActivity, AgentRole } from "@/types/domain"

const ROLE_COLOR: Record<AgentRole, string> = {
  planner: "text-sky-400",
  executor: "text-amber-400",
  reporter: "text-emerald-400",
}

export function ActivityFeed({ activity }: { activity: AgentActivity[] }) {
  if (activity.length === 0) {
    return (
      <p className="p-4 font-mono text-xs text-muted-foreground">Waiting for agent activity…</p>
    )
  }

  return (
    <ScrollArea className="h-full">
      <ol className="font-mono text-xs">
        {activity.map((a, i) => (
          <li
            key={`${a.at}-${i}`}
            className="flex gap-3 border-b border-border/50 px-3 py-2 last:border-0 hover:bg-accent/40"
          >
            <time className="shrink-0 tabular-nums text-muted-foreground">
              {new Date(a.at).toLocaleTimeString("en-GB", { hour12: false })}
            </time>
            <div className="min-w-0">
              <span className={`uppercase tracking-wider ${ROLE_COLOR[a.role]}`}>{a.role}</span>
              <p className="mt-0.5 leading-snug text-foreground/90">{a.action}</p>
            </div>
          </li>
        ))}
      </ol>
    </ScrollArea>
  )
}

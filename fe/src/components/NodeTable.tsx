import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { AccessLevel, EngagementState, NodeStatus } from "@/types/domain"

const STATUS_DOT: Record<NodeStatus, string> = {
  discovered: "bg-muted-foreground",
  scanning: "bg-sky-400",
  exploiting: "bg-amber-400",
  compromised: "bg-destructive",
  failed: "bg-zinc-600",
}

const ACCESS_COLOR: Record<AccessLevel, string> = {
  none: "text-muted-foreground",
  user: "text-amber-400",
  root: "text-destructive",
}

function HeadCell({ children }: { children: React.ReactNode }) {
  return <TableHead className="label-mono h-9">{children}</TableHead>
}

export function NodeTable({ state }: { state: EngagementState }) {
  const nodes = Object.values(state.nodes)

  if (nodes.length === 0) {
    return <p className="p-6 font-mono text-xs text-muted-foreground">No nodes discovered yet.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="border-border hover:bg-transparent">
          <HeadCell>Hostname</HeadCell>
          <HeadCell>Address</HeadCell>
          <HeadCell>OS</HeadCell>
          <HeadCell>Status</HeadCell>
          <HeadCell>Access</HeadCell>
          <HeadCell>Techniques</HeadCell>
        </TableRow>
      </TableHeader>
      <TableBody>
        {nodes.map((n) => (
          <TableRow key={n.id} className="border-border">
            <TableCell className="font-medium">{n.hostname}</TableCell>
            <TableCell className="font-mono text-xs text-muted-foreground">{n.ip}</TableCell>
            <TableCell className="text-xs text-muted-foreground">{n.os ?? "—"}</TableCell>
            <TableCell>
              <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider">
                <span className={`size-1.5 rounded-full ${STATUS_DOT[n.status]}`} />
                {n.status}
              </span>
            </TableCell>
            <TableCell
              className={`font-mono text-xs uppercase tracking-wider ${ACCESS_COLOR[n.access]}`}
            >
              {n.access}
            </TableCell>
            <TableCell className="font-mono text-[11px] text-muted-foreground">
              {n.techniques.join(" · ") || "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

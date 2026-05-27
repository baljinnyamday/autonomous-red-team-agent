import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { Link, Navigate, Route, Routes } from "react-router-dom"
import { Dashboard } from "@/pages/Dashboard"
import { EngagementList } from "@/pages/EngagementList"

const queryClient = new QueryClient()

function Logomark() {
  return (
    <span className="grid size-7 place-items-center border border-primary/40 bg-primary/10">
      <span className="size-2 rotate-45 bg-primary shadow-[0_0_10px_var(--color-primary)]" />
    </span>
  )
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen flex-col">
      <nav className="flex items-center justify-between border-b border-border bg-card/60 px-6 py-3 backdrop-blur-sm">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-3">
            <Logomark />
            <span className="font-mono text-sm font-semibold uppercase tracking-[0.22em]">
              RedTeam<span className="text-primary"> Console</span>
            </span>
          </Link>
          <span className="h-4 w-px bg-border" />
          <Link
            to="/"
            className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground"
          >
            Engagements
          </Link>
        </div>
        <div className="flex items-center gap-2">
          <span className="size-1.5 animate-pulse rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]" />
          <span className="label-mono">System Online</span>
        </div>
      </nav>
      <main className="min-h-0 flex-1 overflow-auto">{children}</main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell>
        <Routes>
          <Route path="/" element={<EngagementList />} />
          <Route path="/engagements/:engagementId" element={<Dashboard />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppShell>
    </QueryClientProvider>
  )
}

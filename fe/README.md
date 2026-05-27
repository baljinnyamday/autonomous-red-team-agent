# RedTeam Console (`fe`)

Frontend for the agentic red-teaming framework. A Vite + React + TypeScript SPA
that watches an engagement live: nodes/VMs discovered and compromised, the
attack path between them, and what each agent is doing right now.

## Why Vite (not Next.js)

This is an authenticated internal dashboard — no SEO, no public pages, so SSR
buys nothing. The data is a live event stream (SSE), which is a client-side
concern. A lean SPA over a documented API is also easier to defend in the
dissertation than Next.js's hybrid rendering model.

## Stack

| Concern        | Choice                          |
| -------------- | ------------------------------- |
| Build/dev      | Vite                            |
| UI             | React + TypeScript              |
| Styling        | Tailwind v4 + shadcn/ui         |
| Routing        | React Router                    |
| Server state   | TanStack Query (REST)           |
| Live updates   | SSE via native `EventSource`    |
| Graph viz      | React Flow (`@xyflow/react`)    |

## Run

```bash
pnpm install
pnpm dev          # http://localhost:5173, proxies /api -> http://localhost:8000
pnpm build        # typecheck + production build
```

The dev server proxies `/api` to the backend (`vite.config.ts`), so the browser
sees one origin — no CORS, cookies just work.

## Architecture

```
src/
├── types/domain.ts             # FE<->BE contract: mirrors BE Pydantic models +
│                               #   defines Node / ActivityEvent (SSE payloads)
├── state/engagementReducer.ts  # folds SSE events -> render-ready state (immutable)
├── hooks/useEventStream.ts     # EventSource lifecycle + dispatch to the reducer
├── api/                        # REST client + TanStack Query hooks
├── components/                 # NodeGraph, NodeTable, ActivityFeed, StatCards
└── pages/                      # EngagementList (landing), Dashboard (live view)
```

The reducer is the core: every SSE frame is folded into one `EngagementState`
object that all components render from. State only changes by reference, so the
UI updates predictably.

## API contract the backend must expose

These endpoints do not exist on the backend yet — `src/types/domain.ts` defines
the shape the FE expects, and `be/docs/architecture.md` already reserves
`api/v1/` for FastAPI routes.

### REST

- `GET /api/v1/engagements` -> `Engagement[]`
- `GET /api/v1/engagements/{id}` -> `Engagement`

### SSE

- `GET /api/v1/engagements/{id}/events` -> `text/event-stream`

Each frame is a JSON `ActivityEvent` (discriminated union on `type`):

| `type`               | Meaning                                    |
| -------------------- | ------------------------------------------ |
| `engagement.status`  | Engagement moved draft->running->…         |
| `agent.step`         | An agent (planner/executor/reporter) acted |
| `node.discovered`    | A new host/VM was found                    |
| `node.status`        | A node changed status / access / technique |
| `edge.added`         | Lateral movement: pivot from A -> B        |

See the `ActivityEvent` union in `src/types/domain.ts` for exact fields.

> Authorized use only. This console visualizes engagements run under the
> backend's scope guardrails (see `be/docs/authorized-use.md`).

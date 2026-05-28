# Architecture

## Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| CLI / API | `cli/`, `api/` | Operator and HTTP boundaries |
| Orchestration | `orchestration/` | Multi-agent workflows and guardrail enforcement |
| Agents | `agents/` | Single-role LLM agents and tools |
| Domain | `targets/`, `techniques/` | Core models and registries |
| Guardrails | `guardrails/` | Authorization enforcement |
| Core | `core/` | Config, logging, shared errors |

## Default workflow

1. Operator enables `AUTHORIZED_ENGAGEMENT` and starts a run for an engagement.
2. `EngagementWorkflow` validates guardrails, then runs planner → executor → reporter.
3. The reporter returns a structured run summary for review.

## Extension points

- Add LLM providers under a future `llm/` package.
- Register techniques in `techniques/registry.py`.
- Expose REST via FastAPI in `api/v1/` using existing route modules.

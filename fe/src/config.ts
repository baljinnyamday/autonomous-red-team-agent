/**
 * Use in-browser mock data instead of the live backend.
 *
 * The harness now serves these in-process during an autonomous run (default
 * http://localhost:8000, proxied via vite.config.ts), so this is `false`:
 *   GET /api/v1/engagements
 *   GET /api/v1/engagements/{id}
 *   GET /api/v1/engagements/{id}/events   (SSE)
 * Flip back to `true` to demo the dashboard without a running harness.
 */
export const USE_MOCKS = false

/** How fast the mock timeline advances, in milliseconds per step. */
export const MOCK_STEP_MS = 1500

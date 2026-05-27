/**
 * Use in-browser mock data instead of the live backend.
 *
 * The backend's REST + SSE endpoints don't exist yet, so this is `true` to make
 * the dashboard demoable. Flip to `false` once `be/` exposes:
 *   GET /api/v1/engagements
 *   GET /api/v1/engagements/{id}
 *   GET /api/v1/engagements/{id}/events   (SSE)
 */
export const USE_MOCKS = true

/** How fast the mock timeline advances, in milliseconds per step. */
export const MOCK_STEP_MS = 1500

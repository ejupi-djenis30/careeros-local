# Private daily application agenda analysis

Date: 2026-07-23

## Cross-artifact consistency

| Requirement | Implementation boundary | Evidence |
|---|---|---|
| FR-055 projection-only daily queue | `ApplicationAgendaService` derives counts and rows from owned scalar application and next-action projections in one CTE/window statement; it imports no inference capability | SQL capture rejects event, `job_snapshot` and payload reads, `EXPLAIN QUERY PLAN` proves an owned-application index, and an interleaved writer test proves snapshot coherence |
| FR-056 bounded deterministic classification | One UTC instant, a required timezone-aware next-local-midnight instant, a 1–30 day horizon and a 1–200 row limit drive classification and ordering | Fixed-time tests cover every state and omission count; backend validation rejects naive, past and more-than-26-hour boundaries; Chromium proves both 2026 Zurich DST transitions |
| FR-057 independently usable interface | `ApplicationAgenda` loads separately from the board, opens the existing focus-contained dialog through native buttons, and owns its abortable refresh lifecycle | React tests cover labels, description, row navigation, retry, request abortion, focus/visibility refresh and timer cleanup; Chromium covers geometry and functional contrast |
| SC-018 privacy, coherence and omission evidence | Aggregate counts and limit-ranked rows share one statement snapshot; corrupt projections fail closed as 422 rather than 500 | Authenticated API, two-user, incomplete-projection, interleaving, route-validation, query-plan and compact-view tests pass |

## Privacy, truth and model-boundary review

The agenda sends no career data outside the authenticated loopback API and stores no new record.
Its single SQL statement filters on `Application.user_id` and neither joins nor selects application
events, dossiers or job snapshots. The result exposes only role-card scalars and the already
maintained next-action projection. No local-inference readiness dependency or heuristic score is
present, so the queue remains available while the required analysis runtime is absent without being
presented as AI output.

## Storage and workload review

No Alembic migration is required. Task events remain canonical and append-only; the agenda is a
read model over projections transactionally maintained by existing task writers. The classified,
ranked and aggregate CTEs are evaluated through one statement, which returns counts and at most the
caller-bounded item view without materializing the full application set in Python. Invalid partial
projections return a translated validation error rather than silently classifying corrupt state.
The 10,000-application benchmark measured the agenda at 59.446 ms p95 against a 200 ms budget.

## Time semantics and residual constraints

The renderer calculates the next local midnight with the browser calendar and sends that
timezone-aware instant to the API. This follows 23-hour and 25-hour local days correctly instead of
reusing a fixed offset. The backend accepts only a future boundary no more than 26 hours after
`generated_at`; the upcoming horizon remains an exact UTC duration. The agenda refreshes at the
earliest returned future deadline or local midnight, on focus, and when the document becomes
visible. Superseded reads and timers are cancelled. It intentionally surfaces one projected next
action per active application; full task history and calendar alarms remain in Application Detail.

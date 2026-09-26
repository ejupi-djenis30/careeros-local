# Implementation Plan: Campaign Review Decisions via CLI

1. Reuse the existing owner-scoped campaign application resolver and exclusive writable vault
   runtime. Add a bounded `record-review` parser and input validation.
2. Append a typed `campaign_review_v1` payload in an ordinary immutable application note event
   through `ApplicationService.append_event`; keep the application stage unchanged.
3. Project the latest valid review on `campaign show` for pre-submission rows only. Do not turn a
   review label into a readiness or submission claim.
4. Add fictional unit/integration tests for successful writes, revision/owner failures,
   validation, and projection. Document usage and known limitation that `hold` next actions do
   not yet become scheduled agenda tasks.
5. Run focused checks and proportionate repository gates; exercise one real, already-reviewed
   campaign row through the supported CLI only after tests pass and the vault is closed.
6. Extend the owner-scoped read model and CLI/HTTP parameter with an optional review-decision
   filter. Reuse the existing validated projection as the sole decision interpreter; stream
   matching rows so count and pagination remain accurate without materializing an unbounded
   campaign. Preserve the fast SQL path when the filter is absent.
7. Test filter combinations, pagination, invalid values, and later `cleared` reviews with
   fictional data; then read the real campaign without modifying its rows.

No schema migration is needed because application events already provide bounded JSON payloads,
owner scoping, revision compare-and-swap, and immutable history.

Constitution check: the command makes only an explicit local-vault write, does not contact an
employer, does not add model inference or a new agent grant, and keeps facts in an immutable,
owner-scoped timeline. The existing CLI module already exceeds the preferred 300-line size; this
small command follows the existing campaign command boundary for consistency. A follow-up should
extract campaign CLI handlers and their parser wiring into a focused module before further
campaign commands are added. No privacy, authority, portability, or release gate is relaxed.

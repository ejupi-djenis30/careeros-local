# Feature Specification: Campaign Review Decisions via CLI

**Feature branch**: `codex/campaign-live-stage-counts`
**Status**: In progress
**Constitution**: CareerOS Local Constitution 2.0.1; reviewed, no boundary change

## Observed problem

A real campaign import contains applications still marked `preparing` after a live vacancy check
proves that the opening is closed, outside the permitted area, or has a missing mandatory
qualification. The offline CLI can show those applications and record a confirmed submission,
but cannot record the review decision. A private side log is currently needed, so a later agent
could mistake an excluded `preparing` row for a candidate ready to send.

## User outcome

The vault owner can append an owner-scoped, revision-checked review event to one imported
application using `careeros campaign record-review`. Decisions are `hold`, `excluded`, and
`cleared` (`cleared` only removes the review block; it does not certify application readiness).
The command requires a reason, a source URL, a concrete next action for `hold`, and explicit
acknowledgement of the local write. `campaign show` exposes the latest review decision and
evidence separately from the application stage, so `preparing` is never conflated with
`applied`, `excluded`, or ready-to-send.

In real campaigns, `--stage preparing` still returns excluded and held rows. The owner can
additionally filter `campaign show` (and its authenticated HTTP read model) by
`review_decision=none|hold|excluded|cleared`. The filter applies after search, stage, and
priority, but before pagination; `filtered_application_count` reflects that filtered set.
`none` means no valid current review projection, **not** verified eligibility or readiness.
Global `live_stage_counts` remain unaffected by read filters.

## Acceptance scenarios

1. A valid review of an owned `saved` or `preparing` application appends one immutable note
   event and advances its revision, without changing its stage or contacting any employer.
2. `campaign show` displays the latest review decision, reason, source URL, next action, and
   timestamp for a pre-submission application. A later `cleared` review supersedes a prior hold;
   an arbitrary malformed note payload cannot masquerade as a valid campaign review.
3. Missing acknowledgement, stale revision, missing or invalid source, blank reason, missing
   next action on hold, foreign campaign/application, and post-submission stage fail closed with
   stable redacted errors and no write.
4. All tests use fictional campaigns; no profile, CV, token, or real vacancy is committed.
5. Filtering by review decision returns only matching current projections, counts and pages
   them accurately, recognizes later `cleared` decisions, and rejects invalid values. It
   neither mutates the vault nor treats unreviewed rows as eligible.

## Non-goals

- Sending applications or marking them `applied`.
- Automatically deciding fit, interpreting an announcement, or confirming candidate facts.
- A new database table, migration, or change to the external agent grant boundary.
- Automatically moving held/excluded rows out of `preparing` or certifying unreviewed rows.

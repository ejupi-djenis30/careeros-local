# Analysis: Campaign Review Decisions via CLI

## Acceptance evidence

- The command requires explicit local-write acknowledgement, an owned campaign application,
  a valid source URL, bounded reason, and current application revision. It permits only
  `saved` and `preparing`, and appends an ordinary note event through the existing application
  service. It never changes stage or sends data externally.
- The read projection displays the latest well-formed review separately from stage. A newer
  `cleared` event supersedes a hold; a malformed note payload cannot impersonate a review.
- Fictional CLI and campaign API tests cover successful write/read, acknowledgement, invalid
  evidence, stale revision, unavailable link, post-submission rejection, and malformed payload.
- A closed local vault accepted 32 real, source-reviewed decisions via the CLI: 25 exclusions
  and seven holds. A subsequent `campaign show` confirmed the review counts and unchanged
  `preparing` stage. No application was marked `applied` or sent by this feature.
- The optional review-decision filter uses the same validated latest-review projection as the
  ordinary detail read. It applies after search/stage/priority and before pagination; `none`
  means no valid current review, not eligibility. On the primary local campaign, 27
  `preparing` rows separated into 20 `excluded`, six `hold`, and one `none`; the secondary
  campaign retained five `excluded` and two `none`; the single LAPA record was `hold`.
  `live_stage_counts` remained global.

## Validation on 2026-09-25

- Focused tests after the last code change: `53 passed`.
- `ruff check backend tests/backend`: passed.
- `mypy backend --ignore-missing-imports --no-error-summary`: passed.
- `git diff --check`: passed.
- Full backend rerun after the review-filter change: `2810 passed, 17 skipped` in 913.62
  seconds. Pytest emitted a cache-write permission warning, not a test failure. An earlier run
  on the prior revision had one session-slot test failure; the exact test passed alone and the
  new full rerun passed, so the previous failure is resolved for this checkout.
- After the separate vacancy-metadata parser change, another full backend rerun passed:
  `2812 passed, 17 skipped` in 924.96 seconds, with the same cache warning.
- Frontend: `npm test` passed (616 Vitest tests and ancillary contract/license/icon tests),
  `npm run lint` passed, and `npm run build` passed its bundle budget.
- Rust: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and `cargo test`
  passed (28 unit tests).
- On a disposable SQLite vault, `python -m alembic upgrade head`, `downgrade -1`, and
  `upgrade head` passed. The `alembic.exe` launcher first exited 1 without diagnostics;
  module invocation was used for the verified cycle. The temporary validation vault was not
  removed because the environment rejected the cleanup command.

## Constitution and risks

No new network path, model authority, grant scope, database table, migration, or employer contact
was introduced. The CLI still requires the exclusive vault lease. `hold` next actions are text
in the review, not scheduled agenda tasks. The preexisting CLI module exceeds the preferred
module-size boundary; the plan records a decomposition follow-up before further commands.

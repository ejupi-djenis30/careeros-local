# CareerOS Local v1.7.0 release preparation

Date prepared: 2026-07-26

Status: local release-candidate implementation, adversarial review and cross-stack verification
completed. Protected-branch CI, the native package matrix and signed-tag publication remain the
remote release gates.

Cross-artifact results:

- [Agent interface analysis](agent-interface-analysis.md)
- [Agent interface convergence](agent-interface-convergence.md)

## Candidate scope

v1.7.0 adds a narrow agent boundary to the existing local-first product. A source-installed
`careeros` command supports human-readable JSON operations and an MCP stdio server for Codex,
Claude Code and compatible clients. It exposes seven typed read tools and no arbitrary file, SQL,
prompt, network-search or mutation primitive.

The operator authenticates with the existing CareerOS password and selects every allowed scope
explicitly. The bearer token is shown once; only its SHA-256 digest, account binding, scopes,
expiry and revocation state are persisted. MCP releases the desktop lease while idle. Each tool
call reacquires that lease and revalidates the grant, so an expired or revoked token stops working
without a server restart and a concurrent desktop session fails closed with `vault_busy`.

Restore revokes active grants for the restored account. Complete vault erasure removes that
account's grants. Both operations preserve grants owned by another local account.

All seven authoritative version sources report `1.7.0`; the planned stable tag is `v1.7.0`.

## Local verification recorded for this candidate

- Version contract: `python scripts/check_release_versions.py --expected-tag v1.7.0
  --expected-release-date 2026-07-26` reported
  `RELEASE_VERSION=1.7.0 RELEASE_DATE=2026-07-26 SOURCES=7`.
- Backend: 1,410 tests passed with 4 expected skips. The focused automation suite passed 27 tests,
  including official MCP negotiation, successful typed calls for all seven tools, revocation and
  expiry during live stdio sessions, cross-account isolation and redacted startup failures.
- Grant lifecycle: focused deletion and portability tests verify account-scoped removal and
  restore-time revocation.
- Python static checks: Ruff passed for backend, tests, migrations and scripts; mypy passed for
  backend and scripts.
- Database: a fresh SQLite vault upgraded to the new head, downgraded one revision and upgraded
  again successfully.
- Dependency security: both hash-locked Python application and development sets passed
  `pip-audit` with no known vulnerabilities.
- Agent packaging: a clean Python 3.12 environment installed the hash-locked development set,
  installed the project editable with pinned `setuptools==83.0.0` and `wheel==0.47.0`, passed
  `pip check`, and ran `careeros --help`, `careeros-mcp --help` and `careeros mcp --help`.
- Frontend: ESLint passed; 64 files and 334 tests passed; all three license-contract tests and the
  production Vite build passed.
- Rust: formatting and locked Clippy with warnings denied passed. `cargo test --locked` passed all
  17 library tests.
- Hygiene: repository hygiene tests and `git diff --check` passed.

The packaged desktop smoke and complete native matrix remain mandatory in the existing release
workflow. The desktop installer does not add the agent commands to the operating-system `PATH`;
v1.7.0 documents and verifies the source-installed integration rather than claiming otherwise.

## Claims and boundaries

- CareerOS itself does not send MCP results over the network, but the connected agent may send
  authorized results to its provider. Starting MCP therefore requires an explicit disclosure
  acknowledgement.
- Tool DTOs omit dedicated contact records, document bodies, artifact bytes, prompts, tokens and
  storage paths. User-authored labels, company names, locations, resume names and task titles may
  still contain sensitive text.
- Scope annotations help clients display intent; server-side account and scope checks remain the
  authority.
- The CLI and MCP server are read-only in this release. Authorization, grant listing and
  revocation remain password-gated human administration commands outside the MCP tool surface.

## Publication sequence

1. Merge the reviewed candidate through protected `main` with every required check green.
2. Review the read-only native matrix rehearsal on the exact merge commit.
3. Create the verified annotated `v1.7.0` tag with the authorized signing identity.
4. Let the tag workflow build, attest, verify and publish the immutable release; do not alter it
   manually.

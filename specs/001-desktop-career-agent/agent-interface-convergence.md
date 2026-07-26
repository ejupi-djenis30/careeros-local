# Agent interface convergence

## Scope

This review aligns User Story 10, FR-061 through FR-066 and SC-021 with the implemented CLI/MCP
boundary, tests and owner documentation.

## Requirement mapping

| Requirement | Implementation | Verification and documentation |
| --- | --- | --- |
| Fixed local CLI and stdio MCP reads | `backend/automation/cli.py`, `backend/automation/mcp_server.py`, `backend/automation/facade.py` | `tests/backend/automation/test_cli.py`, `test_mcp_server.py`; README agent setup |
| User-bound scoped grant with digest-only persistence | `models.py`, `grants.py`, migration `f2a3b4c5d6e7` | `test_grants.py`; privacy and architecture guides |
| Exclusive lease and fail-closed schema handling | `runtime.py`, existing desktop lifecycle lease | CLI subprocess tests; development guide |
| Bounded typed output and scope enforcement | `schemas.py`, `facade.py`, scope-filtered MCP registration | `test_facade.py`, `test_mcp_server.py`; analysis data-minimization table |
| Explicit external-agent disclosure | MCP startup acknowledgement in `mcp_server.py` | CLI/MCP tests; README and privacy warning |
| Restore revocation and complete-erasure removal | `backend/portability/restore.py`, `backend/career/deletion.py` | focused portability/deletion tests; privacy guide |

## Consistency findings

- The interface is read-only in both transport and service layers. MCP annotations describe this
  to the client, while facade scope checks enforce it independently.
- The desktop and automation paths share the same vault lease. MCP releases it while idle and
  reacquires it with a fresh grant check for every tool call.
- The CLI setup guide uses the locked dependency set plus an editable install. It does not claim
  that a native installer exposes `careeros` on `PATH`.
- CareerOS makes no network request for MCP, but documentation does not call the whole workflow
  local-only once an external agent receives a result.
- Tool lists and examples match the implemented commands, scope names, environment variable and
  disclosure flag.
- Privacy copy distinguishes omitted raw content from the private metadata that application and
  resume projections intentionally return.
- Restore and erasure behavior is reflected in the specification, tasks, privacy model and
  architecture.

## Remaining constraints

Write operations, generic prompts, raw document reads, export, restore, deletion, job acquisition
and arbitrary filesystem or database access remain out of scope. Adding any of them requires a new
user-confirmation, idempotency and rollback design rather than an extension of the current grant by
default.

The source-installed command requires Python 3.12 and a repository checkout. Packaging it as a
native companion would need separate release and path-management work.

## Proportional validation

Run on 2026-07-26:

| Check | Result |
| --- | --- |
| `pytest tests/backend/automation -q` | 20 passed |
| `ruff check backend/automation tests/backend/automation alembic/versions/f2a3b4c5d6e7_add_automation_grants.py` | Passed |
| `mypy backend/automation --follow-imports=skip --ignore-missing-imports --no-error-summary` | Passed |
| `git diff --check` | Passed; unrelated working files retain existing line-ending warnings |

These are focused interface checks, not the complete release gate.

## Result

No unresolved contradiction remains between the feature specification, implementation plan, task
list and owner documentation for the initial read-only CLI/MCP interface.

# CareerOS Local v1.10.0 release preparation evidence

Date prepared: 2026-07-30

Status: release metadata and documentation are being prepared. v1.10.0 has not been tagged or
published. The final protected-branch commit, remote CI, complete read-only rehearsal, candidate
digests, attestations and publication checks are all pending.

This document is a gate checklist, not proof that the release already exists. Run identifiers,
commit ids, tree ids and artifact digests must be added only after GitHub reports them for the
exact merged source.

## Candidate basis

- Planned stable version: `1.10.0`.
- Planned release date: `2026-07-30`.
- Final protected `main` commit: pending.
- Final source tree: pending.
- Verified annotated `v1.10.0` tag: not created.
- Published immutable GitHub Release: not created.

All seven authoritative version sources report `1.10.0`, and `CHANGELOG.md` contains one dated
v1.10.0 section. These metadata checks do not establish that the implementation, release workflow,
or native packages have passed their required gates.

## Candidate scope

v1.10.0 makes the existing read-only Agent Access interface installable without a development
checkout. The Python wheel carries the `careeros` CLI, the `careeros-mcp` stdio server, the
canonical Alembic environment and migration history, and the non-code resources required by the
local automation runtime.

Automation data reads open the existing SQLite vault through URI read-only mode and enforce
`PRAGMA query_only=ON` on every connection. Grant validation and revocation remain isolated from
that read-only data session. The wheel does not add write tools, remote transport, telemetry,
cloud inference, or automatic credential storage.

The minimum v1.10.0 public release contract contains 25 assets. The two additions to the existing
23-asset desktop contract are:

- `careeros_local-1.10.0-py3-none-any.whl`;
- the exact `requirements.lock` paired with that wheel.

Both files must be recorded in `release-manifest.json` and `SHA256SUMS`, covered by GitHub
provenance and uploaded from the same verified candidate. The desktop installers remain separate
from Agent Access and do not add its commands to `PATH`.

## Preparation checks

The following local metadata checks are required in the preparation worktree:

```powershell
python -m scripts.check_release_versions `
  --expected-tag v1.10.0 `
  --expected-release-date 2026-07-30
python -m pytest `
  tests/backend/unit/test_release_versions.py `
  tests/backend/security/test_repository_hygiene.py -q
```

Result: Python 3.12.13 reported
`RELEASE_VERSION=1.10.0 RELEASE_DATE=2026-07-30 SOURCES=7`, and the two targeted test files passed
19 tests. These checks ran in the uncommitted preparation worktree; they do not replace
protected-branch CI on the final commit.

## Required remote evidence

No remote result is asserted yet. Before publication, replace each pending item with a direct
GitHub run link and the exact commit it evaluated:

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Protected-branch CI | Python, frontend, Rust, security, supply-chain and container gates | Pending |
| Code scanning | CodeQL on the exact merge commit | Pending |
| Project Page | Build and validation on the exact merge commit | Pending |
| Agent Access distribution | One wheel built once, then the same bytes smoke-tested on supported Python and operating-system runners | Pending |
| Native rehearsal | All six desktop targets, sidecars, installers and packaged lifecycle checks | Pending |
| Candidate assembly | Exact 25-asset inventory, manifest, global checksums and SBOM validation | Pending |
| Tag policy | Verified annotated tag resolving to the exact default-branch commit | Pending |
| Attestations | Provenance for all 25 assets and the required SBOM bindings | Pending |
| Publication | Contract-bound immutable release confirmed as latest | Pending |

## Claims and boundaries

- CLI and MCP access remains read-only and requires an explicitly scoped, revocable local grant.
- Private vault content, prompts and model output remain local unless a separately configured agent
  client transmits the data it receives.
- `requirements.lock` constrains and hashes dependency downloads; it is not an offline wheelhouse.
- `SHA256SUMS` proves byte integrity, while GitHub provenance associates those bytes with a
  workflow and source ref. Neither mechanism is platform code signing.
- Native installers remain unsigned community builds until real platform signing and notarization
  are configured and verified.
- A local pass, draft release, or partial target run is not sufficient release evidence.

## Publication gates

1. Merge the reviewed implementation and release-contract changes through protected `main`.
2. Record the exact merge commit and source tree in this document.
3. Complete protected-branch CI and all required security workflows on that commit.
4. Run the read-only rehearsal for all six native targets and the Agent Access matrix.
5. Review the exact 25-asset candidate, wheel metadata, lock pairing, checksums, SBOMs and smoke
   results.
6. Update this document with truthful run links, test totals, digests and any accepted limitations.
7. Create the verified annotated `v1.10.0` tag only after every prior gate passes.
8. Let the tag workflow rebuild, attest, verify and publish the immutable release.

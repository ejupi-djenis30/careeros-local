# CareerOS Local v1.10.0 release evidence

Date verified: 2026-07-30

Status: published. GitHub reports v1.10.0 as the repository's latest immutable release. Its
annotated SSH-signed tag resolves directly to the protected `main` commit recorded below. The
read-only rehearsal and tag-triggered release workflow both completed successfully against that
same source.

## Candidate basis

- Stable version: `1.10.0`.
- Release date: `2026-07-30`.
- Final protected `main` commit:
  [`6fa804e7925e1d1420bd3f3f56e10cee0d3ea637`](https://github.com/ejupi-djenis30/careeros-local/commit/6fa804e7925e1d1420bd3f3f56e10cee0d3ea637).
- Final source tree: `fd98fb28ffe8eed6c5c69b37c8329f54d97a5eae`.
- Annotated tag object: `2405d3aa0ea752b4bf2a18c55e605ae83610212b`; GitHub reports its
  SSH signature as verified with reason `valid`.
- Published release:
  [`v1.10.0`](https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.10.0),
  final, immutable and returned by the latest-release endpoint.

All seven authoritative version sources report `1.10.0`, and `CHANGELOG.md` contains one dated
v1.10.0 section. The remote evidence below establishes the implementation, packaging and
publication results separately from those metadata checks.

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

Preparation result: Python 3.12.13 reported
`RELEASE_VERSION=1.10.0 RELEASE_DATE=2026-07-30 SOURCES=7`, and the two targeted test files passed
19 tests. Protected-branch CI subsequently repeated the complete project gates against the exact
merged commit.

## Remote evidence

| Gate | Evidence | Result |
| --- | --- | --- |
| Protected-branch CI | [CI run 30559882180](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30559882180) on `6fa804e` | Passed |
| Code scanning | [CodeQL run 30559879224](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30559879224) on `6fa804e` | Passed |
| Project Page | [Page run 30559881638](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30559881638) on `6fa804e` | Passed |
| Read-only rehearsal | [Desktop run 30567465216](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30567465216): six native targets plus Linux, macOS and Windows wheel smoke tests on Python 3.12 and 3.13 | Passed; publisher skipped |
| Tagged build | [Desktop run 30569612855](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30569612855) rebuilt all native and Agent Access targets from the verified tag | Passed |
| Candidate assembly | The tagged run accepted exactly 25 non-empty assets, their manifest, global checksums and three CycloneDX SBOMs | Passed |
| Tag policy | Annotated tag resolves directly to `6fa804e`; Git and GitHub both report the authorized SSH signature as valid | Passed |
| Attestations | GitHub's attestations API returns provenance for all 25 assets; every asset has at least two attestations and native packages have five | Passed |
| Publication | The durable publisher re-read remote names, sizes and digests, then confirmed the release immutable and latest | Passed |

## Selected public digests

These values come from GitHub's immutable release-asset records:

| Asset | SHA-256 |
| --- | --- |
| `careeros_local-1.10.0-py3-none-any.whl` | `82968c297b502b903dd966e49e5de9c77a6bcb6baf51b2fcaf3322f2efe1f536` |
| `requirements.lock` | `68ed3d0d0dc96e24b2b02c5f6b4da8fdc4e53f80ca5d48672138ae1a13a0a03f` |
| `release-manifest.json` | `2b083973ca037e708df6f1738193f6d0cf8c99d8364a8d1f59aa7877ae21f20a` |
| `SHA256SUMS` | `a4587efc66f799893186eb8e8541392082033ef06de024b73300e98e604f9de7` |
| `supply-chain-evidence.tar.gz` | `ab903284b5e54b778632fed6782fec8102a3e2a7b7693c4a58bec36abfb7c934` |

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

## Completed publication record

The implementation and release-contract changes were merged through protected `main`. The exact
merge source passed CI, security analysis and the Page build. The read-only rehearsal then built
all six native targets and tested one wheel across six OS/Python combinations without publishing.
Only after those gates passed was the verified annotated tag created. The tag workflow rebuilt the
candidate, verified every byte and attestation, and published the immutable release.

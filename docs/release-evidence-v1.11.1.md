# CareerOS Local v1.11.1 release evidence

Date verified: 2026-08-01

Status: published. GitHub reports v1.11.1 as the repository's latest immutable release. Its
annotated SSH-signed tag resolves directly to the protected `main` commit recorded below. The
read-only rehearsal and the tag-triggered release workflow both completed successfully against
that same source.

## Candidate basis

- Stable version: `1.11.1` across all seven authoritative version sources.
- Release date: `2026-08-01` in the changelog and release workflow.
- Final protected `main` commit:
  [`96ca0f886a389781127cb65db9d896a154d0331e`](https://github.com/ejupi-djenis30/careeros-local/commit/96ca0f886a389781127cb65db9d896a154d0331e).
- Final source tree: `21b34189d76472fbbcf7cb4f254124a4ad06daf2`.
- Annotated tag object: `7adad19931378bc774e2f300cad1e857d5603328`; Git and GitHub
  both report its authorized SSH signature as valid.
- Published release:
  [`v1.11.1`](https://github.com/ejupi-djenis30/careeros-local/releases/tag/v1.11.1),
  release ID `363615016`, final, immutable and returned by the latest-release endpoint.
- Public contract: schema 4 with exactly 26 non-empty assets. The release was published at
  `2026-08-01T20:01:47Z`.

The release API identifies the exact source commit, tag and curated contract marker. Its asset
records are collision-free under case folding and report `uploaded` state, positive size and a
SHA-256 digest for all 26 names.

## Release scope

v1.11.1 is the first published 1.11 distribution. It carries restart-durable vault reset,
restore and erasure recovery; bounded private-file publication journals; rotating authentication
session families; strict local-runtime and provider response envelopes; packaged migration
recovery; content-free diagnostics; and expanded forced-colors, keyboard, responsive and browser
acceptance coverage.

It also corrects the concurrent content-addressed publication race that stopped v1.11.0. Winner
validation tolerates only the POSIX `ctime` transition caused by removing a publisher's private
hard-link alias. The descriptor, inode, regular-file type, exact size, modification time and bytes
must still match. Recovery metadata retains its stricter single-link and `ctime` checks.

The schema-4 contract adds first-class `LICENSE` and `THIRD_PARTY_NOTICES.txt` assets to the
previous desktop and Agent Access inventory. The Python wheel, exact `requirements.lock`, three
CycloneDX SBOMs, per-target checksums, global `SHA256SUMS`, manifest and supply-chain evidence are
all bound to the same tagged build.

## Superseded unpublished candidate

The authorized `v1.11.0` tag remains an immutable source tag, but it has no GitHub Release or
public assets. Its tag workflow was cancelled before assembly, attestation and publisher
execution after protected-branch CI exposed the publication race. The complete audit trail is
preserved in the [v1.11.0 unpublished candidate record](release-evidence-v1.11.0.md). The tag was
not moved, deleted or reused.

## Local verification

The atomic-publication correction passed 72 focused tests with three expected skips, a 16,000-write
contention stress run and the complete Windows backend suite: 2,184 tests passed, 17 skipped and
81.62% coverage. Release preparation also passed version/date coordination, exact third-party
notice regeneration and verification, release/security/storage tests, Ruff, formatting, mypy,
locked Cargo metadata, Node 24.18 distribution checks and icon validation.

After publication, all 26 public assets were downloaded into a fresh audit directory. The audit
read 697,136,444 bytes and established all of the following without modifying the release:

- each downloaded size and SHA-256 matched the corresponding immutable API asset record;
- `SHA256SUMS` contained exactly the other 25 names and matched every downloaded byte;
- the release-body contract marker matched `release-manifest.json` and `SHA256SUMS`;
- the complete release validator accepted schema 4, all six target inventories, the Agent Access
  wheel and lock, three SBOMs, notices and the deterministic evidence archive;
- the attestations API returned the exact v1.11.1 release, provenance and SBOM subjects for every
  public digest.

## Remote evidence

| Gate | Evidence | Result |
| --- | --- | --- |
| Atomic correction | [PR 71](https://github.com/ejupi-djenis30/careeros-local/pull/71) merged the bounded POSIX `ctime` correction only after the protected checks passed | Passed |
| Release preparation | [PR 72](https://github.com/ejupi-djenis30/careeros-local/pull/72) coordinated v1.11.1 metadata, notices and release records | Passed |
| Protected-branch CI | [CI run 30713994892](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30713994892) on `96ca0f8` | Passed |
| Code scanning | [CodeQL run 30713994708](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30713994708) on `96ca0f8` | Passed |
| Project Page | [Page run 30713994866](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30713994866) on `96ca0f8` | Passed |
| Dependency graph | [Dependency submission run 30713997042](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30713997042) on `96ca0f8` | Passed |
| Read-only rehearsal | [Desktop run 30714009679](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30714009679): six native targets plus Linux, macOS and Windows wheel smoke tests on Python 3.12 and 3.13 | Passed; publisher skipped |
| Tagged build | [Desktop run 30715148178](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30715148178) rebuilt all native and Agent Access targets from the verified tag | Passed |
| Candidate assembly | The tagged run accepted exactly 26 non-empty assets, their schema-4 manifest, global checksums, notices and three CycloneDX SBOMs | Passed |
| Tag policy | The annotated tag resolves directly to `96ca0f8`; Git and GitHub report the authorized SSH signature as valid | Passed |
| Attestations | GitHub returns 83 v1.11.1-specific attestations across 26 assets: release plus workflow provenance for every asset, three exact SBOM bindings for each of ten native packages and the exact backend SBOM for the wheel | Passed |
| Publication | The durable publisher re-read names, sizes and digests, published release ID `363615016`, then confirmed it immutable and latest | Passed |

The cryptographic verification constrained the signer to
`.github/workflows/desktop-release.yml`, source digest `96ca0f8`, source ref
`refs/tags/v1.11.1`, the GitHub Actions OIDC issuer and GitHub-hosted runners. The signed
multi-subject provenance covers the 25 entries in `SHA256SUMS`; a separate signed provenance
statement covers `SHA256SUMS` itself. The three signed native SBOM predicates cover the same ten
package digests, and the wheel's signed predicate matches the published backend SBOM.

## Selected public digests

These values come from GitHub's immutable release-asset records and were independently matched to
the downloaded bytes:

| Asset | SHA-256 |
| --- | --- |
| `careeros_local-1.11.1-py3-none-any.whl` | `fbde4157bda6e73886b791ce7f12e2734b2ac387122ec95d9eac5e87f898eb6d` |
| `requirements.lock` | `68ed3d0d0dc96e24b2b02c5f6b4da8fdc4e53f80ca5d48672138ae1a13a0a03f` |
| `LICENSE` | `0506cd12584bb6180ea9eb17c4f212d25d8aaf3070f0dcaadb12b4ac14b60ce0` |
| `THIRD_PARTY_NOTICES.txt` | `471e83e4c17b90b0e4a5deeec69396cb2f5201f61a54defc15b5ab7c8d71f522` |
| `release-manifest.json` | `daedb91efdfbe2a8ba6dc39b82a11c30f4d2d37fad8be6de01ab2ded06a38a5a` |
| `SHA256SUMS` | `d0f010fe6d53749db99a5584b0bd063c5c7cbc1dbcc201c6f62f165e0d2f93c9` |
| `supply-chain-evidence.tar.gz` | `a1413c8a9a67c42ef12179e9b7e8bb00444dd9986e7fbdfcc5821d7a3c647839` |

## Claims and boundaries

- Private career data, prompts, model output and model weights remain local to the user's device.
- Agent Access remains read-only and requires an explicitly scoped, revocable local grant.
- `requirements.lock` constrains and hashes dependency downloads; it is not an offline wheelhouse.
- `SHA256SUMS` proves byte integrity and GitHub provenance binds bytes to a workflow and source
  ref; neither is platform code signing.
- Native installers and the Python wheel remain unsigned community builds until platform signing
  and notarization are configured and independently verified.
- A local pass, source tag, pull-request build, partial target run or draft release is not
  publication evidence.

## Completed publication record

The implementation and release-contract changes were merged through protected `main`. The exact
merge source passed CI, security analysis, dependency submission and the Page build. The read-only
rehearsal then built all six native targets and tested one wheel across six OS/Python combinations
without publishing. Only after those gates passed was the verified annotated tag created. The tag
workflow rebuilt the candidate, verified every byte and attestation and published the immutable
release. The independent post-publication read confirmed that the public state still matches that
contract.

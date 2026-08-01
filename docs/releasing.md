# Releasing

CareerOS releases fail closed. A manual workflow run is a read-only rehearsal: it may build and
retain workflow artifacts, but it cannot request an OIDC token, create attestations, touch a
GitHub Release, or publish anything. Only a stable-version tag push can enter the publisher.

This guide describes the current, post-v1.10 schema-4 contract. It contains 26 public assets,
including first-class third-party notices; the historical immutable
[v1.10.0 release](release-evidence-v1.10.0.md) used its earlier schema-3, 25-asset contract.
Before the next rehearsal, advance all seven version sources and never reuse a published tag.

## Candidate requirements

Before creating a tag:

1. Complete Spec Kit analysis and convergence with no unresolved critical work.
2. Pass the Python, React, Rust, migration, security, performance, and packaged lifecycle gates.
3. Keep all seven version sources on the same stable `MAJOR.MINOR.PATCH` value. Prerelease and
   build metadata are rejected.
4. Update `CHANGELOG.md` with a dated, human-written section for that exact version.
5. Confirm that `LICENSE` is the approved MIT license, run
   `python -m scripts.third_party_notices --check`, and confirm that security exceptions remain
   valid.

Run the metadata and release-contract tests locally:

```powershell
.venv\Scripts\python.exe -m scripts.check_release_versions
.venv\Scripts\python.exe -m pytest tests\backend\release tests\backend\unit\test_release_versions.py -q
```

## Read-only rehearsal

Run **Desktop packages** from `main`. Supply the new `vMAJOR.MINOR.PATCH` planned tag in
`expected_tag`. The workflow builds six native targets on versioned GitHub-hosted runners,
freezes each sidecar with the exact CPython version in `.native-python-version`, smoke-tests each
package, normalizes installer names, and assembles one exact candidate. The contributor and audit
interpreter remains independently pinned in `.python-version`.

The candidate contains 26 public assets:

- 10 native installers with portable, no-space names;
- six target-specific SHA-256 files whose filenames exactly match their downloads;
- the installable Agent Access wheel `careeros_local-<version>-py3-none-any.whl` and the exact
  hash-locked `requirements.lock` used to install its dependency graph;
- three CycloneDX SBOMs;
- one deterministic supply-chain evidence archive;
- the canonical LF `LICENSE`, downloadable as a first-class asset and byte-identical to the
  project notice embedded by Tauri in every native package;
- the deterministic `THIRD_PARTY_NOTICES.txt`, bound to the npm, Python and Cargo locks and
  byte-identical to the web, container, Tauri and release-candidate payload;
- `release-manifest.json`, which binds target, package type, name, size, SHA-256, source commit,
  release date, evidence, SBOMs, the public MIT `LICENSE`, and third-party notices;
- `SHA256SUMS`, which binds every other public asset.

The native smoke gates do not trust package metadata alone. They mount each DMG read-only,
extract each AppImage and DEB, administratively extract each MSI, and install each NSIS package;
every resulting payload must expose both the approved project `LICENSE` and the generated
`THIRD_PARTY_NOTICES.txt` bytes at the canonical Tauri resource root. Missing, changed, duplicate
case-variant, symlink-alias, or dependency-only files stop the run before staging.

The Agent Access candidate is built once on the pinned release toolchain. Its wheel filename,
metadata, Python range, dependency declarations, entry points, MIT license, package resources,
migration history and internal `RECORD` hashes are validated before upload. The same wheel and
`requirements.lock` bytes are then installed and smoke-tested on Linux, macOS and Windows with
Python 3.12 and 3.13; the matrix never rebuilds the candidate.

Each packaged app must also complete an authenticated readiness handshake across the Python
sidecar, Tauri command bridge and a committed React tree. The app writes fresh, run-scoped evidence
only after that contract succeeds; the package harness removes stale evidence before every launch
and verifies the exact payload afterwards. A blank, stalled or prematurely closed WebView therefore
fails the package smoke instead of being mistaken for a working application.

No artifact from a rehearsal is a release. Review the retained `verified-release-assets`,
`native-subject-checksums` and `agent-subject-checksums` workflow artifacts before proceeding.

## Tag and publication

Create and push an annotated, cryptographically signed `vMAJOR.MINOR.PATCH` tag only after the
rehearsal succeeds. GitHub must report every annotated tag object as verified. The tagged commit
must equal the candidate source and remain contained in the repository's current default branch.

The tag workflow re-runs every build and check. Its final job then:

1. verifies the tag and default-branch policy before requesting attestations;
2. re-hashes the exact 26-file candidate;
3. creates SLSA provenance for all 26 assets;
4. binds each of the three CycloneDX SBOMs to all 10 native installers and the rooted backend SBOM
   to the Agent Access wheel;
5. verifies every attestation against the tag commit, tag ref, workflow identity, GitHub OIDC
   issuer, and GitHub-hosted runner policy;
6. creates or resumes one contract-bound draft without deleting or overwriting remote assets;
7. publishes only when release identity and all remote name/size/digest records match;
8. confirms the published release is immutable and is the repository's latest release.

Every tag-triggered run shares one publication concurrency group, with cancellation disabled for
the running tag. This prevents overlapping publication attempts. GitHub retains at most one
pending run in a concurrency group, so confirm that every intended tag workflow completed and
manually re-run any pending execution GitHub superseded. Immediately before changing a draft into
a public release, the publisher reads every release page again and refuses to promote an older
version if another tag has advanced the published sequence.

Lost API responses are reconciled by reading GitHub again. A matching completed operation is
accepted, an unapplied operation can be retried on the next run, and any duplicate, stale,
foreign, or mismatched state stops publication. An already exact immutable latest release is a
write-free no-op.

## Download verification

The global checksum command requires one directory containing the complete published set:
`SHA256SUMS` plus all other 25 assets. On GNU/Linux or in Git Bash, run:

```bash
sha256sum --check SHA256SUMS
```

If you downloaded only one Windows installer and `SHA256SUMS`, compare that exact entry with
PowerShell's native `Get-FileHash` before verifying provenance:

```powershell
$releaseVersion = "<version>"
$asset = "CareerOS-Local_${releaseVersion}_windows-x64-setup.exe"
$entry = @(Get-Content .\SHA256SUMS | Where-Object { ($_ -split '\s+', 2)[1] -eq $asset })
if ($entry.Count -ne 1) { throw "Expected exactly one checksum entry for $asset" }
$expected = ($entry[0] -split '\s+', 2)[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash
if ($actual -ne $expected) { throw "SHA-256 mismatch for $asset" }

gh attestation verify ".\$asset" `
  --repo ejupi-djenis30/careeros-local `
  --source-ref "refs/tags/v$releaseVersion"
```

The native installers remain unsigned community builds until platform signature checks are
configured and recorded. The Python wheel likewise has no platform code signature. GitHub
provenance binds exact artifact bytes to the repository workflow and source ref; it is not
Authenticode signing, Apple code signing, notarization, or a maintainer signature. Do not describe
an artifact as signed merely because its GitHub provenance verifies successfully.

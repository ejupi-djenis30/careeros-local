# Releasing

CareerOS releases fail closed. A manual workflow run is a read-only rehearsal: it may build and
retain workflow artifacts, but it cannot request an OIDC token, create attestations, touch a
GitHub Release, or publish anything. Only a stable-version tag push can enter the publisher.

## Candidate requirements

Before creating a tag:

1. Complete Spec Kit analysis and convergence with no unresolved critical work.
2. Pass the Python, React, Rust, migration, security, performance, and packaged lifecycle gates.
3. Keep all seven version sources on the same stable `MAJOR.MINOR.PATCH` value. Prerelease and
   build metadata are rejected.
4. Update `CHANGELOG.md` with a dated, human-written section for that exact version.
5. Confirm that `LICENSE` is the approved MIT license and that security exceptions remain valid.

Run the metadata and release-contract tests locally:

```powershell
.venv\Scripts\python.exe -m scripts.check_release_versions
.venv\Scripts\python.exe -m pytest tests\backend\release tests\backend\unit\test_release_versions.py -q
```

## Read-only rehearsal

Run **Desktop packages** from `main`. You may supply the planned tag, such as `v1.1.1`, in
`expected_tag`. The workflow builds six native targets on versioned GitHub-hosted runners,
smoke-tests each package, normalizes installer names, and assembles one exact candidate.

The candidate contains 23 public assets:

- 10 native installers with portable, no-space names;
- six target-specific SHA-256 files whose filenames exactly match their downloads;
- three CycloneDX SBOMs;
- one deterministic supply-chain evidence archive;
- the canonical LF `LICENSE`, downloadable as a first-class asset and byte-identical to the
  project notice embedded by Tauri in every native package;
- `release-manifest.json`, which binds target, package type, name, size, SHA-256, source commit,
  release date, evidence, SBOMs, and the exact public MIT `LICENSE` asset;
- `SHA256SUMS`, which binds every other public asset.

The native smoke gates do not trust package metadata alone. They mount each DMG read-only,
extract each AppImage and DEB, administratively extract each MSI, and install each NSIS package;
every resulting payload must expose the approved project `LICENSE` bytes at the canonical Tauri
resource root. Missing, changed, duplicate case-variant, symlink-alias, or dependency-only license
files stop the run before staging.

No artifact from a rehearsal is a release. Review the retained `verified-release-assets` and
`native-subject-checksums` workflow artifacts before proceeding.

## Tag and publication

Create and push an annotated, cryptographically signed `vMAJOR.MINOR.PATCH` tag only after the
rehearsal succeeds. GitHub must report every annotated tag object as verified. The tagged commit
must equal the candidate source and remain contained in the repository's current default branch.

The tag workflow re-runs every build and check. Its final job then:

1. verifies the tag and default-branch policy before requesting attestations;
2. re-hashes the exact 23-file candidate;
3. creates SLSA provenance for all 23 assets;
4. binds each of the three CycloneDX SBOMs to all 10 native installers;
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
`SHA256SUMS` plus all other 22 assets. On GNU/Linux or in Git Bash, run:

```bash
sha256sum --check SHA256SUMS
```

If you downloaded only one Windows installer and `SHA256SUMS`, compare that exact entry with
PowerShell's native `Get-FileHash` before verifying provenance:

```powershell
$asset = "CareerOS-Local_1.1.1_windows-x64-setup.exe"
$entry = @(Get-Content .\SHA256SUMS | Where-Object { ($_ -split '\s+', 2)[1] -eq $asset })
if ($entry.Count -ne 1) { throw "Expected exactly one checksum entry for $asset" }
$expected = ($entry[0] -split '\s+', 2)[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash
if ($actual -ne $expected) { throw "SHA-256 mismatch for $asset" }

gh attestation verify .\CareerOS-Local_1.1.1_windows-x64-setup.exe `
  --repo ejupi-djenis30/careeros-local `
  --source-ref refs/tags/v1.1.1
```

The packages remain unsigned community builds until platform signature checks are configured and
recorded. Do not describe them as signed merely because GitHub provenance verifies successfully.

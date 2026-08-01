# CareerOS Local v1.11.0 release evidence

Date prepared: 2026-08-01

Status: candidate preparation in progress. The stable metadata and the schema-4, 26-asset release
contract are being reviewed through a protected pull request. No v1.11.0 tag or GitHub Release is
claimed by this preparation record.

## Candidate basis

- Stable version: `1.11.0` across all seven authoritative version sources.
- Release date: `2026-08-01` in both the changelog and release workflow.
- Candidate source: the exact protected `main` commit produced by merging this preparation change;
  its commit and tree identifiers will be recorded after merge.
- Planned tag: `v1.11.0`, annotated and SSH-signed only after the read-only rehearsal passes.
- Public contract: exactly 26 non-empty assets, including `LICENSE`,
  `THIRD_PARTY_NOTICES.txt`, the Agent Access wheel, three CycloneDX SBOMs,
  `release-manifest.json` and `SHA256SUMS`.

## Candidate scope

v1.11.0 hardens CareerOS Local as a daily-driver desktop application. It adds restart-durable vault
reset, restore and erasure recovery; bounded private-file publication journals; rotating
authentication session families; strict local-runtime and provider response envelopes; packaged
migration recovery; and content-free diagnostics. It also strengthens forced-colors, keyboard,
responsive and browser acceptance coverage while preserving the local-only inference boundary.

## Preparation gates

The preparation change must pass these gates before merge:

- release metadata validation for `v1.11.0` and `2026-08-01`;
- exact third-party-notice regeneration with the pinned Python 3.12.13, Node 24.18.x and Cargo
  dependency inputs;
- release-contract, repository-hygiene and distribution tests;
- the complete protected-branch Python, React, Rust, migration, security, browser, container,
  CodeQL and packaging checks.

After merge, the read-only **Desktop packages** rehearsal must build all six native targets and
smoke-test the build-once Agent Access wheel on Linux, macOS and Windows with Python 3.12 and 3.13.
The publisher must remain skipped. Only a successful rehearsal authorizes creation of the planned
tag; the tag workflow must then rebuild and attest the candidate before any immutable release can
be published.

## Claims and boundaries

- Private career data, prompts, model output and model weights remain local to the user's device.
- Agent Access remains read-only and requires an explicitly scoped, revocable local grant.
- `SHA256SUMS` proves byte integrity and GitHub provenance binds bytes to a workflow and source
  ref; neither is platform code signing.
- Native installers and the Python wheel remain unsigned community builds until platform signing
  and notarization are configured and independently verified.
- A local pass, pull-request build, partial target run or draft release is not publication evidence.

This record will be updated with immutable commit, tree, tag, workflow, asset and digest evidence
only after those states exist and have been independently read back from GitHub.

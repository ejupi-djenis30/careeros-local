# CareerOS Local v1.11.0 unpublished candidate record

Date verified: 2026-08-01

Status: not published. The annotated, SSH-signed `v1.11.0` source tag exists and remains
immutable, but its tag workflow was cancelled before candidate assembly, attestation or publisher
execution. GitHub has no v1.11.0 Release and no v1.11.0 release assets. This record must not be
used as installation or publication evidence.

## Immutable candidate identity

- Candidate source:
  [`00676796e9610bd750e5bc565c858b77d56ef430`](https://github.com/ejupi-djenis30/careeros-local/commit/00676796e9610bd750e5bc565c858b77d56ef430).
- Candidate source tree: `b4a754938c334b5336fff38672dc6cedc7c6804f`.
- Annotated tag object: `7e2d0d2d36e6c42444d71231816bd6cb6e07bcdd`; local Git and
  GitHub both reported its authorized SSH signature as valid.
- Read-only rehearsal:
  [Desktop run 30710421406](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30710421406)
  completed all six native targets, all six Agent Access OS/Python smoke combinations and exact
  schema-4 assembly; its publisher was skipped by design.
- Cancelled tag run:
  [Desktop run 30711604611](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30711604611)
  stopped in the first supply-chain job. Every build, assembly and publisher job was cancelled;
  no GitHub Release was created.

## Why publication stopped

The automatic protected-branch
[CI run 30710397422](https://github.com/ejupi-djenis30/careeros-local/actions/runs/30710397422)
reported one failure after 2,191 backend tests had otherwise passed. Concurrent identical
content-addressed writers could observe a false mismatch when the winning writer removed its
private hard-link alias. On POSIX that safe link-count transition changes the inode `ctime` while
leaving the open descriptor, inode, file type, exact size, modification time and bytes unchanged.

The release was stopped fail-closed instead of dismissing the result as a flaky test. The signed
tag was neither moved nor reused. The correction added deterministic adversarial coverage for the
safe publication transition and retained strict single-link and `ctime` validation for recovery
metadata. It passed 16,000 concurrent local writes, the complete backend suite on Windows, the
complete protected Linux backend suite, supply-chain checks and native package smoke before merge
through [PR 71](https://github.com/ejupi-djenis30/careeros-local/pull/71) as
[`47df01ed1c662b980e2d2210f802a962af70b4b0`](https://github.com/ejupi-djenis30/careeros-local/commit/47df01ed1c662b980e2d2210f802a962af70b4b0).

## Superseding release

v1.11.1 carries the complete planned v1.11 product scope together with the corrected storage
invariant. It requires a new protected candidate, read-only six-target rehearsal, annotated signed
tag and tag-triggered rebuild. Only the independently verified v1.11.1 GitHub Release and its exact
26-asset inventory may be described as published.

## Claims and boundaries

- A signed source tag is not a published release and contains no downloadable release contract.
- Private career data, prompts, model output and model weights remain local to the user's device.
- Agent Access remains read-only and requires an explicitly scoped, revocable local grant.
- `SHA256SUMS` and GitHub provenance apply only to an actually published asset set; none is claimed
  for v1.11.0.
- Native installers and the Python wheel remain unsigned community builds until platform signing
  and notarization are configured and independently verified.

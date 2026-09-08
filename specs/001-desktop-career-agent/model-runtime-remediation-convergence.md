# Model runtime remediation convergence

## Closed implementation findings

- Concurrent post-commit journal removal now converges only when the enumerated path is confirmed
  absent. Every extant unstable, replaced or malformed path retains the original fail-closed
  behavior.
- The remaining publication race has a deterministic descriptor-read regression and passed 30
  additional executions of the real cross-profile SQLite/photo path.
- Compose owns a source-verified Ollama 0.33.3 rebuild whose toolchain, source, module graph, native
  runtime and output provenance are explicit and reviewable.
- The persistent runtime uses UID/GID 10001. A networkless `CAP_CHOWN`-only one-shot preserves
  existing named-volume contents, exits before server startup and skips work after ownership is
  already correct.
- Go dependency licensing is regenerated for the resolved graph and shipped beside the patched
  executable; the image embeds build metadata and its executable checksum.
- The expired Trivy inventory and filtered-policy checker are gone. CI builds and exercises the
  model runtime, fails on any HIGH/CRITICAL finding and retains its raw vulnerability report and
  CycloneDX inventory.
- Dependabot now covers the nested Ollama Dockerfile with the repository's seven-day cooldown, so
  digest drift is visible without silently changing coordinated source and module inputs.
- The MCP protocol test uses a deterministic local-model projection and no longer turns host
  connection scheduling into an unrelated protocol failure.

## Validation boundary

The complete current backend tree passes locally with 2,185 tests, 17 platform skips and 81.61%
branch coverage. Ruff, Mypy, focused configuration/recovery tests, 30 repeated publication races,
Compose validation and Actions linting pass. No schema, frontend or native-shell behavior changed.

The local Docker engine was unavailable before a build began, so the branch makes no local image or
scan claim. Protected integration requires the latest commit's Linux container job to compile the
image, start the real service, verify its version, produce the SBOM and return a clean unfiltered
Trivy report. Merge remains blocked automatically until that evidence and every other required job
are green; no exception or administrative bypass is part of convergence.

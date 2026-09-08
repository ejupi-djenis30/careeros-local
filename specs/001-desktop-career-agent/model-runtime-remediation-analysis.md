# Model runtime remediation analysis

## Scope and reproduced failures

This slice closes the two remaining pull-request blockers without changing CareerOS product scope,
data flow or inference authority. The failed backend job ended with 2,196 passing tests and one
cross-profile photo publication race. A writer had already opened another writer's unique journal
when the committed writer unlinked it; the stable reader correctly reported a path-identity change,
but recovery converted that expected post-commit disappearance into an invalid-metadata failure.

Fresh Trivy 0.72.0 scans of the formerly pinned Ollama 0.32.0 image and the reviewed upstream
0.33.3 image each reported 42 HIGH and 1 CRITICAL findings in `usr/bin/ollama`. All were compiled Go
components. The critical CVE-2026-56854 affected `golang.org/x/crypto` 0.43.0 and had no remediation
through the final Ubuntu package layer. The previous exact exception inventory had expired on
2026-08-15, so extending or broadening it was rejected.

## Runtime construction decision

The image retains the exact upstream 0.33.3 native payload and replaces only the Go executable and
its aggregate license document. Every mutable supply-chain boundary is explicit:

| Boundary | Identity or control |
| --- | --- |
| Upstream source | Ollama commit `b79067b0db7417f20108363bc22adb97f35c966a` |
| Source archive | SHA-256 `8f1c4cfe1c687918e00bf9ab6f9966ebd4d727d3d64ccb109b2561afcd347b07` |
| Builder | Go 1.27.1 Bookworm image index `sha256:648f440f42a0958804efb24df176f806f9d353b41f1c0627f666428e40310f6b` |
| Runtime | Ollama 0.33.3 image index `sha256:32931b46719f673c05fdbaa81ccb26da18ea4a1c57590a754874ab28ba269eb2` |
| Patched graph | `jsonparser` 1.1.2 and `x/crypto` 0.55.0, `x/image` 0.45.0, `x/mod` 0.40.0, `x/net` 0.57.0, `x/sync` 0.22.0, `x/sys` 0.47.0, `x/term` 0.45.0, `x/text` 0.41.0 |

The Dockerfile checks the Go toolchain and every resolved module version, runs `go mod verify`,
compiles with `-trimpath`, regenerates `GO_LICENSE`, and embeds the source identities, the
`go version -m` graph and executable SHA-256. Compose builds and tags this image itself. Weekly
Dependabot coverage watches both pinned base images, while exact source/module movement requires a
reviewed coordinated change.

The image defines UID/GID 10001 and the persistent server runs under that identity. To preserve an
existing named model volume, Compose first runs the same image as a network-disabled one-shot with a
read-only root, no-new-privileges, all capabilities dropped except `CAP_CHOWN`, and no application
or model process. It changes ownership only when the volume root is not already 10001:10001 and
exits successfully before the server can start. Subsequent starts skip the recursive migration.

CI starts the real server with the same read-only root, process cap, dropped capabilities and
no-new-privileges boundary used by Compose. It waits for `ollama list`, verifies the patched version,
runs a HIGH/CRITICAL Trivy scan without an ignore file and retains both the raw report and an Ollama
CycloneDX inventory. The expired ignore file, bespoke baseline checker and their tests are removed.

## Journal convergence decision

After a stable journal read reports an identity change, recovery performs one no-follow `lstat` on
the enumerated path. `FileNotFoundError` preserves the already supported concurrent-cleanup signal;
an extant path re-raises the original stability error and remains fail-closed. This does not accept
changed bytes, replacement paths, malformed JSON, links, reparse points or oversized journals.

The MCP protocol test also stopped probing an absent local Ollama port. It now supplies a typed,
deterministic unavailable-model status because the test's responsibility is MCP negotiation and
schema behavior; provider transport has its own bounded integration tests. This removes a Windows
scheduling-dependent five-second test failure without changing production timeouts.

## Local verification

- Full backend gate: 2,185 passed, 17 skipped; branch coverage 81.61% against the 80% floor.
- Focused recovery, publication, MCP and distribution selection: 33 passed.
- Cross-profile normalized-photo race: 30 additional consecutive runs passed.
- Full Ruff and Mypy gates: passed.
- Compose configuration, GitHub Actions YAML parse, `actionlint` and `git diff --check`: passed.
- Distribution configuration selection: 11 passed after the final Dependabot and workflow edits.

The first protected Linux build compiled the source-verified executable, verified its embedded
dependency provenance, started the real server and completed the three-image SBOM step. Repository
misconfiguration scanning then rejected the image's inherited root user as DS-0002 before the
vulnerability gate ran. The follow-up makes the persistent runtime non-root and retains existing
volume data through the bounded initializer described above.

The Windows ARM64 host's Docker Desktop 4.78.0 engine stopped during its own Inference-manager
initialization, before accepting a build. No container result is claimed from that host. The
protected Linux container job remains the authoritative build, health, vulnerability and SBOM gate
for the exact commit and must pass before merge.

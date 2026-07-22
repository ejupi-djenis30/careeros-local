# Research: CareerOS Local Desktop and Compact-Model Accuracy

## Decision 1 — Use Tauri v2 for the desktop shell

**Decision**: Wrap the existing Vite/React single-page application in Tauri v2 and place
native lifecycle code in a small Rust crate.

**Rationale**: Tauri uses the operating-system WebView, supports existing Vite frontends,
provides explicit capability boundaries, and officially supports external binaries such as
Python services packaged by PyInstaller. This yields materially smaller installers than a
bundled browser while preserving the current UI investment.

**Alternatives considered**:

- Electron: mature distribution and familiar JavaScript, but a larger bundled runtime and a
  wider renderer/main-process hardening surface for this single-window local product.
- Full Rust rewrite: smallest process surface, but would discard the tested Python domain,
  migrations and document renderers.
- Browser/PWA: cannot reliably own local model/backend lifecycle or provide a normal installer.

**Primary sources**: [Tauri external binaries](https://v2.tauri.app/develop/sidecar/),
[Tauri Vite integration](https://v2.tauri.app/start/frontend/vite/),
[Tauri security model](https://v2.tauri.app/security/).

## Decision 2 — Freeze the Python backend as one managed sidecar

**Decision**: Produce a platform-native `careeros-backend` runtime with PyInstaller in
one-folder mode, embed that directory as a Tauri resource, and build independently on every
target operating system. A one-file build may be generated only as an explicit diagnostic and
is not included in installers.

**Rationale**: PyInstaller includes the matching interpreter and dependencies, so users do
not install Python. Acceptance testing showed that Windows one-file mode creates an extraction
parent plus an application child: force-terminating the parent can orphan the service and every
launch pays the extraction cost. The embedded one-folder runtime starts faster, gives Tauri one
directly controlled process, and remains inspectable. A parent-PID watchdog covers a native-shell
crash. Its output remains OS-specific, which aligns with the native Tauri build matrix.

**Alternatives considered**:

- Require a system Python: violates clean-machine installation.
- Embed CPython manually: more build and update surface without product value.
- Ship Docker: retains operator friction and is not a desktop application.
- Bundle one-file mode in the installer: rejected after the packaged lifecycle acceptance test
  reproduced an orphan process and slow repeated extraction.

**Primary sources**: [PyInstaller operating modes](https://www.pyinstaller.org/en/stable/operating-mode.html),
[PyInstaller multi-platform builds](https://pyinstaller.org/en/stable/usage.html).

## Decision 3 — Authenticate a random loopback transport

**Decision**: The desktop shell allocates an ephemeral loopback port and a 256-bit session
token, passes both to the sidecar through its private environment, and exposes them only via
the `desktop_bootstrap` command. Every API request includes the session header. The sidecar
rejects non-loopback binding in desktop mode.

**Rationale**: Keeping REST avoids a domain rewrite, but loopback alone does not prevent an
unrelated local web page from probing the service. Random addressing plus a per-launch secret,
strict CORS/hosts and a narrow Tauri capability reduce that exposure.

**Alternatives considered**:

- Fixed localhost port without authentication: vulnerable to local cross-origin probing.
- Proxy every request through Tauri IPC: duplicates streaming, file and error semantics and
  expands privileged IPC surface.
- Unix sockets/named pipes: stronger transport identity but significantly more platform code;
  retained as a future replacement behind the same API client contract.

**Primary sources**: [Tauri capabilities](https://v2.tauri.app/security/capabilities/),
[Tauri CSP](https://v2.tauri.app/security/csp/).

## Decision 4 — Manage llama.cpp and model acquisition explicitly

**Decision**: The production desktop runtime is a pinned llama.cpp server acquired during
model setup, not bundled in the installer. The app selects the exact platform asset from a
signed-in-source catalog, verifies SHA-256, extracts safely into app data, downloads the
official Apache-2.0 Qwen3 1.7B Q8 GGUF with SHA-256 verification, and then starts it on a
random authenticated loopback port. An official Ollama installation is also supported as a
production local fallback when Windows application-control policy blocks the managed runtime. The
fallback is loopback-only, must pass the same identity and structured readiness checks, and never
enables Ollama cloud inference.

**Rationale**: llama.cpp provides small native CPU binaries and schema-constrained chat
completions. Explicit acquisition keeps the installer small, makes model size/license visible,
and preserves full offline operation afterward. The selected model is multilingual, 1.7B
parameters, 32K context and published by the model author.

**Pinned inputs**:

- llama.cpp release `b9637`; per-platform asset hashes live in the checked-in catalog.
- `Qwen/Qwen3-1.7B-GGUF`, `Qwen3-1.7B-Q8_0.gguf`, 1,834,426,016 bytes,
  SHA-256 `061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a`.

**Alternatives considered**:

- Bundle the model: makes every installer and update roughly two gigabytes larger.
- Require Ollama: adds a separate application/service the user must install and operate.
- Download an unpinned “latest” runtime or community quant: weakens reproducibility and trust.

**Primary sources**: [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
[llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases/tag/b9637),
[official Qwen3 1.7B GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF),
[Ollama local-only mode](https://docs.ollama.com/faq).

## Decision 5 — Constrain every trusted AI result with JSON Schema

**Decision**: Each AI task owns a versioned Pydantic contract. The adapter sends its JSON
Schema to llama.cpp `response_format` or Ollama `format`, uses temperature zero, validates the
decoded object again locally, then applies task-specific semantic and evidence rules.

**Rationale**: Grammar/schema decoding removes a major class of syntax failures on compact
models. Local validation remains necessary because a structurally valid value can still be
unsupported or semantically inconsistent.

**Alternatives considered**:

- Prompt-only JSON plus substring extraction: accepts malformed and ambiguous output.
- Free-form chain-of-thought parsing: increases tokens, latency and sensitive intermediate data.
- Unlimited retries: hides quality problems and can stall ordinary hardware.

**Primary sources**: [llama.cpp JSON Schema grammar](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md),
[llama.cpp response formats](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
[Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Decision 6 — Retrieve evidence deterministically before generation

**Decision**: Rank atomic career facts and job fragments locally using a compact BM25-style
scorer plus verification, type and recency weights. Send stable IDs and only the top bounded
evidence. Treat imported text as quoted untrusted data.

**Rationale**: Small models lose precision with oversized, noisy context. Deterministic
selection is inspectable, fast, reproducible and does not require a second embedding model.

**Alternatives considered**:

- Send the complete profile: unnecessary disclosure and attention dilution.
- Add a remote embedding service: violates local-only inference.
- Implicitly download an embedding model: hidden egress and extra storage; optional local
  embeddings may be evaluated later against the same retrieval metrics.

## Decision 7 — Use generate, validate, and one targeted repair

**Decision**: A task performs one constrained generation. If local schema, evidence or domain
validation fails, it may perform one repair containing only error codes, allowed identifiers
and the invalid structured object. A second failure is returned as review-required and cannot
update trusted data.

**Rationale**: A critic pass on every request doubles latency and can reinforce errors.
Selective repair spends compute only where validation proves it is useful and has a fixed bound.

**Alternatives considered**:

- Always run generator plus critic: too slow for 1.7B CPU use and not guaranteed independent.
- Silently coerce every field: can turn hallucinations into plausible trusted values.
- Fail without repair: safe but unnecessarily brittle for minor compact-model mistakes.

## Decision 8 — Evaluate quality offline by task and model profile

**Decision**: Store synthetic/licensed JSONL cases in version control and compute schema pass
rate, exact/normalized field F1, citation precision/recall, unsupported-claim rate, ranking
agreement, latency and peak memory. CI validates the evaluator and fixtures without a model;
release candidates run the pinned compact model offline and archive only aggregate results.

**Rationale**: “Better prompts” are not evidence. Versioned cases and thresholds prevent
regression while avoiding private user content in evaluation artifacts.

**Alternatives considered**:

- Manual spot checks: irreproducible and prone to confirmation bias.
- Use production profiles as test data: unacceptable privacy risk.
- One aggregate score: conceals a critical hallucination failure behind easier tasks.

## Decision 9 — Publish native artifacts through reviewed GitHub Releases

**Decision**: A tag-triggered matrix builds on each native OS, creates Tauri installers,
checksums and SBOMs, performs artifact smoke tests, and uploads a draft GitHub Release for human
review. Updates are enabled only after signing keys and publisher certificates are configured.

**Rationale**: Native build outputs cannot be safely cross-compiled by PyInstaller. Draft
releases preserve review, while Tauri's updater requires cryptographic signatures and must not
be configured with a fake or disposable key.

**Alternatives considered**:

- Build all platforms on one runner: unsupported for the frozen Python sidecar.
- Publish directly from every push: too easy to distribute unreviewed or unsigned artifacts.
- Enable unsigned auto-update: not supported by Tauri and unsafe.

**Primary sources**: [Tauri GitHub pipeline](https://v2.tauri.app/distribute/pipelines/github/),
[Tauri updater signing](https://v2.tauri.app/plugin/updater/).

# Mandatory local analysis — cross-artifact analysis

Date: 2026-07-23

## Decision under review

CareerOS Local now treats opportunity analysis, matching, recommendation and Career Coach as real
local-LLM capabilities. They fail closed until an approved model passes the same structured probes
used by the product. Ownership workflows remain model-independent: users can still edit the Career
Vault, manage manual applications, work with existing documents, export or restore a backup, and
run deterministic application readiness checks.

## Contract analysis

| Boundary | Implementation evidence | Result |
| --- | --- | --- |
| Required analysis | Search and coach routes share a readiness dependency; the React shell presents a keyboard-accessible required setup and recovery flow | Converged |
| No heuristic masquerade | Matching persists only schema-validated model executions with local provenance; unavailable or invalid inference returns an explicit error | Converged |
| Server-owned decisions | The model returns seven bounded scores; policy code computes caps, recommendation, worth-applying, risks and citations from extracted evidence | Converged |
| Grounding | Candidate facts and job requirements retain exact source quotes and identifiers; coaching claims must cite Career Vault evidence | Converged |
| Multilingual requirements | English, German, French and Italian markers, negations, alternatives, years, CEFR levels and qualification ranks are covered by an adversarial matrix | Converged |
| Local-only runtime | Inference accepts loopback and exact explicit single-label container aliases only; there is no cloud provider or telemetry fallback | Converged |
| Persistence safety | Job rows, application snapshots, exports and restores quarantine missing, legacy, imported, downgraded or client-authored analysis provenance; private discovery queries remain on user-owned job rows | Converged |
| Non-AI continuity | Vault, manual records, documents, portability and deterministic readiness do not depend on model availability | Converged |

## Adversarial review

The implementation was exercised against missing mandatory requirements, mixed-polarity clauses,
comma exclusions, disjunctive alternatives, contractions, candidate negations, fluent/native
language ranks, multilingual experience and qualification gaps, exact output cardinality, token
truncation, model identity drift, endpoint tampering, archive downgrade, restored Coach replies,
application snapshot leakage and two accounts saving the same provider listing. Failures remain
explicit and do not create a verified analysis row or cross an account boundary.

The managed llama.cpp runtime completed all four readiness probes with the packaged Qwen model.
Independent Ollama checks completed a natural-language opportunity assessment and an evidence-bound
Career Coach response without a heuristic or remote-model fallback.

## Verification result

- Backend: 1,261 passed, 4 expected skips; branch-aware coverage 80.70%.
- Multilingual evidence matrix: 79 passed; expanded inference, readiness, security and API slices
  passed before the full-suite run.
- Frontend: 62 files and 319 tests passed; V8 line coverage 80.93%.
- Rust desktop shell: 10 tests passed; formatting and Clippy with warnings denied passed.
- Python static analysis: Ruff passed; mypy passed across 188 backend source files.
- Database: fresh SQLite `upgrade head`, `downgrade -1`, `upgrade head` passed.
- Performance: all 4 opt-in tests passed. Readiness measured 70.056 ms p95 against 100 ms;
  10,000-record profile reads measured 3.037 ms p95 and 200-row application pages 25.071 ms p95
  against 200 ms.

No unresolved cross-artifact contradiction remains in the release candidate.

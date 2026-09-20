# Research: MCP Career Workspace

## Decisions and evidence

1. **Decision**: Extend the already installed official MCP Python SDK, retaining stdio and
   proxying new operations to the open desktop. **Rationale**: current read-only runtime takes
   the vault lease and cannot coexist with desktop. **Alternative rejected**: removing the
   lease or opening a separate writable SQLite engine.
   Sources: backend/automation/mcp_server.py, runtime.py, facade.py; MCP SDK in requirements.
2. **Decision**: Client-driven work queue/context/result tools. **Rationale**: MCP exposes tools
   to client-selected models; it does not guarantee initiating Codex/Claude subscription
   inference from CareerOS. **Alternative rejected**: direct cloud SDK or masquerading external
   output as local inference.
   Official client setup: https://learn.chatgpt.com/docs/extend/mcp?surface=cli and
   https://code.claude.com/docs/en/mcp (consulted 2026-09-13).
3. **Decision**: Constitution 2.0.0 permits explicit external disclosure/proposal scopes.
   **Rationale**: owner specifically requests Codex/Claude analysis; old scopes and local
   endpoint allowlist remain unchanged. **Alternative rejected**: silently broadening
   career:read or granting the agent owner approval capabilities.
4. **Decision**: Reuse existing application dossier, resume canvas, grounding and publication.
   **Rationale**: backend/applications/service.py already implements revisioned draft/publish
   ZIP with evidence and manifest; resumes/publishing.py checks bytes and rollback.
   **Alternative rejected**: new parallel packet persistence and unvalidated raw generated HTML.
5. **Decision**: Nine family/locale presets backed by three independent layouts.
   **Rationale**: ../Career has nine CVs and letters but shared ATS, SME photo and Swiss
   operational presentation. Family and language are metadata, not duplicated rendering code.
   Reference-only: ../Career/{Goal.md,cv-templates/README.md,cover-letter-templates/README.md,
   email-templates/README.md,application-packets/README.md,html-templates/build.cjs,a4.css}.
   No personal text is included in this artifact or distributed fixtures.
6. **Decision**: Keep fact truth, narrative and goals distinct. **Rationale**: manual workflow
   explicitly separates Profile.md, Storytelling.md and Goal.md; templates cannot introduce
   facts. **Alternative rejected**: treating imported prose as confirmed structured profile.
7. **Decision**: Use GPT-5.3-Codex-Spark through installed Codex CLI for bounded implementation
   slices, or agy --dangerously-skip-permissions if Spark fails. **Evidence**: installed CLI
   returned SPARK_READY using exact gpt-5.3-codex-spark model. agy --help verifies the actual
   flag has two leading hyphens. Implementation stays in the two authorized engines; reviewer
   agents never implement. Antigravity's available model selector may be used within that engine.
   Execution update: three Spark slices stopped at the Spark usage limit before code changes;
   implementation switched to the already authorized Antigravity CLI. The availability probe
   proved access at that instant only, not enough remaining quota for implementation.
   Initial Antigravity passes used its configured Gemini 3.8 Flash (High); independent review
   identified missing contract/security behavior. Correction passes use Antigravity's listed
   Claude Opus 4.6 Thinking model, still through agy with the requested permissions flag.
8. **Decision**: Apply repository-installed GitHub Spec Kit 0.12.17 workflows. **Evidence**:
   specify preset resolve spec-template resolved .specify/templates/spec-template.md;
   setup-plan.ps1 resolved feature 002. No reinitialization needed.
   Primary source: https://github.com/github/spec-kit (consulted 2026-09-13).
9. **Decision**: Resume implementation directly with the coordinating Codex agent and isolated
   subagents. **Rationale**: after three confirmed quota-blocked turns, the owner explicitly said
   to continue implementation directly. This supersedes the engine-only implementation restriction
   in decision 7 without changing the completed spec, scope, independent review or test gates.

## Resolved uncertainties

Desktop coexistence uses loopback proxy with a distinct grant trust boundary; API/UI evidence
contracts are fixed before delegation. Template compatibility retains old ats/photo publications.
External-model labels are self-reported; successful validation does not prove model identity.
No remote API key, download, credential import or application transmission is part of this change.

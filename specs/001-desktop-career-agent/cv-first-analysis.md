# CV-first first result — cross-artifact analysis

## Observed first-use gap

The published v1.8.0 desktop release has native installers for every documented target, and the
authenticated Home screen already exposes a four-step setup checklist. The first Career Vault
step, however, sent a new user to the long-form profile editor. That editor displayed a local CV
importer only after identity, goals, preferences and facts. More importantly, the importer called
`POST /career-profile/sources`, while that endpoint correctly rejected every document until a
Career Profile already existed. A person who chose the natural “start from my current CV” route
therefore received `Create the career profile before importing source documents` on the first
attempt, with no visible prerequisite.

This was an orchestration defect, not an extraction or storage defect. The existing profile write,
source upload, bounded parsing, atomic storage and provenance contracts were individually correct.

## Decision and request sequence

The Home setup milestone now presents two honest choices:

1. **Start from a CV** opens `/profile?start=import` and places the source importer before the
   long-form editor.
2. **Enter facts manually** retains the original profile route and model-free manual workflow.

On the CV-first route, the profile page remembers whether its initial read returned `404`. An
explicit import follows this sequence:

```text
user chooses file
  -> PUT /career-profile with expected_revision=0
  -> receive revisioned local profile
  -> POST /career-profile/sources with the still-selected file
  -> review deterministic candidates
  -> add selected candidates as imported
  -> focus the facts review heading
  -> user explicitly confirms accurate facts and saves
```

An existing profile skips the bootstrap write. A failed bootstrap starts no source upload. A
failed bootstrap or upload leaves the file selected for a deliberate retry. The profile save and
source upload stay separate because combining them would duplicate a mature revision contract and
move orchestration into the transport layer.

## Trust and privacy review

| Boundary | Result |
| --- | --- |
| Inference | No model service, prompt or analysis route is called. |
| Network | No endpoint was added. The flow reuses the authenticated loopback profile and source routes. |
| Storage | Source bytes still pass the existing size, format, containment, atomic-write and digest controls. |
| Truth | Extracted candidates retain `imported` status. The UI states that they are not confirmed. |
| Failure | Profile-write failure blocks upload; upload failure preserves the user's selected file for retry. |
| Accessibility | Both Home choices have accessible names. The review action moves keyboard focus to a programmatically focusable facts heading. |
| Existing users | A revision greater than zero imports directly and does not create an unnecessary profile revision. |

No schema, migration, runtime, provider consent, local-model policy, telemetry or release contract
changed. The implementation strengthens the existing desktop-product, grounded-truth, user-owned
Vault and keyboard-accessibility principles without amending the constitution.

## Artifact consistency

- Specification: FR-081 and SC-026 define ordering, failure containment and unconfirmed review.
- Plan: Phase O records the frontend orchestration decision and rejected implicit endpoint
  bootstrap.
- Tasks: T164–T168 cover behavior, tests, documentation and convergence.
- Product copy: English and Italian describe what is local, what is saved and what still requires
  confirmation.
- Owner guidance: README and the daily-driver guide describe the same sequence and model boundary.

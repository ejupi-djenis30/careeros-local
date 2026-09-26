# Convergence: Campaign Review Decisions via CLI

The implementation, fictional tests, README contract, full backend rerun, and local-vault
exercise converge on the specified non-submission behavior. The real campaign review evidence
is private vault data and is not committed to source control. Review filtering is a read-only
queue inspection aid; neither `none` nor `cleared` is a submission-readiness result.

Remaining before merge or release:

1. Sign and push a reviewed commit, then let branch protection and CI verify the exact new head.
   The configured SSH signing key is passphrase-protected and was not available in the agent at
   this checkpoint; do not substitute an unsigned commit or bypass branch protection.

No employer submission is implied by this feature or by the recorded review decisions.

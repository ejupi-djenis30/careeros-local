# Renderer request boundary analysis

Date: 2026-09-07

## Finding and reproduction

`validateApiBase` constrained the runtime host and `/api/v1` prefix, while `ApiClient.request`
appended its endpoint without validation. A browser URL parser can normalize dot segments in
an appended path outside that prefix. Other malformed endpoints reached fetch together with
the account and desktop headers. This is a client containment gap; this review does not claim
an exploit of a server route or a cross-origin disclosure.

Before the fix, 18 adversarial request cases resolved through the fetch mock instead of being
rejected. Cases cover dot segments, percent-encoded separators/dots, backslashes, fragments,
malformed encoding, control characters, relative/absolute URLs, an empty value and null.

## Implementation

`requestPath.js` checks the raw endpoint and decoded path segments, then verifies the parsed
pathname against a fixed validation origin and `/api/v1`. `ApiClient.request` invokes it before
allocating a controller or constructing authenticated headers. Query data remains encoded and
unchanged; no additional request or network service is introduced. Redirect rejection and
session refresh/cancellation keep their existing behavior.

Request-level regressions exercise both browser and desktop modes and assert no fetch, header
construction or active controller for a rejected path. Positive cases preserve encoded Unicode
identifiers, spaces/separators in query values and IPv6 loopback desktop operation.

## Verification

- `npm test`: passed the full frontend run (79 Vitest files, 496 tests), four Node runtime
  tests, nine distribution/license tests and the generated icon check.
- After expanding each invalid-path case to both runtime modes, the three client test files
  passed all 81 tests. No production code changed after the full run.
- `npm run lint`: passed.
- `npm run build`: passed, including the existing distribution and byte-budget validator.
  Initial resources: 425,443 raw bytes / 134,247 gzip bytes; existing limits remain unchanged.
- The initial sandboxed Vitest launch was blocked by esbuild directory access. The same tests
  ran successfully with the required local process access; no test was disabled.

## Scope limits

Backend Python, Rust/native installers, migration round trips, AI evaluation and real-browser
end-to-end gates were not run for this renderer-only patch. There is no database or native
capability change. This local verification is not a new release certification.

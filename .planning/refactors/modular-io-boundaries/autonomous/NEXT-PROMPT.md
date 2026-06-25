# Next Prompt

Do not continue autonomously from this state.

## Current State

- Branch: `dev`.
- Last completed boundary: `planning:global-closure-hard-stop-report`.
- Report: `.planning/refactors/modular-io-boundaries/analysis/global-closure-hard-stop-report-2026-06-25.md`.
- Status: `hard-stop-reported`.
- Global/module closure is not claimed.

## Hard Stop

The remaining closure gates cannot be completed by another safe owned local/app-code/planning boundary.

Blocked gates:

- Browser production evidence: no approved pinned Playwright/runtime wrapper, no private non-logged token broker handoff, and production app host remains unsuitable for browser execution from Row294/296.
- Admin-scope production evidence: no supported admin HTTP SLO token/cookie seam; target OA applicant sessions are full-access non-admin.
- Controlled write apply evidence: no explicit approval ticket, reviewed reversible business object, rollback/idempotency/audit acceptance, convergence expectations or suitable auth.

## Smallest Safe External Action

Provide or approve a controlled browser runner runtime first:

- pinned Playwright runtime or container image digest;
- no browser install/download during evidence runs;
- wrapper that consumes target OA token through a private non-logged descriptor;
- artifact policy matching Row305/306 redaction rules.

After that, resume with a bounded `production:authenticated-browser-page-smoke-via-ops-runner` boundary and pre/post health, dirty scope, readiness, read-model outbox and dead-letter checks.

Admin and write apply remain separate future gates.

## Stop Gates

- Do not claim global closure.
- Do not run production browser smoke without the approved runner/wrapper.
- Do not run token-producing commands or print/copy tokens.
- Do not execute admin probes without a supported non-secret admin seam.
- Do not execute production writes without an explicit approval ticket and reviewed reversible target/rollback/idempotency/audit plan.

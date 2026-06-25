# Production Strict Diagnostics Sanitized Output Contract - 2026-06-25

**Boundary:** `frontend:production-strict-diagnostics-sanitized-output-contract`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `deployment:production-browser-smoke-runner-bundle-implementation`

## Goal

Keep local deterministic Playwright diagnostics useful while ensuring production route-shell smoke cannot persist raw console, page error, request failure or dialog detail in artifacts.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-runner-bundle-contract-2026-06-25.md`
- `web/e2e/fixtures/strictTest.ts`
- `web/e2e/production-route-shell.spec.ts`
- `tests/test_playwright_e2e_strict_diagnostics.py`

## Changes Made

`web/e2e/fixtures/strictTest.ts`:

- added `productionDiagnosticsRedactionEnabled` gated by `FIN_OPS_E2E_PRODUCTION_SMOKE=1`;
- added production-only redaction for diagnostics before they enter the collected event list;
- preserved raw local diagnostics when production smoke mode is off;
- redacts `console.error`, `pageerror` and `dialog` details to `<redacted>` in production smoke mode;
- redacts failed request details to method plus path classification, e.g. `/api/<redacted>` or `/fin-ops/<route>/<redacted>`, with no query string or failure text;
- kept the existing maximum diagnostic cap and request resource filtering.

`tests/test_playwright_e2e_strict_diagnostics.py`:

- added a static guard proving production smoke redaction is wired through strict diagnostics;
- kept existing production route-shell readonly/secret guards and the new body-sample guard.

## Verification

Targeted static guard:

```text
python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q
.........                                                                [100%]
9 passed in 0.05s
```

Frontend type/build check:

```text
npm --prefix web run build
```

The build passed. Vite emitted the existing CSS minification warnings for generated selector syntax; no TypeScript/build failure occurred.

No production browser smoke, package install, browser download, token broker, deployment or production command was run.

## Docs Impact Assessment

No long-term docs changed in this implementation slice:

- no runner bundle command is implemented yet;
- no production runner entry point is approved yet;
- no app behavior, auth behavior, deployment behavior or API contract changed.

Future bundle implementation should update operations/testing docs when it introduces a concrete approved command.

## State-Machine Impact

- Row304 transitions from `pending` to `implementation-closed`.
- Row305 is inserted as `pending`.
- Browser production evidence remains deferred until bundle, runner runtime/token broker and production execution are complete.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not applicable; no read model runtime changed.
5. Frontend component and interaction tests: applicable as production diagnostics static guard and TypeScript build coverage.
6. End-to-end business-flow integration tests: not executed; production browser execution remains deferred.
7. Existing feature regression tests: applicable through existing Playwright diagnostics guard, frontend build, docs verification and diff checks.

## Verification Plan

Run before commit:

- `python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q`
- `npm --prefix web run build`
- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

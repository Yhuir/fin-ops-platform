# Production Route Shell Sanitized Output Contract - 2026-06-25

**Boundary:** `frontend:production-route-shell-sanitized-output-contract`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `deployment:production-browser-smoke-runner-bundle-contract`

## Goal

Harden the production route-shell browser smoke so failed route diagnostics cannot persist page body text samples, while preserving the read-only/mutating-request guard and useful route classification metadata.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-ops-runner-design-2026-06-25.md`
- `web/e2e/production-route-shell.spec.ts`
- `web/playwright.config.ts`
- `web/package.json`
- `tests/test_playwright_e2e_strict_diagnostics.py`

## Changes Made

`web/e2e/production-route-shell.spec.ts`:

- removed the `textSample` field from `routeResults`;
- stopped persisting `bodyText.slice(0, 80)` in failed route assertion output;
- preserved allowed diagnostics: route `path`, `blockedSession` and `stillLoading`;
- preserved the read-only mutating request guard for `POST`, `PUT`, `PATCH` and `DELETE`;
- preserved screenshots/traces/videos disabled for this production-only spec.

`tests/test_playwright_e2e_strict_diagnostics.py`:

- extended the production route-shell static guard to reject `textSample`;
- extended the guard to reject `bodyText.slice`, preventing future page body samples from returning to failure output.

## Verification

Targeted static guard:

```text
python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q
........                                                                 [100%]
8 passed in 0.05s
```

No production browser smoke, package install, browser download, token broker, deployment or production command was run.

## Docs Impact Assessment

No long-term docs changed in this implementation slice:

- no production runner is implemented;
- no deployment or test command contract changed;
- no app behavior, auth behavior or API contract changed.

The future runner bundle contract slice should update operations/testing docs if it establishes an approved production browser smoke entry point.

## State-Machine Impact

- Row302 transitions from `pending` to `implementation-closed`.
- Row303 is inserted as `pending`.
- Browser production evidence remains deferred until a runner bundle/runner/token broker is implemented and executed.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not applicable; no read model runtime changed.
5. Frontend component and interaction tests: applicable as a production Playwright spec contract guard; covered by `tests/test_playwright_e2e_strict_diagnostics.py`.
6. End-to-end business-flow integration tests: not executed; production browser execution remains deferred.
7. Existing feature regression tests: applicable through the existing Playwright diagnostics guard plus docs/diff verification.

## Verification Plan

Run before commit:

- `python -m pytest tests/test_playwright_e2e_strict_diagnostics.py -q`
- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

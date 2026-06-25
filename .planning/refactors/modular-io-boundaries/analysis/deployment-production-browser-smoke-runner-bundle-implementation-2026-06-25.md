# Production Browser Smoke Runner Bundle Implementation - 2026-06-25

**Boundary:** `deployment:production-browser-smoke-runner-bundle-implementation`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `deployment:production-browser-smoke-token-broker-runbook`

## Goal

Implement the minimal local bundle packager/manifest contract for production route-shell browser smoke outside normal app release packaging, without deploying, running production browser smoke, installing/downloading browsers or implementing a token broker.

## Inputs Reviewed

- `analysis/deployment-production-browser-smoke-runner-bundle-contract-2026-06-25.md`
- `web/e2e/production-route-shell.spec.ts`
- `web/e2e/fixtures/strictTest.ts`
- `web/playwright.config.ts`
- `web/package.json`
- `web/package-lock.json`
- `scripts/deploy_oa.py`
- `tests/test_deploy_oa_script.py`

## Changes Made

Added `scripts/package_production_browser_smoke.py`:

- creates a local `.tar.gz` bundle for production route-shell smoke runner input;
- includes only approved files:
  - `web/e2e/production-route-shell.spec.ts`;
  - `web/e2e/fixtures/strictTest.ts`;
  - `web/playwright.config.ts`;
  - `web/package.json`;
  - `web/package-lock.json` when present;
- writes `production-browser-smoke-manifest.json` into the bundle;
- records git branch/commit, release name, base URL, included file list and per-file SHA-256;
- records runtime and command contracts;
- records artifact redaction rules;
- explicitly marks `normal_app_release_packaging_changed=false`;
- does not package `node_modules`, browser binaries, `web/dist`, production admin spec, screenshots, traces, videos, HTML report or secret env files.

Added `tests/test_production_browser_smoke_bundle.py`:

- verifies archive contents equal the approved file list plus manifest;
- verifies forbidden paths/artifacts are absent;
- verifies manifest fields and SHA-256 values;
- verifies no concrete token/secret-like values are embedded and the token placeholder is `<in-memory-only>`.

Updated long-term docs:

- `docs/dev/testing.md`;
- `docs/operations/deployment.md`;
- `deploy/oa/README.md`.

The docs state that the bundle is local-only runner input, not normal app release packaging and not browser execution.

## Verification

Targeted bundle/deploy tests:

```text
python -m pytest tests/test_production_browser_smoke_bundle.py tests/test_deploy_oa_script.py -q
..............                                                           [100%]
14 passed in 0.54s
```

No production browser smoke, package install, browser download, token broker, deployment or production command was run.

## Docs Impact Assessment

Long-term docs were updated because this slice introduced a concrete local command:

- `docs/dev/testing.md` documents bundle generation, exclusions and required future production evidence gates.
- `docs/operations/deployment.md` states the bundle is outside release-based app deployment and must not be mixed into `scripts/deploy_oa.py` release packaging.
- `deploy/oa/README.md` repeats the OA deployment boundary for operators.

## State-Machine Impact

- Row305 transitions from `pending` to `implementation-closed`.
- Row306 is inserted as `pending`.
- Browser production evidence remains deferred until token broker, runner runtime and production execution are complete.
- Admin evidence remains deferred pending a supported admin seam.
- Write apply remains blocked pending approval and reversible-object gates.
- Global/module closure remains open.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service/repository code changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: not applicable; no read model runtime changed.
5. Frontend component and interaction tests: indirectly applicable; bundle includes the production route-shell spec but does not execute it.
6. End-to-end business-flow integration tests: not executed; production browser execution remains deferred.
7. Existing feature regression tests: applicable through bundle/deploy tests, docs verification and diff checks.

## Verification Plan

Run before commit:

- `python -m pytest tests/test_production_browser_smoke_bundle.py tests/test_deploy_oa_script.py -q`
- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check` after staging

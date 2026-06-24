# Read Model Full Deterministic E2E Smoke Runbook - 2026-06-25

**Boundary:** `browser:read-model-full-deterministic-e2e-smoke-runbook`
**Status:** `browser-guard-closed`
**Module closure:** `not-module-closed`
**Production mutation:** none
**Worker threads created:** none
**Next boundary:** `planning:post-full-deterministic-e2e-smoke-next-boundary-selection`

## Goal

Execute the repository's full local deterministic Playwright smoke layer after Row265 fixed stale assertions inside smoke specs and Row266 selected broad local browser evidence as the next smallest boundary.

This slice does not run production browser/API smoke, authenticated HTTP probes, deploys, worker replay, queue repair, production writes or module/global closure.

## Inputs Reviewed

- `analysis/planning-post-browser-data-targeted-smoke-next-boundary-selection-2026-06-25.md`
- `analysis/browser-read-model-browser-data-targeted-smoke-runbook-2026-06-25.md`
- `analysis/planning-read-model-browser-data-harness-coverage-map-2026-06-25.md`
- `docs/dev/testing.md`
- `docs/dev/spec-first-e2e-audit.md`
- `web/package.json`
- `autonomous/MODULE-QUEUE.md`
- `autonomous/STATE.md`
- `autonomous/JOURNAL.md`

## Command

```bash
cd web && npm run e2e:smoke
```

## Result

The smoke run executed the repository deterministic Chromium smoke script:

- `175 passed`
- runtime: `7.6m`
- exit code: `0`

No Playwright spec, product code, API contract, smoke script or runtime configuration change was required in this slice.

The run generated local Playwright artifacts under `web/test-results`; those artifacts were cleaned before controller accounting so only analysis and controller files remain in the working tree.

## Evidence Added

Fresh local deterministic browser evidence now exists for the full `npm run e2e:smoke` inventory on current `dev` after Row265's spec fixes, including:

- app shell, responsive shell, AppHealth and finance table system smoke;
- bank details, bank account balance, export, category, stale/refreshing and large-scroll flows;
- Workbench relation fan-out, stale/error, network recovery, permissions, large scroll, exception, cash special, split candidate and withdraw flows;
- pending invoices, OA pending payments, no-OA batches, batch accounting and turnover ledger flows;
- bank/invoice/ETC imports and downstream read-model refresh flows;
- tax offset, cost statistics, input invoice usage and output invoice collection read-model/browser flows;
- permissions role matrix across read-export, full-access and admin gates.

This is local deterministic Chromium evidence only. It does not prove authenticated production browser hydration, authenticated production API response shapes, production high-row browser performance, real PostgreSQL/RabbitMQ/Redis/systemd worker drain, write-after-read convergence in production, or module/global closure.

## State-Machine Impact

- Row267 closes as `browser-guard-closed`.
- Row268 is inserted as `pending`.
- No module status changes to `closed`.
- Production authenticated API/browser evidence remains deferred.
- Production high-row browser and worker-drain/write-after-read evidence remain open.
- Go admission remains blocked.

## Docs Impact Assessment

Controller accounting only:

- `STATE.md`
- `MODULE-QUEUE.md`
- `JOURNAL.md`
- `NEXT-PROMPT.md`
- `prompts/04-master-goal-controller.md`

Module docs and long-term docs are not updated because no smoke membership, product behavior, API contract, module fact or long-term testing guidance changed. Existing docs already define `npm run e2e:smoke` as the deterministic Chromium smoke layer and distinguish it from `external-risk` production/staging evidence.

## Seven Test Category Assessment

1. Business core unit tests: not applicable; no business rule changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: not applicable; no API contract changed.
4. Read model/cache/background job tests: partially exercised through local browser freshness/status/barrier flows; production worker convergence remains open.
5. Frontend component and interaction tests: covered by the full Playwright smoke run.
6. End-to-end business-flow integration tests: covered locally by the full deterministic Playwright smoke inventory.
7. Existing feature regression tests: covered locally by `175 passed` in `npm run e2e:smoke`; production/auth/high-row regression evidence remains open.

## Next Boundary Recommendation

Select `planning:post-full-deterministic-e2e-smoke-next-boundary-selection`.

The next planning slice should reconcile the fresh full local smoke result against the remaining external-risk gaps and select the next smallest safe evidence boundary, likely one of:

- authenticated production API/browser evidence if a non-secret session path can be proven;
- production high-row browser/read-path evidence if it can be bounded without secrets or payload capture;
- production worker/write-after-read convergence evidence if a bounded runbook and rollback/cleanup proof are available.

Do not claim module/global closure from Row267 alone.

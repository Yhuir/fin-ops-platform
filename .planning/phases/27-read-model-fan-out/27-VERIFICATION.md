# Phase 27 Current Release Verification

> Active production baseline: `main-719c9a34-20260725101310`. Current local Candidate A contains the Phase 27 final trigger-contract correction and has not yet been deployed. Phase 27 remains incomplete until Candidate A completes the single production matrix, fixture recovery and final audit.

## Current conclusion

Candidate A now implements one ordinary runtime contract:

1. Ordinary writes commit only canonical facts, owner version, audit and idempotency state. They do not enqueue or wait for downstream page read models.
2. A business page checks its own exact freshness only on route enter/re-entry, page query/scope change, browser manual reload, explicit retry or current-page post-command reconcile.
3. Focus, visibility, BFCache restore, another tab's write, finance domain events and bank-tag business broadcasts produce zero business page I/O.
4. A user-triggered page GET may poll only while that page is non-fresh. Polling is single-flight, cancellable and bounded; fresh, hidden, unmount, query change or timeout stops it.
5. App Health, explicit background-job/import/reapply/repair progress and Workbench refresh-status channels remain. They report operational/job state and do not reload unrelated business pages.
6. PostgreSQL canonical facts, durable queue, freshness gateway, exact scope dedupe, workers, CAS and Workbench active-generation publishing remain unchanged as the consistency foundation.

The three-second SLO is observational follow-up, not a Phase 27 correctness gate. Incomplete payloads, stale-as-fresh, permanent refreshing, failed manual recovery, unrelated page I/O or non-convergent queue/worker state still block.

## Candidate A implementation inventory

### Backend

- `input_invoice_usage` and `output_invoice_collection` access-time gates stage the real shared `workbench_relation` dependency before admitting the page projection.
- The runtime worker reuses the application-owned Workbench relation projection builder and passes the same expected relation source versions to the consumer facade.
- The manifest declares the two real read dependencies. No unrelated dependency, global barrier or writer fan-out was added.
- Tests cover dependency missing/refreshing/fresh, exact enqueue order, no premature consumer job, shared dependency dedupe and registry/manifest wiring.

### Frontend

- `PageRouteHost` no longer installs focus, blur, visibility or BFCache business-reactivation listeners. Route mount is the only shell activation.
- The finance domain-event module, active-domain-event hook, business event emitters/subscribers, bank-tag window/BroadcastChannel path and their old tests are deleted.
- Current-page command reloads remain; unrelated open pages do nothing until the user accesses or reloads them.
- Cost, bank detail, bank-flow, pending/input/output invoice and OA page retries are bounded to the current visible access attempt instead of running forever or continuing while hidden.
- OA retains ETag/304 and `202 -> current rows GET -> fresh`, but deletes fresh-page 500ms polling and hidden→visible auto-check. Non-fresh retry is single-flight and capped at 60 attempts/30 seconds.
- App Health broadcast, background-job progress and Workbench lightweight refresh-status monitoring remain explicitly isolated.

### Old-path deletion

- Deleted production files:
  - `web/src/features/domainEvents.ts`
  - `web/src/hooks/useActiveFinanceDomainEvent.ts`
- Deleted obsolete tests/helpers:
  - `web/src/test/domainEvents.test.ts`
  - `web/src/test/useActiveFinanceDomainEvent.test.tsx`
  - `web/src/test/eventAssertions.ts`
- Architecture guards now fail if any business page restores finance domain events, the active-domain hook, the bank-tag event or a business `BroadcastChannel`.
- Current test commands and module entry points no longer point maintainers to the deleted frontend paths; dated implementation/closure records are explicitly historical.
- No fallback, compatibility event bus, page coordinator, second registry, new endpoint, queue, worker, cache, table, migration or dependency was introduced.

## Local Candidate A evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend freshness/dependency slice | pass | 96/96: manifest, input/output fresh gates, worker registry/scopes and architecture guards |
| Deleted frontend event architecture guard | pass | `RuntimeWorkerEtcImportLinkExistingTests.test_business_pages_do_not_restore_deleted_frontend_domain_events` |
| Frontend affected batch | pass | 35 files / 509 tests |
| Final OA + route regression | pass | Included in the 35-file batch; fresh zero polling, hidden→visible zero I/O, bounded 202 convergence and source guards |
| Production build | pass | TypeScript + Vite build; only existing HeroUI CSS, Node deprecation and main-chunk warnings |
| Python lint | pass | `PATH=/opt/miniconda3/bin:$PATH bash scripts/verify.sh lint` |
| Docs | pass | `bash scripts/verify.sh docs` before the final evidence wording; rerun is required before commit |
| Diff hygiene | pass | `git diff --check`; rerun is required before commit |
| Full browser/CI | intentionally not run | The unrelated 183-browser suite and full CI are excluded by the approved efficient validation policy |

The current change is deletion-heavy: 112 files, about `+1238/-2359` before final evidence wording. Package/lock/requirements/pyproject and migration diffs are zero.

## Seven-category decision

All seven categories apply because this is a cross-module read-model/worker/frontend contract change.

1. **Business core unit — pass**
   - Retained relation, version, idempotency, write safety and invalid-state coverage from the Phase 27 ancestor gates.
   - Candidate A changes no business matching, amount or permission rule.
2. **Service layer — pass**
   - Covers exact dependency staging, durable enqueue order, shared dependency dedupe, worker source-version proof and zero premature consumer enqueue.
3. **API contract — pass**
   - Existing 200/202/fresh/stale/refreshing shapes remain. OA ETag/304 remains server-compatible; only the browser's permanent fresh polling is removed.
4. **Read model/cache/background job — pass locally**
   - Covers freshness gates, exact dependencies, durable queue/worker registry and no dependency blocking unrelated pages.
   - Real systemd/RabbitMQ/PostgreSQL convergence remains a Candidate A production gate.
5. **Frontend component/interaction — pass**
   - Covers route/manual recovery, loading/empty/error/refreshing, current-page command reconcile, fresh zero polling, focus/visibility/BFCache/other-page zero reload and all touched page/Drawer regressions.
6. **End-to-end business flow — pass at targeted local level**
   - Critical command→current-page GET and `202 -> fresh` component/service/API paths pass.
   - The full real 17-page/15-read-model matrix is intentionally performed once after Candidate A deployment, not simulated by rerunning all 183 browser flows.
7. **Existing feature regression — pass for affected surface**
   - 509 affected frontend tests, 96 backend freshness/runtime tests, build, lint and architecture guards protect unrelated page behavior.
   - Production Candidate A must still prove all registered pages and allowed operations with one reversible fixture.

## Architecture / over-design review

- Module I/O remains directional: page → API/query owner → freshness gateway → durable queue → worker/projection; writes stop at their canonical owner.
- Page shell does not know page-to-read-model mappings and does not perform business I/O.
- Real read dependencies are declared only where a consumer actually reads them; independent pages do not gain artificial dependency order.
- Deletion was preferred over compatibility branches. Existing gateways, queue, workers, ETag, query owners and status channels were reused.
- No speculative optimization was added for the deferred three-second SLO.
- The only new bound is an explicit retry ceiling on existing current-page non-fresh convergence, preventing permanent hidden/background I/O.

## Candidate A production gate

After the official commit/push/deploy, use one test-owned, fingerprinted, reversible fixture and preserve every first-attempt result before changing code.

The single matrix must prove:

- every registered page can load a complete fresh payload, and an initial load failure can recover by browser/manual retry;
- every ordinary write/association/withdraw/Drawer save returns after canonical commit and creates zero downstream page fan-out;
- visiting one stale consumer enqueues only its necessary exact scope/dependencies, with one effective job per scope;
- fresh repeat access does not rebuild;
- unrelated pages and already-open tabs produce zero business I/O, including focus/visibility/BFCache transitions;
- current-page post-command reconcile and non-fresh bounded polling reach fresh without stale-as-fresh or request overlap;
- all affected pages show the canonical new state after their own access;
- App Health, System Audit, outbox, dirty scopes and workers converge with no stuck/failed/dead-lettered work;
- the fixture is restored and its fingerprints match the pre-test state.

Performance above three seconds is recorded as `performance_follow_up`, not hidden and not treated as a correctness blocker.

## Candidate workflow lock

- Candidate A is one local batch and one production deployment.
- During its production matrix, findings go into one issue ledger; no code change occurs before the full matrix ends unless data safety requires rollback.
- If there are correctness blockers, fix all shared root causes together, rerun one targeted local batch, and deploy at most one consolidated Candidate B.
- If Candidate A passes, do not create a no-op Candidate B.

## Remaining blocking risk

Only production evidence remains: official Candidate A commit/push/deploy, the full production matrix, fixture recovery and final Phase 27 audit. Local evidence cannot prove real worker scheduling, production history/data shape, permissions, Nginx/auth behavior or every page's real access-to-fresh convergence.

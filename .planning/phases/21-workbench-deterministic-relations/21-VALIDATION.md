---
phase: 21
slug: workbench-deterministic-relations
status: verifying
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-14
---

# Phase 21 — Validation Strategy

> Validation contract for deterministic formal relations, exact Workbench visibility, legacy-chain removal and data-safe recovery.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | Python `unittest`/pytest-compatible repository suite via `scripts/verify.sh` |
| **Frontend framework** | Vitest + Testing Library; Playwright for browser E2E |
| **Disposable database** | Existing PostgreSQL test helpers and migration harness |
| **Config files** | `pyproject.toml`, `web/vitest.config.ts`, `web/playwright.config.ts` |
| **Quick run command** | `PYTHONPATH=backend/src python3 -m unittest <targeted modules> -v` |
| **Wave run command** | `bash scripts/verify.sh backend` and `cd web && npm test -- --run` for affected waves |
| **Full suite command** | `bash scripts/verify.sh all` plus the repository's disposable-PostgreSQL and E2E gates selected by the plans |
| **Estimated runtime** | Targeted: under 2 minutes; full closure: environment-dependent |

## Sampling Rate

- **After every task:** run the narrowest affected backend or frontend tests; migrations must run their SQL contract tests.
- **After every wave:** run lint plus the affected backend/frontend suites and inspect the exact visibility invariant.
- **Before phase verification:** run all applicable repository verification entries, disposable PostgreSQL integration, E2E, static legacy guard and docs checks.
- **Max unattended feedback interval:** one task; no three consecutive behavior-changing tasks may share a deferred test gate.
- Commands must be non-watch and fail closed; skipped/relaxed assertions cannot mask worker, freshness, cleanup or data-integrity failures.

## Per-Requirement Verification Map

| Requirement | Secure / safe behavior | Test types | Mandatory automated evidence | Status |
|-------------|------------------------|------------|--------------------------------|--------|
| RELVIS-01 | Paired and unpaired are an exact, disjoint, duplicate-free partition of eligible facts | core, projection, Audit | set equality, duplicate and orphan assertions for month and all scopes | ✅ local automated |
| RELVIS-02 | Safe matcher calls only the formal command/UoW; no persisted candidate/decision state | core, service, architecture | direct command/history/outbox test and zero legacy access static/runtime guard | ✅ local automated |
| RELVIS-03 | Cross-month arbitrary N:M:K succeeds without business cardinality cap; resource exhaustion creates nothing | core, service | explicit-reference history scan, 365-day composite cases, >6-member shape, budget fail-closed | ✅ local automated |
| RELVIS-04 | Weak, ambiguous, conflicting and unsafe negative/refund evidence remains unpaired | core, E2E | rule-table negative tests plus no relation/history/outbox side-effect assertions | ✅ local automated |
| RELVIS-05 | Complete legacy chain and DB objects are absent without deleting unrelated candidate concepts | architecture, migration, regression | whole-repo semantic guard, forward migration assertions, import/startup smoke | ⚠️ local pass；production catalog pending |
| RELVIS-06 | Existing active relations stay unchanged/paired; explicit withdrawal is audited and blocks exact-row-set recreation | core, service, regression | before/after relation hashes, origin/prefix cases, withdraw/idempotency/recreate-block cases | ✅ local automated |
| RELVIS-07 | All-scope unions active shard members by canonical identity and list/detail/Audit agree | read model, API, Audit | synthetic 13-row/1709.49 counterexample across shards; same generation token | ✅ local automated；production identities pending |
| RELVIS-08 | Bulk reader, pure matcher, command/UoW, repositories and workers respect directional I/O | architecture, service, worker | query-count/bulk tests, no SQL outside repository, gateway/durable queue/freshness assertions | ✅ local automated |
| RELVIS-09 | Forward migration only removes retired derived state and preserves canonical facts/relations | migration, disposable PG, security | migration contract, before/after canonical/relation hashes, registered rehydrate and Audit | ⚠️ contract pass；disposable/production execution pending |
| RELVIS-10 | 520 appears paired; 13 omitted invoices recover; queues/read models/Audit converge | integration, API/UI, E2E, regression | exact named fixture/evidence checks, operation barrier, fresh/queue-drained/System Audit | ⚠️ local pass；production still unpaired |

## Seven-Category Coverage Gate

1. **Business core unit:** matching evidence, cross-month windows, exact sums, N:M:K, ambiguity, resource limits, refund/reversal, lifecycle and withdrawal fingerprint.
2. **Service layer:** bulk repository reads, direct formal command, UoW atomicity, audit/history/outbox, idempotency, concurrency, partial failure and rollback.
3. **API contract:** paired/unpaired response semantics, summary/list/detail generation consistency, two-pane confirmation, permissions, stale/refreshing/conflict/error contracts.
4. **Read model/cache/worker:** active-generation publish, all-scope union, dirty/fresh transitions, dedupe, drain, row/detail parity and no per-row rebuild.
5. **Frontend interaction:** only paired/unpaired rendering, no candidate chips/states, filters/search/sort/pagination/drawer, loading/empty/error/stale/refreshing and permissions.
6. **End-to-end:** cross-month import/source facts -> matching worker -> formal relation -> Workbench/downstream; ambiguous stays separate; confirm/withdraw recovery.
7. **Existing regression:** pre-existing active relations and ETC/batch/turnover/no-OA modes, exports, permissions, downstream pages, Audit and legacy API shapes that remain supported.

Every category is applicable because Phase 21 changes core rules, services, APIs/read payload semantics, read models/workers, frontend rendering and cross-module behavior.

## Wave 0 Requirements

- [x] Freeze a synthetic multi-shard 13-invoice fixture totaling 1709.49 and assert the exact all-scope partition.
- [x] Freeze a 520 active OA+invoice fixture whose case/group ID retains the historical `case:decision:` form and prove no new relation is created.
- [x] Add a pure matcher rule-table fixture covering explicit reference, composite evidence, ambiguity, resource limit and refund/reversal.
- [x] Add a legacy semantic inventory/guard fixture distinguishing Workbench relation candidates from unrelated option/evidence candidates.
- [ ] Run disposable-PostgreSQL 0001–0104 migration fixtures and prove retired tables are absent while canonical/relation hashes and counts are unchanged.

Existing test infrastructure is reused; no new test framework or dependency is allowed.

## Manual / Controlled Verification

| Behavior | Requirement | Why controlled | Instructions |
|----------|-------------|----------------|--------------|
| Real current-data manifest contains the exact 520 and 13-invoice identities | RELVIS-07, RELVIS-10 | Exact 13 production IDs are not committed fixtures | Use the authorized read-only production token wrapper; capture hashes/counts/IDs without secrets or row payload dumps |
| Release apply/backfill/worker drain | RELVIS-09, RELVIS-10 | Changes runtime/database state | Run only after local/disposable gates, using formal deploy/migration/refresh entry points and the approved manifest |
| Browser confirmation of paired/unpaired layout | RELVIS-01, RELVIS-10 | Final user-observable production evidence | Open Workbench through the supported app path after freshness and System Audit pass; verify 520 paired and recovered invoices visible |

Controlled verification supplements but does not replace automated fixtures and exact set audits.

## Data-Safety Gates

- Pre-apply canonical bank/OA/invoice hashes and pre-existing active relation/history hashes are captured in a read-only transaction.
- Migration 0104 may delete only the two retired read-model tables and the exact retired app-setting; it creates no relation IDs and writes no canonical fact/history.
- Existing relation writes remain idempotent and atomic through the command/UoW; the cutover has no data-backfill relation path.
- Schema rollback must roll forward; business relation rollback is not applicable because the migration creates or changes no relation.
- Read models are rebuilt through registered refresh gateways/durable queues; no direct mark-fresh or projection SQL patch.
- Phase cannot pass with dirty/processing/failed/dead-lettered required scopes, mixed release versions, hidden facts, duplicate facts or any runtime access to legacy candidate/decision tables.

## Validation Sign-Off

- [x] Every RELVIS requirement has automated evidence mapped.
- [x] All seven repository test categories are applicable and mapped.
- [x] No watch-mode flags are specified.
- [x] Production writes are separated from local/disposable verification and guarded by a manifest.
- [ ] Wave 0 fixtures and old-behavior failing checks exist.
- [x] Plans assign every local task a concrete command and acceptance criteria.
- [ ] Full phase verification passes and controlled production evidence is authorized/completed.

**Approval:** Grill-me decisions and local execution evidence approved；disposable PostgreSQL and controlled production cutover evidence remain pending.

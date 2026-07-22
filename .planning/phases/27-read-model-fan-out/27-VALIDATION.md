---
phase: 27
slug: read-model-fan-out
date: 2026-07-22
status: draft
---

# Phase 27 Validation Strategy

## Blocking Invariants

1. Every current page, mutation, writable Drawer, manifest entry and direct lifecycle/enqueue site is mapped; unmapped count is zero.
2. Ordinary command commits facts/version/audit atomically and creates zero downstream refresh jobs.
3. Access to a fresh scope creates zero jobs; access to a stale dependency creates at most one current-effective job per model/scope/target version.
4. No stale payload is marked fresh; strict consumers fail closed.
5. Old target version cannot publish over current source version.
6. Ordinary mutation never falls back to bare `all`.
7. Unrelated page source/read-model/queue state remains unchanged for every controlled operation.
8. Workbench active-generation semantics remain unchanged.

## Seven Test Categories

| Category | Required proof |
|---|---|
| Business core unit | operation classification, scope/version, rule CAS, idempotency, conflicts, no `all` fallback |
| Service layer | facts/version/audit transaction, rollback, zero write fan-out, exact dependency intents, failure recovery |
| API contract | fresh/stale/refreshing/missing/failed, 200/202/409, permissions, strict consumer behavior |
| Read model/cache/worker | access-time enqueue, dedupe/coalescing, CAS publish, restart recovery, Redis after gate, bounded batch |
| Frontend interaction | 17 pages, all writable/read-only Drawers, route/focus/visibility/scope, no sort/page rebuild, status UX |
| E2E | bank rules, relations, invoice/receipt, imports, explicit reapply, hidden/visible and two-window flows |
| Regression | old response shapes, filters/sort/page/export/permissions, no empty models, no unrelated dirty/jobs |

## Performance Gates

| Metric | Target |
|---|---:|
| ordinary command | p95 ≤ 500ms; p99 ≤ 1s |
| freshness gate | p95 ≤ 100ms |
| already-fresh page first payload | p95 ≤ 500ms |
| ordinary exact rebuild handler | p95 ≤ 1s |
| access-to-fresh ordinary scope | p95 ≤ 1.5s; p99 ≤ 3s |
| ordinary command downstream jobs | 0 |
| current-effective job per target version | ≤ 1 |
| unrelated dirty/job delta | 0 |

Full-history batches report total throughput and current-scope priority separately; they do not inherit the ordinary 3-second target.

## Verification Levels

### L1 Targeted

- Changed unit/service/API/component tests.
- Architecture and inventory guards.
- Narrow lint/type checks.

### L2 Slice

- Affected backend/frontend module suites.
- Read model/worker integration.
- Critical E2E for the vertical slice.
- Docs verification.

### L3 Repository Release

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh e2e
bash scripts/verify.sh docs
bash scripts/verify.sh runtime-check
bash scripts/verify.sh infra-smoke
bash scripts/verify.sh all
```

### L4 Production

- Exact deployed main SHA.
- Release and worker readiness.
- 17-page read baseline and System Audit.
- Every registered operation/Drawer controlled scenario.
- Per page/operation p50/p95/p99/max and access-to-fresh.
- Queue amplification and unrelated-page deltas.
- Rollback evidence and final zero-issue System Audit.

## Completion Rule

Phase 27 is incomplete until L4 production verification passes. Local success, commit, push, CI or deploy alone cannot mark the phase complete.

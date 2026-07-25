---
phase: 27
slug: read-model-fan-out
date: 2026-07-22
status: active
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
| Frontend interaction | 17 pages, all writable/read-only Drawers, route/query/manual reload/retry, focus/visibility/BFCache zero business reload, status UX |
| E2E | bank rules, relations, invoice/receipt, imports, explicit reapply, route re-entry/manual reload and two-open-window no-auto-refresh flows |
| Regression | old response shapes, filters/sort/page/export/permissions, no empty models, no unrelated dirty/jobs |

## Performance Observation And Correctness Gates

| Metric | Current Phase 27 rule |
|---|---|
| ordinary command latency | Measure and compare with `719c9a34`; p95 ≤ 500ms / p99 ≤ 1s remains a product target, not an isolated fixed-millisecond failure gate |
| freshness gate latency | Measure; p95 ≤ 100ms remains a follow-up target |
| already-fresh page first payload | Measure; p95 ≤ 500ms remains a follow-up target |
| ordinary exact rebuild handler | Measure; p95 ≤ 1s remains a follow-up target |
| access-to-fresh ordinary scope | Must eventually become fresh within the existing bounded validation timeout; p95 ≤ 1.5s / p99 ≤ 3s is recorded as `performance_follow_up`, not a completion gate |
| ordinary command downstream jobs | **Hard gate: 0** |
| current-effective job per target version | **Hard gate: ≤ 1** |
| unrelated dirty/job/page I/O delta | **Hard gate: 0** |
| final payload | **Hard gate: complete canonical facts/relations/version/scope equality** |
| recovery | **Hard gate: failed load can retry through route re-entry, browser reload or explicit retry; no permanent refreshing or stuck queue/worker** |

Full-history batches report total throughput and current-scope priority separately; they do not inherit the ordinary 3-second target. Any latency above the observational targets is reported honestly and deferred without adding code solely for that number. A regression introduced relative to `719c9a34`, infinite wait, timeout, incorrect payload, failed recovery or non-convergent runtime remains blocking.

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
- Use raw values plus median/max when the controlled production sample is too small for meaningful p95/p99.
- Queue amplification and unrelated-page deltas.
- Rollback evidence and final zero-issue System Audit.

## Completion Rule

Phase 27 is incomplete until L4 production correctness verification passes. Local success, commit, push, CI or deploy alone cannot mark the phase complete. A result above 3 seconds does not by itself fail L4 when the page still converges within the existing bounded timeout with correct canonical data, retry/reload works, and the queue/worker/Audit close cleanly.

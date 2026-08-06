# Phase 40: 关联台自收敛补充 - Pattern Map

**Mapped:** 2026-08-06
**Scope:** `40-01` probe/FinanceTable、`40-02` proven SQL、`40-03` import batch rows、`40-04` legacy/local handoff，以及 `40-05..40-08` Workbench self-convergence/Browser SLO/唯一发布
**Files classified:** 15（8 个生产/合同/Browser harness 文件，7 个测试文件）
**Runtime architecture added:** 0

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/src/fin_ops_platform/services/workbench_query_facade.py` | service/facade | request-response + exact event enqueue | 同文件 `_groups_refresh_status_payload` / `_refresh_scope_keys` | exact |
| `web/src/pages/ReconciliationWorkbenchPage.tsx` | page/component | request-response polling | `BackgroundJobProgressProvider.tsx` completion-driven timer + `AppHealthOperationsPage.tsx` in-flight ref | composite exact |
| `web/src/features/workbench/api.ts` | API mapper | transform | 同文件 `mapWorkbenchExceptionApplyResult` | exact deletion owner |
| `web/src/features/workbench/exceptionTypes.ts` | DTO/type | transform | 同文件 `WorkbenchExceptionApplyResult` | exact deletion owner |
| `backend/src/fin_ops_platform/services/workbench_sql_projection.py` | projection/query | batch source-proof | 同文件 `source_versions_for_scopes` | conditional only |
| `tests/test_workbench_query_facade.py` | service test | request-response + event assertion | existing initial/groups freshness tests | exact |
| `tests/test_read_model_refresh_gateway.py` | gateway test | event-driven | existing normalize/validate/dedupe tests | exact, normally unchanged |
| `web/src/test/WorkbenchSelection.test.tsx` | interaction test | timer/browser lifecycle | existing generation refresh and zero-barrier tests | role/data-flow match |
| `tests/test_workbench_source_proof_contract.py` | PostgreSQL contract test | canonical mutation -> proof transform | `test_workbench_query_postgres_integration.py` setup + `test_workbench_sql_runtime.py` proof assertions | composite exact |
| `tests/test_postgres_repositories_boundaries.py` | boundary regression | CRUD transaction negative guard | existing relation zero page-refresh-scope test | exact |
| `backend/src/fin_ops_platform/services/postgres_repositories/core.py` | canonical import repository | batched CRUD | 同文件 `_save_batch_rows` + `PostgresTransaction.execute_many_values` | exact deletion owner |
| `tests/test_postgres_repositories_core.py` | repository performance contract | query-count + owner guard | existing bounded multi-value test | exact |
| `web/e2e/fixtures/operationLatency.ts` | Playwright evidence helper | same-clock marks -> redacted JSON | existing `createOperationLatencyRecorder` | exact extension owner |
| `web/e2e/bank-flow-rule-batches-flow.spec.ts` | Browser business/SLO flow | submit POST -> status -> generation -> DOM | existing bank-flow submit/reload test | exact |
| `tests/test_playwright_e2e_strict_diagnostics.py` | Browser smoke guard | opt-in/secret/redaction/recovery contract | existing production smoke static guards | exact |

## Pattern Assignments

### `workbench_query_facade.py` — reuse the existing self-heal seam

**Analog:** `backend/src/fin_ops_platform/services/workbench_query_facade.py:1011-1041`

```python
refresh_status_payload = self._groups_refresh_status_payload(
    scope_key,
    enqueue_non_fresh=True,
)
```

The implementation should replace the duplicate repository/proof path in `refresh_status` with the existing helper, while preserving its current timeout mapping and `_normalize_refresh_status(...)` response. Do not add another facade method, gateway, endpoint, or enqueue loop.

**Exact-scope fail-closed pattern:** `workbench_query_facade.py:1044-1078`

```python
if requested_scope_key != "all":
    return [requested_scope_key]
# all uses explicit mismatch/failed month shards; active refresh returns [];
# only missing active generation may recover with ["all"].
```

Keep this method as the sole scope-selection owner. The query facade calls its injected enqueue port; application composition already routes that port through `ReadModelRefreshGateway`.

### `read_model_refresh_gateway.py` — do not hand-roll dedupe

**Analog:** `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py:45-114`

```python
normalized_scope_keys = self._scope_policy_registry.normalize_and_validate(
    normalized_scope_type,
    scope_keys,
)
...
enqueue_many_if_inactive(
    scope_type=normalized_scope_type,
    scope_keys=normalized_scope_keys,
    reason=reason,
    ...,
)
```

This existing boundary owns normalize, validation, duplicate removal and active-event coalescing. The additional plan should normally make no gateway production change; it should prove the facade reaches this path with exact month scopes.

**Test analog:** `tests/test_read_model_refresh_gateway.py:64-124` asserts deduped order and invalid Workbench scope rejection. Extend only if a new reason is not covered by existing active-coalescing tests; do not create a second dedupe suite.

### `ReconciliationWorkbenchPage.tsx` — local completion-driven poller

**Primary scheduling analog:** `web/src/features/backgroundJobs/BackgroundJobProgressProvider.tsx:171-220`

```tsx
const clearPollTimer = () => {
  if (timerRef.current !== null) {
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }
};
const schedule = () => {
  clearPollTimer();
  timerRef.current = window.setTimeout(async () => {
    await refresh();
    schedule();
  }, delay);
};
```

Adapt this inside the existing Workbench effect: one local `setTimeout`, scheduled only after the prior request settles. Hidden means clear timer/abort and no reschedule; visible/focus means immediate `pollNow`.

**Single-flight analog:** `web/src/pages/AppHealthOperationsPage.tsx:817-844`

```tsx
if (inFlightRef.current) return;
const controller = new AbortController();
inFlightRef.current = controller;
try {
  await fetch...;
} finally {
  if (inFlightRef.current === controller) inFlightRef.current = null;
}
```

Use the same guard for adjacent `focus` and `visibilitychange`; do not abort a healthy slow request on each tick. Do not extract a generic polling hook.

**Reload-once analog:** `ReconciliationWorkbenchPage.tsx:920-947`

```tsx
if (
  status.readModelStatus === "fresh"
  && nextVersionKey
  && previousVersionKey
  && previousVersionKey !== nextVersionKey
) {
  scheduleWorkbenchReadModelReload();
}
```

Retain the version ref plus existing 300 ms debounced reload. Polling `stale`/`refreshing` must not call combined initial; only a fresh, changed version reloads once.

### Workbench-local dead target DTO deletion

**Owners:**

- `web/src/features/workbench/api.ts:1749-1766`
- `web/src/features/workbench/exceptionTypes.ts:77-87`

Delete only the proven-dead `operationBarrierTargets` mapper/type field and its fallback to `freshnessTargets`. Do not delete the global backend operation-barrier endpoint, maintenance/repair/rehydrate paths, or independent domain jobs. If `freshnessTargets` is also proven unused by the final whole-repo scan, delete it in the same local DTO owner; otherwise leave it without fallback behavior.

### `tests/test_workbench_query_facade.py` — public status self-heal contract

**Analogs:**

- `tests/test_workbench_query_facade.py:121-142`: recorder + exact enqueue assertion.
- `tests/test_workbench_query_facade.py:293-317`: no broad `all` fan-out and cold-start-only `all` recovery.
- `tests/test_workbench_query_facade.py:1527-1580`: fast status port and timeout response/metric contract.

Add table-shaped cases at the public `refresh_status` method:

1. stale `all` with mismatch months enqueues each exact month once;
2. fresh and refreshing enqueue nothing;
3. active refresh does not fall back to `all`;
4. failed exact dirty scope is retried exactly;
5. timeout and HTTP payload shape remain unchanged;
6. heavy diagnostic repository method is never called.

### `WorkbenchSelection.test.tsx` — browser lifecycle and request-count assertions

**Analogs:**

- `web/src/test/WorkbenchSelection.test.tsx:1364-1425`: intercept refresh-status and count calls.
- `web/src/test/WorkbenchSelection.test.tsx:1465-1507`: status sequence before fresh generation.
- `web/src/test/WorkbenchSelection.test.tsx:1200-1270`: assert zero operation-barrier requests.
- `web/src/test/OaPendingPaymentsPage.test.tsx:712-718`: reset mocked `document.visibilityState` after tests.

Use Vitest fake timers and deferred fetch promises to assert observable behavior: immediate entry, exactly one in-flight request, next request only 1000 ms after settle, hidden request count stays zero, visible/focus triggers immediate check but coalesces, every status uses the same cadence, and repeated fresh status with the same version causes zero reload while a new version causes one reload. Also assert polling never calls the combined initial endpoint until generation change.

### `operationLatency.ts` + bank-flow Playwright spec — one browser-inclusive monotonic owner

Reuse `web/e2e/fixtures/operationLatency.ts`; do not add a Python timing runner or runtime correlation field. Add one optional segmented recorder using the same Playwright Node `performance.now()` converted once to integer microseconds. `web/e2e/bank-flow-rule-batches-flow.spec.ts` owns the full sample:

1. capture fresh baseline generation `g0` while Workbench is visible;
2. mark `t0` immediately before authenticated `workbenchPage.context().request.post(...)` to the existing bank-flow submit endpoint and `t1` when its response resolves;
3. inspect raw responses from existing `/api/workbench/refresh-status?month=all`; mark `t2` only when the manifest exact month is stale/enqueue-observed or refreshing, rejecting `all`;
4. mark `t3` only when the same endpoint is fresh at `g1 != g0`;
5. require the next combined payload for `g1` to contain the submitted transaction/relation identity, then mark `t4` when the unique business label is visible in the Workbench DOM.

The sample key is `{sample_id,batch_id,transaction_ids,business_identity,exact_scope,g0,g1}`. Adjacent integer-microsecond differences must telescope exactly to `t4-t0`. The existing 300ms page debounce is therefore inside segment 4. A root-owned test fixture manifest provides existing submit/withdraw paths and payloads; isolated prod-equivalent runs require at least 100 recovered samples, while production is one approved bounded sample and cannot claim p99. The report path is exactly `.planning/phases/40-performance-contract-hot-path-closure/40-workbench-visibility-p99.json`.

### `core.py` — remove the import batch-row compatibility fallback

The existing production transaction already exposes `execute_many_values(sql, params_seq, chunk_size=1000)` with the 60,000-parameter bound. `CorePostgresRepository._save_batch_rows` must call that contract directly and remove the `getattr(...)/sum(connection.execute(...))` per-row fallback. `tests/test_postgres_repositories_core.py` is the exact query-count/owner-conflict analog; no Bank/Pending DTO, Turnover, Cost or App Health file belongs to this Phase without an already named benchmark.

### `test_workbench_source_proof_contract.py` — test-owned matrix, not runtime registry

**PostgreSQL fixture analog:** `tests/test_workbench_query_postgres_integration.py:15-31`

```python
@classmethod
def setUpClass(cls) -> None:
    cls.database_url = require_postgres_test_database_url()
    apply_test_migrations(cls.database_url)

def setUp(self) -> None:
    truncate_test_database(self.database_url)
    self.connection = PostgresConnection(
        PostgresSettings(database_url=self.database_url, pool_enabled=False)
    )
```

**Proof assertion analog:** `tests/test_workbench_sql_runtime.py:1748-1775`, which bulk-loads deduped scopes and asserts concrete proof keys plus one SQL call.

Create one test-only matrix mapping dependency family -> real production writer/mutation -> changed canonical table/field -> expected old/new exact scope -> proof key. For each family: read proof, execute real writer mutation, read proof again, assert affected scope changes and an unrelated scope does not. Then apply `WorkbenchQueryFreshnessService` to prove fresh -> stale. Do not create a runtime manifest or inject Workbench dependencies into writers.

`workbench_sql_projection.py` is conditional: change it only when this real mutation test proves a projection dependency is absent from proof. Prefer fixing the existing proof query (or canonical `updated_at`/version owner) over any write-side notification.

### Negative guards — preserve producer/consumer decoupling

**SQL boundary analog:** `tests/test_postgres_repositories_boundaries.py:1324-1351`

```python
all_sql = " ".join(...)
assert "job.read_model_dirty_scopes" not in all_sql
assert "job.outbox_events" not in all_sql
```

Extend the bank-flow real mutation contract to assert zero dirty/outbox writes and no target/barrier fields. Existing frontend/API analogs already assert `operationBarrierTargets` absent and `/api/operation-barrier/status` uncalled. Add a narrow whole-repo guard for retired `bank_flow_rule_batch.read_model.refresh` runtime references, without treating migration history/negative tests as live code.

## Shared Patterns

### Dependency direction

```text
canonical writer -> canonical facts/version/audit
Workbench status -> freshness proof -> existing facade helper
                 -> ReadModelRefreshGateway -> PostgreSQL durable queue
                 -> existing worker -> atomic active generation
browser          -> status single-flight -> changed fresh version -> one reload
```

No producer imports the Workbench gateway. No frontend constructs refresh scopes. PostgreSQL dirty/outbox remains the durable refresh truth.

### Error and status handling

- Preserve `refresh_status` transient timeout mapping to retryable `503 unavailable`.
- A stale response may remain stale after enqueue; the next status request observes durable progress.
- `fresh`, `stale`, `refreshing`, `failed`, and `unavailable` all use completion + 1000 ms while visible.
- Non-fresh generations remain read-only; atomic publish stays in the existing worker.

### Explicitly skipped

- No new endpoint, worker, read model, table, trigger, cache, transport, dependency, event bus, generic hook or coordinator.
- No bank-flow POST/route/application-service/transaction/page reload production changes.
- No global operation-barrier removal without separate external-consumer proof.
- No ordinary stale `workbench:all` fallback.

## No Analog Found

| File/Concern | Reason | Planner guidance |
|---|---|---|
| Full writer->proof coverage matrix | No single existing test enumerates every Workbench dependency family | Compose existing PostgreSQL fixture and source-proof assertion patterns; keep matrix test-only |
| Exact Workbench visible/hidden 1-second lifecycle test | Existing Workbench tests cover polling/generation but not the complete visibility contract | Use native visibility mocking + fake timers in existing `WorkbenchSelection.test.tsx` |
| Browser-inclusive t0..t4 report | Existing operation recorder has one Node monotonic clock but not segmented Workbench marks | Extend the existing helper/spec only; no new endpoint, runner or runtime field |

## Metadata

**Analogs inspected:** 11 files
**Primary search scope:** Workbench services/page/tests, refresh gateway, PostgreSQL integration tests, legacy target DTO owners
**Pattern extraction date:** 2026-08-06

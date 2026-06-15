# Testing Patterns

**Analysis Date:** 2026-06-15

## Test Framework

**Runner:**
- Python `unittest` for backend tests.
- Backend config: `pytest.ini` only sets Python path for `.` and `backend/src`; the turnover-ledger target commands use `python3 -m unittest`.
- Frontend `vitest` 2.1.4 with jsdom, Testing Library, and user-event.
- Frontend config: `web/vite.config.ts`.

**Assertion Library:**
- Backend: `unittest.TestCase` assertions plus direct dictionary/list assertions in files such as `tests/test_turnover_ledger_api.py` and `tests/test_turnover_ledger_uow_contract.py`.
- Frontend: Vitest `expect`, `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event` in `web/src/test/TurnoverLedgerPage.test.tsx`.

**Run Commands:**
```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade tests.test_turnover_ledger_read_model_refresh tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v
cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/OperationBarrierApi.test.ts src/test/domainEvents.test.ts
bash scripts/verify.sh docs
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh all
```

## Test File Organization

**Location:**
- Backend tests live in root `tests/` and are not co-located with source files.
- Frontend tests live in `web/src/test/`.
- Module test inventory and coverage guidance live in `docs/modules/turnover-ledger/tests.md`.

**Naming:**
- Backend turnover-ledger tests use `test_turnover_ledger_<area>.py` or related impacted-domain names: `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`.
- Frontend tests use subject names: `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/TurnoverLedgerPage.test.tsx`.

**Structure:**
```text
tests/
├── test_turnover_relation_service.py
├── test_turnover_ledger_service.py
├── test_turnover_ledger_extra_service.py
├── test_turnover_ledger_api.py
├── test_turnover_ledger_uow_contract.py
├── test_turnover_ledger_query_service.py
├── test_turnover_ledger_read_facade.py
├── test_turnover_ledger_read_model_refresh.py
├── test_turnover_ledger_source_versions.py
├── test_turnover_ledger_export_service.py
├── test_turnover_workbench_integration.py
└── test_workbench_turnover_grouping.py

web/src/test/
├── TurnoverLedgerApi.test.ts
├── TurnoverLedgerPage.test.tsx
├── GlobalOperationOverlayContext.test.tsx
├── OperationBarrierApi.test.ts
└── domainEvents.test.ts
```

## Test Structure

**Suite Organization:**
```python
class TurnoverLedgerApiTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def test_target_confirm_request_expected_versions_reach_write_command(self) -> None:
        ...
```

```typescript
describe("turnover ledger API", () => {
  test("maps turnover ledger tag selection and saves selected codes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      ...
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(saveTurnoverLedgerTagSelection(...)).resolves.toMatchObject(...);
  });
});
```

**Patterns:**
- Backend tests define small in-file recorders/fakes for ports, queues, transactions, stale precondition checks, and UoW behavior, as in `tests/test_turnover_ledger_api.py` and `tests/test_turnover_ledger_uow_contract.py`.
- Frontend page tests render the actual page under `GlobalOperationOverlayProvider`, `SessionContext.Provider`, and `PageSessionStateProvider` using `renderTurnoverLedgerPage` in `web/src/test/TurnoverLedgerPage.test.tsx`.
- Frontend API tests stub global `fetch`, assert request method/body/path, and verify camelCase mapped results in `web/src/test/TurnoverLedgerApi.test.ts`.
- Tests prefer behavior and contract assertions over private implementation assertions.

## Mocking

**Framework:** `unittest.mock.patch` for backend; Vitest `vi` for frontend.

**Patterns:**
```python
class _QueueRecorder:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_kwargs: object) -> None:
        self.enqueued.append((scope_type, scope_key, reason))
```

```typescript
afterEach(() => {
  vi.unstubAllGlobals();
});

const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
  expect(url.pathname).toBe("/api/turnover-ledger/tag-selection");
  return Response.json({ ... });
});
vi.stubGlobal("fetch", fetchMock);
```

**What to Mock:**
- Mock infrastructure and side-effect ports: runtime queue, dirty/outbox writer, idempotency store, transaction object, state store, Workbench command service, and browser `fetch`.
- Mock session/permission context in frontend tests through `SessionContext` payloads in `web/src/test/TurnoverLedgerPage.test.tsx`.
- Use fakes that record calls and transactions so tests can assert rollback, refresh fan-out, expected versions, affected months, and operation barrier behavior.

**What NOT to Mock:**
- Do not mock the turnover business rules being tested. For relation rules, use `tests/test_turnover_relation_service.py`, `tests/test_turnover_ledger_service.py`, and `tests/test_turnover_ledger_extra_service.py`.
- Do not mock away grouped payload mapping in API client tests; assert snake_case backend payloads map to camelCase frontend types in `web/src/test/TurnoverLedgerApi.test.ts`.
- Do not bypass freshness/operation barriers in page tests when behavior depends on stale, refreshing, or fresh state.

## Fixtures and Factories

**Test Data:**
```typescript
function groupedPayload(family: string, overrides: Record<string, unknown> = {}) {
  const allGroups = [
    {
      group_id: "counterparty:personal:zhangsan",
      counterparty_name: "张三",
      family: "personal",
      pending_direction: "repayment",
      rows: [...],
      flow_rows: [...],
    },
  ];
  ...
}
```

```python
@dataclass
class _Command:
    action_name: str
    scope_keys: list[str] = field(default_factory=lambda: ["all"])
    expected_versions: dict[str, object] = field(default_factory=dict)
    actor_id: str = "finance-user"
    tenant_id: str = "default"
```

**Location:**
- Turnover-ledger fixtures are mostly inline in target test files to keep scenario contracts near assertions: `web/src/test/TurnoverLedgerPage.test.tsx`, `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_uow_contract.py`.
- Do not add root-level temporary Excel/PDF/ZIP/screenshots. `AGENTS.md` requires large samples to stay in local `fixtures/` and tests must not depend on real business files.

## Coverage

**Requirements:** No numeric coverage threshold is enforced. Coverage is risk/category driven through `docs/modules/turnover-ledger/tests.md` and the seven-category repository guidance in `AGENTS.md`.

**View Coverage:**
```bash
# Not configured as a standard project command.
# Use targeted unittest/Vitest commands plus scripts/verify.sh all for release confidence.
```

## Test Types

**Unit Tests:**
- Business rule unit tests belong in `tests/test_turnover_relation_service.py`, `tests/test_turnover_ledger_service.py`, and `tests/test_turnover_ledger_extra_service.py`.
- Cover external turnover family/action rules, suggested vs confirmed candidates, duplicate rows, cross-counterparty rows, non-zero difference, same-direction rows, withdrawal rules, extra validation, grouping amounts, interest, and internal-transfer exclusion.

**Service-layer Tests:**
- UoW and orchestration tests belong in `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_api.py`, and `tests/test_turnover_workbench_integration.py`.
- Cover transaction boundaries, rollback, dirty/outbox in the same transaction, stale preconditions, idempotency replay/conflict, repository/port calls, Workbench command-service delegation, and fail-fast missing command service.

**API Contract Tests:**
- API tests belong in `tests/test_turnover_ledger_api.py` and read facade tests in `tests/test_turnover_ledger_read_facade.py`.
- Assert status/shape fields, not only HTTP success. Include `error`, `message`, `rows`, `groups`, `summary`, `pagination`, `read_model_status`, `read_model_stale_reasons`, `affected_months`, `freshness_targets`, `version`, and relation/extra payloads as relevant.

**Read Model / Cache / Background Job Tests:**
- Use `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_model_refresh.py`, `tests/test_turnover_ledger_source_versions.py`, `tests/test_runtime_worker_registry.py`, and `tests/test_app_status_overview_service.py`.
- Cover stale SQL read models not being returned as fresh, missing required read models returning refreshing payloads, source versions, projection persistence, worker handler behavior, and registry/App Status registration.

**Frontend Component and Interaction Tests:**
- Use `web/src/test/TurnoverLedgerPage.test.tsx` for page behavior and `web/src/test/TurnoverLedgerApi.test.ts` for client mapping.
- Cover grouped table rendering, tag drawer save, manual closure drawer, submit-before-fresh reload/rebind, stale write blocking, selected flow disappearing after reload, extra drawer, export dialog, loading/empty/error states, permission disabled controls, operation overlay, and domain events.

**E2E Business-flow Integration Tests:**
- Use backend integration tests `tests/test_turnover_workbench_integration.py` and `tests/test_workbench_turnover_grouping.py`, plus frontend operation-flow tests in `web/src/test/TurnoverLedgerPage.test.tsx`.
- Protect critical flows: bank detail external tag -> grouped ledger; grouped real flow rows -> manual zero-difference closure -> Turnover relation + Workbench pair relation -> bank-only open group; withdraw -> read model and Workbench recovery.

**Regression Tests:**
- Add regression tests to the closest impacted suite whenever a bug is found. Also record the scenario in `docs/modules/turnover-ledger/tests.md` under the historical bug regression library.
- Existing regression anchors include deterministic relation not entering Workbench, allocation lots not replacing real flow rows, stale writes blocked, SQL runtime using bank detail read model for closure facts, queue/outbox failure rollback, bank tag fan-out, and operation barrier release only after fresh.

## Seven-Category Coverage Guidance

**1. Business core unit tests:**
- Required for any change to external turnover tag eligibility, grouping, amount calculation, zero-difference closure, withdrawal eligibility, relation source/status, extra validation, or internal-transfer exclusion.
- Target files: `tests/test_turnover_relation_service.py`, `tests/test_turnover_ledger_service.py`, `tests/test_turnover_ledger_extra_service.py`.

**2. Service-layer tests:**
- Required for changes to `TurnoverLedgerWriteFacade`, `TurnoverLedgerWriteUnitOfWork`, repository ports, audit, dirty/outbox, idempotency, stale preconditions, or Workbench command-service delegation.
- Target files: `tests/test_turnover_ledger_uow_contract.py`, `tests/test_turnover_ledger_api.py`, `tests/test_turnover_workbench_integration.py`.

**3. API contract tests:**
- Required for changes to `GET /api/turnover-ledger`, tag-selection, bank-row-tags batch, extra, confirm, withdraw, export-preview, or export.
- Target files: `tests/test_turnover_ledger_api.py`, `tests/test_turnover_ledger_read_facade.py`, `web/src/test/TurnoverLedgerApi.test.ts`.

**4. Read model, cache, and background job tests:**
- Required for changes to grouped reads, source versions, SQL projection, refresh gateway behavior, runtime worker registration, App Status, freshness/stale/refreshing status, or dirty scope fan-out.
- Target files: `tests/test_turnover_ledger_query_service.py`, `tests/test_turnover_ledger_read_model_refresh.py`, `tests/test_turnover_ledger_source_versions.py`, `tests/test_runtime_worker_registry.py`, `tests/test_app_status_overview_service.py`.

**5. Frontend component and interaction tests:**
- Required for changes to `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/components/turnoverLedger/*`, `web/src/features/turnoverLedger/api.ts`, `web/src/features/domainEvents.ts`, permissions, drawers, dialogs, table behavior, stale warnings, or operation overlay.
- Target files: `web/src/test/TurnoverLedgerPage.test.tsx`, `web/src/test/TurnoverLedgerApi.test.ts`, `web/src/test/GlobalOperationOverlayContext.test.tsx`, `web/src/test/OperationBarrierApi.test.ts`, `web/src/test/domainEvents.test.ts`.

**6. End-to-end business-flow integration tests:**
- Required when a change crosses bank detail, turnover ledger, Workbench relation, Workbench read model, read model worker, or frontend operation barrier.
- Target files: `tests/test_turnover_workbench_integration.py`, `tests/test_workbench_turnover_grouping.py`, `web/src/test/TurnoverLedgerPage.test.tsx`.

**7. Existing feature regression tests:**
- Always evaluate Workbench grouping, Bank Details tag batch, Cost Statistics/search downstream, domain events, old grouped response shapes, legacy flat/read model compatibility, export fields, permissions, and stale/refreshing UI.
- Add regression coverage to the closest suite and update `docs/modules/turnover-ledger/tests.md` with the new scenario name.

## Common Patterns

**Async Testing:**
```typescript
renderTurnoverLedgerPage();
await waitFor(() => expect(screen.getByText("张三")).toBeInTheDocument());
await userEvent.click(screen.getByRole("button", { name: /保存/ }));
await waitFor(() => expect(fetchMock).toHaveBeenCalled());
```

**Error Testing:**
```python
with self.assertRaises(RuntimeError):
    uow.run(command, handler)
self.assertEqual(connection.rollbacks, 1)
self.assertEqual(dirty_outbox.calls, [])
```

```typescript
await expect(saveTurnoverLedgerTagSelection({
  expectedVersion: 2,
  selectedTagCodes: ["external_rule_borrow_out"],
})).resolves.toMatchObject({
  version: 3,
  selectedTagCodes: ["external_rule_borrow_out"],
});
```

## Verification Practices

**Targeted turnover-ledger verification:**
- Run backend target command from `docs/modules/turnover-ledger/tests.md` after backend turnover-ledger changes.
- Run frontend target command from `docs/modules/turnover-ledger/tests.md` after page/API/client/operation barrier changes.
- Run `bash scripts/verify.sh docs` after docs changes.

**Broader verification:**
- `bash scripts/verify.sh backend` runs clean app check with a temporary `FIN_OPS_DATA_DIR` and full backend unittest discovery.
- `bash scripts/verify.sh frontend` runs all Vitest tests and `npm run build`.
- `bash scripts/verify.sh all` runs backend, frontend, and docs checks; this is the default release-confidence command in `scripts/verify.sh`.

**Manual/staging smoke still required for:**
- Real PostgreSQL historical data refresh for `turnover_ledger`.
- RabbitMQ/Redis/systemd worker drain and restart recovery.
- Browser XLSX export file inspection.
- Large grouped table performance, scrolling, and visual overlap checks.

---

*Testing analysis: 2026-06-15*

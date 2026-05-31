# 进项发票使用情况闭环执行 Prompt

This prompt is intended for Codex workers executing the remaining production closure of `进项发票使用情况`.

/goal Implement the production-grade closure of the `进项发票使用情况` workflows: make payment status rules a versioned, auditable backend rules source used by the row calculation and read-model refresh, and make `以发票反提 OA` a real preview-confirm-draft batch workflow with permissions, optimistic locking, idempotency, audit, and read-model invalidation.

## Non-Negotiable Architecture Rules

- Work on `main`.
- Before editing, read:
  - `AGENTS.md`
  - `README.md`
  - `ARCHITECTURE.md`
  - `docs/dev/backend.md`
  - `docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md`
  - Existing code under `backend/src/fin_ops_platform/services/` related to input invoice usage, app settings, pending invoice commands, ETC OA draft flow, workbench relations, runtime read models, and audit.
- The backend has been partially refactored. Follow the refactored pattern:
  - `app/server.py` is route wiring, auth/session resolution, response assembly, and service invocation only.
  - Business logic belongs in focused service modules under `backend/src/fin_ops_platform/services/`.
  - Persistence belongs in repository/state-store modules, not in route handlers.
  - Do not implement new business workflows directly in `server.py`.
- Use existing encapsulated capabilities before adding new abstractions:
  - `AppSettingsService` for versioned settings and settings audit patterns.
  - `AuditTrailService` for audit entries.
  - `WorkbenchPairRelationService` for invoice/OA/bank relations.
  - Existing OA client/token extraction patterns from ETC only where the contract is genuinely shared.
  - Runtime read-model refresh queues for invalidation.
- Do not add temporary fake success paths. If the OA draft client is not configured, return a structured error and keep batch state recoverable.
- Do not silently invent unknown OA fields. Build payloads from fields already present in `Invoice`, OA target/applicant config, and documented requirements.
- Keep user changes in the dirty worktree. Do not revert unrelated files.

## Current Known State

- `GET /api/input-invoice-usage/rows` and SQL read-model runtime exist.
- `POST /api/input-invoice-usage/oa-reverse/preview` exists, but returns read-only preview with `canCreateDraft: false` and `nextAction: future_contract_only`.
- `GET /api/input-invoice-usage/payment-status-rules` exists, but rules are static read-only in `InputInvoiceUsageQueryService.payment_status_rules()`.
- The SQL read-model source-version bug has been fixed by adding a shared source-version service and having `InvoiceUsageCollectionSqlProjectionBuilder` persist `source_versions`.

## Desired Final State

### Payment Status Rules

Implement a versioned backend rules source for the input invoice usage payment status matrix.

Rules must include the existing default behavior:

- `cash_turnover_chen_xiuyun`: 陈秀云 OA + 流水 + 关联台完全匹配 -> 现金往来
- `paid_full_match`: 有 OA、有流水，并且关联台完全匹配 -> 已付款
- `offset_zhou_jieying`: 周洁莹 OA、无流水，发票和 OA 金额匹配 -> 冲
- `offset_liu_shugang_no_pay`: 刘树刚不付 OA、无流水 -> 冲
- `offset_wei_dailian`: 韦代连 OA、无流水 -> 冲
- `waiting_payment`: 有 OA、无流水 -> 待付款
- `pending_default`: 规则不能自动闭环 -> 待处理

Rules API:

- `GET /api/input-invoice-usage/payment-status-rules`
  - Returns `version`, `readOnly: false`, rules, pending directions, permissions, and source metadata.
- `PUT /api/input-invoice-usage/payment-status-rules`
  - Requires mutation permission.
  - Requires `expectedVersion`.
  - Requires `idempotencyKey`.
  - Validates rule ids, labels, priority uniqueness, supported applicant constraints, and pending direction codes.
  - Writes audit.
  - Persists the new version.
  - Invalidates or enqueues refresh for affected `input_invoice_usage` read-model scopes.
  - Returns the updated rules payload.

The row calculation and SQL projection builder must use the same rules source. It is not acceptable for the drawer to show one rule set while the rows use another.

### OA Reverse Workflow

Implement the formal `以发票反提 OA` batch workflow.

API:

- `POST /api/input-invoice-usage/oa-reverse/preview`
  - Remains read-only and computes candidates/rejections from backend rows.
  - Returns enough invoice display data for the drawer to show a real candidate list, not just IDs.
  - Returns `canCreateDraft` according to permission and candidate validity.
- `POST /api/input-invoice-usage/oa-reverse/batches`
  - Requires mutation permission.
  - Requires `previewId`, `expectedPreviewHash` or equivalent freshness token, and `idempotencyKey`.
  - Creates or returns an idempotent local batch.
  - Stores selected invoice ids, target applicant, preview summary, version, status, audit metadata.
- `GET /api/input-invoice-usage/oa-reverse/batches/{batchId}`
  - Returns the local batch state.
- `POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-draft`
  - Requires mutation permission.
  - Requires `expectedVersion` and `idempotencyKey`.
  - Creates an OA draft through the configured OA client.
  - Stores `oaDraftId`, `oaDraftUrl`, draft batch/status fields, and audit.
  - Creates/updates local active relations only when there is a provable local OA row or draft identity. If the external draft is not yet visible in the OA projection, store draft metadata on the batch and expose detection status rather than fabricating a completed OA relation.
  - Invalidates/enqueues affected input invoice usage read-model scopes.
- `POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-draft/revoke`
  - Requires mutation permission.
  - Requires `reason`, `expectedVersion`, and `idempotencyKey`.
  - Releases the local active draft binding and keeps audit.
  - Does not delete the external OA source-system draft.
  - Invalidates/enqueues affected read-model scopes.
- `POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/oa-status/refresh`
  - Checks whether the external OA draft entered the OA projection / 进行中 state.
  - Updates batch detection status and relations only when evidence exists.
  - Invalidates/enqueues affected read-model scopes when status changes.
- `POST /api/input-invoice-usage/oa-reverse/batches/{batchId}/manual-oa-status`
  - Requires mutation permission.
  - Requires `expectedVersion`, `idempotencyKey`, and structured decision payload.
  - Allows manual fallback only for detection exception states.
  - Writes audit and invalidates/enqueues affected read-model scopes.

Persist batches durably. Prefer adding a focused repository/state-store path if no existing command store fits. Do not overload unrelated pending-invoice command structures unless the existing repository is explicitly generic and the naming remains correct.

### Frontend

Update the existing right-side drawers, do not add a sidebar item or modal.

- `OaReverseWorkspaceDrawer`
  - Shows backend-provided invoice display data.
  - Supports preview -> create batch -> create OA draft -> open draft URL -> status refresh -> revoke/manual fallback.
  - Uses stable loading/error/disabled states.
  - Does not compute candidate totals client-side.
  - Does not show fake success if backend says draft creation is unavailable.
- `PaymentStatusRulesDrawer`
  - Shows editable controls only after backend returns `readOnly: false` and permission allows saving.
  - Saves through `PUT /api/input-invoice-usage/payment-status-rules` with `expectedVersion` and `idempotencyKey`.
  - Handles version conflicts by asking the user to reload, not by overwriting.

## Serial / Parallel Execution Plan

### Serial Step 0: Baseline Verification

Run before code changes:

```bash
git status --short
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api tests.test_invoice_usage_collection_sql_runtime -v
cd web && npm test -- InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx --run
```

Record failures that are unrelated to this work. Do not fix unrelated failures unless they block the implementation.

### Parallel Task A: Payment Rules Backend

Owned files:

- `backend/src/fin_ops_platform/services/input_invoice_usage_payment_rules.py` or equivalent focused service module.
- `backend/src/fin_ops_platform/services/app_settings_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- focused backend tests.

Implement:

1. Default payment rules payload and normalization.
2. Versioned persistence through app settings or a dedicated settings repository.
3. `InputInvoiceUsageQueryService` rules provider injection.
4. Payment status calculation through the same rules source.
5. Rule-source version in read-model freshness or a reliable dirty-scope invalidation mechanism.
6. Tests for default behavior, validation, version conflict, audit, and read-model invalidation.

### Parallel Task B: OA Reverse Backend

Owned files:

- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py` or equivalent focused service module.
- New focused repository/state-store files if needed.
- `backend/src/fin_ops_platform/app/server.py` only for route mapping and service invocation.
- focused backend tests.

Implement:

1. Preview payload with candidate invoice display rows and a freshness token.
2. Batch create/get state machine with optimistic locking and idempotency.
3. OA draft create/revoke/status-refresh/manual-status transitions.
4. Audit events for every mutation.
5. Read-model invalidation/enqueue for affected invoice months.
6. Structured errors for stale preview, version conflict, permission denied, invalid transition, missing OA client, and unavailable OA evidence.

### Parallel Task C: Frontend

Owned files:

- `web/src/features/inputInvoiceUsage/types.ts`
- `web/src/features/inputInvoiceUsage/api.ts`
- `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx`
- `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx`
- relevant frontend tests.

Implement:

1. API client methods for all new endpoints.
2. Editable payment rules drawer gated by backend permissions and `readOnly`.
3. OA reverse drawer state machine for preview, batch, draft, revoke, refresh, and manual fallback.
4. Tests for no fake success, conflict handling, disabled/loading states, and backend-provided invoice list rendering.

### Serial Step 1: Integration

After Tasks A, B, and C are complete:

1. Wire application service construction in `Application.__init__`.
2. Add thin `server.py` routes only.
3. Ensure app entrypoints include the new API paths.
4. Ensure read-model refresh works in production runtime and fallback runtime.
5. Ensure old tests still pass.

### Serial Step 2: Documentation

Update:

- `docs/superpowers/specs/2026-05-24-input-invoice-usage-design.md`
- `docs/dev/api-contracts.md` if it already documents related APIs.
- `docs/operations/invoice-usage-collection-read-model-backfill.md` if rule changes affect refresh/backfill operations.

Document:

- Exact endpoint contracts.
- Rule version and conflict behavior.
- OA draft lifecycle and what revoke does not do.
- Required worker/read-model refresh behavior after rule or OA reverse mutations.

### Serial Step 3: Final Verification

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_service tests.test_input_invoice_usage_api tests.test_invoice_usage_collection_sql_runtime -v
cd web && npm test -- InputInvoiceUsagePage.test.tsx InputInvoiceUsageFiltersAndDrawers.test.tsx --run
cd web && npm run build
```

If new backend test files are added, include them explicitly in the unittest command.

If a production DB is configured, smoke:

```bash
curl -sS 'http://127.0.0.1:8000/api/input-invoice-usage/payment-status-rules' | jq .
curl -sS 'http://127.0.0.1:8000/api/input-invoice-usage/rows?month=2026-05&page=1&page_size=20' | jq '.read_model_status,.pagination'
```

## Required Final Report

Return:

- Files changed.
- Which tasks were executed in parallel and which were serialized.
- Backend architecture notes: where the new business logic lives and what remains thin in `server.py`.
- Verification commands and exact pass/fail status.
- Any remaining production operational step, especially read-model backfill/refresh.

## Prompt Self-Review

- Spec coverage: This prompt covers both unfinished items from the previous analysis: configurable payment status rules and formal OA reverse workflow. It also includes the operational read-model refresh requirement.
- Architecture coverage: It explicitly prevents implementation in `server.py`, requires service/repository boundaries, and requires existing encapsulated services before new abstractions.
- Risk coverage: It forbids fake OA draft success, requires structured unavailable-client errors, and requires not fabricating OA relations before evidence exists.
- Test coverage: It requires backend and frontend tests plus final build/run commands.
- No placeholder scan: There are no `TBD`, `TODO`, or unspecified “handle errors” steps; each required failure mode is named.

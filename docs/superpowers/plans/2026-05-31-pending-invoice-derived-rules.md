# 待找发票规则派生与层级抽屉 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the production-grade `待找发票规则设置` refactor where users edit only `流水代替发票` and `无需开票`, while `需要开票` is derived from all active bank detail auto-tag definitions.

**Architecture:** Keep `pending_invoice_tag_groups` and `bank_transaction_tags` as the only settings facts. Backend owns rule derivation, validation, audit/version behavior, pending invoice read model invalidation, and `filter=requires_invoice` complement semantics. Frontend owns only API mapping and compact hierarchical rendering.

**Tech Stack:** Python custom HTTP server and services under `backend/src/fin_ops_platform`, unittest backend tests, React + TypeScript + MUI frontend, Vitest frontend tests.

---

## File Structure

Backend contract and settings:

- Modify `backend/src/fin_ops_platform/app/server.py`
  - Update `_pending_invoice_rules_payload`.
  - Update `_handle_api_pending_invoice_rules_update` request normalization.
  - Preserve `_invalidate_pending_invoice_read_model_scopes`.
- Modify `backend/src/fin_ops_platform/services/app_settings_service.py`
  - Reuse existing normalization where possible.
  - If needed, add a small helper to normalize only editable pending invoice groups before validation.
  - Do not create a new rule fact source.
- Modify `tests/test_pending_invoice_api.py`
  - Route-level tests for derived `requires_invoice`, ignored legacy input, duplicate validation, hierarchy fields, and refresh enqueue behavior.
- Modify `tests/test_app_settings_service.py`
  - Service-level tests for validation, version/audit behavior, and ignored derived-group input if `AppSettingsService` changes.
- Modify `tests/test_bank_auto_tag_rules_api.py` only if existing tag dictionary compatibility expectations need extra coverage.

Pending invoice query/read model complement semantics:

- Modify `backend/src/fin_ops_platform/services/pending_invoice_service.py`
  - Update `_pending_invoice_tag_groups` / `_group_for_category` behavior so `requires_invoice` is derived.
  - Ensure legacy fallback rows, filter options, export source rows, and status reasoning are aligned.
- Modify `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
  - Update pending invoice projection/filter group logic to use the same complement semantics.
- Modify `tests/test_pending_invoice_service.py`
  - Unit tests for `filter=requires_invoice` complement behavior.
- Modify `tests/test_search_pending_sql_runtime.py` only if SQL projection behavior changes.

Frontend API:

- Modify `web/src/features/pendingInvoices/types.ts`
  - Keep all three group types.
  - Add read-only metadata only if useful and local.
- Modify `web/src/features/pendingInvoices/api.ts`
  - Map hierarchy fields for all group tags.
  - Send only the two editable groups in `rulesRequestBody`.
  - Include only `status=active` tags in `availableTags`.
- Modify `web/src/test/PendingInvoicesApi.test.ts`
  - Verify GET mapping and PUT body shape.

Frontend drawer:

- Modify `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`
  - Replace flat checkbox/chip layout with compact hierarchical blocks.
  - Keep local state limited to the two editable groups.
  - Derive read-only `需要开票` display.
- Modify `web/src/pages/PendingInvoicesPage.tsx` only if save/refresh wiring needs small adjustment.
- Modify `web/src/test/PendingInvoicesPage.test.tsx`
  - UI interaction tests for hierarchy, mutual exclusion, and save.
- Modify `web/src/test/apiMock.ts` only for pending invoice rules mock payload.

Docs and integration:

- Modify `docs/product-specs/pending-invoices.md`.
- Modify `docs/dev/pending-invoices-api.md`.
- Modify `docs/dev/api-contracts.md` only if implementation changes shared API wording.

## Task 1: Baseline And Current Shape

**Files:**
- Read: `docs/superpowers/specs/2026-05-31-pending-invoice-derived-rules-design.md`
- Read: `docs/superpowers/prompts/2026-05-31-pending-invoice-derived-rules-execution.md`
- Read: backend/frontend files listed above

- [ ] **Step 1: Check current worktree**

Run:

```bash
git status --short
```

Expected: existing user changes are visible. Do not revert them.

- [ ] **Step 2: Inspect backend route and settings methods**

Run:

```bash
PYTHONPATH=backend/src python3 - <<'PY'
from fin_ops_platform.app.server import build_application
app = build_application()
print(hasattr(app, "_pending_invoice_rules_payload"))
print(hasattr(app, "_handle_api_pending_invoice_rules_update"))
PY
```

Expected: prints `True` twice.

- [ ] **Step 3: Inspect current pending invoice group matching**

Run:

```bash
rg -n "_pending_invoice_tag_groups|_group_for_category|requires_invoice|pending_invoice_tag_groups" \
  backend/src/fin_ops_platform/services/pending_invoice_service.py \
  backend/src/fin_ops_platform/services/search_pending_sql_projection.py \
  backend/src/fin_ops_platform/app/server.py \
  backend/src/fin_ops_platform/services/app_settings_service.py
```

Expected: identify all places where old persisted `requires_invoice.tag_codes` might be read.

- [ ] **Step 4: Optional focused baseline tests**

Run if practical before editing:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_pending_invoice_service -v
cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx
```

Expected: record current pass/fail. Do not fix unrelated failures before adding focused tests.

## Task 2: Backend Rules API Derivation

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/app_settings_service.py` only if route-level normalization cannot stay small
- Test: `tests/test_pending_invoice_api.py`
- Test: `tests/test_app_settings_service.py` if `AppSettingsService` changes

- [ ] **Step 1: Add failing GET derivation test**

In `tests/test_pending_invoice_api.py`, add a test that:

- builds an app;
- configures `bank_transaction_tags` with active tags `fee`, `salary`, `custom_meal`, and archived tag `old_tag`;
- configures `pending_invoice_tag_groups` with `bank_statement_as_invoice=["fee"]`, `no_invoice_required=["salary"]`, and stale/legacy `requires_invoice=["old_tag"]`;
- calls `GET /api/pending-invoices/rules`;
- asserts:
  - `groups.requires_invoice.tag_codes == ["custom_meal"]`;
  - `groups.requires_invoice.tags[0].output_primary_label` is present;
  - `old_tag` is absent;
  - `pending_invoice_tag_groups.groups.requires_invoice.tag_codes` mirrors `["custom_meal"]` in the response payload.

- [ ] **Step 2: Add failing PUT legacy-ignore test**

In `tests/test_pending_invoice_api.py`, add a test that sends:

```json
{
  "groups": {
    "requires_invoice": { "tag_codes": ["unknown_legacy_code"] },
    "bank_statement_as_invoice": { "tag_codes": ["fee"] },
    "no_invoice_required": { "tag_codes": ["salary"] }
  }
}
```

Expected assertions:

- status is `200`;
- no unknown-tag error is raised for `unknown_legacy_code`;
- response `groups.requires_invoice.tag_codes` is the derived active complement.

- [ ] **Step 3: Add failing duplicate editable test**

In `tests/test_pending_invoice_api.py`, add a test that sends `fee` in both editable groups.

Expected assertions:

- status is `400`;
- error is `duplicate_pending_invoice_tag_mapping`.

- [ ] **Step 4: Run backend API tests and verify failures**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v
```

Expected: new tests fail before implementation.

- [ ] **Step 5: Implement active tag extraction helper**

In `backend/src/fin_ops_platform/app/server.py`, near `_pending_invoice_rules_payload`, add or use small local helpers equivalent to:

```python
def _active_pending_invoice_rule_tags(tag_dictionary: dict[str, object]) -> list[dict[str, object]]:
    raw_tags = tag_dictionary.get("definitions") or tag_dictionary.get("tags") or []
    result = []
    seen = set()
    for raw in list(raw_tags):
        if not isinstance(raw, dict):
            continue
        code = str(raw.get("code") or "").strip()
        if not code or code in seen or str(raw.get("status") or "active") != "active":
            continue
        seen.add(code)
        label = str(raw.get("label") or code)
        primary = str(raw.get("output_primary_label") or label or code)
        sub = str(raw.get("output_sub_label") or "")
        result.append({
            "code": code,
            "label": label,
            "status": "active",
            "output_primary_label": primary,
            "output_sub_label": sub,
        })
    return result
```

Keep it scoped and deterministic. Preserve order from tag dictionary.

- [ ] **Step 6: Implement derived response group**

Update `_pending_invoice_rules_payload` so:

- persisted editable codes come only from `bank_statement_as_invoice` and `no_invoice_required`;
- `requires_invoice` codes are computed from active tags not in editable selected sets;
- every returned tag includes `output_primary_label` and `output_sub_label`;
- compatibility `pending_invoice_tag_groups.groups.requires_invoice` mirrors the derived codes in response.

- [ ] **Step 7: Normalize PUT body to editable groups only**

Update `_handle_api_pending_invoice_rules_update` or a small helper so it passes only:

```python
{
    "groups": {
        "bank_statement_as_invoice": {"tag_codes": [...]},
        "no_invoice_required": {"tag_codes": [...]},
    }
}
```

into `AppSettingsService.update_settings(...)`.

Do not pass request-provided `requires_invoice` into settings validation.

- [ ] **Step 8: Preserve settings audit/version and read model invalidation**

Verify implementation still calls:

- `AppSettingsService.update_settings(...)`;
- `_persist_state()` where it currently does;
- `_invalidate_pending_invoice_read_model_scopes(reason="pending_invoice_rules_update")`.

If `AppSettingsService` changed, add focused service tests in `tests/test_app_settings_service.py` for version and validation behavior.

- [ ] **Step 9: Run backend rules tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_app_settings_service -v
```

Expected: tests pass, except nonexistent or pre-existing unrelated failures should be recorded.

## Task 3: `filter=requires_invoice` Complement Semantics

**Files:**
- Modify: `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- Modify: `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- Test: `tests/test_pending_invoice_service.py`
- Test: `tests/test_search_pending_sql_runtime.py` if SQL projection changes

- [ ] **Step 1: Add failing legacy query fallback test**

In `tests/test_pending_invoice_service.py`, add or update a test with:

- active tags: `fee`, `salary`, `custom_meal`;
- editable groups: `bank_statement_as_invoice=["fee"]`, `no_invoice_required=["salary"]`;
- transactions with effective categories `fee`, `salary`, `custom_meal`, no category, archived/unknown if easy.

Expected:

- `list_rows(direction="expense", filter="requires_invoice")` returns only the `custom_meal` transaction;
- no-category rows are not forced into `requires_invoice`.

- [ ] **Step 2: Run service test and verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service -v
```

Expected: new test fails before implementation if old persisted `requires_invoice` is required.

- [ ] **Step 3: Implement complement helper in query service**

In `PendingInvoiceQueryService`, make group resolution equivalent to:

```python
def _group_for_category(category_code: str | None, tag_groups: dict[str, set[str]]) -> str | None:
    if not category_code:
        return None
    if category_code in tag_groups.get("no_invoice_required", set()):
        return "no_invoice_required"
    if category_code in tag_groups.get("bank_statement_as_invoice", set()):
        return "bank_statement_as_invoice"
    if category_code in tag_groups.get("active_tag_codes", set()):
        return "requires_invoice"
    return None
```

Populate `active_tag_codes` from current `bank_transaction_tags` active dictionary. Do not treat unknown or archived codes as requires.

- [ ] **Step 4: Update SQL projection group logic**

In `search_pending_sql_projection.py`, update pending invoice filter group generation to mirror the same helper semantics.

Search for existing `_pending_invoice_tag_groups` and `_pending_invoice_filter_group_for_tag` style logic and update it rather than creating a parallel implementation.

- [ ] **Step 5: Add SQL projection test if applicable**

If `search_pending_sql_projection.py` changes, add or update `tests/test_search_pending_sql_runtime.py` so pending read model rows get `filter_group="requires_invoice"` only for active complement tags.

- [ ] **Step 6: Run query/read model tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_search_pending_sql_runtime -v
```

Expected: pass or record pre-existing unrelated failures.

## Task 4: Frontend API Mapping

**Files:**
- Modify: `web/src/features/pendingInvoices/types.ts`
- Modify: `web/src/features/pendingInvoices/api.ts`
- Test: `web/src/test/PendingInvoicesApi.test.ts`

- [ ] **Step 1: Add failing API mapping test**

In `web/src/test/PendingInvoicesApi.test.ts`, update rules endpoint mock to include:

- `groups.requires_invoice` with `output_primary_label` / `output_sub_label`;
- active tag in `bank_transaction_tags`;
- a non-active non-archived status such as `disabled` or `inactive`;
- archived tag.

Expected assertions:

- `fetchPendingInvoiceRules()` maps `requiresInvoice.tags` hierarchy fields;
- `availableTags` includes only `status === "active"`;
- `availableTags` excludes inactive/non-active and archived tags.

- [ ] **Step 2: Add failing PUT body test**

In the same test, assert `savePendingInvoiceRules(rules)` sends:

```json
{
  "groups": {
    "bank_statement_as_invoice": { "tag_codes": [...] },
    "no_invoice_required": { "tag_codes": [...] }
  }
}
```

Expected: body does not contain `requires_invoice`.

- [ ] **Step 3: Run API test and verify failure**

Run:

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts
```

Expected: new tests fail before implementation.

- [ ] **Step 4: Update types if useful**

In `web/src/features/pendingInvoices/types.ts`, keep:

- `PendingInvoiceRulesPayload.groups.requiresInvoice`;
- `PendingInvoiceRulesPayload.groups.bankStatementAsInvoice`;
- `PendingInvoiceRulesPayload.groups.noInvoiceRequired`.

Add only local metadata such as `editable?: boolean` if it simplifies UI and tests. Do not require backend to persist a new field.

- [ ] **Step 5: Update mapping and serializer**

In `web/src/features/pendingInvoices/api.ts`:

- map group tags with `outputPrimaryLabel` and `outputSubLabel`;
- build `availableTags` from `bank_transaction_tags.definitions` or `tags`;
- include only `status === "active"` in `availableTags`;
- update `rulesRequestBody` to omit `requires_invoice`.

- [ ] **Step 6: Run frontend API test**

Run:

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts
```

Expected: pass.

## Task 5: Frontend Rules Drawer UI

**Files:**
- Modify: `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx`
- Modify: `web/src/pages/PendingInvoicesPage.tsx` only if refresh/save wiring needs small adjustment
- Modify: `web/src/test/PendingInvoicesPage.test.tsx`
- Modify: `web/src/test/apiMock.ts` only for pending invoice rules mock payload

- [ ] **Step 1: Add failing drawer hierarchy test**

In `web/src/test/PendingInvoicesPage.test.tsx`, add or update a test that opens `待找发票规则设置` and asserts:

- headings/text for `流水代替发票`, `无需开票`, `需要开票`;
- primary label, e.g. `费用`, is visible but not a checkbox;
- child label, e.g. `手续费`, is a checkbox in editable blocks;
- a no-sub-label tag renders as primary plus same-name child.

- [ ] **Step 2: Add failing mutual exclusion test**

In the same test file:

- select a child in `流水代替发票`;
- assert same child in `无需开票` is disabled;
- assert it disappears from `需要开票`;
- unselect it and assert it returns to `需要开票`.

- [ ] **Step 3: Add failing read-only block test**

Assert the `需要开票` block has no checkbox and no clickable child controls.

- [ ] **Step 4: Run page test and verify failure**

Run:

```bash
cd web && npm test -- --run PendingInvoicesPage.test.tsx
```

Expected: new tests fail before implementation.

- [ ] **Step 5: Implement tag tree helpers**

In `PendingInvoiceRulesDrawer.tsx`, add small pure helpers:

```ts
function tagPrimaryLabel(tag: PendingInvoiceRuleTag) {
  return tag.outputPrimaryLabel.trim() || tag.label.trim() || tag.code;
}

function tagChildLabel(tag: PendingInvoiceRuleTag) {
  return tag.outputSubLabel.trim() || tag.label.trim() || tagPrimaryLabel(tag);
}
```

Build groups by primary label and preserve tag order. Do not import bank details page helpers directly unless they are already shared; avoid broad refactors.

- [ ] **Step 6: Implement compact block component**

Replace the flat `RuleGroup` with a local hierarchical component that supports:

- `mode="editable"` with checkbox child rows;
- `mode="readonly"` with text child rows;
- disabled child rows when assigned elsewhere;
- dense spacing and narrow drawer width.

- [ ] **Step 7: Maintain two editable state arrays only**

Update `updateRuleGroup` and save state so:

- only `bankStatementAsInvoice` and `noInvoiceRequired` are toggled;
- `requiresInvoice` display is derived from `availableTags` minus selected editable sets;
- after save, `setPayload(await saveRules(payload))` remains the source of truth.

- [ ] **Step 8: Preserve permission behavior**

Ensure:

- read-only users see the three blocks;
- editable checkboxes are disabled;
- save button is disabled by existing `payload.permissions.canSave`.

- [ ] **Step 9: Run page test**

Run:

```bash
cd web && npm test -- --run PendingInvoicesPage.test.tsx
```

Expected: pass.

## Task 6: Long-Term Docs

**Files:**
- Modify: `docs/product-specs/pending-invoices.md`
- Modify: `docs/dev/pending-invoices-api.md`
- Modify: `docs/dev/api-contracts.md` only if needed

- [ ] **Step 1: Update product spec**

In `docs/product-specs/pending-invoices.md`, update rule language:

- users edit only `流水代替发票` and `无需开票`;
- `需要开票` is backend-derived from all active bank detail auto-tag definitions;
- primary labels are non-selectable; child tags are selectable.

- [ ] **Step 2: Update API doc**

In `docs/dev/pending-invoices-api.md`, update `GET/PUT /api/pending-invoices/rules`:

- `GET` returns three groups;
- `PUT` accepts/saves only two editable groups;
- legacy `requires_invoice` input is accepted but ignored/recomputed;
- validation applies to editable persisted groups;
- `filter=requires_invoice` uses active complement semantics.

- [ ] **Step 3: Run doc grep sanity**

Run:

```bash
rg -n "待找发票规则设置|pending_invoice_tag_groups|requires_invoice|流水代替发票|无需开票" docs/product-specs/pending-invoices.md docs/dev/pending-invoices-api.md docs/dev/api-contracts.md
```

Expected: no contradiction saying users manually edit `需要开票`.

## Task 7: Integration Verification And Review

**Files:**
- Read: `git diff`
- Read: files changed in Tasks 2-6

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_pending_invoice_service tests.test_app_settings_service tests.test_bank_auto_tag_rules_api -v
```

Expected: pass or document pre-existing unrelated failures.

- [ ] **Step 2: Run SQL projection tests if touched**

Run if `search_pending_sql_projection.py` changed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v
```

Expected: pass or document pre-existing unrelated failures.

- [ ] **Step 3: Run focused frontend tests**

Run:

```bash
cd web && npm test -- --run PendingInvoicesApi.test.ts PendingInvoicesPage.test.tsx
```

Expected: pass.

- [ ] **Step 4: Run frontend build if frontend files changed**

Run:

```bash
cd web && npm run build
```

Expected: pass.

- [ ] **Step 5: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 6: Run reviewer prompt**

Use the reviewer prompt in:

```text
docs/superpowers/prompts/2026-05-31-pending-invoice-derived-rules-execution.md
```

Expected: `APPROVED` or actionable findings fixed before final report.

- [ ] **Step 7: Final report**

Report:

- backend contract changes;
- frontend drawer behavior;
- docs changed;
- exact tests run;
- tests not run and why;
- residual risks.


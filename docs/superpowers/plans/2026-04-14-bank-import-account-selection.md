# Bank Import Account Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bank-transaction imports use the user-selected bank-account mapping entry as the primary source for bank label and last-four tag, while keeping auto-detection only as a conflict checker.

**Architecture:** Extend the existing import modal and import preview override payload so each bank file carries `mapping_id / bank_name / last4`. Persist that selection through `FileImportService`, use it during bank-row normalization, compute preview-time conflicts against auto-detected results, and gate confirm with a frontend conflict dialog.

**Tech Stack:** React 18, TypeScript, existing import modal and imports API layer, Python backend services, existing in-memory import preview/confirm flow, Vitest, unittest/pytest style backend tests.

---

### File Map

**Frontend**

- Modify: `web/src/components/workbench/WorkbenchImportModal.tsx`
  Responsibility: bank import selection UI, preview payload construction, conflict-confirm gate before confirm.
- Modify: `web/src/features/imports/types.ts`
  Responsibility: preview override and preview payload types.
- Modify: `web/src/features/imports/api.ts`
  Responsibility: request/response serialization for selected bank mapping and conflict fields.
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
  Responsibility: pass full bank account mappings into import modal instead of deduped bank names.
- Test: `web/src/test/CandidateGroupGrid.test.tsx`
  Responsibility: untouched unless existing tests need fixture alignment.
- Create or modify: `web/src/test/WorkbenchImportModal.test.tsx`
  Responsibility: modal behavior, selection requirements, conflict-confirm gate.

**Backend**

- Modify: `backend/src/fin_ops_platform/services/import_file_service.py`
  Responsibility: carry selected mapping data through preview/retry/session payload and compute file-level conflict metadata.
- Modify: `backend/src/fin_ops_platform/services/imports.py`
  Responsibility: accept selected bank mapping context for bank transaction normalization and persist chosen bank label/last4 into normalized rows.
- Modify: `backend/src/fin_ops_platform/services/bank_account_resolver.py`
  Responsibility: keep current mapping resolver as fallback only; do not override explicit imported selection.
- Modify: `backend/src/fin_ops_platform/app/server.py`
  Responsibility: parse/validate expanded bank override payload and expose new response fields.
- Test: `tests/test_import_file_service.py`
  Responsibility: preview conflict and selected mapping propagation.
- Test: `tests/test_import_api.py` or nearest existing import API test file
  Responsibility: API contract for preview payload and conflict fields.

**Docs**

- Modify: `docs/README.md`
  Responsibility: add references to this spec and plan.

---

### Task 1: Lock backend contract with failing tests

**Files:**
- Modify: `tests/test_import_file_service.py`
- Modify: `tests/test_import_api.py`
- Reference: `backend/src/fin_ops_platform/services/import_file_service.py`
- Reference: `backend/src/fin_ops_platform/app/server.py`

- [ ] **Step 1: Write the failing service tests**

Add tests that preview a bank transaction file with explicit selected mapping:

- selected mapping fields are persisted on the preview file item
- normalized preview rows carry selected `bank_name` and `last4`
- mismatch between selected mapping and auto-detected result produces:
  - `bank_selection_conflict == True`
  - `detected_bank_name`
  - `detected_last4`
  - `conflict_message`

- [ ] **Step 2: Write the failing API tests**

Cover:

- preview request accepts `bank_mapping_id / bank_name / last4`
- preview response returns selected mapping metadata and conflict fields
- retry preview preserves or overrides selected mapping correctly

- [ ] **Step 3: Run the backend tests to confirm failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_service.py tests/test_import_api.py -q
```

Expected:

- FAIL on missing selected mapping fields and conflict behavior

- [ ] **Step 4: Commit the red tests**

```bash
git add tests/test_import_file_service.py tests/test_import_api.py
git commit -m "test: cover bank import account selection contract"
```

### Task 2: Implement backend selected-mapping propagation and conflict detection

**Files:**
- Modify: `backend/src/fin_ops_platform/services/import_file_service.py`
- Modify: `backend/src/fin_ops_platform/services/imports.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Reference: `backend/src/fin_ops_platform/services/bank_account_resolver.py`

- [ ] **Step 1: Extend backend file models**

Add fields to uploaded file / preview item models for:

- selected mapping id
- selected bank name
- selected last4
- detected bank name
- detected last4
- conflict flag
- conflict message

- [ ] **Step 2: Thread selected mapping through preview and retry**

Ensure preview and retry both preserve:

- selected mapping id
- selected bank name
- selected last4

And that overrides can replace the selected mapping on retry.

- [ ] **Step 3: Use selected mapping as normalization source**

For bank transaction rows:

- write bank label from selected `bank_name`
- write last4 tag from selected `last4`
- keep auto-detected values for comparison only

- [ ] **Step 4: Compute conflict metadata**

Compare selected mapping against detectable account/bank hints in file content.  
When mismatch exists, populate file-level conflict fields.

- [ ] **Step 5: Re-run backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_service.py tests/test_import_api.py -q
```

Expected:

- PASS

- [ ] **Step 6: Commit backend implementation**

```bash
git add backend/src/fin_ops_platform/services/import_file_service.py backend/src/fin_ops_platform/services/imports.py backend/src/fin_ops_platform/app/server.py
git commit -m "feat: honor selected bank mapping during import preview"
```

### Task 3: Lock frontend modal behavior with failing tests

**Files:**
- Create or Modify: `web/src/test/WorkbenchImportModal.test.tsx`
- Modify: `web/src/features/imports/types.ts`
- Reference: `web/src/components/workbench/WorkbenchImportModal.tsx`
- Reference: `web/src/features/imports/api.ts`

- [ ] **Step 1: Write failing modal tests**

Cover:

- bank import dropdown lists concrete account mapping options (`bankName + last4`)
- preview is blocked until every file has a selected mapping entry
- preview payload includes `bankMappingId / bankName / last4`
- if preview response contains a conflict, clicking confirm opens conflict dialog instead of calling confirm API
- user can cancel or continue from conflict dialog

- [ ] **Step 2: Run frontend tests to confirm failure**

Run:

```bash
cd web
npm run test -- WorkbenchImportModal.test.tsx --run
```

Expected:

- FAIL on missing mapping fields and conflict dialog behavior

- [ ] **Step 3: Commit the red tests**

```bash
git add web/src/test/WorkbenchImportModal.test.tsx
git commit -m "test: cover bank import mapping selection flow"
```

### Task 4: Implement frontend mapping selection and conflict confirm flow

**Files:**
- Modify: `web/src/components/workbench/WorkbenchImportModal.tsx`
- Modify: `web/src/features/imports/types.ts`
- Modify: `web/src/features/imports/api.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`

- [ ] **Step 1: Pass full mapping options into the modal**

Replace deduped bank-name options with full mapping entries from settings.

- [ ] **Step 2: Update modal selection state**

For each bank file store:

- `bankMappingId`
- `bankName`
- `last4`

Display options as `银行名 后四位`.

- [ ] **Step 3: Send expanded preview overrides**

Preview request for bank files must serialize:

- `bank_mapping_id`
- `bank_name`
- `last4`

- [ ] **Step 4: Render conflict status in preview**

If a preview file reports conflict:

- show explicit warning text in preview card
- include detected vs selected values when available

- [ ] **Step 5: Gate confirm with a conflict dialog**

When any confirmable file has conflict:

- do not call confirm immediately
- open dialog
- “取消” closes dialog with no confirm call
- “继续按所选账户导入” proceeds with confirm

- [ ] **Step 6: Re-run frontend tests**

Run:

```bash
cd web
npm run test -- WorkbenchImportModal.test.tsx --run
```

Expected:

- PASS

- [ ] **Step 7: Run targeted regression tests and build**

Run:

```bash
cd web
npm run test -- CandidateGroupGrid.test.tsx WorkbenchImportModal.test.tsx --run
npm run build
```

Expected:

- PASS

- [ ] **Step 8: Commit frontend implementation**

```bash
git add web/src/components/workbench/WorkbenchImportModal.tsx web/src/features/imports/types.ts web/src/features/imports/api.ts web/src/pages/ReconciliationWorkbenchPage.tsx web/src/test/WorkbenchImportModal.test.tsx
git commit -m "feat: add bank import account selection and conflict confirm"
```

### Task 5: Final integration and documentation

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/superpowers/specs/2026-04-14-bank-import-account-selection-design.md`
- Modify: `docs/superpowers/plans/2026-04-14-bank-import-account-selection.md`

- [ ] **Step 1: Add docs index references**

List the new spec and plan in `docs/README.md`.

- [ ] **Step 2: Run end-to-end targeted verification**

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_service.py tests/test_import_api.py -q
cd web
npm run test -- WorkbenchImportModal.test.tsx CandidateGroupGrid.test.tsx --run
npm run build
```

Expected:

- PASS

- [ ] **Step 3: Manual smoke checklist**

Verify in app:

- bank import modal shows account mapping options
- selecting no mapping blocks preview
- preview shows selected mapping
- conflict preview shows warning
- confirm opens conflict dialog
- continuing confirms import using selected mapping

- [ ] **Step 4: Commit docs and final integration**

```bash
git add docs/README.md docs/superpowers/specs/2026-04-14-bank-import-account-selection-design.md docs/superpowers/plans/2026-04-14-bank-import-account-selection.md
git commit -m "docs: add bank import account selection design and plan"
```

# Batch Accounting Mismatch Note Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `日常报销批量账务管理` users to complete a batch accounting relation when bank amount and selected OA total differ, with a mandatory relation-level difference note and a warning icon in the workbench paired area.

**Architecture:** Keep `workbench_pair_relations` as the only write-model fact. Batch accounting computes and stores relation-level `note` and `amount_check`; the workbench read payload projects those fields to both the paired group and the bank row so the frontend can render the warning icon beside the bank amount. No exception case, ledger, task, or approval flow is created for this approved artificial difference closure.

**Tech Stack:** Python backend services and unittest tests; React + TypeScript + MUI frontend; Vite/Vitest test suite.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-19-batch-accounting-mismatch-note-design.md`
- Prior batch accounting design: `docs/superpowers/specs/2026-05-18-batch-accounting-design.md`
- Worker prompts: `docs/archive/prompts/2026-05-19-batch-accounting-mismatch-note-subagents.md`
- Workbench product spec: `docs/product-specs/workbench.md`
- Backend API contract context: `docs/dev/reconciliation-workbench-v2-data-contracts.md`

## File Structure

- `backend/src/fin_ops_platform/services/batch_accounting_service.py`
  - Owns batch accounting eligibility, amount computation, note validation, relation creation, and submitted payload relation exposure.
- `backend/src/fin_ops_platform/app/server.py`
  - Owns HTTP request parsing, mutation rollback/persistence scheduling, and workbench pair relation projection into grouped payloads.
- `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
  - May need grouped payload serialization updates if relation fields are easier to attach during grouping.
- `tests/test_batch_accounting_api.py`
  - Owns batch accounting backend behavior tests.
- `tests/test_workbench_v2_api.py`
  - Owns workbench paired projection and no-exception/no-ledger side-effect assertions.
- `web/src/features/batchAccounting/types.ts`
  - Owns batch accounting client display types, relation metadata, and submit request note field.
- `web/src/features/batchAccounting/api.ts`
  - Owns batch accounting API mapping and submit request serialization.
- `web/src/pages/BatchAccountingPage.tsx`
  - Owns batch page difference note input and submitted relation display.
- `web/src/test/BatchAccountingPage.test.tsx`
  - Owns batch page UI and request-body tests.
- `web/src/features/workbench/types.ts`
  - Owns frontend workbench display model fields for relation note and amount check.
- `web/src/features/workbench/api.ts`
  - Owns mapping from backend `relation_note`, `amount_check`, and `relation_amount_check` fields.
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
  - Owns the warning icon beside the bank amount and accessible tooltip.
- Workbench frontend tests:
  - `web/src/test/WorkbenchApi.test.ts`
  - `web/src/test/WorkbenchSelection.test.tsx`
  - `web/src/test/WorkbenchZone.test.tsx`
  - `web/src/test/WorkbenchColumns.test.tsx` only if column rendering assertions require updates.

## Stable Payload Contract

Backend `GET /api/workbench` must expose these fields:

```json
{
  "paired": {
    "groups": [
      {
        "group_id": "case:CASE-BATCH-txn_imported_202601_batch_001",
        "relation_note": "OA合计不含员工餐补扣款，财务确认闭环",
        "amount_check": {
          "status": "mismatch",
          "direction": "expense",
          "bank_amount": "3617.41",
          "oa_amount": "3425.41",
          "amount_delta": "192.00",
          "requires_note": true
        },
        "bank_rows": [
          {
            "id": "txn_imported_202601_batch_001",
            "relation_note": "OA合计不含员工餐补扣款，财务确认闭环",
            "relation_amount_check": {
              "status": "mismatch",
              "direction": "expense",
              "bank_amount": "3617.41",
              "oa_amount": "3425.41",
              "amount_delta": "192.00",
              "requires_note": true
            },
            "tags": ["支", "金额不一致"]
          }
        ]
      }
    ]
  }
}
```

Frontend mapping:

- `group.relation_note` -> `WorkbenchCandidateGroup.relationNote`
- `group.amount_check` -> `WorkbenchCandidateGroup.amountCheck`
- `row.relation_note` -> `WorkbenchRecord.relationNote`
- `row.relation_amount_check` -> `WorkbenchRecord.relationAmountCheck`

Tooltip source precedence:

1. Bank row `relationAmountCheck` + `relationNote`.
2. Group `amountCheck` + `relationNote` only as fallback for old cached payloads.

## Preflight for Every Worker

Before editing any file, every worker must run:

```bash
git status --short
git diff -- <owned-file-1> <owned-file-2>
```

If an owned file is already dirty, read the diff and preserve existing changes. Do not revert, overwrite, or stage unrelated changes. This is especially important for `backend/src/fin_ops_platform/app/server.py`, which may already contain unrelated edits.

---

### Task 1: Backend Batch Submit Validation and Relation Persistence

**Files:**
- Modify: `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_batch_accounting_api.py`

- [ ] **Step 1: Write failing tests for note-required mismatch**

In `tests/test_batch_accounting_api.py`, replace the existing unconditional mismatch rejection expectation with two explicit tests:

```python
def test_submit_amount_mismatch_requires_difference_note(self) -> None:
    app = self._build_app()
    response = app.handle_request(
        "POST",
        "/api/batch-accounting/submit",
        body=json.dumps({
            "bank_year": "2026",
            "oa_year": "2026",
            "bank_row_id": "txn_imported_202601_batch_001",
            "oa_row_ids": ["oa-exp-202601-daily-001"],
            "expected_version": 1,
        }),
        headers=self._write_headers(),
    )
    payload = json.loads(response.body)
    self.assertEqual(response.status, HTTPStatus.BAD_REQUEST)
    self.assertEqual(payload["error"], "batch_accounting_note_required")
    self.assertEqual(payload["amount_check"]["status"], "mismatch")
    self.assertTrue(payload["amount_check"]["requires_note"])

def test_submit_amount_mismatch_rejects_whitespace_note(self) -> None:
    app = self._build_app()
    response = app.handle_request(
        "POST",
        "/api/batch-accounting/submit",
        body=json.dumps({
            "bank_year": "2026",
            "oa_year": "2026",
            "bank_row_id": "txn_imported_202601_batch_001",
            "oa_row_ids": ["oa-exp-202601-daily-001"],
            "note": "   ",
        }),
        headers=self._write_headers(),
    )
    self.assertEqual(json.loads(response.body)["error"], "batch_accounting_note_required")
```

Use existing fixture IDs from the file; if the fixture IDs differ, keep the current mismatch fixture and only change expected behavior.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
```

Expected: FAIL because mismatch still returns `batch_accounting_amount_mismatch` or submit route does not parse `note`.

- [ ] **Step 3: Implement amount_check builder and note validation**

In `batch_accounting_service.py`, add a small helper near existing amount helpers:

```python
def _batch_amount_check(self, *, bank_amount: Decimal, oa_amount: Decimal) -> dict[str, Any]:
    amount_delta = self._quantize(bank_amount) - self._quantize(oa_amount)
    status = "matched" if amount_delta == Decimal("0.00") else "mismatch"
    return {
        "status": status,
        "direction": "expense",
        "bank_amount": self._format_amount(bank_amount),
        "oa_amount": self._format_amount(oa_amount),
        "amount_delta": self._format_amount(amount_delta),
        "requires_note": status == "mismatch",
    }
```

Extend `submit(...)` signature:

```python
note: str | None = None,
```

Normalize:

```python
submit_note = str(note or "").strip()
amount_check = self._batch_amount_check(bank_amount=bank_amount, oa_amount=oa_amount)
if amount_check["status"] == "mismatch" and not submit_note:
    raise BatchAccountingError(
        "batch_accounting_note_required",
        "银行流水金额与所选 OA 金额合计不一致，请填写差额说明。",
        payload={"amount_check": amount_check},
    )
```

Remove the old unconditional `batch_accounting_amount_mismatch` rejection.

- [ ] **Step 4: Pass note from HTTP route**

In `server.py` inside `_handle_api_batch_accounting_submit`, pass:

```python
note=str(payload.get("note") or ""),
```

to `self._batch_accounting_service().submit(...)`.

- [ ] **Step 5: Persist relation note and amount_check**

In `batch_accounting_service.py`, when calling `replace_with_confirmed_relation(...)`, set:

```python
note=submit_note if submit_note else "日常报销批量账务管理提交",
amount_check=amount_check,
```

Keep existing `special_metadata` fields unchanged.

- [ ] **Step 6: Run backend batch tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
```

Expected: PASS for updated mismatch note-required tests; existing matched submit tests still pass.

- [ ] **Step 7: Add mismatch-with-note persistence test**

Add a test in `tests/test_batch_accounting_api.py`:

```python
def test_submit_amount_mismatch_with_note_persists_relation_and_history(self) -> None:
    app = self._build_app()
    response = app.handle_request(
        "POST",
        "/api/batch-accounting/submit",
        body=json.dumps({
            "bank_year": "2026",
            "oa_year": "2026",
            "bank_row_id": "txn_imported_202601_batch_001",
            "oa_row_ids": ["oa-exp-202601-daily-001"],
            "note": "OA合计不含员工餐补扣款，财务确认闭环",
        }),
        headers=self._write_headers(),
    )
    payload = json.loads(response.body)
    self.assertEqual(response.status, HTTPStatus.OK)
    relation = payload["pair_relation"]
    self.assertEqual(relation["note"], "OA合计不含员工餐补扣款，财务确认闭环")
    self.assertEqual(relation["amount_check"]["status"], "mismatch")
    self.assertEqual(relation["amount_check"]["requires_note"], True)
    self.assertEqual(relation["special_metadata"]["source"], "batch_accounting")
    history = app._workbench_pair_relation_service.list_history()[-1]
    self.assertEqual(history["note"], "OA合计不含员工餐补扣款，财务确认闭环")
    self.assertEqual(history["amount_check"]["status"], "mismatch")
```

Adjust fixture IDs and expected amounts to current test data.

- [ ] **Step 8: Run test to verify it fails or passes**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
```

Expected: PASS after implementation, or FAIL only if submitted payload/relation shape still needs refinement.

- [ ] **Step 9: Add persistence failure rollback test**

In `tests/test_batch_accounting_api.py`, add a test that stubs `_schedule_workbench_pair_relation_persist` to raise during submit:

```python
def test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails(self) -> None:
    app = self._build_app()
    previous_snapshot = app._workbench_pair_relation_service.snapshot()

    def fail_persist(*_args, **_kwargs):
        raise StatePersistenceError("persist failed")

    app._schedule_workbench_pair_relation_persist = fail_persist
    response = app.handle_request(
        "POST",
        "/api/batch-accounting/submit",
        body=json.dumps({
            "bank_year": "2026",
            "oa_year": "2026",
            "bank_row_id": "txn_imported_202601_batch_001",
            "oa_row_ids": ["oa-exp-202601-daily-001"],
            "note": "财务确认差额闭环",
        }),
        headers=self._write_headers(),
    )

    self.assertNotEqual(response.status, HTTPStatus.OK)
    self.assertEqual(app._workbench_pair_relation_service.snapshot(), previous_snapshot)
```

Use the existing persistence-unavailable response assertion pattern from confirm-link tests if one exists.

- [ ] **Step 10: Implement submit rollback around persistence scheduling**

In `server.py` inside `_handle_api_batch_accounting_submit`, snapshot pair relation state before calling the service:

```python
previous_pair_snapshot = self._workbench_pair_relation_service.snapshot()
```

If `_schedule_workbench_pair_relation_persist(...)` raises, restore:

```python
self._workbench_pair_relation_service = WorkbenchPairRelationService.from_snapshot(previous_pair_snapshot)
self._configure_workbench_exception_application_service()
```

Then return the same persistence-unavailable response pattern used by `_handle_live_workbench_confirm_link`. Do not return successful submit when persistence scheduling fails.

---

### Task 2: Backend Submitted Payload, Workbench Projection, and Side-Effect Guardrails

**Files:**
- Modify: `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py` only if group serialization owns the final payload fields
- Test: `tests/test_batch_accounting_api.py`
- Test: `tests/test_workbench_v2_api.py`

- [ ] **Step 1: Write submitted payload test**

In `tests/test_batch_accounting_api.py`, extend the existing submitted-list test or add:

```python
def test_submitted_list_exposes_mismatch_note_and_amount_check(self) -> None:
    app = self._build_app()
    self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")
    response = app.handle_request("GET", "/api/batch-accounting?bank_year=2026&oa_year=2026&bucket=submitted")
    payload = json.loads(response.body)
    relation_payload = payload["relations_by_bank_row_id"]["txn_imported_202601_batch_001"]
    self.assertEqual(relation_payload["relation"]["note"], "财务确认差额闭环")
    self.assertEqual(relation_payload["relation"]["amount_check"]["status"], "mismatch")
```

- [ ] **Step 2: Run test to verify current exposure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api -v
```

Expected: May already PASS because `relations_by_bank_row_id[*].relation` is returned; keep test to lock contract.

- [ ] **Step 3: Write workbench projection test**

In `tests/test_workbench_v2_api.py`, add a test that submits a batch mismatch with note, then loads `GET /api/workbench?month=all` and finds the paired group containing the bank row:

```python
def test_batch_accounting_mismatch_note_projects_to_paired_bank_row(self) -> None:
    app = self._build_app_with_batch_accounting_fixture()
    self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")
    response = app.handle_request("GET", "/api/workbench?month=all")
    payload = json.loads(response.body)
    group = self._find_group_by_row_id(payload["paired"]["groups"], "txn_imported_202601_batch_001")
    self.assertEqual(group["relation_note"], "财务确认差额闭环")
    self.assertEqual(group["amount_check"]["status"], "mismatch")
    bank_row = next(row for row in group["bank_rows"] if row["id"] == "txn_imported_202601_batch_001")
    self.assertEqual(bank_row["relation_note"], "财务确认差额闭环")
    self.assertEqual(bank_row["relation_amount_check"]["status"], "mismatch")
    self.assertIn("金额不一致", bank_row["tags"])
```

Use existing helpers/fixture setup from nearby pair relation tests.

- [ ] **Step 4: Run workbench test to verify failure**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -v
```

Expected: FAIL because `relation_note` / `relation_amount_check` are not yet projected.

- [ ] **Step 5: Project relation fields into backend payload**

In `server.py`, locate the relation application path used during workbench payload rebuild, especially `_apply_pair_relation_to_row(...)`, `_derive_tags_for_grouped_payload(...)`, `_relation_groups(...)`, and candidate grouping serialization.

Implement the smallest stable projection:

- When a row belongs to an active relation:
  - copy `relation["note"]` to row `relation_note`;
  - copy `relation["amount_check"]` to row `relation_amount_check`;
  - keep existing tags, including `金额不一致`.
- When serializing a relation-backed group:
  - set group `relation_note` from the active relation note;
  - set group `amount_check` from active relation amount_check.

Do not put relation note into bank original `备注` or `tableValues.note`.

- [ ] **Step 6: Add no exception/ledger side-effect assertions**

In the same backend tests, assert mismatch-with-note does not create exception/ledger side effects using before/after counts or known in-memory services/collections. Do not use broad string searches over full snapshots.

```python
before_exception_cases = len(app._workbench_exception_case_service.list_cases())
before_ledger_entries = len(getattr(app, "_turnover_ledger_service").list_entries())

self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")

after_exception_cases = len(app._workbench_exception_case_service.list_cases())
after_ledger_entries = len(getattr(app, "_turnover_ledger_service").list_entries())
self.assertEqual(after_exception_cases, before_exception_cases)
self.assertEqual(after_ledger_entries, before_ledger_entries)
```

If exact service names differ, inspect existing exception/ledger tests and assert against the concrete services or state collections they use. The important behavior is no new `workbench_exception_cases` and no new ledger/follow-up/task/approval fact created by this mutation.

- [ ] **Step 7: Add withdraw cleanup coverage**

Add a test that submits a mismatch with note, withdraws it, then verifies:

- active batch relation is gone;
- `GET /api/workbench?month=all` no longer exposes `relation_note` or `relation_amount_check` for the withdrawn bank row in the paired projection;
- withdraw history `note` equals the withdraw reason;
- original submit history still retains the submit `note` and mismatch `amount_check`.

Test sketch:

```python
def test_withdraw_mismatch_batch_removes_projection_and_preserves_history_notes(self) -> None:
    app = self._build_app_with_batch_accounting_fixture()
    submit_payload = self._submit_batch_mismatch_with_note(app, note="财务确认差额闭环")
    relation_id = submit_payload["relation_id"]

    withdraw = app.handle_request(
        "POST",
        f"/api/batch-accounting/{relation_id}/withdraw",
        body=json.dumps({"reason": "选错 OA"}),
        headers=self._write_headers(),
    )
    self.assertEqual(withdraw.status, HTTPStatus.OK)
    self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(relation_id))

    histories = app._workbench_pair_relation_service.list_history()
    self.assertEqual(histories[-1]["operation_type"], "withdraw_link")
    self.assertEqual(histories[-1]["note"], "选错 OA")
    submit_history = next(history for history in histories if history["operation_type"] == "confirm_link")
    self.assertEqual(submit_history["note"], "财务确认差额闭环")
    self.assertEqual(submit_history["amount_check"]["status"], "mismatch")
```

Use existing workbench payload helpers to assert the withdrawn bank row no longer has mismatch projection in paired groups.

- [ ] **Step 8: Run backend verification**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api -v
```

Expected: PASS.

---

### Task 3: Batch Accounting Frontend Note Input and Submitted Relation Mapping

**Files:**
- Modify: `web/src/features/batchAccounting/types.ts`
- Modify: `web/src/features/batchAccounting/api.ts`
- Modify: `web/src/pages/BatchAccountingPage.tsx`
- Test: `web/src/test/BatchAccountingPage.test.tsx`

- [ ] **Step 1: Write failing frontend tests for mismatch note input**

In `web/src/test/BatchAccountingPage.test.tsx`, update the current mismatch-disabled test and add the related state cleanup tests before implementation:

```tsx
test("requires a difference note before submitting mismatched batch accounting relation", async () => {
  const user = userEvent.setup();
  const requests = installBatchAccountingFetchMock({ mismatch: true });
  render(<BatchAccountingPage />);

  await screen.findByRole("heading", { name: "日常报销批量账务管理" });
  await user.click(screen.getByRole("checkbox", { name: /选择/ }));

  expect(screen.getByLabelText("差额说明")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

  await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
  expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

  await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));
  expect(requests.lastSubmitBody()).toMatchObject({ note: "财务确认差额闭环" });
});

test("keeps mismatch submit disabled for whitespace-only difference note", async () => {
  const user = userEvent.setup();
  installBatchAccountingFetchMock({ mismatch: true });
  render(<BatchAccountingPage />);
  await screen.findByRole("heading", { name: "日常报销批量账务管理" });
  await user.click(screen.getByRole("checkbox", { name: /选择/ }));
  await user.type(screen.getByLabelText("差额说明"), "   ");
  expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();
});

test("does not require a difference note when selected amounts match", async () => {
  const user = userEvent.setup();
  const requests = installBatchAccountingFetchMock({ mismatch: false });
  render(<BatchAccountingPage />);
  await screen.findByRole("heading", { name: "日常报销批量账务管理" });
  await user.click(screen.getByRole("checkbox", { name: /选择/ }));
  expect(screen.queryByLabelText("差额说明")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));
  expect(requests.lastSubmitBody()).toMatchObject({ note: "" });
});
```

Adjust selectors to existing test helpers.

Add tests for the approved note lifetime rules:

- switching selected bank row clears `差额说明`;
- switching `未提交 / 已提交` clears `差额说明`;
- toggling OA rows does not clear `差额说明`;
- submitted bucket refresh renders persisted mismatch status/note from `relations_by_bank_row_id[*].relation`.

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx
```

Expected: FAIL because there is no `差额说明` input and mismatch submit stays disabled.

- [ ] **Step 3: Extend batch accounting types**

In `types.ts`, add:

```ts
export type BatchAccountingAmountCheck = {
  status: "matched" | "mismatch" | string;
  direction: string;
  bankAmount: string;
  oaAmount: string;
  amountDelta: string;
  requiresNote: boolean;
};

export type BatchAccountingRelation = {
  relationId: string;
  note: string;
  amountCheck?: BatchAccountingAmountCheck;
};
```

Change `relationsByBankRowId` to retain relation metadata:

```ts
relationsByBankRowId: Record<string, {
  relationId: string;
  relation?: BatchAccountingRelation;
  oaRows: BatchAccountingOaRow[];
}>;
```

Add `note?: string` to `SubmitBatchAccountingRequest`.

- [ ] **Step 4: Extend API mapper and submit body**

In `api.ts`:

- Map `amount_check` / `amountCheck`.
- Map relation `note`.
- Keep backward compatibility for old array-only `relations_by_bank_row_id` entries.
- Always include `note` in POST body, using the trimmed note or `""`.

- [ ] **Step 5: Implement page state and submit rules**

In `BatchAccountingPage.tsx`:

- Add `const [differenceNote, setDifferenceNote] = useState("");`.
- Define `isAmountMismatch = selectedBankRow && selectedOaRows.length > 0 && differenceCents !== 0`.
- Change `canSubmit`:

```ts
const canSubmit = Boolean(selectedBankRow)
  && selectedOaRows.length > 0
  && isValidYear(bankYear)
  && isValidYear(oaYear)
  && !mutating
  && (differenceCents === 0 || differenceNote.trim().length > 0);
```

- Clear note in `handleBucketChange` and `handleSelectBankRow`.
- Do not clear note in `handleOaToggle`.
- Render `TextField` with label `差额说明` and helper text `金额不一致时必须填写，提交后视为人工差额闭环。` only when `isAmountMismatch`.
- Pass `note: differenceNote.trim()` to `submitBatchAccounting`; the API layer must serialize `note` even when it is `""`.

- [ ] **Step 6: Render submitted mismatch note/status**

When `bucket === "submitted"` and selected relation has `amountCheck.status === "mismatch"`, show a compact existing-control-compatible indicator in the right header. Do not add a new table row and do not append to bank/OA original text.

Use the relation metadata from `payload.relationsByBankRowId[selectedBankRow.id]`.

- [ ] **Step 7: Run batch frontend tests**

Run:

```bash
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx
```

Expected: PASS.

---

### Task 4: Workbench Frontend Mapping and Warning Icon Tooltip

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/components/workbench/WorkbenchRecordCard.tsx`
- Test: `web/src/test/WorkbenchApi.test.ts`
- Test: `web/src/test/WorkbenchSelection.test.tsx` or `web/src/test/WorkbenchZone.test.tsx`

- [ ] **Step 1: Write mapping test**

In `web/src/test/WorkbenchApi.test.ts`, add a raw workbench group with:

```ts
relation_note: "财务确认差额闭环",
amount_check: {
  status: "mismatch",
  direction: "expense",
  bank_amount: "3617.41",
  oa_amount: "3425.41",
  amount_delta: "192.00",
  requires_note: true,
},
bank_rows: [{
  id: "txn_imported_202601_batch_001",
  type: "bank",
  amount: "3617.41",
  relation_note: "财务确认差额闭环",
  relation_amount_check: { ...same values... },
}]
```

Assert mapped group and row contain:

```ts
expect(group.relationNote).toBe("财务确认差额闭环");
expect(group.amountCheck?.status).toBe("mismatch");
expect(bankRow.relationNote).toBe("财务确认差额闭环");
expect(bankRow.relationAmountCheck?.amountDelta).toBe("192.00");
```

- [ ] **Step 2: Run mapping test to verify failure**

Run:

```bash
cd web && npm test -- --run src/test/WorkbenchApi.test.ts
```

Expected: FAIL because fields are not mapped yet.

- [ ] **Step 3: Extend workbench types and mapper**

In `types.ts`, add a `WorkbenchAmountCheck` type and optional fields:

```ts
relationNote?: string;
amountCheck?: WorkbenchAmountCheck;
relationAmountCheck?: WorkbenchAmountCheck;
```

In `api.ts`, map snake_case to camelCase:

- `relation_note` -> `relationNote`
- `amount_check` -> `amountCheck`
- `relation_amount_check` -> `relationAmountCheck`

Keep unknown string statuses allowed.

- [ ] **Step 4: Write icon rendering test**

In `web/src/test/WorkbenchSelection.test.tsx` or `web/src/test/WorkbenchZone.test.tsx`, add a paired bank row with `relationAmountCheck.status = "mismatch"` and `relationNote`.

Assert:

```tsx
const icon = await screen.findByLabelText("查看金额不一致差额说明");
expect(icon).toBeInTheDocument();
await user.click(icon);
expect(await screen.findByText("金额不一致")).toBeInTheDocument();
expect(screen.getByText(/银行流水金额：3,617.41/)).toBeInTheDocument();
expect(screen.getByText(/OA合计：3,425.41/)).toBeInTheDocument();
expect(screen.getByText(/差额：192.00/)).toBeInTheDocument();
expect(screen.getByText(/差额说明：财务确认差额闭环/)).toBeInTheDocument();
```

Also assert:

- keyboard focus opens or exposes the same tooltip content;
- hover opens or exposes the same tooltip content if the project test utilities support hover reliably;
- a matched row does not show the icon;
- a mismatch row with no `relationNote` and `requiresNote !== true` does not show the icon.

- [ ] **Step 5: Implement warning icon beside bank amount**

In `WorkbenchRecordCard.tsx`:

- Find the bank amount rendering path.
- Add an icon button or focusable icon beside the amount only when all are true:
  - row type is bank;
  - row `relationAmountCheck.status === "mismatch"`;
  - `row.relationNote` is non-empty or `row.relationAmountCheck.requiresNote === true`.
- Use existing MUI tooltip/icon patterns if present in the file; otherwise import a MUI warning icon and tooltip/popover consistent with project style.
- Tooltip must support hover, focus, click/touch.
- Accessible label: `查看金额不一致差额说明`.
- Do not add a row or mutate the note column.

Tooltip text should render:

```text
金额不一致
银行流水金额：{bankAmount}
OA合计：{oaAmount}
差额：{amountDelta}
差额说明：{relationNote || "—"}
```

- [ ] **Step 6: Run workbench frontend tests**

Run:

```bash
cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx
```

Expected: PASS.

---

### Task 5: Integration Verification and Documentation Hygiene

**Files:**
- Modify only files already touched in Tasks 1-4 if integration defects are found.
- No new product scope.

- [ ] **Step 1: Run backend focused suite**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_v2_api -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused suite**

Run:

```bash
cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/WorkbenchApi.test.ts src/test/WorkbenchSelection.test.tsx src/test/WorkbenchZone.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 4: Inspect final worktree and protect unrelated changes**

Run:

```bash
git status --short
git diff -- backend/src/fin_ops_platform/app/server.py
```

Expected: Only planned files changed by the workers plus pre-existing unrelated changes. Do not stage or revert unrelated ETC or other files.

- [ ] **Step 5: Final implementation report**

Report:

- Files changed.
- Tests run and results.
- Any unrelated pre-existing dirty files.
- Any remaining risks.

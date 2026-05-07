# OA Expense Claim Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change OA ingestion so each expense claim OA flow appears as one workbench OA row that can relate to multiple invoice rows.

**Architecture:** Aggregate expense claim `schedule` items inside `MongoOAAdapter`, keep invoice rows as separate rows in `WorkbenchQueryService`, invalidate old read models with a schema version bump, and keep reset operations scoped to OA-derived state only.

**Tech Stack:** Python backend services and tests, React/TypeScript workbench UI, existing Mongo-backed state store.

---

## Task 1: Backend OA Aggregation

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. Implement backend OA expense claim aggregation only.

Requirements:

1. Modify `backend/src/fin_ops_platform/services/oa_adapter.py`.
   - Extend `OAApplicationRecord` with optional fields:
     - `expense_items: list[dict[str, str]] = field(default_factory=list)`
     - `amount_source: str | None = None`
     - `amount_mismatch: dict[str, str] | None = None`
   - Preserve backward compatibility for existing callers.

2. Modify `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`.
   - Replace the expense claim behavior that emits one record per `schedule` row with one record per OA document.
   - New expense row id format: `oa-exp-{external_id}`.
   - Main amount resolution:
     - Use document-level `amount` first.
     - If document-level amount is missing/invalid, sum `detailReimbursementAmount` / `amount` from schedule items.
     - Track source as `header` or `detail_sum`.
     - If both header and detail sum exist and differ, populate `amount_mismatch` with header amount, detail sum, and difference.
   - Aggregate detail fields:
     - `OA单号`, `表单ID`, `申请日期`, `流程状态`
     - `明细数量`
     - `明细金额合计`
     - `金额来源`
     - `金额差异` when applicable
     - `项目名称汇总`
     - `费用类型汇总`
     - `费用内容摘要`
     - `报销日期范围`
   - Aggregate attachment files from every schedule item and parse invoices once into the single OA record.
   - Deduplicate parsed attachment invoices by invoice number/digital invoice number plus attachment name fallback.
   - Continue detecting ETC metadata from the document and schedule item text.

3. Update row id parsing.
   - `EXPENSE_ROW_ID_RE` must accept both:
     - new `oa-exp-{external_id}`
     - old `oa-exp-{external_id}-{row_index}`
   - `list_application_records_by_row_ids()` must return the new aggregated record for both new and old ids.
   - It should not duplicate records when both old and new ids are requested.

4. Update `tests/test_mongo_oa_adapter.py`.
   - Change existing tests that expect split rows.
   - Add tests for:
     - one expense document with two schedule rows returns one OA record.
     - amount uses header total when present.
     - amount falls back to schedule sum when header total missing.
     - amount mismatch detail fields are populated.
     - attachments from multiple schedule rows are aggregated and deduped.
     - `list_application_records_by_row_ids(["oa-exp-exp-001", "oa-exp-exp-001-1"])` returns one aggregated record.

Verification:

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_mongo_oa_adapter.py -q
```

Return changed file paths and test output.

## Task 2: Workbench Query, Attachment Rows, and Read Model Version

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. Implement workbench compatibility for aggregated OA rows.

Dependencies: Task 1 changes may be present. If not present, inspect current files and make minimal compatible edits.

Requirements:

1. Modify `backend/src/fin_ops_platform/services/workbench_query_service.py`.
   - Ensure `_build_oa_row()` exposes new OA fields in `detail_fields`:
     - `金额来源`
     - `明细数量`
     - `明细金额合计`
     - `金额差异`
     - `费用内容摘要`
     - `附件发票摘要`
   - Add explicit OA row tags for:
     - `多明细` when expense_items length > 1.
     - `金额差异` when amount_mismatch is present.
   - Ensure `_build_attachment_invoice_rows()` still generates one invoice row per attachment invoice from a single aggregated OA.
   - Ensure `来源OA明细行号` can be `整单` or blank when there is no specific line.

2. Modify `backend/src/fin_ops_platform/app/server.py`.
   - Bump `WORKBENCH_READ_MODEL_SCHEMA_VERSION` to a new value such as `2026-05-06-oa-expense-aggregation`.
   - Ensure stale cached read models are rebuilt automatically through existing schema check.

3. Update tests.
   - `tests/test_workbench_query_service.py`: add or update tests so one OA with multiple attachment invoices yields one OA row and multiple invoice rows sharing a case id.
   - `tests/test_workbench_v2_api.py`: update old id expectations that were tied to split OA rows where needed. Add a regression test that old id detail lookup `oa-exp-...-0` can still resolve through backend row id compatibility if the service path supports it.

Verification:

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_query_service.py tests/test_workbench_v2_api.py -q
```

Return changed file paths and test output.

## Task 3: Settings Reset Scope

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. Implement production-grade OA reset scope.

Requirements:

1. Modify `backend/src/fin_ops_platform/services/settings_data_reset_service.py`.
   - For `RESET_OA_AND_REBUILD_ACTION`, clear only OA-related workbench state.
   - Delete row overrides where row id is OA-derived:
     - `type == "oa"`
     - id starts with `oa-`
     - id starts with `oa-att-inv-`
     - row override payload references OA-derived rows.
   - Delete pair relations only if any row id is OA-derived (`oa-` or `oa-att-inv-`).
   - Preserve pure bank/invoice pair relations that do not include OA-derived rows.
   - Always clear workbench read models, because row ids and grouping changed.
   - Keep OA attachment invoice cache unless existing behavior explicitly says otherwise.
   - Return deleted counts for removed OA overrides, removed OA pair relations, preserved non-OA pair relations, and read models.

2. Modify `backend/src/fin_ops_platform/app/server.py` only if needed.
   - Ensure reset rebuild path calls the new aggregation logic through normal `_build_api_workbench_payload("all")`.
   - Ensure progress messages still match the existing background job contract.

3. Update `tests/test_settings_data_reset_service.py`.
   - Add a test that `reset_oa_and_rebuild` preserves a pure bank+invoice pair relation.
   - Add a test that `reset_oa_and_rebuild` removes a relation containing `oa-exp-1994`.
   - Add a test that `reset_oa_and_rebuild` removes a relation containing `oa-att-inv-oa-exp-1994-01`.
   - Update old expected attachment invoice id format after Task 1 if needed.

Verification:

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_settings_data_reset_service.py -q
```

Return changed file paths and test output.

## Task 4: Frontend Details and Search Compatibility

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. Avoid touching `web/src/app/styles.css` and `web/src/components/workbench/CandidateGroupGrid.tsx` unless absolutely required because they have unrelated user edits.

Requirements:

1. Modify `web/src/features/workbench/api.ts`.
   - Map new OA detail fields without dropping them.
   - Make OA search values include detail fields such as:
     - 明细摘要
     - 费用内容摘要
     - 附件发票摘要
     - 明细金额合计
     - 金额差异
   - Preserve existing table values.

2. Modify `web/src/components/workbench/DetailDrawer.tsx` if needed.
   - Keep generic detail rendering.
   - If there is an existing visual section pattern, make OA detail fields readable when there are many invoice summaries.
   - Do not redesign the page.

3. Modify frontend tests.
   - Add or update tests in `web/src/test` covering:
     - OA detail drawer shows aggregated detail fields.
     - Search can find an OA by attachment invoice summary or fee content summary.
   - Use existing testing patterns.

Verification:

Run:

```bash
cd web
npx vitest run src/test
```

If this is too broad or slow, run the smallest relevant test files and state what was run.

Return changed file paths and test output.

## Task 5: End-to-End Verification and Documentation Update

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. This is a verification/documentation task.

Requirements:

1. Read the final changed files from Tasks 1-4.
2. Update documentation if behavior changed:
   - `docs/dev/reconciliation-workbench-v2-data-contracts.md`
   - Any relevant README section if it documents OA row semantics.
3. Run targeted backend tests:

```bash
PYTHONPATH=backend/src python3 -m pytest \
  tests/test_mongo_oa_adapter.py \
  tests/test_workbench_query_service.py \
  tests/test_settings_data_reset_service.py \
  tests/test_workbench_v2_api.py \
  -q
```

4. Run targeted frontend tests if changed:

```bash
cd web
npx vitest run src/test
```

5. Run a read-only script against real local OA data to verify:
   - OA `1994` appears as one OA record with amount `1549.00`.
   - OA `2045` appears as one OA record.
   - OA `2080` appears as one OA record.
   - No split ids like `oa-exp-1994-0` appear in current generated records.

Return a concise verification report, changed files, and any remaining risks.

## Task 6: Production Multi-Invoice Candidate Grouping for Aggregated OA

**Prompt for Codex worker:**

You are working in `/Users/yu/Desktop/fin-ops-platform`. You are not alone in the codebase; do not revert edits made by others. Implement production-grade workbench grouping for the generic case where one aggregated OA row corresponds to multiple manually imported invoice rows. This must not be ETC-specific.

Context:

- Expense claim OA rows are now aggregated: one OA document should appear as one `oa` row.
- A single aggregated OA may correspond to multiple imported invoice rows.
- The workbench must show the single OA row and the matching invoice rows in the same candidate group/visual row.
- This is only a candidate display grouping. Do not auto-confirm pair relations and do not mutate persisted relation state.
- A previous emergency fix may exist in `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py` with ETC-specific names such as `ETC_INVOICE_KEYWORDS`, `_is_aggregated_etc_expense_oa_row`, `_is_etc_invoice_row`, or reason `aggregated_oa_etc_invoice_sum_candidate`. Replace that narrow logic with the generic rule below.

Requirements:

1. Modify `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`.
   - Add a generic grouping pass before normal standalone temp grouping.
   - Eligible OA rows:
     - `type == "oa"`.
     - not paired and no `case_id`.
     - has a valid amount.
     - has a bounded OA month window. Do not require ETC keywords and do not require `明细数量 > 1`; a single OA line can still be backed by multiple invoice rows.
   - Eligible invoice rows:
     - `type == "invoice"`.
     - not paired and no `case_id`.
     - `source_kind != "oa_attachment_invoice"`.
     - direction matches the OA direction using existing `_direction`.
     - if the OA has a normalized counterparty, require invoice normalized counterparty to match.
     - if the OA counterparty is empty, allow matching-direction invoices, but rely on exact unique subset matching and conflict checks.
     - invoice month must match a bounded OA month window.
   - OA month window:
     - collect month candidates from `pay_receive_time`, `apply_date`, `_month`, `_detail_fields["申请日期"]`, `detail_fields["申请日期"]`.
     - include each collected month and its previous month.
     - if no OA month can be derived, do not create generic multi-invoice candidates for that OA.
   - Matching:
     - use invoice `total_with_tax` when present; otherwise use `amount`.
     - find a subset whose sum exactly equals the OA amount.
     - require at least two invoice rows in the matched subset. Single-invoice matches should continue to use the existing normal candidate grouping path.
     - if multiple subsets can equal the same OA amount, skip that OA as ambiguous.
     - evaluate all eligible OAs first; if the same invoice is selected by more than one OA candidate, skip all conflicting OA candidates.
     - keep subset search bounded and deterministic. If candidate pool is too large for safe matching, skip rather than doing unbounded work.
   - Output:
     - create `CandidateGroup(group_type="candidate", match_confidence="medium", reason="aggregated_oa_multi_invoice_sum_candidate")`.
     - put one OA row and all matched invoice rows in the group.
     - remove grouped rows from remaining rows so they do not also appear as standalone rows.
   - Preserve existing OA attachment invoice behavior, existing bank/invoice/three-way behavior, and existing auto-close behavior.

2. Modify `tests/test_workbench_candidate_grouping.py`.
   - Add or update tests for:
     - one generic non-ETC aggregated OA with two manually imported invoices whose `total_with_tax` values sum exactly to the OA amount.
     - an OA with empty `counterparty_name` still groups when the invoice subset is uniquely identifiable by amount and month.
     - ambiguous subsets are not grouped.
     - cross-OA conflicts are not grouped: if the same invoice subset could match two OAs, neither OA should consume those invoices.
     - OA attachment invoice tests still pass.

3. Modify `backend/src/fin_ops_platform/app/server.py`.
   - Bump `WORKBENCH_READ_MODEL_SCHEMA_VERSION` again so stale cached workbench read models are rebuilt with the generic grouping payload.

Verification:

Run:

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_candidate_grouping.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_query_service.py tests/test_workbench_v2_api.py -q
git diff --check
```

Return changed file paths, test output, and remaining risks. Do not commit.

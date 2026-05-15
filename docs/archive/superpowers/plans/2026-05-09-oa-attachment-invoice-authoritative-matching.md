# OA Attachment Invoice Authoritative Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OA attachment invoices participate in the authoritative workbench candidate pipeline so a single OA can close with its parsed attachment invoices and matching bank transaction in one row.

**Architecture:** OA attachment invoice rows are source-derived rows, not ordinary loose invoices. `WorkbenchMatchingRules` must treat `source_kind=oa_attachment_invoice` plus `derived_from_oa_id`/`oa_row_id` as strong source evidence, and `WorkbenchCandidateGrouping` must keep those rows attached to their source OA even when candidate case ids differ. Reconciliation amounts for OA attachment invoices use gross amount (`total_with_tax`) before net amount.

**Tech Stack:** Python services under `backend/src/fin_ops_platform/services`, unittest/pytest tests under `tests`.

---

## Requirements

- OA attachment invoice parsing remains in `OAAttachmentInvoiceService` and `MongoOAAdapter`; this work updates candidate matching and grouping only.
- OA attachment invoice identity:
  - `source_kind == "oa_attachment_invoice"`
  - source OA id from `derived_from_oa_id` first, then `oa_row_id`.
- Source-linked OA attachment invoices must not compete with manual imported duplicate invoices when producing the OA source-link candidate.
- Matching amount for OA attachment invoice close-loop checks must use `total_with_tax` first, then `amount`.
- If OA amount equals source-linked attachment invoice gross sum but there is no matching bank row, create an open candidate (`incomplete` or `needs_review`), not an auto-closed paired group.
- If OA amount, one bank transaction amount, and source-linked attachment invoice gross sum are all equal, create a high-confidence `auto_closed` candidate.
- Grouping must attach source-linked OA attachment invoice rows to the group containing their source OA before temp/case grouping splits them into standalone candidates.
- Existing ordinary invoice, bank, special rule, and manual confirmed grouping behavior must not regress.

## Codex Task Prompts

### Prompt 1: Rules Layer

Modify `backend/src/fin_ops_platform/services/workbench_matching_rules.py` and `tests/test_workbench_matching_rules.py`.

- Add tests first for `oa_attachment_invoice_source_link` behavior:
  - OA `oa-tian` amount `196.00`.
  - Bank `bank-tian` amount `196.00`, counterparty `田孟维`.
  - Two OA attachment invoices linked to `oa-tian`: gross amounts `70.00` and `126.00`; net amounts `66.04` and `124.75`.
  - Two manual imported duplicate invoices with the same invoice numbers/gross amounts.
  - Expected: one high-confidence auto-closed candidate containing OA, bank, and only the two OA attachment invoice rows.
- Add no-bank test:
  - Same OA and source-linked attachment invoices, no bank.
  - Expected: open candidate with OA and source-linked attachment invoices; not auto-closed.
- Implement the source-link rule before generic multi-invoice sum rules.
- Use `derived_from_oa_id` or `oa_row_id` to identify source-linked invoices.
- Use gross amount (`total_with_tax`) for source-linked attachment invoice sums.
- Keep sum matching limits and ambiguity checks for generic rules unchanged.

### Prompt 2: Grouping Layer

Modify `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py` and `tests/test_workbench_candidate_grouping.py`.

- Add tests first for source attachment regrouping:
  - OA and bank share a candidate case id.
  - Two OA attachment invoice rows have different candidate case ids, but `derived_from_oa_id` points to the OA.
  - Expected: one paired group containing OA, bank, and both attachment invoices when gross amounts close.
- Change grouping so source-linked OA attachment invoice rows attach to a group containing their source OA before temp/case grouping finalization.
- Update `_attachment_invoice_reconciliation_amount` to use `total_with_tax` before `amount`.
- Do not change ordinary manual imported invoice grouping semantics.

### Prompt 3: Integration Verification

Run:

```bash
pytest tests/test_workbench_matching_rules.py tests/test_workbench_candidate_grouping.py -q
pytest tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_get_api_workbench_merges_oa_attachment_invoice_rows_into_live_grouping -q
```

Then, if the local backend is running, inspect January workbench payload for `oa-exp-1970`:

```bash
curl -sS 'http://127.0.0.1:8001/api/workbench?month=2026-01' | jq '...'
```

Expected behavior: `oa-exp-1970`, `txn_imported_0743`, and `oa-att-inv-oa-exp-1970-01/02` appear in the same candidate/paired group. If the API still shows stale data, invalidate workbench read model/candidate cache according to existing service conventions rather than adding ad hoc frontend logic.

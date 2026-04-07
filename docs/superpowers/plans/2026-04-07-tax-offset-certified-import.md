# Tax Offset Certified Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the tax offset page's placeholder certified-invoice import with a real Excel import flow based on the provided “进项认证结果 用途确认信息” templates, persist the imported certified invoices, and drive plan locking plus tax calculation from imported data instead of hardcoded samples.

**Architecture:** Build a dedicated certified-invoice import pipeline for the tax-offset domain: parse the template `发票` sheet, persist normalized certified invoice records by month, then update the tax offset read model so it derives `matched_in_plan`, `certified_outside_plan`, and `locked` plan state from persisted imports. Finally wire the tax-offset modal to preview, confirm, and refresh the page.

**Tech Stack:** Python backend services, workbook parsing with `openpyxl`, existing state store, React 18, TypeScript, Testing Library.

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/tax_offset_service.py`
- Modify: `backend/src/fin_ops_platform/services/state_store.py`
- Create: `backend/src/fin_ops_platform/services/tax_certified_import_service.py`
- Create or modify: `tests/test_tax_offset_api.py`
- Create or modify: `tests/test_tax_offset_service.py`
- Create: `tests/test_tax_certified_import_service.py`

### Frontend

- Modify: `web/src/components/tax/CertifiedInvoiceImportModal.tsx`
- Modify: `web/src/pages/TaxOffsetPage.tsx`
- Modify: `web/src/features/tax/api.ts`
- Modify: `web/src/features/tax/types.ts`
- Modify: `web/src/test/TaxOffsetPage.test.tsx`
- Modify: `web/src/test/apiMock.ts`

### Docs

- Modify: `银企核销需求.md`
- Modify: `docs/README.md`
- Modify: `prompts/README.md`

---

## Task 1: Build certified invoice template parsing and persistence

- [ ] Write a failing backend test for parsing the provided “进项认证结果 用途确认信息.xlsx” template
- [ ] Run the targeted test and confirm failure
- [ ] Normalize only the `发票` sheet into certified invoice records
- [ ] Extract and persist:
  - invoice number fields
  - seller tax no / seller name
  - issue date
  - amount / tax amount / deductible tax
  - selection status
  - invoice status
  - check time
- [ ] Add batch/file level metadata and deduplication
- [ ] Run targeted backend tests and confirm they pass

## Task 2: Replace hardcoded certified data with imported data in tax offset service

- [ ] Write a failing backend test proving `/api/tax-offset` uses persisted certified imports instead of hardcoded `certified_items`
- [ ] Run the targeted test and confirm failure
- [ ] Keep output invoices and input plan invoices logic intact
- [ ] Build `certified_matched_rows` from persisted imports
- [ ] Build `certified_outside_plan_rows` from persisted imports
- [ ] Derive `locked_certified_input_ids` from real matches
- [ ] Keep the calculation rule:
  - all certified invoices always count
  - only selected uncertified plan rows add to plan tax
- [ ] Run targeted backend tests and confirm they pass

## Task 3: Implement tax offset certified import modal preview and confirm flow

- [ ] Write a failing frontend test for the certified import modal preview/confirm flow
- [ ] Run the targeted test and confirm failure
- [ ] Add preview request and confirm request APIs
- [ ] Show preview summary inside the modal:
  - recognized rows
  - matched plan rows
  - outside-plan certified rows
  - invalid/unmatched imported rows
- [ ] Confirm import and refresh tax offset page in place
- [ ] Run targeted frontend tests and confirm they pass

## Task 4: Harden, document, and verify

- [ ] Run full backend tests
- [ ] Run full frontend tests
- [ ] Run frontend build
- [ ] Update docs and prompt indexes
- [ ] Manual verification:
  - import the provided 2026-01 template
  - import the provided 2026-02 template
  - confirm matched plan rows become locked/grey
  - confirm outside-plan certified rows appear in the drawer
  - confirm summary and result amounts include certified invoices automatically

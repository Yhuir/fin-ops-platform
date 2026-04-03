# Tax Offset Certified Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the tax offset page into a clear “计划 vs 实际” workspace with read-only output invoices, editable input certification plan rows, and a right-side certified results drawer that locks matched plan items.

**Architecture:** Extend the tax offset backend contract so it returns separate output invoices, input plan invoices, and certified imported invoices, plus explicit lock and match metadata. Then rebuild the frontend tax offset page around a two-column main workspace and a right drawer, with recalculation based on “all certified + selected uncertified plan rows”.

**Tech Stack:** Python backend services, existing tax offset API, React 18, TypeScript, Vite, Testing Library.

---

## File Map

### Backend

- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `backend/src/fin_ops_platform/services/tax_offset_service.py` or equivalent tax aggregation service
- Modify: `backend/src/fin_ops_platform/services/import_file_service.py` if certified import metadata must be read
- Modify: `backend/src/fin_ops_platform/services/state_store.py` if certified invoice state needs persistence support
- Create or modify: `tests/test_tax_offset_api.py`
- Create or modify: `tests/test_tax_offset_service.py`

### Frontend

- Modify: `web/src/pages/TaxOffsetPage.tsx`
- Modify: `web/src/components/tax/TaxTable.tsx`
- Create: `web/src/components/tax/CertifiedResultsDrawer.tsx`
- Modify: `web/src/components/tax/TaxSummaryCards.tsx`
- Modify: `web/src/components/tax/TaxResultPanel.tsx`
- Modify: `web/src/features/tax/api.ts`
- Modify: `web/src/features/tax/types.ts`
- Modify: `web/src/app/styles.css`
- Modify: `web/src/test/apiMock.ts`
- Modify: `web/src/test/TaxOffsetPage.test.tsx`
- Modify: `web/src/test/App.test.tsx` if navigation expectations change

### Docs

- Modify: `docs/README.md`
- Modify: `prompts/README.md`
- Optionally create after implementation: `docs/dev/tax-offset-certified-plan.md`

---

## Task 1: Redefine the tax offset data contract

- [ ] Write a failing backend test that expects output invoices to be returned as read-only rows
- [ ] Run the targeted test and confirm failure
- [ ] Write a failing backend test that expects input plan rows to carry:
  - selection state
  - locked certified state
  - status label
- [ ] Run the targeted test and confirm failure
- [ ] Extend the tax offset payload to return:
  - `outputInvoices`
  - `inputPlanInvoices`
  - `certifiedResults`
  - `certifiedMatchedRows`
  - `certifiedOutsidePlanRows`
  - `lockedCertifiedInputIds`
- [ ] Run targeted backend tests and confirm they pass

## Task 2: Implement certified import matching and recalculation rules

- [ ] Write a failing backend test for matching certified imported invoices back into input plan invoices
- [ ] Run the targeted test and confirm failure
- [ ] Write a failing backend test for certified imported invoices that do not exist in the current plan
- [ ] Run the targeted test and confirm failure
- [ ] Implement first-version matching rules using:
  - digital invoice number
  - invoice code + invoice number
  - date
  - amount
  - seller identifier / seller name
- [ ] Implement recalculation rule:
  - all certified invoices are always included
  - only selected and uncertified plan invoices are additionally included
- [ ] Run targeted backend tests and confirm they pass

## Task 3: Rebuild the tax offset page layout

- [ ] Write a failing frontend test that expects the old symmetric dual-selection layout to be replaced
- [ ] Run the targeted test and confirm failure
- [ ] Remove `返回关联台`
- [ ] Keep header actions to:
  - `已认证发票导入`
  - month picker
- [ ] Rebuild the main layout into:
  - left: `销项票开票情况`
  - center: `进项票认证计划`
  - right drawer: `已认证结果`
- [ ] Run targeted frontend tests and confirm they pass

## Task 4: Lock output rows and certified input rows

- [ ] Write a failing frontend test that output invoice rows cannot be toggled
- [ ] Run the targeted test and confirm failure
- [ ] Write a failing frontend test that certified matched input rows render disabled and greyed out
- [ ] Run the targeted test and confirm failure
- [ ] Update the tax table component so:
  - output rows never render as selectable
  - input plan rows remain selectable
  - locked certified rows are disabled
- [ ] Run targeted frontend tests and confirm they pass

## Task 5: Add the certified results drawer

- [ ] Write a failing frontend test for the right-side certified drawer
- [ ] Run the targeted test and confirm failure
- [ ] Create `CertifiedResultsDrawer`
- [ ] Render two groups:
  - `已匹配计划`
  - `已认证但未进入计划`
- [ ] Show matched counts on the drawer handle when collapsed
- [ ] Clicking a matched certified row should highlight the corresponding input plan row
- [ ] Run targeted frontend tests and confirm they pass

## Task 6: Update summary and result calculation presentation

- [ ] Write a failing frontend test for new summary semantics:
  - output tax
  - certified input tax
  - planned input tax
  - final result
- [ ] Run the targeted test and confirm failure
- [ ] Update summary cards and result panel copy to reflect:
  - read-only output base
  - certified actuals
  - editable plan
- [ ] Confirm recalculation only depends on:
  - certified actuals
  - selected uncertified plan rows
- [ ] Run targeted frontend tests and confirm they pass

## Task 7: Harden, document, and verify

- [ ] Run full frontend tests
- [ ] Run frontend build
- [ ] Run full backend tests
- [ ] Update prompt and docs indexes
- [ ] Perform manual verification:
  - output invoices are not selectable
  - input plan rows are selectable
  - certified matched rows lock correctly
  - certified outside-plan rows appear only in the drawer
  - removing `返回关联台` does not break page navigation


# server-py:workbench-retained-all-oa-payload-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-oa-payload-builder-extraction`
**Selected next boundary:** `server-py:workbench-retained-all-oa-payload-builder-extraction`

## Purpose

Audit `_build_retained_all_oa_row_payload(...)`, retained month selection, supplemental retained OA row selection, parse suppression and selected-scope raw OA payload construction.

## Findings

- `_build_retained_all_oa_row_payload(...)` owns retained-all orchestration:
  - no-cutoff all-scope payload load and promotion;
  - retained month/supplemental row lookup;
  - background parse suppression while syncing retained scopes and supplemental row ids;
  - selected-scope raw OA payload construction;
  - promotion scope calculation.
- Retained month selection, supplemental retained OA row selection and selected-scope raw OA payload construction remain separate helper trees and should not be moved in the same slice.

## Decision

Select `server-py:workbench-retained-all-oa-payload-builder-extraction` as the next narrow local implementation boundary.

This moves only retained-all orchestration into a builder with explicit ports, while deferring supplemental retained OA row selection and selected-scope raw OA payload internals.

## Out Of Scope

- No production browser/admin/write validation.
- No supplemental retained OA row selection migration.
- No selected-scope raw OA payload migration.
- No canonical OA attachment promotion internals migration.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.

# server-py:workbench-supplemental-retained-oa-row-selection-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-retained-all-oa-payload-builder-extraction`
**Selected next boundary:** `server-py:workbench-supplemental-retained-oa-row-selector-extraction`

## Purpose

Audit `_supplemental_retained_oa_row_ids(...)`, retained OA supplemental relation read port, live row resolution and retention date checks.

## Findings

- `_supplemental_retained_oa_row_ids(...)` owns selection of manual retained OA rows plus relation-linked OA rows whose bank rows are on or after the retention cutoff.
- The method already uses `WorkbenchRetainedOaSupplementalRelationReadPort`, but still owns relation row/type parsing, live bank row resolution and cutoff predicate application.
- This selection logic can move into a focused service with explicit manual row, relation port, live row resolver and date predicate dependencies.

## Decision

Select `server-py:workbench-supplemental-retained-oa-row-selector-extraction` as the next narrow local implementation boundary.

This keeps retained all-OA payload orchestration and selected-scope raw OA payload construction unchanged while moving supplemental retained OA row selection out of `Application`.

## Out Of Scope

- No production browser/admin/write validation.
- No selected-scope raw OA payload migration.
- No retention date parsing migration.
- No relation read port implementation change.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.

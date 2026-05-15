# Workbench DataGrid Pro Spike Boundary

Date: 2026-05-04

This document records the boundary for a future DataGrid Pro spike. It is not part of the current MUI Community refactor and must not introduce Pro or Premium dependencies.

## Current Decision

The reconciliation workbench keeps its custom tri-pane sheet grid in the Community-only MUI refactor.

The following modules remain the production layout boundary:

- `web/src/components/workbench/CandidateGroupGrid.tsx`
- `web/src/components/workbench/CandidateGroupCell.tsx`
- `web/src/components/workbench/WorkbenchRecordCard.tsx`
- `web/src/components/workbench/ResizableTriPane.tsx`
- `web/src/features/workbench/groupDisplayModel.ts`
- `web/src/features/workbench/tableConfig.ts`
- `web/src/features/workbench/columnLayout.ts`

MUI can be used around this boundary for dialogs, drawers, menus, buttons, filters, loading states, and page chrome. The grouped sheet layout itself is intentionally not replaced by DataGrid Community.

## Why Community DataGrid Is Not Enough

The workbench requires behavior that is outside the Community DataGrid scope or risky to reproduce with independent grids:

- Three panes must preserve candidate-group row height alignment.
- One OA record can visually align to multiple bank or invoice rows.
- Single-row groups stretch while multi-row groups split without losing the sheet band.
- Pane widths are manually resizable and can collapse to zero width.
- Column order is persisted per workbench pane.
- Current row click selects rows without opening detail.
- Group-level hover and `caseId` highlight must stay synchronized across panes.

Known MUI X licensing boundaries:

- Column pinning is Pro.
- Column reordering is Pro in DataGrid.
- Master-detail panels are Pro.
- Row grouping is Premium.
- Excel export is Pro/Premium and must not replace backend export.

## Spike Preconditions

Only run this spike if the user explicitly agrees to evaluate Pro membership.

Before any production changes, create a separate prototype route or isolated prototype file. Do not modify the production workbench route and do not delete the custom implementation.

## Prototype Questions

The spike must answer these questions with working UI and tests or screenshots:

- Can three independent DataGrid instances keep group row heights synchronized under filtering, sorting, expansion, and density changes?
- Can a single logical candidate group render as one horizontal sheet band across OA, bank, and invoice panes?
- Can `1 to many` and `many to many` candidate groups preserve the current visual relation without confusing row focus and keyboard navigation?
- Can manual pane resizing and collapsed panes coexist with DataGrid virtualization?
- Can the existing column layout contract map cleanly to Pro column reorder and pinning?
- Can row selection, detail actions, ignore/restore, exception handling, and confirm/cancel actions keep the current API calls unchanged?
- Does virtualization preserve performance on the largest expected workbench response?

## Pass Criteria

The spike can be considered viable only if all of the following are true:

- Existing workbench behavior is preserved or improved.
- `WorkbenchSelection.test.tsx`, `CandidateGroupGrid.test.tsx`, `WorkbenchColumns.test.tsx`, `WorkbenchColumnLayout.test.tsx`, `WorkbenchZone.test.tsx`, `WorkbenchSearchModal.test.tsx`, and `WorkbenchImportModal.test.tsx` can be kept or replaced by equivalent coverage.
- Complex candidate groups are visually clear at desktop and embedded OA widths.
- The required Pro/Premium features and license cost are explicitly accepted.
- The prototype does not require backend contract changes.

## Current Refactor Rule

Until the spike passes, ordinary pages may use DataGrid Community, but the workbench tri-pane core must stay on the custom sheet grid.

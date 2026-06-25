# server-py:workbench-raw-payload-row-id-set-helper-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `_raw_workbench_payload_row_ids(...)` and its caller.

## Findings

- The helper is pure raw payload pane traversal:
  - paired/open section handling;
  - OA/bank/invoice pane handling;
  - row id normalization into a `set[str]`.
- The only current caller is the OA invoice offset sync executor factory.
- The behavior belongs with the existing `WorkbenchOaAttachmentContextRowIndex` because that class already owns raw payload row indexing and pane traversal.

## Decision

Select `server-py:workbench-raw-payload-row-id-set-helper-extraction`.

## Deferred

- No production validation is required for this pure helper.
- Production browser/admin/write evidence remains deferred.

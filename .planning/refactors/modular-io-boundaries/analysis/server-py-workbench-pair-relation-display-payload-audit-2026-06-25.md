# server-py:workbench-pair-relation-display-payload-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `_apply_pair_relation_to_row(...)`, `_pair_relation_display_payload(...)`, relation metadata decorators and mode-specific pair metadata calls.

## Findings

- `_apply_pair_relation_to_row(...)` still mixes multiple responsibilities:
  - relation field assignment;
  - display payload lookup;
  - relation metadata propagation;
  - amount check propagation;
  - mode-specific metadata decorators;
  - available action decisions.
- Moving the full row mutation helper in one slice would be too broad.
- `_pair_relation_display_payload(...)` is a narrow policy boundary:
  - no-OA display delegation;
  - internal transfer label;
  - salary tag label lookup;
  - personal advance repayment label;
  - turnover closure label;
  - OA invoice offset row-type specific label;
  - default fully-linked payload.

## Decision

Select `server-py:workbench-pair-relation-display-policy-extraction`.

## Deferred

- `_apply_pair_relation_to_row(...)` row mutation remains deferred.
- Mode-specific metadata mutation remains deferred.
- Production browser/admin/write evidence remains deferred.

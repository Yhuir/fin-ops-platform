# server-py:workbench-oa-attachment-repair-context-audit

Date: 2026-06-25
Status: analysis-closed

## Scope

Audited `_repair_active_relations_with_oa_attachment_context(...)` after OA invoice offset sync executor extraction.

## Findings

- The function is side-effecting orchestration, not HTTP handling:
  - raw payload row indexing;
  - OA attachment context row grouping;
  - active relation reads through `WorkbenchOaAttachmentRepairRelationReadPort`;
  - dedicated-withdraw skip;
  - missing attachment row detection;
  - repaired row id/type construction;
  - amount check calculation;
  - command-service `confirm_relation` with `replace_existing=True` and `before_relations`;
  - changed case/scope collection;
  - pair relation persistence;
  - derived lifecycle emission.
- The logic can be moved behind explicit ports without direct `Application`, HTTP, repository, read-model gateway or auth dependencies.
- Local proof must cover no-op cases, a repaired relation, dedicated-withdraw skip, command-service payload shape, persistence and lifecycle emission.

## Decision

Select `server-py:workbench-oa-attachment-repair-context-executor-extraction`.

## Deferred

- Lower-level OA attachment context row-id grouping helpers remain as compatibility helpers for a later narrow extraction.
- Production browser/admin/write evidence remains deferred.

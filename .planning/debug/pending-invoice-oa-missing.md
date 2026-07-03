---
status: resolved
trigger: "待找发票页面 145 行已有关联发票和关联台配对，但 OA 列为空"
created: 2026-07-03
updated: 2026-07-03
---

# Current Focus

- hypothesis: `workbench_relation` distribution 生成 `linked_oa` 时未读到 OA source object，而不是待找发票 UI 丢字段。
- test: 用 legacy completed workflow status 构造 relation projection，验证银行行是否生成 `linked_oa`。
- expecting: 完成态别名进入 OA projection 边界后，relation distribution 输出 OA summary，pending invoice 继续只消费 distribution。
- next_action: resolved

# Evidence

- timestamp: 2026-07-03
  observation: `SearchPendingSqlProjectionBuilder` 只通过 `WorkbenchRelationReadFacade.get_by_row_ids(..., require_fresh=True)` 读取 `linked_oa`，不拥有 relation facts。
- timestamp: 2026-07-03
  observation: `WorkbenchRelationSqlProjectionBuilder._linked_summaries(...)` 只会输出 `_summaries_by_id` 中存在的 OA summary；canonical relation 有 OA row id 但 `app.oa_applications` predicate 查不到时，下游 OA 列为空。
- timestamp: 2026-07-03
  observation: 旧 `COMPLETED_WORKFLOW_STATUS_SQL` 只接受空值或 `completed`，历史 OA projection 可能保留 `已完成`、`approved`、`2` 等完成态别名。

# Resolution

- root_cause: OA 完成态 I/O 边界过窄，导致 relation distribution 的 OA source object lookup 丢失历史完成态 OA rows。
- fix: 完成态别名集中到 OA projection 边界，bump `OA_PROJECTION_SYNC_VERSION=2026-07-03-completed-workflow-status-aliases-v1` 触发 relation/pending read model 重建；不在待找发票添加 fallback 推断。
- verification: `tests/test_workbench_relation_sql_projection.py::WorkbenchRelationSqlProjectionTests::test_rebuild_keeps_oa_summary_for_legacy_completed_workflow_status` and `tests/test_oa_projection_sync_service.py::OaProjectionSyncServiceTests::test_oa_sync_treats_legacy_completed_workflow_aliases_as_completed`.
- files_changed: `backend/src/fin_ops_platform/services/postgres_repositories/oa_projection.py`, `backend/src/fin_ops_platform/services/oa_projection_sync.py`, relation/pending/OA docs and tests.

# 免OA流水批量处理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 免 OA 流水批量处理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、application/service、API contract、read model/worker、前端交互、Workbench integration 和旧功能回归。
- 本模块是 Bankdetail 高风险子域。后续不要把 no-OA 机械拆成脱离 Bankdetail 的独立事实源。
- `GET /api/no-oa-bank-batches` 和 detail 读路径不得在 missing/stale 时同步重建全量批次；必须返回 read model status 并 enqueue refresh。
- PostgreSQL list 读路径允许返回 fresh empty rows，但必须由 `job.read_model_dirty_scopes` 无 active blocker 且 `read_model.app_status_readiness` 记录为 fresh 共同证明；不能把无 rows 直接当 fresh。
- Workbench confirm-link 的 internal transfer 特例必须最终写 no-OA submitted batch 和 `relation_mode=no_oa_bank_batch`，不得绕过批次写普通 `manual_confirmed`。
- no-OA legacy migration、submitted repair、category drift cleanup 和 submitted single-side consolidation 必须通过 `WorkbenchRelationCommandService` 写 relation；缺 command service 时 fail fast，不回退 direct pair mutation。
- no-OA submit/withdraw 的长期目标是 facts/audit/dirty/outbox 同事务；当前目标契约由 `tests/test_bankdetail_write_uow_contract.py` 保护，真实收敛前保持 `documented-risk`。
- 前端 stale polling、route unmount cleanup、category/rules events 刷新 list/detail/tag drawer 都是页面行为契约。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `no-oa-bank-batches` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：免 OA 页面、tag-selection、list/detail、submit-selection、batch submit、bulk submit、withdraw、internal transfer from Workbench、no-OA read model、no-oa-bank-batch worker、App Status、Bankdetail tag/rule events。
- CodeGraph 审计：
  - `NoOaBankBatchPage` 调用 `fetchNoOaBankBatches`、`fetchNoOaBankBatchDetail`、`fetchNoOaBankBatchTagSelection`、`saveNoOaBankBatchTagSelection`、`submitNoOaBankBatchSelection`、`submitNoOaBankBatch`、`withdrawNoOaBankBatch`，并在 read model 非 fresh 时后台轮询。
  - `NoOaBankBatchApiRoutes` 是 HTTP route facade，负责 payload/session 映射和 error status；业务落在 `NoOaBankBatchApplicationService`。
  - `NoOaBankBatchApplicationService` 覆盖 list read model fallback、tag selection、submit/withdraw、after_mutation、durable queue enqueue 和 Workbench 影响。
  - `NoOaBankBatchService` 覆盖 draft/submitted/withdrawn/stale/conflict、internal transfer、legacy relation migration、pair relation metadata 和 snapshot/audit。
  - `NoOaBankBatchReadModelRefreshService` 只处理 `no_oa_bank_batch.read_model.refresh`，stale source version event 会 skip。
  - worker registry 和 App Status registry 已登记 `no-oa-bank-batch` worker、`no_oa_bank_batch` read model 和 `no_oa_bank_batch.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_no_oa_bank_batch_service.py`。
  - Application/service：`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py`。
  - API/route：`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py`。
  - Read model/worker：`tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`。
  - Frontend：`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、domain event tests。
  - Integration/regression：`tests/test_no_oa_bank_batch_workbench_integration.py` 覆盖 Workbench internal transfer、manual relation 分流、mixed conflict、submitted/withdraw/open 恢复。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 大数据月份、长标签树、长银行流水列表的浏览器性能和视觉遮挡。
  - Bankdetail/no-OA 写 UoW 真实事务内收敛尚未完全由本地 fixture 证明。
- 后续事项：
  - 修改 submit/withdraw 前，优先补 service/UoW/API characterization test。
  - 修改 read model freshness 前，必须运行 no-OA read model integration 和 worker refresh tests。
  - 修改前端 stale polling、route activation 或 domain event 时，必须运行 no-OA page tests 和 `useActiveFinanceDomainEvent` tests。

## 2026-06-11 - 内部往来双入口闭环

- 目标：修复同一组内部往来在免 OA 页面和关联台两个入口之间可能出现重复 active relation、旧未提交/冲突批次残留、历史 `manual_confirmed` 占用后不进入免 OA 已提交区域的问题。
- 决策：
  - 关联台仍允许作为内部往来提交入口，但成功事实必须委托并收敛到 no-OA submitted batch。
  - 如果免 OA 页面已经提交同一组 `row_ids`，关联台再次 confirm-link 复用 existing submitted batch 和同一个 `case_id`，保持幂等。
  - 存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，刷新时迁移为 submitted no-OA internal transfer batch。
  - Workbench pair relation service 增加 active row 独占保护，不同 active case 不能共享同一 row。
  - PostgreSQL no-OA snapshot 保存必须删除新 snapshot 中缺席的旧 batch row，防止 SQL read model 继续返回旧 unsubmitted/conflict。
- 验收测试：
  - `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch`
  - `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`
  - `test_create_active_relation_rejects_active_row_reuse_by_different_case_id`
  - `test_save_no_oa_bank_batches_replaces_absent_read_model_rows`

## 2026-06-12 - Relation command service 写入口收敛

- 目标：把 no-OA submit、submit-selection、Workbench internal transfer submit 和 withdraw 的 relation 写入收敛到 `WorkbenchRelationCommandService`，避免 no-OA 页面和 Workbench 形成独立事实源。
- 决策：
  - `NoOaBankBatchService` 保留为批次领域状态机，只产出 `relation_command_payload_for_batch(...)`，不再直接调用 `create_active_relation` 或 `cancel_relation`。
  - `NoOaBankBatchApplicationService` 负责调用 relation command service，并在失败时回滚 no-OA batch snapshot 与 relation snapshot。
  - relation 占用和写入使用 canonical relation command/write safety；`submit_selected_rows` 不再读取 pair service list。
  - relation distribution/read model non-fresh 不阻断 batch submit；提交后继续刷新 no-OA、Workbench 和 downstream read model。
  - no-OA legacy migration、submitted repair、category drift cleanup 后续已在 Phase 7L 迁入 relation command service。
- 验收测试：
  - `test_submit_batch_delegates_relation_write_to_command_service`
  - `test_withdraw_batch_delegates_relation_cancel_to_command_service`
  - `test_internal_transfer_from_workbench_delegates_relation_write_to_command_service`
  - `test_submit_batch_marks_submitted_and_exposes_relation_command_payload_idempotently`
  - `test_submit_uses_canonical_relation_when_relation_read_model_is_not_fresh`
  - `test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open`
  - `test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled`

## 2026-06-12 - Read model refresh 不再隐式修复 relation

- 目标：把 `no_oa_bank_batch.read_model.refresh` 从 relation 写入口中剥离，避免 worker 在重建 no-OA projection 时顺手创建/取消 pair relation，形成隐藏事实源写入。
- 决策：
  - `NoOaBankBatchService.build_batches(...)` 增加 `apply_relation_repairs` 参数；默认保持 legacy 兼容行为。
  - `NoOaBankBatchApplicationService.refresh_batches(...)` 暴露同名参数，并且只有启用 repair 时才根据 `last_legacy_migration_result` 触发 relation/workbench persist。
  - `NoOaBankBatchReadModelRefreshService` 固定调用 `refresh_batches(apply_relation_repairs=False)`；worker 只保存 no-OA snapshot，不保存 pair relation，不执行 legacy migration/repair/consolidation。
  - legacy migration、submitted repair、category drift cleanup 仍是待迁移兼容路径，后续应收敛为显式 repair command/离线 repair 工具。
- 验收测试：
  - `test_refresh_does_not_repair_workbench_relations_from_read_model_path`
  - `test_no_oa_read_model_refresh_does_not_run_relation_repairs`

## 2026-06-12 - Legacy relation repair 写入口收敛

- 目标：把 no-OA legacy relation migration、submitted relation repair、category drift cleanup 和 submitted single-side consolidation 从 direct pair service mutation 收敛到 `WorkbenchRelationCommandService`。
- 决策：
  - `NoOaLegacyRelationMigrationService` 通过 command service cancel legacy relation，再 confirm `relation_mode=no_oa_bank_batch`；缺 command service 时抛 `no_oa_relation_command_unavailable`。
  - `NoOaBankBatchService` 的 legacy/repair/consolidation 路径通过 `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` 委托 command service，不再调用 `_pair_relation_service.create_active_relation/cancel_relation/record_history`。
  - `Application` 为 no-OA batch service 注入 `WorkbenchRelationCommandService(require_fresh_relations=False)`，使显式 repair 路径复用统一 command/history/snapshot 边界，同时避免 read model worker 隐式 repair。
  - 已有 current submitted no-OA batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 `relation_case_id`，避免新建 legacy batch case 后与旧 submitted batch 形成两个 active relation。
  - submitted repair 遇到 row 已被非 no-OA active relation 占用时跳过重建 no-OA relation，保留 active row 独占事实，并在 migration result 的 `skipped` 中记录 blocking case。
- 验收测试：
  - `test_submitted_internal_transfer_with_active_non_no_oa_relation_does_not_duplicate_as_unsubmitted_conflict`
  - `test_legacy_salary_relation_migrates_to_submitted_no_oa_batch_idempotently`
  - `test_existing_submitted_single_row_salary_batches_consolidate_by_month_and_account`
  - `test_consolidated_submitted_salary_batch_repairs_stale_single_row_relations`
  - `test_submitted_single_side_batch_prunes_rows_that_no_longer_match_category`
  - `test_submitted_batch_that_becomes_stale_clears_active_relation`
  - `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback`
- 验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py -q
```

- 七类测试覆盖：
  - Business core unit tests：适用并覆盖 legacy migration、submitted repair、category drift、single-side consolidation、active row occupation 和同 row set case reuse。
  - Service-layer tests：适用并覆盖 no-OA service 到 relation command service 的委托、缺 command fail-fast 和 read model worker 不隐式 repair。
  - API contract tests：本阶段未改 HTTP response shape；通过 no-OA API 回归保护旧 contract。
  - Read model/cache/background job tests：适用并继续覆盖 worker refresh 不写 relation。
  - Frontend component and interaction tests：本阶段未改前端，未新增。
  - End-to-end business-flow integration tests：适用并通过 no-OA workbench integration 回归保护 no-OA/Workbench 同一 relation fact。
  - Existing feature regression tests：适用并保留 legacy salary/internal transfer、stale/category drift、snapshot round-trip 和 API 回归。
- 剩余风险：
  - 真实 PostgreSQL 历史数据的全量回放和 repair dry-run 仍需 staging/生产前 smoke。
  - relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
  - 前端跨页面即时反馈仍需完整浏览器 smoke；domain event 仍只是刷新提示，不是事实源。

## 2026-06-13 - fresh empty rows readiness 证明

- 目标：修复当前月份没有免 OA 候选时 API 持续返回 missing/refresh_enqueued，导致页面一直“同步中”或 authenticated HTTP SLO freshness gate 失败。
- 影响范围：`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`、no-OA list API 读取语义、HTTP SLO 默认 no-OA 探针。
- 关键决策：list 查询无 rows 时，只有 dirty scope 已 fresh 且 `read_model.app_status_readiness` 对 `no_oa_bank_batch/all` 为 fresh，才返回 `[]`；否则保持 `None`，让上层继续返回 refreshing 并入队真实刷新。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_repository_returns_fresh_empty_rows_when_readiness_is_fresh`、`test_no_oa_repository_keeps_missing_when_readiness_is_absent_or_refreshing`。
- 验证命令：见最终交付说明。
- 未测风险：需要发布后用真实生产 readiness 行验证当前月份 empty state 不再被误判为 missing。
- 后续事项：若后续把 no-OA scope 从 `all` 拆到月份维度，必须同步更新 readiness 证明条件和测试。

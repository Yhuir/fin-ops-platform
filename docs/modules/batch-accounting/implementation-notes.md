# 批量账务 实施记录

## 2026-06-14 - 撤回历史显示归属过滤

- 目标：批量账务撤回复用 Workbench relation history 时，不再把 OA 附件 case_id / `existing_case` 显示归属恢复成 active relation。
- 影响范围：`WorkbenchPairRelationService` 的可恢复 relation snapshot 边界、`BatchAccountingService.withdraw` 回归断言和本模块文档。
- 关键决策：读侧仍可按 case_id 展示 OA 与附件发票的归属关系；写侧撤回只恢复真实 active relation snapshot，display-only 归属不进入 relation repository。
- 测试覆盖：更新 `tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_withdraw_does_not_restore_display_only_oa_invoice_snapshot_as_active_relation`。
- 发布前审计：2026-06-14 已在生产执行只读 SQL 审计，`active_display_only_relation_count=0`、`display_only_history_before_relation_count=3`、`affected_history_case_count=3`；历史污染由运行时过滤覆盖，不需要 backfill。
- 未测风险：未执行生产写入型 repair；本次审计结论为无需写入型 backfill。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 批量账务不拥有独立 read model；列表和 mutation 前置判断依赖 `workbench_relation` read model freshness。
- `GET /api/batch-accounting` 必须保持只读，不能为了修复历史关系在 GET 路径写入。
- `read_model_status !== "fresh"` 时前端必须显示 warning，不能把空关系当作真实未提交；写操作是否可提交由后端 canonical write safety、权限/session、DB 和 owner/version/idempotency 判定，普通 relation distribution 追赶中不应作为长期全局禁用理由。
- 批量账务 submit relation 写入必须通过 `WorkbenchRelationCommandService.confirm_relation(...)`；缺少 command service 时 fail fast，不回退 direct `WorkbenchPairRelationService.replace_with_confirmed_relation(...)`。
- 提交/撤回成功后的前端 `workbenchRelationUpdated` 只是刷新提示，不替代后端 dirty scope、worker、operation barrier 和 readiness。页面释放全屏操作 overlay 前必须等 `workbench_relation` barrier fresh 并重新加载。
- 历史 case id collision 修复保留在 service 显式路径和 mutation/repair 语义中，不能重新散落到列表读取。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-14 - submit/withdraw 操作后 freshness barrier

- 目标：批量账务提交/撤回后隐藏短暂 read model 收敛时间，避免用户在 relation distribution 未 fresh 时看到旧 bucket 或继续重复操作。
- 影响范围：`BatchAccountingPage` submit/withdraw、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功不是页面可继续操作的完成点；前端等待 `workbench_relation` barrier 对 affected months fresh，再 reload 当前 payload 并关闭 overlay。前端事件仍只作为刷新提示，不是同步事实。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/BatchAccountingPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

## 2026-06-12 - legacy repair relation command fallback 删除

- 目标：删除 `BatchAccountingService.repair_legacy_case_id_collisions` 直接调用 `WorkbenchPairRelationService.create_active_relation/record_history` 的历史修复写入口。
- 影响范围：`BatchAccountingService.repair_legacy_case_id_collisions`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：repair 仅在确实需要恢复 relation 时要求 `WorkbenchRelationCommandService`；缺 command service 代表 wiring 错误，应返回 `batch_accounting_relation_command_unavailable`。恢复 relation 使用 `confirm_relation(..., history_operation_type="repair_batch_accounting_relation_id_collision")`，保留 legacy case id、repair source、repaired_at 和 amount metadata。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 `test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service`、`test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback` 和 `test_batch_accounting_repair_has_no_direct_pair_write_fallback`；完整 batch accounting API/service 回归通过。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py -q`。
- 未测风险：真实 PostgreSQL 历史数据中 legacy relation / 半迁移 / 重复 case id 的全量回放仍需 staging 或生产前 dry-run。
- 后续事项：继续收口 no-OA legacy repair/consolidation。

## 2026-06-12 - submit relation command fallback 删除

- 目标：删除 `BatchAccountingService.submit` 在缺少 relation command service 时的 direct pair relation fallback，避免批量账务提交绕过统一 relation 事实源。
- 影响范围：`BatchAccountingService._submit_unlocked`、`tests/test_batch_accounting_api.py`、`tests/test_platform_runtime_boundary_guards.py` 和本模块文档。
- 关键决策：生产 `Application._batch_accounting_service()` 已注入 `WorkbenchRelationCommandService`；缺少 command service 代表 wiring 错误，应返回 `batch_accounting_relation_command_unavailable`，不能调用 `replace_with_confirmed_relation(...)`。legacy collision repair 后续已在同日迁移到 command service。
- 文档影响：更新 `README.md`、`tests.md`、`implementation-notes.md`，并同步 `workbench-relations` 模块。
- 测试覆盖：新增 `test_submit_requires_relation_command_service_without_direct_pair_fallback`；新增 runtime boundary guard 防止 `_submit_unlocked` 重新出现 direct pair write fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_delegates_relation_write_to_command_service tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_requires_relation_command_service_without_direct_pair_fallback tests/test_batch_accounting_api.py::BatchAccountingApiTests::test_submit_amount_mismatch_with_note_persists_relation_and_history -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_batch_accounting_submit_has_no_direct_pair_write_fallback -q`。
- 未测风险：本阶段不迁移 `repair_legacy_case_id_collisions`；该路径后续已在同日迁移到 command service。
- 后续事项：继续收口 no-OA legacy repair/consolidation。

## 2026-06-11 - relation read model missing/stale 闭环

- 目标：修复批量账务页面出现 `关联台关系读模型 missing/read_model_missing` 时只能提示刷新、但列表读取和 mutation fresh gate 没有形成完整闭环的问题。
- 影响范围：`BatchAccountingService` relation facade 调用、`GET /api/batch-accounting` freshness payload、submit/withdraw 错误合同、`BatchAccountingPage` non-fresh warning 和 feedback。
- 关键决策：GET 列表保持只读，但所有 relation distribution 读取都通过现有 `WorkbenchRelationReadFacade` 的 `require_fresh` 边界入队刷新；submit/withdraw 在后端再次要求 relation read model fresh，非 fresh 返回 `batch_accounting_read_model_not_fresh`；前端只展示后端 status/reason/scope，不把 domain event 当事实源。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增/更新后端 API/service 测试覆盖 missing/stale 入队、submit/withdraw fresh gate；新增前端交互测试覆盖刷新未入队提示和 mutation non-fresh reason/scope feedback。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx -t "relation read model refresh is not enqueued|mutation is rejected as non-fresh"`
- 未测风险：真实 PostgreSQL/RabbitMQ/systemd worker drain 和生产历史 dirty scope 收敛仍需 staging 或发布前 smoke；单元测试验证的是 facade/gateway 调用合同和页面行为。
- 后续事项：最终合入前继续运行模块全量后端、前端和 docs verify。

## 2026-06-11 - 首轮测试闭环文档化

- 目标：用 CodeGraph 审计批量账务页面、API、service、relation read model、worker/App Status 和测试入口，补齐模块文档闭环。
- 影响范围：`BatchAccountingPage`、`batchAccounting/api.ts`、`BatchAccountingService`、`WorkbenchRelationReadFacade`、`WorkbenchRelationSqlProjectionBuilder`、`workbench-relation` worker、App Status domain/job 映射、domain event。
- 关键决策：批量账务 mutation 必须依赖 fresh relation read model；GET 保持只读；前端事件不作为事实源；历史 collision repair 通过显式 service 回归保护。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`，并在全局测试闭环依赖地图中补充 batch-accounting 细化。
- 测试覆盖：后端 `tests/test_batch_accounting_api.py` 覆盖业务/API/service 回归；relation facade/projection/registry/App Status/lifecycle tests 覆盖 read model 和 worker；前端 `BatchAccountingPage.test.tsx` 覆盖页面交互和 stale 禁用。
- 验证命令：
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api tests.test_workbench_relation_read_facade tests.test_workbench_relation_sql_projection tests.test_runtime_worker_registry tests.test_app_status_overview_service tests.test_derived_data_lifecycle_service -v`
  - `cd web && npm test -- --run src/test/BatchAccountingPage.test.tsx src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx`
  - `bash scripts/verify.sh docs`
- 未测风险：真实生产 PostgreSQL 历史批量账务关系、真实 RabbitMQ/Redis/systemd `workbench-relation` worker drain、大数据浏览器性能和下游页面最终展示仍需 staging/发布前 smoke。
- 后续事项：后续改动若触及 relation freshness、DTO shape、提交/撤回规则或 Workbench relation fan-out，必须先按 `tests.md` 选择窄范围回归，再升级到跨模块验证。

# 外部往来款管理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口、回归范围和未测风险。实现后按实际影响更新矩阵。

## 影响面清单

外部往来款不是孤立页面。修改时必须先确认影响面：

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/TurnoverLedgerPage.tsx`、`web/src/features/turnoverLedger/api.ts` | grouped table、标签抽屉、补充信息 drawer、人工闭环 drawer、导出 dialog、loading/empty/error/stale、权限禁用 |
| Operation overlay | `GlobalOperationOverlayProvider`、`web/src/features/operationBarrier/api.ts` | tag-selection、extra、confirm、withdraw 成功后等待 `turnover_ledger` barrier fresh，再 reload grouped payload；失败不假装同步 |
| API contract | `backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_turnover_ledger.py`、`docs/dev/api-contracts.md` | `GET /api/turnover-ledger`、tag-selection、bank-row-tags batch、extra、confirm、withdraw、export-preview/export |
| Business core | `TurnoverRelationService`、`TurnoverLedgerService`、`TurnoverLedgerExtraService` | 外部往来标签准入、同组一收一支、零差额、同对方、同语义、人工闭环、撤回、extra 校验、内部转账排除 |
| Write UoW | `TurnoverLedgerWriteFacade`、`TurnoverLedgerWriteUnitOfWork`、`turnover_ledger_write_adapters.py` | stale precondition、idempotency、relation/extra/settings/bankdetail 写入、dirty/outbox 同事务、rollback、Workbench relation command service 委托 |
| Read model / worker | `TurnoverLedgerQueryService`、`TurnoverLedgerSqlProjectionBuilder`、`TurnoverLedgerReadModelRefreshService` | fresh/stale/missing/refreshing、source versions、group breakdown、worker complete dirty scope |
| 跨页面影响 | Workbench pair relation、Bank Details、Cost Statistics、Search、App Status | 手动闭环进入 Workbench active pair relation；撤回/分类变化后下游不能读旧 relation；App Status 不能误判 green |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | `turnoverRelationUpdated`、`workbenchRelationUpdated`、`turnoverLedgerExtraUpdated` 只触发刷新提示，不替代后端 dirty/outbox |

## 现有测试入口

后端核心测试：

- `tests/test_turnover_relation_service.py`
- `tests/test_turnover_ledger_service.py`
- `tests/test_turnover_ledger_extra_service.py`
- `tests/test_turnover_ledger_source_versions.py`
- `tests/test_turnover_ledger_export_service.py`

后端 API / UoW / read model / worker：

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_facade.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `tests/test_turnover_workbench_integration.py`
- `tests/test_workbench_turnover_grouping.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_runtime_worker_registry.py`

前端：

- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/src/test/domainEvents.test.ts`

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_turnover_relation_service.py`、`tests/test_turnover_ledger_service.py`、`tests/test_turnover_ledger_extra_service.py` | 已覆盖四类 family、候选/确定候选、人工闭环、重复/跨对方/非零差额/同方向拒绝、撤回、内部转账排除、extra 字段校验、分组金额和利息。 |
| 2. Service-layer tests | 适用 | `tests/test_turnover_ledger_uow_contract.py`、`tests/test_turnover_ledger_api.py`、`tests/test_turnover_workbench_integration.py` | 已覆盖 UoW transaction、rollback、dirty/outbox、stale precondition、idempotency、settings/extra/bankdetail/relation ports、Workbench relation command service 委托、缺 command fail-fast 和 Workbench pair relation。 |
| 3. API contract tests | 适用 | `tests/test_turnover_ledger_api.py`、`tests/test_turnover_ledger_read_facade.py` | 已覆盖列表/grouped/tag-selection/bank-row-tags/extra/confirm/withdraw/export、权限、错误、版本冲突、idempotency replay/conflict、stale conflict、relation freshness 诊断、HTML response routing error。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_turnover_ledger_query_service.py`、`tests/test_turnover_ledger_read_model_refresh.py`、`tests/test_turnover_ledger_source_versions.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 已覆盖 stale SQL read model 不伪装 fresh、missing required SQL read model 返回 refreshing、legacy fallback、source versions、projection 保存、worker handler、registry/App Status 登记。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/TurnoverLedgerApi.test.ts`、`web/src/test/GlobalOperationOverlayContext.test.tsx`、`web/src/test/OperationBarrierApi.test.ts` | 已覆盖 API mapper、tag drawer 保存、grouped table、manual closure、提交前 fresh/rebind 最新 flow row versions、刷新后所选流水消失时不发 POST、跨组/非零差额禁用、extra drawer、detail missing error、stale 阻断 manual closure、operation overlay、导出、domain event。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py`、`web/src/test/TurnoverLedgerPage.test.tsx` | 已覆盖 deterministic 不进入 Workbench、manual zero-difference closure 写 Workbench pair relation、canonical write safety 不通过时不半写入、legacy relation 不污染 Workbench grouping、前端闭环前重刷台账且闭环后刷新关联台可见性。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_workbench_turnover_grouping.py`、`web/src/test/domainEvents.test.ts` | 已保护旧 grouped shape、legacy flat/read model 兼容、导出字段、Workbench open grouping、Bankdetail tag batch、旧 relation/system relation 拒绝、domain event contract。 |

当前首轮闭环未发现必须立即新增的 P0 测试。已有 turnover 测试覆盖密度高，本轮不为了覆盖率新增低价值测试。

## 场景覆盖清单

| 场景 | 代表测试 |
| --- | --- |
| 外部往来标签准入默认选择和版本冲突 | `test_turnover_ledger_tag_selection_get_put_and_version_conflict` |
| tag-selection queue failure rollback | `test_turnover_ledger_tag_selection_queue_failure_rolls_back_settings_save`、`test_tag_selection_outbox_failure_rolls_back_settings_save_and_audit` |
| grouped read model stale/missing | `test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh`、`test_missing_required_sql_read_model_returns_empty_refreshing_payload_and_enqueues_miss` |
| grouped table 金额和真实 flow rows | `test_grouped_ledger_places_flow_amounts_by_turnover_action_type_and_exposes_breakdowns`、`test_expands_Jia_Xiaohua_with_real_flow_rows_instead_of_allocation_lot_rows` |
| 人工零差额闭环 | `test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation`、`test_closure_request_boundary_returns_workbench_visibility_freshness_targets`、`test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_open`、`test_confirms_a_manual_zero-difference_turnover_closure_from_three_same-group_flow_rows`、`test_turnover_workbench_pair_port_delegates_manual_closure_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure` |
| SQL runtime 银行流水闭环事实源 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure`、`test_sql_turnover_rows_tolerate_early_startup_before_app_settings_service_is_bound` |
| 前端闭环提交前最新版本保护 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload`、`shows grouped read model stale warning and blocks manual closure` |
| 非法闭环拒绝 | `test_confirm_zero_difference_closure_rejects_duplicate_row_ids`、`test_confirm_zero_difference_closure_rejects_cross_counterparty_rows`、`test_confirm_zero_difference_closure_rejects_non_zero_difference`、`test_confirm_zero_difference_closure_rejects_same_direction_pair` |
| stale/idempotency | `test_target_confirm_request_expected_versions_reach_write_command`、`test_target_confirm_idempotency_key_replays_without_duplicate_confirm_or_refresh`、`test_withdraw_stale_precondition_rejects_changed_relation_before_mutation_or_refresh`、`test_manual_closure_uses_canonical_relation_when_workbench_relation_read_model_is_stale` |
| relation extra | `test_relation_extra_get_returns_default_structure_and_put_persists`、`test_target_relation_extra_stale_expected_version_rejects_without_save_or_refresh`、`test_relation_extra_outbox_failure_does_not_return_best_effort_success` |
| Bankdetail tag batch fan-out | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes`、`test_target_turnover_bank_row_tag_batch_queue_failure_rolls_back_category_save` |
| Workbench 回归 | `test_deterministic_turnover_relation_does_not_group_bank_rows_in_workbench`、`test_bank_only_turnover_manual_closure_rows_remain_open_even_when_linked`、`test_manual_pair_relation_occupied_bank_row_is_not_overridden_by_turnover_relation`、`test_turnover_workbench_pair_port_delegates_manual_closure_withdraw_to_relation_command_service`、`test_turnover_workbench_pair_port_requires_relation_command_service_for_manual_closure_withdraw`、`test_turnover_closure_and_withdraw_wiring_use_workbench_relation_command_service` |
| Worker / App Status | `test_worker_handler_rebuilds_scope_and_completes_dirty_scope`、`test_domain_registry_covers_frontend_routes`、`test_required_worker_missing_marks_critical_domain_blocked` |
| 前端 stale 写禁用 | `shows grouped read model stale warning and blocks manual closure` |
| 前端 operation-to-fresh closure | tag-selection、extra、manual closure confirm/withdraw 后保持全屏 overlay；manual closure confirm 提交前等待 `turnover_ledger:all` fresh 并 reload/rebind 最新 flow rows，提交后等待后端 `freshness_targets` 中的 `turnover_ledger`、`workbench_relation`、`workbench` barrier fresh，再 reload grouped payload、发送关联台刷新事件 |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| deterministic 被误当作已闭环并进入 Workbench | `tests/test_turnover_workbench_integration.py`、`tests/test_workbench_turnover_grouping.py` |
| grouped 视图把 allocation lot 当真实流水导出或展示 | `tests/test_turnover_ledger_export_service.py`、`web/src/test/TurnoverLedgerPage.test.tsx` |
| stale read model 下仍允许确认/撤回/extra 写入 | `web/src/test/TurnoverLedgerPage.test.tsx` stale 写禁用测试，后端 stale precondition 测试 |
| manual closure 抽屉缓存旧 row version，POST 使用旧 `expected_versions` 被后端拒绝，导致关联台没有生成配对/open 组 | `refreshes the grouped ledger before manual closure and submits latest bank row versions`、`blocks manual closure when a selected flow disappears after the fresh ledger reload` |
| SQL runtime 下闭环写路径读取 legacy import snapshot，而不是 `bank_detail` SQL read model，导致生产已有流水仍报 `unknown_transaction_id` 或 stale，且 Workbench relation 没有写入 | `test_sql_bank_detail_turnover_rows_keep_legacy_source_ids_for_manual_closure` |
| 写操作成功后 `turnover_ledger` 仍 refreshing 时页面提前可操作或展示旧分组 | `web/src/test/TurnoverLedgerPage.test.tsx` operation overlay 回归、`web/src/test/OperationBarrierApi.test.ts` |
| queue/outbox 失败后 API 返回成功导致 read model 永久旧 | `tests/test_turnover_ledger_uow_contract.py` rollback tests |
| relation extra legacy full snapshot fallback 误吞持久化问题 | `tests/test_turnover_ledger_api.py` dedicated store / no full snapshot fallback tests |
| 外部往来 API 写 Bankdetail facts 后漏刷 Workbench/Turnover | `test_turnover_bank_row_tag_batch_refreshes_all_required_scopes` |
| 银行标签配置损坏为只有 label 的历史定义，旧确认记录缺外部往来 action，导致台账/关联台无法重建关系 | `tests/test_bank_transaction_category_service.py::BankTransactionCategoryServiceTests.test_legacy_category_record_uses_current_external_definition_semantics`、`tests/test_bank_details_sql_runtime.py::BankDetailSqlProjectionBuilderTests.test_rebuild_enriches_legacy_confirmation_from_current_external_tag_definition` |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 银行明细已确认外部往来分类 -> tag-selection 生效 -> grouped ledger 展示。
2. grouped table 选择同组多条真实 flow rows -> 提交前等待台账 fresh 并重绑最新 row versions -> 人工零差额闭环 -> Turnover manual relation + Workbench pair relation -> 关联台 bank-only open -> 前端刷新。
3. bank-only 手动 relation 撤回 -> Turnover read model 和 Workbench relation 恢复；已升级为三栏 paired 时必须从关联台撤回；Workbench relation read model 不 fresh 时必须 fail fast 且不产生 Turnover 半写入。
4. extra 保存 -> relation row 更新 -> `turnoverLedgerExtraUpdated` 只作为局部刷新提示。
5. tag-selection / bank-row-tags / confirm / withdraw / extra 的 outbox 失败必须 rollback 或显式暴露失败。
6. tag-selection / extra / confirm / withdraw -> 全屏 overlay；manual closure 提交前额外执行 `turnover_ledger:all` fresh gate 和 grouped reload/rebind -> 写成功后等待 operation barrier fresh -> reload grouped ledger -> overlay 释放。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史数据上刷新 `turnover_ledger` read model。
- 真实 RabbitMQ/Redis/systemd worker drain。
- 浏览器导出 XLSX 文件打开检查。
- 大数据 grouped table 性能和滚动检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_api tests.test_turnover_ledger_export_service tests.test_turnover_relation_service tests.test_turnover_ledger_extra_service tests.test_workbench_turnover_grouping tests.test_turnover_ledger_source_versions tests.test_turnover_ledger_read_facade tests.test_turnover_ledger_read_model_refresh tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/GlobalOperationOverlayContext.test.tsx src/test/OperationBarrierApi.test.ts src/test/domainEvents.test.ts
```

文档验证：

```bash
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 通过 backend unittest discovery、frontend Vitest 和 frontend build 覆盖本模块。由于 turnover 后端测试数量多，nightly 可以发现大部分 API/UoW/read model/worker 回归；本地开发时仍应优先运行上方目标验证命令，减少反馈时间。

## 未测风险

- 真实生产 PostgreSQL 历史数据中的重复、缺字段、半迁移状态，不能由本地 fixture 完全证明。
- 真实 RabbitMQ/Redis/systemd worker drain、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke。
- 大数据量 grouped table、导出 XLSX 文件和浏览器视觉遮挡需要真实浏览器/样本验证。
- 外部往来写路径仍保留 legacy fallback 分支；常规 manual closure/withdraw 已通过 command service 收敛，未来删除 fallback 前需要单独回归。
- 自动标签规则恢复只证明银行明细 read model 可从当前定义补齐历史确认语义；真实生产仍需刷新对应 `bank_detail`、`turnover_ledger`、`workbench_relation`、`workbench` scopes 后验证 open 区可见。

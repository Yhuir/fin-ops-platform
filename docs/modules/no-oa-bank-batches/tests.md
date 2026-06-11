# 免OA流水批量处理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 影响面 | 当前事实源 | 需要保护的行为 |
| --- | --- | --- |
| 页面和 API client | `web/src/pages/NoOaBankBatchPage.tsx`、`web/src/features/noOaBankBatches/api.ts` | 三栏布局、标签抽屉、提交选择、内部往来提交、撤回 dialog、stale retry、跨账户选择保护 |
| API contract | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`、`docs/dev/api-contracts.md` | list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit 的 response shape、错误码、version、affected months |
| Business core | `NoOaBankBatchService`、`NoOaManagedRulePolicy` | draft/submitted/withdrawn/stale/conflict、内部往来配对、active relation 占用排除、legacy relation migration |
| Application service | `NoOaBankBatchApplicationService` | read model fallback、tag selection、submit/withdraw、after_mutation、derived lifecycle、durable queue enqueue |
| Write contract | `bankdetail_write_uow.py`、`tests/test_bankdetail_write_uow_contract.py` | stale expected version、batch + Workbench pair relation + audit + dirty/outbox 同事务目标 |
| Read model / worker | `NoOaBankBatchReadModelRefreshService`、`runtime_worker_registry.py` | missing/stale 不同步重建、source version 保护、worker complete dirty scope |
| 跨页面影响 | Bank Details、Workbench、Cost Statistics、Search、App Status | no-OA 提交/撤回影响 Workbench relation、银行明细关系状态、成本统计、搜索候选和 App Status |
| 前端跨页事件 | `web/src/features/domainEvents.ts` | submit/withdraw 后发 `workbenchRelationUpdated`；分类/规则更新刷新 no-OA list/detail/tag drawer |

## 现有测试入口

后端核心和服务层：

- `tests/test_no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_application_service.py`
- `tests/test_bankdetail_write_uow_contract.py`
- `tests/test_no_oa_bank_batch_tag_selection_api.py`

后端 API / route / read model / integration：

- `tests/test_no_oa_bank_batch_api.py`
- `tests/test_no_oa_bank_batch_routes.py`
- `tests/test_no_oa_bank_batch_workbench_integration.py`
- `tests/test_no_oa_bank_batch_read_model_refresh.py`
- `tests/test_bank_auto_tag_rules_api.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_app_status_overview_service.py`

前端：

- `web/src/test/NoOaBankBatchApi.test.ts`
- `web/src/test/NoOaBankBatchPage.test.tsx`
- `web/src/test/domainEvents.test.ts`
- `web/src/test/useActiveFinanceDomainEvent.test.tsx`

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 当前结论 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_no_oa_bank_batch_service.py` | 已覆盖 fee/salary/bonus/internal_transfer draft 生成、active relation 排除、stale/superseded、legacy relation migration、submit/withdraw、audit/snapshot。 |
| 2. Service-layer tests | 适用 | `tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py` | 已覆盖 after_mutation persist/non-persist、durable queue enqueue、stale expected version、batch/relation/audit/dirty/outbox 同事务目标和 rollback。 |
| 3. API contract tests | 适用 | `tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py` | 已覆盖 list/detail/tag-selection/submit-selection/submit/withdraw/bulk-submit、409 version conflict、404 unknown、invalid JSON、persistence error、partial results。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 已覆盖 missing SQL read model 不同步重建、stale SQL source versions 不伪装 fresh、detail 不刷新全量、worker stale source version skip、worker registry/App Status 登记。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/NoOaBankBatchPage.test.tsx`、`web/src/test/NoOaBankBatchApi.test.ts` | 已覆盖三栏布局、tag drawer、主/子标签键盘操作、提交选择、跨账户选择保护、内部往来 batch submit、撤回、stale polling、route unmount cleanup、保持 stale rows 可见。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_no_oa_bank_batch_workbench_integration.py` | 已覆盖 Workbench confirm internal transfer 走 no-OA batch、非内部往来保持 manual relation、混合 internal transfer 拒绝、no-OA relation 配对/撤回回到 open。 |
| 7. Existing feature regression tests | 适用 | 上述全部，加 `tests/test_bank_auto_tag_rules_api.py`、domain event tests | 已保护旧 summary/category labels、legacy relation collapsed summaries、Bankdetail tag/rule changes refresh no-OA、前端事件不在 route unmount 后 replay。 |

当前首轮闭环未发现必须立即新增的 P0 测试。已有 no-OA 测试覆盖 business、API、read model、worker、Workbench integration 和前端 stale polling；本轮不为了覆盖率新增低价值测试。

## 场景覆盖清单

| 场景 | 代表测试 |
| --- | --- |
| 标签准入 active tags 和版本冲突 | `test_tag_selection_active_tags_are_bank_auto_rule_tags_only`、`test_tag_selection_version_conflict_returns_409_and_error_code` |
| 新标签默认不自动选中 | `test_new_auto_tag_rule_is_available_but_not_selected_by_default` |
| archived selected tag 被规则更新移除 | `test_archived_selected_tag_is_removed_by_auto_tag_rule_update` |
| 未提交候选由 tag selection 控制 | `test_tag_selection_starts_empty_and_controls_unsubmitted_candidates` |
| submit-selection 只提交当前选择 | `test_selected_row_submit_creates_one_batch_for_same_bank_subset`、前端 `submits only the selected transaction rows and dispatches affected months` |
| 跨银行/单边 internal transfer 拒绝 | `test_selected_row_submit_rejects_cross_bank_selection`、`test_selected_row_submit_rejects_single_sided_internal_transfer_selection` |
| internal transfer 从 Workbench 进入 no-OA | `test_workbench_confirm_internal_transfer_bank_rows_submits_no_oa_batch` |
| mixed internal transfer 拒绝普通 manual relation | `test_workbench_confirm_mixed_internal_transfer_bank_rows_rejects_no_oa_conflict` |
| submitted/withdraw relation 生命周期 | `test_submit_persists_batch_and_pair_relation_and_invalidates_workbench`、`test_withdraw_cancels_pair_relation_and_persists_snapshot` |
| active relation 占用排除 unsubmitted | `test_unsubmitted_list_excludes_internal_transfer_rows_occupied_by_active_relation` |
| stale/category drift | `test_stale_batch_after_category_drift_clears_relation_and_is_not_withdrawable` |
| read model stale/missing | `test_no_oa_bank_batches_do_not_return_stale_sql_source_versions_as_fresh`、`test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path` |
| worker stale source version | `test_stale_source_version_does_not_rebuild_or_overwrite_read_model` |
| 前端 stale polling | `shows read model stale state and reloads until the no OA read model is fresh`、`cleans up stale read model retry reload after route unmount` |
| 前端分类/规则事件刷新 | `refreshes tag selection, list, and detail cache after bank transaction category updates`、`refreshes tag selection, list, and detail cache after bank auto tag rules update` |

## 历史 bug 回归库

| 风险/历史问题 | 当前保护 |
| --- | --- |
| GET list/detail 在 read model missing 时同步 rebuild，拖慢热路径或伪造 fresh | `tests/test_no_oa_bank_batch_workbench_integration.py` read model tests |
| internal transfer 从 Workbench confirm-link 直接写 `manual_confirmed` | `test_workbench_confirm_internal_transfer_bank_rows_submits_no_oa_batch` |
| 混合 internal transfer 和非 internal transfer 被静默普通确认 | `test_workbench_confirm_mixed_internal_transfer_bank_rows_rejects_no_oa_conflict` |
| submitted no-OA relation 被未提交候选重复出现 | `test_unsubmitted_list_excludes_internal_transfer_rows_occupied_by_active_relation`、service active relation tests |
| 标签规则变更后 no-OA 标签选择或候选未刷新 | `tests/test_bank_auto_tag_rules_api.py`、前端 category/rules event tests |
| route unmount 后 stale polling 继续 replay | `web/src/test/NoOaBankBatchPage.test.tsx` route unmount cleanup test |

新增线上或手工发现 bug 时，必须先在本节补复现测试名称，再修实现。

## 关键 Smoke Flow

本地自动化重点保护：

1. 保存免 OA 标签准入 -> 未提交候选按 selected codes 出现。
2. 选择同月、同账户、同 category code 的流水 -> `submit-selection` 生成一个 submitted batch -> Workbench relation refresh。
3. Workbench 选择两条 internal_transfer 银行流水 -> confirm-link 委托 no-OA batch submit -> Workbench active pair relation 使用 `relation_mode=no_oa_bank_batch`。
4. submitted batch 撤回 -> pair relation cancel -> 流水回到未配对/open。
5. SQL read model stale/missing -> API 返回当前/空 payload + refresh enqueued，不同步 rebuild，不伪装 fresh。

真实环境 smoke 仍需在发布前执行：

- 真实 PostgreSQL 历史 no-OA 批次和 Workbench relation migration 回放。
- 真实 RabbitMQ/Redis/systemd no-oa-bank-batch worker drain。
- 大数据月份列表、标签规则更新后的 stale polling。
- 浏览器三栏布局和长列表滚动检查。

## 模块验证命令

后端目标验证：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_service tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_api tests.test_no_oa_bank_batch_routes tests.test_no_oa_bank_batch_tag_selection_api tests.test_no_oa_bank_batch_workbench_integration tests.test_no_oa_bank_batch_read_model_refresh tests.test_bankdetail_write_uow_contract tests.test_bank_auto_tag_rules_api tests.test_runtime_worker_registry tests.test_app_status_overview_service -v
```

前端目标验证：

```bash
cd web && npm test -- --run src/test/NoOaBankBatchApi.test.ts src/test/NoOaBankBatchPage.test.tsx src/test/domainEvents.test.ts src/test/useActiveFinanceDomainEvent.test.tsx
```

文档验证：

```bash
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 通过 backend unittest discovery、frontend Vitest 和 frontend build 覆盖本模块。no-OA 后端和前端目标测试均会进入 nightly；本地开发时优先运行上方目标命令。

## 未测风险

- 真实生产 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放不能由本地 fixture 完全证明。
- 真实 RabbitMQ/Redis/systemd no-oa-bank-batch worker drain、网络抖动和 worker 重启恢复需要 staging 或生产前 smoke。
- 大数据月份、长标签树、长银行流水列表的浏览器性能和视觉遮挡需要真实浏览器验证。
- Bankdetail/no-OA 写 UoW 仍有目标契约测试；真正事务内 facts/audit/dirty/outbox 收敛完成前保持 `documented-risk`。

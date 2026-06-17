# 银行明细测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

银行明细不是单纯列表页。它同时维护银行流水展示、自动标签、人工分类入口、关系标签投影、账户余额 read model 和多个下游页面的刷新信号。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 银行流水原始字段 | import normalized payload、`BankDetailsService`、`BankDetailSqlProjectionBuilder` | 各银行 purpose/summary/note/detail 字段不能互相兜底污染；导出字段必须保留可追溯原文。 |
| 自动标签规则 | `AppSettingsService`、`BankTransactionCategoryService`、`BankTransactionAutoCategoryService` | 系统规则 `internal_transfer` 固定 priority 1；普通规则 priority/sort_order、版本、归档、文件替换、field errors。 |
| 候选确认 | `/api/bank-details/transactions/{id}/category-confirmation` | 只能确认当前规则生成的 `needs_confirmation` 候选；外部往来同 code 多第三层时必须校验第三层标签。 |
| 人工补分类 | `/api/bank-details/transactions/{id}/category-assignment` | 只允许 `unmatched` 行；不能覆盖 `auto_matched`、`needs_confirmation`、`internal_transfer`。 |
| 银行明细 read model | `read_model.bank_detail_rows/scopes`、`bank_detail.read_model.refresh` | stale/schema mismatch/missing/refreshing 不能被伪装成 fresh；规则版本变化要判 stale。 |
| 账户余额 read model | `read_model.bank_account_balances`、`bank_account_balance.read_model.refresh` | 余额来自独立 read model；日期/关键字/分类筛选和标签规则变化不能覆盖 fresh balance。 |
| 关系标签投影 | `BankDetailsRelationTagProjectionService`、workbench relation distribution | 关联台确认/撤回、OA-only、invoice-only、OA+invoice relation tag 要在银行明细行刷新。 |
| 下游 fan-out | turnover ledger、no-OA batch、pending invoices/search、cost/tax、App Health | 标签/分类/导入/关系变更必须通过 lifecycle/dirty scope/outbox 刷新下游，不能只靠前端事件。 |
| 前端交互 | `BankDetailsPage`、`web/src/features/bankDetails/api.ts` | loading/empty/error/stale/refreshing、drawer、filter、pagination、export、权限、domain event refetch。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 银行流水 identity/dedup | P0 | `tests/test_bank_transaction_identity_service.py` | covered | 相同业务字段稳定去重；serial 相同但业务字段不同不能误判。 |
| 自动标签规则解析和执行 | P0 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_service.py` | covered | 关键词、方向、组合条件、regex、priority、外部往来候选、内部往来优先。 |
| 自动标签规则 API GET/PUT/file replacement/reapply | P0 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_app_settings_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_restore_bank_auto_tag_rules_tool.py` | covered | 权限、版本冲突、字段错误、审计、规则重应用、队列不可用 503；`/api/workbench/settings` 不能绕过本入口写 `bank_transaction_tags`；文件恢复必须复用损坏历史 custom code 和 `external_turnover` code；生产恢复工具默认 dry-run，写入必须显式确认并走银行明细 application service。 |
| 候选确认防伪造 | P0 | `tests/test_bank_auto_tag_rules_api.py` | covered | 非当前候选、非自动规则、单一 auto match、unmatched 行均拒绝。 |
| 外部往来第三层候选和人工补分类 | P0 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetailsPage.test.tsx` | covered | 候选确认和人工补分类均覆盖第三层标签、动作语义和前端选择。 |
| 人工补分类只允许 unmatched | P0 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_transaction_category_service.py` | covered | 禁止绕过自动候选或覆盖确定性自动结果。 |
| 分类/规则写入事务和 outbox | P0 | `tests/test_bankdetail_write_uow_contract.py`、`tests/test_bank_details_sql_runtime.py` | covered | 版本冲突、rollback、dirty/outbox、turnover/no-OA fan-out。 |
| 银行明细 SQL read model freshness | P0 | `tests/test_bank_details_sql_runtime.py` | covered | missing、fresh empty、schema mismatch、dirty scope refreshing、规则版本 stale、cache key。 |
| 下游标签读取 facade | P0 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests` | covered | fresh bank_detail 给 turnover/no-OA 等下游发布标签事实时必须保留 `category_version`、`manual_category_version`、`version`，否则下游 fresh read model 会携带旧 expected version。 |
| read model refresh worker | P0 | `tests/test_bank_details_sql_runtime.py` | covered | `all` fan-out 到月份 shard；月份 scope rebuild 后按 source version complete。 |
| 账户余额独立 read model | P0 | `tests/test_bank_account_balance_read_model.py`、`web/src/test/BankDetailsPage.test.tsx` | covered | latest balance、CNY 别名、日期筛选只影响 count、不从 detail rows 聚合、不用 stale 覆盖 fresh。 |
| 关系标签投影 | P0 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/e2e/workbench-relation-fanout.spec.ts` | covered | relation distribution row、OA/invoice-only 边界、失败降级、不读 legacy candidate matches；Browser e2e 覆盖关联台 confirm 后页面标签从 `候选oa`/`候选发票` 变为 `有oa`/`有发票`。 |
| 银行流水导入后列表显示 | P0 | `tests/test_import_formalization_api.py`、`tests/test_bank_details_sql_runtime.py`、`web/e2e/imports-bank-transactions-flow.spec.ts` | covered | 导入确认后 bank detail read model 应能展示导入行；Browser e2e 覆盖导入页 confirm 后进入银行明细看到新流水。 |
| API route contract | P0 | `tests/test_bank_details_routes.py`、`tests/test_bank_auto_tag_rules_api.py` | covered | stale rows 仍 200；refreshing 空 payload 才 202；权限、错误 envelope、导出 facade。 |
| 导出 | P1 | `tests/test_bank_details_export_service.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx` | covered | 多 sheet、筛选转发、空结果、分页、公式转义、错误映射、filename、超过 20,000 行上限时页面展示行动建议。 |
| 前端列表/筛选/分页/search | P1 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts` | covered | 默认日期、账户切换、关键词、分类 counts、分页、表格中文标签。 |
| 前端 drawer、规则保存、重应用 | P1 | `web/src/test/BankDetailsPage.test.tsx` | covered | 保存/重应用后全局遮罩等待 `bank_detail` 可见月份 barrier fresh，再重读当前交易直到 fresh；只刷新交易，不重取账户余额；完成后广播事件和反馈状态。 |
| 前端 stale/refreshing/error/abort | P1 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts` | covered | 保留旧 rows、隐藏 read model 细节、unmount 清理 timer、abort 不报错。 |
| 跨页面真实 worker smoke | P2 | 夜间 CI + staging/手动验证 | documented-risk | 真实 Postgres/RabbitMQ/Redis 和历史数据需要环境级 smoke。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_bank_transaction_auto_category_service.py`、`tests/test_bank_transaction_category_service.py`、`tests/test_bank_transaction_identity_service.py` | 分类规则、内部往来、外部往来候选、manual/effective category、identity/dedup 属于核心业务。 |
| 2. Service-layer tests | 适用 | `tests/test_bank_details_service.py`、`tests/test_bank_details_export_service.py`、`tests/test_bankdetail_write_uow_contract.py` | 覆盖 service 编排、relation provider、导出、事务、审计、dirty/outbox rollback。 |
| 3. API contract tests | 适用 | `tests/test_bank_details_routes.py`、`tests/test_bank_auto_tag_rules_api.py` | 覆盖 accounts/transactions/规则/确认/人工补分类/reapply/file replacement、权限、错误字段和 stale/refreshing 响应。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_bank_details_sql_runtime.py`、`tests/test_bank_account_balance_read_model.py`、`tests/test_bankdetail_backfill_cli.py` | 覆盖 bank detail rows/scopes、schema/source version、dirty scope、worker fan-out、账户余额 read model 和 backfill。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/BankDetailsApi.test.ts` | 覆盖页面加载、筛选、drawer、候选确认、人工补分类、导出、domain event、stale/refreshing/abort。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bankdetail_write_uow_contract.py`、Workbench/no-OA/turnover/import 相关模块测试、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` | 本模块现有集成以 API/UoW/lifecycle 为主；Browser e2e 覆盖 Workbench confirm 后银行明细 relation tags fan-out，以及银行流水导入确认后银行明细显示导入行；真实导入到更多页面完整 smoke 仍归 staging/nightly 风险项。 |
| 7. Existing feature regression tests | 适用 | 上述全部 bank details 回归测试，加 `tests/test_workbench_*`、`tests/test_no_oa_*`、`tests/test_turnover_*`、`tests/test_cost_statistics_*` 的按改动选择扩展集 | 银行明细是多个页面上游事实源；任何标签、分类、read model、导入或关系变更都要先问会影响哪些旧页面。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 标签规则重应用只刷新银行明细交易，不应重算或覆盖账户余额。 | `web/src/test/BankDetailsPage.test.tsx`、`tests/test_bank_account_balance_read_model.py` | covered |
| 长期 | read model stale/schema mismatch 时空 rows 被误解为真实空列表。 | `tests/test_bank_details_routes.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/BankDetailsPage.test.tsx` | covered |
| 长期 | 前端用全量标签字典确认非当前候选，导致伪造分类。 | `tests/test_bank_auto_tag_rules_api.py`、`web/src/test/BankDetailsPage.test.tsx` | covered |
| 长期 | 人工分类绕过自动候选/内部往来确定性结果。 | `tests/test_bank_auto_tag_rules_api.py`、`tests/test_bank_transaction_category_service.py` | covered |
| 长期 | 银行原始字段跨银行 fallback，导出或表格展示错误语义。 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_export_service.py`、`web/src/test/BankDetailsApi.test.ts` | covered |
| 2026-06-16 | 银行明细导出超过 20,000 行时后端返回 `bank_detail_export_row_limit_exceeded`，前端若吞掉错误会误导用户以为下载失败且无缩小范围建议。 | `web/src/test/BankDetailsApi.test.ts::maps bank detail export row-limit errors to actionable messages`、`web/src/test/BankDetailsPage.test.tsx::shows backend export row-limit messages without starting a download` | covered |
| 长期 | 标签/分类写入成功但 dirty/outbox 或审计半写入。 | `tests/test_bankdetail_write_uow_contract.py`、`tests/test_bank_details_sql_runtime.py` | covered |
| 长期 | 关联台关系变更后银行明细 relation tag 不刷新。 | `tests/test_bank_details_service.py`、`tests/test_bank_details_sql_runtime.py`、`web/src/test/BankDetailsPage.test.tsx` | covered |
| 2026-06-15 | 自动标签配置被历史 settings 保存污染成只有 label 的 custom/system 定义，导致文件恢复生成新 code、旧确认记录缺外部往来 action。 | `tests/test_bank_transaction_category_service.py`、`tests/test_bank_details_sql_runtime.py` | covered |
| 2026-06-16 | `bank_detail:all` fan-out command 被下游 all-scope dependency defer 当成稳定 freshness scope，导致外部往来和免 OA 页面长期 refreshing。 | `tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_does_not_enqueue_bank_detail_all_for_all_scope_dependency`、`tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_bank_detail_all_shard_reason_does_not_bump_active_scope` | covered |
| 2026-06-16 | fresh `bank_detail` read model 中缺失部分 transaction id 时，tag facade 误判为 missing/not fresh 并持续补投 `downstream_bank_tag_read`。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_keeps_fresh_status_when_some_rows_are_not_projected`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_category_records_do_not_refresh_or_raise_when_fresh_model_has_missing_rows` | covered |
| 2026-06-16 | downstream tag facade 在任一月份 refreshing 时重刷所有相关月份，把已经 fresh 的月份反复打回 pending。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_refreshes_only_blocking_dirty_scopes` | covered |
| 2026-06-17 | downstream tag facade 丢弃 `category_version`、`manual_category_version`、`version`，导致外部往来 fresh grouped read model 提交旧 expected version，被后端 stale precondition 拒绝。 | `tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_get_by_transaction_ids_returns_standardized_fresh_tagged_rows`、`tests/test_bank_details_sql_runtime.py::BankTransactionTagReadFacadeTests::test_bulk_get_for_rows_preserves_versions_for_downstream_preconditions` | covered |
| 2026-06-17 | 自动标签规则保存/重新应用后页面在银行明细 read model 仍 refreshing 时提前可操作，导致用户看到旧标签或手动刷新后才更新。 | `web/src/test/BankDetailsPage.test.tsx::saving automatic tag rules refreshes bank details`、`web/src/test/BankDetailsPage.test.tsx::reapplying automatic tag rules refreshes bank details without saving changes`、`web/src/test/GlobalOperationOverlayContext.test.tsx` | covered |

## 关键 smoke flows

1. `银行流水导入确认 -> bank_account_balance + bank_detail dirty scope -> worker refresh -> /api/bank-details/accounts + /transactions fresh -> 页面展示余额、标签和原始字段`。当前 Browser e2e 覆盖导入页 confirm 后进入银行明细看到导入行。
2. `自动标签规则保存/文件替换 -> audit + lifecycle -> bank_detail/no-OA/turnover dirty -> 页面全局遮罩等待当前可见月份 fresh -> 交易重读 fresh -> 页面规则抽屉反馈完成 -> 旧账户余额不被 stale payload 覆盖`
3. `needs_confirmation 行 -> 后端重新计算当前候选 -> 用户确认第三层标签 -> dirty/outbox -> 银行明细、往来款、成本统计刷新`
4. `unmatched 行 -> 人工补分类 -> audit + dirty/outbox -> manual 清除 -> 回到当前自动规则计算`
5. `关联台确认/撤回 -> workbench relation distribution -> bank details relation tag projection -> 页面收到 domain event 或重新进入页面后 refetch`。当前 Browser e2e 覆盖 confirm 后回到银行明细显示 `有oa` / `有发票`；withdraw 仍待补。

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_service tests.test_bank_transaction_auto_category_service tests.test_bank_transaction_category_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api tests.test_bank_details_routes tests.test_bankdetail_write_uow_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bankdetail_backfill_cli -v
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_export_service tests.test_bank_transaction_identity_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_restore_bank_auto_tag_rules_tool -v
cd web && npm test -- --run src/test/BankDetailsApi.test.ts src/test/BankDetailsPage.test.tsx
cd web && npm run e2e:smoke
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_turnover_workbench_integration tests.test_no_oa_bank_batch_workbench_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_search_pending_projection -v
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/TurnoverLedgerPage.test.tsx src/test/CostStatisticsPage.test.tsx
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、build 和 deterministic Playwright smoke，覆盖完整 bank details 后端/Vitest 测试集，并覆盖真实 Chromium 中 Workbench confirm 后银行明细 relation tags 更新，以及银行流水导入后银行明细显示导入行。单轮模块验证只跑最小闭环，避免把所有历史下游页面回归作为每次人工推进的阻塞项。

## 未测风险

- 本轮不运行真实生产 Postgres/RabbitMQ/Redis worker drain；真实导入、backfill 和多页面 smoke 需要 staging 或夜间环境验证。
- 前端 Vitest 覆盖交互和 API mapper；当前 Browser e2e 覆盖 Workbench confirm fan-out 和银行导入后列表显示，但不覆盖 withdraw、错误恢复、真实浏览器视觉布局、超大数据滚动性能和下载文件人工验收。
- 银行明细对 pending invoices、turnover、no-OA、cost/tax 的 fan-out 仍需在对应模块轮次继续矩阵化；本模块只记录上游影响和已有关键保护。

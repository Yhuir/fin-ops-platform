# 待找发票测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

待找发票是发票生命周期、银行标签规则、Workbench 关系、人工补票和搜索 read model 的交汇页。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 发票获取状态 | `InvoiceLifecyclePolicy`、`invoice_lifecycle` read boundary、pending invoice read model | `invoice_acquisition_status` shape 保持兼容；页面不能私有定义状态或 primary action。 |
| 方向 | `expense` / `income` query scope | 支出读取进项发票与支出流水；收入读取销项发票与收入流水；`all` direction 组合双方 summary。 |
| 规则组 | `pending_invoice_tag_groups.version`、`pending_output_invoice_tag_groups.version` | 支出/收入规则版本独立；`requires_invoice` 是 active tag complement，不是可编辑持久事实。 |
| 银行标签 | bank detail effective category facade/read model | 规则筛选必须使用 effective category；标签归档/重命名刷新规则 drawer 和 pending read model。 |
| 人工补票 | `PendingInvoiceApplicationService.preview_manual_invoice` / `confirm_manual_invoice` | preview 不写事实；confirm 创建规范发票、relation、audit、command log 和 lifecycle event，且幂等/可恢复。 |
| 选择已有发票 | attach existing preview/confirm | 只允许 expense 选择 input invoice；可附加已被其他付款关联的发票；必须写 audit/finalizer。 |
| 收入状态标记 | income status override | `income_no_invoice_required` / `cash_income` 只刷新 pending/search，不误刷税金/成本/银行余额。 |
| API/read model | `PendingInvoiceReadModelService`、`SearchPendingSqlProjectionBuilder` | rows/filter-options/export 必须先经过 read model fresh gate；非 fresh 不能把空 rows 当真实结果。 |
| SQL projection | `read_model.pending_invoice_rows`、`read_model.pending_invoice_scopes` | four-zone payload、filter JSON、sort、source versions、bank tag freshness、relation distribution 和 OA identity。 |
| worker | `search-pending` worker | `pending_invoice.read_model.refresh` 支持方向/规则 filter/month shard 和 legacy scope fan-out。 |
| 前端交互 | `PendingInvoicesPage`、`web/src/features/pendingInvoices/api.ts` | 方向/filter、表头筛选、rules drawer、detail drawers、manual invoice、attach existing、income actions、read model refreshing。 |
| 跨模块 fan-out | invoice import、pending rules、manual invoice、attach existing、workbench relation、bank tag update | 必须先触发 invoice lifecycle，再刷新 pending invoice、search、税金/成本等下游；无关页面不能被误刷。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 支出待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | covered | 多发票同流水、规则命中、发票付款事实、最终 `invoice_acquisition_status`。 |
| 收入待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | `income_pending_invoice`、`cash_income`、`income_no_invoice_required`、收入规则筛选和 manual override。 |
| 规则版本与规则保存 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | 支出/收入版本独立、stale version conflict、requires complement、互斥分组、保存后 lifecycle。 |
| 人工补票 preview/confirm | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | preview 不写事实，confirm 幂等、失败可恢复、audit/finalizer、request id 保留。 |
| 选择已有发票 attach existing | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | preview/confirm、expense/input 限制、已关联其他付款仍可选、行刷新。 |
| API contract | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | covered | rows、detail、candidates、rules、manual、attach、income status、export、权限和错误 shape。 |
| SQL read model freshness | P0 | `tests/test_search_pending_sql_runtime.py` | covered | miss/stale/source mismatch 返回 refreshing 并入队，不同步扫描；filter-options/export 非 fresh 返回 accepted。 |
| SQL projection 内容 | P0 | `tests/test_search_pending_sql_runtime.py` | covered | four-zone payload、relation distribution、bank tag freshness、OA identity、candidate id 隔离、filter/sort。 |
| worker scope fan-out | P0 | `tests/test_search_pending_sql_runtime.py`、`tests/test_runtime_worker_registry.py` | covered | search/pending refresh handler、legacy pending scope、filter scope、month shard。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_pending_invoice_api.py` | covered | rules/manual/attach/income status 事件刷新正确 read model，不误刷无关域。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py` | covered | pending route/read model/worker 在 domain registry 中可观测。 |
| 前端交互 | P1 | `web/src/test/PendingInvoicesPage.test.tsx` | covered | four-zone table、filters、rules drawer、conflict、detail drawers、attach existing、manual invoice、refreshing 时操作可用。 |
| 前端 API mapper | P1 | `web/src/test/PendingInvoicesApi.test.ts` | covered | 不猜缺失状态、filter/sort query、rules/detail/candidates/attach/export/manual/income mapper。 |
| 真实生产数据与 worker drain | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres、RabbitMQ/Redis、search-pending/invoice-lifecycle worker 和大数据量样本。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖支出/收入状态、规则组、人工补票、attach existing、income override、候选排序和状态优先级。 |
| 2. Service-layer tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py` | 覆盖 application service、command repository、audit/finalizer、identity/backfill 和状态写入边界。 |
| 3. API contract tests | 适用 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | 覆盖 rows、filter-options、detail、rules、manual、attach、income status、export 和权限/错误。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_search_pending_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL read model fresh/stale/missing/source mismatch、worker refresh、lifecycle fan-out 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | 覆盖页面状态、筛选、规则、drawer/dialog、manual/attach/income 操作、refreshing 状态和 API mapper。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_pending_invoice_api.py`、`tests/test_search_pending_sql_runtime.py`、`web/src/test/PendingInvoicesPage.test.tsx` | 覆盖 manual/attach/rules/income status -> lifecycle/dirty scope -> read model -> 页面刷新；真实 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 pending invoice tests，加 invoice lifecycle、workbench、tax offset、cost statistics、bank details tests 的按改动选择扩展集 | 待找发票规则和关系会影响多个下游页面；任何改动都要问旧页面会不会被误刷或误判 fresh。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 前端在后端缺少状态字段时自行推断 pending invoice 状态或 primary action。 | `web/src/test/PendingInvoicesApi.test.ts` | covered |
| 长期 | `bank_statement_as_invoice` 筛选继续展示已经关联发票的流水。 | `tests/test_search_pending_sql_runtime.py::test_pending_invoice_sql_projection_excludes_already_invoiced_rows_from_statement_filter` | covered |
| 长期 | `requires_invoice` 被当成用户可编辑持久分组。 | `tests/test_pending_invoice_api.py::test_pending_invoice_rules_put_ignores_legacy_requires_invoice_input`、`tests/test_pending_invoice_service.py::test_requires_invoice_filter_uses_active_tag_complement` | covered |
| 长期 | 收入规则和支出规则共用版本或互相污染。 | `tests/test_pending_invoice_api.py::test_income_pending_invoice_rules_are_saved_separately_from_expense_rules`、`tests/test_pending_invoice_service.py::test_income_filters_use_pending_output_invoice_rule_groups` | covered |
| 长期 | 候选 relation case id 被当作真实 OA id 请求详情。 | `tests/test_pending_invoice_service.py::test_rows_keep_candidate_case_id_separate_from_real_oa_id`、`web/src/test/PendingInvoicesPage.test.tsx` | covered |
| 长期 | API/read model miss 时同步扫描旧 snapshot 并伪装 fresh。 | `tests/test_pending_invoice_api.py::test_read_model_miss_returns_refreshing_without_sync_scan`、`tests/test_search_pending_sql_runtime.py` | covered |
| 长期 | 人工补票 confirm 中途失败后重复创建发票或关系。 | `tests/test_pending_invoice_service.py::test_retry_recovers_invoice_created_before_relation_created`、`tests/test_pending_invoice_service.py::test_retry_recovers_relation_created_before_finalization` | covered |
| 长期 | attach existing 不允许已关联其他付款的发票，阻断合法多付款场景。 | `tests/test_pending_invoice_service.py::test_attach_existing_allows_invoice_already_linked_to_another_bank_payment` | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle refresh -> pending_invoice/read search dirty scope -> search-pending worker -> /pending-invoices rows fresh`
2. `待找发票规则保存 -> pending_invoice_rules_changed lifecycle -> pending/invoice_lifecycle/workbench/tax/cost/search refresh -> 不刷新 no_oa/bank balance/turnover`
3. `人工补票 preview -> confirm -> invoice import fact + pair relation -> audit/finalizer -> affected months -> 页面 refetch`
4. `选择已有发票 preview -> confirm -> relation/audit/finalizer -> affected months -> relation/detail/drawer 刷新`
5. `收入行标记 no invoice required/cash income -> pending_invoice_income_status_override_confirmed -> pending/search refresh -> 税金/成本不误刷`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_service tests.test_pending_invoice_api tests.test_invoice_lifecycle_page_integration -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_pending_invoice_relation_identity tests.test_pending_invoice_oa_identity_backfill -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v
cd web && npm test -- --run src/test/PendingInvoicesApi.test.ts src/test/PendingInvoicesPage.test.tsx
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api tests.test_tax_offset_api tests.test_cost_statistics_api tests.test_bank_auto_tag_rules_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api tests.test_oa_pending_payment_api tests.test_output_invoice_collection_api -v
cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx src/test/TaxOffsetPage.test.tsx src/test/CostStatisticsPage.test.tsx
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest 和 build，覆盖完整待找发票、SQL projection、invoice lifecycle、App Status 和前端测试集。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试不连接真实生产 Postgres 大数据量，不验证真实搜索/待找发票 SQL projection 的 EXPLAIN、锁等待或长尾分页性能。
- 本地测试不跑真实 RabbitMQ/Redis/systemd search-pending 与 invoice-lifecycle worker drain；dirty/outbox 到 projection 的最终收敛需要 staging 或夜间 CI/生产前 smoke。
- 前端 Vitest 覆盖交互和 mapper，不覆盖真实浏览器下载、大文件导出和真实网络中断恢复。

# 待找发票测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 发票获取状态 | `InvoiceLifecyclePolicy`、`PendingInvoiceQueryService`、invoice lifecycle read boundary | `invoice_acquisition_status` shape 保持兼容；页面不能私有定义状态或 primary action。 |
| 方向 | `expense` / `income` direct query scope | 支出读取进项发票与支出流水；收入读取销项发票与收入流水；`all` direction 组合双方 summary。 |
| 规则组与状态桶 | `pending_invoice_tag_groups.version`、`pending_output_invoice_tag_groups.version`、`invoice_acquisition_status.code` | 支出/收入规则版本独立；`requires_invoice` 作为列表 filter 是最终状态桶，不能依赖 `filter_group`。 |
| 银行标签 | bank detail effective category facade/direct provider | 规则筛选必须使用 effective category；标签归档/重命名后 direct refetch 规则 drawer 和 direct rows。 |
| 选择已有发票 | attach existing candidates/preview/confirm、`WorkbenchRelationCommandService` | 支持多条流水和多张发票批量 preview/confirm；候选表“流水关联”chip 由后端 relation facts 驱动；必须写 audit/finalizer。 |
| 多关系成员展示 | `workbench_relation` distribution、direct rows payload | `bank_transactions`、`input_invoices`、`oa` 分区必须按 relation 成员聚合；多项时 `+N` 表示该类型全部成员，不能同时展示 primary。 |
| 收入状态标记 | income status override | `income_no_invoice_required` / `cash_income` 支持批量选择；必须全量预检后一次写 command/audit/finalizer，不能逐行循环造成半成功。 |
| API/read model | direct rows/rules/filter/export frontend contract | 页面 API 不读取或返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_key(s)` 或 `refresh_enqueued`；`PendingInvoiceReadModelService`、`SearchPendingSqlProjectionBuilder`、`PendingInvoiceReadModelRepositoryPort` 已删除。 |
| SQL projection | 无 pending-invoice SQL projection | 当前运行代码不再读取/写入 `read_model.pending_invoice_rows` 或 `read_model.pending_invoice_scopes`；历史 migrations 仅作为数据库历史。 |
| worker | 无 pending-invoice worker | `pending_invoice.read_model.refresh`、`pending-invoice` worker、AppStatus/manifest/deploy env 已删除；runtime/RabbitMQ 示例测试不得再把该事件列为 supported event。 |
| 前端交互 | `PendingInvoicesPage`、`web/src/features/pendingInvoices/api.ts` | 方向/filter、表头筛选、rules drawer、detail drawers、选中工具栏 attach existing、收入批量状态；页面不得依赖 freshness 字段。 |
| 跨模块 fan-out | invoice import、pending rules、attach existing、income status、workbench relation、bank tag update | 必须先触发 invoice lifecycle / direct rows 可见变化；无关页面不能被误触发同步。 |

## 场景覆盖清单

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 支出/收入待找发票状态 | P0 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/pending-invoices-income-status-flow.spec.ts` | covered | 规则命中、发票付款事实、最终 `invoice_acquisition_status`、收入状态 override。 |
| 规则版本与规则保存 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-rules-save-flow.spec.ts` | covered | 支出/收入版本独立、stale version conflict、保存后 direct rows refetch、不请求 operation barrier。 |
| manual invoice 新写入口移除 | P0 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts` | covered | manual preview/confirm HTTP route 返回 not_found；页面没有行内三点、补票 dialog 或 manual API client。 |
| 选择已有发票 attach existing | P0 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-attach-existing-flow.spec.ts` | covered | candidates/preview/confirm、expense/input 限制、候选“流水关联”chip、preview 冲突原因、relation 合并和 withdraw 恢复。 |
| 多 OA / 多流水 / 多发票 `+N` 展示 | P0 | `tests/test_pending_invoice_service.py`、`web/src/test/PendingInvoicesApi.test.ts`、`web/src/test/PendingInvoicesPage.test.tsx` | covered | direct query 按 `workbench_relation` 聚合成员，前端按 `kind=bank|invoice|oa` 展开。 |
| API direct contract | P0 | `tests/test_pending_invoice_api.py`、`tests/test_invoice_lifecycle_sql_projection.py` | covered | 页面 route 返回 direct business payload 且剥离 freshness 字段；invoice lifecycle 不再导入 `SearchPendingSqlProjectionBuilder` 或读取 pending-invoice scopes。 |
| filter-options direct 聚合 | P0 | `tests/test_pending_invoice_api.py`、`tests/test_http_slo_probe.py` | covered | direct service 聚合筛选项；HTTP SLO 探针使用前端默认 `direction=expense`。 |
| export 全量收集上限 | P2 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/e2e/pending-invoices-export-download.spec.ts` | covered | 超过 20,000 行结构化返回 `pending_invoice_export_row_limit_exceeded`，不继续分页生成 XLSX。 |
| pending-invoice worker/projection/storage 不回流 | P0 | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_platform_runtime_boundary_guards.py` | covered | 负向覆盖 worker/registry/manifest/projection/repository port/read-model storage 当前运行面已删除。 |
| 前端交互 | P1 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`web/e2e/pending-invoices-*.spec.ts` | covered | four-zone table、filters、rules drawer、detail drawers、attach existing、收入批量标记、导出下载、失败可重试。 |
| 真实生产数据与 direct API 性能 | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres 大数据量样本、direct rows/filter/export SQL 性能和部署后旧 `invoice-lifecycle` worker 不再运行的 smoke。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖支出/收入状态、规则组、attach existing、多 relation 成员聚合和去重、income override、manual 新入口移除。 |
| 2. Service-layer tests | 适用 | `tests/test_pending_invoice_service.py`、`tests/test_pending_invoice_api.py`、`tests/test_pending_invoice_relation_identity.py`、`tests/test_pending_invoice_oa_identity_backfill.py` | 覆盖 application service、command repository、relation command service 委托、relation detail、identity/repair/backfill 工具、状态写入边界和 `page_size` 上限。 |
| 3. API contract tests | 适用 | `tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoicesApi.test.ts` | 覆盖 rows、detail、rules、candidate、attach、income status batch、export、权限/错误，以及页面响应不返回 freshness 字段。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_runtime_worker_registry.py`、`tests/test_invoice_lifecycle_sql_projection.py`、`tests/test_read_model_manifest.py`、`tests/test_postgres_repositories_boundaries.py` | 负向覆盖 pending-invoice worker/projection/repository port/read-model storage 当前运行面已删除；lifecycle 覆盖 direct pending query source。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/PendingInvoicesApi.test.ts`、`web/e2e/pending-invoices-*.spec.ts` | 覆盖页面状态、筛选、规则、drawer、`+N` 展示、选中工具栏 attach/income、manual UI 移除、首屏有界请求和失败恢复。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_pending_invoice_api.py`、`web/e2e/pending-invoices-*.spec.ts` | 覆盖 attach/rules/income status -> lifecycle/direct rows -> 页面 direct refetch；真实 direct API 收敛仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 pending invoice tests，加 invoice lifecycle、workbench、tax offset、cost statistics、bank details tests 的按改动选择扩展集 | 任何改动都要问旧页面会不会被误触发同步、误判 direct payload 可用、漏导 relation 字段、只导当前分页、在 filter/sort 后丢状态过滤或在 mutation 失败时半写。 |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle facts -> /pending-invoices direct rows reload`
2. `待找发票规则保存 -> lifecycle/direct rows refetch -> 不触发 pending-invoice read model worker`
3. `选择已有发票 candidates -> preview -> confirm -> relation/audit/finalizer -> affected months -> direct rows refetch`
4. `多选收入流水 -> 批量标记 no invoice required/cash income -> direct rows refetch -> 税金/成本/search 不被误触发同步`
5. `manual invoice legacy command retry -> command log 恢复旧中断状态；HTTP/UI 新入口保持不可达`

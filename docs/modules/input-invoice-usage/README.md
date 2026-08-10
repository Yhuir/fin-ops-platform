# 进项发票使用情况模块维护入口

- Module key：`input-invoice-usage`
- Route：`/input-invoice-usage`
- Page key：`input-invoice-usage`
- 当前读架构：页面专属 canonical PostgreSQL 直读

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/modules/input-invoice-usage/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/oa-integration/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 代码入口

- `web/src/pages/InputInvoiceUsagePage.tsx`
- `web/src/components/inputInvoiceUsage/*`
- `web/src/features/inputInvoiceUsage/api.ts`
- `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_canonical_query_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_export_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py`

## 当前事实边界

- 浏览器只调用 `/api/input-invoice-usage/*` 页面专属 API。首屏、筛选、排序、分页、summary、statistics 和 filter options 由一次 `/rows` 请求返回。
- 生产查询由 `InputInvoiceUsageCanonicalQueryService` 调用 `PostgresInputInvoiceUsageQueryRepository`。repository 在同一显式 `REPEATABLE READ READ ONLY` 事务内读取 rows、summary、statistics、facets 和支撑事实。
- 发票、银行流水、OA snapshot、支付规则和 OA reverse batch 来自 PostgreSQL canonical facts。页面请求热路径不得访问 OA、MongoDB、MySQL 或对象存储。
- 正式关系只读取 `app.workbench_pair_relations` 中 `status='active'` 的关系。不得读取 `read_model.workbench_relation_*`、`read_model.input_invoice_usage_*` 或 `read_model.invoice_lifecycle_*` 作为页面事实。
- 同一 active relation component 中的多发票、多 OA、多流水归并为一行；`invoiceRelations`、`oa`、`bankTransactions` 保留合计、`relationCount`、`detailMode` 和明细摘要。
- 支付状态只由 active relation、OA/流水金额合计和已配置支付规则判定；未正式化 candidate 不得充当已付款证据。
- `/rows/{row_id}/relation-details`、详情、导出和 OA reverse preview 使用同一 canonical query 边界，不允许 live fallback、双读或全量 Python 过滤。
- OA 详情以 rows DTO 中的 canonical `oa.id` 定向读取 `app.oa_applications` 及 admission；不得把 OA id 当作进项发票使用行的 hash id，也不得先加载整组页面行。
- rows 响应不含 `read_model_status`、`source_versions`、refresh target 或 polling 合同；前端只维护 loading、empty、error 和用户主动刷新状态。
- OA reverse 命令继续写 canonical batch/relation/audit/idempotency facts；成功后当前页面重跑正常 GET。写命令不等待页面 read model 或 operation barrier。

## 权限与审计

- 页面读取和导出沿用现有 `finops:app:view` / 导出权限映射。
- 支付规则、OA reverse 草稿和人工状态写入沿用原有 full-access/admin 权限。
- route 只做 session、权限、参数和 HTTP 映射；service 不读取 header/cookie，repository 不做权限判断。
- App Health 中历史 read-model 审计入口仍是共享运维能力，不是本页面读路径；其删除或调整由全局清理任务统一处理。

## 维护触发器

发生以下变化时更新本目录，并按影响同步长期事实源：

- 页面筛选、排序、分页、详情、导出、OA reverse 或权限变化。
- canonical 表、active relation 口径、支付规则或 rows/summary/facets DTO 变化。
- snapshot 一致性、查询次数、SQL 性能或写后 GET 行为变化。
- 页面专属旧 read-model 代码或共享 worker/manifest 的最终清理。

## 本目录文件

- `boundary-io.md`：当前输入、输出、文件和依赖边界。
- `tests.md`：七类测试适用性、命令和剩余风险。
- `state-machine.md`：OA reverse 与支付状态业务状态。
- `oa-reverse-design.md`：OA reverse 业务与安全设计。
- `implementation-notes.md`：历史决策记录；历史 read-model 描述不覆盖本 README 的当前事实。

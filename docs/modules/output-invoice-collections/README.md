# 销项发票收款情况模块维护入口

- Module key：`output-invoice-collections`
- Route：`/output-invoice-collections`
- Page key：`output-invoice-collections`
- 当前读架构：页面专属 canonical PostgreSQL 直读

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/modules/output-invoice-collections/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/domain-events-lifecycle/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 代码入口

- `web/src/pages/OutputInvoiceCollectionsPage.tsx`
- `web/src/components/outputInvoiceCollections/*`
- `web/src/features/outputInvoiceCollections/api.ts`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_receipt_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/output_invoice_collection.py`

## 当前事实边界

- 浏览器只调用 `/api/output-invoice-collections/*` 页面专属 API。首屏、筛选、排序、分页、summary、statistics 和 filter options 由一次 `/rows` 请求返回。
- 生产查询由 `OutputInvoiceCollectionCanonicalQueryService` 调用 `PostgresOutputInvoiceCollectionQueryRepository`。repository 在同一显式 `REPEATABLE READ READ ONLY` 事务内读取 rows、summary、statistics、facets、关系和 lifecycle overlay。
- 发票、银行流水、OA snapshot、收款/红字/收据 lifecycle facts 来自 PostgreSQL canonical tables。页面请求热路径不得访问 OA、MongoDB、MySQL 或对象存储。
- 正式关系只读取 `app.workbench_pair_relations` 中 `status='active'` 的关系。不得读取 `read_model.workbench_relation_*`、`read_model.output_invoice_collection_*` 或 `read_model.invoice_lifecycle_*` 作为页面事实。
- 同一 active relation component 中的多张销项发票归并为一行，金额按成员净额合计；负数和红字发票必须保留在 `invoiceRelations.summaries`。
- 收款状态由 canonical relation、银行流水和 lifecycle overlay 组合；正式收据 create/void/reissue、手动状态、提醒和红蓝票关系继续写 canonical facts。
- `/rows/{row_id}/relation-details`、详情、导出和写后查询使用同一 canonical query 边界，不允许 live fallback、双读或全量 Python 过滤。
- rows 响应不含 `read_model_status`、`source_versions`、refresh target 或 polling 合同；前端只维护 loading、empty、error 和用户主动刷新状态。
- 写命令保持权限、审计、CAS/idempotency 和冲突合同；成功后当前页面重跑正常 GET，不等待 operation barrier。

## 权限与审计

- 页面读取和导出沿用现有 view/export 权限。
- 收款状态、提醒、红蓝票、收据生命周期和编号设置沿用原 full-access/admin 权限。
- route 只做 session、权限、参数和 HTTP 映射；service 不读取 header/cookie，repository 不做权限判断。
- App Health 中历史 read-model 审计入口仍是共享运维能力，不是本页面读路径；其最终清理由全局任务处理。

## 维护触发器

发生以下变化时更新本目录，并按影响同步长期事实源：

- 页面筛选、排序、分页、详情、导出、drawer/dialog 或权限变化。
- canonical 表、active relation 口径、净额归并、lifecycle 或 rows/summary/facets DTO 变化。
- snapshot 一致性、查询次数、SQL 性能、收据幂等或写后 GET 行为变化。
- 页面专属旧 read-model 代码或共享 worker/manifest 的最终清理。

## 本目录文件

- `boundary-io.md`：当前输入、输出、文件和依赖边界。
- `tests.md`：七类测试适用性、命令和剩余风险。
- `state-machine.md`：收款、提醒、红蓝票和收据生命周期。
- `implementation-notes.md`：历史决策记录；历史 read-model 描述不覆盖本 README 的当前事实。

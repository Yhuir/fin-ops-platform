# 销项发票收款情况模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：`canonical-direct-read`
- 当前边界可信度：high
- Query owner：`OutputInvoiceCollectionCanonicalQueryService`
- PostgreSQL owner：`PostgresOutputInvoiceCollectionQueryRepository`
- 旧页面 read model：已退出 API/frontend 运行时；共享 projection/worker 注册项待主控统一清理。

## 职责边界

### 负责

- 销项发票收款 rows、summary、statistics、facets、筛选、排序和服务端分页。
- OA、收入流水、关联发票、红蓝票、收据详情和当前筛选导出。
- active relation component 的多发票净额归并，保留负数/红字成员。
- 手动收款状态、提醒、红蓝票 relation 和正式收据 canonical 写入及写后 GET。

### 不负责

- 不拥有进项发票使用或外部 OA 同步业务。
- 不拥有 `app.workbench_pair_relations` 的写模型。
- 不读取或刷新 Workbench、invoice lifecycle 或页面 read model。
- 不修改共享 worker、manifest、scope policy、dispatcher、deploy env 或 App Status registry。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| rows 查询 | `OutputInvoiceCollectionsPage.tsx` | `page`、`page_size`、keyword、日期/月、filters、sort；非法值返回 400 |
| canonical invoices | `app.invoices` | 只取非删除 output invoices；正数、负数和红字成员都保留 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；按 relation component 聚合 |
| bank/OA facts | `app.bank_transactions`、`app.oa_applications` | 只读取已同步 PostgreSQL snapshot |
| lifecycle facts | output collection lifecycle/receipt tables | 同 transaction 读取 status/reminder/red relation/receipt overlay |
| lifecycle command | 页面专属写 API | 保持权限、审计、CAS/idempotency 和冲突合同；成功后 GET |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `/rows` | 页面 | 同一 snapshot 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions` |
| relation/details | drawer | 按 row/invoice/bank/OA id 定向读取；不存在返回 404 |
| export preview/download | export drawer | 复用 canonical filters/sort；20,000 行上限和原错误合同不变 |
| lifecycle/receipt result | 页面 | 响应只含 canonical mutation result；不含 refresh target/barrier |
| write convergence | 页面 | 成功后重跑当前 GET，读取同一 canonical query contract |

`/rows` 不输出 `read_model_status`、`source_versions`、`refresh_enqueued`、scope 或 polling 字段。

## 一致性与性能合同

- 每个页面读请求开启一个 `REPEATABLE READ READ ONLY` transaction。
- rows、summary、statistics、facets、facts 和 lifecycle overlay 都在该 transaction 中读取。
- rows/summary/facets 复用一次 materialized canonical CTE；含 supporting red pair 与 lifecycle overlay 时整个请求最多 11 条批量 SQL statement，数量不随当前页行数或 relation 数增长。
- 服务端完成筛选、排序、分页；Python 只组装当前页有界 facts。
- 多发票 relation 金额使用成员净额，负数/红字发票不得在 SQL 或 DTO 中丢失。
- 只有 EXPLAIN 或真实慢查询证据支持时才增加索引；本模块不自行创建 migration。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/src/features/outputInvoiceCollections/*`、`web/src/components/outputInvoiceCollections/*` |
| Route | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` |
| Query service | `output_invoice_collection_canonical_query_service.py` |
| Business assembler | `output_invoice_collection_service.py` |
| Query repository | `postgres_repositories/invoice_usage_collection_query.py` |
| Lifecycle repository | `postgres_repositories/output_invoice_collection.py` |
| Commands | `output_invoice_collection_lifecycle_service.py`、`output_invoice_collection_receipt_service.py` |
| Tests | `tests/test_output_invoice_collection*.py`、`tests/test_invoice_usage_collection_canonical_query.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections*.spec.ts` |

## 依赖方向

`frontend -> route -> canonical query service -> page query repository -> canonical PostgreSQL tables`

写路径为：

`frontend -> route -> lifecycle/receipt service -> canonical repository/audit -> current rows GET`

禁止依赖方向：

- route -> SQL
- query service -> HTTP/session
- page query repository -> read-model tables
- frontend -> filter-options/read-model refresh/status endpoint

## 共享清理 HANDOFF

本分支不删除仍由其它调用方或全局注册引用的以下共享资源：

- `InvoiceUsageCollectionSqlProjectionBuilder` 的 output projection 代码。
- `invoice-usage-collection` worker/handler/registry/manifest/deploy 配置。
- `output_invoice_collection` read-model scope policy、App Status/audit/repair 注册项和全局表清理 migration。
- 仍被其它模块使用的 `invoice_lifecycle` 或 `workbench_relation` read model。

所有页面分支合并后，由主控做 whole-repo scan 再统一删除。

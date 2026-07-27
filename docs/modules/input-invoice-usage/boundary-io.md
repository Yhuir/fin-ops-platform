# 进项发票使用情况模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：`canonical-direct-read`
- 当前边界可信度：high
- Query owner：`InputInvoiceUsageCanonicalQueryService`
- PostgreSQL owner：`PostgresInputInvoiceUsageQueryRepository`
- 旧页面 read model：API/frontend、projection/repository、worker/registry/deploy 和 lifecycle 间接链均已删除。

## 职责边界

### 负责

- 进项发票使用 rows、summary、statistics、facets、筛选、排序和服务端分页。
- 发票/OA/银行流水/关联发票详情、当前筛选导出和 OA reverse preview。
- active relation component 聚合、金额合计和支付状态计算。
- OA reverse canonical batch、relation、审计、CAS/idempotency 写入及写后 GET。

### 不负责

- 不拥有 OA 登录和外部 OA 数据同步。
- 不拥有 `app.workbench_pair_relations` 的写模型。
- 不读取或刷新 Workbench、invoice lifecycle 或页面 read model。
- 不修改共享 worker、manifest、scope policy、dispatcher、deploy env 或 App Status registry。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| rows 查询 | `InputInvoiceUsagePage.tsx` | `page`、`page_size`、keyword、日期/月、filters、sort；非法值返回 400 |
| canonical invoices | `app.invoices` | 只取非删除 input invoices；金额和日期保持 canonical 口径 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；按 relation component 聚合 |
| bank/OA facts | `app.bank_transactions`、`app.oa_applications` | 只读取已同步 PostgreSQL snapshot |
| payment rules | `app.app_settings` | 使用现有 input invoice payment rule contract |
| OA reverse facts | `app.input_invoice_usage_oa_reverse_batches` | statistics、preview 和命令状态 |
| lifecycle command | 页面专属写 API | 保持原权限、审计、CAS/idempotency；成功后 GET |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `/rows` | 页面 | 同一 snapshot 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions` |
| relation/details | drawer | 按 row/invoice/bank/OA id 定向读取；不存在返回 404 |
| export preview/download | export drawer | 复用 canonical filters/sort；20,000 行上限和原错误合同不变 |
| OA reverse preview/command | OA reverse drawer | preview 只读 canonical snapshot；命令只写 canonical facts |
| write result | 页面 | 不含 refresh target/barrier；页面成功后重跑当前 GET |

`/rows` 不输出 `read_model_status`、`source_versions`、`refresh_enqueued`、scope 或 polling 字段。

## 一致性与性能合同

- 每个页面读请求开启一个 `REPEATABLE READ READ ONLY` transaction。
- rows、summary、statistics、facets 和用于组装当前页的 facts 都在该 transaction 中读取。
- rows/summary/facets 复用一次 materialized canonical CTE；整个请求最多 8 条批量 SQL statement，数量不随当前页行数或 relation 数增长。
- 服务端完成筛选、排序、分页；Python 只组装当前页有界 facts。
- 只有 EXPLAIN 或真实慢查询证据支持时才增加索引；本模块不自行创建 migration。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/features/inputInvoiceUsage/*`、`web/src/components/inputInvoiceUsage/*` |
| Route | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py` |
| Query service | `input_invoice_usage_canonical_query_service.py` |
| Business assembler | `input_invoice_usage_service.py` |
| Query repository | `postgres_repositories/invoice_usage_collection_query.py` |
| Commands/export | `input_invoice_usage_oa_reverse_service.py`、`input_invoice_usage_export_service.py` |
| Tests | `tests/test_input_invoice_usage*.py`、`tests/test_invoice_usage_collection_canonical_query.py`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` |

## 依赖方向

`frontend -> route -> canonical query service -> page query repository -> canonical PostgreSQL tables`

写路径为：

`frontend -> route -> command service -> canonical repository/audit -> current rows GET`

禁止依赖方向：

- route -> SQL
- query service -> HTTP/session
- page query repository -> read-model tables
- frontend -> filter-options/read-model refresh/status endpoint

## 跨页面清理结果

`InvoiceUsageCollectionSqlProjectionBuilder` 的 input projection、invoice-usage-collection worker/handler/registry/manifest/deploy、input read-model scope/App Status/audit/repair 注册项已删除。历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

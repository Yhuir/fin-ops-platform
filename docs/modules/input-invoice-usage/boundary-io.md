# 进项发票使用情况模块边界与 I/O

日期：2026-08-11

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
| rows 查询 | `InputInvoiceUsagePage.tsx` | `page`、`page_size`、keyword、日期/月、filters、sort；非法值返回 400。纯金额 keyword 使用无千分位文本并查询价税合计、未税金额、税额和关联流水金额。 |
| canonical invoices | `app.invoices` | 只取非删除 input invoices；金额和日期保持 canonical 口径 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；按 relation component 聚合 |
| bank/OA facts | `app.bank_transactions`、`app.oa_applications`、`app.oa_pending_payment_admissions` | 只读取已同步 PostgreSQL snapshot；OA summary 输出 canonical `workflowStatus=completed|in_progress`，重复 identity fail closed |
| OA detail id | rows DTO 的 `oa.id` | 只接受 canonical OA identity；repository 通过既有 OA workflow repository 定向查询，不经过进项发票使用行 hash |
| payment rules | `app.app_settings` | 使用现有 input invoice payment rule contract |
| OA reverse facts | `app.input_invoice_usage_oa_reverse_batches` | statistics、preview 和命令状态 |
| lifecycle command | 页面专属写 API | 保持原权限、审计、CAS/idempotency；成功后 GET |
| OA 草稿预填配置 | `GET/PUT /api/workbench/settings/oa-draft-prefill/input-invoice-usage` | 所有已授权 App 账户可见并可只读打开页面右上角抽屉，仅 admin 可编辑/保存独立 versioned family；创建 reverse batch 时固化当次配置快照，后续 OA draft 创建不受并发设置变更影响。多销方或缺失销方 fail closed |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `/rows` | 页面 | 同一 snapshot 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions` |
| relation/details | drawer | row/invoice/bank 按 canonical id 定向读取，不存在返回 404；OA 详情按 canonical OA id 返回 `detailAvailable=true|false`，不可用时保持 200 的既有 drawer 合同 |
| OA 申请人列 | frontend | 使用 HeroUI 原生 chip 显示真实申请类型与“已完成/进行中”；不得从 linked/unlinked 关系状态推断流程状态 |
| export preview/download | export drawer | 复用 canonical filters/sort；20,000 行上限和原错误合同不变 |
| OA reverse preview/command | OA reverse drawer | preview 只读 canonical snapshot，并分别返回 `permissions.canCreateDraft` 写能力与当前整组 `canCreateDraft` 业务可创建状态；前端对当前勾选集合只做同一非空销方的轻量可用性判断，提交前必须按精确发票集合重新 preview，并以新 preview 的权限、业务状态和 hash 为准。命令只写 canonical facts；候选金额展示与本地搜索都使用无千分位文本。OA payload 动态写目标申请人、当天日期、所选总额和唯一销方，申请事由只显示发票数/发票号码，内部 reverse batch ID 仅保留结构化字段。 |
| write result | 页面 | 不含 refresh target/barrier；页面成功后重跑当前 GET |

`/rows` 不输出 `read_model_status`、`source_versions`、`refresh_enqueued`、scope 或 polling 字段。

## 一致性与性能合同

- 每个页面读请求开启一个 `REPEATABLE READ READ ONLY` transaction。
- rows、summary、statistics、facets 和用于组装当前页的 facts 都在该 transaction 中读取。
- rows/summary/facets 复用一次 materialized canonical CTE；付款规则从同一 request snapshot 交给有界行装配，禁止逐行重读 `app_settings`。整个请求最多 8 条批量 SQL statement，数量不随当前页行数或 relation 数增长。
- 服务端完成筛选、排序、分页；Python 只组装当前页有界 facts。
- OA 详情使用一个独立只读 repeatable-read transaction 和一次有界 OA identity 查询；禁止加载页面 row group、发票或流水作为间接查找。
- 只有 EXPLAIN 或真实慢查询证据支持时才增加索引；本模块不自行创建 migration。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，页面不得维护第二套详情 renderer。
- 单条和多条使用同一公开字段合同；多条只重复 `OA N`、`银行流水 N`、`发票 N` 分区，不输出关系概况、数量、是否多条或内部 case/source 信息。
- 仅展示 canonical API 实际返回且已登记为用户可见的字段；内部 ID、raw payload、批次字段和推导字段在共享边界过滤。
- 详情按需一次有界读取，不得逐成员 N+1；时间统一为 `Asia/Shanghai` 的无 `T`/`Z`/offset 格式。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/features/inputInvoiceUsage/*`、`web/src/features/oaDraftPrefill.ts`、`web/src/components/inputInvoiceUsage/*`、`web/src/components/common/OaDraftPrefillDrawer.tsx` |
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

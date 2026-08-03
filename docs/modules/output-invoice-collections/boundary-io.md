# 销项发票收款情况模块边界与 I/O

日期：2026-07-31

## 模块化状态

- 状态：`canonical-direct-read`
- 页面能力：只读、筛选、排序、分页、详情、导出
- Query owner：`OutputInvoiceCollectionCanonicalQueryService`
- PostgreSQL owner：`PostgresOutputInvoiceCollectionQueryRepository`
- 自动红蓝票关系 owner：Workbench matching/formal relation 边界
- 页面 read model/worker：无

## 职责边界

### 负责

- 销项发票 rows、summary、statistics、facets、筛选、排序和服务端分页。
- 销项发票、已关联收入流水和销项发票关系详情。
- 当前筛选结果的导出预览和 XLSX 下载。
- 根据 canonical facts 计算六种收款/红蓝票状态。
- 消费 Workbench 已正式化的 `output_invoice_reversal` 关系。

### 不负责

- 不拥有 OA、收据、提醒、预计收款日期或手工收款状态。
- 不提供手工红蓝票确认/撤销 API。
- 不拥有 `app.workbench_pair_relations` 写模型；自动关系由 Workbench 边界创建和撤回。
- 不读取或刷新任何页面、Workbench relation 或 invoice lifecycle read model。
- 不修改共享 worker、manifest、dispatcher 或 deploy env。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| rows 查询 | `OutputInvoiceCollectionsPage.tsx` | `page`、`page_size`、keyword、月份、filters、sort；非法值返回 400。纯金额 keyword 使用无千分位文本并查询价税合计、税额、待收和关联收款金额。 |
| canonical invoices | `app.invoices` | 只取非删除 output invoices；正票和负票分别保留 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；红蓝票关系识别 `mode=output_invoice_reversal` |
| bank facts | `app.bank_transactions` | 只统计 active relation 中的收入流水；支出不计入已收金额 |
| exact reversal candidates | Workbench matching engine | 标准化税号、币种、税率及金额绝对值；唯一、日期合法才允许正式化 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `GET /rows` | 页面 | 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions` |
| `GET /filter-options` | 页面/兼容调用 | 返回同一 canonical facets；不读取缓存或 read model |
| invoice/bank detail | 详情抽屉 | 按 canonical id 定向读取；不存在返回 404 |
| relation detail | 详情抽屉 | 只支持 `kind=bank|invoice` |
| export preview/download | 导出 | 复用 canonical filters/sort；20,000 行上限 |

row 顶层只包含：

`id`、`invoiceId`、`invoiceIdentityKey`、`invoice`、`collectionStatus`、`bank`、`invoiceRelations`。

禁止输出 OA、receipt、manual status、reminder、read-model freshness、source version、refresh target 或 polling 字段。

## 状态输出

| code | 展示 | 判定 |
| --- | --- | --- |
| `pending_collection` | 待收款 | 正票且没有足额关联收入 |
| `partial_collected` | 部分收款 | 正票已关联部分收入 |
| `collected` | 已收款 | 正票已关联足额收入 |
| `reversed_by_red` | 已被红冲 | 正票处于有效 `output_invoice_reversal` 关系 |
| `reverses_blue` | 已冲销蓝票 | 负票处于有效 `output_invoice_reversal` 关系 |
| `unmatched_red` | 红票待核对 | 负票没有有效红蓝票关系 |

## 一致性与性能合同

- 一个页面请求使用一个 `REPEATABLE READ READ ONLY` snapshot。
- repository set-based 完成筛选、排序、分页和聚合；service 只组装当前页有界 DTO。
- SQL 数量不得随当前页行数、关系数量或红蓝票数量线性增长。
- 自动红蓝票关系必须确定性、幂等；歧义时不创建关系。
- 页面不通过 Redis/read model 提速；只有真实慢查询证据才增加索引或缓存。
- API 错误必须 fail closed，不回退已删除的 lifecycle/receipt/read-model 路径。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/OutputInvoiceCollectionsPage.tsx`、`web/src/features/outputInvoiceCollections/*`、`web/src/components/outputInvoiceCollections/OutputInvoiceCollection*.tsx` |
| Route | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` |
| Query service | `backend/src/fin_ops_platform/services/output_invoice_collection_canonical_query_service.py` |
| Assembler | `backend/src/fin_ops_platform/services/output_invoice_collection_service.py` |
| Query repository | `backend/src/fin_ops_platform/services/postgres_repositories/invoice_usage_collection_query.py` |
| Matching/formal relation | `workbench_free_matching_engine.py`、`workbench_relation_command_service.py`、`postgres_repositories/workbench_formal_relation.py` |
| Tests | `tests/test_output_invoice_collection*.py`、`tests/test_invoice_usage_collection_canonical_query.py`、`tests/test_workbench_free_matching_engine.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-*.spec.ts` |

## 依赖方向

读取：

`frontend -> route -> canonical query service -> query repository -> canonical PostgreSQL tables`

自动红蓝票：

`Workbench matcher -> relation command service -> formal relation repository -> app.workbench_pair_relations`

禁止：

- route -> SQL
- query service -> HTTP/session
- page query repository -> read-model/lifecycle/receipt tables
- frontend -> mutation/status/reminder/receipt/manual-red API
- output collection module -> Workbench repository 直接写关系

## 旧代码删除条件

旧 lifecycle/status/reminder/receipt/manual-red 文件、route、frontend drawer、API client、DTO、E2E mock 和权限 opener 必须保持删除。历史 schema/migration 只有在独立、可回滚的数据迁移中才物理删除。

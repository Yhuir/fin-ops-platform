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
| canonical invoices | `app.invoices` | 只取非删除 output invoices；正票和负票分别保留；原始 `remark` 仅按精确“被红冲蓝字数电发票号码”标记提取结构化号码 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；红蓝票关系识别 `mode=output_invoice_reversal` |
| bank facts | `app.bank_transactions` | 只统计 active relation 中的收入流水；支出不计入已收金额 |
| exact reversal candidates | Workbench matching engine | 标准化税号、币种、税率及金额绝对值；唯一、日期合法才允许正式化 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `GET /rows` | 页面 | 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions`；`invoice.reversalTargetInvoiceNos` 只来源于原始备注精确标记；`collection_status` 候选排除自身状态条件后聚合，并补齐六种合法状态，选择状态不得缩减候选词表 |

`statistics` 只包含 canonical 销项发票总数、收入流水、蓝字发票和红字发票数量；红蓝按含税总额符号互斥分类，并满足蓝字 + 红字 = 销项总数。旧收款和关系状态数量字段已删除。
| `GET /filter-options` | 页面/兼容调用 | 返回同一 canonical facets；不读取缓存或 read model |
| invoice/bank detail | 详情抽屉 | 按 canonical id 定向读取；发票详情保留完整 remark 和精确提取的被冲红蓝票号；不存在返回 404 |
| relation detail | 详情抽屉 | 只支持 `kind=bank|invoice` |
| export preview/download | 导出 | 复用 canonical filters/sort；独立输出“冲红蓝字发票号码”列；20,000 行上限 |

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
- 收款状态的 self-excluding facet 与当前页 rows 共用一个 SQL statement 和同一 canonical CTE snapshot，不增加 API 或数据库往返。
- SQL 数量不得随当前页行数、关系数量或红蓝票数量线性增长。
- keyword 在同一 grouped invoice SQL 中搜索发票备注，不增加逐行查询、缓存、worker 或 read model。
- 自动红蓝票关系必须确定性、幂等；歧义时不创建关系。
- 备注提取号码是展示/搜索/导出证据，不能反向修改收款状态或正式红蓝票关系。
- 页面不通过 Redis/read model 提速；只有真实慢查询证据才增加索引或缓存。
- API 错误必须 fail closed，不回退已删除的 lifecycle/receipt/read-model 路径。
- 首次加载可显示 skeleton；后续筛选、排序、分页和手动刷新保留现有 HeroUI FinanceTable DOM，只更新表格内容，刷新失败保留上一份成功结果并显示错误。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，页面不得维护私有详情 grid/card。
- 单条和多条使用同一公开字段合同；红蓝票和其它多条关系只重复 `发票 N` 分区，不输出关系概况、关系数量、是否多条或内部 case/source 信息。
- 仅展示 canonical API 实际返回且已登记为用户可见的字段；内部 ID、raw payload、批次字段和推导字段在共享边界过滤。
- 详情按需一次有界读取，不得逐成员 N+1；时间统一为 `Asia/Shanghai` 的无 `T`/`Z`/offset 格式。

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

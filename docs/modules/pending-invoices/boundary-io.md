# 待找发票模块边界与 I/O

日期：2026-07-27

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 页面读边界：页面专属 API → `PendingInvoiceCanonicalQueryService` → `PostgresPendingInvoiceCanonicalRepository` → PostgreSQL canonical facts。
- 运行时语义：页面没有 read-model freshness gate、refresh enqueue、polling、202、stale/fallback 或 `read_model_status/source_versions`。
- 共享资源：`search` 与 `workbench_relation` 只服务各自登记消费者；旧
  `pending_invoice`、search-pending、invoice-lifecycle 页面 worker 已删除。

## 职责边界

### 负责

- 待找发票 rows、summary、全期间 statistics、filter options、筛选、排序、服务端分页和导出。
- 页面候选发票、relation detail、流水/发票/OA object detail。
- 规则读取/保存、选择已有发票、收入状态覆盖的页面 API 与写后重新 GET。
- 保持支出/收入/现金收入、`paid_invoiced`、无需开票、OA/进销项覆盖、规则优先级和权限审计口径。

### 不负责

- 不拥有 bank/invoice/OA canonical facts，也不直接写这些表。
- 不拥有 `app.workbench_pair_relations`；关系写入仍委托 `WorkbenchRelationCommandService`。
- 不拥有 Search API、invoice lifecycle 页面或共享 read-model/worker 的删除。
- 不从外部 OA/Mongo/MySQL/对象存储读取页面请求。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| direction/filter/date/keyword/field filters/sort/page | `PendingInvoicesPage.tsx`、`features/pendingInvoices/api.ts` | route 只传递解析后的 query；service 验证方向、筛选、日期、排序、过滤器和分页；repository 负责 SQL |
| 页面 canonical facts | PostgreSQL `app.*` | 银行流水、分类/确认、settings、pending income overrides、invoice/OA snapshots；禁止读取 `read_model.pending_invoice_*`、`read_model.bank_detail_*`、`read_model.workbench_relation_*`、`read_model.search_*` |
| 正式配对关系 | `app.workbench_pair_relations` | 只读取 `status='active'`；排除 `turnover_manual_closure`；跨月 relation 不按当前月份截断 |
| 候选与详情 | 页面专属 API | 候选采用 canonical input invoices + selected canonical expense banks + active relation facts；object detail 按 canonical id 有界读取 |
| 规则/关联/收入状态写入 | existing application/rules services | 保留权限、audit、idempotency、CAS/占用冲突、command 状态；写成功后页面重新 GET canonical facts |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| rows + summary + statistics | 前端页面 | 同一显式 `REPEATABLE READ / READ ONLY` snapshot；settings SELECT + 一次 set-based 页面 SELECT；固定两次 SELECT |
| rows.filter_options | 前端筛选 | 与 rows/summary/statistics 共用同一 `REPEATABLE READ` snapshot 和同一次 HTTP 响应；有界每字段最多 50 项，数据库聚合，不把全部 rows 加载到 Python/浏览器 |
| export-preview/export | 前端导出 | 复用同一 canonical row DTO；最大 20,000 行，超限先报错；不读取页面 read model |
| relation/object detail | 前端抽屉 | active canonical relations；`kind=bank|invoice|oa` 只控制响应分区 |
| invoice candidates | 前端选择已有发票抽屉 | 服务端过滤、排序、分页；固定两次 SELECT；返回 candidate/bank relation status 与关联流水数 |
| loading/empty/error | 前端可观察状态 | loading、合法空集、错误可区分；没有 refreshing/stale UI 或轮询 |

## 一致性、查询与性能

- `PostgresPendingInvoiceCanonicalRepository.query()` 显式开启 `REPEATABLE READ / READ ONLY`。
- rows、当前筛选 summary、全期间 statistics、facets/counts 由一次 set-based SQL 计算，分页在 SQL 中执行。
- 页面首次加载和筛选变更只调用 `/api/pending-invoices/rows`；独立
  `/api/pending-invoices/filter-options` 只保留为兼容 API，页面不得再并行发出重复聚合请求。
- 分类/确认/income override、relation members、invoice/OA/bank summaries 都批量聚合；禁止 per-row/per-group N+1。
- 自动规则字符串使用 PostgreSQL `normalize(..., NFKC)`、空白折叠及现有“帐户→账户”口径。
- SQL 分类后由 `pending_invoice_status_payload` 再校验；若 SQL 和领域策略分歧则请求失败。
- 50,003 条本地 PostgreSQL canonical bank rows 的实测记录在 `implementation-notes.md`；本次未新增 cache、queue、worker、materialized view、索引或依赖。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/PendingInvoicesPage.tsx` |
| Frontend API/types/components | `web/src/features/pendingInvoices/*`、`web/src/components/pendingInvoices/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` |
| Page query service/repository | `backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py` |
| Existing write/export formatting | `pending_invoice_service.py`、`pending_invoice_rules_application_service.py` |
| Minimal assembly | `backend/src/fin_ops_platform/app/server.py` |
| Tests | `tests/test_pending_invoice_canonical_query.py`、`tests/test_pending_invoice_api.py`、`web/src/test/PendingInvoices*.test.*` |

## 依赖方向

- 允许：page route → canonical query service → page-specific PostgreSQL repository。
- 允许：page route → existing application/rules services for writes and pure export formatting。
- 禁止：route/server 堆业务 SQL；service 接收 `Application`；repository 依赖 HTTP/auth。
- 禁止：页面直接访问共享 read model、worker、queue、cache 或外部同步源。

## 跨页面清理结果

- `PendingInvoiceReadModelService`、source-version provider、repository/projection、manifest/query-owner 和 `search-pending`/invoice-lifecycle 页面链已删除。
- Search 独立索引与 `workbench_relation` 共享 distribution 保留给明确登记的消费者，但本页面不消费它们。
- `read_model.pending_invoice_*` 历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

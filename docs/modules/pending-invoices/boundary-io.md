# 待找发票模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：待找发票页面读取 `pending_invoice` scoped read model；规则、关联和收入状态写入只提交 canonical facts/version/audit，当前页面或后续页面访问再收敛精确 scope。
- 当前结论：rows、filter-options、export-preview 和 export 只允许通过 `PendingInvoiceReadModelService` freshness gate 读取 `pending_invoice` read model；候选、详情和导出格式化只接受明确输入 rows 或 scoped id，不再暴露同步全量 rows 直查入口。
- 旧代码删除结果：`Application._handle_api_pending_invoice_rows` 兼容入口、`PendingInvoiceQueryService.list_rows`、旧同步 `filter_options`、旧同步 `export_preview/export` 和旧 rows-only filter/sort helper 已删除；tests 不再引用旧 handler 或旧 query-service rows API。

## 职责边界

### 负责

- 待找发票列表、规则、筛选、导出和发票关联入口。
- `pending_invoice` read model 的 direction/filter/month scope。
- 与 search/invoice lifecycle 的投影联动。

### 不负责

- 不拥有发票生命周期源事实。
- 不直接维护关联台关系事实源。
- 不接受 bare `all` scope 重建。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选、方向、规则操作 | `PendingInvoicesPage.tsx`、`features/pendingInvoices/api.ts` | scope 必须落到 direction/filter/month；filter-options 只用一行 rows 做 freshness gate 且不计算未消费的页面 statistics，关系 source-version proof 必须在一个 SQL snapshot 中批量聚合全部命中月份，禁止逐月查询 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=pending-invoices`；以 active 银行流水及 collapsed relation 内全部银行成员为 independent canonical expected-set；折叠成员的方向/月必须分别回到 canonical 银行流水重算，不能继承主展示行方向，主行方向、成员金额/交易日/对方户名及 status 结构仍需一致；以 active bank 为 anchor 的 linked shared relation OA/bank/input/output-invoice typed edges，必须与 fresh `pending_invoice_rows.payload` summaries 按 `relation_case_id + member` 双向相等；所有证明在同一只读一致性快照执行，页面只消费结构化 integrity/freshness/queue 与有上限 issue samples，不直接读取审计表或触发修复 |
| 关联/规则写入 | pending invoice services | 普通写只提交规则版本、command/relation facts、收入状态覆盖与 audit，不写 `pending_invoice`、search 或 invoice-lifecycle dirty/outbox。响应可返回信息性的受影响月份/scope hints，但 freshness/barrier targets 为空；当前可见页立即重跑正常 GET，隐藏/未访问页在下次访问时由自己的 expected source-version gate 收敛。关联台撤回若方向不明确，只能保留 expense+income 两个月方向提示，禁止用绝对金额符号猜方向 |
| 关联台关系分发 | `WorkbenchRelationReadFacade` / `workbench_relation` read model | 待找发票只按银行流水 row id 读取 `linked_oa`、`linked_input_invoices`、`linked_output_invoices`、`group_ids` 等 relation distribution；不得自行从发票附件、OA payload 或关联台 raw payload 反推 OA。若 `workbench_relation` non-fresh，必须保持 refreshing/stale 状态而不是伪装 fresh。 |
| Worker 关系源端快路径 | `WorkbenchRelationReadModelRepositoryPort` | `search-pending` / `pending-invoice` projection 可通过 `list_active_workbench_relation_source_rows(...)` / `workbench_relation_source_summary_from_source(...)` 读取 active relation source rows/source summary，构造待找发票 relation context 与 source-version proof；待找发票 source fast path 必须请求成员源摘要，至少补齐银行金额、OA 申请人/项目和发票号码/供应商/金额，不能只用 relation row_ids/row_types 计算 `paid_invoiced` 状态却输出空展示字段；API expected-source gate 必须按当前 pending invoice rows 命中的月份和 row id 调同一个 source summary，不能再拿 `read_model.workbench_relation_scopes.source_versions` 和 source-fast-path 写入值比较；SQL owner 仍归 workbench-relations repository，下游不得直接读 relation 表，也不得把源端快路径用于页面 fresh payload 或关系写状态机。 |
| 导入/运行时派生范围 | `PendingInvoiceScopePlanner` | 从 `cost_statistics` 与 `bank_detail` 月份 scope 合并生成 `expense:all:<YYYY-MM>`、`income:all:<YYYY-MM>`、`income:cash_income:<YYYY-MM>`；没有可识别月份时只返回三类父 scope，不写 bare `all` |
| Refresh scope | `pending_invoice` manifest | `direction:filter_group[:YYYY-MM]`；bare `all` forbidden |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 待找发票 rows/summary/statistics | 前端页面 | fresh/status 可见；主 rows 响应附带全期间 `statistics` 与独立 `statistics_status`，按 `bank_transactions.summaries` 中唯一流水 ID 统计总流水、支出、收入、已找到/待找、无需开票、现金收入及 OA/进项/销项关联覆盖；统计忽略当前 direction/filter/date/keyword/sort/page。任一 pending-invoice child scope non-fresh 或完整方向 scope 缺失时 `statistics=null`，合法 fresh 空集才返回零；缺少/未知 read model status 保持 refreshing/non-fresh。所有 filter shard 共用 direction-wide 月份 dependency proof；filtered aggregate 必须保留当前方向的零行月份 proof，不能让合法空 `cash_income` 永久 mismatch；存在月 shard 时只聚合月 shard，旧父 scope metadata 不得参与并污染规则或 dependency 版本。若仅 Bank Detail/Workbench relation 的嵌套月份版本不同，rows 与 statistics gate 都只 enqueue 差异月份 shard；own schema 或规则版本变化才允许父 scope 展开全部月份。 |
| 页面 Audit 状态 | 标题附件 | 仅 integrity pass、freshness fresh、queue drained 且页面 read model 明确 fresh 才显示成功 |
| 规则保存结果 | API | 持久化 direction-owned 规则版本和审计；expense expected versions 不包含收入规则版本，income expected versions 不包含支出规则版本；不触发写时刷新 |
| 发票关联/收入状态写结果 | API/frontend | 返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys` 作为访问提示；`freshness_targets=[]`、`operation_barrier_targets=[]`，前端不得把响应中的旧 targets 恢复为写时 barrier |

批量导出的所有分页均使用内部 `include_statistics=false`，不读取、校验或透传页面标题统计，从而跳过与导出无关的统计 scope/dirty/outbox 聚合；每一页仍执行 rows read-model freshness、schema 与 source-version 检查。
| Dirty scope | runtime queue | 不允许无界全量 |

## 持久化与投影

- Read model：`pending_invoice`
- Projection：`scoped_incremental`
- Worker：`pending-invoice`，辅助 `search-pending`
- Query owner：`PendingInvoiceReadModelService`
- Repository owner：`PendingInvoiceReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/PendingInvoicesPage.tsx` |
| Frontend feature/components | `web/src/features/pendingInvoices/*`、`web/src/components/pendingInvoices/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` |
| Backend service | `pending_invoice_service.py`、`pending_invoice_read_model_service.py`、`pending_invoice_rules_application_service.py`、`pending_invoice_lifecycle_service.py`、`pending_invoice_status.py` |
| Repository / SQL | `pending_invoice_read_model_repository.py`、`search_pending_sql_projection.py`、`invoice_lifecycle_sql_projection.py` |
| Tests | `tests/test_pending_invoice*.py`、`web/src/test/PendingInvoices*.test.*`、`web/e2e/pending-invoices-*.spec.ts` |

## 依赖方向

- 允许依赖：invoice lifecycle policy/read facade、search projection、workbench relation read facade。
- 必须通过：PendingInvoiceReadModelService and rules application service。
- 禁止绕过：恢复已删除的 import/runtime `pending_invoice_scope_planner.py`、普通写 fan-out 或 bare all refresh；页面自行合成 invoice status。

## 测试与验证

- `tests/test_pending_invoice_service.py`
- `tests/test_pending_invoice_api.py`
- `tests/test_import_processing_service.py`
- `web/e2e/pending-invoices-fanout.spec.ts`
- `web/e2e/pending-invoices-filter-sort-flow.spec.ts`

## 当前缺口和删除条件

- 修改规则或 scope policy 时必须同步 manifest/scope tests。
- 已删除旧路径后仍需保持覆盖：expense/income 方向级版本、规则保存、关联、收入状态、导出严格 freshness、普通写零 downstream job，以及页面访问收敛。

## Canonical facts ownership

- Owned facts: `app.pending_invoice_manual_invoice_commands`。
- Shared facts: `app.invoices` 由 canonical invoice pool owner 管理；关系事实由 `workbench-relations` owner 管理。
- Allowed writes: pending invoice manual invoice command service、pending invoice application boundary。
- Allowed reads: `PendingInvoiceReadModelService`、transaction-scoped pending invoice query/detail/candidate services、manual command repository/read ports。
- Downstream outputs: canonical version/scope hints；`pending_invoice`、invoice-lifecycle、search、workbench-relation 由各自访问 owner 发现 mismatch 后输出精确 dirty scope。
- Forbidden paths: pending invoice 页面或 service 不得直接创建第二发票池、直接写 relation facts 或绕过 command 状态机。
- Old code deletion: manual invoice command snapshot fallback、direct invoice/relation write fallback、bare all refresh、旧 API handler 和同步 rows/filter/export 直查路径已关闭；migration/audit/rollback 工具保留不算污染。

# 进项发票使用情况模块边界与 I/O

日期：2026-07-07

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：进项发票使用情况通过 `input_invoice_usage` read model 查询；filter-options 和 OA reverse preview 通过 read model repository 窄端口读取；筛选字段/排序解析由 `input_invoice_usage_query_contract.py` 纯合同模块提供；OA 反提本地 batch 状态与真正影响 rows 的 relation/evidence 写入分离。
- 当前缺口：OA reverse、applicant credentials 和 workbench relation 依赖交织，变更时必须同步权限和 freshness。
- 旧代码删除条件：API route、export 和 OA reverse preview 不保留 live fallback；缺失 read model 时只返回 refreshing/业务错误并入队刷新；read route 只接收明细/规则窄 callable，不持有完整 `InputInvoiceUsageQueryService`；fresh gate 不接收 `InputInvoiceUsageQueryService`，不得保留 `live_query` 标记，architecture guard tests 覆盖旧符号不得回归。

## 职责边界

### 负责

- 进项发票使用情况页面列表、筛选、明细、OA 反提和使用规则。
- `input_invoice_usage` scoped read model。
- 与 invoice usage collection worker 的 event 合同。
- rows 聚合单位必须是 confirmed/linked 配对关系组优先；同一配对关系组内多张进项发票、多条 OA 或多条流水只能生成一行，行内展示合计和 `+N` 明细。没有 confirmed relation group 的发票才按发票 identity 聚合兜底。
- `InputInvoiceUsageQueryService` 必须显式接收支付状态规则 provider 或上层 lifecycle policy；生产 `Application` 和 SQL projection 必须注入 app-settings backed provider，`InvoiceLifecyclePolicy` 不提供进项支付规则默认值，生产模块不得保留静态支付规则 provider，禁止静默回退静态规则污染支付状态链路；规则设置完整保存时以提交的 `conditions` 为准，读取历史配置时才补默认条件。
- OA reverse evidence detected 后通过 relation command 写入真正影响 rows 的事实，并返回 `input_invoice_usage` write target envelope；创建 OA 草稿、撤回本地草稿绑定、手动确认 submitted/not_submitted 只修改本地 batch 状态，不污染 rows read model。

### 不负责

- 不拥有 OA 登录/凭证的底层认证事实。
- 不直接维护关联台关系事实源。
- 不处理销项发票收款业务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/明细 | `InputInvoiceUsagePage.tsx`、`features/inputInvoiceUsage/api.ts` | rows/filter/export/relation-details 进入 read model service/fresh gate；invoice/bank/OA detail 和 payment rules 通过 route 显式注入的窄 callable 调用 |
| Filter options | `InputInvoiceUsageReadModelFreshGateService.filter_options(...)` | 生产路径调用 `InputInvoiceUsageReadModelRepositoryPort.list_input_invoice_usage_filter_options(...)`，由 PostgreSQL 结构化列聚合 enum options；筛选字段配置和 query 解析来自 `input_invoice_usage_query_contract.py`；禁止为 options 拉齐全部 row payload 或依赖 `InputInvoiceUsageQueryService` 私有方法 |
| OA reverse preview 读路径 | `InputInvoiceUsageOaReverseService.preview(...)` | 当前筛选走 `InputInvoiceUsageReadModelFreshGateService.rows(...)`；显式发票选择走 `rows_by_invoice_ids(...)` 和 repository `list_input_invoice_usage_rows_by_invoice_ids(...)`；非 fresh 或 repository 缺失时返回 refreshing 业务错误并入队刷新，不得接收 `InputInvoiceUsageQueryService` 或回退 live scan |
| OA reverse 写操作 | `input_invoice_usage_oa_reverse_service.py` | 必须带 OA applicant context 和审计 |
| OA reverse target envelope | `InputInvoiceUsageOaReverseService.batch_payload(..., include_write_targets=True)` | 仅用于 evidence detected / relation-impacting 写入；从 batch invoice display rows 提取 invoice month；无月份时退回 `all`，并返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Refresh scope | `input_invoice_usage` manifest | month or `all`；`all` 是 fan-out command。显式运维 `force_refresh=true` 必须传播到 month shard 并绕过 unchanged fast path，重新生成并覆盖目标 scope rows；不得写 canonical invoice 或 relation facts |
| Relation upstream freshness | `workbench_relation` month scope | projection 在读取 relation source versions、执行 unchanged-scope 判断或写 rows 前必须先通过 fresh gate；non-fresh 抛出已登记 dependency-not-fresh 错误交 worker defer，禁止与 relation refresh 并行落盘旧版本 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 使用情况 rows/details | 前端页面 | fresh/status 可见；confirmed relation group 是优先行边界，组内发票/OA/流水各显示一次合计与 `+N`，未 linked 发票按 identity 兜底；all scope 读取多个 month shard 时按 read model row id 去重；rows summary 的 `invoiceCount` 按唯一进项发票 ID 统计并驱动标题右侧 `进项票 N`，`pagination.total` 仍是表格行数/配对组行数；标题统计表示全量进项票数，不随当前 keyword/filter/month/sort 的表格筛选结果变化 |
| 页面 Audit icon | AppHealth operations audit API | admin-only；active canonical 进项发票（含 collapsed members）是 independent expected-set，成员/金额/scope 与共享 relation 的受影响月份双向 edge 必须在同一只读一致性快照中相等；只有结构化 integrity=pass、freshness=fresh、queue=drained 且 database snapshot 已启用才显示成功，unknown 不得伪装 fresh，问题数显示为 sample |
| 支付状态 | rows/filter/export/read model | 只消费 `workbench_relation` distribution 中 confirmed/linked 关系；多 OA/多流水用 linked 合计与发票价税合计比对；无 active relation 或历史 candidate 兼容值不参与 `已付款` 判断 |
| OA reverse 本地状态 | API/OA drawer | draft/staged/submitted/not_submitted 只落 `app.input_invoice_usage_oa_reverse_batches`，前端立即释放按钮；不等待 `input_invoice_usage` operation barrier |
| OA reverse relation 结果 | Workbench relation / API / operation barrier | evidence detected 写入 relation 后触发 dirty scope，并返回 `read_model_key=input_invoice_usage`、`scope_key=<invoice month>` |
| Dirty scope | runtime queue | `input_invoice_usage.read_model.refresh` |

## 持久化与投影

- Read model：`input_invoice_usage`
- Projection：`scoped_incremental`
- Worker：`invoice-usage-collection`
- Query owner：`InputInvoiceUsageReadModelService`
- Repository owner：`InputInvoiceUsageReadModelRepositoryPort`
- OA reverse preview hot path：`read_model.input_invoice_usage_rows.invoice_id` 定向读取；`0094_input_invoice_usage_oa_reverse_preview_hot_path.sql` 维护 `(invoice_id, generated_at desc)` 索引。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/InputInvoiceUsagePage.tsx` |
| Frontend feature/components | `web/src/features/inputInvoiceUsage/*`、`web/src/components/inputInvoiceUsage/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`、`routes_input_invoice_usage_oa_reverse.py` |
| Backend service | `input_invoice_usage_service.py`、`input_invoice_usage_query_contract.py`、`input_invoice_usage_oa_reverse_service.py`、`input_invoice_usage_payment_rules.py`、`input_invoice_usage_read_model_*` |
| Repository / SQL | `input_invoice_usage_read_model_repository.py`、`invoice_usage_collection_sql_projection.py`、`postgres_repositories/input_invoice_usage_oa_reverse.py`、`postgres_repositories/read_models.py` |
| OA dependencies | `oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py`、`postgres_repositories/oa_applicant_credentials.py` |
| Tests | `tests/test_input_invoice_usage*.py`、`web/src/test/InputInvoiceUsage*.test.*`、`web/e2e/input-invoice-*.spec.ts` |

## 依赖方向

- 允许依赖：OA credential provider, workbench relation read facade, invoice usage projection。
- 必须通过：InputInvoiceUsage service/read model service。
- 禁止绕过：service 直接读取 HTTP cookie/header；页面绕过 fresh gate。

## 测试与验证

- `tests/test_input_invoice_usage_api.py`
- `tests/test_input_invoice_usage_read_model_fresh_gate_service.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_input_invoice_usage_oa_reverse_service.py` 覆盖 OA reverse 本地状态不触发 read model target、evidence detected 才返回 target envelope，并覆盖 preview 通过 read model/fresh gate 读取、不回退 live query。
- `web/e2e/input-invoice-usage-flow.spec.ts`

## 当前缺口和删除条件

- OA reverse 变更必须覆盖权限、凭证、审计和 read model recovery。

## Canonical facts ownership

- Owned facts: `app.input_invoice_usage_oa_reverse_batches`。
- Allowed writes: input invoice usage OA reverse service、明确 application/UoW boundary。
- Allowed reads: input invoice usage application/query services、OA reverse query ports。
- Downstream outputs: input_invoice_usage、invoice_lifecycle、workbench_relation dirty scopes 或 owner producer 输出。
- Forbidden paths: OA reverse 工具不得绕过 owner 状态机；read model rows 不得反向成为 reverse batch 事实。
- Old code deletion: 旧 OA reverse direct-write path 和 snapshot fallback 必须删除；migration/audit/rollback 工具保留不算 closure。

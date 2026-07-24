# 进项发票使用情况模块边界与 I/O

日期：2026-07-22

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
- OA reverse evidence detected 后只通过 relation command 写入真正影响 rows 的 canonical relation；新建 batch、创建/撤回草稿和 submitted/not_submitted 状态只写本模块 batch/version/audit。普通 Drawer 操作不直接 enqueue rows 或标题统计；当前页面保存后重跑正常 GET，由 relation/batch generation mismatch 在访问边界精确收敛。

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
| OA reverse scope hints | `InputInvoiceUsageOaReverseService.batch_payload(..., include_write_targets=True)` | 从 batch invoice display rows 提取受影响 invoice month，作为 `affected_scope_keys` / `read_model_scope_keys` 信息性提示；所有普通 batch/evidence 状态写返回空 `freshness_targets` / `operation_barrier_targets`，不得无月份退回写时 `all` fan-out |
| Refresh scope | `input_invoice_usage` manifest | month or `all`；`all` 是 fan-out command。显式运维 `force_refresh=true` 必须传播到 month shard 并绕过 unchanged fast path，重新生成并覆盖目标 scope rows；不得写 canonical invoice 或 relation facts |
| Relation upstream freshness | `workbench_relation` month scope | projection 执行 unchanged 判断或写 rows 前必须先通过 fresh gate；embedded proof 按本月 canonical 进项发票 IDs 计算，只统计实际触达这些 IDs 的 active payment relation，并排除只服务 Workbench/Turnover/Cost 的 `turnover_manual_closure`。non-fresh 抛出已登记 dependency-not-fresh 错误交 worker defer，禁止并行落盘旧版本 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 使用情况 rows/details/statistics | 前端页面 | fresh/status 可见；confirmed relation group 是优先行边界，组内发票/OA/流水各显示一次合计与 `+N`，未 linked 发票按 identity 兜底；all scope 读取多个 month shard 时按 read model row id 去重。主 rows 响应的 `statistics` 从完整 `input_invoice_usage` 投影按唯一发票成员 ID 计算发票、OA/流水关联、付款及补集，并补充本模块 OA reverse 批次数；忽略当前 keyword/filter/month/sort/page。`pagination.total` 仍是表格行数/配对组行数；任一 child scope non-fresh 时统计不可用，合法 fresh 空集才返回零。 |
| 页面 Audit icon | AppHealth operations audit API | admin-only；active canonical 进项发票（含 collapsed members）是 independent expected-set，成员/金额/scope 与共享 relation 的受影响月份双向 edge 必须在同一只读一致性快照中相等。页面 freshness 与 Audit 共用 consumer-semantic relation 边界：每月 proof 只统计实际触达该月进项发票 IDs 的 active payment relation，并排除 `turnover_manual_closure`；纯银行或仅销项关系变化不得令本页 mismatch。只有结构化 integrity=pass、freshness=fresh、queue=drained 且 database snapshot 已启用才显示成功。 |
| 支付状态 | rows/filter/export/read model | 只消费 `workbench_relation` distribution 中 confirmed/linked 关系；多 OA/多流水用 linked 合计与发票价税合计比对；无 active relation 或历史 candidate 兼容值不参与 `已付款` 判断 |
| OA reverse 本地状态 | API/OA drawer | draft/staged/submitted/not_submitted 只落 `app.input_invoice_usage_oa_reverse_batches`，canonical commit 后立即释放按钮并让当前页正常 GET；不在写响应链 enqueue 统计或等待 barrier |
| OA reverse relation 结果 | Workbench relation / API | evidence detected 写入 canonical relation 后返回月份 hints；`input_invoice_usage` 与 relation distribution 均由被访问 owner 自行检测版本差异并收敛，不从 Drawer fan-out |
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
- `tests/test_input_invoice_usage_oa_reverse_service.py` 覆盖全部 OA reverse 状态和 evidence detected 都不触发 write-time read model target，同时覆盖 preview 通过 read model/fresh gate 读取、不回退 live query。
- `web/e2e/input-invoice-usage-flow.spec.ts`

## 当前缺口和删除条件

- OA reverse 变更必须覆盖权限、凭证、审计和 read model recovery。
- 已删除标题计数的 `page_size=1` 二次请求；标题统计只能消费 rows 主响应，禁止恢复独立 title-total I/O。
- `input_invoice_usage_statistics_schema_version` 负责生产旧 scope 的统计元数据回填；source version 相同但缺少合法统计元数据时也必须重建，不能走 unchanged skip。批量导出的所有分页均传 `include_statistics=false`，不重复读取、校验或透传页面标题统计；每一页仍执行 rows freshness、schema 和 source-version gate。
- 默认 `month=all` 只表示页面查询视图，不是 refresh 命令。fresh gate 通过 `input_invoice_usage_scope_source_versions(...)` 一次读取有效月份 shard 的 base/source status，再通过 `input_invoice_usage_relation_source_versions(...)` 批量比较每月 consumer-semantic canonical payment relation proof；该 proof 与共享 distribution 一致排除 `turnover_manual_closure`，只 enqueue mismatch 的具体月份。具体月 rows 可保持 fresh，跨月标题统计独立返回 `statistics_status=refreshing` 并只补投其 stale shard；禁止失败回退 `input_invoice_usage:all`。
- `input_invoice_usage_scope_source_versions(...)` 的同一 set-based SQL 还必须把 canonical 进项发票月份库存纳入 scope inventory，并按月返回发票数量与 `max(updated_at)`。projection 发布相同 proof；未关联的新发票、新月份、删除或更新都会在下一次页面访问时只阻断真实变化月份。不得再用静态规则版本或 relation proof 代替 canonical 发票完整性，也不得由 import writer 恢复跨页面 fan-out。销项发票集合使用同一共享合同。
- 本次 canonical inventory 合同版本为 `input-invoice-usage:v5-canonical-invoice-inventory`；旧 scope 缺少 proof 必须重建，不得沿用 v4 relation-only vector。
- `input_invoice_usage_scope_source_versions(...)` 必须在同一 SQL statement snapshot 内同时读取 scope dirty 状态和同 scope active outbox event。已有 `pending|processing` event 的阻塞月份只返回 `refreshing`，不得再次进入 enqueue candidates；页面下一轮 normal GET 再观察该 event 发布后的 fresh proof。
- 标题统计 freshness 与 rows 共用 durable dirty scope、已发布 metadata 和 source-version proof。投影已经发布且 dirty scope 已完成后，worker 正在收尾的 outbox event 不得再次把统计降级为 refreshing，也不得由页面轮询创建下一代相同月份任务；outbox `pending/processing` 只用于 active enqueue coalescing 和运维可观测性。
- `oa_reverse_batch_count` 是 owned batch 表的当前小型 canonical 聚合，只在标题统计返回前 overlay；不再写入每个月份 scope metadata，也不参与月 shard source version。因此 OA reverse Drawer 保存不会令全部历史月份 stale。月度统计仍由 worker 原子发布；overlay 不改变 rows freshness。
- 关联详情抽屉从当前行 `invoice.issueDate` 传递 `month`。detail miss 或 repository unavailable 只刷新该月份；缺少合法月份时 fail closed，不猜测性 enqueue `all`。

## Canonical facts ownership

- Owned facts: `app.input_invoice_usage_oa_reverse_batches`。
- Allowed writes: input invoice usage OA reverse service、明确 application/UoW boundary。
- Allowed reads: input invoice usage application/query services、OA reverse query ports。
- Downstream outputs: owner batch/relation version与受影响月份 hints；input-invoice-usage、invoice-lifecycle、workbench-relation dirty scope 只由对应访问 owner 输出。
- Forbidden paths: OA reverse 工具不得绕过 owner 状态机；read model rows 不得反向成为 reverse batch 事实。
- Old code deletion: 旧 OA reverse direct-write path 和 snapshot fallback 必须删除；migration/audit/rollback 工具保留不算 closure。

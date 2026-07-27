# 批量账务模块维护入口

- Module key：`batch-accounting`
- 类型：页面模块
- Route：`/batch-accounting`
- Page key：`batch-accounting`

## 修改前必读

- `docs/product-specs/reconciliation-and-workbench.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/architecture/module-boundaries/canonical-facts.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/workbench-relations/boundary-io.md`
- `docs/modules/canonical-facts/boundary-io.md`
- `docs/modules/permissions-and-audit/boundary-io.md`

## 代码入口

- `web/src/pages/BatchAccountingPage.tsx`
- `web/src/features/batchAccounting/api.ts`
- `web/src/features/batchAccounting/types.ts`
- `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
- `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/batch_accounting.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/app/server.py`：仅依赖组装和 HTTP 接线

## 当前职责

批量账务页面把符合条件的银行流水与已完成的日常报销 OA 主单人工建立正式关系，并支持撤回。页面没有独立 read model，也不读取 Workbench active generation 或 `workbench_relation` projection：

- 浏览器只访问 `/api/batch-accounting` 页面专属 API。
- `BatchAccountingService` 负责业务组合、金额校验、候选资格、冲突和 CAS 语义。
- `PostgresBatchAccountingQueryRepository` 在一个显式 `REPEATABLE READ / READ ONLY` 快照中读取 PostgreSQL canonical facts。
- 正式关系只认 `app.workbench_pair_relations` 中 `status='active'` 的事实；已提交列表还要求 `relation_mode='batch_accounting'`。
- submit/withdraw 继续委托 `WorkbenchRelationCommandService`，页面 repository 不写关系表。

## 列表合同

- `GET /api/batch-accounting` 始终返回 `summary`、`bank_rows`、`oa_rows`、`relations_by_bank_row_id` 和 `pagination`。
- 响应不返回 `read_model_status`、`source_versions`、`refresh_enqueued`、refresh targets 或 operation barrier targets；页面只保留 loading、empty 和 error 状态。
- 银行和 OA 使用独立服务端分页，页大小上限 200；不得先读全量再在 Python 或浏览器分页。
- `oa_search` 在 PostgreSQL 候选查询中执行，并与 OA count、分页使用同一筛选。
- `unsubmitted` 直接查询指定年份、对方户名为“批量账务集中处理”、支出且尚无 active relation 的 canonical 银行流水；OA 直接查询已完成的日常报销主单，不按年份过滤，且没有包含银行流水的 active relation。
- OA 已有发票关系或其它不含银行流水的关系时仍可成为候选；附件发票只按当前可见/选中的 OA IDs 查询。
- `submitted` 直接分页查询带指定年份 canonical 银行成员的 active batch-accounting relations，再用一次批量成员查询补齐 OA/发票详情。
- `summary.submitted_count` 按 relation 中 canonical 银行成员的年份统计，支持跨月关系。

## 写合同

- submit 只读取指定 `bank_row_id + oa_row_ids` 的 canonical 银行、OA 和附件发票上下文，不读取整页或整年 payload。
- 写前检查银行资格、OA 日常报销资格、金额差异说明、银行/OA active relation 冲突和 expected version。
- OA 已有关联发票但未关联银行时允许提交；银行或 OA 已处于包含银行的 active relation 时拒绝。
- submit 使用 `WorkbenchRelationCommandService.confirm_relation(...)`，并记录 `relation_mode=batch_accounting`、row types、金额校验、跨月 `affected_scope_keys` 和 metadata。
- withdraw 只允许 active batch-accounting relation，要求撤回原因并检查 expected version，最终调用 command service 的 canonical cancel。
- 写成功后当前页面恰好重新执行一次普通 GET；不轮询、不等待 read model、不请求 operation barrier。重新 GET 失败时保留写成功事实并提示用户手动刷新。

## 查询与性能边界

- 未提交 GET 最多 5 条数据库语句（包括 transaction isolation 设置）：summary、银行页、OA 页、当前 OA 附件发票。
- 已提交 GET 最多 4 条数据库语句（包括 isolation 设置）：summary、关系/银行页、关系成员。
- submit 上下文最多 4 条数据库语句（包括 isolation 设置）：银行、OA、选中 OA 附件发票。
- 禁止 12 月循环、逐 scope proof、全 Workbench payload、全量附件扫描、逐 row relation lookup、N+1 和递归大 JSON copy。
- 只有真实 PostgreSQL `EXPLAIN` 或端点测量证明需要时才新增索引；本模块不新增缓存、worker、queue、materialized view 或依赖。

## 影响面清单

| 改动点 | 必查影响 |
| --- | --- |
| 候选口径、筛选、双分页 | canonical bank/OA 查询、summary、空集、跨年 OA、前端交互 |
| submitted 关系/详情 | active batch relation、canonical member detail、跨月 relation、withdraw |
| API DTO/错误码 | route contract、frontend mapper、旧 freshness 字段不得恢复 |
| submit/withdraw | command owner、权限、审计、CAS、冲突、写后一次 GET |
| canonical 表或 identity | canonical-facts、workbench-relations、reconciliation-workbench 上下游 |
| 性能 | 固定查询次数、服务端分页、页面最大 200 行 |

## 跨页面清理结果

旧 Workbench generation reader、registry、worker 和 App Status 配置已删除。本页面只读 canonical facts/active relations；仍保留的 `workbench_relation` 是其它明确登记消费者的共享 distribution，不进入本页面读链。历史 migration/表暂留作回滚证据。

## 本目录文件

- `boundary-io.md`：模块职责、I/O、文件范围和依赖方向。
- `state-machine.md`：业务与页面可观察状态。
- `tests.md`：七类测试覆盖和验证入口。
- `e2e-spec.md`：浏览器业务验收合同。
- `e2e-coverage.md`：Spec ID 到证据映射。
- `implementation-notes.md`：提炼后的决策、验证和 HANDOFF。

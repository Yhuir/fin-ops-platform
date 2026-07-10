# 外部往来款管理模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：外部往来款页面读取 `turnover_ledger` read model；写操作通过 write facade/UoW/adapters 进入 scoped dirty projection。
- 当前闭环：read path 由 `TurnoverLedgerApiRoutes` route owner 进入 `TurnoverLedgerQueryService` / read model；write path 由 request-boundary facade 进入 `TurnoverLedgerWriteFacade` / UoW / explicit adapters；refresh producer 只负责通过 `ReadModelRefreshGateway` enqueue，不再暴露 direct clear I/O。
- 旧代码删除状态：`TurnoverLedgerReadFacade` app 转发壳、`TurnoverLedgerRelationMutationInvalidationLegacyAdapter`、`Application._after_turnover_relation_mutation(...)` 与 refresh producer `clear_best_effort()` 已删除；provider-backed 生产投影不再在 `BankTransactionTagReadFacade` 之后逐笔回读 legacy `category_service.get(...)`；边界 guard 防止恢复。

## 职责边界

### 负责

- 外部往来款列表、确认关联、撤回、导出、余额/账期查询。
- `turnover_ledger` read model。
- 与银行流水、关联台关系事实源之间的 write/read adapter。

### 不负责

- 不拥有银行流水源事实。
- 不直接维护 workbench relation 表。
- 不绕过 write UoW 直接更新 turnover source versions。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/筛选 | `TurnoverLedgerPage.tsx`、`features/turnoverLedger/api.ts` | 进入 `TurnoverLedgerApiRoutes` route owner，再由 `TurnoverLedgerQueryService` 读取 read model |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?domain=turnover_ledger`；canonical turnover relations 与 ledger extras 必须双向覆盖 read model，金额/状态/关系类型/银行成员和利息扩展字段必须重算一致，并要求共享 relation 双向 edge equality 与只读一致性快照；只消费结构化 audit status 与 issue samples，不进入本模块写 facade |
| 确认/撤回写操作 | write facade/UoW | 已知 affected months 的写路径触发 turnover/workbench/workbench_relation/cost/search affected month scopes；未知月份例外才允许 `all` fan-out |
| Workbench relation requirement | `TurnoverLedgerWorkbenchPairPort` | 创建 `turnover_manual_closure` 时必须写入 `requires_oa`、`requires_invoice`、`paired_requirement_source`、`paired_requirement_version`；这些字段是关联台分区的唯一输入，不能由关联台查询当前设置兜底 |
| Refresh scope | `turnover_ledger` manifest | month or `all`；`all` 是 fan-out command，不是普通写操作默认 scope。`all`/month scope 在 own source_versions 未变化、仅 Workbench relation source_versions 追平时，可以从现有 rows 重套 relation context 后保存，避免 relation-version 追平重建整本台账。`all` 查询由月度/行级 rows 拼接时允许 mixed row source_versions，freshness 以 repository 返回的 durable `refresh_status` 为准；dirty scope 非 fresh 时仍必须返回 refreshing/stale |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 外部往来款 rows/summary | 前端页面 | query gateway 后 fresh/status |
| 页面 Audit 状态 | 标题附件 | unknown/non-fresh 不得显示 Fresh；样本截断必须显式呈现 |
| 写操作结果 | API/frontend operation barrier | 可审计、幂等或有版本保护；返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Workbench active relation | `workbench-relations` | 只通过 `WorkbenchRelationCommandService` 写入/撤回；`turnover_manual_closure` relation metadata 明确声明 OA/发票 requirement。metadata 缺失的旧关系必须 fail closed，等待规则保存同步链路升级 |
| Dirty scope | runtime queue | `turnover_ledger.read_model.refresh` |
| 导出 | 用户下载 | 复用查询权限和筛选 |

## 持久化与投影

- Read model：`turnover_ledger`
- Projection：`partitioned_scoped_incremental`
- 生产投影必须信任 `BankTransactionTagReadFacade` 输出的 fresh bank-detail tag 事实；只有无 provider 的 legacy/local 路径才允许回退 `BankTransactionCategoryService` snapshot。禁止在 provider-backed worker hot path 逐笔读取旧 category service。
- `all` 聚合查询不得要求所有行级 source_versions 完全一致；按月增量 worker 刷新会让不相关月份保留旧 provenance。Query owner 只能在 repository 标记 mixed row versions 且 durable dirty scope 为 fresh 时把 all-view 判为 fresh，不能绕过 dirty scope。
- Worker：`turnover-ledger`
- Query owner：`TurnoverLedgerQueryService`
- Repository owner：`TurnoverLedgerReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` |
| Frontend feature/components | `web/src/features/turnoverLedger/*`、`web/src/components/turnoverLedger/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` |
| Backend service | `turnover_ledger_service.py`、`turnover_relation_service.py`、`turnover_ledger_query_service.py`、`turnover_ledger_write_facade.py`、`turnover_ledger_write_uow.py`、`turnover_ledger_write_adapters.py` |
| Repository / SQL | `turnover_ledger_read_model_repository.py`、`turnover_ledger_sql_projection.py` |
| Worker/read model | `turnover_ledger_read_model_refresh.py`、`turnover_ledger_read_model_refresh_producer.py`、`turnover_ledger_source_versions.py` |
| Tests | `tests/test_turnover_*.py`、`web/src/test/TurnoverLedger*.test.*`、`web/e2e/turnover-ledger-flow.spec.ts` |

## 依赖方向

- 允许依赖：bank row version provider, workbench relation adapters, read model query gateway。
- 必须通过：TurnoverLedgerQueryService for reads, write facade/UoW for writes。
- 禁止绕过：直接操作数据库确认/撤回；API 返回 stale payload as fresh。

## 测试与验证

- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_uow_contract.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `web/src/test/TurnoverLedgerApi.test.ts`
- `web/src/test/TurnoverLedgerPage.test.tsx`
- `web/e2e/turnover-ledger-flow.spec.ts`

## 当前缺口和删除条件

- 本地模块化边界已 close；后续若新增写入口，必须先明确 affected scopes，不能恢复 default direct clear、route forwarding shell 或 legacy invalidation adapter。
- 方式 B 可控样本验证优先通过业务操作恢复；若生产样本没有业务恢复路径，可按用户批准的 bounded DB restore protocol 使用精确 predicate 恢复到操作前快照，不得通过 DB 伪造 read model freshness。

## Canonical facts ownership

- Owned facts: `app.turnover_relations`、`app.turnover_relation_events`、`app.turnover_ledger_extras`。
- Shared facts: relation facts 由 `workbench-relations` owner 管理；银行分类 facts 由 `bank-details` owner 管理。
- Allowed writes: turnover write facade、write UoW、turnover relation service。
- Allowed reads: turnover query service/read ports、turnover ledger read model boundary。
- Downstream outputs: turnover_ledger、workbench_relation、workbench、cost、search dirty scopes 或 owner producer 输出。
- Forbidden paths: legacy fallback facade 不得进入 production normal write path；不能直接写 workbench relation 或 bank category facts；不能从银行明细或 Application helper 直接清 `turnover_ledger` read model。
- Old code deletion: app read forwarding facade、relation mutation legacy invalidation adapter、producer direct clear I/O、direct relation fallback 和 snapshot bank-row source fallback 已删除；migration/audit/rollback 工具保留不算 closure。

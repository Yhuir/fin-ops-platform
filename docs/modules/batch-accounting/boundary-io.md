# 批量账务模块边界与 I/O

日期：2026-07-05

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：批量账务页面通过 BatchAccounting service 操作批量关系和账务候选，关系事实写入必须走 workbench relation 边界。
- 当前缺口：无本地模块化 closure blocker。批量账务不拥有独立 read model，依赖 `workbench_relation` read/write 和 runtime worker fan-out 是设计边界，不作为 partial 原因。
- 旧代码删除状态：旧 server.py 批量账务入口不再承载业务逻辑；所有关系写入走 command service；submit/withdraw route 不再调用旧 pair relation persist、snapshot restore、旧 lifecycle 或旧 workbench read model persist 链路；已提交 bucket 不再回退 12 个月 `list_by_month` 扫描；service-level `repair_legacy_case_id_collisions(...)` 旧修复入口已删除并由静态 guard 防回归。

## 职责边界

### 负责

- 批量账务页面、批量选择、批量关系操作和账务候选展示。
- 调用 workbench relation 事实源完成关系写入。
- 通过 workbench relation command repository 触发相关 read model dirty/outbox fan-out。
- 定义右侧 OA 候选：日常报销 OA 主单，且没有关联银行流水；仅发票关系或无流水候选关系不排除该 OA，不再按 OA 年份过滤。

### 不负责

- 不拥有 workbench relation 表。
- 不直接维护 bank/invoice/turnover 源事实。
- 不直接写 read model projection。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面批量选择/操作 | `BatchAccountingPage.tsx`、`features/batchAccounting/api.ts` | 进入 batch accounting API/service |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?page=batch-accounting`；页面直接消费 filtered shared relation groups，不拥有第二 read model；active canonical `special_metadata.source=batch_accounting` case set 与 linked group logical case set 必须双向相等，canonical `relation_mode` 必须为 `batch_accounting` 并与 group payload mode/source/special metadata 一致，不能误与表示 OA/银行组合形态的 `relation_kind` 比较；全部成员 edge 由 canonical/shared typed-edge equality 证明，所有检查在只读一致性快照执行；与批量提交/撤回 command 隔离，不触发 relation 或 read model 写入 |
| 批量账务候选 payload | Workbench SQL active read model，fallback 为 Workbench payload builder | 未提交 GET 列表优先走 `load_batch_accounting_workbench_payload(bank_year=...)`；该全量候选读口只服务列表，不得进入提交 command 热路径 |
| 提交 command 窄 payload | Workbench SQL active read model | `POST /api/batch-accounting/submit` 必须优先走 `load_batch_accounting_submit_workbench_payload(bank_year, bank_row_id, oa_row_ids)`，只读取本次选中银行流水、OA 主单和这些 OA 的附件发票；禁止为单次提交扫描整年银行/OA/发票候选 |
| 已提交银行列表 payload | Workbench SQL active read model | `bucket=submitted` 的银行行上下文优先走 `load_batch_accounting_submitted_bank_workbench_payload(bank_year)`，只读取批量账务银行行；OA/发票明细来自 relation DTO，不再用整页候选 payload 补齐 |
| workbench row context | `BatchAccountingService._build_workbench_row_context` | 只解析 row/index/invoice links，不读取整页 relation distribution |
| list context | `BatchAccountingService._build_list_context` | 仅列表读取使用，先构造 Workbench row context，再通过候选级 relation distribution 产出 eligible bank/OA |
| unsubmitted relation context | `BatchAccountingService._context_with_candidate_relation_distribution` | 未提交列表只把批量账务银行候选和日常报销 OA 候选传入 `workbench_relation` facade；禁止把 Workbench 全量 open OA 当作 relation lookup 输入 |
| submitted relation count | `WorkbenchRelationReadFacade.count_batch_accounting_relations_by_year` | 未提交列表 summary 只读取年份级 batch-accounting relation count；不能为了 `submitted_count` 扫描 12 个月完整 relation DTO |
| submitted relation DTO | `WorkbenchRelationReadFacade.list_batch_accounting_relations_by_year` | 已提交 bucket 需要关系明细时，必须一次读取年份内 batch-accounting relation groups，并透出 freshness/status；缺少年份级 reader 时 fail closed 为 `read_model_status=unavailable`，禁止回退到 12 个月循环读取污染已提交页加载 |
| submit context | `BatchAccountingService._build_submit_context` | 仅提交使用，禁止读取整页 relation distribution；写前 active relation 冲突只通过 command service 按本次 row ids 查询，不再把 relation read model freshness 作为普通写阻断 |
| 关系写入请求 | `BatchAccountingService` | 必须委托 workbench relation command boundary。PostgreSQL 运行态必须通过 durable `PostgresWorkbenchRelationRepository` load/save `app.workbench_pair_relations` 与 history；禁止只使用进程内 `WorkbenchPairRelationService` snapshot。 |
| affected scope keys | `BatchAccountingService` | submit 必须基于本次银行/OA/附件发票 row payload 日期输出真实 `affected_scope_keys` 并写入 relation `special_metadata`；withdraw 优先读取 metadata，旧关系缺 metadata 时必须用 SQL 窄 submit context 反查 row 日期；没有窄 loader 时不能退回全量 Workbench loader，只能按 relation month/all fallback；只有完全无法解析具体月份时才允许回退 `all` |
| read model fan-out | workbench relation command repository | route 不再拥有 batch relation fan-out；command repository 保存 relation 时按 relation payload / `affected_scope_keys` 触发 `workbench_relation`、`workbench` 和下游 read model dirty/outbox。禁止 route 重新调用 duplicate derived lifecycle、`_schedule_workbench_read_model_persist` 或旧 pair persist。 |
| OA 候选事实 | Workbench active read model + `workbench_relation` read facade | 不接收 OA 年份；“没有流水”表示 relation distribution 中该 OA 没有 `linked_bank_transactions`，仅发票关系或无流水候选关系仍可进入批量账务右侧 OA 栏 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 批量账务操作结果 | 前端页面 | 返回成功/失败、受影响对象、`affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`。提交/撤回 command 成功后，后置 barrier/reload 只影响读侧收敛提示，不能把 command 成功改写成失败。`affected_months`/`affected_scope_keys` 必须优先是具体月份集合，不得无条件包含 `all`。撤回语义是通过 relation command repository 取消当前 batch relation，并记录 `withdraw_link` history；不得走旧 restore-style withdraw 或进程内 fallback。 |
| 页面 Audit 状态 | 标题附件 | integrity/freshness/queue 分栏判断；问题数量只显示 sample |
| Relation dirty scopes | workbench relation/read model | 不直接写下游 payload |
| 关联台已配对展示 | `workbench` active generation / `WorkbenchCandidateGroupingService` | active `relation_mode=batch_accounting` 且 `special_metadata.source=batch_accounting` 的 row-set 是已确认批量账务关系；即使行级 relation code 是 `batch_accounting` 而不是旧 `fully_linked`，也必须进入 paired 区，不得被 `existing_case_candidate` open 旧候选链路接管 |
| Audit/result | audit/job status | 重要批量操作可追踪 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Downstream read model：主要影响 `workbench_relation` 和其下游 fan-out；`workbench` active generation 必须把 batch-accounting active relation 投影为 paired group。
- Worker：依赖 runtime worker registry 中的 workbench relation/read model workers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BatchAccountingPage.tsx` |
| Frontend feature | `web/src/features/batchAccounting/api.ts`、`types.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_batch_accounting.py`、历史 `server.py` |
| Backend service | `backend/src/fin_ops_platform/services/batch_accounting_service.py` |
| Relation dependency | `workbench_pair_relation_service.py`、`workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Worker fan-out | `workbench_relation_command_service.py`、`postgres_repositories/workbench_relation.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |

## 依赖方向

- 允许依赖：workbench relation command/read facade。
- 必须通过：BatchAccountingService then relation boundary。
- 禁止绕过：直接写 relation/read model 表；在页面批量合成业务状态。
- 未提交列表 relation lookup 必须以页面可展示/可提交候选行为输入；`submitted_count` 必须走 relation facade 的轻量 count I/O，不能回退到 submitted relation 明细扫描污染首屏读路径。
- 已提交列表必须走年份级 batch-accounting relation DTO I/O，不能按 12 个月循环读取 relation distribution；银行行上下文只能读批量账务银行行。
- submit 写操作必须经过 `_build_submit_context`，只按本次选中的银行/OA/发票 row ids 读取命令所需 row payload，并只按本次 row ids 读取 canonical active relation 冲突；不能调用 `_build_list_context`、不能为了校验一次提交扫描整页银行/OA/发票候选或整页 relation distribution，也不能因普通 `workbench_relation` read model refreshing/stale/missing 直接拒绝 command 写入。
- submit/withdraw 写操作后的 route 不得再触发 duplicate derived lifecycle、`_schedule_workbench_pair_relation_persist`、`_schedule_workbench_read_model_persist` 或 snapshot rollback restore。关系事实持久化和 read model dirty/outbox fan-out 的唯一写边界是 `WorkbenchRelationCommandService` 及其 repository。PostgreSQL runtime 下 `Application._batch_accounting_service(...)` 必须注入 durable relation command service；缺失 durable repository 会造成 API 基于进程内状态返回成功但 canonical relation/read model 不收敛，必须 fail closed 或修正 wiring。withdraw route 必须以 `use_sql_read_model=True` 构造 service，保证旧关系 scope backfill 不会触发整页 Workbench loader。
- 批量账务写 API 不能同步执行默认 `workbench_read_model` rebuild executor；该 executor 会重建关联台 Workbench 视图，生产三个月 scope 可耗时十秒级。`PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` 已按 relation scope 投递 durable `workbench_relation`、`workbench` 和下游 read model refresh；route 层不得再补投递。
- 批量账务 relation 可以跨月，但跨月不等于 `all`。如果 row payload 可解析出 `2026-MM`，派生刷新必须只覆盖这些月份，避免 bank_detail/cost/search/workbench_relation 等下游读模型被 all scope 长耗时刷新拖慢。

## 测试与验证

- `tests/test_batch_accounting_api.py`
- `web/src/test/BatchAccountingApi.test.ts`
- `web/src/test/BatchAccountingPage.test.tsx`
- `web/e2e/batch-accounting-flow.spec.ts`

## 当前缺口和删除条件

- 如果新增独立 read model，必须先登记 manifest/scope policy/worker/tests/docs。
- 已删除旧链路：旧 app-level repair helper、service-level legacy case-id repair、submit/withdraw direct pair fallback、route duplicate lifecycle fan-out、旧 pair persist/snapshot restore、旧 workbench read model persist、已提交 bucket 12 个月 relation scan fallback。
- 批量账务 submit/withdraw 的生产 smoke 必须验证 durable relation 表、`workbench_relation` read model 和关联台 `workbench` active generation 同时收敛；单看 API `success=true` 不足以证明运行时外部收敛，但不影响本地模块边界 closed。

## Phase 19 relation normalization（2026-07-12）

- migration 0101 将 `special_metadata.source=batch_accounting` 的 active relation 从历史 `manual_confirmed` 规范为 `relation_mode=batch_accounting`，并同步结构化列与 normalized/raw payload mode。
- 该迁移只改变可由 owner metadata 唯一确定的 App 内部 relation 分类；不得新增、删除或猜测 relation member。

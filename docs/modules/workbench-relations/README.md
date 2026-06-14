# 关联台关系事实源 模块维护入口

- Module key: `workbench-relations`
- 类型: 资源模块
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `ARCHITECTURE.md`
- `docs/architecture/persistence-and-read-models.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/batch-accounting/README.md`
- `docs/modules/etc-tickets/README.md`

## 代码入口

当前实现分散在以下位置，后续迁移目标是把 relation 写入边界收敛到正式后端模块：

- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
- `backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`
- `backend/src/fin_ops_platform/services/workbench_relation_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/workbench_relation_distribution_mapper.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/batch_accounting_service.py`
- `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py`
- `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`
- `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`
- `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`

## 当前事实源分析

`app.workbench_pair_relations` 是 OA、银行流水、正式发票和 OA 附件发票跨页面已确认配对关系的 canonical write model。`app.workbench_pair_relation_history` 保存 confirm、cancel、withdraw、repair 等操作历史。当前 PostgreSQL migration 已经提供 `case_id`、`relation_mode`、`status`、`version`、`month_scope`、`row_ids`、`row_types`、`amount_check`、`special_metadata`、`source_versions` 和 raw payload。

`workbench_relation` 是跨页面 relation distribution read model。它从 `app.workbench_pair_relations` 读取 active 手工关系，同时从 `read_model.workbench_reconciliation_decisions` 补充分发已 paired 的自动决策和未配对区 open/proposed 候选。自动决策只作为候选或展示上下文，不是已确认写事实，不能被页面当作 active relation 写模型。

distribution payload 必须保留关系展示语义：`relation_status='linked'` 表示已确认或已 paired 的关系上下文；`relation_status='candidate'` 表示关联台未配对候选，只能用于页面展示候选证据，不得作为 confirmed fact、支付完成判断或 row 占用事实。下游 mapper 不得把 candidate 硬编码成 `status='active'`。

`WorkbenchRelationReadFacade` 是下游页面读取关系上下文的唯一后端边界。待找发票、OA 待付款、进项发票使用、销项发票收款、银行明细关系标签、成本、税金、搜索和批量账务的读路径必须通过它或它封装的 request-scoped context 读取 `workbench_relation` distribution。

`WorkbenchPairRelationService` 当前同时承担领域规则对象和部分 runtime mutable snapshot 的角色。它已经覆盖 row 去重、row type 对齐、active row overlap、active case reuse、cancel、withdraw 和 history 生成。后续应保留为纯领域规则对象，不能继续被页面 service 当作事实源或读接口。

## 当前缺口

1. `PostgresWorkbenchRepository` 同时负责 workbench、no-OA、turnover、candidate match 和 relation 持久化，其中 `load_workbench_pair_relations`、`save_workbench_pair_relations`、history replace、dirty scope 推导和 downstream refresh 入队属于 relation 专属逻辑，应抽到 `PostgresWorkbenchRelationRepository`。
2. `server.py` 仍持有 `_workbench_pair_relation_service`，并包含 `_persist_workbench_pair_relations`、`_persist_workbench_pair_relations_in_transaction`、background persist、confirm preview、active relation repair、ETC summary cancel、OA invoice offset auto pair 等 relation 业务流程。它应只保留 route、依赖组装和 HTTP 映射。
3. ETC 业务批次删除、历史 repair、historical business batch migration 和 existing ETC batch link 的生产 wiring 已在 Phase 7A 迁入 command service，且 Phase 7B 删除了这些 ETC service 的 direct pair mutation fallback；input invoice OA reverse 已在 Phase 7C 迁入 command service；batch accounting submit/withdraw 已迁入 command service，且 submit 缺 command 时的 direct pair fallback 已删除；turnover manual closure/withdraw 的 legacy fallback 也已删除 direct pair write fallback。pending invoice manual/attach 已在 Phase 4 迁入 command service，no-OA submit/withdraw/internal transfer submit 已在 Phase 5 迁入 command service，turnover manual closure/withdraw 常规路径已在 Phase 6 迁入 command service。Phase 7F 已阻止 no-OA read-model worker 隐式执行 relation repair；Phase 7G 已删除 Workbench `confirm-link` / `cancel-link` 主写入口的 direct pair fallback；Phase 7H 已迁移个人暂借款还清 relation 写入；Phase 7I 已迁移 Workbench exception closed apply 的 `normal_match` / `oa_exempt` relation 写入；Phase 7J 已迁移 `server.py` 内 OA invoice offset auto pair 和 OA 附件上下文 repair 的 direct pair mutation；Phase 7K 已迁移 batch accounting legacy case id collision repair；Phase 7L 已迁移 no-OA legacy migration、submitted relation repair、category drift cleanup 和 submitted single-side consolidation。当前生产代码中 relation mutation 的属性级 direct pair service 扫描应只允许命中 `WorkbenchRelationCommandService` 与 `WorkbenchPairRelationService` 领域对象内部。
4. 写入口的 freshness、version conflict、幂等、active row occupation、审计、affected months 和 read model refresh enqueue 分散在各模块，容易出现多个事实源或半写入。
5. 前端 `workbenchRelationUpdated` 已被多个页面用作刷新提示，但它不是事实源。所有页面必须在 mount/refetch 或 mutation success 后重新读取后端状态。

## 目标边界

后续正式模块命名建议使用 `workbench_relations`。它不是新的大一统 OA/发票/流水源数据模块，只负责 relation lifecycle、relation identity、relation audit、dirty scope 和 read model 分发边界。OA、银行流水、正式发票、OA 附件发票的源事实仍归各自 repository、projection 和 import/OA 模块。

### `WorkbenchRelationCommandService`

统一承接所有 relation 写入：

- workbench confirm/cancel。
- workbench withdraw preview/submit。preview 必须返回 `operation_type`、`preview_id`、`submit_expected_versions`；submit 必须使用这些字段校验当前 relation identity，状态变化时返回 conflict，不得重新猜测当前可撤回对象。
- pending invoice attach existing/create manual invoice relation。
- no-OA submit/withdraw、internal transfer confirm-link、legacy migration、submitted repair、category drift cleanup 和 submitted single-side consolidation 收敛。常规入口已在 Phase 5 迁入 command service；legacy/repair/consolidation 已在 Phase 7L 迁入 command service，且 read model worker 继续禁止隐式 repair。
- turnover manual closure confirm/withdraw。
- batch accounting submit/withdraw。
- ETC 删除、历史修复、existing batch link、业务批次迁移。
- input invoice OA reverse 产生或撤销的 relation 写入。

该 service 负责：

- 加载当前 canonical relation snapshot 或 SQL rows。
- 调用 `WorkbenchPairRelationService` 执行业务规则和状态转换。
- 默认按 canonical relation 写模型校验 expected version、idempotency key、active row occupation 和合法 relation mode/state transition；只有调用方显式要求 freshness precondition 时才校验 `workbench_relation` read model fresh。
- 记录 before/after、actor、reason、affected months、request id、source versions。
- 通过 repository 同事务写入 relation 和 history。
- 通过统一 affected scope calculator 入队 `workbench_relation` 以及 downstream read model refresh。

### `PostgresWorkbenchRelationRepository`

从 `PostgresWorkbenchRepository` 抽离 relation 专属 SQL：

- `load_relations` / `load_case_ids` / `load_active_by_row_ids`。
- `save_snapshot` / `save_cases` / `replace_history_for_cases`。
- relation history append 或 replace。
- relation dirty scope 推导需要的银行、发票、OA、OA 附件行查询。
- transaction-bound durable queue 入队委托。

repository 可以知道 `app.workbench_pair_relations`、`app.workbench_pair_relation_history`、`job.outbox_events` 和 `job.read_model_dirty_scopes` 的 SQL 细节；业务 service 不散落 SQL。

### `WorkbenchRelationReadFacade`

继续作为所有下游页面读关系的唯一入口，不下沉到页面 service。它必须保留 freshness/status/enqueue 语义：

- `require_fresh=True` 时，missing/stale/source mismatch 返回非 fresh 状态并入队刷新。
- 读结果必须包含 `status`、`read_model_scope_keys`、`stale_reasons`、`refresh_enqueued`、`source_versions`。
- 业务写 API 不能把 facade 返回的空 rows 当成真实无关系。
- 读结果必须保留 `linked` / `candidate` / `unlinked` 语义。进项发票使用、OA 待付款、待找发票等下游页面可以展示 candidate 作为关联台候选证据，但只有 linked 能参与已支付、已关联、已占用等业务判断。

### `WorkbenchPairRelationService`

保留为纯领域规则对象：

- row id 去重并保持 row type 对齐。
- active case reuse 和 active row overlap 校验。
- relation replace/cancel/withdraw/history 生成。
- withdraw 的上一状态计算和无 history 时撤到无关联的领域转换。
- mode/state registry 的领域规则校验可以委托给它或独立 policy。

禁止它承担以下职责：

- 页面读关系事实。
- 直接写 PostgreSQL。
- 直接 enqueue read model refresh。
- 直接读取 HTTP、auth、cookie、header。

## Relation mode/state registry

需要显式维护 relation mode 和状态转换，不再让页面或 service 随意写字符串。

建议初始 mode：

- `manual_confirmed`：关联台普通人工确认。
- `normal_match`：Workbench exception closed apply 后形成的普通闭环关系。
- `oa_exempt`：Workbench exception apply 后形成的免 OA 闭环关系。
- `personal_advance_repayment_settlement`：个人暂借款还清 special relation。
- `oa_invoice_offset_auto_match`：OA 附件发票冲抵自动闭环关系。
- `pending_invoice_attach_existing_invoice`：待找发票选择已有发票。`pending_invoice_attach_existing` 仅作为迁移期兼容 mode，不再新增生产写入。
- `pending_invoice_manual_invoice`：待找发票人工补票后建立关系。
- `no_oa_bank_batch`：免 OA 批次提交或 internal transfer confirm-link 收敛。
- `turnover_manual_closure`：外部往来人工零差额闭环。
- `batch_accounting`：批量账务提交。
- `etc_business_batch` / `etc_historical_repair` / `etc_batch_invoice_link`：ETC summary、历史修复、历史批次补关联或业务批次迁移；`etc_batch_invoice_link` 是历史 ETC link/repair 的兼容 mode，新增生产写入必须通过 command service。
- `input_invoice_oa_reverse`：以发票反提 OA 本地确认关系。
- `automatic_decision`：只允许出现在 read model distribution 的自动决策上下文，不写入 active confirmed fact。

建议状态：

- `active`：当前有效，row 独占。
- `cancelled`：被关联台取消、ETC 删除、repair 或上层关系替换取消。
- `withdrawn`：由业务 owner 撤回，保留业务语义和撤回原因。
- `superseded`：被新 relation 显式替代，保留历史。
- `repair_attention`：迁移/修复发现不一致但不能自动改写时的工具状态，不应作为页面 active relation。

详见 `state-machine.md`。

## 读写入口覆盖清单

写入口必须迁移到 command service：

- `POST /api/workbench/actions/confirm-link`、`cancel-link` 和 `withdraw-link` 已迁入 command service；缺 command service 时 fail fast，不再回退到 direct pair snapshot 写入。`withdraw-link` preview/submit 由 command service 锁定 relation identity；无 history 时撤到无关联，不再由 facade 合成恢复关系。个人暂借款还清 `confirm_personal_advance_repayment` 已迁入 command service。Workbench exception closed apply 已通过 command service 写入 `normal_match` / `oa_exempt`，并在创建本地 exception case 前执行 canonical relation write safety。`server.py` 中 OA invoice offset auto pair 和 OA 附件上下文 repair 已通过 command service 写入；其他 server 读/展示/persist helper 仍待后续抽离。

`split_candidate` 不属于 relation lifecycle，不写入 `app.workbench_pair_relations` 或 relation history。关联台未配对区统一按钮在没有 active relation 但命中自动候选时，由 `WorkbenchWriteFacade` 复用 `WorkbenchCandidateMatchService.mark_candidates_suppressed(..., suppressed_reason="manual_override")` suppress 候选，并触发 Workbench read model refresh。
- pending invoice manual invoice confirm、attach existing 单条和批量已迁入 command service；读侧 active/candidate relation 仍走 `WorkbenchRelationReadFacade` distribution，写侧 row occupation、version、idempotency 和状态转换由 canonical relation command 负责。
- no-OA `submit-selection`、`submit-batch`、`withdraw` 已迁入 command service；`no_oa_bank_batch.read_model.refresh` 不再执行 relation repair；legacy relation migration、submitted repair、category drift cleanup 和 submitted single-side consolidation 已通过 command service 写入或取消 relation。已有 submitted batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 relation case，避免创建第二条 active relation。
- turnover manual zero-difference closure、withdraw 已迁入 command service；legacy fallback 缺少 command service 时的 direct pair write fallback 已删除，缺 command 会 fail fast。
- batch accounting submit、withdraw 已迁入 command service；submit 缺 command 时的 direct pair fallback 已删除；legacy case id collision repair 已通过 command service 写入。
- ETC 业务批次删除、历史 repair、historical business batch migration、existing batch link。Phase 7A 已完成生产 wiring：删除/reset 通过 command service 取消包含 summary row 的 active relation；历史 repair 通过 command service confirm `etc_batch_invoice_link`；历史业务批次迁移和 existing link 通过 command service 更新 relation metadata。Phase 7B 已删除这些 ETC service 的 direct pair mutation fallback；缺少 command service 或 canonical write safety 不通过时 fail fast，不先写本地 ETC 批次或 relation。
- input invoice OA reverse evidence detected 本地确认已迁入 command service；写入 `input_invoice_oa_reverse`，command service 缺失、权限/session 不满足、DB/目标写模型不可用或 canonical write safety 不通过时 fail fast，不先推进本地 batch。
- 数据重置、repair 和 migration 工具涉及 relation 的写入。

读入口必须保持通过 read facade/read model：

- workbench relation distribution。
- workbench open/proposed unmatched candidates distribution。候选必须通过 `WorkbenchRelationReadFacade` 发给各页面，不能让页面直接读取关联台本地候选或自动匹配表。
- bank detail relation tags。
- pending invoice rows/detail/OA detail。
- input invoice usage。
- output invoice collection。
- OA pending payment。
- no-OA batches/detail。
- turnover ledger。
- batch accounting。
- cost statistics、tax offset、search。

## Freshness、并发和幂等

- 所有写 API 在持久化前必须基于 canonical write model version、preview lock、idempotency、row occupation、owner 状态、权限/session 和 DB 可写性做强一致检查。`workbench_relation` read model freshness 是读侧状态；只有调用方显式启用 freshness precondition 时，非 fresh 才返回携带 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued` 的业务错误。
- 同一个 row 不能同时属于两个不同 active case。当前领域服务已在内存层检查，生产级还需要 command service 在事务中使用 row occupation lock、case lock、advisory lock 或 relation-row occupancy table 做并发保护。
- 重复 request 必须返回同一 relation 或同一业务错误，不能创建第二条 active relation。pending invoice、turnover 和 receipt 类似场景已有 idempotency contract，可复用其 store 模式。
- `version` 应作为 write model 乐观锁，不应用 read model version 替代。写成功后返回 relation version、affected months、changed case ids 和 refresh enqueue 结果。

## PostgreSQL history replay

生产或 staging 发布前应先运行只读 history replay，确认现有 `app.workbench_pair_relations` 没有 active row 多 case 占用、row id/type 结构错误、active unknown mode 或 read model readiness 问题。

本地或服务器命令：

```bash
cd /opt/fin-ops/releases/<release>/src
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
PYTHONPATH=/opt/fin-ops/releases/<release>/src/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.tools.workbench_relation_history_replay --json
```

`--fail-on-issues` 只用于 CI/release gate；生产手工巡检建议先不加该参数，确保 JSON 报告完整输出。该工具只执行 `select`，不会修复或写库。发现 warning 后应先分类确认，再单独设计 repair plan。

## Affected scope 和 downstream refresh

需要把 `_workbench_relation_dirty_scope_keys` 收敛成统一 affected scope calculator。它应根据 relation 的 `month_scope`、row ids、row types 和 row 来源查询银行、发票、OA、OA 附件月份，生成：

- `workbench_relation` scope。
- `workbench` active generation scope。
- `bank_detail` scope。
- `pending_invoice` 固定方向/状态 scopes。
- `input_invoice_usage`、`output_invoice_collection`、`oa_pending_payment` scopes。
- `invoice_lifecycle` 需要时的 scopes。
- `no_oa_bank_batch`、`turnover_ledger` owner scopes。
- `search`、`cost_statistics`、`tax_offset` scopes。

所有非事务入队走 `ReadModelRefreshGateway`；事务内 writer 保持同一业务事务并满足等价 scope contract。

2026-06-13 起，普通 `manual_confirmed` relation 的 downstream refresh 必须按 relation shape 收敛：

- 事务内 confirm 由 `PostgresWorkbenchRelationRepository` 基于 canonical row 表推导 scope，不得从 `read_model.workbench_rows` 反推写侧 affected scope。
- `app.invoices.invoice_type` 为进项时只刷新 `input_invoice_usage` 与税金相关 scope；销项时只刷新 `output_invoice_collection` 与税金相关 scope；方向未知时才保守刷新两侧。
- `app.bank_transactions.txn_direction` 为支出时只刷新 expense pending invoice 父 scopes；收入时只刷新 income pending invoice 父 scopes；方向未知时才保守刷新两侧。
- 生产 `withdraw-link` 必须和 `confirm-link` / `cancel-link` 一样走 transaction-bound Workbench UoW 与 `PostgresWorkbenchRelationRepository`，由同一事务写 canonical relation、history 和 durable dirty/outbox；不得在成功写入后再同步调用 legacy pair persist/read-model lifecycle 作为响应前置条件。
- 非 UoW legacy `withdraw-link` 兼容路径的 service 层 lifecycle 必须传 `include_all=False`，并携带 `downstream_scope_types`、`invoice_usage_scope_types`、`pending_invoice_scope_keys` metadata，让普通 read model 非相关失败不拖慢或污染本次操作链路。
- 以上收敛只减少不相关 read model refresh；页面 `已同步` 仍必须来自 durable queue/readiness 的真实 fresh gate。

## 旧逻辑删除清单

Phase 迁移完成后必须删除或降级：

- `server.py` 的 `_persist_workbench_pair_relations`、`_persist_workbench_pair_relations_in_transaction`、`_persist_workbench_pair_relations_in_background` 业务持久化职责。
- `server.py` 中直接操作 `_workbench_pair_relation_service` 的 confirm preview、active relation payload apply、读展示和 persist helper 等业务流程；ETC cancel 生产写入口已迁移，Workbench confirm/cancel 主写入口 direct fallback 已删除，Workbench exception closed apply 已迁移，OA invoice offset auto pair 和 OA 附件上下文 repair direct mutation 已迁移。
- `PostgresWorkbenchRepository.load_workbench_pair_relations` 和 `save_workbench_pair_relations` 的 relation SQL 实现，保留兼容代理时必须转调新 repository，并在迁移结束删除代理。
- no-OA legacy migration/repair/consolidation 直接写 pair relation 的旧路径已在 Phase 7L 删除，保留的 `pair_relation_service` 只作为领域 snapshot/read 校验输入，写入必须通过 `WorkbenchRelationCommandService`。pending invoice 已移除 direct relation write fallback；no-OA 常规 submit/withdraw/internal transfer 写入口已改为 command service；no-OA read model refresh 已关闭 legacy relation repair；turnover manual closure/withdraw 和 legacy fallback 写入口已改为 command service fail-fast；ETC 业务批次删除、历史 repair、historical migration 和 existing link 生产 wiring 已改为 command service，且 direct pair mutation fallback 已在 Phase 7B 删除；input invoice OA reverse 已改为 command service；batch accounting submit 和 legacy repair direct fallback 已删除；Workbench exception closed apply direct write 已删除。
- downstream query/read services 对 `WorkbenchPairRelationService` 的任何读依赖。
- 测试 helper 可以保留 fake relation facade，但生产代码不能再以 pair snapshot fake fresh。

## 迁移顺序

1. 抽离 `PostgresWorkbenchRelationRepository`，保持行为等价，现有 `PostgresWorkbenchRepository` 暂时转调。
2. 建立 `WorkbenchRelationCommandService`、mode/state policy、affected scope calculator 和 command result DTO。
3. 先迁移 workbench confirm/cancel 与 batch accounting，因为它们已经显式依赖 `workbench_relation` freshness。
4. 迁移 pending invoice attach/create，并复用现有 request id/idempotency command store。Phase 4 已完成：manual invoice、attach existing 单条和批量写入口均委托 command service，缺少 command service 时 fail fast。
5. 迁移 no-OA submit/withdraw/internal transfer confirm-link，保证 no-OA batch 与 active relation 收敛到同一个 case。Phase 5 已完成常规写入口迁移和 stale/fresh API fail-fast；Phase 7L 已完成 legacy migration/repair/consolidation 写入口收敛。
6. 迁移 turnover closure/withdraw，与现有 UoW 对接。Phase 6 已完成常规 manual closure/withdraw command service 委托和 Application wiring guard；Phase 7E 已删除 legacy fallback 直连 pair service 写入。
7. 迁移 ETC 删除/历史修复/input invoice OA reverse 等 repair 工具路径。Phase 7A 已完成 ETC 业务批次删除、历史 repair、historical business batch migration 和 existing link 的 command service 生产 wiring；Phase 7B 已删除这些 ETC repair/link/migration service 的 direct pair mutation fallback；Phase 7C 已完成 input invoice OA reverse command service 写入和 no-half-write；Phase 7D 已删除 batch accounting submit 缺 command direct fallback；Phase 7E 已删除 turnover legacy fallback direct pair write；Phase 7F 已剥离 no-OA read model worker 隐式 repair；Phase 7G 已删除 Workbench confirm/cancel direct fallback；Phase 7H 已迁移个人暂借款 relation；Phase 7I 已迁移 Workbench exception closed apply relation；Phase 7J 已迁移 server OA offset auto pair 和 OA 附件上下文 repair direct mutation；Phase 7K 已迁移 batch accounting legacy case id collision repair；Phase 7L 已迁移 no-OA legacy repair/consolidation。
8. 删除 `server.py` 旧 helper 和 service 旧注入，扩展架构守卫测试。
9. 执行全量 read model/e2e/staging smoke，确认跨页面一致性。

## 是否过度设计

这不是过度设计，前提是模块只抽 relation lifecycle，不接管 OA、发票、银行流水源事实。当前代码已经有 write model、read model、read facade、领域服务和 boundary guard tests；问题是写入边界分散。把写入统一到 command service、把 SQL 抽到 repository、保留 read facade，是把已有事实源边界补齐，而不是引入新事实源。

真正过度设计的方案是新建一个“关联台全量对象模块”，把 OA、银行流水、发票源事实也搬进去。那会破坏 import、OA projection、invoice lifecycle、bank detail 和 read model 的现有 ownership，并形成更大的同步问题。本模块只定义关系，不拥有对象本身。

## 维护触发器

发生以下变化时，必须更新本模块文档：

- 新增、删除或改变 relation mode/state。
- 新增 relation 写入口或迁移旧写入口。
- 改变 `app.workbench_pair_relations`、history、read model distribution schema。
- 改变 freshness、version conflict、idempotency、audit、affected scope 或 dirty/outbox contract。
- 改变前端 relation mutation 后的刷新策略。
- 删除旧 relation helper 或新增架构守卫测试。

## 本目录文件

- `state-machine.md`：relation mode、状态、合法转换和非法状态。
- `tests.md`：七类测试适用性、现有测试入口和后续新增测试。
- `implementation-notes.md`：Phase 0 架构盘点、迁移计划、验收和风险。

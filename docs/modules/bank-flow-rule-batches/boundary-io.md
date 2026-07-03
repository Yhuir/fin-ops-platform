# 流水规则批量处理模块边界与 I/O

日期：2026-07-01

## 模块化状态

- 状态：implemented-modular-closure
- 当前边界可信度：high for API/UI/application service/relation rules/read model runtime/physical batch storage/tag-rule settings family/frontend feature split
- 本 slice 范围：生产入口、API、规则抽屉、批量提交、关联台判定、历史 no-OA rebaseline API、文档和自动化测试。
- 当前边界：新模块接管“按银行流水标签配置 OA/发票闭环要求并批量提交银行流水 relation”的业务；HTTP route、application service、read model key、refresh producer、worker event、operation barrier target、repository port、mutation persistence port、refresh persistence port、PostgreSQL 批次存储、read model row 表和 tag-rule settings family 已独立为 `bank_flow_rule_batch`。旧 no-OA 模块只保留自身 legacy API 与历史批次功能，不再承接 bank-flow 新链路。
- 当前缺口：无已知生产链路模块边界缺口。页面级 state/effect 编排仍保留在 `BankFlowRuleBatchPage.tsx`，纯 I/O、DTO、策略、view model、operation barrier helper 和通用组件位于 `web/src/features/bankFlowRuleBatches/`。新功能生产路径不接收 `selected_tag_codes`；旧 no-OA `selected_tag_codes` 写路径只属于 legacy no-OA 域。
- 旧代码删除条件：bank-flow 新链路不得 import/继承 no-OA route、application service、read model refresh、persistence port、no-OA worker 或 no-OA physical batch/read-model 表；no-OA 主入口、`selected_tag_codes` 写路径和 no-OA 常驻 worker 只属于 no-OA legacy 业务，不得重新接入 bank-flow。

## 职责边界

### 负责

- 流水规则批量处理页面和右侧紧凑 xlsx/grid 抽屉。
- 读取银行明细 active 标签事实，并为每个标签维护 `requires_oa` / `requires_invoice` 规则。
- 基于用户当前选择的银行流水创建批量 relation，并写入足够 metadata 供关联台判定 paired/open。
- 触发独立 `bank_flow_rule_batch`、`workbench_relation`、`workbench`、`bank_detail` 等受影响 read model 刷新。
- 提供历史 no-OA submitted rebaseline 的 dry-run/apply 合同。

### 不负责

- 不新增、编辑或删除银行明细标签。
- 不拥有银行流水、银行分类、OA、发票或 Workbench relation canonical facts。
- 不在前端本地伪造 paired/open 状态。
- 不绕过 `WorkbenchRelationCommandService` 写入、取消或恢复 relation。
- 不把旧 `selected_tag_codes` 自动迁移成新规则事实。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 银行标签事实 | `bank-details` active tag read facade / 自动标签规则 payload | 只读。每个标签至少包含 code、direction、primary label、sub label、status 和 rule version。标签增减必须反映到本模块抽屉左侧。 |
| 标签闭环规则 | `GET/PUT /api/bank-flow-rule-batches/tag-rules` | 本模块拥有 `app_settings.bank_flow_rule_batch_tag_rules` 中的规则版本和 `requirements_by_tag_code`。未知、停用、重复 tag code fail fast。新增/未配置标签默认 `requires_oa=true, requires_invoice=true`。 |
| 页面查询 | `BankFlowRuleBatchPage.tsx` | 查询候选/已提交/已撤回批次，必须携带 read model freshness/status。 |
| 批量提交 | `POST /api/bank-flow-rule-batches/submit-selection` | `transaction_ids` 必填、非空、去重。提交前重查银行流水身份、月份、账户、标签、active relation 占用和当前规则版本。 |
| 已提交重置 | `POST /api/bank-flow-rule-batches/reset-submitted` | 批量撤回当前所有 submitted 批次，必须走 withdraw + relation command，不直接 SQL 改表；旧批次保留 withdrawn/audit history，释放的银行 rows 在 read model rebuild 后重新成为候选。 |
| Rebaseline dry-run/apply | 管理 API 或运维工具 | 显式跨模块操作，只通过注入的 no-OA batch service 处理 legacy submitted no-OA relation/batch，并通过 no-OA mutation persistence 保存旧批次变更。apply 必须提交 dry-run manifest 并校验 batch/version 一致；缺失或漂移时拒绝。重复 apply 同一 manifest 幂等返回。 |
| 权限/session | API session / permissions | 读取、保存规则、提交批次、rebaseline 分别校验权限；缺权限 fail fast。 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 标签规则 payload | 前端抽屉 | 返回 `active_tags`、`rules`、`requirements_by_tag_code`、`version`、`bank_auto_tag_rules_version`、`permissions`。不返回可编辑左侧标签字段。 |
| 标签规则保存副作用 | `workbench-relations` / read models | 保存 `requires_oa` / `requires_invoice` 后，必须同步所有 active `relation_mode=bank_flow_rule_batch` 关系的 `special_metadata.requires_oa`、`requires_invoice`、`flow_rule_version`；同时同步匹配外部往来规则的 active `turnover:*` 关系，把旧 `manual_confirmed` 升级为 `turnover_manual_closure` 并写入 `requires_oa`、`requires_invoice`、`paired_requirement_tag_codes`、`paired_requirement_source`、`paired_requirement_version`。同步只能通过 `WorkbenchRelationCommandService.update_relation_metadata_for_case_id(...)`，且 relation command 的 load/save 必须接入 durable relation repository；不能依赖进程内 snapshot，不能让 Workbench 查询当前 settings 兜底，也不能直接改 relation 表。 |
| 批次列表 payload | 页面 | 返回 summary、rows、status bucket、read model status、stale reasons、scope keys 和分页信息。非 fresh 不能展示为真实空态。 |
| Relation command | `workbench-relations` | 使用 `relation_mode=bank_flow_rule_batch`，行级 relation display code 必须保持 `bank_flow_rule_batch`，不能退回 `fully_linked` 或 `no_oa_bank_batch`。metadata 至少包含 `source_batch_id`、`flow_rule_tag_code`、`flow_rule_version`、`requires_oa`、`requires_invoice`、`source_row_count`、`collapsed_bank_rows`；display tags 使用 `流水规则` + 业务标签，不能继承旧 `免OA` 标签。 |
| 关联台展示 | `reconciliation-workbench` | 银行流水数 `>3` 时默认折叠；是否进入 paired 由 required row type 是否已满足决定。 |
| Operation barrier | 前端 | 写成功后返回 `affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`。批量提交、撤回和 reset 的完整 target envelope 必须同时包含页面自身 `bank_flow_rule_batch` 受影响 month scope，以及关联台实际读取的 `workbench_relation`、`workbench` 的 `all` + 受影响 month scope；不能由 route 覆盖 service 返回的目标，也不能只返回 `bank_flow_rule_batch` 后让关联台读取旧 `month=all` 空 generation。流水规则批量处理页面的提交按钮只把 `bank_flow_rule_batch` 自身 target 作为阻塞等待 I/O；完整跨页 visibility targets 必须继续通过 `workbenchRelationUpdated` 事件传给下游页面和全局刷新链路，禁止把 `workbench/all` 聚合刷新重新接入当前页提交阻塞链路。 |
| Dirty scope/outbox | runtime/read models | 通过 owner producer 或同事务等价 writer 污染 `bank_flow_rule_batch`、`workbench_relation`、`workbench`、`bank_detail` 以及受影响下游。 |
| Audit record | permissions/audit | 保存规则、提交、撤回、rebaseline dry-run/apply 都记录 actor、reason、before/after、affected rows/months 和 request id。 |

## 持久化与投影

目标 canonical facts：

- `app.bank_flow_rule_batches`
- `app.bank_flow_rule_batch_events`
- `read_model.bank_flow_rule_batch_rows`

当前规则持久化选择：

- 使用 `app_settings.bank_flow_rule_batch_tag_rules.requirements_by_tag_code`，通过 `/api/bank-flow-rule-batches/tag-rules` 暴露为 `rules`。
- 迁移 `0083_bank_flow_rule_batch_tag_rules.sql` 只在缺失新 key 时从 `app_settings.no_oa_bank_batch_tag_selection` 一次性复制历史值；运行时不再回退读取 no-OA settings family。
- 新 API 和服务边界拒绝 `selected_tag_codes` / `selectedTagCodes`；`rules` 中重复 `tag_code` fail fast。legacy no-OA API 仍可读取旧字段用于历史兼容。
- 未配置 active tag 默认 `requires_oa=true`、`requires_invoice=true`。
- 规则设置不是关联台运行时事实源。已提交批次是否进入 paired/open 只读取 relation metadata；规则保存后若 requirement 变化，规则 owner 必须重写 active bank-flow relation metadata 并触发 `bank_flow_rule_batch` / `workbench_relation` / `workbench` 相关刷新。

目标拆分仍可新增独立表 `app.bank_flow_rule_tag_requirements`，前提是保留版本、审计和乐观锁，并提供旧 settings family 的一次性迁移。

当前 read model：

- Read model：`bank_flow_rule_batch`
- Projection：`scoped_incremental`
- `all` 语义：`fan_out_command`
- Scope：month scope。
- Worker：`bank-flow-rule-batch`
- Event：`bank_flow_rule_batch.read_model.refresh`
- Query owner：`BankFlowRuleBatchApplicationService`
- Repository owner：`BankFlowRuleBatchReadModelRepositoryPort`
- Operation barrier：`bank_flow_rule_batch` 自身目标直接读取 `bank_flow_rule_batch` readiness/outbox/worker facts，不再映射到 `no_oa_bank_batch`；同一次 mutation 返回的 `workbench_relation` / `workbench` visibility targets 必须覆盖关联台 `month=all` 首屏和受影响月份，确保批量提交后关联台不会在 relation 已写入但 active generation 未刷新时显示真实空态。
- 新 relation 写入 `relation_mode=bank_flow_rule_batch`，批次 payload/read model row 也必须携带 `relation_mode=bank_flow_rule_batch`。列表 API 查询 submitted/unsubmitted/withdrawn 时必须通过 `list_bank_flow_rule_batch_rows` repository port 过滤，旧 no-OA payload 缺失该字段时只按 `no_oa_bank_batch` 处理。
- PostgreSQL 运行时批次存储和 read model 查询使用 `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`；迁移 `0082_bank_flow_rule_batch_storage.sql` 从历史 no-OA 物理表按 `relation_mode=bank_flow_rule_batch` 回填，但运行时不再把 no-OA 表作为 bank-flow source of truth。no-OA legacy 仍使用 `app.no_oa_bank_batches`、`app.no_oa_bank_batch_events`、`read_model.no_oa_bank_batch_rows`。
- 持久化 I/O 使用 `PostgresWorkbenchRepository.save_bank_flow_rule_batches*` 命名入口，在同一事务内只删除/写入 bank-flow 物理表，并使用批量 values upsert 写 `app.bank_flow_rule_batches` 与 `read_model.bank_flow_rule_batch_rows`；禁止通过 no-OA persistence port、no-OA 物理表或逐行 projection fallback 写入新模块。
- Read model refresh 从 active relation 或已提交批次 relation fact 回灌 submitted 批次时必须按调用方目标 relation mode 判定；`bank_flow_rule_batch` 刷新不能复用 no-OA event/scope/producer，也不能把 bank-flow 批次显示到 legacy no-OA 列表。
- 业务写入后的 derived lifecycle 事件为 `bank_flow_rule_batch_changed`，domain 为 `bank_flow_rule_batch_read_model` + Workbench/relation/cost/search 下游；禁止再以 `no_oa_bank_batch_changed` / `source=no_oa_bank_batch` 表示 bank-flow 写入。
- 服务内由 submitted batch 反推 relation fact 时，必须继承该 batch 的 `relation_mode`、`source=bank_flow_rule_batch` 和 bank-flow display tags，并且只为当前 refresh `relation_mode` 生成 fact；禁止再把所有 submitted batch 硬编码为 `no_oa_bank_batch`。旧 no-OA legacy migration/repair 只允许处理 no-OA/明确 legacy relation，不得处理 `bank_flow_rule_batch`。
- 关联台按 relation metadata 判定 open/paired。

## 性能与刷新 I/O

- 列表 API 优先读取 `BankFlowRuleBatchReadModelRepositoryPort.list_bank_flow_rule_batch_rows(...)`；read model missing/stale 时返回非 fresh 状态并 enqueue `bank_flow_rule_batch` refresh，不能伪装空态。
- Worker 持久化写入必须保持 scoped incremental I/O；同一 scope 的多个 batch rows 应在 repository 边界批量 upsert，避免逐 batch round-trip 放大 worker handler 时间。
- `detail_payload(batch_id)` 和 `withdraw_batch(batch_id)` 先读取当前 bank-flow batch storage；只有 batch 缺失时才 fallback `scope_key=all` 重建 runtime snapshot。
- `reset-submitted` 不做前置 `all` refresh；撤回后只同步刷新受影响月份 scope，没有月份时才 fallback `all`。
- 页面提交、撤回、reset 的前端阻塞等待只等待 `bank_flow_rule_batch` 自身 target。`workbench_relation` / `workbench` targets 保留在 mutation result 和事件广播中，由关联台或后台 runtime 收敛；不能让 `workbench/all` 聚合刷新拖慢当前页提交完成反馈。
- Worker refresh 使用 `bank_flow_rule_batch_source_versions_summary(...)` 判断 scope source versions 是否 unchanged；能证明 unchanged 时完成 dirty scope 并跳过批次重建和 snapshot 发布。
- `tag-rules` 保存仍触发 `all` refresh，因为规则变更可能影响所有 active bank-flow relation requirement metadata；后续若要优化必须先有按 relation/tag 反查受影响 scope 的可靠索引。

Workbench relation facts 仍归 `workbench-relations`：

- 新模块只能通过 `WorkbenchRelationCommandService` 写入/撤销 `relation_mode=bank_flow_rule_batch`。
- 不能直接 SQL 写 `app.workbench_pair_relations` 或 read model。

## 文件范围

| 层 | 计划文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BankFlowRuleBatchPage.tsx` via `/bank-flow-rule-batches`；只负责页面级状态编排、请求生命周期和模块组合 |
| Frontend feature | `web/src/features/bankFlowRuleBatches/api.ts`、`types.ts`、`policy.ts`、`viewModel.ts`、`components.tsx` via `/api/bank-flow-rule-batches` |
| Frontend tests | `web/src/test/BankFlowRuleBatch*.test.*`、`web/e2e/bank-flow-rule-batches-flow.spec.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_flow_rule_batches.py` |
| Backend service | `bank_flow_rule_batch_application_service.py`；共享批次计算内核在中性 `bank_batch_application_service.py` / `bank_batch_service.py` |
| Repository/read model | `bank_flow_rule_batch_read_model_repository.py`、`bank_flow_rule_batch_read_model_refresh.py`、`bank_flow_rule_batch_read_model_refresh_producer.py`、`postgres_repositories/workbench.py`、`postgres_repositories/read_models.py`、`postgres_state_store.py`；refresh/mutation 保存走 `save_bank_flow_rule_batch*` 命名 IO |
| PostgreSQL migration | `0082_bank_flow_rule_batch_storage.sql`、`0083_bank_flow_rule_batch_tag_rules.sql` |
| Runtime registry | `read_model_manifest.py`、`runtime_worker_registry.py`、`app_status_domain_registry.py`、`app_status_read_model_registry.py` |
| Integration | `workbench_candidate_grouping.py`、Workbench display policy/decorator、relation command metadata mapping |
| Tests | `tests/test_bank_flow_rule_batch*.py`、`tests/test_workbench_candidate_grouping.py`、affected no-OA regression tests |

## 依赖方向

- 允许依赖：bank detail tag read facade、bank transaction identity/query port、Workbench relation command/read boundary、runtime queue/read model gateway、audit/permission service。
- 必须通过：`BankFlowRuleBatchApplicationService` 作为页面/API 编排入口；`WorkbenchRelationCommandService` 作为 relation 写入口。
- 禁止绕过：直接写银行分类表、直接写 relation 表、直接操作 read model 表、直接复用旧 no-OA `selected_tag_codes` 作为规则事实。

## 测试与验证

实现 slice 必须新增或更新：

- Business unit tests：规则默认值、勾选语义、标签增减、提交校验、paired/open gate。
- Service tests：规则保存、批次提交、relation command payload、rebaseline dry-run/apply、dirty scope。
- API contract tests：规则 GET/PUT、列表、submit-selection、rebaseline dry-run/apply、权限和版本冲突。
- Read model/worker tests：`bank_flow_rule_batch` freshness、scope、source version、旧 no-OA rebaseline 后刷新。
- Frontend interaction tests：xlsx/grid 抽屉、checkbox、只读左侧标签、保存错误、分页/选择/提交。
- Playwright E2E：详见 `e2e-spec.md`。
- Existing regression：no-OA、Workbench paired/open、bank details tag rules、pending invoices、turnover、search affected paths。

## 当前缺口和删除条件

- 代码已实现 bank-flow route/service/worker/event/barrier/producer/repository/persistence IO、PostgreSQL 物理批次/read model 表和 tag-rule settings family 独立。
- 旧 no-OA 模块仍承载自身历史事实和 legacy no-OA read model，当前不能删除其 route/service/tests；但 bank-flow HTTP、application service、read model event、worker、operation barrier、producer、mutation persistence 和 refresh persistence 不得再进入 no-OA route/service/event/scope/worker/persistence port。
- 历史 submitted no-OA 全量撤回必须单独作为 rebaseline 工具/API 实现，不能在普通页面查询或提交时隐式执行。
- 旧 `selected_tag_codes` 写路径、no-OA 页面主入口、no-OA internal transfer 特例和 no-OA read model 常驻 worker 只能服务 no-OA legacy 域，要么删除，要么有明确 retained tooling 边界和退休条件。

## Canonical facts ownership

- Owned facts: `app.bank_flow_rule_batches`、`app.bank_flow_rule_batch_events`、`read_model.bank_flow_rule_batch_rows`、`app_settings.bank_flow_rule_batch_tag_rules`。
- Shared facts: 银行标签和分类由 `bank-details` owner 管理；relation facts 由 `workbench-relations` owner 管理；WorkBench active generation 由 `reconciliation-workbench` 管理。
- Allowed writes: `BankFlowRuleBatchApplicationService`、明确 UoW、受控 rebaseline service。
- Allowed reads: bank flow rule batch query/read ports、规则 read service、read model boundary。
- Downstream outputs: `bank_flow_rule_batch`、`workbench_relation`、`workbench`、`bank_detail`、`turnover_ledger`、`search` dirty scopes 或 owner producer 输出。
- Forbidden paths: shared state-store broad snapshot、旧 no-OA selected code 兼容写入、调用方直接改 batch/relation 状态。

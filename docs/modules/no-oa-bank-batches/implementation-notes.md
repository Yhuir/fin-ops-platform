# 免OA流水批量处理 实施记录

> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 免 OA 流水批量处理首轮测试闭环状态为 `documented-risk`：已有测试覆盖 business core、application/service、API contract、read model/worker、前端交互、Workbench integration 和旧功能回归。
- 普通未提交 draft 流水的行级选择入口属于 `submit-selection` 新链路，前端显示 checkbox 只依据 canonical lifecycle：`bucket=unsubmitted`、`status=draft`（兼容旧 SQL/read model `status=unsubmitted` 归一后的 draft 语义）且非 `internal_transfer`；不得再由旧批次级 `can_submit` flag 控制。`can_submit` 仍可用于内部往来整批提交等批次级动作，最终提交合法性由后端 `submit-selection` 校验同月、同账户、同 `category_code` 和标签准入。
- 2026-06-19 Spec-first E2E Audit 校准后，本地 `NO-OA-E2E-001..009` 已有 Browser、组件、API、service 和 integration 映射；`NO-OA-E2E-010` 真实基础设施 worker drain 保持 staging/runtime `external-risk`。
- 本模块是 Bankdetail 高风险子域。后续不要把 no-OA 机械拆成脱离 Bankdetail 的独立事实源。
- `GET /api/no-oa-bank-batches` 和 detail 读路径不得在 missing/stale 时同步重建全量批次；必须返回 read model status 并 enqueue refresh。
- PostgreSQL list 读路径允许返回 fresh empty rows，但必须由 `job.read_model_dirty_scopes` 无 active blocker 且 `read_model.app_status_readiness` 记录为 fresh 共同证明；不能把无 rows 直接当 fresh。
- no-OA read model 支持 `all` 和月份 scope；月份 refresh 只读目标月银行流水，只替换目标月批次，合并保留其它月份 snapshot。
- Bankdetail/effective category 依赖未 fresh 时属于依赖等待，应保持 no-OA readiness 为 `refreshing` 并由 runtime worker defer/retry，不能记录为 `failed` blocker。
- Workbench confirm-link 的 internal transfer 特例必须最终写 no-OA submitted batch 和 `relation_mode=no_oa_bank_batch`，不得绕过批次写普通 `manual_confirmed`。
- no-OA legacy migration、submitted repair 和 submitted single-side consolidation 必须通过 `WorkbenchRelationCommandService` 写 relation；缺 command service 时 fail fast，不回退 direct pair mutation。银行明细标签变化不得触发 submitted batch 的 category drift cleanup。
- no-OA submit/withdraw 的长期目标是 facts/audit/dirty/outbox 同事务；当前目标契约由 `tests/test_bankdetail_write_uow_contract.py` 保护，真实收敛前保持 `documented-risk`。
- `GET /api/no-oa-bank-batches` 支持可选显式分页 `page/page_size` 或 `pageSize`；只有请求带分页参数时才裁剪 `batches` 并返回 `pagination`，旧调用方不带分页参数时保持原 shape。no-OA 前端默认以 `page=1&page_size=200` 读取列表并渲染分页控件；切换月份、状态 bucket 或页码时必须清空选择、详情缓存和详情错误。`page_size` 上限为 200，超限必须 fail closed 为 `invalid_paging`。
- 前端 stale polling、route unmount cleanup、category/rules events 刷新 list/detail/tag drawer 都是页面行为契约。submit-selection、submit、withdraw、tag-selection 保存等写操作必须用全屏 operation overlay 等待 `no_oa_bank_batch` barrier fresh 后再释放。
- relation-backed 的旧 `stale/category drift` 只作为内部兼容状态。只要 SQL read model payload 仍属于 submitted bucket 或可撤回，API/前端必须按 `submitted` 呈现、保留撤回入口，并清除复核类 blocked reason；页面不得显示“分类已变更，需复核”。
- `status=stale,status_bucket=unsubmitted` 表示旧 submitted batch 的源流水或分类漂移后已失去 active no-OA relation，不属于可提交 draft；该状态现在属于内部兼容/诊断状态，不得进入主列表、summary 或分页 total。生产历史行需通过公开 snapshot 或 `repair_no_oa_bank_batch_lifecycle` 清理。
- submitted/withdrawn 批次的行级标签是提交事实的一部分。提交时必须冻结 `row_tag_snapshot`，并写入 no-OA batch snapshot 与 Workbench relation `special_metadata`；详情接口对 submitted/withdrawn 优先用冻结标签，银行明细后续标签变化只影响 draft 候选。
- 右侧流水栏展示每条流水的银行明细有效标签，使用 detail row 的 `category_label_path`，为空时回退 `category_primary_label/category_sub_label/category_label/category_code`；标签显示为摘要单元格内紧凑 chip，不新增表格列。
- 2026-06-24 起，本模块是 modular IO read model 主线的第十一个非 Go pilot。下一步先审计 read model repository/state-store/public-snapshot/refresh-worker ownership，再决定首个实现抽取边界；不直接跳 Go/Fiber/Go Worker。

## 2026-06-25 - route callback collapse

- 目标：执行 `server-py:no-oa-bank-batch-route-callback-collapse`，把 `/api/no-oa-bank-batches*` HTTP mapping 从 `server.py` 收到 `NoOaBankBatchApiRoutes.route(...)`。
- 影响范围：no-OA bank batch route owner、server dispatch、route/API/static Guard tests；不改变 no-OA 业务规则、read model refresh/dirty/outbox/lifecycle owner、前端行为或生产数据。
- 关键决策：route owner 只接管 dispatch、path parsing、mutation-session/body/json-response ports；relation command、persist/rollback、refresh enqueue、source-version 和 stale-reason 继续由 application service / lower services 拥有。
- 文档影响：新增 modular IO implementation analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期事实源不变。
- 测试覆盖：新增 route-owner HTTP mapping/port 测试和 static Guard；复跑 no-OA API public regression。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-callback-collapse-2026-06-25.md`。
- 未测风险：完整 backend discover、前端 Vitest、Browser e2e、真实 PostgreSQL/RabbitMQ/Redis/systemd worker、admin/write evidence 和生产写入闭环仍未执行；本 slice 不声明模块全局 closed。
- 后续事项：执行 `server-py:no-oa-bank-batch-route-owner-local-closure-audit`。

## 2026-06-25 - route-owner callback audit

- 目标：执行 `server-py:no-oa-bank-batch-route-owner-audit`，审计 `server.py` 中 `/api/no-oa-bank-batches*` route callback 残留。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、本实施记录；不改变运行时代码、API response shape、权限、审计、read model freshness、worker 或前端。
- 关键决策：当前 8 个 no-OA bank batch callbacks 都是 dispatch/session/body/json wrappers；业务行为、relation command、persist/rollback、refresh enqueue 和 source-version/stale reason 仍由 `NoOaBankBatchApiRoutes` / `NoOaBankBatchApplicationService` / lower services 拥有。下一实现边界选择 route callback collapse，并通过显式 ports 注入 mutation session、JSON body loader 和 JSON response。
- 文档影响：新增 modular IO route-owner audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、本实施记录和测试矩阵；长期事实源不变。
- 测试覆盖：本轮 analysis-only，不新增运行时测试；下一实现 slice 必须补 route-owner/API/static Guard 测试。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker、Browser、admin/write evidence 和生产写入闭环仍未执行；no-OA module/global closure 未声明。
- 后续事项：执行 `server-py:no-oa-bank-batch-route-callback-collapse`。

## 2026-06-24 - Modular IO refresh persistence boundary extraction

- 目标：把 no-OA read model refresh worker 的 public snapshot 持久化从 broad state-store 直接调用中抽出。
- 影响范围：`NoOaBankBatchReadModelRefreshService`、`NoOaBankBatchReadModelPersistencePort`、runtime worker wiring、no-OA refresh tests 和 platform boundary guard；不改变业务规则、API shape、worker event、queue schema、Redis/cache、权限、审计或前端行为。
- 关键决策：`NoOaBankBatchReadModelPersistencePort.save_public_snapshot(...)` 是 worker refresh 的显式持久化边界，内部继续委托现有 `save_no_oa_bank_batches(...)` capability；SQL 清理/写入 owner 仍是 `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)`。
- 保留语义：`public_snapshot()` 仍只保存公开生命周期，stale source-version event 仍 skip，月度 refresh 仍保留其它月份批次，refresh worker 仍不得 repair/persist Workbench relation。
- 测试覆盖：新增 persistence port delegation test、refresh handler explicit persistence boundary test，并强化 no-OA refresh static guard，禁止 handler 直接出现 `save_no_oa_bank_batches`。
- 验证限制：完整 `tests.test_platform_runtime_boundary_guards` 仍有两个无关 OA invoice / ETC repair guard 失败；本切片新增的 no-OA guard 目标测试已通过。
- 后续事项：list/query 侧 broad `workbench_sql_read_repository` 注入已由 `read-models:no-oa-bank-batch-read-model-repository-port-extraction` 收敛；下一边界审计 refresh enqueue、derived lifecycle、operation barrier、force refresh 和剩余 app-owned helper surfaces。

## 2026-06-24 - Modular IO read model repository port extraction

- 目标：把 no-OA list/query 侧从 broad `workbench_sql_read_repository.list_no_oa_bank_batch_rows(...)` 收敛到 no-OA 专属 read model repository port。
- 影响范围：`NoOaBankBatchReadModelRepositoryPort`、`NoOaBankBatchApplicationService.list_batches_payload(...)`、`PostgresStateStore.no_oa_bank_batch_sql_read_repository`、`Application._no_oa_bank_batch_application_service(...)` wiring、read model manifest、no-OA application/workbench integration tests 和 platform boundary guard。
- 关键决策：`NoOaBankBatchReadModelRepositoryPort` 是 no-OA list/query 的应用侧 repository owner；`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)` 继续作为过渡期 SQL/table owner，不复制 SQL。
- 保留语义：missing/stale/fresh/unavailable status、refresh enqueue、summary、pagination、public lifecycle filtering、API shape、权限、审计、worker event、queue schema、Redis/cache 和前端行为不变。
- 旧路径分类：`list_batches_payload(...)` 不再读取 `_workbench_sql_read_repository`；旧 constructor 参数仅保留 compat adapter，会立即包装成 no-OA port，不能作为主 read path owner。
- 测试覆盖：新增 no-OA repository port isolation test、manifest owner assertion 和 platform guard；route-level stale/missing integration tests 改为注入 `_no_oa_bank_batch_sql_read_repository`。
- 下一步：执行 `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`，审计 refresh enqueue、derived lifecycle、operation barrier、force refresh、dirty/outbox 和剩余 app-owned helper surfaces。

## 2026-06-24 - Modular IO freshness/derived lifecycle boundary audit

- 目标：审计 no-OA read model 在 persistence/repository port 抽取后的 refresh enqueue、scope policy、App Status/worker registration、operation barrier、derived lifecycle 和剩余旧链路污染面。
- 结论：refresh enqueue 已通过 `ReadModelRefreshGateway`/scope policy；manifest、runtime worker registry、App Status read model/domain registry 和前端 operation barrier 目标已有本地证据。未发现页面把 stale no-OA read model payload 伪装为 fresh 的新增问题。
- 未闭合 gap：`Application._derived_lifecycle_no_oa_bank_batch_executor(...)` 仍拥有 no-OA derived lifecycle target scope 选择和 enqueue result assembly；`NoOaBankBatchApplicationService.persist_mutation(...)` 仍保留缺少 atomic mutation boundary 时的 broad state-store fallback。
- 下一边界：先执行 `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction`；之后再执行 `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`。
- 文档影响：本轮不改变业务状态、UI 状态、API shape、worker event、queue schema、operation barrier 状态、权限或审计含义；`state-machine.md` 定义不变。
- 测试决策：本轮是 analysis/accounting only；下一实现 slice 必须新增 executor service-layer/static guard，并复跑 no-OA application/read model/workbench integration 与相关 lifecycle 回归。

## 2026-06-24 - Modular IO derived lifecycle executor extraction

- 目标：把 no-OA derived lifecycle target scope 选择、refresh metadata forwarding 和 enqueued-job accounting 从 `Application` 移到显式 service executor。
- 影响范围：`NoOaBankBatchDerivedLifecycleExecutor`、`Application` derived lifecycle target map/wiring、executor unit tests、platform runtime boundary guard、modular IO state；不改变 API shape、业务规则、worker event、queue schema、Redis/cache、权限、审计或前端行为。
- 关键决策：`NoOaBankBatchDerivedLifecycleExecutor` 是 no-OA derived lifecycle 行为 owner；`Application._no_oa_bank_batch_derived_lifecycle_executor(...)` 只负责依赖组装并注入 no-OA refresh enqueue callback。
- 保留语义：月份 scope 继续成为具体月份 refresh target；非月份/空 scope 继续 fan out 到 `all`；默认 reason 仍为 `derived_lifecycle_no_oa_bank_batch`；result 仍返回 `deleted_counts`、`invalidated_scopes`、`enqueued_jobs`。
- 测试覆盖：新增 executor service-layer tests 和 platform boundary guard，防止 `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` 回归。
- 下一步：执行 `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`，处理 `persist_mutation(...)` 中缺少 atomic mutation boundary 时的 broad state-store fallback。

## 2026-06-24 - Modular IO mutation persistence fallback quarantine

- 目标：移除 no-OA mutation persistence 在 service 层的 broad state-store fallback，强制写入通过明确 `save_no_oa_bank_batch_mutation(...)` boundary。
- 影响范围：`NoOaBankBatchApplicationService.persist_mutation(...)`、`ApplicationStateStore.save_no_oa_bank_batch_mutation(...)`、no-OA application tests、state-store tests、platform guard 和 modular IO state；不改变 API shape、业务规则、worker event、queue schema、Redis/cache、权限、审计或前端行为。
- 关键决策：生产 PostgreSQL 继续使用 `PostgresStateStore.save_no_oa_bank_batch_mutation(...)`；local/Mongo 通过新增 `ApplicationStateStore.save_no_oa_bank_batch_mutation(...)` 保持同名显式边界；service 若拿不到该 boundary 就 fail fast 为 `NoOaBankBatchPersistenceError`。
- 旧路径分类：`persist_mutation(...)` 不再直接调用 `save_workbench_pair_relations(...)`、`save_no_oa_bank_batches(...)`、`save_workbench_read_models(...)`。
- 测试覆盖：新增缺少 atomic boundary 的 fail-fast service test、本地 state-store mutation boundary test、platform guard 防止 broad fallback 回归。
- 下一步：已由 `read-models:no-oa-bank-batch-local-implementation-closure-audit` 发现 broad full-state snapshot gap，并进入 full-state snapshot quarantine。

## 2026-06-24 - Modular IO full-state snapshot quarantine

- 目标：移除 broad `Application._persist_state(...)` 对 `no_oa_bank_batches` 的旧全状态 snapshot 写入。
- 影响范围：`Application._persist_state(...)`、read model architecture guard、modular IO state；不改变 no-OA 业务规则、API shape、worker event、queue schema、Redis/cache、权限、审计或前端行为。
- 关键决策：no-OA mutation persistence 继续通过 `save_no_oa_bank_batch_mutation(...)`；worker refresh public snapshot persistence 继续通过 `NoOaBankBatchReadModelPersistencePort.save_public_snapshot(...)`；broad full-state writer 不再作为 no-OA batch snapshot 的第二写入路径。
- 旧路径分类：`Application._persist_state(...)` 不再序列化 `no_oa_bank_batches` 或调用 `_no_oa_bank_batch_service.snapshot()`。
- 测试覆盖：新增 `ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist`，防止旧 full-state 写路径回归，同时确认 explicit no-OA persistence boundaries 仍存在。
- 下一步：已由 `read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit` 复核本地支持并记录真实环境证据 deferred。

## 2026-06-24 - Modular IO post-full-state local closure audit

- 目标：复核 full-state snapshot quarantine 后 no-OA 是否还有本地 implementation gap。
- 结论：未发现剩余本地 implementation gap；local support 已在 repository port、refresh persistence port、derived lifecycle executor、mutation persistence boundary、full-state snapshot quarantine 和 frontend operation barrier 方面 accounted。
- 旧路径清理：删除未使用的 `Application._no_oa_bank_batch_source_versions(...)` 和 `_no_oa_bank_batch_stale_reasons(...)`，source-version/stale reason 计算由 `NoOaBankBatchApplicationService` 继续拥有。
- 模块状态：记录为 `production-evidence-deferred`，不是 module closed；真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍需发布/生产只读验证。
- 下一步：执行 `read-models:next-pilot-selection-after-no-oa-bank-batch`，从 `search` 和 `bank_account_balance` 等剩余非 Go read model 候选中选择下一 pilot。

## 2026-06-24 - Modular IO repository/state-store boundary audit

- 目标：审计 no-OA read model repository/state-store/public-snapshot/refresh-worker ownership，确定第一个实现抽取边界。
- 结论：manifest、scope policy、runtime worker registry 和 route mapping 已是明确边界；`PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` 负责 SQL 清理和写入 `app.no_oa_bank_batches` / `read_model.no_oa_bank_batch_rows`；`PostgresStateStore.save_no_oa_bank_batches(...)` 仍是 broad state-store facade。当前最高风险 gap 是 `NoOaBankBatchReadModelRefreshService` 在 worker handler 中直接拿 `public_snapshot()` 并调用 broad `state_store.save_no_oa_bank_batches(...)`。
- 下一边界：`read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`。下一步应引入明确的 no-OA read model refresh persistence boundary/adapter，保持 SQL owner 不变，避免 refresh worker 继续直接依赖 broad state-store 写入口。
- 非首选边界：list-only `NoOaBankBatchReadModelRepositoryPort` 仍需要做，但不是第一刀；它只收敛 GET/list read side，不能解决 worker 写路径的 state-store/public snapshot 污染。
- 文档影响：全局和模块状态机定义不变；本轮没有改变业务状态、UI 状态、read model 状态、worker event、operation barrier、API shape、权限、审计或前端行为。
- 测试决策：本轮是 analysis/accounting only；下一实现 slice 至少需要覆盖 service-layer、read model/cache/background job 和 existing feature regression categories，并复跑 no-OA refresh/application/workbench integration 目标测试。

## 2026-06-24 - Modular IO read model pilot selection

- 目标：在 `turnover_ledger` 本地支持 accounted 后，把 `no_oa_bank_batch` 选为下一个非 Go read model 模块化试点。
- 理由：免 OA 批次有页面级 stale-read 风险、Bank Detail 依赖、Workbench relation 写邻接、public snapshot 持久化、operation barrier 和旧异常状态清理；它比 `search` 更适合作为页面级下一试点，也比 `bank_account_balance` 更高风险。
- 下一边界：`read-models:no-oa-bank-batch-repository-state-store-boundary-audit`。
- 审计范围：`NoOaBankBatchReadModelRefreshService`、`NoOaBankBatchApplicationService`、`NoOaBankBatchService.public_snapshot()`、`PostgresStateStore.load_no_oa_bank_batches(...)`、`PostgresStateStore.save_no_oa_bank_batches(...)`、`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`、route/list/detail/tag-selection read model 行为和 local/state-store snapshot 兼容路径。
- 兼容修复：目标测试发现 `NoOaBankBatchReadModelRefreshService` 仍用旧 `pair_relation_service=` keyword 构造 application service；已改为传入 `pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(...)`，与当前 `Application._no_oa_bank_batch_application_service(...)` factory 保持一致。
- 非目标：本选择 slice 不改业务规则、API shape、worker event、queue schema、Redis/cache、权限、审计、前端或 Go/Fiber/Go Worker，也不做 repository port 抽取。
- 测试决策：`tests.test_no_oa_bank_batch_read_model_refresh` 覆盖上述构造兼容修复；下一实现/审计 slice 必须至少评估 service-layer、read model/cache/background job 和 existing feature regression categories；若触及 response freshness shape 或前端 barrier，则补 API/frontend 测试。

## 2026-06-23 - 提交后批次行级标签冻结

- 目标：已提交免 OA 批次作为业务事实，不随银行明细后续标签调整而改变批次内流水标签；当前标签变化只驱动新的未提交候选。
- 根因：`NoOaBankBatchApplicationService.detail_payload(...)` 每次打开详情都会重新读取当前 effective category，再写入 detail rows 和 `categories_by_transaction_id`。这让 submitted batch 的状态和批次标签保持已提交，但明细行标签可能随银行明细当前标签漂移。
- 架构决策：
  - `NoOaBankBatchService` 在 draft 生成/提交链路保存 `row_tag_snapshot`，字段随 batch snapshot 持久化。
  - `relation_command_payload_for_batch(...)` 的 `special_metadata` 携带同一份 `row_tag_snapshot`，relation-backed projection 可从 relation metadata 恢复提交时标签。
  - submitted/withdrawn detail rows 与 `categories_by_transaction_id` 使用冻结 snapshot；draft detail 继续使用当前银行明细 effective category。
  - 历史 batch/relation 缺少 `row_tag_snapshot` 时，按 batch type/label 生成保守快照，避免用当前银行标签覆盖历史事实。
- 测试覆盖：
  - `tests/test_no_oa_bank_batch_service.py::NoOaBankBatchServiceTests::test_submitted_batch_snapshot_freezes_row_tags`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_submit_batch_delegates_relation_write_to_command_service`
  - `tests/test_no_oa_bank_batch_application_service.py::NoOaBankBatchApplicationServiceTests::test_submitted_batch_detail_keeps_submitted_row_tags_after_bank_category_changes`
- 七类测试覆盖：
  - Business core unit tests：适用，覆盖 batch snapshot 保存提交时行级标签。
  - Service-layer tests：适用，覆盖 relation metadata 与 detail payload 的冻结标签投影。
  - API contract tests：适用，detail rows 和 `categories_by_transaction_id` 继续保持原字段 shape，但 submitted/withdrawn 语义改为提交时标签。
  - Read model/cache/background job tests：本轮未改 refresh gateway/worker contract；冻结字段随 public snapshot/raw payload 持久化。
  - Frontend component and interaction tests：本轮未改前端渲染字段，前端继续消费 detail row 的同名标签字段。
  - End-to-end business-flow integration tests：本轮未新增浏览器链路；风险由 service/API 级语义测试覆盖。
  - Existing feature regression tests：适用，现有 no-OA service/application tests 继续覆盖 public lifecycle、relation-backed stale、submit/withdraw。
- 未测风险：生产历史提交批次若完全没有 `row_tag_snapshot`，只能按 batch type/label 做保守回填，无法还原当时更细的标签路径。

## 2026-06-23 - 公开状态收敛与生产数据修复入口

- 目标：按产品目标把免 OA 批量处理公开生命周期收敛为 `draft/submitted/withdrawn`，保证未提交区域出现的批次都能提交；旧 `conflict/stale/superseded` 不再污染主列表、summary、pagination 或持久化 read model。
- 根因：后端 service 会生成内部 `conflict/stale/superseded` 兼容状态，旧 application/API/前端又把 `conflict/stale` 算入未提交 summary。结果是用户看到“未提交”数量和批次，但这些批次不可提交、没有 checkbox。
- 影响范围：`NoOaBankBatchService.public_snapshot()`、`NoOaBankBatchApplicationService` 公开投影和持久化、`NoOaBankBatchReadModelRefreshService` worker 保存、前端 API mapper/types/page、生产 repair CLI、no-OA module docs/tests/e2e docs。
- 架构决策：
  - 公开 API/list/detail/summary/pagination 只返回 `draft/submitted/withdrawn`；`read_model_status=stale` 保留为读模型新鲜度状态，不是批次业务状态。
  - `status=unsubmitted,status_bucket=unsubmitted` 在后端公开投影、前端 mapper 和 repair 中归一为 `draft`，并设置为可提交，保护历史 read model。
  - relation-backed stale 通过 active no-OA relation 或 submitted bucket/canWithdraw 投影为 `submitted`；无 active relation 的 stale、internal transfer conflict、superseded 从公开 snapshot 清理。
  - 持久化入口改存 `public_snapshot()`，下一次 mutation/worker refresh 会原子删除 `app.no_oa_bank_batches` 与 `read_model.no_oa_bank_batch_rows` 中不在公开 snapshot 的旧异常行。
  - 新增 `fin_ops_platform.tools.repair_no_oa_bank_batch_lifecycle`：默认 dry-run 输出 removed/normalized batch IDs 和状态计数；加 `--apply` 才写库，且通过 `PostgresStateStore.save_no_oa_bank_batches` 执行。
- 测试覆盖：
  - `tests/test_no_oa_bank_batch_service.py` 覆盖 public snapshot 清理 conflict/stale，并保留 relation-backed stale 为 submitted。
  - `tests/test_no_oa_bank_batch_lifecycle_repair.py` 覆盖生产修复纯函数：删除 unsubmitted exception、stale active -> submitted、legacy unsubmitted -> draft。
  - `tests/test_no_oa_bank_batch_application_service.py` 覆盖 SQL read model exception rows 不进入公开 payload/summary/detail。
  - `web/src/test/NoOaBankBatchApi.test.ts` 覆盖非公开 exception batch 被过滤、legacy unsubmitted canSubmit 归一。
  - `web/src/test/NoOaBankBatchPage.test.tsx` 覆盖 exception batch 不进入主列表，普通/内部往来 draft 仍可提交。
  - `web/e2e/no-oa-bank-batches-flow.spec.ts` 继续覆盖七个普通 draft 类型 checkbox、submit-selection、barrier、withdraw 和 history。
- 七类测试覆盖：
  - Business core unit tests：适用，覆盖 public snapshot 与内部状态过滤。
  - Service-layer tests：适用，覆盖 application projection、持久化 public snapshot fallback、生产 repair pure function。
  - API contract tests：适用，覆盖公开 list/detail/summary 不泄漏 exception 状态；HTTP shape 保持兼容旧 count 字段但值不再污染未提交。
  - Read model/cache/background job tests：适用，worker refresh 保存 public snapshot，不再把 exception rows 写回主 read model。
  - Frontend component and interaction tests：适用，页面未提交区域只展示可提交状态。
  - End-to-end business-flow integration tests：适用，Playwright 验证所有普通 draft 类型 checkbox 和主写链路。
  - Existing feature regression tests：适用，保护 relation-backed stale submitted 投影、legacy unsubmitted 兼容、internal_transfer batch submit、read model stale freshness polling。
- 未测风险：本地没有直接连接生产库执行 repair dry-run；上线前应先运行 dry-run 保存报告，再确认 `removed_batch_ids/normalized_batch_ids` 后执行 `--apply` 并触发 no-OA read model refresh。

## 2026-06-23 - unsubmitted stale 明示复核原因与全普通类型 checkbox E2E（已被后续公开状态收敛取代）

- 目标：复查“右侧栏没有 checkbox”的截图复现。后续产品口径已收敛为公开生命周期只保留 `draft/submitted/withdrawn`，因此本节关于“明示复核”的 UI 方案不再作为当前实现依据；当前依据见上方“公开状态收敛与生产数据修复入口”。
- 根因：页面只对 `conflict` 显示 `blocked_reason`，对 `status=stale,status_bucket=unsubmitted` 静默处理；同时 `STATUS_META.stale` 仍显示“待提交”。后续架构修复改为不让 `stale/conflict/superseded` 进入主列表、summary 或 pagination。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块 E2E spec/coverage 和测试矩阵。
- 架构决策：
  - 旧方案曾计划把 `stale` 徽标从“待提交”改为“需复核”；该方案已被 public snapshot/repair 方案取代。
  - 页面只渲染公开状态；普通 draft/legacy draft 才显示行级 checkbox。
  - Playwright deterministic mock 新增 `ordinaryDraftMatrix` 场景，覆盖 `fee/salary/holiday_bonus/bonus/tax_payment/treasury_tax_collection/social_security` 七个普通类型逐个显示 checkbox、可勾选、可取消。
- 测试覆盖：
  - 当前回归改为 `web/src/test/NoOaBankBatchPage.test.tsx::filters unsubmitted stale batches out of the main list`，覆盖 `多账户8106` 类似截图的 stale 无 checkbox根因不会再进入主列表。
  - `web/e2e/no-oa-bank-batches-flow.spec.ts::shows selectable checkboxes for every ordinary draft no-OA batch type` 在真实 Chromium 覆盖七个普通可提交类型的 checkbox。
  - 完整 `web/e2e/no-oa-bank-batches-flow.spec.ts` 继续覆盖首屏失败恢复、stale polling、标签保存、submit-selection、成本统计 fan-out、撤回和历史只读。
- 七类测试覆盖：
  - Business core unit tests：不适用，本轮不改后端 stale 生成、关系清理或提交校验。
  - Service-layer tests：不适用，本轮不改 service/repository/audit/worker。
  - API contract tests：不适用，本轮不改 HTTP response shape；只修前端呈现和 e2e mock。
  - Read model/cache/background job tests：不适用，本轮不改 read model freshness 或 worker。
  - Frontend component and interaction tests：适用，新增 stale 阻断原因组件测试。
  - End-to-end business-flow integration tests：适用，新增真实 Chromium 全普通类型 checkbox 测试，并重跑 no-OA browser 主链路。
  - Existing feature regression tests：适用，防止 `stale` 再显示为“待提交”且无解释，防止普通类型 checkbox 只覆盖手续费一个 happy path。
- 未测风险：未连接真实生产 2026-01 数据直接读取 payload；如果生产中还有其它未知阻断状态，需要按真实 response 继续扩展 policy/mapper 和展示文案。

## 2026-06-23 - 旧 unsubmitted 状态归一与右侧选择列 policy 化

- 目标：修复免 OA 流水批量处理右侧流水栏部分普通未提交批次没有 checkbox 的问题；截图中的 `费用 / 手续费` 应走普通行级 `submit-selection`，不能因为旧 read model 状态值而隐藏选择列。
- 根因：页面可见状态和操作能力没有共享同一个 lifecycle 契约。API/read model 新契约使用 `status=draft,status_bucket=unsubmitted` 表示未提交草稿，但旧 SQL/read model 或旧 mock 可能返回 `status=unsubmitted,status_bucket=unsubmitted`。页面能力判断原先直接依赖 `status === "draft"`，导致同属未提交 bucket 的普通费用批次被判为不可逐行选择。内部往来原本也存在同类风险，只是它显示的是整批提交按钮而不是 checkbox。
- 影响范围：`web/src/features/noOaBankBatches/api.ts`、`web/src/features/noOaBankBatches/policy.ts`、`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPolicy.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、本模块维护文档。
- 架构决策：
  - API client mapper 在前端边界归一 batch lifecycle：`status=unsubmitted,status_bucket=unsubmitted` 投影为 canonical `status=draft,status_bucket=unsubmitted`；relation-backed stale 继续投影为 submitted。
  - 新增 `web/src/features/noOaBankBatches/policy.ts`，集中维护 `statusBucketFor`、普通行级选择、内部往来整批提交和撤回可用性。页面组件只调用 policy，不再散落生命周期判断。
  - 普通类型（fee/salary/holiday_bonus/bonus/tax_payment/treasury_tax_collection/social_security）在 `unsubmitted` bucket 且 draft 语义下显示右侧行级 checkbox；`internal_transfer` 在同状态下不显示行级 checkbox，改走批次级提交按钮；`conflict/stale/submitted/withdrawn` 不开放提交控件。
  - 状态徽标保留 legacy `unsubmitted -> 待提交` 文案兜底，避免局部测试或未来详情 payload 绕过 mapper 时出现英文状态。
- 测试覆盖：
  - `web/src/test/NoOaBankBatchApi.test.ts::maps legacy unsubmitted batch status to draft in the unsubmitted bucket` 覆盖 API 边界归一。
  - `web/src/test/NoOaBankBatchPolicy.test.ts` 覆盖普通类型行级选择、内部往来整批提交分流、非 draft 状态禁用和撤回能力。
  - `web/src/test/NoOaBankBatchPage.test.tsx::keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status` 覆盖页面右侧 checkbox 可见、可点击并调用 `submit-selection`。
- 七类测试覆盖：
  - Business core unit tests：不适用，本轮不改后端批次生成、金额、状态流转或提交校验。
  - Service-layer tests：不适用，本轮不改 application service、repository、audit、rollback、dirty scope 或 worker。
  - API contract tests：适用前端 API mapper contract，HTTP 后端字段和 response shape 未变。
  - Read model/cache/background job tests：不适用，本轮不改 freshness、cache、read model 写入或后台任务。
  - Frontend component and interaction tests：适用，新增 API mapper、policy 和页面 interaction 回归。
  - End-to-end business-flow integration tests：不新增，本轮只修前端状态投影和控件显隐；既有 Browser selected-row submit/withdraw flow 继续保护主链路。
  - Existing feature regression tests：适用，防止旧 lifecycle status 再次隐藏普通行级选择，并保护 internal_transfer 与普通类型分流。
- 未测风险：未使用真实生产登录态回放 2026-01 大月份截图数据；真实历史 SQL/read model 中如果存在新的未知状态值，仍需按生产数据巡检扩展 mapper/policy。

## 2026-06-22 - 未提交普通流水选择列不再受旧 can_submit 污染

- 目标：修复免 OA 流水批量处理里普通未提交手续费流水前没有 checkbox，用户无法选择流水后提交批次的问题。
- 根因：页面已有 `submit-selection` 新链路和 row selection state，但行级 checkbox 的显示仍额外依赖批次级 `canSubmit`。当 SQL/read model 旧 payload 缺少 `can_submit` 时，前端 mapper 会把 `canSubmit` 归一为 `false`，导致普通 `draft` 流水隐藏选择列，旧批次级 flag 污染了按流水选择提交的新链路。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、本模块测试矩阵。
- 架构决策：
  - 普通未提交流水的可选择性由页面可见业务状态决定：`bucket=unsubmitted`、`status=draft`、非 `internal_transfer`。
  - `can_submit` 不再参与普通行级选择入口；它保留给内部往来整批提交等批次级动作。
  - 后端 `submit-selection` 继续作为最终事实边界，校验空选择、重复、跨标签、未准入标签、跨月份、跨账户、内部往来单边和 active relation 占用。
- 测试覆盖：
  - `web/src/test/NoOaBankBatchPage.test.tsx::keeps draft row selection available when legacy read model rows omit can_submit` 覆盖旧 SQL/read model payload 缺少 `can_submit` 时 checkbox 仍显示并提交 `submit-selection`。
  - `tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group` 覆盖同账户多条手续费通过 `submit-selection` 提交后，在关联台已配对区显示为 `collapsed_summary` 折叠组。
- 七类测试覆盖：
  - Business core unit tests：不适用，本轮不改批次生成、状态流转、金额或后端选择校验。
  - Service-layer tests：不适用，本轮不改 application service、repository、audit、rollback 或 worker。
  - API contract tests：不适用，本轮不改 HTTP contract 或 DTO 字段。
  - Read model/cache/background job tests：不适用，本轮不改 freshness、cache、dirty scope 或后台任务。
  - Frontend component and interaction tests：适用，页面测试覆盖 checkbox 可见、可点击和 selected-row submit 请求体。
  - End-to-end business-flow integration tests：适用，新增 no-OA 多行手续费 submit-selection -> Workbench paired collapsed summary 后端集成验证。
  - Existing feature regression tests：适用，新增旧 read model payload 缺字段回归，避免旧 flag 再次隐藏新链路选择入口。
- 未测风险：真实生产长列表横向滚动、登录态权限和 staging/生产 worker drain 仍按既有 smoke 管理。

## 2026-06-21 - 右侧流水栏行级银行明细标签

- 目标：修复免 OA 流水批量处理右侧流水栏只显示摘要/用途/备注，缺少每条银行流水在银行明细中的有效标签，用户无法逐行核对分类事实的问题。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/app/styles.css`、`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、本模块测试矩阵。
- UI 决策：
  - 不新增列，避免压缩交易时间、对方户名和金额列；标签放入“摘要/用途/备注”单元格内。
  - 优先按 `category_label_path` 拆成多个 chip；路径缺失时回退主/子/标签名/code。
  - 无标签时不显示占位文案；relation context chip 仍保留在标签下方。
  - CSS 从 `span:first-child/last-child` 改为显式 class，避免新增 chip 被摘要/备注样式误伤。
- 文档影响：本轮只改变 no-OA 页面展示和测试矩阵，不改变业务口径、后端 API contract、read model、worker 或长期架构文档。
- 测试覆盖：
  - `web/src/test/NoOaBankBatchApi.test.ts::maps batch detail rows` 覆盖 detail row 分类路径映射。
  - `web/src/test/NoOaBankBatchPage.test.tsx::renders tag management and compact main/sub/transaction layout without account search or debug fields` 覆盖右侧流水行内银行明细标签 chip。
  - `web/src/test/NoOaBankBatchPage.test.tsx::keeps premium compact rails, transaction table, and interaction CSS contracts` 覆盖标签行 flex-wrap 和 chip 样式。
- 七类测试覆盖：
  - Business core unit tests：不适用，本轮不改批次生成、状态流转、金额、选择或提交规则。
  - Service-layer tests：不适用，本轮不改 application service、repository、audit、rollback 或 worker。
  - API contract tests：适用，前端 API mapper 测试锁定 detail row 的银行明细标签字段。
  - Read model/cache/background job tests：不适用，本轮不改 freshness、cache、dirty scope 或后台任务。
  - Frontend component and interaction tests：适用，页面测试覆盖流水表行级标签可见。
  - End-to-end business-flow integration tests：不适用，本轮不改跨模块写流程。
  - Existing feature regression tests：适用，既有 no-OA page/API 回归保护分页、标签管理、提交/撤回、只读门禁和 stale polling。
- 未测风险：真实生产长标签路径、超长摘要和大数据月份下的横向滚动/视觉遮挡仍需 staging 或生产登录态 smoke。

## 2026-06-20 - no-OA list GET 加载失败刷新恢复

- 目标：补齐 `/no-oa-bank-batches` 的本地 `NETWORK-RECOVERY` Browser 负面链路，防止首屏 `GET /api/no-oa-bank-batches` 暂时失败时页面同时显示普通空态，误导用户以为当前标签下没有流水。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块测试矩阵和全局 Spec-first/testing 文档。
- 关键决策：只做产品侧最小修正；错误态不再显示“当前标签下暂无流水”，刷新仍复用既有 `刷新` 入口和 `loadBatches` 路径，不改变 list API contract、read model freshness、submit/withdraw、tag-selection 或 operation barrier 语义。
- 测试覆盖：组件测试覆盖首屏 list 503 -> 错误态 -> 刷新 -> 列表恢复；Playwright 覆盖真实 Chromium 中 list 503、普通空态防伪成功、手动刷新恢复业务行、未选择时提交按钮仍禁用、失败文案清除和无可见错误残留。
- 验证命令：`cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx`；`cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`。
- 未测风险：本轮只覆盖 `GET /api/no-oa-bank-batches` 首屏加载失败恢复；submit/withdraw/tag-selection mutation 级网络失败、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实生产历史 no-OA relation 和大数据月份仍按后续 Browser/staging/runtime smoke 管理。

## 2026-06-19 - 成功写流可见错误残留 guard

- 目标：防止 no-OA 标签保存、selected-row submit、成本统计 fan-out、withdraw 或 history 只读节点已经成功，但页面仍残留“操作失败/同步失败/read model 失败”等可见错误提示。
- 影响范围：`web/e2e/no-oa-bank-batches-flow.spec.ts`、`tests/test_playwright_e2e_strict_diagnostics.py`、本模块测试矩阵和全局测试文档。
- 关键决策：不改变产品逻辑或 deterministic mock；在每个成功节点复用 `expectNoUnexpectedSuccessUiErrors(...)`，把“成功但报错提示仍显示”作为 Browser 回归失败。
- 文档影响：更新本模块 `tests.md`、`e2e-coverage.md` 和全局 testing closure state。
- 测试覆盖：`web/e2e/no-oa-bank-batches-flow.spec.ts` 加强标签保存、submit、成本统计下游、withdraw 和 history 成功路径；静态诊断防止后续移除该 guard。
- 验证命令：`cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`。
- 未测风险：真实生产 no-OA 写入仍需真实认证、业务审批和可回滚 scenario；本轮只覆盖 deterministic Browser flow 的可见错误残留。

## 2026-06-19 - no-OA Spec-first covered 校准与标签保存 Browser E2E

- 目标：建立 `/no-oa-bank-batches` 的 Spec-first E2E 合同和覆盖矩阵，并补齐标签准入保存的真实浏览器 freshness closure。
- 影响范围：`docs/modules/no-oa-bank-batches/e2e-spec.md`、`docs/modules/no-oa-bank-batches/e2e-coverage.md`、`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块测试矩阵、全局 Spec-first inventory 和 testing closure state。
- 关键决策：
  - 不改产品逻辑；deterministic mock 支持 `PUT /api/no-oa-bank-batches/tag-selection` 返回保存后的 selected tag codes。
  - Browser 测试断言标签 drawer 中选择“工资”、`PUT` body 包含 `expected_version=3` 和 `selected_tag_codes=["fee","salary"]`、operation barrier target 为 `no_oa_bank_batch:all`、保存成功后 drawer 关闭并重读 no-OA list。
  - 本地 Spec-first covered 不等于真实 worker drain；真实 PostgreSQL/RabbitMQ/Redis/systemd no-OA、Workbench、search、cost worker 收敛继续作为 staging/runtime smoke。
- 测试覆盖：扩展 `web/e2e/no-oa-bank-batches-flow.spec.ts`，新增 `saves tag scope through the freshness barrier and reloads the no-OA list`；新增 `e2e-spec.md` / `e2e-coverage.md` 映射 `NO-OA-E2E-001..010`。
- 验证命令：`cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`。
- 未测风险：真实生产历史 no-OA 批次/legacy relation/半迁移/重复 relation 回放、真实 worker drain、真实大月份/长标签树/长流水列表、真实网络恢复和 search 外层 UI。
- 后续事项：后续只在新增 no-OA 写入口、独立 search Browser route、真实下载/导出或网络恢复 UI 时追加本地 Browser E2E；真实 worker 最新性走 staging/runtime smoke。

## 2026-06-19 - Browser e2e 补 no-OA 到成本统计 fan-out

- 目标：扩展免 OA 浏览器主链路，证明 selected-row submit 不只让 no-OA 本页状态变化，还会让成本统计通过自己的 fresh read model 展示对应手续费成本行。
- 影响范围：`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、本模块测试矩阵、成本统计测试矩阵和全局 testing closure state。
- 关键决策：
  - 复用现有 no-OA submit/withdraw spec，避免新增只覆盖成本页静态 mock 的平行测试。
  - deterministic mock 使用 opt-in `noOaCostFanout`，提交前不影响成本统计；提交后成本统计项目视图出现 `免OA手续费成本项目`、金额 `8.80`、费用类型 `手续费` 和流水表 `网银手续费` / `建设银行`。
  - 本轮不改变 no-OA API、read model、worker 或 business logic；真实 worker drain 仍按 `infra-smoke` / staging gate。
- 测试覆盖：更新 `web/e2e/no-oa-bank-batches-flow.spec.ts` 并验证真实 Chromium 通过。
- 验证命令：`cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd no-OA 和成本统计 worker、生产历史 no-OA 批次、超大月份和真实搜索 fan-out 仍需 staging/生产 smoke。

## 2026-06-17 - relation-backed stale 可见状态收敛

- 目标：修复免 OA 流水批量处理页面在已提交 bucket 中显示“分类已变更，需复核”的误导状态；已提交批次按已提交展示并可撤回，未提交 draft 继续按未提交提交。
- 影响范围：`NoOaBankBatchApplicationService.summary/resolve_labels(...)`、`web/src/features/noOaBankBatches/api.ts`、`web/src/pages/NoOaBankBatchPage.tsx`、no-OA application/API/page tests。
- 关键决策：
  - 不改 persisted batch fact，不新增 relation 写路径；只在 API 出口和前端 DTO mapper 做用户可见投影。
  - `status=stale` 且 `status_bucket=submitted` 或 `can_withdraw=true` 时，对页面投影为 `status=submitted,status_bucket=submitted,can_withdraw=true,can_submit=false`，并清空复核类 blocked reason。
  - 真实 `conflict` 仍显示阻断提示且不可提交；这次不把 conflict 伪装成未提交。
  - 关联台 paired/open 闭环沿用既有 integration tests：提交后进入 paired，撤回后回到 open/unmatched。
- 测试覆盖：
  - `NoOaBankBatchApplicationServiceTests.test_sql_read_model_relation_backed_stale_batch_is_presented_as_submitted`
  - `web/src/test/NoOaBankBatchApi.test.ts::maps relation-backed stale batches as submitted`
  - `web/src/test/NoOaBankBatchPage.test.tsx::presents relation-backed stale batches as submitted without review prompts`
  - `NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open`
  - `NoOaBankBatchWorkbenchIntegrationTests.test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled`
- 七类测试覆盖：
  - Business core unit tests：本轮未改 no-OA 批次状态转换或 relation command payload。
  - Service-layer tests：适用，覆盖 SQL read model stale/submitted projection 与 summary 计数。
  - API contract tests：适用，前端 API mapper 覆盖旧 payload 兼容；HTTP route shape 未变。
  - Read model/cache/background job tests：本轮未改 worker/dirty scope；既有 stale SQL source version 和 Workbench integration 保护。
  - Frontend component and interaction tests：适用，覆盖不显示复核提示、显示已提交和撤回按钮。
  - End-to-end business-flow integration tests：适用，复用 no-OA submit -> Workbench paired、withdraw -> open 的后端 integration。
  - Existing feature regression tests：适用，保留 conflict 阻断、read-only 门禁、operation overlay、分页和旧 API mapper 回归。
- 未测风险：真实生产历史中无 active relation 的旧 stale 行如何清理仍需数据巡检；真实 worker drain 和大数据月份仍按既有 staging/生产 smoke 覆盖。

## 2026-06-17 - read-only 写入口权限门禁

- 目标：把免 OA 页提交、撤回、tag scope 保存和批量选择接入 session `can_mutate_data`，避免 read_export_only 用户在浏览器层看到或触发写操作。
- 影响范围：`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`。
- 关键决策：不改变 no-OA API contract；后端权限仍是安全边界，前端只做可见行为门禁。只读用户仍可查看批次、明细和标签范围。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并由 `docs/modules/permissions-and-audit/` 记录全局权限矩阵事实。
- 测试覆盖：新增 read-export unit regression；Playwright role matrix 覆盖 no-OA read-only 提交/撤回/tag scope 保存禁用。
- 验证命令：`cd web && npm test -- --run src/test/NoOaBankBatchPage.test.tsx`；`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`。
- 未测风险：真实生产长标签树、大月份和长列表滚动/视觉遮挡仍需 staging/生产登录态 smoke。

## 2026-06-17 - Browser e2e 选择提交到撤回闭环

- 目标：补齐免 OA 流水批量处理的真实浏览器主路径，防止后续页面维护时破坏选择未提交流水、提交、等待 read model fresh、进入已提交、撤回和历史只读。
- 影响范围：`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、本模块测试矩阵与全局测试闭环文档。
- 关键决策：
  - 使用 deterministic API mocks 固定一个 `fee` 手续费批次，状态从 `draft` -> `submitted` -> `withdrawn` 随浏览器操作流转。
  - e2e 断言用户可见 UI 合约和 HTTP mutation request body，不断言页面没有渲染的 submitted/withdrawn actor 字段。
  - 写操作成功后必须经过 `/api/operation-barrier/status`，再进入后续 bucket 验证，避免只测 API 成功不测 freshness closure。
- 测试覆盖：
  - `web/e2e/no-oa-bank-batches-flow.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改业务状态机，由既有 service tests 保护。
  - Service-layer tests：本轮未改 service 写边界，由既有 application/UoW tests 保护。
  - API contract tests：本轮未改后端 contract；e2e 额外断言 `submit-selection` 和 `withdraw` 请求体。
  - Read model/cache/background job tests：适用前端 freshness closure，e2e 断言 operation barrier 被调用；真实 worker drain 仍属未测风险。
  - Frontend component and interaction tests：适用并新增真实 Chromium 页面选择、bucket、dialog、toast 和只读状态。
  - End-to-end business-flow integration tests：适用并新增 selected-row submit -> barrier -> withdraw -> history browser flow。
  - Existing feature regression tests：适用并防止按钮、bucket 数量、请求体和 freshness barrier 回归。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd no-oa-bank-batch worker drain、大数据长列表、网络恢复和生产历史半迁移仍需 staging/生产 smoke。

## 2026-06-16 - P2/P3 显式分页首屏保护

- 目标：为免 OA list 建立可执行首屏上限，避免后续大数据月份把全部批次一次性返回给首屏。
- 影响范围：`NoOaBankBatchApplicationService.list_batches_payload(...)`、`NoOaBankBatchApiRoutes.list_batches(...)`、`web/src/features/noOaBankBatches/api.ts`、`web/src/pages/NoOaBankBatchPage.tsx`、no-OA route/service/API/page tests。
- 关键决策：
  - 显式请求 `page/page_size` 或 `pageSize` 时，list 只返回当前页 `batches`，但 `summary` 仍基于完整过滤结果，`pagination.total` 返回完整命中数。
  - 不带分页参数时保持旧 response shape，避免破坏旧调用方和既有测试。
  - 前端默认发送 `page=1&page_size=200`，用后端 `pagination` 渲染上一页/下一页控件；月份、状态 bucket 或页码变化会清空当前选择、详情缓存和详情错误，避免旧页状态污染新页操作。
  - `page_size>200`、非正数或非法整数统一返回 `invalid_paging`，route facade 映射为结构化 400。
- 测试覆盖：
  - `NoOaBankBatchApplicationServiceTests.test_list_batches_explicit_pagination_protects_first_screen_slo`
  - `NoOaBankBatchRoutesTests.test_list_batches_invalid_paging_returns_structured_400`
  - `web/src/test/NoOaBankBatchApi.test.ts`
  - `web/src/test/NoOaBankBatchPage.test.tsx::uses backend pagination for no OA first-screen batches`
- 七类测试覆盖：
  - Business core unit tests：本轮未改 no-OA 批次生成业务规则。
  - Service-layer tests：适用，覆盖 250-row synthetic list、`page_size=200`、第二页和超限 fail closed。
  - API contract tests：适用，覆盖 `invalid_paging` 结构化 400。
  - Read model/cache/background job tests：本轮未改 freshness、dirty scope 或 worker。
  - Frontend component and interaction tests：适用，覆盖 API client 参数/响应映射、首屏 200-row 分页、下一页重载、旧页批次不残留和分页控件 CSS contract。
  - End-to-end business-flow integration tests：本轮未改跨页写流程。
  - Existing feature regression tests：适用，通过 no-OA application/routes/API/page 全量目标测试保护既有 list/submit/withdraw contract。
- 未测风险：真实 PostgreSQL 大数据 EXPLAIN、真实浏览器长列表滚动/视觉遮挡和生产登录态 API p95 仍需 staging/生产 smoke。

## 2026-06-14 - 写操作后 freshness barrier

- 目标：免 OA 批次提交、撤回和标签保存后隐藏 read model 收敛窗口，避免页面提前显示旧批次、旧候选或允许重复提交。
- 影响范围：`NoOaBankBatchPage` 写操作、`GlobalOperationOverlayProvider`、`operationBarrier` API client。
- 关键决策：写 API 成功后等待 `no_oa_bank_batch` barrier 对 affected months/current scope fresh，再重新加载 list/detail/tag selection。前端 domain event 仍只做刷新提示，不作为同步完成证据。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：更新 `web/src/test/NoOaBankBatchPage.test.tsx`，并由 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts` 覆盖共享 overlay/barrier 行为。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态 operation-to-fresh latency 需要发布后度量。

## 2026-06-11 - 首轮测试闭环审计

- 目标：把 `no-oa-bank-batches` 从测试闭环 `pending` 推进到可维护的 `documented-risk` 状态。
- 影响范围：免 OA 页面、tag-selection、list/detail、submit-selection、batch submit、bulk submit、withdraw、internal transfer from Workbench、no-OA read model、no-oa-bank-batch worker、App Status、Bankdetail tag/rule events。
- CodeGraph 审计：
  - `NoOaBankBatchPage` 调用 `fetchNoOaBankBatches`、`fetchNoOaBankBatchDetail`、`fetchNoOaBankBatchTagSelection`、`saveNoOaBankBatchTagSelection`、`submitNoOaBankBatchSelection`、`submitNoOaBankBatch`、`withdrawNoOaBankBatch`，并在 read model 非 fresh 时后台轮询。
  - `NoOaBankBatchApiRoutes` 是 HTTP route facade，负责 payload/session 映射和 error status；业务落在 `NoOaBankBatchApplicationService`。
  - `NoOaBankBatchApplicationService` 覆盖 list read model fallback、tag selection、submit/withdraw、after_mutation、durable queue enqueue 和 Workbench 影响。
  - `NoOaBankBatchService` 覆盖 draft/submitted/withdrawn/stale/conflict、internal transfer、legacy relation migration、pair relation metadata 和 snapshot/audit。
  - `NoOaBankBatchReadModelRefreshService` 只处理 `no_oa_bank_batch.read_model.refresh`，stale source version event 会 skip。
  - worker registry 和 App Status registry 已登记 `no-oa-bank-batch` worker、`no_oa_bank_batch` read model 和 `no_oa_bank_batch.read_model.refresh` event。
- 关键测试覆盖：
  - Business core：`tests/test_no_oa_bank_batch_service.py`。
  - Application/service：`tests/test_no_oa_bank_batch_application_service.py`、`tests/test_bankdetail_write_uow_contract.py`。
  - API/route：`tests/test_no_oa_bank_batch_api.py`、`tests/test_no_oa_bank_batch_routes.py`、`tests/test_no_oa_bank_batch_tag_selection_api.py`。
  - Read model/worker：`tests/test_no_oa_bank_batch_workbench_integration.py`、`tests/test_no_oa_bank_batch_read_model_refresh.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`。
  - Frontend：`web/src/test/NoOaBankBatchApi.test.ts`、`web/src/test/NoOaBankBatchPage.test.tsx`、domain event tests。
  - Integration/regression：`tests/test_no_oa_bank_batch_workbench_integration.py` 覆盖 Workbench internal transfer、manual relation 分流、mixed conflict、submitted/withdraw/open 恢复。
- 文档影响：
  - 补齐 `README.md` 模块边界和代码入口。
  - 将 `tests.md` 迁入测试闭环标准结构。
  - 补齐 `state-machine.md`。
- 未测风险：
  - 真实 PostgreSQL 历史 no-OA 批次、legacy relation、半迁移状态和重复 relation 的全量回放。
  - 真实 RabbitMQ/Redis/systemd worker drain 和网络抖动恢复。
  - 大数据月份、长标签树、长银行流水列表的浏览器性能和视觉遮挡。
  - Bankdetail/no-OA 写 UoW 真实事务内收敛尚未完全由本地 fixture 证明。
- 后续事项：
  - 修改 submit/withdraw 前，优先补 service/UoW/API characterization test。
  - 修改 read model freshness 前，必须运行 no-OA read model integration 和 worker refresh tests。
  - 修改前端 stale polling、route activation 或 domain event 时，必须运行 no-OA page tests 和 `useActiveFinanceDomainEvent` tests。

## 2026-06-11 - 内部往来双入口闭环

- 目标：修复同一组内部往来在免 OA 页面和关联台两个入口之间可能出现重复 active relation、旧未提交/冲突批次残留、历史 `manual_confirmed` 占用后不进入免 OA 已提交区域的问题。
- 决策：
  - 关联台仍允许作为内部往来提交入口，但成功事实必须委托并收敛到 no-OA submitted batch。
  - 如果免 OA 页面已经提交同一组 `row_ids`，关联台再次 confirm-link 复用 existing submitted batch 和同一个 `case_id`，保持幂等。
  - 存量两行、全银行流水、同金额、不同账户、收支成对且有效分类均为 `internal_transfer` 的 `manual_confirmed` active relation，刷新时迁移为 submitted no-OA internal transfer batch。
  - Workbench pair relation service 增加 active row 独占保护，不同 active case 不能共享同一 row。
  - PostgreSQL no-OA snapshot 保存必须删除新 snapshot 中缺席的旧 batch row，防止 SQL read model 继续返回旧 unsubmitted/conflict。
- 验收测试：
  - `test_manual_confirmed_internal_transfer_relation_migrates_to_submitted_no_oa_batch`
  - `test_workbench_confirm_after_no_oa_submit_reuses_existing_internal_transfer_fact`
  - `test_create_active_relation_rejects_active_row_reuse_by_different_case_id`
  - `test_save_no_oa_bank_batches_replaces_absent_read_model_rows`

## 2026-06-12 - Relation command service 写入口收敛

- 目标：把 no-OA submit、submit-selection、Workbench internal transfer submit 和 withdraw 的 relation 写入收敛到 `WorkbenchRelationCommandService`，避免 no-OA 页面和 Workbench 形成独立事实源。
- 决策：
  - `NoOaBankBatchService` 保留为批次领域状态机，只产出 `relation_command_payload_for_batch(...)`，不再直接调用 `create_active_relation` 或 `cancel_relation`。
  - `NoOaBankBatchApplicationService` 负责调用 relation command service，并在失败时回滚 no-OA batch snapshot 与 relation snapshot。
  - relation 占用和写入使用 canonical relation command/write safety；`submit_selected_rows` 不再读取 pair service list。
  - relation distribution/read model non-fresh 不阻断 batch submit；提交后继续刷新 no-OA、Workbench 和 downstream read model。
  - no-OA legacy migration、submitted repair、category drift cleanup 后续已在 Phase 7L 迁入 relation command service。
- 验收测试：
  - `test_submit_batch_delegates_relation_write_to_command_service`
  - `test_withdraw_batch_delegates_relation_cancel_to_command_service`
  - `test_internal_transfer_from_workbench_delegates_relation_write_to_command_service`
  - `test_submit_batch_marks_submitted_and_exposes_relation_command_payload_idempotently`
  - `test_submit_uses_canonical_relation_when_relation_read_model_is_not_fresh`
  - `test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open`
  - `test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled`

## 2026-06-12 - Read model refresh 不再隐式修复 relation

- 目标：把 `no_oa_bank_batch.read_model.refresh` 从 relation 写入口中剥离，避免 worker 在重建 no-OA projection 时顺手创建/取消 pair relation，形成隐藏事实源写入。
- 决策：
  - `NoOaBankBatchService.build_batches(...)` 增加 `apply_relation_repairs` 参数；默认保持 legacy 兼容行为。
  - `NoOaBankBatchApplicationService.refresh_batches(...)` 暴露同名参数，并且只有启用 repair 时才根据 `last_legacy_migration_result` 触发 relation/workbench persist。
  - `NoOaBankBatchReadModelRefreshService` 固定调用 `refresh_batches(apply_relation_repairs=False)`；worker 只保存 no-OA snapshot，不保存 pair relation，不执行 legacy migration/repair/consolidation。
  - legacy migration、submitted repair、category drift cleanup 仍是待迁移兼容路径，后续应收敛为显式 repair command/离线 repair 工具。
- 验收测试：
  - `test_refresh_does_not_repair_workbench_relations_from_read_model_path`
  - `test_no_oa_read_model_refresh_does_not_run_relation_repairs`

## 2026-06-12 - Legacy relation repair 写入口收敛

- 目标：把 no-OA legacy relation migration、submitted relation repair、旧 category drift cleanup 和 submitted single-side consolidation 从 direct pair service mutation 收敛到 `WorkbenchRelationCommandService`。注意：2026-06-23 后当前语义已改为银行明细标签变化不得改 submitted batch，旧 category drift cleanup 不再作为当前 submitted 写路径。
- 决策：
  - `NoOaLegacyRelationMigrationService` 通过 command service cancel legacy relation，再 confirm `relation_mode=no_oa_bank_batch`；缺 command service 时抛 `no_oa_relation_command_unavailable`。
  - `NoOaBankBatchService` 的 legacy/repair/consolidation 路径通过 `_confirm_no_oa_relation(...)` / `_cancel_no_oa_relation(...)` 委托 command service，不再调用 `_pair_relation_service.create_active_relation/cancel_relation/record_history`。
  - `Application` 为 no-OA batch service 注入 `WorkbenchRelationCommandService(require_fresh_relations=False)`，使显式 repair 路径复用统一 command/history/snapshot 边界，同时避免 read model worker 隐式 repair。
  - 已有 current submitted no-OA batch 与 legacy active relation 命中同一 row set 时，迁移复用 existing submitted batch 的 `relation_case_id`，避免新建 legacy batch case 后与旧 submitted batch 形成两个 active relation。
  - submitted repair 遇到 row 已被非 no-OA active relation 占用时跳过重建 no-OA relation，保留 active row 独占事实，并在 migration result 的 `skipped` 中记录 blocking case。
- 验收测试：
  - `test_submitted_internal_transfer_with_active_non_no_oa_relation_does_not_duplicate_as_unsubmitted_conflict`
  - `test_legacy_salary_relation_migrates_to_submitted_no_oa_batch_idempotently`
  - `test_existing_submitted_single_row_salary_batches_consolidate_by_month_and_account`
  - `test_consolidated_submitted_salary_batch_repairs_stale_single_row_relations`
  - 历史旧测：`test_submitted_single_side_batch_prunes_rows_that_no_longer_match_category`、`test_submitted_batch_that_becomes_stale_clears_active_relation` 已被当前 `test_submitted_single_side_batch_keeps_rows_when_category_changes`、`test_submitted_batch_stays_submitted_after_category_change` 取代。
  - `test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback`
- 验证：

```bash
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_no_oa_legacy_repairs_have_no_direct_pair_write_fallback -q
PYTHONPATH=backend/src python3 -m pytest tests/test_no_oa_bank_batch_service.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_read_model_refresh.py tests/test_no_oa_bank_batch_api.py tests/test_no_oa_bank_batch_workbench_integration.py -q
```

- 七类测试覆盖：
  - Business core unit tests：适用并覆盖 legacy migration、submitted repair、旧 category drift 收敛边界、single-side consolidation、active row occupation 和同 row set case reuse。
  - Service-layer tests：适用并覆盖 no-OA service 到 relation command service 的委托、缺 command fail-fast 和 read model worker 不隐式 repair。
  - API contract tests：本阶段未改 HTTP response shape；通过 no-OA API 回归保护旧 contract。
  - Read model/cache/background job tests：适用并继续覆盖 worker refresh 不写 relation。
  - Frontend component and interaction tests：本阶段未改前端，未新增。
  - End-to-end business-flow integration tests：适用并通过 no-OA workbench integration 回归保护 no-OA/Workbench 同一 relation fact。
  - Existing feature regression tests：适用并保留 legacy salary/internal transfer、submitted 标签变化不改历史事实、snapshot round-trip 和 API 回归。
- 剩余风险：
  - 真实 PostgreSQL 历史数据的全量回放和 repair dry-run 仍需 staging/生产前 smoke。
  - relation command service 的生产级并发 row occupation 仍未引入 PostgreSQL 锁或唯一占用约束。
  - 前端跨页面即时反馈仍需完整浏览器 smoke；domain event 仍只是刷新提示，不是事实源。

## 2026-06-13 - fresh empty rows readiness 证明

- 目标：修复当前月份没有免 OA 候选时 API 持续返回 missing/refresh_enqueued，导致页面一直“同步中”或 authenticated HTTP SLO freshness gate 失败。
- 影响范围：`PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)`、no-OA list API 读取语义、HTTP SLO 默认 no-OA 探针。
- 关键决策：list 查询无 rows 时，只有 dirty scope 已 fresh 且 `read_model.app_status_readiness` 对 `no_oa_bank_batch/all` 为 fresh，才返回 `[]`；否则保持 `None`，让上层继续返回 refreshing 并入队真实刷新。
- 文档影响：更新本实施记录和测试矩阵。
- 测试覆盖：`tests/test_no_oa_bank_batch_workbench_integration.py::NoOaBankBatchWorkbenchIntegrationTests::test_no_oa_repository_returns_fresh_empty_rows_when_readiness_is_fresh`、`test_no_oa_repository_keeps_missing_when_readiness_is_absent_or_refreshing`。
- 验证命令：见最终交付说明。
- 未测风险：需要发布后用真实生产 readiness 行验证当前月份 empty state 不再被误判为 missing。
- 后续事项：若后续把 no-OA scope 从 `all` 拆到月份维度，必须同步更新 readiness 证明条件和测试。

## 2026-06-14 - no-OA 月度刷新和 Bankdetail 依赖状态闭环

- 目标：修复生产 App Status 中 Bankdetail 已同步但免 OA 批次长期 failed/blocker 的链路，避免 no-OA worker 因依赖 read model 暂未 fresh 被误标失败，并把刷新范围从全量收敛到月份。
- 根因：
  - `NoOaBankBatchReadModelRefreshService` 没有把 runtime event 的 `scope_key` 传给 application service，月份 dirty scope 实际读取 `all`。
  - `NoOaBankBatchApplicationService.refresh_batches(...)` 对同一批 rows 重复读取 Bankdetail effective categories，放大依赖读取和刷新时延。
  - `NoOaBankBatchService.build_batches(...)` 原本按完整 snapshot 替换；如果直接传入月度 rows，会误删其它月份批次。
  - `ReadModelReadinessReporter.record_event_failure(...)` 把 `bank_detail_read_model_not_fresh` 这类依赖等待记录为 `failed`，即使 runtime worker 后续会 defer/retry，也会污染 App Status current-effective blocker。
- 决策：
  - `no_oa_bank_batch` scope policy 明确只允许 `all` 或 `YYYY-MM`，防止 legacy/非法 scope 进入 durable queue。
  - Worker refresh 按 event scope 读取银行流水；月份 scope 只重建目标月份，并把其它月份现有批次合并回完整 snapshot 后保存。
  - effective category 对同一批 rows 只读一次；读完后显式装饰 row payload。
  - `*_read_model_not_fresh` 在 readiness 层记录为 `refreshing`，保留 last_error 诊断，但不升级为 failed blocker。
  - 月份查询空结果时，若目标月份 dirty scope 仍 pending/processing/failed，不允许用 `all` readiness 伪装 fresh empty；目标月自身 fresh 或 `all` fresh 且目标月无 dirty blocker 才能返回真实 `[]`。
- 验收测试：
  - `test_dependency_not_fresh_exception_records_refreshing_not_failed`
  - `test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches`
  - `test_refresh_reads_effective_categories_once_for_same_rows`
  - `test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only`
  - `test_no_oa_repository_does_not_treat_all_fresh_as_month_fresh_when_month_is_dirty`
  - `test_no_oa_repository_accepts_month_fresh_without_all_readiness_record`
- 七类测试覆盖：
  - Business core unit tests：本次未改业务批次生成规则，只改 refresh scope 和合并方式；由 no-OA read model refresh/integration 测试覆盖。
  - Service-layer tests：适用，覆盖 application service 对 scope_key、category provider 和 batch service 的调用。
  - API contract tests：本次未改 HTTP response shape。
  - Read model/cache/background job tests：适用，覆盖 dependency non-fresh、dirty scope、readiness、worker 月度 refresh 和 repository fresh-empty gate。
  - Frontend component and interaction tests：本次未改前端。
  - End-to-end business-flow integration tests：适用，通过 no-OA workbench integration 回归保护 no-OA/Workbench relation 事实。
  - Existing feature regression tests：适用，通过 runtime worker/readiness/gateway/App Status/no-OA 回归保护旧链路。

## 2026-06-25 - no-OA public snapshot FK 删除顺序修复

- 目标：修复生产 `no_oa_bank_batch.read_model.refresh` dead-letter。生产只读诊断显示 `no_oa_bank_batch:all` dirty scope pending，readiness failed，14 个 all-scope refresh event 因 `app.no_oa_bank_batch_events_no_oa_bank_batch_id_fkey` dead-letter；失败 UUID 对应一个 `superseded` 批次，仍有 6 条 event row 引用。
- 根因：`PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` 在替换 public snapshot 时，先删除缺席于新 snapshot 的 `app.no_oa_bank_batches`，再替换 event rows；当旧 `superseded/conflict/stale` 批次被清理但仍有 `app.no_oa_bank_batch_events.no_oa_bank_batch_id` 引用时，PostgreSQL 正确阻止删除。
- 决策：
  - 非空 snapshot：先删除将被移除批次的 `app.no_oa_bank_batch_events`，再删除对应 `app.no_oa_bank_batches`。
  - 空 snapshot：先清空 `app.no_oa_bank_batch_events`，再清空 `app.no_oa_bank_batches`。
  - 保留现有 retained batch upsert 与 `_replace_no_oa_bank_batch_events(...)` 行为；不改变业务状态、API shape、worker event、queue/readiness、relation command 或前端行为。
- 验收测试：
  - `test_no_oa_bank_batch_save_deletes_removed_events_before_removed_batches`
  - `test_no_oa_bank_batch_empty_snapshot_deletes_events_before_batches`
- 验证命令：

```bash
PYTHONPATH=backend/src pytest tests/test_postgres_repositories_boundaries.py -q
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/workbench.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh -v
bash scripts/verify.sh docs
git diff --check
```

- 七类测试覆盖：
  - Business core unit tests：不适用；未改批次状态机、分类或提交/撤回规则。
  - Service-layer tests：适用；repository boundary tests 锁定持久化顺序，read model refresh tests 覆盖 worker 调用路径。
  - API contract tests：不适用；HTTP contract 未变。
  - Read model/cache/background job tests：适用；生产故障路径是 worker refresh 持久化 public snapshot。
  - Frontend component and interaction tests：不适用；前端未变。
  - End-to-end business-flow integration tests：本地未新增；当前无 staging DB / local `PGSQL_URL`，生产收敛需后续受控 runbook。
  - Existing feature regression tests：适用；复跑 repository boundary 与 no-OA refresh 回归。
- 剩余风险：修复尚未部署；生产仍有 `no_oa_bank_batch:all` pending dirty scope、dead-lettered refresh event 和 failed readiness，需后续受控部署/收敛验证后才能声明生产闭环。

## 2026-06-25 - no-OA FK 修复生产部署与收敛

- 目标：将 FK 删除顺序修复发布到生产，并让 `no_oa_bank_batch:all` 从 pending/failed 收敛到 done/fresh。
- 发布：`./scripts/deploy-oa.sh --release-name dev-no-oa-fk-20260625014906` 成功，active release 为 `/opt/fin-ops/releases/dev-no-oa-fk-20260625014906/src`，`RELEASE.json.git_commit=cc43e262eeb13c1a459d0f96e991666d0db2f280`。
- 受控操作：发布后旧 event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` 仍为 `dead_lettered`，dirty scope 仍为 pending；T0 通过 active release runtime env 执行一次 exact event requeue，reason=`no_oa_fk_delete_order_fix_deployed`，返回 `requeued=true`。
- 收敛证据：
  - exact event 变为 `done`，`attempts=1`，`processed_at=2026-06-25 01:52:57.111992+08`。
  - `no_oa_bank_batch:all` dirty scope 变为 `done`，`source_version=35430`。
  - `read_model.app_status_readiness` 中 `no_oa_bank_batch:all` 为 `fresh`，`source_versions={"source_version": 35430}`。
  - `/health/ready` 返回 `status=ready`，`queue_backlog={}`，`failed_jobs=0`，`stale_dirty_scope_count=0`，required worker missing/stale/mismatch 均为 0。
  - no-OA worker 发布后日志抽样未出现新的 FK violation、dead-letter、PoolTimeout 或 shared-memory 错误。
- 未执行：没有手工 SQL 更新/删除、没有 mark-done、没有 broad replay、没有 repair `--apply`、没有输出 secret。
- 剩余风险：历史 obsolete `dead_lettered` rows 仍存在，但当前 `/health/ready` 不再把它们计为 blocker；如需清理，必须另开 bounded maintenance runbook。

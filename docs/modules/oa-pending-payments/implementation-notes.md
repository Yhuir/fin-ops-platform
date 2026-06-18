# OA待付款核对 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- OA 待付款列表以 OA application 为主行；银行流水、进项发票和 relation 只是付款证据或详情证据。
- Workbench active relation 是 OA/支出流水/进项发票关联关系的唯一事实源；多 OA、流水或发票在同一 relation 中必须聚合成一条核对行，并通过 `relationCount`/`summaries` 展开详情。
- `paymentStatus` 由 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` 判定，前端不得按金额字段自行推断。
- `paymentStatus` 不输出 `overpaid` 或 `merged_paid`；支出流水合计大于 OA 合计进入 `pending_review`，多 OA 合并付款先按 relation group 合计后再判定。
- `/oa-pending-payments` 通过 `view_mode=completed|in_progress` 承载同一页面的两类 OA：completed 是原待付款核对，in_progress 只展示 OA 系统仍进行中的支付申请/日常报销。
- completed 视图展示 OA、支付状态、支出流水和进项发票证据；in_progress 视图隐藏发票列，直到 relation 事实能证明发票证据。
- OA/支付状态/支出流水是表格主体的固定三段：OA 单元格内按“申请人 / 项目 / 金额”三栏展示，支出流水单元格内按“对方户名 / 金额 / 摘要”三栏展示；支付状态列保持窄列，只展示付款状态、可用确认动作和“未写回/已写回”。
- 进行中 OA 的候选流水不能自动写回；必须由用户点击“确认已支付”，后端校验 workflow/outflow/金额/flow_id 后确认 Workbench relation，并写回 OA MySQL `t_payment_simple.pay_status=1`。
- OA MySQL `t_payment_simple.flow_id` 使用 OA Mongo `form_data._id`。该结论来自 2026-06-17 服务器实机脱敏验证：现有 `t_payment_simple.flow_id` 为 24 位 ObjectId 形态，能匹配 Mongo `_id`，未匹配 Flowable `PROC_INST_ID_`；流程实例 ID 和流程请求 ID 只作为详情/诊断信息，不作为最终写回 ID。
- 生产 rows、filter-options 和 detail 必须走 `OaPendingPaymentReadModelService` 的 freshness/source-version gate；非 fresh 返回 refreshing/unavailable 并入队 `oa_pending_payment.read_model.refresh`，不能 live scan。
- `invoice-usage-collection` worker 同时负责 `input_invoice_usage`、`output_invoice_collection` 和 `oa_pending_payment` read model；OA all scope 只 fan-out month shards，不同步重建全量历史。
- `invoice-usage-collection` refresh handler 必须在 rebuild/fan-out 前校验 event source_version 是否仍为当前 dirty scope；旧事件只能返回 `skipped/stale_source_version`，不能覆盖较新的 read model。
- OA pending `all` scope 的 source version 判定优先从 `read_model.oa_pending_payment_rows` 的实际行聚合；只有完全没有实际行时才退回 scope 表，避免历史空月份 scope 把默认视图误判为 stale。
- 2026-06-17 生产已通过 release `main-e8de2711-20260617182353` 更新/重启服务器 `invoice-usage-collection` worker；后续不得只用本地手工 rebuild 代替标准 release/worker helper。
- 生产 OA MySQL 支付状态写回必须显式配置 `FIN_OPS_OA_PAYMENT_STATUS_*`。2026-06-17 已创建最小权限 MySQL 账号 `finops_oa_payment_status` 并写入 root-only 生产 env；该账号仅有 `smart_oa.t_payment_simple` 的 `SELECT`、`INSERT(flow_id, pay_status)`、`UPDATE(pay_status)` 权限。
- pending invoice rules 对 OA 待付款的刷新当前由执行层 workbench invalidation 间接入队 invoice usage collection，已有 `tests/test_pending_invoice_api.py` 回归保护；dry-run plan 的 domain 名称不直观，暂记为 documented-risk。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-18 - OA pending 主体三段表格内部布局调整

- 目标：按最新 UI 要求调整 OA 待付款核对的 completed/in-progress 表格主体，让 OA 区域内部固定展示申请人、项目、金额三栏；流水区域内部固定展示对方户名、金额、摘要三栏；支付状态列收窄并只展示“待支付/已支付”“确认已支付”和“未写回/已写回”。
- 影响范围：`OaPendingPaymentsTable`、表格 CSS、`OaPendingPaymentsPage.test.tsx` 和本模块测试/实施文档；后端 API、read model、付款判定和写回流程不变。
- 关键决策：保持 HTML 主表格仍以 OA、支付状态、流水为主体；completed 视图按既有状态机继续保留发票情况列，in-progress 视图继续隐藏发票列。写回状态不展示失败标签，外部依赖不可用仍只展示同步状态异常。
- 文档影响：更新本实施记录和 `tests.md`；长期 API/架构文档不适用。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 OA/流水内部三栏结构、流程状态 chip 文案、支付状态列宽、写回状态文案和缺流水 `-` 展示。

## 2026-06-18 - 修复进行中 OA 投影后页面不刷新的链路

- 目标：修复生产“OA 待付款核对 / 进行中 OA”为空。排查确认 Mongo 中 2026 年后存在进行中支付申请/日常报销，Postgres OA projection 与 `read_model.oa_pending_payment_rows` 中没有 `in_progress` 行；直接原因是生产未用当前 projection 逻辑重跑，且 `oa.sync` 完成后没有把 `oa_pending_payment` read model 标脏。
- 影响范围：`OAProjectionSyncService`、生产 `oa.sync` / `oa_pending_payment.read_model.refresh` worker drain、本模块测试文档。
- 关键决策：OA projection sync 仍是统一事实源；页面不 live scan Mongo。`oa.sync` 完成后必须同时 fan-out `workbench`、`search`、`pending_invoice` 和 `oa_pending_payment`，让进行中 OA 通过 worker/read model 进入页面。
- 测试覆盖：新增 `tests/test_oa_projection_sync_service.py`，锁定 `in_progress` OA 同步后会入队 `oa_pending_payment` 月份和 `all` refresh。
- 生产修复动作：部署后触发一次 `oa.sync:all`，确认 `app.oa_applications.workflow_status='in_progress'` 和 `read_model.oa_pending_payment_rows.oa_workflow_status='in_progress'` 均有数据。

## 2026-06-18 - OA pending completed 视图恢复发票证据列

- 目标：修复 Playwright smoke 暴露的回归：`oa-pending-payments` rows payload 已返回 `invoice.digitalInvoiceNo`，但表格只渲染 OA/支付状态/流水三列，导致真实浏览器首屏看不到发票号，也无法打开发票详情。
- 影响范围：`OaPendingPaymentsTable`、`OaPendingPaymentsPage`、表格 CSS、`OaPendingPaymentsPage.test.tsx`、本模块测试/实施文档；后端 API contract 不变。
- 关键决策：按状态机保留 view-mode 区分。`completed` 视图显示发票情况列，支持单发票详情和多发票 relation 明细；`in_progress` 视图继续隐藏发票列。表格展示层只消费后端 row payload，不自行推断发票状态。
- 文档影响：更新本实施记录和 `tests.md`；状态机既有“completed 视图保留 invoice detail 能力、in_progress 不展示发票列”的口径不变。
- 测试覆盖：更新 `web/src/test/OaPendingPaymentsPage.test.tsx`，覆盖 completed 发票列/发票筛选/开票日期排序/单发票详情/多发票 relation 明细，并保留 in-progress 隐藏发票列断言；`web/e2e/oa-pending-payments-flow.spec.ts` 重新通过。
- 验证命令：`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm run e2e:smoke`。
- 未测风险：未做真实大数据横向滚动截图；新增列宽由 deterministic browser smoke 和 Vitest 覆盖基本可读性，真实生产宽表仍需 staging/人工抽样。

## 2026-06-17 - OA 支付状态 MySQL 写回生产配置闭环

- 目标：解除 Phase 08 最后一项生产 blocker，使“进行中 OA 确认已支付”具备可用的 OA MySQL 写回路径。
- 影响范围：生产 MySQL `smart_oa.t_payment_simple` 最小权限账号、`/etc/fin-ops/fin-ops.secrets.env`、fin-ops API/worker/dispatcher 重启、`oa_pending_payment` read model refresh。
- 关键决策：不重置 MySQL root；通过一次 MySQL init-file 重启创建 `finops_oa_payment_status` 的 `127.0.0.1` 和 `localhost` host entry；临时 init-file/drop-in 创建后立即删除；验证写权限使用事务 rollback，不落业务 probe 行。
- 文档影响：更新本实施记录；`deploy/oa/README.md` 保留后续运维 runbook。
- 测试覆盖：生产侧验证 `MySQLOAPaymentStatusRepository.from_environment()` 可实例化并读取 sentinel flow_id；MySQL 最小权限账号对 `t_payment_simple` 的读、插入、更新通过 rollback smoke；`MySQLOAPaymentStatusRepository.mark_paid()` 真实 SQL 路径通过 rollback-on-commit smoke；重启后 `oa_pending_payment:all` durable refresh 由生产 worker 消费。
- 验证命令：root SSH 生产脚本创建账号并执行 PyMySQL rollback smoke；`sudo -n /usr/local/sbin/finops-deploy-control restart`；生产 env repository smoke；`/fin-ops-api/health/ready`；投递 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：`finops_oa_payment_status@127.0.0.1` 与 `finops_oa_payment_status@localhost` 均可读取 `smart_oa.t_payment_simple`，事务内 insert/update 后 rollback 剩余 probe 行数为 `0`；`SHOW GRANTS FOR CURRENT_USER()` 显示 `USAGE` 以及 `SELECT, INSERT(flow_id, pay_status), UPDATE(pay_status)` on `smart_oa.t_payment_simple`。生产 env 七个 `FIN_OPS_OA_PAYMENT_STATUS_*` key 均存在，repository configured/read_ok；`mark_paid()` rollback-on-commit smoke 返回 `pay_status=1` 且 probe 剩余行数为 `0`。
- Worker 证据：重启后 source_version `123` 的 `oa_pending_payment.read_model.refresh` event `a8a7eee2-04ff-4033-8f07-7276f0c1ccd2` 已 `done`，dirty scope `done`，月份 shard 更新在 `2026-06-17 18:44:56` 至 `18:44:58`，`invoice-usage-collection` heartbeat current。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `210`。当前仍没有可执行真实 confirm-paid 的进行中 OA 行，因此没有改动真实业务支付状态；写回能力通过生产权限和 rollback smoke 验证。
- 未测风险：真实用户点击 confirm-paid 需要未来出现一条真实进行中 OA + 支出流水候选/关系时再做业务级 smoke；当前生产事实数据没有 in-progress 行可用于不造数验证。
- 后续事项：当出现真实进行中 OA 样本时，执行一次确认已支付，核对 `t_payment_simple.flow_id=<OA Mongo form_data._id>` 最新记录 `pay_status=1`，并核对页面 `oaPaymentWriteback.label=已写回`。

## 2026-06-17 - Phase 08 生产发布与 worker smoke

- 目标：按 GSD 主控闭环完成 Phase 08 发布后验证，确认进行中 OA 视图的生产 read model/worker/页面数据路径不是只在本地可用。
- 影响范围：生产 release、PostgreSQL durable queue、`invoice-usage-collection` worker、`oa_pending_payment` read model、公开前端入口和 OA MySQL 写回配置核验。
- 关键决策：生产 smoke 使用 `ReadModelRefreshGateway` 入队 `oa_pending_payment:all`，等待已部署 worker 消费；不通过手工 rebuild 伪造 fresh。支付状态 MySQL 只做只读连通性核验，不在没有样本 flow_id 时写入。
- 文档影响：更新本实施记录，明确生产 release 已闭合以及 OA MySQL 写回 env/凭据仍未闭合。
- 测试覆盖：沿用 Phase 08 后端 service/API/read model、migration/boundary、前端 Vitest 和 docs/build 验证；生产侧补 durable queue smoke 和 repository 同源读取。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`bash scripts/verify.sh docs`；`cd web && npm run build`；`./scripts/deploy-oa.sh --dry-run`；`./scripts/deploy-oa.sh`；生产入队 `oa_pending_payment:all` refresh 并查询 `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.oa_pending_payment_*`。
- 运行时证据：生产 release metadata 为 `main-e8de2711-20260617182353` / commit `e8de27118e15403ff0b256a6c40ab82b13a69932`；`/fin-ops-api/health/ready.status=ready`，runtime release consistent；deploy-control 显示 API、dispatcher 和 `fin-ops-worker@invoice-usage-collection.service` active。post-deploy event `cade4a8b-d7e3-40f8-a704-9b591803dbf0` source_version `122` 已 `done`，all scope fan-out 到 `2026-06` 至 `2025-12` month shards，最近生产 rows 更新在 `2026-06-17 18:27:19` 至 `18:27:21`。
- 数据结论：生产 repository 同源读取 `view_mode=in_progress` 为 fresh、total `0`；`view_mode=completed` 为 fresh、total `211`。当前进行中视图空表是 OA 投影事实数据，不是页面未加载。
- 未测风险：当时未能完成生产 OA MySQL 写回配置验证；文件层已确认目标表在 MySQL datadir 的 `smart_oa/t_payment_simple.ibd`，但缺少可用 MySQL 管理凭据。该 blocker 已由后续“OA 支付状态 MySQL 写回生产配置闭环”记录解除。
- 后续事项：已由后续记录补齐最小权限账号、生产 env、只读 repository smoke 和 rollback 写权限 smoke；真实业务级 confirm-paid smoke 仍需等待生产出现进行中 OA 样本。

## 2026-06-17 - OA pending read model runtime freshness 闭环

- 目标：修复 Phase 08 runtime smoke 中发现的默认 `all` 视图持续 `refreshing`、手工 v3 rebuild 后又被旧刷新路径写回 v1/空 workflow status 的问题。
- 影响范围：`InvoiceUsageCollectionReadModelRefreshService`、`PostgresReadModelRepository.list_oa_pending_payment_rows`、`Application.rebuild_oa_pending_payment_read_model_scope` 兼容路径、SQL runtime 测试、生产发布/worker 运维。
- 关键决策：刷新事件处理前复用 durable queue 的 `read_model_refresh_is_current` guard；stale event 不 rebuild、不 complete dirty scope；OA pending `all` freshness 优先从实际 rows 的 `source_versions` 聚合，历史空 scope 不参与有行视图的新鲜度证明。
- 文档影响：更新本模块 implementation-notes、tests、state-machine；生产发布仍按 `scripts/deploy-oa.sh`，不能手工绕过 release/worker helper。
- 测试覆盖：新增/更新 `tests/test_invoice_usage_collection_sql_runtime.py::test_oa_refresh_handler_skips_stale_source_version_before_rebuild`、`test_oa_repository_all_scope_aggregates_monthly_scope_source_versions`，以及 `tests/test_oa_pending_payment_api.py::test_legacy_application_rebuild_includes_completed_and_in_progress_rows`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_oa_pending_payment_api tests.test_oa_pending_payment_service tests.test_oa_payment_status_service tests.test_oa_pending_payment_command_service tests.test_oa_projection_sql_runtime tests.test_mongo_oa_adapter -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations tests.test_platform_runtime_boundary_guards -v`；`cd web && npm test -- OaPendingPaymentsPage.test.tsx --run`；`cd web && npm run build`；本地 Playwright 打开 `/oa-pending-payments` 并切换“进行中 OA”。
- 运行时证据：当前源码 rebuild 后 7 个活跃月份 scope 均写入 `oa-pending-payment:v3` / `2026-06-17-workflow-status-v1`；HTTP smoke 显示 `view_mode=in_progress` fresh 且 total=0、`view_mode=completed` fresh 且 total=210。当前 OA projection 没有 `in_progress` 行，因此页面空表是事实数据，不是未加载。
- 未测风险：生产服务器 heartbeat 显示 `invoice-usage-collection` worker 仍在运行旧部署；未完成 release activate 前，服务器 worker 可能继续用旧逻辑覆盖 read model。由于当前工作树包含未提交 Phase 08 改动，`scripts/deploy-oa.sh` 标准发布会拒绝 dirty worktree，必须先提交/发布/重启 worker 后再做生产 smoke。
- 后续事项：完成干净 release 发布后，重跑 `oa_pending_payment:all` refresh，确认 worker heartbeat 更新时间、scope source versions、HTTP rows/filter-options 和页面空态/数据态一致。

## 2026-06-17 - 进行中 OA 支付确认与 OA 写回

- 目标：在 OA 待付款核对页新增 `已完成 OA / 进行中 OA` 切换，把进行中支付申请/日常报销拉入三列视图，并支持候选流水确认后写回 OA 支付状态。
- 影响范围：OA Mongo adapter/projection、OA pending payment query/read model/service/API、OA MySQL payment status adapter、Workbench relation confirm command、`OaPendingPaymentsPage`/table/API types/styles、模块/产品/API 文档和相关测试。
- 关键决策：继续复用 Workbench relation 作为关联事实源；candidate relation 只展示证据和确认按钮，不直接判定 `paid` 或写回；confirm-paid 后端负责金额相等、outflow、workflow_status、flow_id 和 relation command 校验，页面只提交用户确认。
- 文档影响：更新本模块 README、state-machine、tests、implementation-notes，并同步 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/app-architecture/pages.md`。
- 测试覆盖：新增/更新 `tests/test_oa_payment_status_service.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_command_service.py`、`tests/test_oa_pending_payment_api.py` 和 `web/src/test/OaPendingPaymentsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_payment_status_service tests.test_mongo_oa_adapter.MongoOAAdapterTests.test_list_application_records_maps_payment_requests_and_reimbursement_details tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_external_oa_mysql_client_is_confined_to_role_sync_adapter tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_raw_postgres_sql_in_services_is_classified_by_platform_boundary -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_command_service tests.test_oa_pending_payment_api -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA MySQL/Mongo，不覆盖真实网络超时、账号权限、生产锁等待、真实 OA 字段变体和 worker drain；需要 staging 用真实进行中 OA、候选流水和 `t_payment_simple` 样本 smoke。
- 后续事项：部署前配置 `FIN_OPS_OA_PAYMENT_STATUS_*` 环境变量并在 staging 验证 `flow_id` 解析命中率、confirm-paid 审计链和 2 秒目标 refresh。

## 2026-06-17 - OA待付款Browser e2e闭环

- 目标：补齐 OA 待付款核对页面真实浏览器层的首屏、筛选/排序和详情抽屉保护，降低只靠 Vitest 时漏掉实际导航、drawer、请求参数编码或规则抽屉复用 endpoint 回归的风险。
- 影响范围：Playwright deterministic API mocks、`web/e2e/oa-pending-payments-flow.spec.ts`、smoke 脚本和 OA 待付款测试文档；后端业务代码和 API 契约不变。
- 关键决策：本轮选择只读高价值链路，覆盖 rows/filter-options、搜索、支付状态筛选、交易时间排序、OA/流水/发票详情和支出流水无需开票规则抽屉；真实 OA/Mongo、真实 Postgres 和 worker drain 仍留给 staging/生产 smoke。
- 文档影响：更新本模块 `tests.md`、`state-machine.md`，并同步 `docs/dev/testing.md`、`docs/dev/nightly-ci.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：新增 `web/e2e/oa-pending-payments-flow.spec.ts`，并加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/oa-pending-payments-flow.spec.ts`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`。
- 未测风险：真实 OA/Mongo 字段变体、真实生产 PostgreSQL 大数据 EXPLAIN/锁等待/长分页、真实 RabbitMQ/Redis/systemd worker drain、虚拟滚动压力、像素级视觉和网络中断恢复仍需 staging/生产 smoke。
- 后续事项：继续按 fan-out 风险补 `no-oa-bank-batches` 等页面的 Browser e2e。

## 2026-06-16 - 首屏 page-size 性能护栏证据

- 目标：补齐 P2/P3 大数据列表本地 synthetic SLO 与前端首屏请求证据，防止 OA 待付款核对首屏请求把超大 page size 透传为全量读取。
- 影响范围：`OaPendingPaymentQueryService.list_rows` 的分页 contract、`OaPendingPaymentsPage` 首屏 rows 请求回归和模块测试矩阵；业务行为不变。
- 关键决策：保留现有严格上限语义，`page_size=200` 为最大允许页大小，`page_size>200` 返回 `invalid_paging`，不做静默 clamp；前端默认继续使用更保守的 `page_size=20`，页大小选项限制为 20/50/100。
- 文档影响：更新 `tests.md` 与 P2/P3 closure ledger。
- 测试覆盖：新增 `OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo`，用 250 行 synthetic 数据验证 200 行上限、total 保留和超限错误；更新 `web/src/test/OaPendingPaymentsPage.test.tsx` 锁定首屏 `page=1&page_size=20` 和 20/50/100 页大小选项。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service.OaPendingPaymentQueryServiceTests.test_page_size_limit_protects_first_screen_slo -v`；`npm --prefix web test -- --run src/test/InputInvoiceUsagePage.test.tsx src/test/OutputInvoiceCollectionsPage.test.tsx src/test/OaPendingPaymentsPage.test.tsx`。
- 未测风险：真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动和网络中断恢复仍需 staging/production smoke。
- 后续事项：如 API 层改变 page size 映射，必须同步保留 `invalid_paging` 或等价 fail-closed contract。

## 2026-06-11 - OA待付款关联台分组关系闭环

- 目标：修复多条 OA/支出流水/进项发票在关联台已清晰配对时，OA 待付款页拆成多行并误显示“支付多了”或“多条OA合并支付”的问题。
- 影响范围：`InvoiceLifecyclePolicy`、`OaPendingPaymentQueryService`、OA pending payment read model detail builder、SQL projection 复用路径、`/api/oa-pending-payments/rows/{row_id}/relation-details`、`OaPendingPaymentsTable`、前端 OA pending payments 类型、模块/API 文档和相关测试。
- 关键决策：关联关系完全来自 Workbench active relation；同一 relation 下的 OA、有效 outflow 支出流水和进项发票分别汇总为一条核对行，列表只显示合计金额和 `+N`，点击 `+N` 分别以 `kind=oa|bank|invoice` 查看明细。
- 文档影响：更新模块状态机、测试矩阵、实施记录、产品口径和 API 合同。
- 测试覆盖：新增/更新 lifecycle policy、query service、API/read model detail、SQL projection runtime 和前端交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_invoice_lifecycle_policy tests.test_oa_pending_payment_api tests.test_invoice_usage_collection_sql_runtime -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx`；`cd web && npm run build`。
- 未测风险：未连接真实 OA/Mongo、生产 Postgres 大数据、真实 RabbitMQ/Redis/systemd worker drain 和真实浏览器截图 smoke。
- 后续事项：如需发布前进一步验证，使用截图中的真实月份在 staging 触发 relation 确认/撤回、`oa_pending_payment` scope refresh 和页面浏览器 smoke。

## 2026-06-11 - OA待付款测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `oa-pending-payments` 模块轮次，确认 OA 单据、支出流水、进项发票、Workbench relation、SQL read model、worker 和前端交互的回归保护。
- 影响范围：`docs/modules/oa-pending-payments/README.md`、`docs/modules/oa-pending-payments/tests.md`、`docs/modules/oa-pending-payments/state-machine.md`、`docs/modules/oa-pending-payments/implementation-notes.md`；未改变业务代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖付款状态、缺失证据、API shape、权限、read model freshness、detail stale/missing、SQL projection/repository、worker fan-out、App Status registry 和前端交互；本轮不新增重复测试。
- 文档影响：补齐模块必读事实源、代码入口、七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/TableAlignmentStyles.test.ts`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_service tests.test_oa_pending_payment_api tests.test_invoice_lifecycle_page_integration -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_runtime_worker_registry -v`；`cd web && npm test -- --run src/test/OaPendingPaymentsPage.test.tsx src/test/TableAlignmentStyles.test.ts`。
- 未测风险：未连接真实 OA/Mongo，不验证真实 OA sync 字段变体和权限菜单；未在真实生产 Postgres 跑大数据 EXPLAIN/锁等待/长分页；未跑真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain；未做真实浏览器大数据表格和网络中断 smoke。
- 后续事项：下一轮处理 `turnover-ledger`，重点审计手动闭环、extra、relation stale precondition、read model freshness 和前端筛选/抽屉交互。

# 外部往来款管理性能实施计划

日期：2026-07-20

## 目标

在不改变业务口径、API shape、canonical 写入、共享 gateway/worker 和其他页面 read model 的前提下，把外部往来款列表改为有界读取，修复 all-scope freshness 证明，并完整删除旧 live fallback、dead clear port 和 raw payload 双写。

## 任务 1：先固化合同测试

- 扩展 repository fake/真实 PostgreSQL 测试，覆盖 family/status/direction/filter-empty、金额 fallback、四个 family 汇总、稳定排序、分页 total 和 mixed source versions。
- 增加 all-scope dirty 聚合：fresh、pending、processing、failed 及混合优先级。
- query service 测试改为 fail-closed：repository miss 必须返回 refreshing 并 enqueue，不再存在 optional legacy path。
- port/manifest/architecture guard 固化只暴露 `list_turnover_ledger_view`、`save_turnover_ledger_rows`。
- projection 持久化测试证明 `payload` 是唯一规范化读取列，`raw_payload` 不再复制 payload。

## 任务 2：有界 SQL 查询

- 在 `PostgresSummaryReadModelRepository.list_turnover_ledger_view` 内建立 turnover 专属固定 CTE。
- family/status/scope/direction 全部在 SQL 中过滤；direction 语义与当前 Python 判断完全一致。
- 第一次 query 只返回总 summary、四个 family summary、total、source_versions/mixed proof 和“该 scope 是否已构建”的存在性。
- 第二次 query 只返回当前 page 的 `payload`，保持 `scope_month desc nulls last, generated_at desc, relation_id` 排序。
- 筛选为空但 read model 已存在时返回 fresh 空 payload；真正未构建时返回 `None` 交给 gateway enqueue。
- 删除列表对 `raw_payload` 的读取和 Python 全量 rows 汇总/分页。

## 任务 3：all-scope freshness 完整证明

- 增加 turnover 专属 `_turnover_ledger_refresh_status(scope_key)`。
- 非 all 保持精确 scope 查询；all 聚合所有 turnover dirty scopes：任一 failed → stale，否则任一 pending/processing → refreshing，否则 fresh。
- 不改 shared `_refresh_status` 和 `ReadModelQueryGateway`，避免影响其他页面。

## 任务 4：删除旧代码并升级 projection schema

- 删除 `TurnoverLedgerQueryService` 的 `legacy_payload_builder`、`settings_provider`、`_postgres_required` 及 server 注入。
- repository 不可用或 miss 时统一 fail closed，经正式 gateway enqueue；不保留 hidden fallback。
- 删除 `clear_turnover_ledger_rows` 的 narrow port、summary repository、broad wrapper、manifest、fake/test/docs 合同。
- `save_turnover_ledger_rows` 只写规范化 `payload`，`raw_payload` 写空对象；query 不再调用 generic raw fallback。
- `TURNOVER_LEDGER_SCHEMA_VERSION` 从 v5 bump 到 `2026-07-turnover-ledger-v6`，部署后只通过 gateway/worker 重建。
- whole-repo symbol/text scan 证明生产旧入口为零。

## 任务 5：文档影响

- 更新 turnover-ledger `README.md`、`boundary-io.md`、`tests.md`、`implementation-notes.md`。
- 更新 read-model contracts、read-model module boundary/tests/implementation notes 和 manifest 事实。
- 产品口径、权限和 UI 不变；现代 closure response shape 与撤回选择合同因删除重复事实而变化，必须同步 API contract、模块状态机和 smoke scenario。前端 mapper 已兼容无 `turnover_relation` 响应，不新增 UI 分支。

## 任务 6：本地验证

按风险最小集合运行：

1. Business core：既有 turnover 汇总/方向/金额/状态规则回归；不新增业务规则。
2. Service：query fail-closed、source-version normalization、refresh enqueue、port boundary。
3. API contract：完整 turnover API 测试，验证 grouped/list/audit shape 与权限。
4. Read model/cache/job：repository SQL、projection refresh、source versions、manifest、dirty status、真实 PostgreSQL。
5. Frontend：TurnoverLedger API/Page/operation barrier 现有测试；前端无实现变更。
6. E2E：现有 turnover/relation 关键流；生产再做安全可逆写入。
7. Regression：architecture guard、shared read-model consumers 的目标测试与 Page Audit。

同时运行 `bash scripts/verify.sh lint`、相关 docs check、`git diff --check`。不运行与本页无关的重复全仓 CI。

## 任务 7：提交、部署与生产闭环

- clean diff 后 commit 并 push `main`。
- 使用 `./scripts/deploy-oa.sh` 部署精确 SHA，不手工改生产数据库。
- 通过正式 read-model control/gateway 触发 turnover all fan-out rebuild；等待全部月份 fresh、queue drained。
- authenticated 40-sample：shell、grouped、tag selection、Page Audit。
- 验证 schema v6、row count、raw payload 不再复制、child dirty 聚合与 query timing。
- 做 turnover 直接 Audit，以及 reconciliation-workbench、bank-details、cost-statistics、oa-pending-payments 交叉 Audit。
- 若安全 fixture 仍有效，执行唯一 idempotency key 的 closure confirm→fresh→withdraw→fresh，最终确认没有残留 active relation；否则把写验证保留为最终系统门并说明证据缺口。

## 回滚

- 应用或性能不达标：部署上一精确 release。
- 本轮无 migration、无 canonical 数据迁移；v6 只是 read-model schema version。
- 新 projection 的规范化 `payload` 与旧 reader 兼容；`raw_payload={}` 不影响旧 reader 因其优先读取 `payload`。
- 不直接恢复/修改 read-model 表；回滚后由正式 gateway 按旧 expected versions 重建。

## 第三次计划反审阅

- 生产级：freshness、权限/契约保持、审计、schema 重建、回滚和生产读写验证齐全。
- 模块化：修改局限于 turnover query/projection owner；共享事实只读，共享 gateway 行为不变。
- 简洁：只有一个专属查询 CTE、一个专属 freshness helper 和旧链删除；无新基础设施或通用抽象。
- 高性能：分页 payload 读取受 page size 约束，汇总在数据库完成，去除重复 raw JSON。
- 旧链删除：live fallback、settings switch、dead clear port、raw payload fallback/双写均有 whole-repo guard。
- 隔离：其他页面 API、port、SQL、read model、worker、command 不变，并有交叉 Audit。
- 闭环：测试、文档、提交、部署、重建、40 样本、可逆写验证和回滚条件明确。

审阅结论：计划满足要求，没有遗漏，也没有需要新增的层。实施期间若 SQL 等价测试不能证明业务语义，必须停止并缩小修改，不能用 fallback 绕过。

## 发布后补充修复计划（写入门失败）

1. command I/O 收窄：为 turnover confirm/withdraw 增加按 transaction ids 读取银行 read-model 行的 provider；stale precondition 与 relation domain refresh 只读取所选行，不再扫描全部月份。
2. relation 单事实持久化：`TurnoverRelationService` 增加只替换指定银行行输入而不重建全部自动 relation 的公开 domain 操作；PostgreSQL repository 增加单 relation + 单 audit event 的原子 upsert；`TurnoverLedgerRelationWritePort` 删除全量 rebuild/full-snapshot save。
3. projection 去串行等待：turnover projection 直接通过已有窄 repository I/O 读取 canonical active pair relation rows 与 source summary；删除 `WorkbenchRelationReadFacade` 依赖，不等待另一 read model 发布，也不写同步 read model。
4. 旧链门禁：production scan 必须证明 confirm/withdraw 不再调用 `_turnover_bank_transaction_rows()` 全量 provider、`_rebuild_relation_snapshot`、full `save_turnover_relations` 或 turnover projection relation read-model facade。
5. 验证：先跑 domain/UoW/repository/worker/API/architecture 目标测试与真实 PostgreSQL；部署精确 SHA 后重建 turnover scopes，跑 40 次读取、直接/交叉 Audit，再执行至少两组 test-owned confirm→fresh→withdraw→fresh。门槛保持 command p95 `<=1000ms`、response-to-fresh p95 `<=2000ms`、hard max `3000ms`；不通过则继续本页闭环，不能进入下一页。

## 最终实施增补：canonical 单事实闭环

1. `TurnoverRelationService.preview_zero_difference_closure(...)` 复用既有业务规则，只返回确定性 closure descriptor，不改变 relation/audit snapshot。
2. `/closures/confirm` 的 UoW 只持久化 `app.workbench_pair_relations` 与 history；删除现代链路对 `app.turnover_relations` / `app.turnover_relation_events` 的重复写入和响应字段。
3. 新闭环统一捕获 `workbench_pair_relation.case_id` 并调用 `/closures/withdraw`；撤回事务内重新验证 active members 仅为 `oa/bank` 且至少两条 bank rows。
4. `cash_closure_relation_id` 只从显式 legacy metadata 读取，不从 case id 猜测，保证历史兼容与现代链路隔离。
5. 删除无收益的 `turnover-ledger-secondary` registry、manifest、env、部署文档和测试；保持单 worker，不新增基础设施。
6. 本地门：domain/service/API/read-model/job/E2E contract、runtime registry/manifest、前端 page/API、architecture guard、lint/docs/diff。生产门：精确 SHA 部署、旧 worker 退役、两轮可逆写、40 轮读、直接/交叉 Audit、queue drained、fixture 恢复。

## 第二次生产门补充：changed-case 镜像限域

1. 生产两轮探针证明热态 read-model response-to-fresh 已小于 2s，但同步 command 仍为 `1.759–2.684s`；AppHealth 把热态数据库时间定位在约 `0.67s`，剩余开销集中在 canonical relation save 后的全量进程镜像重建。
2. 在 `WorkbenchPairRelationService` 提供单一 `apply_snapshot_delta` domain I/O；只归一化 incoming scoped snapshot，按 changed case replace/delete relation 与 history。
3. 删除 adapter 的全局 `snapshot()`、无关 relation/history 深拷贝、全量 `from_snapshot()` 重建与私有状态写入；无新缓存、worker、read model、API 或事实源。
4. 先以测试证明无关 case/history 保持、删除语义与“禁止读取全局 snapshot”；通过共享 relation command 回归后提交、部署并复用同一可逆探针。

## 第三次生产门补充：active case 窄读取

1. release `b4fce65f8` 已证明 changed-case apply 有效：热态 confirm `0.804–1.025s`，但 withdraw 仍为 `1.530–1.757s`，首轮冷态 command/fresh 仍超过 hard max。
2. 真实调用图证明 withdraw 事务前的 case 校验在无 transaction repository 时进入 adapter 全局 snapshot fallback；事务内预检也为只读 active relation 加载完整 history。
3. 在 canonical repository/adapter 增加单行 active-case read I/O，command service 优先使用；in-memory fallback 直接查 case。mutation 仍保留事务锁、history restore 与全部 outbox。
4. 删除无一致性价值的 adapter after-apply exception-service 重建回调；guard 禁止恢复全局 snapshot fallback、history 读和 after-apply callback。

## 第四次生产门补充：command history append-only delta

1. release `f18f62136` 的三轮生产探针证明 withdraw 已达到 `0.787–0.999s`，但 confirm 首轮 `6.030s`、热态 `1.004–1.211s`；剩余同步热点是 confirm overlap 通用读取加载全部 case history，以及 save 删除后重写完整 history。
2. 增加 active row/case overlap 窄读端口，confirm 只读取 active canonical relations，不读取 cancelled facts/history；withdraw 恢复逻辑继续按需读取相关 history。
3. command 统一输出 changed relations + 本次 history events；PostgreSQL 同事务 append/idempotent upsert 新 history，不 delete/rewrite 旧历史；进程镜像按 operation id 追加去重。
4. 在线 command 删除 full snapshot/history save 调用；full replacement 仅留给 migration/repair/restore。用 domain、adapter、command、SQL statement-count 与 architecture guard 证明旧链不能回流，然后部署精确 SHA 复跑同一三轮生产门。

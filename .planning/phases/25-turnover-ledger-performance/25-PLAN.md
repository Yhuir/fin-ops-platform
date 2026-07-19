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
- 产品口径、API response shape、权限、状态机和 UI 不变，因此 product spec、API contract 与前端文档无需改动；如实现核验发现事实变化，再做最小更新。

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

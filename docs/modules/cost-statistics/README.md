# 成本统计 模块维护入口


- Module key: `cost-statistics`
- 类型: 页面模块
- Route: `/cost-statistics`
- Page key: `cost-statistics`

## 修改前必读

- `docs/product-specs/cost-tax.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/components/cost-statistics/*`
- `web/src/features/cost-statistics/*`
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_source_versions.py`
- `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/cost_statistics_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/cost_statistics_bank_tags.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/cost_statistics_page_audit.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/cost_statistics_sql_projection.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

关注项目范围、费用归因、导出 shape、成本统计标签规则、cost read model freshness 和 query/runtime I/O。成本统计 read model refresh scope 必须是 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 或 `all:all`；旧的裸月份/裸 `all` 只能在统一 read model refresh scope gateway 中归一化，不能直接进入 durable queue。生产旧 readiness、dirty scope 或 outbox 中残留的裸 scope 使用 `scripts/check-read-model-scope-contracts.py` 检查和受控清理。

模块状态为 `READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD`：API/query miss 只返回 `refreshing` 并入队 `cost_statistics.read_model.refresh`，不再同步调用 live builder 或本地 read model fallback；legacy live service、本地 read model、warmup job、旧 summary/project HTTP contract、full-view loader、无版本 Redis writer 和混合 cost/tax owner 均已删除。成本归集规则只由 `CostStatisticsSqlProjectionBuilder` 构建并写入 SQL read model。

生产刷新由专用 `cost-statistics` RabbitMQ consumer 承担独立性能 lane；旧 `cost-tax` 成本统计兼容消费者已移除，`cost-tax` 只保留税金抵扣兼容链路。当前 P2/P3 closure 按首屏 API 或 direct refresh p95 <= 1000ms 验收，写操作链路还要求 operation-to-fresh p99 <= 3000ms。`cost_statistics` freshness 仍以 PostgreSQL dirty scope/outbox/readiness 为事实源，不能为了达标把 stale 伪装成 fresh。

月度 scope projection 只能消费对应 `read_model.workbench_generations` 的 active generation，并必须把 active generation 的 `source_versions` 纳入自身 `source_versions`。禁止直接按 `scope_key` 扫描 `read_model.workbench_groups` / `workbench_rows` 的历史 generation；父 scope shard 枚举也只能来自 active `workbench_generations`。当 SQL read model 的 `source_versions` 完全一致时，worker 可以返回 `skipped/source_versions_unchanged`，不得扫描 Workbench groups 或重写 payload；该判定只允许通过 `get_cost_statistics_scope_metadata(...)` 按 scope 读取 parent `entry_count + source_versions`，不得调用 full-view loader、读取两张明细表或页面 dependency gate。缺少 metadata 接口或版本不一致时必须按 active generation 重建。

2026-07-13 后成本统计页面有两组统计口径：`按项目`、`按银行`、`按OA费用类型` 是 OA 配对支出流水统计；`按标签`、`按时间` 是全银行收支流水统计。2026-07-16 起页面不再接收两类完整 row arrays，而是通过原 explorer endpoint 的 `scope/view/filter/cursor` 合同读取服务端 summary/facets 和 bounded rows；统计口径不变。全流水视图不显示收入与支出的合并总金额：页面顶部、主标签和子标签均分别显示正数绝对值的“支出金额 / 收入金额”，同时分别显示笔数；收入使用绿色，支出使用橘色，流水明细保留资金方向和该笔金额。成本统计标签规则由右侧紧凑抽屉维护，收入与支出标签都可选择；旧显式选择在 selection schema v2 归一化时保留原支出选择并一次性加入当前有效收入标签。保存规则只持久化 app settings，不触发 read model rebuild。

2026-07-14 起五个统计分类与“成本统计”标题同排，当前视图的时间范围和金额摘要位于下一行且范围控件固定在最左。OA 配对三类汇总和列表金额统一显式标注“支出”；按标签的收支标签左对齐、金额右对齐。项目、银行、OA 费用类型和标签四种下钻表不再保留独立“时间”列，而是在“对方户名”或“项目名”下方显示时间 chip；桌面端 explorer 各栏共享同一高度并独立滚动。`按时间`主表仍保留独立时间列，因为时间是该视图的主维度。

2026-07-16 起成本页用唯一 `effectiveCostPageState` 合并当前 explorer lifecycle、explorer freshness envelope、App Status 中精确 `cost_statistics + active scope` 和标签规则 operation barrier。只有明确 `fresh` 才开放成本业务操作；loading/refreshing/stale/unavailable/error 使用页面内内联状态轨、原生 `inert` 和约 80% 透明的 cost-local 拦截层。它不是 dialog，没有实色 card、背景模糊或任何遮罩/状态装饰动画；标题、Audit、App Shell 和导航始终在锁定边界外。进入锁定会关闭成本页自有详情/导出 portal，标签规则抽屉保留草稿但锁定 body/footer；focus、visibility 与 BFCache 返回都会先重校验。

2026-07-16 起成本页面 Audit 的唯一 owner 是 `cost_statistics_page_audit.py`。统一 page key、通用只读 CLI 与 System Audit 都直接分派给该 owner，并继续复用 caller-owned repeatable-read read-only snapshot；共享 `page_business_audit.py` 不再包含成本合同、SQL、issue mapping 或 dependency dispatch。05-09 已把 summary/dirty/outbox 合为一次查询，复用 Workbench collector 已执行的 relation equality，并跳过成本调用后会丢弃的 Workbench generation summary I/O；05-10 又把 row/scope、月度上游和 parent shard 三类 source-version 证明从三次往返合为一次集合 SQL。05-16 将关键字段、bank-flow 字段、scope summary、project/expense summary 和 bank accounts 五类业务值证明合为一个 `cost_business_value_proofs` statement；每个分支仍独立 limit 并保留原 issue contract。05-17 删除 canonical expected-set、bank-flow 字段和 scope summary 中最后 3 处 parent JSON bank-flow array 读取；投影完整性、字段和父级汇总证明现在只读 `cost_statistics_bank_flow_rows` 的类型化字段，父 scope 按 concrete month rows 逻辑 rollup。05-18 又把 scope row count、missing scope、duplicate identity 和 canonical expected-set 四个入口合为一个 `cost_exact_set_proofs` statement，四分支仍各自 bounded，并删除旧四 helper 与无调用通用 proof helper。成本 owner 现在只有 queue/readiness、source-version、exact-set、business-values 四组集合 SQL；包含 active relation、会真实触发 group-row proof 的固定本地总预算由旧实现的 36 依次降到 32、30、26、23。统一部署后的 cost-local timing 将生产慢点定位到 `exact_set` 的 Workbench bank member 身份解析；该私有 SQL 已把 `bank_transactions.id::text OR legacy_mongo_id` 扫描改为 UUID 主键和 legacy 唯一键的两个 equality probe，不新增共享索引、缓存、read model 或跨页面运行时分支，并保留双身份冲突的 exact-set 语义。生产 `<=5s` 仍以修复 release 的连续 Audit 实测为最终门禁。

首次统一生产验证证明成本 Audit 的数据库 SQL 是主要耗时，且混合 OA refresh 期间会出现显著长尾。为避免凭猜测增加索引，成本 owner 以加法字段 `proof_timings` 暴露六段只读耗时：四组 cost-local proof，以及 Workbench / Bank Detail 两个既有 dependency collector；每段同时返回 issue count。该诊断不新增 SQL、不改变 query budget、不缓存绿色结果，也不影响其它页面 Audit response owner。取得真实分组数据后只优化被证明的慢 statement。

2026-07-16 的 05-12 将页面读时的多 owner expected-source 链路收敛到一个成本专属 PostgreSQL gate statement：同一 MVCC snapshot 读取成本 metadata/current dirty、App Settings 成本片段、月份 Workbench active generation/current dirty 与 Bank Detail scope/current dirty。query 以纯 helper 从该快照生成业务 source versions 和标签筛选 token；settings、Workbench、Bank Detail 不再由 Application/runtime provider 串行二次读取。依赖缺失、非法 JSON、pending/failed、schema/source version 漂移都会在 Redis/ETag/rows 前 fail-closed。旧 Application 四个 source wrapper、runtime source provider/expected method、query tag-selection provider 和按当前 expected key 删除 Redis 的旧逻辑均已删除；生产 EXPLAIN 与 p95/p99 仍等待统一部署窗口。

2026-07-16 的 05-13 又删除了 `CostStatisticsReadModelService` module/class/test 及 Application 的启动 snapshot、field 和显式 local persistence callback。projection 直接向既有 repository port 提交单 scope write model；runtime invalidation 不再清理进程内 dict，而只把规范 scope 写入 durable refresh gateway，queue 不可用时不得报告已失效。PostgreSQL read-model table/repository 仍是正式边界，不属于被删除的本地 service。当时保留的 warmup 终结桥已在统一发布准备收口中删除。

2026-07-16 的 05-14 删除了成本 repository port、共享 PostgreSQL repository、`PostgresStateStore`、本地 `ApplicationStateStore`、`StateStoreProtocol` 与 manifest 中残留的全量 load / 无条件 save 合同。应用启动/全状态快照不再扫描或携带成本 read model，broad `save(payload)` 也不再接受该 key；正式写入只允许带 `tenant_id + scope_key + source_version` 的 conditional publish，正式读取只保留 scoped freshness/page/export/transaction 与 Workbench source-version I/O。该删除只收窄成本边界，不改变其他页面 read model、API、worker event、表结构或前端行为。

2026-07-16 的 05-15 将 bulk `export-preview` / `export` 从完整 explorer payload 迁到成本专属 `get_cost_statistics_export_page(...)`。preview 只取 SQL 汇总与最多 8 行；同步 XLSX 在 20,000 行门槛通过后按每批最多 1,000 行读取，并直接写 openpyxl write-only worksheet。下载生成后再次校验同一 schema、业务 source versions 与 `published_source_version`；中途发布变化时丢弃文件并返回既有 non-fresh 409。transaction 单笔导出继续走 freshness gate + identity 点查。HTTP、筛选、文件名、sheet 和权限合同未改变，也未把导出抽象扩散到其他页面。

2026-07-16 的 05-19 将 projection 的 `source_versions_unchanged` 判定迁到 cost-local `get_cost_statistics_scope_metadata(...)`。该 I/O 是一次 parent scope point query，只返回 `scope_key/entry_count/source_versions`，不读取 payload、结构化 cost/bank-flow rows、dirty queue、Workbench、Bank Detail 或 App Settings。统一发布准备收口取得 owner 明确认定后，旧 month/project HTTP contract 与最后一个 full-view loader 已全量删除。

2026-07-16 的 05-20 删除了混合 owner `cost_tax_sql_projection.py`。成本 builder 与全部成本私有 helper 现在只属于 `cost_statistics_sql_projection.py`；税金 builder 迁到 `tax_offset_sql_projection.py`。生产 worker 直接 import 两个 owner，旧 module、re-export、compat shim 和 fallback 均不存在；税金行为、API、read model、queue 与 worker event 未改变。

2026-07-16 的统一发布准备收口以系统 owner 明确认定和生产只读 `/api/background-jobs/active` 证据关闭最后两个删除门：不存在旧成本 HTTP contract 的已知脚本、RPA、BI 或第三方 consumer，且该 contract 从未作为公共集成合同承诺；生产 active/attention warmup job 均为 0。由此删除 warmup scheduler/retry/recovery、App Health/runtime/frontend registry、旧 root/project route 与 mock、full-view query/repository/DTO，以及 projection 的 Redis 兼容构造参数。未新增 cache、endpoint、worker、表、fallback 或跨页面 read model；部署与生产性能/Audit 验证仍只在统一部署窗口执行。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `performance-freshness-lock-overlay-design.md`：本轮高性能、freshness、Audit、轻量锁和旧链路删除的唯一主设计与实施校准文档。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护成本统计页面 Spec-first Browser E2E 验收合同。
- `e2e-coverage.md`：维护成本统计 Spec ID 到自动化测试的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

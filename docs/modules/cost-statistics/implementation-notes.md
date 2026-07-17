# 成本统计 实施记录

## 2026-07-18 - relation delta 完整性与直接因果证明修正（生产复验待发布）

- 首次生产试跑证明 direct Cost worker 本身已达到短链路：confirm 的月份 delta `863.994ms`、直接 parent 约 `302ms`，root→`active:all` 约 `1.011s`；withdraw 的月份 delta 最大 `275.028ms`、root→`active:all` 约 `0.34–0.39s`。此前报告的 confirm `19.35s` / withdraw `8.7s` 是 smoke 在等待所有其它 consumer 后才读取 Cost，并且 direct parent 没有 trace 时误选后续 Workbench convergence path，不是 Cost direct all 链路耗时。
- 生产试跑同时否证了发布完整性：delta 把月份 payload 覆盖成只含 month/scope/accounts 的最小对象；parent 快聚合只重算 summary，遗漏 project/expense groups；Bank Detail 在业务签名不变时仅增长执行 `source_version`，Cost 仍被误判 upstream mismatch。这三项会让 Cost Audit 在操作后失败，因此该 release 不能作为闭环结果。
- 修正边界：既有 Cost repository 在 delta 的同一事务完成目标行替换后，从最终 `cost_statistics_rows` 以一次 set-based aggregate 计算 summary/project/expense groups，再以一次 bank-flow aggregate 计算方向摘要，并原子保存完整月份 metadata。parent 复用同一个窄 repository I/O；删除 projection 内重复 SQL，不恢复全行 loader、Python group-by 或旧 JSON rows。
- 依赖语义：首次复验又发现 Bank Detail 的业务内容签名不变，但其内部 `workbench_relation_source_versions` lineage 随 relation 写入变化，仍造成 4 个 Cost upstream mismatch。最终 Cost 只忽略嵌套 `bank_detail_source_versions.source_version` 与 `workbench_relation_source_versions` 两个不消费的 provenance 键；Bank Detail scope 必须仍为 fresh/drained，schema、业务 source signature、row count、标签规则与任何未知新增字段仍精确比较，Cost 直接依赖的 Workbench 与其它 source versions 继续精确比较。query/cache/Audit 使用同一 Cost-owned semantic helper/SQL 口径，不改变 Bank Detail 或其它页面的 read model 合同。
- 因果证明：Cost 月份事件没有 caller trace 时，parent enqueue 使用 exact event id 作为 trace，使 production smoke 只能选择 direct delta→parent 链，不能以较慢的 Workbench 最终收敛链冒充 direct latency。
- 隔离与旧链：无 migration、新表、索引、worker、queue、HTTP、前端、共享 freshness 或兼容 fallback；只修改 Cost query/projection/repository/Audit owner。旧 parent 内联聚合 SQL被删除，既有旧 full-row loader/row parser、HTTP consumer、无身份 direct rebuild 与第二队列保持为零。
- 本地证据：Cost/query/API、relation UoW、queue、Workbench/周转写路径、架构 guard、SLO/smoke 共 `690 passed, 1 skipped`；真实 PostgreSQL 在临时空库应用 migrations 后，delta/parent 完整聚合与真实 Cost Audit SQL 共 `6/6` 通过，临时库已删除。`lint`、docs 与 `git diff --check` 通过；本轮无前端行为变化，不重复运行无关前端全量 CI。

## 2026-07-18 - relation 写后 all 可见性精准增量（生产验证待发布）

- 生产否证：第一轮“只等 Workbench publish 再刷新 Cost”的 release 在真实 withdraw 中，Cost all 可见耗时 `18.624s`；约前 `12s` 消耗在 Workbench 全月 generation，Cost 月份与 parent 又消耗约 `6s`。因此下方第一轮的“Workbench 是唯一 relation-origin Cost owner”结论已失效，不能作为当前设计依据。
- 当前边界：relation write transaction 在持久化业务关系的同一事务内，额外向既有 `cost_statistics` queue 投递一个 `active:YYYY-MM` 精准增量。唯一输入是按 `case_id` 分区的 `{status: active|cancelled, row_ids}`；Cost worker 不读 relation repository，不猜 relation 状态，也不修改其他页面 read model。行点读覆盖 Workbench 当前 active generations，并优先目标月份副本，因此跨月关系不必等待新 generation 才取得另一个月份的原生 row。成功且 current 的 Workbench 月 generation 仍投递 `workbench_shard_published`，但只承担最终收敛。
- 并发与失败：同 scope 队列按 case 合并，最多 200 case；不同 case 独立，同 case 后写覆盖前写。非法、缺失或超限 delta 不执行不完整增量，而是走既有全月 Cost 重建。active delta 仅在目标 Workbench rows 已进入当前 active generation 时发布，否则保持未发布并等待 Workbench convergence；cancelled delta 删除目标关系成本行。
- 发布 I/O：增量 repository 在同一事务锁定精确 dirty/source version，只删除/插入受影响的 `cost_statistics_rows`，标签从 Cost 自有 `cost_statistics_bank_flow_rows` 点查，并同步当前 scope 行版本证明与完整月份 metadata；不修改 bank-flow 业务行。成功月份发布才 fan-out parent。parent 不再加载全部月份行并构造大型 Python DTO，而是读取 shard metadata，再以两条 SQL 计算成本 summary/project/expense groups 与 bank-flow summary。
- 旧链删除：不恢复第一轮已删除的无身份 direct full rebuild、`workbench_relation_changed` / `turnover_relation_changed` 成本 reason、repository 隐藏 fan-out、HTTP consumer、第二 queue/worker、兼容 API 或 fallback；本轮继续删除 parent 的全行 loader/row parser。自动匹配和 lifecycle 不拥有 relation Cost delta。
- 页面与证据：前端仍使用 Cost 私有 exact barrier 与既有轻量 inert overlay。生产通过条件是 relation receipt 包含 exact delta、delta month→`active:all` causal completion、explorer `200/fresh`、source versions 与业务断言变化，并在写后收敛状态对 Cost/Workbench/OA 三页面执行 `pass/fresh/drained` Audit。event done 不能冒充页面可见。
- 本地验证：相关 backend/architecture/write-operation 回归 `811 passed, 1 skipped`；真实 PostgreSQL 空库实际应用全部 migrations 后，精准发布、不同 case JSONB 合并/同 case 覆盖、跨月 active-generation 点读、当前 shard parent aggregate 与既有 facet/unchanged 合同共 `6/6` 通过，临时库已删除。`lint`、docs、impact matrix JSON 与 `git diff --check` 通过；本轮未改前端，沿用已发布并覆盖的 Cost exact barrier/inert overlay。
- 剩余发布门禁：标准部署、真实 confirm/withdraw p99 `<=3s`、写后 Cost/Workbench/OA 三页面 `pass/fresh/drained` Audit 与非消费者隔离仍需完成；正确性和性能证据齐全前不声明生产闭环。

## 2026-07-17 - unchanged 版本确认闭环（生产验证待发布）

- 生产证据：正式 turnover relation confirm/withdraw 后，`active:2026-04` 与 `active:all` 的成本 payload 内 Workbench/Bank Detail 来源版本已经是当前值，但 parent `published_source_version` 停留在旧值；month/parent 每秒重复产生多组 `cost_statistics_all_shard` / `cost_statistics_shard_converged` event，Cost Audit 长期 refreshing。只读生产查询确认不是单条慢 SQL，而是持续收敛循环。
- 根因：旧 `_unchanged_cost_statistics_scope_result(...)` 在业务 `source_versions` 相等时直接返回 `skipped=true`；readiness reporter 按合同忽略 skipped event，所以当前 dirty event 的发布版本从未被确认。month 完成后投递 parent，parent 又把 month 判为 non-fresh 并补投，形成闭环自激。
- 决策：在既有成本 repository port 增加单一 `acknowledge_unchanged_cost_statistics_scope(...)`。它在同一事务锁定当前成本 dirty row，精确比较 tenant/scope/event source version，并用 JSONB equality 再验 parent 的完整业务 source versions；成功时只更新 `published_source_version/updated_at`，不重写 payload、两张结构化 rows 或 obsolete scopes。projection 返回 `published=true/skipped_rebuild=true` 让既有 readiness 正常记录；竞态失败保持 unpublished/refreshing。
- 旧路径删除：删除“source versions 相等便直接通用 skipped、无需版本确认”的语义；不保留第二 worker、queue/readiness 特判、fallback 或兼容 API。
- 隔离：改动只在 Cost Statistics projection、窄 port、成本 SQL owner 与 manifest；无 migration/schema、共享 queue/readiness、其它页面 read model、API、前端或缓存变更。
- 测试：定向 304 tests 已覆盖 exact equality、processing、dirty/source race、零 payload/row rewrite、port/manifest 与跨模块 architecture guards。完整 backend/lint/docs/真实 PostgreSQL/CI、发布与生产队列/Audit/性能证据仍是本条目的发布门禁。

## 2026-07-17 - 统一生产部署与写后验证闭环

- 发布：精确 SHA `d3fc16026` 通过 Nightly CI 后部署为 `main-d3fc16026-oa-outbox-index-20260717`；migration 0110 在生产应用耗时 `248ms`，API、dispatcher、22 个 worker、readiness、前端 hash 和公网 session route 全部通过。
- 性能：浏览器等价持久连接 isolated 100 次均为 `200/fresh`，成本 explorer 为 `p50=62.776ms / p95=81.029ms / p99=152.244ms`；三页 simultaneous 50 轮仍为 `p95=228.575ms / p99=254.969ms`，通过 `300/500ms` 页面门槛。
- Audit：部署后基线和可逆 turnover relation 正式 confirm + withdraw 后两轮 Page Audit 均为 `pass/fresh/drained`、`issues=0`、`database_snapshot=true`；写后两轮 Audit 分别约 `2.123s` 与 `2.250s`，低于 5 秒证明门槛。
- 隔离：生产 dashboard 中成本 explorer 固定 3 queries，包含 simultaneous 样本的 rolling p95 为 `166.241ms`；未新增缓存、共享池改动或其它页面 read model 依赖。

## 2026-07-17 - 生产 explorer facet 百分比 placeholder 修复

- 生产证据：精确 release 的多视图只读探针中，`time` 与 `bank_tag` 均为 `200/fresh`，但 `project`、`bank`、`expense_type` 的 `scope=all` 50/50 返回 500；正式 request-id 日志统一报告 psycopg 拒绝裸 `%` placeholder。
- 根因：三个 facet 共用的百分比 SQL 在参数化 statement 内使用了裸百分号字符串；本地 fake connection 只记录 SQL，没有执行 psycopg placeholder 解析，因此旧测试未捕获。
- 修复：只在 `_cost_statistics_percentage_sql()` 的传输 SQL 中把 `%` 转义为 `%%`；PostgreSQL 最终业务值仍是单个百分号，聚合、排序、分页、scope、read model 和 API shape 均不变。
- 隔离性：只有成本 explorer 的 project/bank/expense_type facets 受影响；time/bank_tag、Audit、其它页面和共享 read model 不变。没有新增 fallback、缓存、endpoint 或兼容分支。
- 测试责任：现有单 statement repository 测试新增 psycopg 百分号转义断言；发布前还必须在真实临时 PostgreSQL 上执行五种 explorer view，发布后复跑生产 200/fresh 与 p95/p99 门槛。


## 2026-07-17 - 生产 Cost Audit 宽 payload 物化移除

- 生产证据：统一 release `main-535474753-cost-audit-jit-20260717` 上，成本 Page Audit 仍为 `pass/fresh/drained`，但总耗时 `8.83s`、`exact_set=6849.942ms`；事务级关闭 JIT 没有改善，因而该假设已被生产证伪，相关代码直接删除，不保留无效配置。
- 根因：`member_payloads` 被 group facts、OA context 和 bank member 三个下游 CTE 复用，PostgreSQL 默认将它物化；该中间集保留 Workbench 成员完整 JSON payload，生产宽 OA payload 会导致 TOAST 解压与 temp I/O，而成本证明最终只消费有限标量字段。
- 修复：仅将成本 Audit 私有 SQL 的 `member_payloads` 声明为 `NOT MATERIALIZED`，允许 planner 把 OA/bank pane 过滤下推，避免宽 JSON 中间集落到 temp；所有分支仍在同一 repeatable-read read-only snapshot 内从同一 canonical/read-model 事实重算，issue contract、query budget 和 `<=5s` 门槛不变。
- 量化验证：真实 PostgreSQL 0001–0108 上构造 300 个 paired groups、600 个 Workbench members、每个 50KB payload；原 SQL 执行 `2771.833–2859.864ms`、root temp read blocks `2,212,294`，`NOT MATERIALIZED` 为 `262.030–321.771ms`、temp read/write 均为 `0`，约快 9–10 倍。临时数据库已删除。
- 隔离：不改全局 PostgreSQL、schema/index/migration、成本页面读 API、read model/worker、其他页面 Audit 或业务数据；没有 fallback、feature flag、第二 executor 或新抽象。生产连续 Page Audit、三页面 HTTP/混合负载与精确 SHA CI 仍须在本修复发布后闭环。


## 2026-07-16 - 生产 Cost Audit exact-set 索引化身份解析

- 生产证据：统一 release 上连续两次只读 Page Audit 的 `exact_set` 分别为 `9538.201ms`、`9402.896ms`，而 queue/source-version/business-values/Workbench/Bank Detail 其余 proof 合计约 `2.1s`；正确性均为 pass，慢点被限定在成本私有 canonical exact-set SQL。
- 根因：Workbench bank member 到 canonical `app.bank_transactions` 的连接使用 `id::text = key OR legacy_mongo_id = key`；UUID cast 到 text 不能直接使用主键，OR 又阻碍两个现有唯一索引形成稳定 equality probes。
- 修复：成本 Audit 私有 SQL 先解析 member transaction identity，再分别通过 UUID 主键和 `legacy_mongo_id` 唯一键做 lateral equality probe；同一 canonical 行只保留一次，不同 canonical 行的双身份冲突仍全部进入 exact-set，因此没有弱化完整性证明。
- 隔离：未新增 migration/共享索引、缓存、read model、API 字段或 fallback；不修改成本页面读链、其他页面查询和任何业务写入。
- 验证责任：结构测试禁止旧 `id::text OR` 回流并锁定两个 indexed probe；真实 PostgreSQL Audit 与生产连续 `<=5s` 仍是发布后硬门禁。


## 2026-07-16 - 统一发布准备闭环：删除 warmup 与旧 HTTP/full-view

- 目标：关闭成本统计最后两个本地发布阻断项，使模块达到 `READY_FOR_UNIFIED_DEPLOYMENT`，同时保持 `DEPLOYMENT_HOLD`，不部署、不操作生产 migration/queue/worker/业务数据。
- 删除门证据：系统 owner 明确认定不存在旧成本 root/project HTTP contract 的已知脚本、RPA、BI 或第三方 consumer，且该 contract 从未作为公共集成合同承诺；使用现有生产 admin token 只读查询 `/api/background-jobs/active`，`cost_statistics_cache_warmup` 的 active、attention 与 jobs 均为 0。
- 旧链删除：删除 server warmup recovery/retry/schedule/run、runtime/background-job dependency、derived lifecycle 双路径、App Health/runtime/frontend registry、旧 root/project route、query full/month/project 方法、repository full-view port/SQL/facade/manifest、projection Redis兼容构造参数、HTTP SLO旧summary probe、前后端 mocks与只保护旧链的测试。未保留 fallback、shim、第二 endpoint、第二 worker或兼容 job。
- 当前边界：页面只走 explorer page、export page、transaction point lookup 与 tag-rules；所有读取先过 dependency-bound PostgreSQL fresh gate，non-fresh 只通过现有 `ReadModelRefreshGateway` 入队正式 durable event。
- 隔离：未改成本业务口径、schema/migration、其他页面 API/read model、共享 relation事实、税金 worker或生产数据；共享生命周期调用点只删除已失效的 warmup布尔参数，仍走原有 cost executor/gateway。
- 测试：成本 SQL/API/runtime/projection、route/manifest/architecture guards、App Health/background job通用策略、frontend mock与交互、HTTP probe、全量 backend/frontend/E2E/docs及 migration验证全部通过。无外部 PostgreSQL 时后端为 `4078 passed, 35 skipped`；显式临时 PostgreSQL 实际应用 `0001–0107` 后为 `4104 passed, 6 skipped`，临时库已自动删除；前端 `72 files / 855 tests`、production build、Playwright `179/179`、lint、docs 与 `git diff --check` 全通过。生产源码、前端 client、E2E mock、脚本和部署文件对旧 warmup、旧 root/project HTTP、full-view repository/query 与 projection Redis兼容参数的扫描均为零。
- 验证校准：首次 PostgreSQL 命令因临时 URL 缺少显式 host 被 migration 安全阀拒绝；仅修正命令连接串后重跑，没有修改代码、测试或安全断言。production build 仅保留既有第三方 CSS minify/chunk warning。
- 状态：`READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD`。统一部署窗口仍需执行备份、旧 lane drain、migrations、rehydrate、Page Audit、canary、真实生产性能和三页面混合负载隔离性验证；这些是生产执行门，不恢复已删除旧链，也不阻止当前发布准备判定。


## 2026-07-16 - GSD 05-20 删除 cost/tax 混合 projection owner

- 目标：删除 `cost_tax_sql_projection.py`，让成本和税金 projection 各自拥有明确文件边界，不保留 re-export、shim或 fallback。
- 变更：成本 builder和私有 helper迁入 `cost_statistics_sql_projection.py`；税金 builder和私有 helper迁入 `tax_offset_sql_projection.py`；生产 worker与直接测试改为明确 import。
- 隔离：Tax Offset SQL、payload、Redis、read model、queue、worker event、API与页面均未改变；共享 dirty `worker.py` 只修改 cost/tax import，保留其它 thread现有 diff。
- 验证：成本 rules/SQL/API、税金 SQL runtime、worker bootstrap、runtime-state/read-model architecture与静态 owner guards通过；完整命令见 `05-20-SUMMARY.md`。
- 状态：本地实现 `READY_FOR_COORDINATED_DEPLOY`，整体目标仍 `DEPLOYMENT_HOLD`；warmup、旧HTTP/full-view和生产SLO/Audit必须等待统一部署窗口。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 成本统计 read model refresh scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`；旧裸月份/裸 `all` 必须在统一 read model refresh gateway 中归一化，不能直接进入 durable queue。
- `cost_statistics.read_model.refresh` 只由 `cost-statistics` worker 消费；旧 `cost-tax` 成本统计消费链路已移除，不能作为辅助 lane 回接。
- 生产库中已有的成本统计 legacy/invalid runtime scope 通过 `scripts/check-read-model-scope-contracts.py` 检查；`--apply` 删除旧状态，并补投可归一化的规范 replacement scope。
- 成本税务 projection 中的发票输入必须来自 canonical invoice facts；OA 附件正式发票先 promotion 到 Invoice repository / `app.invoices`，不能从 `app.oa_attachment_invoice_cache` 直接拼计划或成本税务输入项。
- 成本统计 export-preview/export 是同步生成路径；time、month、project、expense_type 导出超过 20,000 行时必须返回 `cost_statistics_export_row_limit_exceeded`，不能继续生成大预览或 XLSX。
- 成本统计月份 shard 的 Workbench 输入来自 active generation 的 `workbench_group_rows + workbench_rows` 结构化成员，不再读取 `workbench_groups.payload` 里的 `oa_rows/bank_rows` 旧 JSON 成员数组。
- v9 成本 read model 的 OA 配对行与全银行收支行分别持久化到 `read_model.cost_statistics_rows` 和 `read_model.cost_statistics_bank_flow_rows`；parent metadata 不保存 `time_rows` / `bank_flow_time_rows`，也不保留 JSON fallback。transaction detail 经 fresh gate 后直接按 identity index 点查。
- 成本统计模块边界已达到 `READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD`：query service 只读 SQL read model/Redis fresh cache；miss/stale 不同步 rebuild；runtime 不持有 live explorer loader或background job依赖。legacy live service、本地 read model、warmup job、旧 root/project HTTP/full-view、live export helper 和 `ProjectDetailExportService` 均已删除；业务归集只由 SQL projection owner 负责。
- 05-13 已删除 `CostStatisticsReadModelService` module/class/test、Application startup snapshot/field/local persist callback，以及 runtime 的 local clear/invalidate/persist dependency。projection 直接发布单 scope repository write model；invalidation 只有 durable gateway 接受后才报告成功。正式 PostgreSQL table/repository 不属于被删除的本地 owner。
- 05-14 已删除成本 repository/state-store/protocol/manifest 的全量 load 与无条件 save 合同。启动/全状态 snapshot 不再扫描或携带成本 read model，broad save 不再识别成本 key；正式写 I/O 只剩 source-version conditional publish，当前读取只剩 scoped gate/page/export/transaction 接口。
- 05-15 已把 bulk export-preview/export 从完整 explorer payload 迁到 cost-owned `get_cost_statistics_export_page(...)`。preview 只取 SQL summary + 8 行；download 门槛通过后每批最多 1,000 行并写入 write-only XLSX。文件生成后重新比较 schema/source versions/published version，中途变化时丢弃 bytes 并返回既有 409。旧 `_filtered_entries_from_read_model`、普通 bulk workbook 和全量 entries/rows list 已删除；transaction point export 不变。
- 05-19 已把 projection unchanged 判定迁到 `get_cost_statistics_scope_metadata(...)`。它只按 scope 点查 parent `entry_count/source_versions`；完全相等才 skip，missing/mismatch 重建。worker 不读取 payload、两张明细表或页面 dependency gate；统一发布准备收口已在 owner 证明后删除旧 month/project HTTP合同和 full-view loader。
- cost projection 不再写或删除旧 `cost_statistics:explorer:{scope}` 无版本 Redis key；Redis payload 只属于 query gateway 的 gate-after-read versioned cache。
- 页面 Audit 的 paired-cost canonical expected-set 读取 active Workbench generation 的结构化 group/member payload，严格遵循 builder 的 candidate/linked-open 判断、完整 OA context tuple 和 bank payload 方向/金额语义；禁止退回 `app.bank_transactions` 近似 Workbench 成员，或用 group 列值替代 payload 业务状态。
- 成本 Audit 的唯一 owner 是 `postgres_repositories/cost_statistics_page_audit.py`；统一 page key、只读 CLI 与 System Audit 直接分派并透传 caller-owned snapshot。共享 `page_business_audit.py` 不保留成本合同/SQL/fallback；05-18 后成本 owner 的 queue/readiness、source-version、exact-set、business-values 固定为四组集合 SQL，active-relation 23-query 总预算只保护当前 I/O 上限，不能作为生产 `<=5s` 结论。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖成本归因、API/导出、SQL read model、parent/shard readiness、scope gateway、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

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

## 2026-07-16 - GSD 05-18 成本 Audit exact-set 单语句收敛

- 目标：把 scope row count、missing scope、duplicate identity 与 canonical expected-set 四次成本自有数据库往返收敛为一次，同时保留完整双向集合证明和每类独立 sample bound。
- 影响范围：仅成本 Audit owner、专属测试与成本维护文档；不改共享 Audit、Workbench/Bank Detail proof、页面/API、read model、worker、schema/index、连接池或其他页面。
- 关键决策：四段原 proof 作为独立 limited CTE 统一输出 `issue_code/subject_id/scope_key/details`；canonical 分支仍完整构造 Workbench OA-bank expected cost 与 canonical full bank-flow exact set。Python 只做既有 code→message 映射，未知 code fail fast。
- 旧代码删除：删除四个 per-query helper 和不再有调用方的 `_proof_query_issues`，whole-repo 当前代码无成本调用方；不保留 compatibility wrapper、fallback、query builder、proof cache/context、临时表或并行连接。
- 性能证据：成本 owner 本地 SQL 从 7 组收敛为设计约束的 4 组；active-relation 固定总预算从 26 降至 23。一次性本地 PostgreSQL 0001–0107 migration + 完整成本 Audit clean-pass证明合并 SQL 可执行，但不冒充真实数据 plan或生产 SLO。
- 测试覆盖：四类 issue 合同、四个独立 limit、参数顺序、单 marker、23-query预算、只读 snapshot、唯一 owner 分派、成本 API/SQL runtime、repository boundary 与 disposable PostgreSQL。
- 未测风险：真实数据 `EXPLAIN (ANALYZE, BUFFERS)`、生产 `p95 <=5s`、upstream mismatch修复与连续 pass仍待统一部署；整体继续 `DEPLOYMENT_HOLD`。

## 2026-07-16 - GSD 05-17 成本 Audit v9 结构化 bank-flow cutover

- 目标：删除成本 Audit 中 canonical expected-set、bank-flow 关键字段和 scope summary 三处已失效的 parent JSON array 读取，只从 v9 结构化 bank-flow 表证明投影。
- 影响范围：仅成本 Audit owner、直接测试和成本维护文档；不改 schema、发布/query repository、API、worker、前端、共享 Audit、Workbench/Bank Detail owner 或其他页面。
- 旧代码删除：`cost_statistics_page_audit.py` 对 `bank_flow_time_rows` 与相应 lateral JSON 展开为零；System Audit PostgreSQL v9 parent fixture 也删除该旧字段；未保留 dual-read、fallback、feature flag 或第二 proof 路径。
- 正确性：canonical set 按 `scope_month + transaction_id` 比较 typed count/amount；字段 proof 直接比较结构化 identity/display/tag 列；summary 以 month rows 加 parent 逻辑 rollup 重算收支笔数/金额，空 scope 仍为 0。
- 性能/隔离：删除三次大数组解析但不改变 statement 数，active-relation 固定预算仍为 26；无新层、表、索引、缓存、连接或跨页面 diff。
- 测试覆盖：结构化表唯一读取、旧数组零引用、parent rollup、typed numeric、三类 issue 合同、只读 snapshot、26-query 预算及通用 Audit 回归；一次性本地 PostgreSQL 完整 0001–0107 migration 后的 clean cost Audit 证明真实 SQL syntax/列解析通过。
- 未测风险：空数据 PostgreSQL 集成不等于生产 EXPLAIN/数据量或 `p95 <=5s`；整体继续 `DEPLOYMENT_HOLD`。

## 2026-07-16 - GSD 05-16 成本 Audit 业务值证明单次往返

- 目标：把同一成本 Audit snapshot内关键字段、bank-flow字段、scope summary、project/expense summary和bank accounts五类证明从五次`fetch_all`收敛为一次。
- 影响范围：仅成本 Audit owner、专属测试与成本维护文档；不改 Workbench/Bank Detail proof、通用 Audit、页面/API、read model、worker或schema。
- 关键决策：保留五段原 SQL及各自排序/`limit`，仅将其包装为limited subquery后`UNION ALL`；issue code用绑定参数传入，统一输出`issue_code/subject_id/scope_key/details`。不增加proof cache/context、query builder class、临时表或并发连接。
- 旧链路删除：05-16 删除五次 `_proof_query_issues(...)` 循环调用且不保留逐查询 fallback；该 helper 当时仍被 canonical expected-set 单查询使用，随后已在 05-18 合并 exact-set 后随最后调用方一并删除。
- 性能证据：active relation固定本地总预算从30降至26；business-values数据库调用从5次降至1次。该证据只证明往返不回退，不替代真实PostgreSQL plan或生产`p95 <=5s`。
- 测试覆盖：五类issue code/details、五个独立limit、精确参数顺序、单次marker、26-query预算、只读snapshot、registry/CLI/System Audit回归。
- 未测风险：当前无真实PostgreSQL syntax/EXPLAIN/生产数据量证据；剩余四个exact-set类成本查询、上游collector耗时、真实mismatch与连续pass仍未关闭。
- 后续事项：下一prompt只能根据05-16验证结果选择一个有界剩余风险；历史warmup删除继续等待production active-job=0，整体保持`DEPLOYMENT_HOLD`。

## 2026-07-16 - GSD 05-15 bulk export 有界读取

- 目标：删除 preview/download 对完整 explorer payload 和全量 Python entries/rows list 的依赖，同时保持同步导出合同与 20,000 行门槛。
- 影响范围：CostStatisticsQueryService、cost repository port/manifest、PostgreSQL cost rows query、直接测试和文档；不改前端、route、worker、Audit、migration 或其他页面。
- 关键决策：只新增一个 cost-owned export page I/O；preview page size=8，download batch size=1000。首批 SQL 返回完整筛选 summary，month/project period aggregation 在 SQL 完成；bulk workbook 使用 write-only 模式，项目详情只保留费用汇总 buckets 并直接 append 流水。
- 一致性：下载前 gate 取得 tag selection 与发布证明，序列化后再次比较 schema/source_versions/published_source_version；中途变化时 bytes 不返回。没有长事务、server-side cursor、通用导出框架或异步 job。
- 测试覆盖：preview 8 行、bounded pages、limit-before-workbook、version race、repository filters/limits、manifest/port、workbook shape 和静态 legacy guard。
- 未测风险：真实 PostgreSQL planner、20k 行内存/耗时、Nginx/OA 下载代理和并发发布只可在统一部署后验证；保持 `DEPLOYMENT_HOLD`。
- 后续事项：下一 prompt 仍由实际完成状态决定；warmup 删除需 production active-job=0 证据，Audit 最终四组 SQL 和 SLO 需统一部署后的真实 plan/data，不能与本地导出改动混做。

## 2026-07-16 - GSD 05-14 删除全量 load 与无条件 save 旧表面

- 目标：在 05-13 删除进程内 owner 后，继续移除无 production caller 的成本全表 load、无 source-version save、state-store snapshot key 与协议/manifest 暴露面。
- 影响范围：成本 repository port、共享 PostgreSQL repository 的成本专属方法、Postgres/local state store、state-store protocol、manifest、直接测试与文档；不改 schema、API、worker event、Audit、前端或其他页面 read model。
- 关键决策：正式写入只允许 `publish_cost_statistics_read_models(...)` 以 `tenant_id + scope_key + source_version` 在同一事务 CAS 发布；broad state load/save 明确不拥有成本 read model。历史 local pickle key 作为无人读取的 inert data 留存，不增加迁移或兼容清理分支。
- 旧逻辑删除：全量 loader、无条件 saver、facade delegate、StateStore methods/key/branch、protocol/manifest contract 与只保护旧行为的测试 fixture 已删除；row batching/parent metadata/obsolete delete 测试迁到 conditional publish。
- 验证：见 `.planning/phases/05-cost-statistics-improvements/05-14-SUMMARY.md`；本轮保持 `DEPLOYMENT_HOLD`。
- 未测风险：真实 PostgreSQL plan、worker drain、历史 warmup active-job=0、Audit `<=5s`、导出和页面 p95/p99 均待后续 prompt 或统一部署窗口。

## 2026-07-16 - GSD 05-13 进程内成本 read model 旧模块删除

- 目标：删除已不参与页面读取、却仍在启动、projection 和 invalidation 中保留第二状态 owner 的 `CostStatisticsReadModelService`。
- 影响范围：成本 source-version constant、projection publish shape、runtime/lifecycle invalidation、Application 组合根、成本/设置 reset tests 和直接模块文档；不改数据库 schema、正式 repository、共享 gateway、前端或 Audit。
- 关键决策：schema version 由现有 `cost_statistics_source_versions.py` 唯一定义；projection 直接构造既有单 scope write shape并继续 conditional publish。runtime 不删除 SQL rows或本地 dict，只返回成功经 gateway 规范化并接受的 durable scopes；queue 不可用返回空。
- 旧链路删除：删除 module/class/test、server import/field/startup load/persist callback、runtime constructor `read_model_service/persist_read_models` 和 `_persist` 分支。API fixture 由测试 SQL repository 自持 view mapping，不重造 test service。
- 隔离与反过度设计：未新增表、migration、worker、adapter、cache或共享分支；Tax Offset、Workbench、Bank Detail和其他页面 read model未修改。正式 PostgreSQL repository的 load/save/publish合同保留。
- 测试覆盖：service/lifecycle、API、SQL publish、settings reset、state-store constant import和静态边界 guard；完整结果见 `05-13-SUMMARY.md`。
- 未测风险：历史 `cost_statistics_cache_warmup` job type 仍需统一部署窗口先证明 active job为零；生产 worker drain、EXPLAIN/p95/p99与 Audit `<=5s`仍未执行。


## 2026-07-16 - GSD 05-12 单次依赖鲜度门禁与请求期旧 provider 删除

- 目标：把 explorer/page、内部 full/month loader 与 transaction detail 在 payload/cache 前的 settings、Workbench、Bank Detail 多 owner I/O 收敛为一个成本专属 PostgreSQL statement，同时保持统一事实源变化后旧页面必然锁定。
- 关键决策：gate 在同一 MVCC snapshot 返回 cost metadata/current dirty、成本所需 settings 片段、concrete month 的 Workbench active generation/current dirty 与 Bank Detail scope/current dirty。projection/query 共用 `cost_statistics_source_versions(...)`；标签选择由 `AppSettingsService.cost_statistics_tag_selection_payload_from_settings(...)` 对 gate snapshot 纯映射，不再二次 I/O。
- 可靠性：cost、Workbench、Bank Detail 的 pending/processing/failed，published/dirty version drift，缺失 active/scope/source versions，Bank Detail schema/status 异常，settings 缺失或 JSON shape 非法，及业务 source/schema mismatch 均在 ETag/Redis/rows 前 fail-closed。settings 事实版本变化的回归证明旧 snapshot 不会继续显示 fresh。
- 旧链路删除：删除 Application `_cost_statistics_expected_source_versions/_cost_statistics_source_versions/_cost_statistics_workbench_source_versions/_cost_statistics_bank_detail_source_versions` 与 dead Redis delegate；runtime 删除 `source_versions_provider/expected_source_versions/delete_redis_cache`；query 删除 `tag_selection_provider` 和 request-time settings reload。versioned Redis 旧 namespace 只由 TTL 自然退出，不恢复无版本 delete/writer。
- 反过度设计与隔离：未新增表、migration、索引、worker、通用 gateway、连接池或缓存层；未改 Workbench/Bank Detail/Tax Offset/前端/Audit。只新增一个成本纯 helper，并扩展既有 cost repository gate 与 settings owner mapper。
- 验证：成本/App Settings/边界主回归 316 tests、共享 freshness/gateway/scope 回归 46 tests、lint/docs/diff gate 全部通过；见 `05-12-SUMMARY.md`。
- 未测风险：保持 `DEPLOYMENT_HOLD`；没有真实 PostgreSQL syntax/plan、生产数据量、连接获取或 p95/p99 证据，不声明生产 SLO 已完成。
- 后续事项：下一 prompt 必须根据本轮 PASS 重新选择单一剩余风险；不得在本轮继续混入 warmup/local read-model 删除、Audit 下一组 SQL、流式导出或部署。

## 2026-07-16 - GSD 05-11 业务规则迁移与 legacy live service 删除

- 目标：移除已无 production caller、但仍被测试 fixture 调用的 `CostStatisticsService` 第二事实源；保持导出错误合同并把有效归集规则直接锁在唯一 production SQL projection。
- 影响范围：cost projection 的局部归集 helper、query/route 的导出异常 owner、成本 API/SQL projection/边界测试及直接模块文档；不改 server 装配、公共 read-model gateway、queue/worker/schema、前端或其他页面。
- 规则闭环：SQL projection 现在直接处理 `exclude_all`、`hint_only`、`include_ticket_cost_only`、OA 冲账/排除标记、借款/还款、placeholder/detail fallback、收入/credit 排除，以及 active scope 按 App Settings completed id/name 排除且保留未知项目。
- 旧链路删除：删除 `cost_statistics_service.py`、`test_cost_statistics_service.py`、全部 production/test import 与 `_cost_statistics_service` sentinel；API fixture 调用 production builder，导出 20,000 行 limit/error 由 query owner 直接拥有。静态 guard 禁止 module/class/import/field/shim 回归。
- 隔离性：该 05-11 切片当时未删除仍有 production impact 的 `CostStatisticsReadModelService`；其 runtime/projection/server 迁移已由后续 05-13 独立闭环，本条仅保留历史决策顺序。
- 验证：见 `05-11-SUMMARY.md`；保持 `DEPLOYMENT_HOLD`，未访问生产。

## 2026-07-16 - GSD 05-10 成本 Audit source-version 证明单次往返

- 目标：只收敛成本 owner 内同一 source-version 证明族的数据库往返，避免在无真实 PostgreSQL plan 时混入其他 proof、索引或公共框架。
- 关键决策：row/scope version、月度 Workbench/Bank Detail current version 和 parent materialized shard map 仍按原条件独立计算、独立排序并各自 `limit`，但由一个 `cost_source_version_proofs` SQL 统一返回固定 issue code 与结构化 details。
- 旧链路删除：旧 `queries` 列表、三次 `fetch_all` 循环及三个独立 check query 入口已删除；没有 fallback、第二 dispatcher 或通用 query builder。
- 性能证据：active relation 场景本地总查询上限从 32 降为 30；source-version proof 数据库调用由 3 次降为 1 次。
- 测试覆盖：成本/通用 page/operations/System 65 tests（2 skipped）通过；成本 API/SQL runtime 66 tests 通过；lint/docs/diff gate 见 `05-10-SUMMARY.md`。
- 未测风险：`FIN_OPS_TEST_DATABASE_URL` 未配置，未获得真实 PostgreSQL syntax/EXPLAIN/生产数据量与 `Audit p95 <=5s` 证据；生产 mismatch 和连续 pass 仍未证明。
- 后续事项：下一 prompt 必须基于 30-query 结构选择一个独立剩余 SQL proof group 或另一最高风险，禁止把 provider、导出、剩余 legacy 与生产发布混成一轮。

## 2026-07-16 - GSD 05-09 成本 Audit 重复证明与固定往返收敛

- 目标：先删除有结构证据的重复/无消费 I/O，避免在没有生产 query timing/EXPLAIN 时盲改 1,700 行证明 SQL 或预加索引。
- 关键决策：summary query 使用两个 materialized CTE 同时返回 dirty/outbox count 与 bounded samples；成本不再单独执行这两次查询。Workbench collector 仍完整执行 relation equality，成本复用同一结果并保留原成本 code 与 dependency code；成本调用显式跳过随后会丢弃的 active-generation summary，Workbench 页面默认行为不变。
- 性能证据：包含 active relation、真实触发 group-row proof 的本地查询上限从旧实现的 36 降到 32；relation equality 从同 snapshot 两次降为一次。空数据不再作为唯一预算门禁。
- 测试覆盖：成本专属 8 tests、共享 page/operations/System Audit 64 tests 与 Workbench Audit 15 tests 通过；成本 API/SQL runtime 扩展回归被共享工作树缺失 `workbench_canonical_oa_attachment_raw_payload_repairer` 模块阻断，本轮未修改该并行 Workbench 路径。
- 未测风险：无 `FIN_OPS_TEST_DATABASE_URL`，未执行真实 PostgreSQL syntax/plan/data-volume gate；生产 `<=5s`、四组集合 SQL、真实 mismatch 与连续 pass 仍未证明。
- 后续事项：下一 prompt 必须基于本轮 32-query 结构继续选择一个有界 SQL group 合并或其他最高风险项；不得混入 provider、导出和全部 legacy 删除。

## 2026-07-16 - GSD 05-08 成本 Audit 唯一 owner 与共享旧分支删除

- 目标：行为等价地把成本 Audit 从 3,400 行通用 repository 迁回成本域，删除所有共享成本分支，为后续 SQL 性能合并建立可独立维护的 I/O 边界。
- 影响范围：新增成本 Audit repository；调整 page registry、operations dispatch、通用只读 CLI、成本 Audit tests 与直接边界文档；不修改页面、read model、worker、业务事实、权限或其他页面 proof。
- 关键决策：不新建 route/snapshot/registry/repair；继续复用完整 Workbench proof、明确的 Bank Detail canonical/field/version provider 和共享 relation proof；System Audit 仍传同一个 `AuditSnapshot`。
- 旧链路删除：`page_business_audit.py` 的成本 contract、7 组 SQL 分支、成本 dependency mapper 与 generic domain dispatch 均为零；CLI/HTTP/System Audit 无 legacy fallback。
- 测试覆盖：成本 SQL 行为断言迁到唯一 owner；新增 35-query budget、显式 snapshot、registry/operations、CLI 和 shared-file zero-text guard；其他 page-business/OA 回归继续通过。
- 未测风险：尚未在真实 PostgreSQL 上合并/量测四组集合 SQL，也未修复生产 upstream mismatch 或证明 Audit `<=5s`；保持 `DEPLOYMENT_HOLD`。
- 后续事项：下一 prompt 只能根据 05-08 的实际 query budget 选择 Audit SQL 性能合并或另一个剩余有界风险，不能把 provider、导出和全部 legacy 删除一起混入。

## 2026-07-16 - GSD 05-07 Impeccable 轻量 freshness 交互锁

- 目标：仅在 `/cost-statistics` 落地约 80% 透明、非 dialog 的页面内交互锁，使 loading/non-fresh/revalidating/barrier 期间无法操作旧数据，同时保留标题、Audit、导航和诊断能力。
- 影响范围：`CostStatisticsPage`、cost tag-rules drawer、`cost-*` 样式、页面 Vitest/Chromium mock 与成本模块文档；后端 API/read model/worker/Audit、共享 App Status/StatePanel/AppDrawer 语义和其他页面不变。
- 关键决策：复用 explorer freshness 与现有 App Health SSE/5s fallback，只精确匹配当前 `cost_statistics` scope；使用原生 `inert` 而非逐按钮伪锁；20% alpha 拦截层与状态点均无 blur/card/shadow/动画；锁定关闭 detail/export portal，drawer 保留草稿但锁 body/footer；focus/visibility/BFCache 返回均重校验。
- 旧链路删除：移除旧 loading/non-fresh `.state-panel` 状态表达和旧文案，不保留并行 fallback；详情请求支持 abort，锁定后晚到结果不能重开 portal；没有新增全局 overlay 或 cost-specific 通知通道。
- 测试覆盖：Vitest 覆盖视觉静态合同、initial/non-fresh/error/retry、native inert、焦点恢复、domain portal、drawer、BFCache；Chromium 覆盖三种 non-fresh、retry、精确/无关 App Status scope、五视图/导出/详情/大表/窄屏回归。
- 验证命令：见 `05-07-SUMMARY.md`；本轮未部署、未访问生产。
- 未测风险：真实 SSE/fallback 与跨设备通知窗口、生产数据规模性能、Audit/queue/drain 需在统一部署窗口继续；不得据此标记整体 `/goal` 完成。
- 后续事项：下一 prompt 必须由 05-07 实际 PASS 状态选择一个剩余有界风险，不能把 Audit、provider、导出和全量 legacy 删除一次性混入。

## 2026-07-16 - GSD 05-06 view-specific cursor explorer

- 目标：把页面从完整 explorer DTO + 浏览器五套聚合原子切换到同 endpoint 的 `scope/view/filter/cursor` page contract，保持高性能所需的有界 I/O，同时不增加 `/v2`、表、worker、依赖或共享页面影响。
- 影响范围：成本统计 route/query/runtime cache key/narrow repository port/PostgreSQL cost row reader、cost page/client/types、成本测试/mock 与直接事实文档；不修改其他页面 read model、共享 gateway、共享 pool 或全局 UI。
- 关键决策：freshness gate 永远先于 ETag/Redis/page SQL；cache miss 只执行一个 set-based statement；summary/facets 基于完整筛选集合，rows 每页默认 50/最大 100；cursor 绑定 schema/query/published version；available years 独立于当前 month/year scope；导出选项只在用户动作后读取两个 bounded facets。
- 旧链路删除：页面不再映射/保存 `time_rows` 或 `bank_flow_time_rows`，不再执行 full rows 过滤、分组、百分比和汇总；旧 endpoint shape 无 fallback；详情 stale/409 不再使用当前列表行拼本地详情。whole-repo current production scan 必须为这些符号/字段零命中。内部 `get_cost_statistics_view()` 暂留并登记后续调用方迁移条件。
- 文档影响：同步 API contract、read-model contract、模块 boundary/state/tests 与主性能设计；保持 `DEPLOYMENT_HOLD`。
- 测试覆盖：backend API/repository/manifest，frontend API/page，Chromium 五视图、non-fresh、详情/导出和大数据 cursor 追加；验证明细见 `05-06-SUMMARY.md`。
- 未测风险：生产 EXPLAIN/SLO、真实发布迁移与重建；Audit、Impeccable 轻量遮罩、请求期 provider、流式导出和剩余内部 legacy cleanup 属后续单一 prompt。
- 后续事项：05-06 通过后仍不部署、不标记 `/goal` complete；下一个 prompt 只能由本轮完成状态生成。

## 2026-07-16 - 删除 Application legacy CostStatisticsService 装配

- 目标：清除关联台旧 full-page builder 的最后一个跨页面生产消费者，同时保持当前成本统计 SQL read model/query/worker 链路完全不变。
- 证据：CodeGraph 未发现 `CostStatisticsService` 运行时 caller；whole-repo runtime scan 仅剩 `Application.__init__` 的无调用者实例赋值。成本页面 route 已由 `CostStatisticsApiRoutes` + `CostStatisticsQueryService` 独立拥有，projection/worker 直接使用 SQL builder/repository。
- 变更：删除 server import 和 `self._cost_statistics_service = CostStatisticsService(... grouped_workbench_loader=self._build_api_workbench_payload ...)`；扩展 runtime boundary guard，禁止 Application 恢复 legacy service/full builder wiring。
- 隔离性：未修改 cost API DTO、scope、freshness gate、structured rows、projection、worker、Redis、标签规则、前端或其他页面 read model；未给 legacy service 新增 adapter。
- 测试：Cost query/runtime/API 既有测试继续证明 SQL owner；本轮定向运行 runtime boundary 与 Cost route/query 回归。真实生产 SLO 仍按统一部署窗口验证，本轮不部署。

## 2026-07-16 - 首屏 I/O 隔离与前端旧缓存删除

- 目标：执行 GSD 05-05，移除当前月首屏无条件承担的 `active:all` 大 payload 和不能证明 freshness 的前端 5 分钟缓存；不在同一切片引入 cursor API、后端 endpoint、遮罩或 Audit 改造。
- 影响范围：成本统计页面、cost-local API client/types、前端 API/page tests 与成本模块长期文档；不修改后端、read model、worker、共享 UI/cache、其他页面或 HTTP DTO。
- 关键决策：当前 scope explorer 由 `scopeKey + payload` 绑定，scope/view/domain refresh 时上一 scope 不再暂存为当前内容；time/bank-tag 导出不读取 all，project/expense-type 只有缺少本次 mount 内 fresh 全期间选项时才按需读取，non-fresh/失败保持导出中心关闭。后端 PostgreSQL gate 继续是唯一 freshness 权威。
- 旧代码删除：删除 `costExplorerCache`、TTL/get/clear API、首屏 all-prefetch effect、`fetchCostStatisticsMonth`、`fetchProjectCostStatistics` 和孤立 DTO/types；不保留 fallback、兼容分支或新缓存层。
- 测试覆盖：首屏 request count、scope loading 隔离、API 无 module cache、导出直接打开/弹窗内模式切换的 lazy all、all refreshing fail-closed，以及既有五视图/详情/规则/导出/non-fresh Browser 回归。
- 验证命令：`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx --reporter=verbose`（35 passed）；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`（10 passed）；`cd web && npm run build`（通过，保留既有第三方 CSS minify warning）。
- 未测风险：真实生产数据量下 browser/API SLO、PostgreSQL EXPLAIN、完整 explorer/cursor、遮罩、Audit 和剩余后端旧模块删除；统一部署前均不宣称闭环。
- 后续事项：本轮保持 `DEPLOYMENT_HOLD`；下一轮只能根据 05-05 实际完成状态生成一个新 prompt，不预生成 05-06。

## 2026-07-16 - 结构化 rows、详情点查和旧 projection cache writer 删除

- 目标：执行 GSD 05-04，将大数组从 parent JSON 移出并优先消除详情的全期间线性扫描，同时删除已确认污染链路的旧无版本 Redis writer；不在同一切片引入 cursor API、Audit 拆分或前端 UI 改造。
- 影响范围：`0107` migration、成本 repository port/共享 repository 的 cost-owned 方法、cost projection、cost query service、成本测试与边界文档。未修改其他页面 API/read model，也未修改共享 query gateway 默认顺序。
- 关键决策：新增且只新增 `read_model.cost_statistics_bank_flow_rows`；保留现有 `cost_statistics_rows`。conditional publish 在同一事务写 metadata 与两类 month rows，parent/obsolete scope 删除同步清理两类 rows。parent snapshot 通过深拷贝只移除两类 arrays；view loader 只从结构化 rows 重建旧 DTO，禁止 dual-read。详情保持 cost-row 优先于 bank-flow-row 的旧语义，通过 `project_scope + transaction_id` 点查。
- 旧代码删除：删除 `CostStatisticsSqlProjectionBuilder` 的 `cost_statistics:explorer:{scope}` set/delete 和 cost-local `_set_redis_json`；删除详情调用 `_require_fresh_explorer("all")` 后扫描两类 arrays 的路径；parent builder 删除从 child payload 解析 `bank_flow_time_rows` 的路径。
- 测试覆盖：结构化写入与 parent metadata quarantine、父聚合结构化读取、无旧 JSON fallback、identity SQL/详情 no-full-view、tag selection、旧 Redis writer 零调用、migration table/index/grant 和既有 API/export shape。
- 未测风险：真实 PostgreSQL 迁移后的全 scope rebuild、索引计划、生产行数/并发 SLO、Audit 和浏览器遮罩需在后续切片与统一部署窗口验证。
- 后续事项：下一轮必须基于本轮真实完成状态选择唯一剩余高风险切片；不得预先生成多个 prompt。本轮保持 `DEPLOYMENT_HOLD`，不 stage/commit/deploy。

## 2026-07-15 - 单次跨月银行明细快照边界

- 生产证据：v7 精确 main SHA `a62393663f5fd38a0bd150689e61e7c92a985179` 的 branch/main CI 与官方部署、19-scope Workbench rehydrate 均成功，520 元 OA/发票正式关系可见且 Workbench 无完整性问题；但两个 `2026-07` 成本事件在约 52 秒已达 18/17 attempts，约 71 秒升至 48/47，证明三个无写副作用的 bank-detail 读取仍会在一次 projection 内观察到不同 freshness 时点。release 已立即回滚到 `etc-import-e5d6e6a4e-20260714-visibility`，旧 Workbench 重建后 queue/dirty scope 全部排空，failed job 为 0。
- 根因：v7 消除了 read-side enqueue TOCTOU，但 cost month 仍依次读取 source versions、正式关系流水标签和目标月全流水。并发 fan-out 下三个独立 status gate 不能组成一个一致性依赖快照，runtime worker 因而持续 defer 同一成本事件。
- 修复：先从 Workbench active generation 读取正式 paired groups 和关系流水 ID，再通过 `BankTransactionTagReadFacade.snapshot_for_month(...)` 进行唯一一次 dependency I/O。repository 在 `REPEATABLE READ READ ONLY` transaction 内返回目标月 rows、关系引用的跨月 rows、全部涉及 scope 的 freshness/signatures；projection 纯内存拆分，目标月 rows 生成全流水统计，完整 rows 只补关系标签。
- 跨月边界：正式关系可把其他月份的成员补入当前 Workbench shard；快照因此必须接收关系流水 ID，禁止只读目标月后把合法跨月成员静默降为未分类。同时跨月补充 rows 不得进入目标月 `bank_flow_time_rows`，避免污染月份统计。成本 source-version fresh gate 仍绑定目标月 bank-detail signature，保持现有 API/Audit 合同不变。
- 旧链路删除：cost projection 不再调用 `source_versions_for_scope_keys(...)`、`get_by_transaction_ids(...)` 或 `list_by_month(...)`；三次独立读取和旧 cost-specific enqueue reason 均不属于新链路。现有 facade 方法可继续服务其他 owner，不是成本统计兼容 fallback。
- 测试：成本 projection 锁定唯一 snapshot call、跨月标签可用、跨月补充行不进入目标月全流水、非 fresh 不保存；facade/repository 测试锁定一次快照 I/O、目标月/跨月 rows 分离、全部 scope freshness 与无 read-side enqueue。
- 生产门禁：v8 exact-SHA branch/main CI 后只允许官方部署；Workbench rehydrate 后 durable queue 首次排空还必须延迟至少 120 秒复核仍为空，再执行 Workbench、bank-details、cost-statistics Audit、520 关系和 ETC/migration/data count 复验。任一 cost attempts 持续增长或 queue 不收敛立即回滚。

## 2026-07-15 - 银行明细 dependency read 纯读边界

- 生产证据：v6 精确 SHA `920a5a27a08afa23743c811248e591b7dfe702b2` 部署和 Workbench 重建成功，但约 38 秒时两个成本月份事件已达 22 attempts；近 15 分钟指标记录 357 次 bank-detail 完成和 173 次 cost-statistics 完成，bank-detail p95 仅约 434ms，排除“单次银行投影耗时过长”。release 已立即回滚，旧 Workbench 重建后 queue/dirty scope 排空并延迟复核稳定。
- v7 根因结论：active coalescing 只能看 enqueue 时刻是否仍有 pending/processing outbox，无法原子覆盖“cost 在 T1 读到 refreshing、bank worker 在 T2 完成并 ack、cost 在 T3 基于过时读结果 enqueue”的 TOCTOU 窗口。reason 统一只能缩小竞态，不能消除读侧写 I/O；v7 生产进一步证明，纯读之后三个独立 snapshot 时点仍不足以保证一次 projection 收敛。
- 修复：三个 cost projection bank-detail 读取统一使用 `require_fresh=False`；projection 自己检查 `status=fresh` 并 fail-closed，`RuntimeWorker` 成为唯一 dependency refresh 调度 owner。transaction tag 路径改用 facade 的 `get_by_transaction_ids(...)` 读取完整 status envelope，再从同一 fresh payload 归一化标签。
- 边界：不改 API、业务金额、read model schema、repository、gateway、worker 状态机、数据库或 migration；删除的是 projection read 隐含 enqueue 行为，不新增兼容 fallback。
- 测试：完整月份投影锁定三个 pure-read 参数与金额/标签输出；非 fresh projection 不写成本 read model；真实 facade 锁定 non-fresh diagnostic reads 不写 queue。
- 生产门禁：main 精确 SHA CI 后重新部署，必须证明 bank-detail/cost sample 不再异常放大，durable queue 首次排空后延迟复核仍为空，再执行 Workbench、bank-details、cost-statistics Audit 和 520 关系验证。

## 2026-07-15 - 银行明细三个 fresh read gate 完整收敛

- 生产证据：v5 部署后 Workbench 重建成功，但 `cost_statistics active/all:2026-07` 在约 110 秒内达到 140 attempts；新 release 已立即回滚，旧 release 重建后恢复 `pass/fresh/drained` 和空 durable queue。
- 遗漏根因：v5 只收敛 source-version read；同一 projection 的 transaction tag read 与 month row read 仍使用 `cost_statistics_bank_tag_read`、`cost_statistics_bank_flow_rows`，可在并发 fan-out 窗口绕过 active coalescing。
- 修复：删除两个 cost-specific reason；三个要求 fresh 的银行明细读 I/O 统一复用 `downstream_bank_tag_read`。不改 gateway、worker、repository、状态、migration 或业务数据。
- 测试：完整 month projection 锁定三个 facade 调用 reason；既有 gateway 测试继续证明 active `bank_detail` scope 不重复写 dirty/outbox。
- 生产门禁：Workbench、`bank-details`、`cost-statistics` Audit 必须 `pass/fresh/drained`，durable queue 延迟复核仍为空，否则立即回滚。

## 2026-07-15 - 银行明细依赖 active coalescing

- 目标：修复 Workbench schema 切换后成本月份 shard 等待同一 `bank_detail` scope 时，成本 worker 与银行 worker 互相制造下一条 pending event 的不收敛循环。
- 根因：成本 projection 使用未登记的 `cost_statistics_bank_tag_source_versions` reason，绕过统一 gateway 已有的 ensure/wakeup active coalescing；不是业务数据、projection rows 或 migration 损坏。
- 关键决策：删除该专用 reason，复用既有 `downstream_bank_tag_read`；不新增状态、队列逻辑、repository、worker、fallback 或 migration。
- 测试覆盖：成本 projection 锁定 reason；gateway 锁定 active `bank_detail` scope 不重复写 dirty/outbox。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh tests.test_read_model_refresh_gateway.ReadModelRefreshGatewayTests.test_ensure_refresh_reason_does_not_bump_active_scope -v`。
- 生产门禁：部署后 Workbench 与 `bank-details`、`cost-statistics` 页面 Audit 都必须 `pass/fresh/drained`，并确认 durable queue/dirty scopes 最终为空。

## 2026-07-14 - 成本统计紧凑账本式排版

- 目标：提升五种成本统计视图的金额比较效率、标题区信息密度和三栏下钻扫读体验，避免大卡片和独立时间列挤占宽度。
- 影响范围：`CostStatisticsPage` 顶部导航与摘要、`CostStatisticsTable` 复合 cell text、成本统计样式、Vitest/Chromium 页面回归；后端与业务口径不变。
- 关键决策：分类与标题同排；范围控件固定在下一行最左；金额由左侧语义标签与右对齐 tabular 数字组成；OA 三类统一使用“支出”；项目/银行/费用类型/标签下钻把时间放入户名或项目名下方 chip，`按时间`主表保留独立时间列；桌面 explorer 使用同一 viewport 高度并让各栏独立滚动。
- 文档影响：更新模块 README、boundary I/O 展示合同、测试矩阵和本实施记录；产品口径、API、read model/worker 长期事实源不变。
- 测试覆盖：`CostStatisticsPage.test.tsx` 覆盖五视图 DOM/样式/复合单元格；`cost-statistics-flow.spec.ts` 在真实 Chromium 覆盖导航、时间 chip 与三栏等高。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产超长文本、非默认缩放和极大数据量下的最终视觉密度需 staging/manual smoke。
- 后续事项：如窄屏真实使用率上升，再基于实际断点数据调整分类组换行，不新增第二套移动端视图。

## 2026-07-13 - 流水统计按收入与支出双方向闭环

- 目标：让按时间、按标签统计完整消费银行收入与支出，并按用户确认的层级分别展示金额和笔数。
- 影响范围：成本统计 SQL projection、read model schema/Audit、query/export API、AppSettings 标签选择 schema、成本统计页面和导出中心；OA 配对统计不变。
- 关键决策：不展示合并总金额或净额；金额均为正数绝对值；收入绿色、支出橘色；主标签、子标签均分列收支，明细保留方向；收入标签进入同一规则；新增 `bank_tag` 导出。
- 文档影响：同步产品口径、API contract、read-model contract、cost-statistics/settings boundary、E2E spec/coverage 和测试矩阵。
- 测试覆盖：backend projection/query/API/settings/Audit contract，frontend mapper/component/interaction，deterministic Browser flow。
- 未测风险：生产历史 read model 需由 schema v8 freshness gate 触发重建；真实生产数据量 XLSX 打开耗时仍需 staging smoke。

## 2026-07-12 - 成本流水展示字段 Audit 与 canonical 文本优先级对齐

- 目标：消除成本统计 Audit 对未配对 OA 银行流水「费用内容」的假阳性，保持关键展示字段独立重算证明。
- 影响范围：仅调整 `cost_statistics` 页面 Audit 的 expected value 重算及全局 Audit 合同版本；不改成本 read model builder、页面 API、业务数据或队列。
- 关键决策：与正式 `CostStatisticsSqlProjectionBuilder` 对齐，「费用内容」按银行明细 canonical 文本 `summary -> purpose -> payload.remark -> 标签`重算；不通过忽略字段或放宽比较绕过证明。
- 文档影响：Audit 合同升级为 `page-audit-contract.v25`；模块边界和 I/O 不变。
- 测试覆盖：`test_cost_statistics_bank_flow_recalculation_uses_bank_detail_scope_owner` 锁定 scope owner 与完整文本 fallback 链，Audit/API 合同测试锁定 v25。
- 未测风险：只有当生产单一 System Audit 快照中所有登记业务页均为 `pass / fresh / drained` 时才算闭环。

## 2026-07-05 - 父 scope rollup 热路径索引

- 目标：降低写操作 fan-out 后 `cost_statistics:active:all` / `all:all` 父 scope 从月 shard 聚合的 I/O 成本，收敛生产 1 秒目标附近的长尾。
- 影响范围：新增 migration `0092_cost_statistics_parent_rollup_hot_path.sql`，只给 `read_model.cost_statistics_rows` 增加父聚合读取索引；不改变成本归因、scope contract、read model payload、worker 事件、权限或审计。
- 关键决策：父 scope 仍从已物化月 shard rows 聚合，不回读 Workbench all 或 live service。索引按真实过滤/排序口径覆盖 `project_scope`、`scope_month`、`trade_date desc nulls last`、`trade_time_text desc`、`transaction_id`、`row_key`，避免为该热点新增服务层分支。
- 文档影响：本实施记录同步；模块边界仍保持 closed。
- 测试覆盖：`tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_cost_statistics_parent_rollup_hot_path_index_is_declared` 和 migration 顺序 pinning。
- 验证命令：`python3 -m pytest tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_expected_migration_files_are_present_and_ordered tests/test_postgres_migrations.py::PostgresMigrationDiscoveryTests::test_cost_statistics_parent_rollup_hot_path_index_is_declared tests/test_postgres_test_utils.py::PostgresTestUtilsTests::test_discover_stage06_migrations_is_pinned_to_current_set -q`。
- 未测风险：索引收益必须发布后用生产 write-operation cross-page audit、HTTP SLO 和必要时 `EXPLAIN (ANALYZE, BUFFERS)` 复核；本地测试只锁定 migration contract。

## 2026-07-05 - 成本统计模块化 Close：删除旧 fallback 和 live export 链路

- 目标：关闭 `boundary-io.md` 中的 `partial` 状态，移除会污染 SQL read model/fresh gate 的旧代码逻辑。
- 影响范围：`CostStatisticsQueryService`、`CostStatisticsRuntimeService`、`CostStatisticsService`、derived lifecycle plan/executor、成本统计 API tests、静态边界守卫和模块文档。
- 关键决策：query service 只读取 SQL read model/Redis fresh cache；缺失、stale 或 repository unavailable 时返回 `refreshing` envelope 并入队 `cost_statistics.read_model.refresh`，不再同步调用 live `CostStatisticsService` 或 local read model fallback。runtime service 不再接收 `explorer_loader`，旧 `cost_statistics_cache_warmup` 入口仅关闭历史 job 或桥接 refresh，不写 read model/Redis fresh cache。live `CostStatisticsService.get_export_preview/export_view`、`ProjectDetailExportService` 和对应旧测试已删除；当时导出由 `CostStatisticsQueryService` 从 fresh explorer read model 组装，该 full-payload 读取随后由 05-15 迁到 bounded export-page SQL。
- 文档影响：更新 `README.md`、`boundary-io.md`、`tests.md`、`state-machine.md` 和本实施记录。
- 测试覆盖：更新 `tests/test_cost_statistics_api.py` 使用内存 SQL repository 验证 SQL read model 命中、API miss fail-closed、invalidation enqueue refresh、历史 warmup retry 关闭旧 job；更新 `tests/test_cost_statistics_service.py` 保留 business-core 成本归因；更新 `tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_derived_data_lifecycle_service.py` 和 `tests/test_platform_runtime_boundary_guards.py` 锁定不再回退 warmup。
- 验证命令：`python3 -m pytest tests/test_cost_statistics_api.py tests/test_cost_statistics_service.py tests/test_cost_statistics_runtime_service.py tests/test_cost_statistics_derived_lifecycle_executor.py tests/test_derived_data_lifecycle_service.py -q`；`python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_platform_runtime_boundary_guards.py -q`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis worker drain、生产 p95/p99 和全浏览器回归需按最终验证命令继续执行。
- 后续事项：生产发布前后继续执行成本统计 HTTP SLO、route shell/browser smoke 和 worker/App Status 检查。

## 2026-07-03 - Workbench group payload 去重后的成本输入迁移

- 目标：配合 Workbench active generation payload owner 边界迁移，避免成本统计继续依赖 `workbench_groups.payload` 的旧成员数组。
- 影响范围：`CostStatisticsSqlProjectionBuilder._cost_entries_from_workbench(...)`、Workbench read model generation payload 合同、成本统计状态机/实施记录、read-models 持久化文档；不改变成本归因业务规则、scope contract、API response 或前端页面行为。
- 关键决策：成本统计 worker 先从 Workbench 月份 active generation 的 `workbench_group_rows + workbench_rows` materialize 成本关系输入，再复用既有 `is_candidate_workbench_group`、`is_cost_eligible_open_group` 和 `_cost_context_from_oa_rows` 业务判断；禁止恢复 `jsonb_path_exists(workbench_groups.payload, ...)` 读取旧 JSON 成员。
- 文档影响：更新成本统计状态机/实施记录、read-models boundary、关联台 boundary 和持久化架构文档。
- 测试覆盖：`tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts` 锁定 SQL 必须 join `workbench_group_rows` 与 `workbench_rows`，且不再使用 `jsonb_path_exists`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_workbench_sql_runtime.py -q`。
- 未测风险：真实生产成本统计 worker drain 和高行数 SLO 仍需要随本轮生产 release 复测。

## 2026-06-25 - cost statistics route-owner local closure audit

- 目标：执行 `server-py:cost-statistics-route-owner-local-closure-audit`，确认 route callback collapse 后 `server.py` 剩余 cost statistics surface 是否仍有本地 route-owner 缺口。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、cost-statistics 实施记录；不改变成本归因、项目范围、read model freshness、parent aggregate、cache、worker、导出或前端行为。
- 关键决策：`server.py` 已无 `_handle_api_cost_statistics*` callback；剩余 cost statistics 方法被归类为组合根、query/runtime、source-version、persistence、cache、worker、warmup、import-scope 或 platform adapter 端口。本地 route-owner 支持 accounted，但不声明模块/生产闭环。
- 文档影响：新增 modular IO cost statistics route-owner local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；成本统计状态机定义不变。
- 测试覆盖：本轮为分析/状态机闭合，未改运行时代码；沿用 Row376 的 `tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py` 和 `tests/test_platform_runtime_boundary_guards.py` route-owner Guard。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实生产高行数、真实浏览器生产样本和 admin/write evidence 仍为最终验证范围。
- 后续事项：执行 `server-py:turnover-ledger-route-owner-audit`。

## 2026-06-25 - cost statistics route callback collapse

- 目标：执行 `server-py:cost-statistics-route-callback-collapse`，把 `/api/cost-statistics*` HTTP dispatch/query parsing 从 `server.py` 迁入 `CostStatisticsApiRoutes.route(...)`。
- 影响范围：`backend/src/fin_ops_platform/app/routes_cost_statistics.py`、`backend/src/fin_ops_platform/app/server.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` 和 modular IO autonomous state。
- 关键决策：保留既有 handler/response contract，不改变成本归因、项目范围、read model freshness、parent aggregate、cache、worker、导出或前端行为；导出 flag 的 optional bool parsing 作为显式 route-owner port 注入。
- 文档影响：新增 modular IO cost statistics route callback collapse analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；成本统计状态机定义不变。
- 测试覆盖：`tests/test_cost_statistics_api.py` 覆盖 API shape/export/project scope；`tests/test_cost_statistics_sql_runtime.py` 覆盖 route-owner path 下 SQL/Redis/freshness fail-closed；`tests/test_platform_runtime_boundary_guards.py` 新增 Guard 防止 `_handle_api_cost_statistics*` callbacks 回到 `server.py`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/server-py-cost-statistics-route-callback-collapse-2026-06-25.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实生产高行数、真实浏览器生产样本和 admin/write evidence 仍为最终验证范围。
- 后续事项：执行 `server-py:cost-statistics-route-owner-local-closure-audit`。

## 2026-06-25 - cost statistics route-owner audit

- 目标：执行 `server-py:cost-statistics-route-owner-audit`，审计 `/api/cost-statistics*` 在 `server.py` 的剩余 route ownership。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、cost-statistics 实施记录；不改变成本归因、项目范围、read model freshness、parent aggregate、cache、worker、导出或前端行为。
- 关键决策：`CostStatisticsApiRoutes` 已拥有 month/explorer/project/export/export-preview/transaction 的 response mapping；`server.py` 剩余 `_handle_api_cost_statistics*` callback 是 query/path 参数解析后的薄委托。下一条边界选择 route callback collapse，把 `/api/cost-statistics*` dispatch/query parsing 移入 route owner。
- 文档影响：新增 modular IO cost statistics route-owner audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt；成本统计状态机定义不变。
- 测试覆盖：本轮为分析/状态机闭合，未改运行时代码；下一实现边界需更新 `tests/test_platform_runtime_boundary_guards.py` 并复跑 `tests/test_cost_statistics_api.py`。
- 验证命令：`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实生产高行数、真实浏览器生产样本和 admin/write evidence 仍为最终验证范围。
- 后续事项：执行 `server-py:cost-statistics-route-callback-collapse`。

## 2026-06-24 - Modular IO post-full-state local closure audit

- 目标：执行 `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`，在 full-state snapshot quarantine 后复核成本统计本地实现是否还有必须先修的 implementation gap。
- 影响范围：`Application` cost statistics route/runtime/query delegates、`CostStatisticsRuntimeService`、`CostStatisticsQueryService`、worker/App Status/manifest registry、modular IO state；不改变运行时代码。
- 关键决策：未发现新的本地 implementation gap。成本统计本地支持在 repository port、SQL fresh gate、parent aggregate、worker registry、derived lifecycle executor、runtime warmup/retry/rebuild owner、explicit persistence 和 full-state snapshot quarantine 方面已 accounted；local compatibility fallback 和 startup snapshot load 不作为生产闭环证据。
- 文档影响：新增 post-full-state local closure audit analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵。
- 测试覆盖：本轮是 analysis/accounting only；复用 `tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_derived_lifecycle_executor.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_architecture_guards.py` 作为本地证据。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-full-state-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；不声明 `cost_statistics` module closed。
- 后续事项：执行 `read-models:next-pilot-selection-after-cost-statistics`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO full-state snapshot quarantine

- 目标：执行 `read-models:cost-statistics-full-state-read-model-snapshot-quarantine`，移除 broad `_persist_state(...)` 对 `cost_statistics_read_models` 的旧全状态写入。
- 影响范围：`Application._persist_state(...)`、read model architecture guard、modular IO state；不改变成本归因、项目范围、导出、parent aggregate、API、UI、worker event、queue schema 或 Redis envelope。
- 关键决策：`_persist_state(...)` 不再 serializes `cost_statistics_read_models`，避免 broad full-state snapshot 成为成本统计 read model 第二写入路径。当时显式 persistence 和 startup compatibility load 暂时保留；两者已由 2026-07-16 的 05-13 删除，本条仅记录迁移过程。
- 文档影响：新增 full-state snapshot quarantine analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵。
- 测试覆盖：当时扩展 `tests/test_read_model_architecture_guards.py`，证明 broad full-state writer 不写成本或税金 read model；当前 guard 已进一步禁止成本进程内 service、startup field 和显式 persistence helper 回归。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-full-state-read-model-snapshot-quarantine.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；`cost_statistics` 仍需 post-full-state local closure audit，不声明模块 closed。
- 后续事项：执行 `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO post-derived local closure audit

- 目标：执行 `read-models:cost-statistics-post-derived-local-implementation-closure-audit`，在 repository port、freshness/barrier 和 derived lifecycle executor extraction 后重新审计成本统计本地实现闭环。
- 影响范围：`Application._persist_state(...)`、cost statistics warmup/retry/rebuild app delegates、`CostStatisticsRuntimeService`、worker registry、modular IO state；不改变运行时代码。
- 关键决策：warmup/retry/rebuild app 方法均为 `CostStatisticsRuntimeService` 的 compat-only delegate，`cost-tax` 仍是 manifest/registry 记录的 compat lane；但 broad `Application._persist_state(...)` 仍把 `cost_statistics_read_models` 写入旧全状态 snapshot，属于本地 implementation gap。
- 文档影响：新增 post-derived local closure audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only；下一实现边界必须新增/更新 static guard，防止 broad `_persist_state(...)` 再写 `cost_statistics_read_models`。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-derived-local-implementation-closure-audit.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-full-state-read-model-snapshot-quarantine`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO derived lifecycle executor extraction

- 目标：执行 `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`，把成本统计 derived lifecycle invalidation、warmup-vs-refresh fallback、metadata propagation 和 `enqueued_jobs` accounting 从 `Application` 移到显式 service 边界。
- 影响范围：新增 `CostStatisticsDerivedLifecycleExecutor`，调整 `Application` lifecycle registry 和 executor factory，新增 executor unit tests/static guard；不改变成本归因、项目范围、导出、parent aggregate、API、UI、worker event、queue schema 或 Redis envelope。
- 关键决策：`Application._derived_lifecycle_cost_statistics_executor(...)` 已删除并由 guard 防回归；`Application._cost_statistics_derived_lifecycle_executor(...)` 仅组装 `CostStatisticsRuntimeService`、gateway-backed generic refresh callback 和 `ReadModelRefreshGateway.can_enqueue()` callback。
- 测试覆盖：新增 `tests/test_cost_statistics_derived_lifecycle_executor.py`，覆盖 explicit/all/empty scopes、`pending_invoice_rules_changed` `persist_empty=False`、no-warmup fallback metadata 和 job accounting；`tests/test_platform_runtime_boundary_guards.py` 新增 explicit executor boundary guard。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-derived-lifecycle-executor-port-extraction.md`。
- 未测风险：真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred；warmup/retry wrappers、`Application.rebuild_cost_statistics_read_model_scope(...)` 和 broad `_persist_state(...)` 成本统计 snapshot 仍需下一条 local closure audit 分类。
- 后续事项：执行 `read-models:cost-statistics-post-derived-local-implementation-closure-audit`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO freshness and barrier audit

- 目标：执行 `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`，复核 repository port 之后成本统计 freshness、operation barrier、parent aggregate、worker ownership 和 legacy/app-owned surface。
- 影响范围：`CostStatisticsQueryService`、`CostStatisticsRuntimeService`、`CostStatisticsReadModelRefreshService`、`CostStatisticsSqlProjectionBuilder`、`Application._derived_lifecycle_cost_statistics_executor(...)`、成本统计 tests/docs、modular IO state；不改变成本归因、项目范围、导出、API、UI、worker event、queue schema 或 Redis envelope。
- 关键决策：SQL fresh gate、production repository unavailable fail-closed、force refresh scope normalization、parent aggregate proof、primary `cost-statistics` worker 和 `cost-tax` compatibility lane 均有本地证据；但 `Application._derived_lifecycle_cost_statistics_executor(...)` 仍直接编排成本统计 lifecycle invalidation、warmup/refresh fallback 和 `enqueued_jobs` accounting，必须先抽取为显式 executor，不能进入 Go summary-rollup admission。
- 文档影响：新增 freshness/barrier audit analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮是 analysis/accounting only；下一实现边界必须新增/更新 derived lifecycle executor/static guard tests。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 App Status/high-row/browser evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO repository port extraction

- 目标：执行 `read-models:cost-statistics-repository-port-extraction`，把成本统计 read model load/get/save surface 收窄到显式 repository port。
- 影响范围：`CostStatisticsReadModelRepositoryPort`、`CostStatisticsSqlProjectionBuilder`、`PostgresStateStore.cost_statistics_sql_read_repository`、成本统计 SQL runtime/state-store tests；不改变成本归因、项目范围、导出、parent aggregate、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策（历史，已由 05-14 收窄）：当时新增 `CostStatisticsReadModelRepositoryPort` 并保留全量 load、单 scope view 与无条件 save；`CostStatisticsSqlProjectionBuilder` 和 PostgreSQL SQL read wiring 使用该 port。05-14 已删除其中全量 load / 无条件 save，当前 port 只保留 scoped reads 与 source-version conditional publish；SQL/table owner 仍是 `PostgresReadModelRepository`。
- 文档影响：新增 modular IO repository port extraction analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵。
- 测试覆盖：新增 `CostStatisticsReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`，扩展 `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection`，复跑成本统计 SQL projection parent/month 目标测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实大数据性能、真实浏览器生产样本和生产 scope cleanup evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO pilot selected after tax offset

- 目标：执行 `read-models:next-pilot-selection-after-tax-offset`，确认 `cost_statistics` 是否应作为 tax offset 之后的下一非 Go read model 模块化试点。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵；不改成本归因、API、UI、worker、queue 或 Redis 合同。
- 关键决策：选择 `cost_statistics`。本模块同时消费 Workbench relation、银行明细标签、导入事实、ETC/no-OA/turnover/settings fan-out；还拥有 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all` 特殊 scope、queryable parent aggregate 和旧 `cost-tax` compatibility worker lane。首切为 `CostStatisticsReadModelRepositoryPort` 抽取。
- 文档影响：新增 modular IO next-pilot selection analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮为 analysis/accounting only；下一实现切片必须新增/更新 repository port guard，并保持 SQL runtime/freshness/parent aggregate 测试通过。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实大数据性能、真实浏览器生产样本和生产 scope cleanup evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-repository-port-extraction`；Go summary-rollup admission 继续 blocked。

## 2026-06-20 - 成本统计 explorer 加载失败刷新恢复

- 目标：补齐 `cost-statistics` 的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 explorer 首屏暂时 503 时页面显示正常空态、允许导出中心伪成功，或没有显式恢复路径。
- 影响范围：`web/src/pages/CostStatisticsPage.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/src/test/apiMock.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、成本统计和全局测试闭环文档；不改后端业务逻辑、成本归因、read model scope contract 或 API shape。
- 关键决策：页面新增显式 `刷新` 入口，手动刷新时清理 explorer cache 并触发重新请求；根 explorer 加载失败且没有可用 explorer 数据时禁用导出中心，但流水详情加载失败不禁用导出中心；deterministic mock 的 transient failure 只作用于当前可见月份 explorer，避免隐藏的 `month=all` 导出参考数据请求消耗失败次数。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`；新增 `web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium` 通过 9 tests；`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx` 通过 20 tests。
- 未测风险：本地 deterministic 503 不等于真实网络中断、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 或生产大数据恢复；这些仍需 infra-smoke/staging/production smoke。
- 后续事项：继续按全局 `NETWORK-RECOVERY` 队列补其他页面或 mutation 级失败恢复。

## 2026-06-19 - 生产 authenticated 成本统计 500 与 schema_version 查询修复

- 目标：修复生产 authenticated HTTP probe 暴露的成本统计 API 500，避免成本统计页面在真实登录态下无法作为 Spec-first runtime gate 的一部分闭环。
- 影响范围：`PostgresReadModelRepository.get_cost_statistics_view(...)`、`tests/test_cost_statistics_sql_runtime.py`、生产 release `main-bf02acc5-coststats-schema-20260619172500`；不改变成本归因、scope contract、payload shape、read model refresh 或前端展示。
- 生产证据：使用现有目标 OA 申请人凭据临时登录后，`/api/session/me` authenticated 通过，SSE first-event smoke 通过；full authenticated HTTP probe 发现 `/api/cost-statistics/explorer?month=2026-03&project_scope=active` 和 `/api/cost-statistics?month=2026-03&project_scope=active` 返回 `500 internal_server_error`。后端日志显示 `column "schema_version" does not exist`，位置在 `get_cost_statistics_view(...)` 查询 `read_model.cost_statistics_read_models`。
- 根因：`read_model.cost_statistics_read_models` 由 `0006_read_models.sql` 创建，表上没有顶层 `schema_version` 列；版本事实在 `payload` / `raw_payload` 内。旧测试模拟 row 带有 `schema_version` 字段，未约束 SQL 不选择不存在列。
- 修复与发布：新增 RED 测试 `test_repository_reads_cost_statistics_schema_version_from_payload_not_table_column`，确认 repository 从 payload 读取 schema version 且父表 SQL 不包含 `schema_version`；随后移除父表 select 中的 `schema_version`。在隔离 clean worktree 基于生产 commit `3d88ce99` 提交 `bf02acc5 Fix cost statistics read model schema query` 并发布激活。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_postgres_repositories_boundaries.py -q` 通过 `38 passed`；`PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；`git diff --check`；`VITE_APP_BASE_PATH=/fin-ops/ npm run build`。
- 发布后复验：`health_ready_payload_probe` 通过；`read_model_slo_smoke --apply --read-model-key output_invoice_collection --read-model-key cost_statistics --target-ms 5000` 通过，`cost_statistics:active:2026-04` 约 `2843.542ms`；两个成本统计 authenticated endpoint 从 `500` 变为 `200`。
- 未测风险：full authenticated HTTP gate 仍未闭合，因为生产缺 admin 登录态导致 admin-only dashboard 403，且 `output-invoice-collections` 默认 `all` 读路径仍返回 `read_model_status=refreshing`。

## 2026-06-19 - 生产 direct refresh SLO 失败与 rows 批量保存发布复验

- 目标：处理生产 critical read model apply gate 中 `cost_statistics:active:2026-04` 超过 5 秒 direct refresh SLO 的问题，避免成本统计真实 worker drain 成为 Spec-first E2E 总闭环尾部风险。
- 影响范围：`PostgresReadModelRepository._replace_cost_statistics_rows(...)`、成本统计 read model rows 写入性能、本模块实施记录；不改变成本归因、项目范围、scope contract、API shape、前端展示或导出行为。
- 生产证据：在 release `main-33a150e7-write-e2e-approval-gate-20260619151922` 执行 `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120`，15 个 critical scope 全部达到 dirty/outbox `done` 和 readiness `fresh`/`dirty_done`，但 `cost_statistics:active:2026-04` enqueue-to-fresh 约 6459.019ms。只重跑失败 scope 后，`invoice_lifecycle` 已通过，`cost_statistics:active:2026-04` 仍约 7003.227ms，说明成本统计不是一次性并发抖动。
- 根因调查：成本统计 month scope rebuild 最终调用 `_replace_cost_statistics_rows(...)`；该方法删除 scope rows 后对 `time_rows` 每行执行一次 `connection.execute(...)` insert/upsert。生产失败样本 handler duration 接近 enqueue-to-fresh duration，慢点集中在 handler 本身，逐行写入是当前最直接根因。
- 修复与发布：新增 `tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch`，先 RED 证明 `executed_many` 为 0；随后将 rows 保存改为收集 params 并调用 `_execute_many(...)`，保持 delete、字段映射、`on conflict (scope_key, row_key)` 和同一事务不变。为避免混入主工作区未提交变更，基于生产 commit `33a150e7` 创建隔离 clean worktree，提交 `3d88ce99 Optimize cost statistics read model row saves`，通过 release `main-3d88ce99-coststats-batch-20260619170500` 发布激活。
- 发布后复验：新 release 上 `health_ready_payload_probe` 通过，`runtime_release.consistent=true`、`runtime_blocker_count=0`；`read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120` 15/15 pass，summary p50 约 490.393ms、p95/max 约 3176.5ms，`cost_statistics:active:2026-04` 降至约 3176.5ms。
- 文档影响：同步 `docs/modules/read-models/implementation-notes.md` 与全局 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 repository boundary 性能合同测试；既有成本统计 SQL runtime 测试继续覆盖 read model payload、freshness、cache 和 API 行为。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch -q` 先 RED 后 PASS；`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_cost_statistics_sql_runtime.py -q` 通过 37 tests；`PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 通过。
- 未测风险：生产 direct refresh SLO 已复验通过；真实业务写操作 SLO、认证态 HTTP SLO 和受控 mutating write scenario 仍未闭环。

## 2026-06-19 - 成本统计 Spec-first covered 校准

- 目标：完成 `cost-statistics` 本地 Spec-first E2E Audit 校准，把剩余 `COST-E2E-007`、`COST-E2E-009` 和 `COST-E2E-010` 从 partial 收敛为 covered。
- 影响范围：成本统计 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：成本页当前无写入口，页面权限风险集中在 read/export，`read_export_only` 当前筛选下载、forbidden/expired/API auth 与全局 role matrix/API contract 足以覆盖 `COST-E2E-007`；导出 Browser download event、文件名、请求筛选和内容字段已覆盖，真实 workbook 打开归 staging/manual 风险，不阻塞 `COST-E2E-009`；银行/发票/ETC 导入、bank-flow、turnover、settings 和 Workbench relation 已有成本统计 fresh read model 或下游影响行 Browser 证据，search 目前无独立前端 route，由 API/runtime 证据覆盖，因此 `COST-E2E-010` 本地闭环。
- 文档影响：`docs/modules/cost-statistics/e2e-coverage.md` 将 `COST-E2E-007/009/010` 标记为 `covered`；`docs/dev/spec-first-e2e-inventory.md` 将 `cost-statistics` 页面状态更新为 `covered`。
- 测试覆盖：未新增测试；本轮是基于现有 `cost-statistics-flow`、`cost-statistics-relation-fanout`、导入/bank-flow/turnover/settings Browser specs 和后端 read model/API 证据做覆盖校准。
- 验证命令：待本轮运行 `bash scripts/verify.sh docs`、成本统计相关 Playwright specs 和 `git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 打开、真实大文件/历史模板、生产 scope cleanup `--apply`、未来独立 search Browser UI 和新增成本页写入口仍需 staging 或后续功能轮次。
- 后续事项：按全局队列继续推进其他 `spec-first-partial` 页面，优先 import、pending invoices、no-OA/turnover/batch-accounting 或真实 infra smoke。

## 2026-06-19 - 成本统计 detail/export non-fresh Browser 防伪成功

- 目标：补齐 `COST-E2E-006` 在 fresh explorer 下的 detail/export non-fresh Browser 负面路径，避免只证明主 explorer 非 fresh 防 false-empty。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/cost-statistics-flow.spec.ts`、成本统计 Spec-first 覆盖矩阵、测试矩阵和全局 testing closure 文档；不改产品代码。
- 关键决策：扩展 deterministic mock 的 `costStatisticsTransactionDetailReadModelStatus` 和 `costStatisticsExportReadModelStatus`，让 transaction detail、export-preview 和 export 能返回 `cost_statistics_*_not_fresh` 409。Browser 用例在 fresh explorer 下触发详情和导出，断言不打开旧详情、不显示旧预览表、不触发 download，并展示“成本统计数据正在刷新，请稍后重试导出。”。预期 409 会产生浏览器资源日志，测试只允许该预期日志，不允许其他 console/page/request/dialog 错误。
- 文档影响：`COST-E2E-006` 从 `partial` 更新为 `covered`；当时成本统计整体仍保持 `spec-first-partial`，现已由本文件上方 “成本统计 Spec-first covered 校准” 记录取代。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::does not treat non-fresh transaction detail or export responses as successful results`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium -g "does not treat non-fresh transaction detail"`；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：真实 RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 打开、生产大数据和 search 外层 UI 仍需后续轮次或 staging smoke。
- 后续事项：已完成 `COST-E2E-010` 本地闭环校准；真实 worker drain、真实 XLSX 和未来 search Browser UI 继续作为 staging/后续功能风险。

## 2026-06-19 - 成本统计按银行/费用类型 Browser baseline

- 目标：补齐 `COST-E2E-001` 的真实浏览器 bank/expense baseline，避免成本统计只用 Vitest/API 证明按银行和按费用类型视图。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、成本统计 Spec-first 覆盖矩阵、测试矩阵和全局 testing closure 文档；不改产品代码或 API mock shape。
- 关键决策：复用现有 deterministic 成本 explorer 数据，在同一 Chromium 用例中从成本统计页切到按银行，选择 `工商银行 账户 0001` 和 `云南溯源科技`，断言银行对应流水表展示 `PLC 模块采购` 与供应商并打开流水详情；再切到按费用类型，选择 `设备货款及材料费`，断言费用类型流水表和详情可用。用例收集 console/pageerror/requestfailed/dialog，防止“页面显示了但浏览器报错”被误判为通过。
- 文档影响：`COST-E2E-001` 从 `partial` 更新为 `covered`；当时成本统计整体仍保持 `spec-first-partial`，现已由本文件上方 “成本统计 Spec-first covered 校准” 记录取代。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::shows bank and expense-type baselines with drilldown details`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium -g "shows bank and expense-type baselines"`；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：真实生产超大数据、真实 worker drain、真实 XLSX workbook 打开和 search 外层 UI 仍需后续轮次或 staging smoke。
- 后续事项：继续审计 `COST-E2E-006` detail/export non-fresh 和 `COST-E2E-010` 真实基础设施 fan-out。

## 2026-06-19 - 成本统计大数据窄屏宽表 Browser 覆盖

- 目标：补齐 `COST-E2E-008`，用真实 Chromium 证明成本统计在大数据、长字段、390px 窄屏下不是只返回 fresh payload，而是表格和下钻交互仍可用。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计测试矩阵、Spec-first 覆盖矩阵和全局 testing closure 文档。
- 关键决策：
  - 新增 opt-in deterministic mock `costStatisticsLargeDataset`，默认成本统计数据不变；启用时向 `2026-03` active/all explorer 增加 120 条长项目名、长对方户名、长费用内容和多费用类型成本行。
  - Browser 流先等待 `/api/cost-statistics/explorer?month=2026-03&project_scope=active` 返回 `read_model_status=fresh` 和 120+ rows，再断言按时间表存在大数据行、表格可横向/纵向滚动、右侧列在 viewport 内、导出入口未被遮挡且无浏览器错误。
  - 切到按项目后继续等待 `active:all` fresh explorer，选择长项目和费用类型，断言项目对应流水表展示长字段并可横向/纵向滚动。
  - 首次运行失败属于测试断言问题：按时间表本来不展示对方户名，已把对方户名断言放到项目下钻表；第二轮失败属于 HeroUI 表头包装层导致的 `elementFromPoint` 假阳性，表头改为 viewport 可见性，按钮/选择器仍保留未遮挡检查。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 新增 `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables fresh, scrollable, and usable on narrow screens`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的成本统计 large dataset mock。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker；真实 enqueue-to-fresh drain、生产超大数据查询/下载耗时、真实 XLSX 打开和生产视觉性能仍需 staging/production smoke。
- 后续事项：继续推进真实基础设施 worker drain、其他页面 relation 字段导出或更多撤销链路。

## 2026-06-19 - settings project scope 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明设置页项目状态变化后，成本统计通过自己的 active/all project scope read model 展示一致结果。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和 settings 测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `settingsProjectScopeFanout`，让 settings GET/POST 保留 `completed_project_ids`，并把保存后的完成项目集传给成本统计 explorer。
  - Browser 流保持 settings 主链路：设置页项目状态管理 -> 把 `昆明卷烟厂动力设备控制系统升级改造项目` 标记完成 -> 保存设置并断言 POST `completed_project_ids` -> 进入成本统计 -> 默认 active scope 不显示该项目 -> 切到 all scope 后显示该项目和金额 `4,800.00`。
  - 测试捕获 `pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog，避免 settings 保存成功但成本页浏览器报错被误判为通过。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、settings 测试矩阵/实施记录、全局 Spec-first inventory / testing closure state。
- 测试覆盖：
  - 更新 `web/e2e/settings-data-reset-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 settings -> cost statistics project scope fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd settings lifecycle 与 cost-statistics worker；真实 enqueue-to-fresh drain、历史 settings payload 和 search 联动仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - turnover manual closure 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明外部往来手动闭环确认后，成本统计不是只依赖周转页成功 toast，而是重新读取自己的 fresh read model 并展示闭环成本行。
- 影响范围：`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和外部往来测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `turnoverCostFanout`，仅在外部往来闭环已确认且测试显式启用时，把 `turnover-bank-expense-1000` 作为 `2026-05` 的外部往来闭环成本行暴露给成本统计；默认成本统计 mock 不变。
  - Browser 流保持外部往来主链路：选择同组两条流水 -> confirm closure -> operation barrier -> 成本统计 fresh explorer -> 按项目/费用类型/流水表展示 `外部往来闭环成本项目`、`外部往来款付款`、`浏览器 e2e 归还借款` 和 `建设银行` -> 回外部往来完成撤回并验证闭环 chip 移除。
  - 测试捕获 `pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog，避免“关系已建立但浏览器报错”被误判为通过。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/modules/turnover-ledger/tests.md`、`docs/modules/turnover-ledger/implementation-notes.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 更新 `web/e2e/turnover-ledger-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 turnover -> cost statistics fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `turnover-ledger` 与 `cost-statistics` worker；真实 enqueue-to-fresh drain、生产历史周转关系和大数据页面性能仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - no-OA submit 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明 no-OA 手续费批次提交后，成本统计不是依赖本页状态或静态数据，而是重新读取自己的 fresh read model 并展示 no-OA 成本行。
- 影响范围：`web/e2e/bank-flow-rule-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和 no-OA 测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `noOaCostFanout`，仅在 no-OA 批次已提交且测试显式启用时，把 `no-oa-bank-e2e-001` 作为 `2026-05` 的免 OA 手续费成本行暴露给成本统计；默认成本统计 mock 不变。
  - Browser 流保持 no-OA 主链路：选择未提交流水 -> submit-selection -> operation barrier -> 成本统计 fresh explorer -> 按项目/费用类型/流水表展示 `免OA手续费成本项目`、`手续费`、`网银手续费` 和 `建设银行` -> 回 no-OA 完成撤回和历史只读断言。
  - 首次运行失败属于测试 selector bug：`/手续费/` 同时匹配项目按钮和费用类型按钮；已收窄为 `/手续费 1 条流水/`，未发现产品逻辑问题。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/modules/no-oa-bank-batches/tests.md`、`docs/modules/no-oa-bank-batches/implementation-notes.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 更新 `web/e2e/bank-flow-rule-batches-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 no-OA -> cost statistics fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/bank-flow-rule-batches-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `no-oa-bank-batch` 与 `cost-statistics` worker；真实 enqueue-to-fresh drain、生产历史 no-OA 批次和大数据页面性能仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-07-05 - bank-flow submit 到成本统计 Browser fan-out 校准

- 目标：配合 `bank-flow-rule-batches` 模块 close，把 `COST-E2E-010` 的当前页面级 Browser 证据从历史 no-OA 入口校准为 bank-flow selected-row submit。
- 关键决策：`web/e2e/bank-flow-rule-batches-flow.spec.ts` 和 deterministic `apiMocks.ts` 使用 `bank-flow-rule-e2e-*` transaction id、`bank-flow-rule-batch-e2e-*` batch id、`bank_flow_rule_batch_*` stale reason 与 `流水规则手续费成本项目`，不再用旧 `no-oa-*` id 或“免OA”成本项目名表示 bank-flow 行为。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/modules/bank-flow-rule-batches/*`；上方 2026-06-19 记录作为历史上下文保留，不再代表当前 Browser 入口。

## 2026-06-19 - ETC 导入到成本统计 Browser fan-out 文档校准

- 目标：推进 `COST-E2E-010` 的导入类 fan-out 闭环，确认 ETC 导入确认后不是只在导入页显示 job success，而是进入成本统计页读取 fresh read model 并展示导入成本行。
- 影响范围：成本统计 Spec-first E2E 覆盖矩阵、测试矩阵、实施记录和全局 testing closure state；本轮不改业务代码。
- 关键决策：
  - 复用 `web/e2e/imports-etc-invoices-flow.spec.ts::confirms ETC import and observes downstream read models as fresh` 作为成本统计下游导入 fan-out 的 Browser 证据，避免重复造一条只覆盖同一 mock 状态的成本页测试。
  - 该测试在 ETC confirm 后依次进入 ETC 票据、税金抵扣和成本统计；成本统计阶段等待 `/api/cost-statistics/explorer`，断言 `read_model_status=fresh`，再切到按项目并展示 `ETC导入通行成本项目`、金额 `32.26`、`ETC高速通行费` 和 `ETC导入通行服务商`。
  - 当时 `COST-E2E-010` 仍为 `partial`：ETC 导入已有 Browser 证据；后续银行/发票导入、no-OA、turnover、settings 和权限/导出证据补齐后，已由本文件上方 covered 校准记录收敛。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：未新增测试；校准并验证既有 `web/e2e/imports-etc-invoices-flow.spec.ts` 中 ETC import downstream fan-out。
- 验证命令：`cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd import/cost-statistics worker；真实 ETC zip、对象存储、OA 草稿、enqueue-to-fresh drain、真实 search/historical repair 仍需 staging 或生产只读 smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - 成本统计导出 Browser download event

- 目标：补齐 `COST-E2E-009` 的本地 Browser 证据，避免成本统计只覆盖导出预览和 row-limit 错误，而没有真实 download event、文件名、筛选参数和导出字段保护。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计 Spec-first E2E 覆盖矩阵、测试矩阵和全局 testing closure state。
- 关键决策：
  - 成本统计 deterministic mock 默认仍返回 row-limit 400，保留既有错误反馈测试；只有 `costStatisticsExportDownloadSuccess` opt-in 时返回成功下载。
  - Browser 测试使用 `read_export_only` session，先跑 export-preview，再触发真实 download event，断言 `view=time`、`month=2026-03`、`project_scope=active`，且不带 `page` / `page_size`。
  - 本地下载体使用可读文本模拟 xlsx payload，锁定流水 ID、项目、费用类型、费用内容、对方户名、支付账户和筛选字段；真实生产 XLSX workbook 打开和完整解析仍留给 staging/manual smoke。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：
  - 新增 `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的成本统计导出成功 mock。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实生产/staging 后端生成真实 XLSX；真实 workbook 打开、格式、公式、超大数据耗时和代理下载头仍需真实环境 smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - 成本统计 read model 非 fresh Browser 防护

- 目标：补齐 `COST-E2E-006` 的真实浏览器负面场景，避免 explorer 返回 `refreshing` / `stale` / `failed` 空 payload 时，页面把它当作最终空态、0 条 summary 或允许导出非 fresh 成本数据。
- 影响范围：`CostStatisticsPage` 的 read model status gate、成本统计 deterministic Playwright mock、成本统计 Browser 主流程 spec、页面 Vitest 和模块 Spec-first E2E 文档。
- 关键决策：
  - `refreshing`、`stale`、`failed`、`missing`、`schema_mismatch`、`unavailable` 均视为非 fresh；非 fresh 时显示刷新或不可用语义，不渲染成本表格，不显示最终空态或 0 条 summary，不允许打开导出中心。
  - Playwright mock 新增 `costStatisticsReadModelStatus` 选项，专门构造非 fresh 空 payload；测试断言无 console error、无 pageerror，且没有非 abort 请求失败。
  - 不改变成本归因 service、API shape、SQL read model、scope policy 或 worker 入队逻辑；真实 worker drain 仍由 `infra-smoke` / staging gate 验证。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录和全局 Spec-first inventory / testing closure state。
- 测试覆盖：
  - 更新 `web/src/pages/CostStatisticsPage.tsx`。
  - 更新 `web/src/test/CostStatisticsPage.test.tsx::hides read model refresh details without treating empty accepted payload as final empty data`。
  - 更新 `web/e2e/fixtures/apiMocks.ts`。
  - 新增 `web/e2e/cost-statistics-flow.spec.ts` 中 `refreshing` / `stale` / `failed` Browser 场景。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker；真实 enqueue-to-fresh、真实大数据下载和真实文件打开仍需 staging/production smoke。
- 后续事项：`COST-E2E-009` 已由后续 download event 覆盖；继续补真实基础设施 worker drain、更多导入变体或大数据视觉稳定性。

## 2026-06-18 - 成本统计 explorer payload contract 修复

- 目标：修复 App Health 显示 `成本统计 已同步`，但进入成本统计页仍出现“成本统计数据加载失败”的问题，避免旧 read model/cache payload 被当作当前 explorer API 的 fresh 数据。
- 影响范围：`CostStatisticsQueryService.get_explorer_from_sql_read_model(...)`、`ReadModelQueryGateway`、成本统计 SQL runtime 测试、read-models 共享测试与文档。
- 关键决策：
  - 成本统计 explorer 的 fresh payload 必须包含 `summary`、`time_rows`、`project_rows`、`expense_type_rows`；只看 schema/source/readiness 不足以证明页面 mapper 可消费。
  - 业务 shape 校验放在后端 read boundary：旧 Redis payload 校验失败时 miss 并改读 SQL view；旧 SQL payload 校验失败时返回 canonical empty refreshing payload，入队 `api_payload_shape_invalid`，不写 fresh cache。
  - 前端不新增旧 shape 兼容分支，避免让页面继续承接过期 API contract。
- 文档影响：更新成本统计状态机、测试矩阵、实施记录，并同步 read-models 状态机/测试矩阵/实施记录。
- 测试覆盖：
  - 新增 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues`。
  - 新增 `tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache`。
  - 更新 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_reads_sql_and_populates_short_redis_cache` 的 valid explorer fixture，锁定当前 shape。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实 OA iframe、真实生产 Redis/PostgreSQL 或 worker drain；发布后若生产已有旧缓存，需等待 TTL 或按运维流程清理，但新后端不再把 invalid cache 当 fresh 返回。
- 后续事项：后续 explorer API shape 改动必须同步 payload validator、schema/source version、SQL projection 和前端 API mapper 测试。

## 2026-06-18 - 成本统计 explorer 认证错误呈现修复

- 目标：修复进入成本统计页时后端返回 `401 invalid_oa_session` 却被页面统一显示为“成本统计数据加载失败”的问题，避免把 OA 登录态缺失误判为成本统计/read model 故障。
- 影响范围：`web/src/pages/CostStatisticsPage.tsx`、`web/src/test/CostStatisticsPage.test.tsx`、成本统计测试矩阵。
- 关键决策：
  - 保持后端 API、read model、worker、scope contract 和成本归因架构不变；直接请求应用接口已确认无 OA 登录态时后端返回结构化 `401` 和业务 `message`。
  - 页面加载 explorer 失败时仅对 `401`、`403` 和 `invalid_oa_session` 暴露后端业务文案；普通 500/网络异常继续使用泛化成本统计失败文案，避免暴露底层异常。
  - `202 refreshing`、empty accepted payload、SQL read model miss/stale 仍走既有刷新状态，不当作本次错误。
- 文档影响：更新本实施记录和 `tests.md`；产品规格、API 契约、状态机、read model/worker 长期事实源不变。
- 测试覆盖：
  - 新增 `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading`。
  - 保留既有泛化 500 加载失败测试，避免所有后端错误都直接透出。
- 七类测试覆盖：
  - Business core unit tests：不适用；未改变成本归因、状态流转、金额计算或项目范围。
  - Service-layer tests：不适用；未改 service/repository/read model/worker。
  - API contract tests：后端契约未改；用直接应用请求确认 `401 invalid_oa_session` shape。
  - Read model/cache/background job tests：不适用；未改变 read model freshness、queue、cache 或 worker。
  - Frontend component and interaction tests：适用，新增页面级认证错误呈现回归。
  - End-to-end business-flow integration tests：不适用；未跨模块改变业务流。
  - Existing feature regression tests：适用，保留成本统计 500 泛化失败、refreshing empty payload 和既有交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`；直接应用请求 `/api/cost-statistics/explorer?month=2026-03&project_scope=active`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_sql_runtime -v`。
- 未测风险：未跑真实 OA iframe 登录链路、真实浏览器手工进入、生产 PostgreSQL scope cleanup 或 RabbitMQ/Redis worker drain；本轮修复只覆盖错误呈现层。

## 2026-06-18 - Workbench 成本关系 Browser fan-out

- 目标：补齐 Spec-first Browser E2E 中的成本统计下游 fan-out，防止关联台 open candidate 被误算进成本，或 confirmed 成本关系写入后成本页没有重新读取并展示。
- 影响范围：`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、成本统计 Spec-first E2E 文档、测试矩阵、状态机和全局测试闭环文档。
- 关键决策：
  - 使用 opt-in deterministic mock `costStatisticsRelationFanout` 构造成本关系链路；默认成本统计 mock 数据保持不变。
  - Browser 规格先断言候选阶段看不到 `智能工厂项目` 和 `智能工厂设备尾款`，再通过关联台确认关系，返回成本页验证项目金额 `58,000.00`、对应流水和详情 modal。
  - 本轮不改成本归因 service、SQL projection 或 read model worker；candidate 排除和 confirmed inclusion 的后端规则继续由既有 service/SQL tests 保护。
- 文档影响：新增 `e2e-spec.md` / `e2e-coverage.md`，更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing*.md` 和 workbench-relations 覆盖矩阵。
- 测试覆盖：
  - `web/e2e/cost-statistics-relation-fanout.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改业务规则；candidate 排除由既有成本 service/SQL 测试继续保护。
  - Service-layer tests：本轮未改 service/read model 写边界；真实 worker drain 仍为 staging/production 风险。
  - API contract tests：适用；e2e 断言成本 explorer/detail 在 Workbench confirm 后重新读取并展示 confirmed 成本关系。
  - Read model/cache/background job tests：本轮未改 worker/readiness；真实 enqueue-to-fresh 仍需 staging smoke。
  - Frontend component and interaction tests：适用并新增真实 Chromium 跨页确认、返回成本页、项目/费用/流水/详情展示。
  - End-to-end business-flow integration tests：适用并新增 Workbench confirm -> 成本统计重新读取 -> confirmed 成本关系出现的浏览器闭环。
  - Existing feature regression tests：适用，防止 candidate/linked relation 成本语义和既有成本页下钻断链。
- 未测风险：真实 RabbitMQ/Redis/cost-statistics worker drain、生产旧 scope cleanup、真实大数据下载/视觉性能、settings/project scope 和其他导入变体到成本页的更多 fan-out 仍需后续轮次或 staging smoke。

## 2026-06-17 - Browser e2e 项目下钻与导出错误反馈

- 目标：补齐成本统计真实浏览器主路径，防止后续页面维护时破坏 project scope、项目/费用类型/流水详情下钻、导出 preview 和结构化导出错误反馈。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、成本统计测试矩阵与全局测试闭环文档。
- 关键决策：
  - 使用 deterministic API mocks 构造 active/all 项目范围差异，浏览器必须请求 `project_scope=all` 后才能看到已完成项目。
  - e2e 断言真实 Chromium 中的可见 UI、transaction detail query、export-preview query 和 export row-limit JSON 错误展示；不新增后端业务代码或 read model 逻辑。
  - 导出接口在 e2e 中返回 `cost_statistics_export_row_limit_exceeded`，用于保护前端对结构化错误的真实浏览器闭环。
- 文档影响：更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing*.md` 和 testing closure dependency/state。
- 测试覆盖：
  - `web/e2e/cost-statistics-flow.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改成本归因规则，由既有 service tests 保护。
  - Service-layer tests：本轮未改 service/read model 写边界，由既有 cost read model/runtime tests 保护。
  - API contract tests：适用，e2e 额外断言 explorer project scope、transaction detail、export-preview 和 export row-limit response。
  - Read model/cache/background job tests：本轮未改 worker/readiness；真实 worker drain 仍属未测风险。
  - Frontend component and interaction tests：适用并新增真实 Chromium tab、scope、三段下钻、modal、preview 和导出错误反馈。
  - End-to-end business-flow integration tests：适用并新增 explorer -> project scope -> drilldown -> export preview/error browser flow。
  - Existing feature regression tests：适用并防止 project scope、detail modal 和 export center 在真实浏览器中断链。
- 未测风险：真实 PostgreSQL scope cleanup `--apply`、真实 RabbitMQ/Redis/cost-statistics worker drain、真实文件下载/打开、大数据下载耗时和视觉性能仍需 staging/manual smoke。

## 2026-06-17 - 成本统计项目费用类型下钻重复流水行修复

- 目标：修复成本统计项目视图中选中项目后再切换费用类型，真实数据含同一流水多条成本行时页面卡死/白屏的问题。
- 影响范围：`CostStatisticsPage` 的成本流水表行身份、`CostStatisticsTable` 行 key contract、成本统计前端 mock 和页面交互测试。
- 关键决策：`transaction_id` 是银行流水身份，不是成本统计行身份；前端表格行 key 改为由流水 id、交易时间、项目、费用类型、费用内容、金额和行序号组成的渲染键，避免同一流水拆成多条成本行时 HeroUI Table collection 冲突或丢行。不改变 API shape，后端 `row_key` 是否外露另行评估。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug/前端交互覆盖；产品、API、read model 和 worker 长期事实源不变。
- 测试覆盖：新增 `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable`，mock API 可返回重复 `transaction_id` 的成本行。
- 验证命令：`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx -t "project view keeps split cost rows" --reporter=verbose`；`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx --reporter=verbose`；`cd web && npm run build`。
- 未测风险：本地没有连接真实生产后端复现用户截图中的 123 条明细；真实生产数据量、浏览器白屏堆栈和后端是否应外露 canonical cost row key 仍需 staging/production smoke 进一步确认。
- 后续事项：如后端 API 后续补充 `row_key`，前端可优先使用后端 canonical cost row identity，保留当前合成键作为兼容 fallback。

## 2026-06-16 - 成本统计导出错误反馈闭环

- 目标：确保成本统计同步导出被后端行数上限拒绝时，前端下载路径解析结构化错误并在导出中心展示具体原因。
- 影响范围：`web/src/features/cost-statistics/api.ts`、`web/src/pages/CostStatisticsPage.tsx`、成本统计前端 API/page 测试和 P2/P3 闭环台账。
- 关键决策：非 2xx 下载响应先读取 `message` / nested `error.message` / `error`，HTML fallback 仍按代理配置错误处理；页面导出和预览 catch 保留后端消息，不再统一覆盖成泛化失败。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；长期产品/API 文档不变。
- 测试覆盖：新增 `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`；新增 `web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center`。
- 验证命令：`npm run test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx src/test/TurnoverLedgerApi.test.ts src/test/PendingInvoicesApi.test.ts`。
- 未测风险：真实浏览器下载、代理错误页面、生产网络中断和大文件打开仍需 staging/manual smoke。
- 后续事项：如业务需要超过 20,000 行导出，应改异步导出任务并补任务进度/下载链接闭环。

## 2026-06-16 - P2/P3 成本统计同步导出上限

- 目标：收敛成本统计 time/project/expense_type 大数据 export-preview/export 的同步生成风险，避免大匹配集继续构造预览 rows 或 XLSX。
- 影响范围：`CostStatisticsService`、`CostStatisticsApiRoutes`、成本统计 service/API 测试、模块测试矩阵和 P2/P3 闭环台账。
- 关键决策：导出上限为 20,000 行；超过上限返回 `cost_statistics_export_row_limit_exceeded`，details 包含 `view`、`total` 和 `limit`。transaction 单笔详情不使用该上限。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期文档未扩展，因为这是性能保护边界。
- 测试覆盖：新增 `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_export_preview_and_download_reject_large_time_export_before_workbook_generation`；新增 `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service.CostStatisticsServiceTests.test_export_preview_and_download_reject_large_time_export_before_workbook_generation tests.test_cost_statistics_api.CostStatisticsApiTests.test_cost_statistics_export_limit_returns_structured_error -v`。
- 未测风险：真实 PostgreSQL EXPLAIN、生产数据分布、浏览器下载/打开文件和视觉性能仍需 staging/manual smoke；本地只证明超大匹配集不会继续同步生成预览或 XLSX。
- 后续事项：继续执行 authenticated HTTP/SSE/read model final gate；若真实用户需要超过 20,000 行导出，应另设异步导出任务而不是放宽同步路径。

## 2026-06-16 - P2/P3 首屏 SLO 与父 scope 有界聚合证据

- 目标：复核成本统计在 P2/P3 一秒级推进中的真实性能护栏，避免把该页误按普通 rows 分页列表处理。
- 影响范围：`tests/test_http_slo_probe.py`、成本统计测试矩阵和 P2/P3 闭环台账；未改变成本统计业务代码、API contract 或页面行为。
- 关键决策：成本统计页面首屏事实源是 explorer/summary 聚合 read model，不是可追加 `page_size` 的 rows 列表；本地证据应锁定认证态 SLO 探针覆盖 `/api/cost-statistics/explorer` 与 `/api/cost-statistics`，并复用 SQL runtime 中父 scope 从已物化月份 shard 聚合、不读 Workbench 全量 payload 的测试。
- 文档影响：更新 `tests.md` 和本实施记录；长期产品/API 文档不变。
- 测试覆盖：更新 `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`，显式断言成本统计 explorer/summary 默认探针；沿用 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v`。
- 未测风险：未连接真实 PostgreSQL 执行 EXPLAIN、pg_stat 或生产旧 scope `--apply`；真实登录态 p95/p99、worker drain、导出耗时和浏览器下载仍需 staging/生产 smoke。
- 后续事项：生产 scope contract repair 获批后，复跑认证态 HTTP SLO 和 cost-statistics App Status。

## 2026-06-16 - 外部往来 Postgres 写路径补齐成本统计 scope contract

- 目标：补齐 `turnover_relation_changed` 下游对成本统计的事务内入队 contract，避免再次产生裸月份/裸 `all` 的 `cost_statistics.read_model.refresh`。
- 影响范围：外部往来确认/撤回后的成本统计 dirty scope、outbox、readiness，以及生产 scope contract repair。
- 关键决策：成本统计 canonical scope 仍只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；事务入队路径在写入 durable queue 前归一化，不改变 worker projection contract。
- 文档影响：更新成本统计、read-models、turnover-ledger 和 P2/P3 closure ledger。
- 测试覆盖：新增 turnover Postgres dirty outbox writer 回归；保留 `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` 的成本统计 scope policy/repair 覆盖。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产现存 legacy rows 只完成 dry-run 取证，未执行 `--apply`；一秒级 worker drain 需在发布和 cleanup 后复测。
- 后续事项：批准后执行 production scope contract repair，再复查 cost-statistics App Status 和 write-operation SLO。

## 2026-06-13 - 成本税务发票输入收敛到 canonical invoice facts

- 目标：删除成本税务 SQL projection 直接读取 `app.oa_attachment_invoice_cache` 拼进项计划项的旁路，跟随统一 Invoice repository 事实源。
- 影响范围：`CostTaxSqlProjectionBuilder._build_tax_payload`、税金抵扣服务共享发票读取链路、Workbench OA 附件发票 promotion。
- 关键决策：`app.oa_attachment_invoice_cache` 继续作为 OA 附件 parser cache 和运维审计对象，但不作为成本税务 read model 的正式发票输入。OA 附件正式发票进入 `app.invoices` 后由 `_invoice_items(..., output=False)` 统一读取。
- 文档影响：更新本模块记录，并同步 Workbench/Tax Offset 记录。
- 测试覆盖：通过 `tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py` 和 Workbench canonical projection tests 间接覆盖；本模块未新增重复成本统计专测。
- 验证命令：见本轮最终执行记录。
- 未测风险：未跑完整成本统计 API/SQL 回归；若后续修改成本归因或 projection scope，应按本模块测试矩阵补跑最小闭环。

## 2026-06-11 - 成本统计测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `cost-statistics` 模块轮次，确认新功能改动不会绕过成本归因、read model freshness、App Status 或页面交互回归保护。
- 影响范围：`docs/modules/cost-statistics/tests.md`、`docs/modules/cost-statistics/state-machine.md`、`docs/modules/cost-statistics/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖成本归因规则、项目范围、API 契约、导出 shape、SQL read model、`active/all` parent 与 month shard readiness、scope gateway、worker/App Status 语义和前端 loading/empty/error/refreshing/stale 交互；本轮不新增重复测试。
- 文档影响：补齐七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py`、`tests/test_project_costing_api.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`。
- 未测风险：未在真实生产数据库执行 `scripts/check-read-model-scope-contracts.py --apply`；未跑真实 RabbitMQ/Redis/cost-statistics worker drain；未做大数据量导出和真实浏览器下载 smoke。
- 后续事项：下一轮处理 `tax-offset`，重点审计税金认证导入、ETC、invoice lifecycle 与成本税务共享链路。

## 2026-06-10 - 成本统计生产旧 scope 检查与清理

- 目标：清理历史 `2026-03`、`2026-04`、裸 `all` 或未知 project scope 造成的成本统计 App Status readiness、dirty scope 和 dead-letter/outbox 污染。
- 影响范围：`read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` 中 `cost_statistics` 相关旧状态。
- 关键决策：只删除当前 scope policy registry 不认为是 canonical 的成本统计状态；legacy scope 会通过 gateway 补投 `active/all` replacement scope，invalid scope 不猜测含义。
- 文档影响：更新成本统计测试矩阵和 runtime worker 运维 runbook。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖检查、删除和 replacement enqueue 去重。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`。
- 后续事项：无。

## 2026-06-10 - 成本统计 read model refresh scope contract

- 目标：阻止裸月份/裸 `all` 作为 `cost_statistics.read_model.refresh` scope 进入 durable queue，避免 SQL projection 报 `scope_key must use project_scope:month` 并污染 App Status readiness。
- 影响范围：成本统计 read model refresh 入队 contract、worker lifecycle 触发链路。
- 关键决策：合法成本统计 scope 统一为 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。旧裸月份/裸 `all` 只允许在统一 gateway 中归一化；未知 project scope 直接拒绝。
- 文档影响：更新成本统计、read-models、runtime-workers 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 覆盖成本统计 policy，`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖 worker lifecycle。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`。
- 未测风险：阶段 1 未执行真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口补齐。

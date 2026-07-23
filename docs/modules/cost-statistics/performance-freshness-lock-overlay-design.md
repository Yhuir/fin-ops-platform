# 成本统计高性能、鲜度与轻量锁定遮罩设计

> 历史设计说明（2026-07-22）：本文保留成本模块此前的演进记录。其“relation 写后事务内投递成本增量”“Workbench 发布后再投递成本收敛”等主动 fan-out 段落已被 Phase 27 取代：普通 relation/rule write 只提交 canonical fact/version，成本页访问或重新激活时由 dependency-bound fresh gate 比较 exact scope，mismatch 才经 gateway 去重入队；显式维护命令仍按运维合同执行。当前边界以 `boundary-io.md` 与 `docs/architecture/module-boundaries/read-model-contracts.md` 为准。
>
> 状态：历史设计；Phase 27 本地迁移完成，`PRODUCTION_VERIFICATION_PENDING`
> 日期：2026-07-18
> 范围：`/cost-statistics` 页面、`cost_statistics` read model / worker / query / Audit 链路，以及历史发布后 fan-out 方案
> 本文是唯一主设计与实施校准文档；已落地内容和剩余门禁必须在此区分，不以设计项冒充完成项。

## 1. 结论

本方案合理，且在再次审阅后不属于过度设计。

目标方案只保留解决当前生产问题不可缺少的能力：

1. 请求链路从“加载整份 explorer JSON 并在前端重算”改成“单次持久化鲜度门禁 + 当前视图的服务端分页查询”。
2. `cost_statistics` worker 使用现有 durable queue 的 `source_version` 做原子条件发布和条件完成，禁止旧任务覆盖新事实。
3. 页面在数据未确认 fresh 时进入成本页局部锁定状态；用户能看到旧页面轮廓，但不能把旧值当作可操作的新数据。
4. Audit 从通用大文件中拆回成本统计边界，以少量集合 SQL 在同一 `REPEATABLE READ READ ONLY` snapshot 内完成。
5. 旧 live service、本地 read model、全量 payload、无版本缓存、未使用 API client、cost/tax 混合 owner、warmup bridge、旧 summary/project HTTP contract 与 full-view loader 均已删除，不保留 fallback。
6. relation 写后鲜度使用同一 durable queue 的两阶段 I/O：事务内按 case 投递 Cost 月份精准增量以满足低延迟，Workbench 成功发布后投递全月收敛；不新增表、worker、endpoint 或兼容链。parent 只读 shard metadata 并以 SQL aggregate 生成 summary，不再加载全部月份行构造大型 Python DTO。

遮罩采用 Impeccable 的 `Ledger Calm` 产品设计语言：约 80% 透明、无弹窗、无实色卡片、无大阴影、无背景模糊。它是页面内的轻量交互锁，不是 modal。

当前闭环状态：

| 切片 | 本地状态 | 已关闭风险 | 尚未声明 |
| --- | --- | --- | --- |
| 05-02 | 完成 | worker `source_version` 条件发布/完成，旧事件不能覆盖新 dirty | 生产竞态/SLO |
| 05-03 | 完成 | PostgreSQL metadata gate 在 Redis/full rows 之前 | 请求期多 owner version 读取删除 |
| 05-04 | 完成 | 两类结构化 rows、parent array quarantine、详情 identity 点查、旧 projection Redis writer 删除 | view-specific cursor、流式导出、Audit、遮罩 |
| 05-05 | 完成 | 删除前端 TTL payload cache、首屏 `active:all` 预取和两个零调用旧 client；导出参考数据改为 fresh 后按需读取 | explorer 仍为全量 DTO，尚未达到 cursor/payload/SLO 终态 |
| 05-06 | 完成 | 原 endpoint 原子切换 view-specific cursor；每页最多 100 rows；SQL summary/facets；ETag/versioned cache；删除前端 full DTO、全量聚合与明细本地 fallback | 生产 EXPLAIN/SLO、请求期 expected-source provider、流式导出、Audit、遮罩、剩余内部 full loader |
| 05-07 | 完成 | 成本页唯一 effective lock；native `inert`；20% alpha 非 dialog 遮罩；精确 App Status scope；focus/BFCache/portal/drawer 闭环；删除旧 non-fresh state-panel | 生产 SSE/浏览器 SLO；Audit、请求期 expected-source provider、流式导出、剩余内部 legacy |
| 05-08 | 完成 | 成本 Audit 合同/SQL/依赖证明迁入唯一 `cost_statistics_page_audit.py` owner；统一 HTTP/CLI/System Audit 直接分派；共享 repository 的全部成本分支删除；固定本地查询预算 35 | Audit SQL 仍需在专属边界内合并/量测至 `<=5s`；生产 mismatch/连续 pass 尚未证明 |
| 05-09 | 完成 | summary/dirty/outbox 合为一次 SQL；复用 Workbench collector 的 relation equality；跳过成本不消费的 generation summary；active-relation 查询上限由真实旧基线 36 降至 32 | 仍未达到最多四组 SQL；无真实 PostgreSQL plan/生产 `<=5s`、mismatch/连续 pass 证据 |
| 05-10 | 完成 | row/scope、月度上游与 parent shard 三类 source-version proof 合为一次 SQL；每类独立 limit/code/details 不变；active-relation 上限由 32 降至 30 | 仍未达到最多四组 SQL；无真实 PostgreSQL plan/生产 `<=5s`、mismatch/连续 pass 证据 |
| 05-11 | 完成 | 有效成本业务规则迁入唯一 SQL projection owner；删除 legacy `CostStatisticsService` module/class/test/import；导出 limit/error 归 query owner | 仍存在 runtime/local read-model/warmup legacy；生产回归未执行 |
| 05-12 | 完成 | page/full/month/detail 的 settings、Workbench、Bank Detail 读时 I/O 合为单次 dependency-bound gate；projection/query 共用纯 source-version helper；删除 Application/runtime/query 旧 providers 与 Redis delete | 无真实 PostgreSQL EXPLAIN、连接获取与页面 p95/p99；warmup/local read-model、流式导出、Audit 剩余 SQL 仍待独立切片 |
| 05-13 | 完成 | 删除 `CostStatisticsReadModelService` module/class/test、Application startup snapshot/field/local persist callback 与 runtime local clear/invalidate/persist；projection 直接发布单 scope write model；失效只认 durable enqueue | 历史 warmup job type/delegates仍需 production active-job=0 证据；正式 repository旧 load/save调用面、流式导出与 Audit剩余 SQL待独立切片 |
| 05-14 | 完成 | 删除 repository/state-store/protocol/manifest 的成本全量 load、无 source-version save、启动 snapshot key 与 broad save branch；正式写入只剩 CAS publish，scoped read/query 保持 | 历史 warmup job type/delegates仍需 production active-job=0 证据；流式导出、Audit剩余 SQL与生产 SLO待独立切片 |
| 05-15 | 完成 | preview 最多 8 行；bulk export 每批最多 1,000 行并写 write-only XLSX；导出结束复核发布证明；删除 full-payload bulk export旧路径 | 真实 PostgreSQL/代理/内存与导出 SLO；历史 warmup 与 Audit剩余 SQL |
| 05-16 | 完成 | 五类业务值/summary/account proof由 5 次往返合为 1 次集合查询；独立 limit/code/details不变；active-relation固定预算由30降至26 | exact-set剩余查询、真实 PostgreSQL plan/生产 `<=5s`、mismatch与连续 pass |
| 05-17 | 完成 | 删除成本 Audit 最后 3 处 parent JSON bank-flow array 读取；canonical set、字段和 summary proof 只读结构化 bank-flow rows，parent 按 month rows 逻辑 rollup；0001–0107 本地 PostgreSQL clean cost Audit 通过 | exact-set 剩余查询、真实数据 plan/生产 `<=5s`、mismatch 与连续 pass |
| 05-18 | 完成 | scope count、missing scope、duplicate identity、canonical expected-set 四个入口合为 1 次集合查询；四分支独立 bounded；删除旧四 helper 与无调用 proof helper；active-relation预算由26降至23 | 真实数据 plan/生产 `<=5s`、mismatch与连续 pass |
| 05-19 | 完成 | worker unchanged 判定改为 parent `scope_key/entry_count/source_versions` 单次点查；删除 projection/full-view 调用与旧 fixture，不读 payload/明细 rows/dependency gate | 真实 worker/写后鲜度 SLO |
| 05-20 | 完成 | 成本与税金 SQL projection 拆为两个明确 owner；删除 `cost_tax_sql_projection.py`、全部 current import与混合 helper，不留 re-export/shim/fallback | 生产 worker实跑；warmup/旧HTTP证据已由后续统一发布准备收口关闭 |
| 统一发布准备收口 | 完成 | owner 明确认定无旧 HTTP 外部 consumer且从未公开承诺；生产只读 active/attention warmup job 均为0；删除 warmup、旧HTTP/full-view及所有 registry/mock/compat I/O | 只剩统一部署窗口的生产执行与性能/Audit验证 |
| relation 写后精准增量 | 本地实现，生产验证待执行 | case-keyed delta、精确 CAS、Workbench convergence、parent metadata/SQL aggregate、旧 parent full-row loader 删除 | 真实 confirm/withdraw p99 `<=3s`、写后 Audit 与三页面隔离 |
| 整体任务 | `PRODUCTION_VERIFICATION_PENDING` | 原首屏/Audit/旧链删除已发布闭环；本轮 relation 低延迟实现待验证 | 标准部署后的真实写后性能、Audit 与隔离证据 |

## 2. 已确认的验收门槛

以下数值是本次设计的发布门槛，不是观察目标：

| 场景 | p95 | p99 | 说明 |
| --- | ---: | ---: | --- |
| 冷启动到首屏数据可用 | `<= 700ms` | `<= 1s` | 浏览器真实 data-ready，不只量 API |
| 暖访问或返回页面 | `<= 250ms` | `<= 400ms` | 必须先通过 durable freshness gate |
| 切换视图、范围或筛选后的首屏 | `<= 300ms` | `<= 500ms` | 只返回当前视图第一页 |
| `active:all` 首屏 | `<= 500ms` | — | 禁止传输整份全期间 payload |
| Audit | `<= 5s` | — | integrity=`pass`、freshness=`fresh`、queue=`drained` |
| 写操作到相关成本 scope fresh | — | `<= 3s` | 沿用 operation barrier / worker SLO |

验收必须在生产等价数据量和正常并发下进行，不能依赖空闲数据库或预先手工清空队列。

## 3. 当前证据与根因

### 3.1 生产只读量测

| 证据 | 当前表现 | 结论 |
| --- | --- | --- |
| 页面 shell | 约 `95–107ms` | HTML / 静态壳不是主瓶颈 |
| 月份 explorer | 样本约 `210–282ms`；约 `58,989B` decoded / `5,364B` gzip | 单月尚可，但请求仍做了过多门禁查询和完整映射 |
| `active:all` | 样本约 `765,203B` decoded / `55,284B` transfer，浏览器请求约 `1.769s` | 全量 JSON 是明确热点；05-05 已从首屏移除无条件预取，但 project/all 与按需导出仍会读取该大 payload |
| 浏览器冷 data-ready | 约 `1.189–1.337s` | 未达到已确认 SLO |
| 浏览器主线程 | `50–91ms` long task，约 `2,065` DOM nodes | 全量 mapping、前端聚合和一次渲染过重 |
| explorer 生产窗口 | p50 `234.3ms`，p95 `3936.76ms` | 长尾严重 |
| 数据库连接获取 | p95 `3184.878ms` | 请求内多次数据库访问放大连接池排队 |
| explorer SQL | p95 `681.712ms`，每次约 `8–13` 个数据库查询 | 门禁与 payload 重建未收敛成短查询 |
| Audit | 首次约 `34.64s`；队列排空后仍约 `12.276s` | Audit 自身过重，且不是单纯队列积压 |
| Audit 正确性 | 队列 drained 后仍有 `cost_statistics_upstream_source_versions_mismatch`，样本 scope=`active:2026-02` | worker 收敛/版本完成存在缺口，不能通过隐藏 Audit 解决 |

### 3.2 前端根因（设计时基线与实施校准）

- 05-05 前页面首屏加载当前 scope 的同时，无条件加载 `active:all`，只为导出中心准备项目和费用类型选项；现已删除，time/month 首屏只请求当前 scope，项目/费用类型导出需要时才经后端 fresh gate 按需读取 `active:all`。
- 05-05 前 `api.ts` 的 5 分钟内存 `Map` 会先显示缓存再重新发请求，不能证明数据 fresh；该 Map、get/clear API 与缓存初始化已完整删除，页面重进必须重新经过后端 freshness boundary。
- 05-06 前 explorer 响应包含 `time_rows`、`bank_flow_time_rows`、项目和费用类型聚合，页面再次执行 map/filter/group；现已由同一路径的 view-specific page DTO 取代，生产页面只映射服务端 summary/facets/rows。
- `DEFAULT_MONTH` 仍是静态 `2026-03`。它是共享常量，不能为了成本统计修改其他页面；成本页必须自行解析当前业务月或后端默认 scope。
- 页面只监听当前浏览器内的 finance domain event。其他用户、其他设备或后台同步改变事实时，已打开页面不会立即知道。
- 流水详情在 05-04 前会读取 `active:all` 再线性扫描交易；该项已改为 fresh gate 后 identity 点查。
- 页面已经有独立的 Audit icon，Audit 不在首屏关键路径；应保持这一点。

### 3.3 后端读取根因（设计时基线及实施校准）

- 05-12 前 query service 在读 Redis 前通过 Application/runtime provider 串行访问 settings、Workbench 和 Bank Detail，并再次读取 settings 生成 tag selection；05-12 已删除该多 owner 链路，改为单次 dependency-bound gate statement 与纯内存映射。
- 05-03 前 full view 会再次读取 dirty scope；现已由独立 metadata-only gate 负责，full view 不再查询 dirty table。
- 05-04 前 `bank_flow_time_rows` 保存在 parent JSON；现已迁移到 `cost_statistics_bank_flow_rows`，parent snapshot 同时剥离两类 arrays。05-17 又删除成本 Audit 中最后 3 处读取该旧数组的残留；页面、query 和 Audit 现在均无 parent JSON row fallback。
- `active:all` 以完整 JSON payload 作为读模型输出，不适合首屏、详情或导出查询。
- Redis 命中仍必须发生一次前置数据库 gate I/O，这是 stale-as-fresh 防线；05-12 已把所有当前依赖证明合入该一次 statement，本地不能替代生产 EXPLAIN 与连接获取量测。
- 当前 DB acquisition p95 很高，但直接新增全局连接池或修改共享池会影响其他页面。应先消除本链路的多查询和长占用，再用 SLO 决定是否需要单独容量评审。

### 3.4 一致性根因

- `CostStatisticsReadModelRefreshService` 完成 dirty scope 时没有传入 event `source_version`。
- worker 没有在重建前和发布后验证当前 dirty scope 版本；旧 event 可以在新事实到达后错误完成 scope。
- Bank Detail 发布 fresh 后没有完整、显式地向对应成本 scope fan-out；Workbench 已有相应方向，不能假设所有依赖都一样。
- 当前 Bank Detail projection 内部已经能做一致性快照；无需新建跨模块全局 snapshot 框架。成本 worker 只需记录依赖版本并在发布前后复核。
- 当前页面 event 不是事实源；真正的事实源仍是 PostgreSQL 的 `job.outbox_events` 与 `job.read_model_dirty_scopes`。

### 3.5 Audit 根因与实施校准

- 05-08 前成本 Audit 混在通用 `page_business_audit.py` 中；05-08 已把合同、成本 SQL、上游证明和 response owner 完整迁入 `cost_statistics_page_audit.py`，共享 repository 的成本 runtime/text 分支为零。
- 生产窗口中 Audit p95 约 `34.5s`、SQL p95 约 `33.95s`、查询数 p95 约 `215`，与成本页 `<=5s` 目标不相容。
- 05-08 行为等价迁移后的空数据预算是 `1 fetch_one + 34 fetch_all = 35`，但真实 active relation 会触发额外 group-row query，实际旧上限为 36。05-09 把 summary/dirty/outbox 合为一次 I/O、删除第二次 relation equality，并跳过成本不消费的 Workbench generation summary；05-10 把成本 owner 内三个 source-version proof 往返合为一次；05-16 又把五类业务值/summary/account proof 从五次往返合为一次。每个 proof branch 仍独立 bounded，active-relation 上限依次降为 32、30、26。05-17 不再压 statement 数量，而是先纠正三段与 v9 存储合同冲突的旧 JSON 读取，避免空投影误报和数组解析；预算仍为 26。05-18 把剩余四个 exact-set 类入口合为一个 statement，每分支在 union 前独立限流，删除旧 helper 后固定预算降为 23；成本 owner 自有 SQL 已达到 queue/readiness、source-version、exact-set、business-values 四组设计目标。该数字仍只防回退，不能冒充生产性能达标；Workbench/Bank Detail 完整依赖证明不得为追求更低数字而删除。
- 当前 Audit 已使用单个 `REPEATABLE READ READ ONLY` snapshot；这部分正确，应保留而不是再增加第二套 snapshot 机制。
- 队列 drained 之后仍有上游版本 mismatch，说明 Audit 暴露的是实际收敛错误，不是误报 UI。

## 4. 目标边界与 I/O

```mermaid
flowchart LR
    W["Workbench / Bank Detail / Settings 发布完成"] --> Q["现有 ReadModelRefreshGateway"]
    Q --> D["PostgreSQL durable dirty scope + outbox\n含 source_version"]
    D --> CW["cost_statistics worker"]
    CW --> RM["成本专属 metadata + 结构化 rows"]
    RM --> G["单次 PostgreSQL freshness gate"]
    G --> C["仅缓存已通过 gate 的当前视图 payload"]
    C --> API["view-specific cursor API"]
    API --> UI["成本统计页面"]
    H["现有 App Health SSE\n5s fallback"] --> UI
    UI --> L["轻量锁定遮罩 / fresh 后解锁"]
    RM --> A["cost_statistics Audit repository\n单 snapshot 集合校验"]
```

### 4.1 模块职责

| 模块 | 输入 | 输出 | 禁止事项 |
| --- | --- | --- | --- |
| Cost refresh producer | 已完成的上游发布、settings 写事务 | 规范化、去重后的成本 scope refresh | 不直接写 cost 表，不自行拼 SQL queue 事件 |
| Cost worker | `cost_statistics.read_model.refresh` + `source_version` | 原子发布的成本 metadata / rows | 不依赖 HTTP、cookie、`Application` 或 UI DTO |
| Cost repository | scope、view、filter、cursor | gate、summary、group、row、detail 查询 | 不返回整份全期间 JSON，不含业务 HTTP 映射 |
| Cost query service | API query DTO、repository、Redis | 200 fresh / 202 refreshing / 明确错误 | 不扫描 canonical live tables，不在 miss 时同步 rebuild |
| Cost Audit repository | caller-owned audit snapshot | exact-set、value、version、queue issues | 不写数据，不缓存绿色结论，不逐行查询 |
| Cost page | API DTO、App Status、local request state | 视图渲染、轻量 lock、用户操作 | 不重算业务事实，不把本地 cache 当 freshness 证明 |

### 4.2 隔离承诺

- 只新增或修改 `cost_statistics` 自有表、repository、query、worker、Audit、前端组件和样式。
- 对 Workbench 和 Bank Detail 的唯一行为变化是：它们成功发布 fresh 后，通过现有 gateway 增加成本 scope refresh 事件；不改变其 payload、API、表或 read model。
- 不改变其他页面的 read model、Redis key、worker、App Status 语义或 `DEFAULT_MONTH`。
- 不修改共享数据库连接池参数，不为本方案预先增加专用 SSE、WebSocket 或消息总线。
- 05-20 已删除 `cost_tax_sql_projection.py`：成本 builder 只属于 `cost_statistics_sql_projection.py`，税金 builder 只属于 `tax_offset_sql_projection.py`；税金业务行为和输出零变化。
- 遮罩是成本页局部组件和 `cost-*` 样式，不修改全局 `StatePanel`、App Shell 或其他页面。

## 5. 高性能读取设计

### 5.1 数据布局

保留现有 `read_model.cost_statistics_rows`，它只承载 OA 正式配对后的成本行。

新增且只新增一张成本专属明细表：

- `read_model.cost_statistics_bank_flow_rows`：承载按时间、按标签所需的完整银行收支行。

`read_model.cost_statistics_read_models` 只保存：

- scope metadata；
- summary / direction summary；
- schema version；
- 当前 cost queue `source_version`；
- dependency source versions；
- parent scope 的 exact `source_shards` manifest；
- generated time、row counts 和 cache status。

禁止继续在 parent payload 保存 `time_rows` 或 `bank_flow_time_rows` 大数组。`active:all` / `all:all` 仍是 readiness parent，但查询行时直接从月份 rows 按 `project_scope` 读取，不复制一份全期间行。

索引只按真实查询形状增加：

- scope / project_scope + trade time + stable row key 的 cursor index；
- project + expense type 下钻 index；
- bank account + project 下钻 index；
- expense type + project 下钻 index；
- bank tag primary + sub tag 下钻 index；
- transaction identity point lookup index。

每个索引必须由 `EXPLAIN (ANALYZE, BUFFERS)` 证明；不因“可能以后会查”添加索引。

2026-07-16 实施校准：05-04 只落地当前查询已经使用的 scope/time、parent rollup 和两类 transaction identity index；project/bank/expense/tag cursor indexes 未随表一起预建。它们必须等 view-specific SQL 定型并由 `EXPLAIN (ANALYZE, BUFFERS)` 证明后再添加，避免以“高性能”为名堆叠未使用索引。migration 是 additive，v9 schema gate 负责触发旧 scope 重建；读链路没有 dual-read。

### 5.2 Freshness gate

每次 API 读取最多先执行一个短 PostgreSQL gate query。它一次返回：

- scope metadata / schema version；
- read model 已发布的独立 metadata `published_source_version`（不得混入业务 `source_versions`）；
- 该 scope 按 `source_version desc, updated_at desc, id desc` 确定的最新 dirty record 及 status；
- App Settings 中仅成本需要的 bank tags、bank account mappings 与 tag selection 片段；
- concrete month 的 Workbench active generation/current dirty 与 Bank Detail scope/schema/status/current dirty/source versions；parent `all` 不查询两类虚构的 `all` dependency；
- 生成 ETag 所需的 version token。

判定规则：

1. schema 不匹配、model 缺失、cost/WB/Bank Detail dirty=`pending|processing|failed`、任一已发布 source version 未追上最新 dirty version、settings shape 非法、dependency scope/source versions 缺失，或业务 source versions 不匹配时，都不能返回 fresh payload；done history被 retention 清理、当前已无 dirty record 时允许以正式已发布 metadata 继续判定。
2. 非 fresh 时通过现有 `ReadModelRefreshGateway` normalize / validate / dedupe 后 enqueue，并返回 `202` 和稳定的 freshness envelope。
3. 只有 gate fresh 后才能读取 Redis。
4. Redis key 包含 scope、view、filters、cursor、schema、published source version、业务 source versions 和 tag-selection token；tag selection 由 settings owner 的无 I/O mapper从本次 gate settings snapshot 生成，不再次读取 settings。缓存中不保存 freshness 权威状态。
5. Redis miss 才执行当前 view 的结构化 rows query。暖路径是 `1` 次短 PG gate + `1` 次 Redis；冷路径再增加当前视图 SQL。

`latest dirty` 必须覆盖该 scope 的 active 与历史 terminal rows 并确定性取最高版本，不能使用没有 status/order 的任意一行。worker 的原子发布会在同一 repository transaction 中比较“已发布版本”和 event version：event 更旧时不得 delete/replace rows，也不得覆盖 metadata。

这样每次读请求只执行一个 indexed statement，且 Workbench、Bank Detail 和 settings 与 cost metadata 来自同一数据库 snapshot；没有跨 owner 网络往返，也不会因只信历史 metadata 而把事实源变化后的旧页面伪装为 fresh。durable fan-out、worker 条件发布和 Audit 继续承担最终收敛证明。

2026-07-16 实施校准：05-03 已落地 `0105` nullable metadata、conditional publish 同事务写版本、cost-only PostgreSQL gate、gate 后 Redis，以及旧 full-view dirty 查询删除；05-06 复用该 gate并在其后加入 cost-owned page cache/SQL；05-12 把 settings/Workbench/Bank Detail 的 current dependency proof 合入同一 statement，并删除 Application/runtime/query providers。page/full/month/detail 共享同一 gate contract，旧 provider symbol 由静态 guard 禁止回归。当前证据只证明 I/O 收敛与 fail-closed 正确性；真实 PostgreSQL plan、连接池排队和生产 SLO 仍待统一部署窗口。

05-04 继续沿用该 gate：transaction detail 不经过 Redis/full explorer，而是在 gate fresh 后调用 `get_cost_statistics_transaction(project_scope, transaction_id)`。05-06 又删除了前端详情失败时从列表行拼本地详情的 fallback；non-fresh/409 现在明确失败，不能打开伪成功详情。父级 `source_shards` 仍直接读取 concrete month metadata，因此无业务行的合法月份不会从版本证明中消失。

### 5.3 View-specific API

保留 `/api/cost-statistics/explorer` 作为页面唯一 explorer 入口，不新增长期并行 `/v2`。

请求参数收敛为：

- `project_scope=active|all`；
- `scope=YYYY-MM|year:YYYY|all`；
- `view=time|project|bank|expense_type|bank_tag`；
- 当前 view 所需的 project / bank / expense / tag filters；
- `cursor`；
- `page_size`，上限 `100`。

响应只包含：

- 当前 scope / view 的 summary；
- 当前层级 group/facet；
- 当前选中层级的第一页 rows；
- `next_cursor`；
- freshness / generated / ETag metadata。

summary 和 group/facet 必须由同一版本、同一组 filters 的完整集合在 SQL 中计算；cursor 只分页明细 rows，前端不得用当前页反推总额或总笔数。

页面切换 view 时才请求该 view。禁止在首屏加载其他四个 view，也禁止首屏加载 `active:all` 导出参考数据。

`year:YYYY` 只是以 `project_scope:all` parent 作为 freshness gate、再对结构化月份 rows 做年份过滤；禁止新增 year read-model scope、year worker 或 year cache warmup。

cursor 必须绑定 scope、view、稳定排序键和 published source version。翻页时版本已经变化则返回 non-fresh/重新开始，而不是把两个版本的 rows 拼在同一列表。前端切换 scope/view/filter 时取消旧请求，并用 request generation 保证只有最后一次响应可以写入页面状态。

响应使用原生 HTTP `ETag` 和 `Cache-Control: private, no-cache`；删除自定义 JavaScript TTL cache，不再增加另一套前端缓存层。

导出中心打开时才获取所需选项：project/expense-type 通过两个 `scope=all&page_size=1` 的 bounded facet 请求并行读取；time/bank-tag 不发该请求。preview/download 仍走原独立导出 API，不新增常驻 export-options 请求。

### 5.4 详情与导出

- transaction detail 通过 `transaction_id` / canonical identity 直接索引查询，不再加载 `active:all` 后线性扫描。
- export-preview 与 export 使用相同 repository filter contract，避免页面、preview、下载三套筛选口径。
- XLSX 使用 write-only workbook 和有界批次读取；禁止先把所有行装入 Python list。
- 保留现有 row-limit、权限和错误 DTO；超限必须在生成 workbook 前失败。
- 导出、详情和任何未来写操作都重新经过后端 freshness gate，不能仅相信页面遮罩状态。

2026-07-16 实施校准：05-15 没有引入通用 export framework、异步 job 或 HTTP streaming。成本 repository port 新增唯一
`get_cost_statistics_export_page(...)`：首批返回完整筛选集合 summary、最多 8（preview）或 1,000（download）行与 next offset，
后续批次不重复 summary。time/bank-tag 查 bank-flow rows，其余 bulk view 查 OA cost rows；month/project period 聚合在 SQL
完成。下载门槛通过后才创建 `Workbook(write_only=True)`，项目多 sheet 只保留费用类型/内容 aggregation buckets。序列化完成后
再次比较 schema、业务 source versions 与 `published_source_version`；变化时丢弃 bytes 并返回既有 non-fresh 409。bulk export
对完整 explorer payload、`_filtered_entries_from_read_model` 和普通 workbook 的旧依赖已删除。

### 5.5 数据库连接长尾

第一阶段不修改共享 pool：把每个 explorer 请求从约 `8–13` 个数据库查询收敛到暖路径 `1` 个短 gate query，显著缩短连接持有时间。

发布前负载测试若仍满足以下两个条件，才提出单独的成本 read capacity 变更：

- cost gate 的 pool acquire p95 仍高于 `100ms`；
- SQL 本身 p95 已低于 `100ms`，且等待是剩余主要耗时。

该容量变更必须单独评审 PostgreSQL 总连接预算和其他关键页面回归，不能在本方案中预先改全局 pool。SLO 未通过则不得发布，但也不为尚未证明的问题增加连接池抽象。

## 6. 事实变化后的收敛设计

### 6.1 回答“事实源变了但页面还是旧数据”

该风险真实存在；当前浏览器内事件不能覆盖跨用户、跨设备和后台任务。目标链路用三层保证消除“旧数据伪装 fresh”：

1. **durable fan-out**：所有直接依赖发布后都必须 enqueue 对应成本 scope，source version 在 PostgreSQL 内递增。
2. **worker CAS 语义**：repository 在同一事务中比较 event version 和已发布版本，只允许较新或相同版本替换 rows/metadata；完成 dirty scope 时传入 event `source_version`。
3. **read gate**：即使旧 worker 已写出一份结果，只要存在更高 dirty source version，API 就返回 refreshing，页面立即锁定，不会把旧 payload 标为 fresh。

### 6.2 必须补齐的 fan-out

- Workbench scope/schema、active generation / formal relation 的 `source_versions`：沿用现有成本 fan-out，补齐 scope 和 source-version 测试。
- Bank Detail scope 的 `source_versions`：发布 fresh 后新增对应 `active:YYYY-MM`、`all:YYYY-MM` 成本 refresh；父 scope 由月份 worker 收敛后再 enqueue。
- Cost settings：`bank_auto_tag_rules_version`、`bank_account_mappings_fingerprint`、cost tag selection/version 和 project status 变化后，经现有 derived lifecycle / gateway 标记全部受影响的成本月份 scope；当前可见 scope 由 operation barrier 等待，其他 scope 依靠 dedupe 后台收敛。
- OA attachment parser version 和 OA projection sync version：由 OA/Workbench owner 先完成自己的发布，再从 Workbench 成功发布 fan-out；禁止 cost 模块直接订阅半完成 OA 状态。
- schema version 只由部署触发成本 scope rebuild，不作为业务写事件。
- OA、invoice、ETC 等普通事实不直接跨边界写成本表；它们先由其 owner 收敛 Workbench / Bank Detail，再从 owner 的成功发布 fan-out，避免重复和乱序刷新。

上述清单必须与当前 `_cost_statistics_source_versions` 中的真实依赖逐项对齐，并由静态 contract test 锁定；删除请求时 expected-version 读取前，任何一项都不能遗漏。worker 将实际 settings snapshot、Workbench versions 和 Bank Detail versions 写入 model metadata，query 只读已发布 metadata。

### 6.3 worker 规则

1. 可先做一次确定性的 current-version precheck 跳过明显旧 event；precheck 只优化耗时，不承担正确性。
2. 在已有一致性 read snapshot 中读取 Bank Detail 依赖和 Workbench active generation，并记录完整 dependency versions。
3. 生成 rows 和 summaries。
4. repository 在单个写事务中锁定/比较 scope metadata：stored queue version 大于 event version 时整次发布 no-op；否则 replace rows、summary 和 metadata，并写入 event source version。
5. `complete_read_model_refresh(..., source_version=event.source_version)` 条件完成；返回 false 表示已经出现更高版本，新 dirty 必须保留。
6. query gate 始终比较 model published version 与该 scope 的最高 dirty source version；即使进程在 publish 与 complete 之间退出，也只能返回 refreshing，不能伪装 fresh。
7. 月份 scope 成功后 enqueue 同 project scope parent；parent 只有在 exact shard manifest 全部 fresh 后才能发布。

当前通用 `read_model_refresh_is_current` 若不能确定性读取最高/active source version，就不能被成本 worker 当作正确性门禁；允许把它作为 best-effort precheck，正确性只由原子条件发布、版本条件完成和 read gate 三者承担。

不新增分布式锁。现有 queue source version、dedupe 和条件完成已经足够表达该竞态。

### 6.4 已打开页面的更新

- 复用现有 `AppHealthStatusContext` 的 `/api/app-health/stream` SSE；EventSource 不可用时沿用 `5s` fallback poll。
- 成本页订阅 App Status 中 `cost_statistics` 当前 scope 状态，不新增 cost-specific SSE。
- 当前用户完成相关写操作时，沿用 operation barrier，立即进入 lock，不等待 SSE。
- 窗口重新 focus、`visibilitychange` 回到 visible、或 BFCache `pageshow.persisted=true` 时，成本页先进入 revalidating lock，再重新请求 gate。
- SSE 与 fallback 之间最多存在短通知窗口；详情、导出和写操作的后端 gate 会在该窗口内继续阻止旧数据被使用。

若未来明确要求“其他设备写入后 1 秒内必须看到视觉遮罩”，再单独评估 cost-specific notification；当前没有证据支持新增第二条实时通道。

## 7. Impeccable 轻量锁定遮罩设计

### 7.1 视觉意图

使用场景是一名财务人员在明亮办公环境中扫描密集表格；刷新发生时，界面应像账簿暂时被盖上一层薄描图纸：仍能辨认上下文，但明确知道它不可操作。

设计方向为 `Restrained`：

- 不做 modal dialog；
- 不做居中的实色 card；
- 不做玻璃拟态、`backdrop-filter`、大阴影或背景模糊；
- 不用营销式大标题、插画或装饰动画；
- 只使用现有 `--fp-*` token、正文层级和 info / warning / danger 语义色。

“80% 透明”在实现上表示遮罩底色 alpha 约 `0.20`，不是 80% 不透明。

### 7.2 页面结构

```text
成本统计页面
├─ 标题 + Audit 图标：保持可用，不进入 lock boundary
└─ 成本业务区域（相对定位）
   ├─ 视图、范围、刷新、标签规则、导出、表格、详情
   │  └─ locked 时 inert + aria-busy + opacity 降权
   ├─ 交互拦截层：20% page/surface 色，只覆盖成本业务区域
   └─ 顶部内联状态轨：小状态图标 + 一行主文案 + 一行辅助文案/重试
```

状态轨属于页面流和页面顶部，不悬浮在视口中央。它没有 card 外框、圆角容器或 dialog shadow，只用一条细分隔线建立阅读层级。

### 7.3 尺寸与 token

| 属性 | 设计值 |
| --- | --- |
| 遮罩背景 | `color-mix(in srgb, var(--fp-page) 20%, transparent)`；视觉上约 80% 透明 |
| 原内容降权 | 单一 wrapper `opacity: 0.62`；仅 opacity transition |
| 状态轨高度 | desktop 最小 `44px`；compact 自适应，允许两行 |
| 状态图标 | `14px`，使用现有 info/warning/danger 色 |
| 主文案 | `14px / 700`，`--fp-text-primary` |
| 辅助文案 | `12px / 400`，`--fp-text-secondary` |
| 分隔线 | `1px solid var(--fp-border)` |
| 动画 | 无；遮罩与 `14px` 状态点都保持静止，减少视觉噪声与合成工作 |
| 层级 | 仅高于成本页内容，低于全局 App Shell 状态与导航 |

不使用背景 blur。大面积 blur 会增加合成/绘制成本，也会让密集表格产生不必要的“玻璃”质感。

### 7.4 文案

| 状态 | 主文案 | 辅助文案 | 动作 |
| --- | --- | --- | --- |
| initial loading | 正在加载成本统计 | 数据就绪后将自动开放操作。 | 无 |
| refreshing | 成本数据正在同步 | 当前页面已暂时锁定，完成后自动恢复。 | 自动重试 |
| stale / version mismatch | 正在更新至最新数据 | 检测到事实已变化，旧数据暂不可操作。 | 自动重试 |
| failed / unavailable | 成本数据暂未就绪 | 页面保持锁定，请重新检查或稍后再试。 | `重新检查` ghost button |
| offline / request error | 无法确认成本数据状态 | 网络恢复前页面保持锁定。 | `重新检查` ghost button |

不向用户展示 `dirty scope`、`source_version`、SQL、worker event 等内部术语。

### 7.5 交互锁定

视觉遮罩不是安全边界，必须同时使用真实交互锁：

- 原页面业务 wrapper 设置原生 `inert`，阻止鼠标、触摸和键盘焦点。
- wrapper 设置 `aria-busy="true"`，并由状态轨 `aria-describedby` 说明原因。
- 拦截层使用 `pointer-events: auto`、`touch-action: none` 和 `user-select: none`。
- 状态轨位于 `inert` wrapper 外，因此失败状态的 `重新检查` 仍可操作。
- 页面标题、具备权限时的 Audit 图标、App Shell、全局导航和全局 App Status 不在 lock boundary 内，用户仍能诊断状态或离开页面；其他成本页按钮全部锁定。
- 页面 fresh 后一次性移除 inert 和拦截层，不逐个恢复按钮状态。
- export、tag rules、detail 等服务端 API 仍单独执行 freshness / permission gate；不能依赖 DOM 防护。

成本页拥有的 portal 不能逃逸锁定：

- 只读 transaction detail 和 export center 在进入 non-fresh 时关闭并清除旧 preview/detail。
- tag-rules drawer 若正在保存，沿用当前 saving + operation barrier 状态；否则保持 drawer 可见但把 drawer body / footer 一并 inert，保留当前草稿，不新增草稿持久化系统。
- 重新 fresh 后 drawer 恢复；保存仍携带 `expected_version`，后端继续拒绝跨用户版本冲突。

### 7.6 可访问性

- 状态轨使用 `role="status"`、`aria-live="polite"`、`aria-atomic="true"`。
- 只有当前焦点位于即将 inert 的成本业务区时，才把焦点移动到状态轨；不抢占 App Shell 或浏览器其他焦点。
- 颜色不是唯一提示：图标、主文案和辅助文案共同表达状态。
- 遮罩与状态点均无动画，因此不需要 reduced-motion 特例。
- 进入 lock 前记录最后一个成本业务区焦点；fresh 后仅在元素仍存在且可用时恢复，否则回到可编程聚焦的页面标题。
- 小屏状态轨可换行，但不覆盖导航；遮罩覆盖整个成本页滚动区域。

### 7.7 Effective UI state

页面只维护一个 `effectiveCostPageState`，按最严格状态合并：

1. API freshness envelope；
2. App Status 当前 cost scope；
3. 当前 explorer request；
4. 当前 operation barrier；
5. 网络/请求错误。

优先级：`failed/unavailable > stale/version_mismatch > refreshing/revalidating > loading > fresh`。

只要 effective state 不是 `fresh`，页面就锁定。只有 fresh payload 且 summary row count 为 `0` 时才能显示真实 empty state。

## 8. Audit 修复与性能设计

### 8.1 模块拆分

将成本统计分支从 `page_business_audit.py` 移到成本模块拥有的 `cost_statistics_page_audit.py`。通用 operations audit 只负责 registry dispatch 和统一 response envelope。

这不是增加新层；它把已经存在的成本 SQL 从通用模块移回正确 owner，并使 query budget、索引和测试责任可独立维护。

2026-07-16 实施校准：05-08 已完成该所有权迁移。`PAGE_AUDIT_REGISTRY` 使用唯一 `cost_statistics` executor；统一 HTTP、通用只读 CLI 和 System Audit 都直接调用 `audit_cost_statistics_page(...)`，并透传 caller-owned `AuditSnapshot`。`page_business_audit.py` 只继续拥有其余通用页面，并通过一个明确的 Bank Detail projection proof provider 向成本 owner 输出已登记的 canonical/field/version issues；成本 SQL、成本 issue mapping 和成本 dependency dispatch 已从共享文件删除。没有第二 route、snapshot、registry、repair 或 legacy fallback。

2026-07-16 实施校准：05-09 没有新增 proof cache/context 或通用 query builder。成本 summary query 用已有 dirty/outbox 表的 materialized CTE 同次返回 count 与 bounded samples；Workbench relation equality 只由既有 collector 执行一次，再映射出原成本与 dependency issue codes；`include_summary=False` 只用于成本丢弃该 summary 的调用，Workbench 页面默认仍读取完整 proof summary。active relation 本地预算固定为 32，但最多四组集合 SQL 与 `<=5s` 仍未完成。

2026-07-16 实施校准：05-10 只修改成本 owner 的 source-version proof。row/scope equality、月度 Workbench/Bank Detail current versions 和 parent materialized shard map 由一次集合 SQL 返回；每个分支在 union 前独立排序和 `limit`，保留三个既有 blocking issue codes 与 details。旧三次查询循环已删除，没有改通用 Audit、上游 proof owner 或 snapshot。active relation 本地预算固定为 30，但最多四组集合 SQL 与 `<=5s` 仍未完成。

2026-07-16 实施校准：05-16 只修改成本 owner 的 business-values proof。五个既有 SELECT 继续独立排序和 `limit`，再作为 limited subquery 用 `UNION ALL` 一次返回 `issue_code/subject_id/scope_key/details`；issue code通过绑定参数传入。旧五次 `_proof_query_issues(...)` 循环已删除，没有增加 query builder、proof cache/context、临时表、上游 owner修改或 fallback。active relation固定本地预算为26；成本自有 SQL尚有 summary/readiness、source-version、四个 exact-set类入口和 business-values共7组，生产 `<=5s`仍未证明。

2026-07-16 实施校准：05-17 根据 v9 schema 事实先删除 canonical expected-set、bank-flow 字段和 summary 重算中 3 处 `payload.bank_flow_time_rows` 旧读取。canonical 投影直接按结构化 `scope_month/transaction_id/amount` 聚合；字段 proof 直接比较结构化 identity/display/tag 列；summary 从 concrete month rows 构造 parent 逻辑 rollup。没有 dual-read、fallback、adapter、migration 或 query-budget 变化，成本 Audit owner 对该旧数组为零引用。一次性本地 PostgreSQL 完成 0001–0107 migration 后，v9 parent 无 row arrays 的完整 cost Audit clean-pass，证明 SQL syntax/列解析；真实数据 plan 和生产 `<=5s` 仍需统一部署后证明。

2026-07-16 实施校准：05-18 将 scope row count、missing scope、duplicate identity 和 canonical expected-set 四个 cost-local proof 作为独立 limited CTE，用一次 `cost_exact_set_proofs` statement 返回原 `issue_code/subject_id/scope_key/details`。canonical 分支仍完整执行 Workbench OA-bank 与 canonical full bank-flow 双向 equality；没有用 count/hash 代替 exact set。旧四 helper 与仅剩该调用方的 `_proof_query_issues` 已删除，无 wrapper/fallback。成本自有 SQL 从 7 组收敛为 4 组，active-relation 总预算从 26 降到 23；一次性本地 PostgreSQL 0001–0107 clean cost Audit 证明 SQL 可执行，真实 plan 与生产 `<=5s` 仍待统一部署窗口。

### 8.2 四组集合校验

成本 owner 在同一 caller-owned `REPEATABLE READ READ ONLY` snapshot 内执行四组集合 SQL：

1. **exact-set completeness**：canonical expected identities 与 `cost_statistics_rows` / `cost_statistics_bank_flow_rows` 双向 anti-join，识别 missing / extra。
2. **business values**：金额、方向、project、expense、bank tag 和 row count 不一致。
3. **version / parent proof**：row-model source versions、Workbench / Bank Detail 当前版本、parent exact shard manifest。
4. **queue / readiness**：当前 cost scopes 的 dirty/outbox/readiness 是否 drained/fresh。

05-18 已完成这四组 cost-owned statement 的本地收敛。为证明同一 snapshot 的上游事实，正式 Workbench 与 Bank Detail collector 仍会执行各自登记的完整集合查询；它们不属于成本 owner 的重复 SQL，不能删除、缓存或用成本投影反向自证。包含 active relation 的总查询预算因此是 23，而不是 4。

禁止：

- 按 scope 或按 row 循环发 SQL；
- 先取全量到 Python 再比较；
- 用 hash 相等代替 exact set 证明；
- 缓存上一次绿色 Audit 结果冒充当前证明；
- Audit 自动写数据或修复数据。

每组记录 `duration_ms`、row count、sample count 和 timeout。单组 statement timeout 不能代替总 SLO；整体 p95 必须 `<=5s`。

2026-07-16 生产校准：第一版 cost-local 诊断以不新增 SQL 为硬约束，先在响应中输出四组 owner proof 与两个 dependency collector 的 `duration_ms` / `issue_count`。底层 statement timeout 继续由 caller-owned Audit snapshot 和现有错误 envelope fail-closed；在没有 SQL 自身返回扫描行数的情况下不伪造 row count。取得慢组证据后，若需要 SQL 级 row/plan 数据，只对该组走受控 `EXPLAIN (ANALYZE, BUFFERS)`，不把通用 profiling 框架扩散到其它页面。

### 8.3 当前 mismatch 的修复判定

`cost_statistics_upstream_source_versions_mismatch` 只有在以下条件全部满足后才能关闭：

- Bank Detail 和 Workbench 发布后 fan-out 完整；
- cost worker 发布 metadata 记录实际依赖版本和 queue source version；
- worker 使用版本条件完成，旧 event 不能清除新 dirty；
- parent source shards 与当前月份 shard exact 相等；
- 生产 drain 后 Audit 连续多次 pass，而不是手工改 readiness。

## 9. 旧模块与旧代码删除清单

最终目标不允许旧链路并行、隐藏 fallback 或重复实现。以下内容必须在实现中做 whole-repo symbol/text scan 后删除。

### 9.1 后端删除

| 旧内容 | 当前证据 | 目标 |
| --- | --- | --- |
| `CostStatisticsReadModelService` 及 `cost_statistics_read_model_service.py` | **已删除（05-13）**；projection 直接提交单 scope repository write model，Application/runtime/API fixture 均无本地 owner | 静态 guard 禁止 module/class/import/server field/local persistence或测试替身回归 |
| `CostStatisticsService` 及 `cost_statistics_service.py` | **已删除（05-11）**；导出限制归 query owner，业务规则与测试归唯一 SQL projection owner | 静态 guard 禁止 module、class、import、`_cost_statistics_service` 测试替身或兼容 shim 回归 |
| `CostStatisticsRuntimeService` 中 local read model / background job / persist dependencies | **已删除**；runtime 只保留 durable refresh gateway 与规范 scope helper | 静态 guard 禁止 local owner、background job 或 persist dependency 回归 |
| repository/state-store 全量 load 与无版本 save | **已删除（05-14）**；port/manifest 只登记 scoped reads 与 conditional publish，broad load/save 不再携带成本 key | static guard 禁止旧方法、snapshot key、facade delegate、protocol method 或 direct-save test fixture 回归 |
| 请求时 expected source-version / tag-selection 读取 | **已删除（05-12）**；current settings/Workbench/Bank Detail 与 cost metadata 由单次 gate statement 读取，query 只做纯映射 | 静态 guard 禁止 server wrappers、runtime provider/expected method、query tag-selection provider 和 request-time settings/source reads 回归 |
| 旧成本 warmup job | **已删除**；生产只读 `/api/background-jobs/active` 证明 active/attention 均为0 | 静态 guard 禁止 server retry/recover/schedule/run、App Health/runtime registry、前端 type/mock 与 tests fixture 回归 |
| Application warmup delegates | **已删除**；derived lifecycle 直接经现有 gateway 入队 `cost_statistics.read_model.refresh` | 禁止恢复兼容 retry 或第二 job type |
| unversioned Redis keys | 05-04 已删除 projection 的 `cost_statistics:explorer:{scope}` set/delete；query gateway 使用 versioned key | 本地代码已完成；统一部署窗口只需确认历史 key 由 TTL/受控清理退出，禁止恢复 writer |
| `cost_tax_sql_projection.py` 的混合所有权 | **已删除（05-20）**；成本与税金 builder 已迁到各自 owner，生产 worker直接 import两者 | 静态 guard 禁止旧文件、旧 import、跨 owner class或兼容 re-export回归；税金行为不变 |
| parent JSON full arrays | 05-04 已让 v9 metadata snapshot 剥离 `time_rows` / `bank_flow_time_rows`，view/parent 只读结构化行 | 本地代码已完成；生产 migration 后必须全 scope rebuild 并证明旧 JSON 不再被读 |
| `get_transaction_detail` 的 `all` scan | 05-04 已删除两次线性扫描，改为 gate 后 repository identity lookup | 本地代码已完成；生产用 EXPLAIN 和 detail SLO 复验 |
| projection unchanged 的 full-view scan | **已删除（05-19）**；只用 `get_cost_statistics_scope_metadata(...)` 点查 parent 三字段，fixture/静态 guard禁止 full-view/payload 回归 | 本地代码已完成；统一部署后验证真实 worker skip 与 write-to-fresh p99 |
| 旧 summary/project API route | **已删除**；系统 owner 确认无已知脚本、RPA、BI或第三方 consumer，且从未作为公共集成合同承诺 | 静态 guard 与全仓生产扫描禁止 route、DTO、client/mock、full-view loader 或 fallback 回归 |

### 9.2 前端删除

- 5 分钟 `costExplorerCache`、`getCachedCostStatisticsExplorer`、`clearCostStatisticsExplorerCache`。（05-05 已本地删除）
- 首屏 `active:all` export reference prefetch effect。（05-05 已本地删除；导出参考数据只在需要时读取 fresh payload）
- `fetchCostStatisticsMonth`、`fetchProjectCostStatistics` 和无调用 types/mappers。（05-05 已本地删除）
- explorer 全量 `timeRows` / `bankFlowTimeRows` mapper 和客户端 group-by / summary 重算。
- 依赖完整 all payload 的导出选项与 project expense options 计算。
- 旧 non-fresh `state-panel` 文案分支。（05-07 已由唯一 `effectiveCostPageState` 和 lock rail 替代）
- 为旧 warmup job 提供的 background job type、label 和 UI test fixtures。

### 9.3 测试与文档处理

- 删除旧模块测试前，把仍有效的业务规则迁移到 projection/repository/query contract tests；不能以删测试代替迁移责任。
- 当前模块 README、boundary I/O、state machine、tests、app architecture、read model contracts、worker governance 和 API docs 随实现更新。
- `.planning/` 历史记录和已归档 implementation history 可以保留为历史证据，但不得被当前文档描述为可用 fallback。
- 加静态边界 guard：禁止重新出现旧 class、warmup job type、unversioned Redis key、全量 all prefetch、query live scan 和混合 cost-tax owner。

## 10. 实施顺序与回滚

### 10.1 实施切片

1. **预检**：完成 access log、历史 warmup job、Redis key、所有 symbol/caller、部署 manifest 和外部消费者扫描。
2. **Schema + repository**：新增 bank-flow rows 表和已证明索引；实现 gate、view query、detail query 和 streaming export。
3. **Worker correctness**：补齐 fan-out、event version 原子条件发布、conditional complete、parent exact shards。
4. **API + frontend**：同一次应用发布切换 view-specific contract；加入 cost-local lock overlay；移除 custom cache 和 all prefetch。
5. **Audit**：迁移成本 SQL、优化四组集合校验，修复真实 mismatch。
6. **旧代码删除**：删除 live/local/warmup/full-payload/client 路径和对应 current docs；运行 whole-repo guard。
7. **生产重建**：schema version 升级使旧 scope fail-closed；优先重建当前业务月，再收敛 parent scopes。页面在此期间显示 lock，不走旧读路径。
8. **验收**：性能、Audit、worker race、跨用户 freshness、其他页面回归全部通过后才结束发布。

当前执行状态：worker correctness、PostgreSQL-first dependency gate、结构化 rows、详情点查、view-specific cursor、bounded/write-only导出、cost-local lock、成本 Audit唯一 owner与四组 cost-owned 集合 SQL，以及 legacy live/local read-model owner、repository/state-store全量load/无条件save、cost/tax混合 owner、warmup 和旧 HTTP/full-view删除均已本地完成。页面没有新旧 response/non-fresh UI双读；Audit没有新旧 executor双路；projection没有混合 module或兼容 import。未新增索引，必须等待统一部署窗口的真实 `EXPLAIN (ANALYZE, BUFFERS)` 决定。当前是 `READY_FOR_UNIFIED_DEPLOYMENT / DEPLOYMENT_HOLD`，只剩生产执行、mismatch修复、连续 pass与SLO验证。

### 10.2 无双读迁移

- 不新增 feature flag、双写或 legacy read fallback。
- 新版本只认新 schema；旧 scope 返回 `202 refreshing`，由 worker 重建。
- 前后端作为同一 release 部署，避免长期兼容两种 explorer response。
- 若 access log 发现外部 summary/project consumer，必须在发布前迁移；不能用永久兼容分支绕过。

### 10.3 回滚

- 数据库变更保持 additive；回滚不 drop 新表或索引。
- 回滚使用上一 release artifact，不把旧实现留在当前代码分支。
- 上一版本通过 canonical facts 重建旧 schema；必要时先恢复 read model 表备份。read model 可重建，不手改 fresh 状态。
- 回滚期间页面继续 fail-closed / lock，直到对应版本重建完成。
- 首选 roll-forward 修复；只有权限、数据损坏或无法满足 SLO 时回滚。

## 11. 测试闭环

本次变化跨 frontend、API、repository、read model、worker 和 Audit，七类测试全部适用。

| 类别 | 必须覆盖 |
| --- | --- |
| 1. 业务核心 unit | project/expense/tag/direction 口径、empty/boundary/duplicate、scope 解析、exact source version 比较 |
| 2. service-layer | repository 分页/详情/导出、Redis 仅缓存 fresh、fan-out idempotency、Audit repository、无半写状态 |
| 3. API contract | fresh 200 shape、refreshing 202、failed/unavailable、非法 cursor/filter、权限、ETag/304、export limit 和错误 DTO |
| 4. read model/cache/worker | source-version race、旧 event、重建中再次写入、parent 等 shard、cache stale、dirty conditional complete、worker retry/cleanup |
| 5. frontend interaction | initial/refreshing/stale/error/fresh/empty、inert、pointer/keyboard、focus restore、reduced motion、retry、portal lock、view pagination |
| 6. E2E business flow | Workbench relation 或 Bank Detail 事实变化 -> durable queue -> worker -> page lock -> fresh 自动解锁 -> 新值可见；Audit pass |
| 7. existing regression | Workbench、Bank Detail、Tax Offset、导出、权限、App Status、其他 read model 和旧页面加载性能不回退 |

还必须增加以下负面用例：

- source 在 worker rebuild 中途再次变化；旧 event 不能完成新 dirty。
- v2 已发布后 v1 才结束时，v1 的 transaction 不能覆盖 v2 rows/metadata。
- cursor 携带的 published version 过期时不能继续翻页；快速切换 view 时旧响应不能覆盖新响应。
- SSE 不可用时，5 秒 fallback 能让已打开页面锁定并最终解锁。
- BFCache 返回页面时先 revalidate，不能瞬间开放旧操作。
- Redis 留有旧 payload 时，PG gate 不 fresh 必须忽略 cache。
- drawer / modal 通过 portal 渲染时不能继续提交、导出或打开详情。
- Audit queue drained 但 upstream versions mismatch 时仍失败。
- 新 schema 发布期间没有任何 legacy full-payload fallback。

## 12. 可观测性与发布门禁

成本链路增加分阶段 metrics，但不增加新的监控系统：

- server：pool acquire、freshness gate、Redis、rows SQL、serialize、response bytes、query count；
- client：navigation-to-data-ready、fetch、JSON/map、React commit、DOM node count；
- worker：enqueue-to-claim、build、publish、enqueue-to-fresh、superseded event count；
- Audit：四组 SQL各自 duration / rows / samples / timeout。

发布必须同时满足：

- 第 2 节全部 SLO；
- Audit 三项通过；
- 当前月与 `active:all` freshness 正确收敛；
- 新旧 writer/read path 静态 guard 通过；
- 其他关键页面 p95、错误率和 read model 状态不回退；
- 发布候选中不存在 warmup job/旧 HTTP/full-view production path；历史 Redis key 不存在 writer，只能自然 TTL 或按统一部署 runbook 受控清理。

## 13. 过度设计复审

### 13.1 保留的复杂度及理由

| 保留项 | 为什么不可省 |
| --- | --- |
| 一张 bank-flow rows 表 | 当前银行流水只在大 JSON 中，无法做索引分页、点查或 streaming export |
| durable queue source-version CAS | 生产 Audit 已证明可能错误收敛；仅靠 UI 刷新不能修复 |
| view-specific cursor query | `active:all` 已达 765KB，前端全量聚合无法达到已确认 SLO |
| 成本专属 Audit repository | 当前 Audit 12–35s 且混在通用 SQL 中，不能独立优化和维护 |
| 成本页局部 lock | 用户明确接受刷新期不可操作，并且它阻止旧数据被误用 |

### 13.2 明确不做

- 不新增专用 SSE、WebSocket、Kafka、RabbitMQ 事实源或前端事件总线。
- 不新增通用遮罩框架，不把该 UI 推到其他页面。
- 不新增多张预聚合表或 OLAP 系统。
- 不新增 `/v2` 长期并行接口。
- 不引入虚拟列表/表格依赖；先用服务端分页把每页限制在 `<=100`。
- 不新增 year read-model scope、year worker、分布式锁或请求 singleflight；只有负载证据证明现有分页 SQL仍不足时再评估。
- 不改全局 App Shell、全局 StatePanel、共享 DEFAULT_MONTH 或其他页面 read model。
- 不预先改共享数据库 pool。
- 不保留 live scan、local read model、warmup、full JSON 或 unversioned cache fallback。
- 不用定时全量重建掩盖缺失 fan-out。
- 不让 Audit 自动修复数据。

## 14. 最终计划复审与遗漏检查

再次审阅后，原计划中容易遗漏的部分已全部纳入：

- 其他用户/后台任务改变事实后的已打开页面鲜度；
- worker rebuild 中途再次写入的版本竞态；
- 发布事务防止旧 event 覆盖新 rows，以及 cursor / latest-response 版本稳定性；
- 当前全部直接 dependency versions 的 durable fan-out 清单；
- Redis 命中不能绕过 durable gate；
- BFCache、focus、background tab 和 SSE 不可用；
- modal/drawer portal 逃逸 `inert`；
- 刷新期间 Audit 图标仍可诊断，而其他成本操作保持锁定；
- 详情和导出对 `active:all` 的隐藏依赖；
- 首屏无条件导出参考数据预取；
- 静态默认月份；
- 父 scope exact shard 收敛；
- Audit 性能和真实 mismatch 的分离处理；
- 旧 class、Redis key、client、混合 projection owner、warmup job、旧 route/full-view 与对应 tests/current docs 全量删除；
- 无双读迁移、生产重建和外部 consumer 预检；
- additive schema rollback；
- 七类测试、可观测性、其他页面不回退门禁。

最终判断：这是一个简洁但闭环的生产方案。它没有为未来假设增加平台级抽象；每个保留部件都对应已量测的性能问题、已出现的 Audit 失败、明确的一致性风险或用户已经确认的交互要求。

# 关联台 实施记录

## 2026-07-25 - 同次 freshness proof 复用

- Workbench 页面 gate 已计算 canonical expected source versions 时，enqueue 同时携带与 exact scope 绑定的 token/proof；queue 只保留有界安全 metadata，worker 校验 token/scope 后直接交给 projection，避免 worker 再跑同一组 canonical SQL。
- worker 发布仍以 event source version 条件完成并生成 active generation；proof 只省略重复 expected 计算，不绕过 active projection、dirty/outbox 或 source-version 竞态检查。projection missing 时不附 proof/token，保留既有首次访问自愈。
- 未引入 proof cache、第二事实源、表、migration、queue、worker 或新 API；删除了评估中不能证明收益的 watermark/cache 方案。

## 2026-07-26 - 搜索首屏复用 freshness gate

- 生产 durable outbox 证明并发恢复后的残余 `workbench:all` 均来自 `api_initial_page_stale`。真实页面携带区域搜索，旧 facade 把 Redis cacheability 与 source freshness gate 绑定，导致不可缓存查询跳过 exact mismatch proof，随后按 `all` scope 补投全量刷新。
- 修复让默认、搜索、筛选和排序首屏统一先走现有 freshness/status/scope gateway；`cacheable_query` 只控制 Redis read-through。真正 missing/cold-start 的恢复入口保留，relation 写、projection builder、worker、API shape 与其它页面 I/O 不变。

## 2026-07-25 - 完成窗口 target 去重与旧 background persist 删除

- 第一候选生产只读事件时间线显示，同一`2026-02` scope在页面轮询期间连续消费10992→10995等多个执行版本，但canonical业务target没有相应次数变化；写API已零read-model fan-out，放大发生在active event刚done到页面再次poll的完成窗口。
- Workbench访问producer仅在active projection存在时，用exact scope与canonical expected source versions生成稳定`freshness_token`；projection missing不附token，保持首次自愈。query facade按单次请求复用freshness gate已经计算的expected versions，bulk all-scope proof也把同一次结果直接交给enqueue，不为生成token重复执行canonical proof。共享runtime queue在原有advisory lock内比较active/最新成功target；不同target保留必要follow-up，dirty orphan/failed不被历史done吞掉。
- 删除未再被生产调用的`_schedule_workbench_read_model_persist`、后台重建线程、版本锁/pending set与`FIN_OPS_WORKBENCH_PERSIST_ASYNC`分支。正式生产链只保留访问时gateway→durable queue→Workbench worker→active generation原子发布；旧测试改为直接断言符号不存在，不保留no-op兼容入口。

## 2026-07-24 - 并发月份 generation-set 原子发布

- production round 8 中两个 Workbench 月份由两个 worker并行完成，但旧 per-month advisory lock允许两个发布事务分别基于中间 active month set写 all-scope stats；最终 generation-set digest可能没有对应统计，confirm checkpoint System Audit因此 fail closed，并出现约 3.25–3.33秒的 handler争用。
- 最小修复保留 payload计算与 generation staging/COPY并行；重型数据写完后才用单个 `workbench_generation_set` transaction lock串行化 active切换和 all-scope stats。没有新增表、worker、queue、缓存、协调器或第二 read model；若该短发布段生产仍超过3秒，先优化既有 stats SQL，不拆分原子发布合同。

## 2026-07-23 - 访问时 canonical proof 去重

- 生产 test-owned turnover closure 证明普通 confirm 已在 `198.312ms` 内提交且写后页面 refresh event 为零，但首次访问 stale Workbench groups 为 `1548.125ms`，超过单次 HTTP 1 秒门槛；请求 profile 显示约 `1471.805ms` 为数据库时间。
- 真实原因是同一次 `WorkbenchQueryFacade.initial_page/groups` 请求先通过 freshness status 计算 canonical expected source proof，加载 payload 后又调用 payload stale-reason gate计算同一 proof。两次 proof 的 scope、结果和 enqueue 语义相同，第二次属于旧重复读链路。
- 最小修复复用 freshness status 已完成的 source proof；freshness status 不可用时仍执行既有 payload fallback 并 fail closed。active generation、version conflict、Redis fresh gate、精确 refresh gateway、Cost 上游依赖 gate 和普通写零 fan-out合同均不改变。
- 测试锁定 initial/groups 不再第二次调用 payload stale proof，同时保留 freshness callback、月份/all 依赖和现有 stale/refreshing/version-drift 回归。

## 2026-07-23 - 访问轮询 active refresh 去重

- 生产 test-owned fixture 证明普通 confirm/withdraw 写耗时短且零页面 fan-out，但 Workbench worker 单次 handler 约 1.3–1.6 秒时，页面轮询仍在数秒内产生多个 source version，使 in-flight generation 被 supersede，访问到 fresh 延长到约 4.7 秒。
- 根因是 `RuntimeQueueRepository.read_model_refresh_is_active(...)` 只看 outbox active event；outbox 可先于 durable dirty scope 完成，形成错误的“无任务”窗口。
- 最小修复把 active 事实改为 exact dirty scope `pending/processing`。不新增缓存、协调器、页面分支或写后 target；canonical mutation、显式 repair/reapply 和 force 仍推进版本。

## 2026-07-22 - 两区滚动自动分页与全量搜索闭环

- 目标：移除已配对和未配对区域底部“已加载 N / total”与手动“加载更多”，保留每区 50 组首屏，并在用户滚动接近各自列表底部时自动加载下一页；区域搜索继续命中服务端全部数据，包括尚未加载页、隐藏 pane 和折叠明细。
- 边界决策：只在 `RelationGroupGrid` 内用原生 `IntersectionObserver` 观测滚动容器底部哨兵，向页面输出 `zoneId`；页面继续拥有 `/groups` 请求、查询 key、active read-model version、合并和错误状态。没有新增 API、后端查询、缓存、worker、依赖或通用分页抽象。
- Freshness 与竞态：自动分页只在区域可见、`read_model_status=fresh`、搜索防抖已稳定、当前已安装 query key 与请求 query key 一致时开放；每区独立 in-flight/sequence gate 去重，搜索、筛选或 active version 更新立即使旧响应失效。普通网络失败停止自动重试，只在原区域显示一次显式重试，防止观察器形成请求风暴。
- 旧链清理：删除 `zone-page-footer`、`zone-load-more-btn`、`onLoadMore` 组件 I/O 和旧错误文案；没有保留隐藏按钮、兼容 fallback 或并行分页实现。Cost Statistics 的同名分页属于独立模块，不在本次范围内。
- 性能：首屏和服务端全量搜索合同不变；无滚动时不增加 `/groups` 请求。接近底部才读取 50 组下一页，避免一次性把全部组传输和渲染到 DOM；观察器回调为浏览器原生交叉检测，同区最多一个在途请求。
- 测试覆盖：Vitest 锁定 fresh 才注册观察、stale 不触发、失败仅显式重试；Browser E2E 锁定首屏 50、滚动前零分页请求、滚动后单次请求、搜索第 155 组并高亮、分页失败不循环重试及手动恢复，同时回归详情、选择和三栏滚动。
- 文档影响：combined initial/API response shape、read-model scope、worker、权限和跨模块 I/O 均未改变；更新本模块 `boundary-io.md`、`tests.md`、`e2e-spec.md`、`e2e-coverage.md` 与本记录，其他长期事实源不适用。

## 2026-07-21 - relation 冻结要求与关联台展示分区闭环

- 真实原因：新 formal-relation grouping 曾把所有 active relation 无条件发布到 paired，覆盖了 relation 创建时的 `requires_oa` / `requires_invoice`；deterministic matching 写入又遗漏 requirement snapshot，因此“工程服务费 / 人员保险”只有 OA+银行、没有发票时仍显示为已配对。
- 边界决策：active relation 继续是跨页面 linked ownership 唯一事实源；只有关联台纯分组投影按 relation 自身冻结要求决定 paired/unpaired。未满足要求的 active relation 保持同一 case，不拆成员，不回查当前 settings，并返回 `completion.missing_row_types`。ETC、批量账务等显式业务完成合同继续隔离。
- 写路径：人工确认复用既有 bank-tag fresh bulk read；deterministic matching 在一个 batch 内只读取一次全部 bank tags，并在 relation UoW 首次保存时写入 requirement snapshot。non-fresh 或缺行时整批 fail closed，不写半条 relation。
- 旧链清理：删除 no-OA application 中越权扫描、逐 relation 回写 bank-flow requirement 的旧 `_sync_bank_flow_rule_relation_requirements` 及专用比较 helper；规则保存保持 O(1)，existing relation 不追溯改写。存量缺快照关系只允许在部署窗口经 relation command/history 一次性修复。
- 性能与隔离：没有新增表、索引、worker、queue、共享 read model 或请求内 I/O；分区计算是已加载 relation 上的纯 O(member count) 判断。Redis groups/initial 使用关联台专属 cache schema 淘汰旧分区 payload，不升级共享 Workbench projection schema，因此不标脏成本统计或搜索 read model。
- Audit：Page Audit 独立复算快照完整性与期望 zone；缺快照或错误 paired/unpaired 都 blocking，不能复用生产分组 helper 自证。
- 生产存量闭环：发布账号不具备任意 root shell 权限；一次性存量修复因此收敛为 root-owned
  `workbench-requirement-repair` 固定命令。它先以 current active relation + 一次 fresh 标签批量读取生成
  source fingerprint，再在 fingerprint 未变化时逐 case 更新 tool runtime，并通过既有
  `persist_workbench_pair_relations` port 一次持久化正式 metadata/history 与 durable refresh；不允许直接
  SQL，也不恢复规则保存后的持续回扫旧链。
- 生产 rehydrate 补充门禁：旧 generation consistency 曾把任何 active relation 出现在 unpaired 都判为
  损坏，和“active relation 缺冻结要求时保留同一 case 并进入 unpaired”的新合同冲突。validator 现只在
  group 没有显式 `completion.is_complete=false` 证据时阻断；它复用 projection 已发布的 completion
  结果，不在 repository SQL 复制 OA/发票业务规则。缺 completion 仍 fail closed，避免放宽旧坏数据。


## 2026-07-20 - 折叠流水详情按需加载合同闭环

- 目标：修复部分已配对组点击“展开 N 条明细”无响应，同时保持首屏不预取折叠明细；生产样例表现为 3 条摘要组可直接展开，而 28 条摘要组的详情响应缺少空的 OA/发票数组，前端映射抛错后被静默吞掉。
- 影响范围：仅关联台 active-generation group detail materializer、`GET /api/workbench/groups/detail` 客户端合同、关联台详情安装语义和 `RelationGroupGrid` 展开交互；不修改 relation 事实、projection、worker、queue、Redis、数据库 schema 或其他页面 read model。
- 关键决策：repository 详情物化必须稳定输出 `oa_rows`、`bank_rows`、`invoice_rows` 三个数组，空 pane 返回空数组；详情客户端验证 group identity、三数组 shape 与声明成员数，HTTP 200 但结构缺失或成员不完整一律 fail-closed；页面 Promise 只有在同一 active read-model version 的完整详情写入后才 fulfilled；组件仅在用户点击时请求详情，失败时保持折叠并显示“加载失败，点击重试”。
- 旧逻辑清理：删除 mount/update 时自动预取折叠详情的 effect、pending/failed request refs、request-key helper 和静默失败分支；不保留并行预取、兼容 fallback 或第二套详情状态机。
- 文档影响：模块边界、输入/输出 owner、API URL、response 字段、read-model scope 和 worker 合同均未改变；本记录和 `tests.md` 补充详情完整性与惰性加载不变量，其他长期文档不适用。
- 测试覆盖：后端覆盖 production-shape materialized group 在 OA/发票 pane 无成员时仍返回空数组；API 单测覆盖字段缺失、声明成员不完整 fail-closed；组件覆盖零预取、点击单次请求、失败可见及重试；E2E 覆盖 3 条摘要经一次详情请求展开为 4 条完整流水。
- 验证命令：见本轮最终说明及 `tests.md`；发布后使用正式生产 release、真实 active generation 与只读浏览器/API probe 验证。
- 未测风险：本条记录写入时生产部署和生产性能验证尚未执行，最终结果以本轮发布后的生产证据为准。

## 2026-07-17 - 统一生产部署与写后验证闭环

- 发布：精确 SHA `d3fc16026` 的 Nightly CI 成功后，生产 release `main-d3fc16026-oa-outbox-index-20260717` 完成 migration、API/dispatcher/22 workers、readiness、前端 hash 与公网 session route 门禁。
- 性能：浏览器等价持久连接 isolated 100 次均为 `200/fresh`，combined initial 为 `p50=455.076ms / p95=607.207ms / p99=679.595ms`；三页 simultaneous 50 轮为 `p95=689.027ms / p99=725.643ms`，通过 `1000/1500ms` 门槛。
- 写后正确性：test-owned turnover relation 经正式 API confirm 后由正式 withdraw API恢复为 `inactive`；撤回后的两轮关联台 Page Audit 均为 `pass/fresh/drained`、`issues=0`、`database_snapshot=true`，约 `1.560s` 与 `1.414s`。
- 隔离：dashboard rolling profile 保持固定 13 queries、连接获取 p95 低于 1ms；没有修改 Workbench read model、连接池或响应合同来迁就 OA 页面性能。

## 2026-07-17 - combined initial 首屏 payload 收敛

- 生产证据：`GET /api/workbench?month=all` fresh 响应解压后约 `2.84MB`、gzip 约 `171KB`，浏览器等价单次请求约 `1059ms`；现有 combined initial 每区返回 200 groups，传输、JSON 解析和可见成员物化成为首屏固定成本。
- 决策：保持同一 `WorkbenchQueryFacade -> PostgresReadModelRepository`、repeatable-read、active generation version、Redis read-through 和 `/groups` 分页合同；只把 paired/unpaired 首屏固定为各 50 groups，并同步前端默认 page size。summary total、`has_more` 与后续 `expected_read_model_version` 分页保持完整。
- 隔离：不改 projection、worker、relation write、其它页面 read model、cache owner、表或索引；不新增 preload/prefetch 或第二首屏 API。
- 测试：SQL shape 锁定单次双区查询 `zone_rank <= 51`、两区 `page_size=50`、筛选首屏 limit 51 和最多 10 statements；相关后端与前端 Workbench tests 通过。
- 待生产门：发布后复测 combined initial p95，并在 confirm/withdraw 后等待 exact barrier、重读 fresh 页面和 Page Audit；若仍超 1 秒，先用请求/SQL证据定位，不恢复 200-group 首屏或叠加缓存层。


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 2026-07-25 - 写后恢复轻量状态等待

- 真实原因：没有 operation projection 的关联台写操作在 active generation 恢复期间每 150ms 重复调用 combined initial；公开 refresh-status 同时仍走完整 consistency diagnostic，页面读 I/O 会与 worker 重建竞争。
- 边界决策：保留现有 canonical write、exact access enqueue、active-generation 原子发布和 10 秒操作等待；第一次 combined initial 负责触发 recovery，等待阶段只读既有轻量 groups freshness status，canonical proof 返回 fresh 后再读取一次完整 payload。
- 实现范围：`WorkbenchQueryFacade.refresh_status` 复用 SSE/groups gate 已使用的 repository port；前端复用既有 `fetchWorkbenchRefreshStatus`。没有新增 cache、表、索引、migration、queue、worker、SSE、协调器或第二 freshness 系统。
- 旧链清理：删除操作等待循环中的重复 combined initial 读取；完整 diagnostic repository port 只作为缺少轻量 port 的兼容 fallback，不再是生产页面热路径 owner。
- 测试：backend 锁定轻量 port 与 timeout fallback；frontend 锁定 refreshing 期间 3 次 status poll、完整页面恰好 2 次，并验证撤回后的三类 singleton 数据完整性。
- 首个候选生产证据：confirm/withdraw 均约 `296–323ms`，写后零 fan-out、最终数据和恢复断言、queue drain、worker、System Audit 全部通过；轻量 refresh-status 为 `241–372ms`，Workbench worker handler 为 `1.278–1.925s`。剩余 Workbench 首次 fresh 读取为 `3.776–5.235s`，请求数据库 p95 约 `3.260s`，证明慢点已从状态轮询/worker 收敛到新 generation 发布后的第一次 groups SQL。
- SQL 根因与修复：带搜索的 all-scope count 把全部 active members 强制 `MATERIALIZED`，形成优化屏障；搜索和最终成员计数都要重新扫描该临时集合。保留原 SQL owner、事实和返回合同，仅改为 `NOT MATERIALIZED`。20 万 active member 的临时 PostgreSQL 17 对照中，旧计划写/读 3747 个 temp blocks、`258.863ms`；新计划无 temp I/O、`94.614ms`。没有新增 cache、表、索引、migration、worker 或第二 freshness 系统。
- 最终生产闭环：release `main-f06711b7-20260725213147` 已激活。`/api/workbench/groups` 滚动 p95 从首候选 `3476.949ms` 降到 `2882.325ms`，发布后 5 次 hot all-scope 搜索为 `340–756ms`；confirm/withdraw、完整配对数据、输入隔离、写后零 fan-out、eventual fresh、durable drain、24 workers 和 System Audit 全部通过。六 consumer 并发仍有 Workbench `4616.117ms` 尾样本，因此硬 3 秒保证继续延期，不以平均值冒充绝对 SLO。

## 当前决策

- `oa_bank_exact_sum` 属于后端自动匹配规则；符合正式化条件的 paired decision 必须由后端通过 relation command 写成 active relation，不能只在 `server.py` 或前端补展示逻辑。
- Workbench matching 的生产关系口径已经收敛为 decision/free engine -> active relation；legacy candidate 名称只作为历史代码/测试兼容，不再作为下游业务关系状态。
- 旧逻辑清理不和业务规则变更混做。`WorkbenchMatchingRules`、`WorkbenchFreeMatchingEngine`、`WorkbenchReconciliationEngine`、工资/内部转账 legacy rule code 仍有 orchestrator、worker、免 OA、分组和异常投影调用或兼容引用，不能无测试删除。
- OA 附件解析缓存不是正式发票事实源。Workbench 发票栏和 relation projection 只读取 canonical invoice/read model；OA 附件 OCR 结果是否补充到统一发票池由设置页 `OA附件发票晋级` 控制，默认 `link_existing_only` 只关联已有发票，不创建缺失发票，`disabled` 完全跳过，只有 `create_missing` 才允许受控创建。旧 OA query service 只保留 OA detail 附件摘要。
- 外部往来 `turnover_manual_closure` 是 confirmed active relation fact；同一个 active case 下两条及以上银行流水形成的外部往来闭环必须保留 canonical ownership 和“收支闭环”证据。展示分区由 relation metadata 的 OA/发票 requirement 决定，未满足 paired 条件时留在 open 待处理区，满足后进入 paired。
- Workbench SQL active generation 的发布跳过逻辑不能只比较 numeric `source_version`。当 incoming `source_versions` 中的 builder/schema/rules/parser 等签名与现有 active generation 不一致时，即使 incoming `source_version` 更低，也必须发布新 generation；否则 schema bump 只能让状态显示 stale/refreshing，无法替换旧 generation。

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

## 2026-07-16 - Release B 旧状态 migration 版本合同修正

- 目标：修正 Workbench 文档把 Release B 旧状态 drop migration 固定为 0104 的版本冲突；当前 0104 已属于 OA 待付款 source snapshot。
- 决策：Release A 不携带 Workbench 旧状态 drop migration。只有 Release A 的运行时零访问、数据哈希、freshness、queue 和 Audit 证据全部通过后，Release B 才使用届时下一个可用版本创建 forward-only drop migration；不提前预留空 migration。
- 行为影响：仅修正文档与发布合同，不改变 runtime、schema、read model、worker、API 或其他页面。
- 验证：migration discovery、docs check 和 architecture guard 纳入统一 release candidate 验证。

## 2026-07-16 - 删除 raw/on-demand 失活后的旧 Workbench 级联链

- 目标：在关联台页面读链已经收敛到 active generation 后，删除不再有生产调用者的 live/OA/raw/retention/grouping/ETC 兼容拼装链，防止旧 DTO owner 继续污染查询、写入和测试。
- 影响范围：`server.py` 旧 wrapper/instance cache、24 个 test-only service module、旧 `WorkbenchApiRoutes` 读兼容壳、OA 附件 context row index 的 raw surface、架构 guard、Workbench/ETC/Cost 测试 fixture 与模块边界。
- 关键决策：保留当前 SQL projection、`WorkbenchQueryFacade`、canonical row resolver、relation command/grouping、确认关联仍使用的 grouped OA attachment context index、Settings reset 的 retention month/date parser，以及 ETC relation cleanup 使用的稳定 summary row id。删除旧 read-time OA 冲账自动配对/修复，不新增替代 executor、projection、fallback 或兼容 API。
- 旧逻辑清理：删除 live/OA/retained-all/selected-scope builders、raw mutation/canonical repair/live merge/group-row helper、read-time OA invoice-offset sync/desired/repair executors及其 read ports、旧 ETC summary DTO 拼装、grouped payload 二次 override/tag 链、legacy row-detail/action wrappers 和 `WorkbenchApiRoutes`。负向 guard 同时锁定文件和 server symbol 不得恢复。
- I/O 结果：页面 initial/groups/group detail/row detail 只走 query facade -> active generation repository；写命令仍从明确 canonical/relation I/O 取事实；Redis、worker、其他页面 read model 与 DTO 均未新增 owner。
- 测试覆盖：关联台 SQL/query/write/V2、ETC、Settings reset、OA projection 455 passed、4 skipped；完整 runtime boundary guard 202 passed；移除旧 route 后 Workbench V2 + Cost API 51 passed。Ruff 通过。
- 未测风险：按用户要求未部署、未访问生产 token/队列；真实生产 cold/hot 与 worker/SLO 仍留待统一发布后验证。
- 后续事项：继续按 Phase 04 主控检查 Import Workflow 解耦、legacy Cost service 最终删除、前端/E2E、受控性能报告和统一发布交接。

## 2026-07-16 - 删除 on-demand Workbench 整页构建链

- 目标：在 initial/groups/detail、Search、Batch Accounting、Settings、Cost fixture 和写入命令均已迁到 active generation 或窄 canonical I/O 后，删除请求内同步重建整页 Workbench 的最后入口。
- 影响范围：Application on-demand build/cache gate、raw assembler、旧 cache-read helper、OA invoice-offset cache repair helper、Workbench/ETC/Cost 测试 fixture 与负向架构 guard。
- 关键决策：生产查询只读现有 active generation；Redis 仍只缓存 fresh gate 后的版本化首屏。没有新增 projection、adapter、fallback、cache owner 或 worker。OA invoice-offset 当前 relation builder 保留，并直接使用已有 `oa_attachment_matches_oa(...)` 过滤附件发票。
- 旧逻辑清理：删除同步 on-demand getter/raw assembler/cache gate 及三个专属 service module；旧 GET/cache/Mongo/row-detail fallback 测试直接删除。仍有价值的写入/UOW 测试改用 canonical row fixture，并显式隔离已由 query-facade 契约测试覆盖的 generation precondition；ETC 删除链改为断言 relation fact，不再读取旧整页 API。
- 测试覆盖：canonical personal-advance 边界、Cost relation fixture、Workbench write/UOW、ETC relation cleanup、current V2 API、SQL/query/Search 与负向删除 guard。
- 未测风险：按用户要求未部署、未访问生产数据或 token；生产 cold/hot p95/p99 留待统一发布后验证。
- 后续事项：继续删除 raw assembler 失去调用者后暴露出的 test-only live/OA/retention/grouping helper cascade，再做全量零引用与性能闭环。

## 2026-07-16 - 删除 repository generic Workbench full-view adapter

- 目标：移除当前 initial/groups/detail API 已不调用的 `get_workbench_view(...)` 兼容 DTO，防止 repository 同时维护窄查询和旧整页/rows-page 两套 owner。
- 影响范围：PostgreSQL Workbench repository、Application 无调用 persisted getter、SQL runtime tests、架构文档与删除 guard。
- 关键决策：保留 current initial/summary/groups/group detail/row detail/search/ignored/Batch Accounting 窄 I/O，以及它们共用的结构化 group member materialization；只删除 generic full-view、materialized-all snapshot view 和旧 rows-page helpers。
- 测试覆盖：删除只保护兼容 DTO 的六个测试/fakes；负向 guard 禁止 repository full-view 和 Application persisted getter 回流；current Workbench SQL/query tests 继续覆盖真实 owner。
- 未测风险：本轮不改 projection/schema/worker，不需要数据迁移；统一发布前仍需完成完整当前链性能验证。

## 2026-07-16 - 删除同步 Workbench page-cache warmer

- 目标：从 generation 发布热路径移除两次首屏 page SQL、Redis version 写和 payload 写，避免可选缓存 I/O 放大 worker handler 尾延迟。
- 影响范围：Workbench page-cache helper、worker wiring、refresh service、定向测试、监控与模块边界文档。
- 关键决策：保留现有 `WorkbenchGroupsPageCache` key/TTL 与 `WorkbenchQueryFacade` query-time versioned read-through；删除 warmer class、同步 env 开关和 publish result 的 `cache_warmup` 字段，不新增异步 event/worker。
- 一致性：Redis 仍不是 freshness 事实源；miss/down 继续读取同一 fresh SQL generation，旧 generation key 自动失效。worker publish/Cost fan-out/dirty completion 不依赖缓存。
- 测试覆盖：refresh service 证明 publish 不查询 page 且结果无 warmup 字段；静态删除 guard 防止 class/env/injection 回流；query facade 既有 cache hit/miss/down 测试保持。
- 未测风险：按用户要求未部署；真实冷 cache 首个 API 的 p95 留待统一发布后验证。

## 2026-07-16 - 删除 Workbench 全局聚合 lane

- 目标：删除已经不参与页面查询的全局 generation 聚合链路，避免维护第二个 worker、第二套发布函数和写后聚合调度。
- 影响范围：Workbench refresh service、SQL projection repository port、runtime queue、worker registry/deploy env、relation refresh producer、rehydrate script、测试与 worker/read-model 文档。
- 关键决策：保留现有 active month generation；`month=all` 继续 query-compose 月份 shard。单一 `workbench` worker 同时 claim 月份和 `all`，其中 `all` 只经现有 `ReadModelRefreshGateway` fan-out 到月份 scopes，并传播 tenant、priority、trace 与显式 force metadata；不新增 projection、aggregate lane、fallback 或兼容发布。
- 旧逻辑清理：删除全局 aggregate builder、aggregate-only handler 分支、queue helper、独立 registry/env、deploy 迁移 helper 和对应测试。relation 已知具体月份时不再额外投递 `all`。
- 测试覆盖：覆盖单 worker registry/deploy 合同、`all` fan-out 与 metadata 传播、dirty command 完成、月份发布后的成本统计 fan-out，以及旧 worker/函数删除 guard。
- 未测风险：没有部署或操作生产队列；真实 worker pickup/handler p95 留待用户统一发布后按交接门禁验证。
- 后续事项：删除页面 cache warmer，再完成 raw/on-demand 旧读链路收口。

## 2026-07-16 - 删除零调用 Workbench full-payload API assembler

- 目标：在 Search、ignored、Settings、Batch Accounting、Cost Statistics 和 Workbench write consumer 已解耦后，删除不再有生产调用者的 legacy full-page API builder。
- 影响范围：`server.py`、legacy provider/API assembler/发票库存统计模块、对应测试与 runtime boundary guard。
- 关键决策：删除 `_build_api_workbench_payload`、`WorkbenchApiPayloadAssembler`、`WorkbenchLegacyApiSqlReadProvider` 和只服务旧 DTO 的 `InvoiceInventoryStatsService`；不新增 facade/fallback，不触碰仍有 generation/write 调用的 raw/live/OA builders。
- 文档影响：模块边界明确当前首屏只由 `WorkbenchQueryFacade.initial_page(...)` 和 active generation SQL owner 提供；其他页面继续使用各自窄 I/O。
- 测试覆盖：旧实现细节单测删除；业务测试改为直接验证 active-generation/read-model 或 command 结果；删除 guard 防止 provider/assembler/wrapper 恢复。
- 验证命令：见 Phase 04 执行状态与最终交接。
- 未测风险：生产 external consumer/access-log 门禁按用户要求留到统一发布前执行；本轮不部署。
- 后续事项：继续删除 raw/on-demand page build、伪 aggregate lane 和 cache warmer。

## 2026-07-05 - 详情抽屉即时打开链路收敛

- 目标：修复关联台点击 OA 流水/发票详情 icon 时抽屉被详情请求耗时拖慢的问题，达到点击后立即从右侧出现、详情数据随后填充。
- 影响范围：`web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/test/WorkbenchSelection.test.tsx`。
- 关键决策：详情抽屉打开不再暴露可等待的 async handler；点击时先用列表行数据打开抽屉并显示加载态，再异步请求 `/api/workbench/rows/{row_id}` 替换详情。用请求序号隔离旧请求，避免快速切换或关闭后旧响应回写抽屉。不新增缓存、状态机或后端链路。
- 文档影响：本次不改变模块边界、API contract、read model、worker、权限或业务状态机；只更新本实施记录。
- 测试覆盖：更新 `WorkbenchSelection.test.tsx`，挂起 row detail 请求，断言点击后抽屉在请求完成前已可见并显示加载态。
- 验证命令：见本轮最终说明。
- 未测风险：未改变真实接口耗时；如果后端详情接口本身仍慢，只会影响详情字段填充，不再影响抽屉出现。

## 2026-07-05 - 详情抽屉与内部字段展示收敛

- 目标：将关联台 OA、银行流水、发票详情从居中弹窗改为右侧抽屉，并让详情内容按 OA 待付款核对同类详情的表格样式展示。
- 影响范围：`web/src/components/workbench/DetailDrawer.tsx`、`web/src/app/styles.css`、关联台详情相关 Vitest 和大数据 Playwright smoke。
- 关键决策：复用项目公共 `AppDrawer`，不新增 drawer 框架；详情字段仅在前端展示层过滤 Mongo 文档 ID、流程 ID、记录编号、source row id、附件识别/闭环状态等内部字段，后端/API/read model 仍保留这些字段供 OA 附件归属、支付状态和 source binding 使用。
- 文档影响：本次不改变模块边界、API contract、read model、worker、权限或业务状态机；只更新本实施记录。
- 测试覆盖：更新 `DetailDrawer.test.tsx` 覆盖表格式抽屉与内部字段隐藏；更新 `WorkbenchSelection.test.tsx` 覆盖详情抽屉打开、关闭、Escape 和 OA 附件来源字段过滤；更新 `workbench-large-scroll-flow.spec.ts` 覆盖真实浏览器下详情抽屉打开/关闭后选择状态仍可用。
- 验证命令：`cd web && npm test -- --run src/test/DetailDrawer.test.tsx src/test/WorkbenchSelection.test.tsx`；`cd web && npm run build`；`cd web && npm run e2e -- e2e/workbench-large-scroll-flow.spec.ts --project=chromium`。
- 未测风险：未跑完整 `npm run e2e:smoke`；真实生产数据中混合发票摘要可能仍包含用户不想看的附件文件哈希，当前仅移除独立内部字段和括号内长 hash 文件名。
- 后续事项：如业务确认某些银行流水号或凭证号也应隐藏，可继续把对应中文字段加入展示层过滤列表，不改后端事实源。

## 2026-07-05 - legacy `/workbench` HTTP compat 删除

- 目标：删除旧 `/workbench` 页面读入口、旧静态 prototype 和旧 `/workbench/actions/confirm|difference|exception|offline|offset` HTTP 包装层，避免旧 `ManualReconciliationService` + ledger sync 链路继续作为关联台 action 入口污染现代 `/api/workbench/actions/*` relation/read-model 链路。
- 影响范围：`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`、`tests/test_workbench_api.py`、`tests/test_ledger_api.py`、`tests/test_app.py`、`tests/test_platform_runtime_boundary_guards.py`、本模块边界 I/O 和测试矩阵。
- 关键决策：保留 `ManualReconciliationService` 与 `LedgerReminderService` 本身；它们仍有 reconciliation/ledger service 层用途。删除的是旧 Workbench HTTP compat route owner 和 entrypoints。
- 已删除：`routes_legacy_workbench_actions.py`、`Application._legacy_workbench_action_routes` 装配、`Application._handle_legacy_workbench_action(...)`、`Application._handle_workbench(...)`、`Application._handle_workbench_prototype(...)`、旧 `/workbench` / `/workbench/prototype` / `/workbench/actions/*` dispatch、prototype HTML 和 health entrypoints。
- 测试覆盖：`test_legacy_workbench_http_endpoints_stay_deleted` 防止旧 route owner/server/prototype 回流；`test_legacy_workbench_endpoints_are_removed` 断言旧 endpoint 返回 404；ledger API 测试改为 service 造数后继续验证 `/ledgers` 与 `/reminders`。
- 验证命令：见本轮最终说明。
- 未测风险：本轮未迁移后端 `/api/workbench` full payload contract。

## 2026-07-05 - legacy Workbench API action service 删除

- 目标：继续关闭关联台旧 action 逻辑污染面，把 legacy `WorkbenchApiRoutes` 从 action wrapper 降为 read-only 兼容壳，并删除旧 `WorkbenchActionService`。
- 影响范围：`backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/services/workbench_action_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_cost_statistics_api.py`、`tests/test_workbench_v2_api.py`、本模块边界 I/O 和测试矩阵。
- 关键发现：`WorkbenchActionApiRoutes` 已拥有现代 confirm/mark/cancel/update-bank-exception 写链路；成本统计回归只是借 legacy `confirm_link` 构造“已关联”的 full-payload 输入，不是成本统计边界或关联台写链路的真实调用方。
- 已删除：legacy `WorkbenchActionService` 文件、`Application._workbench_action_service` 装配、`WorkbenchApiRoutes.confirm_link(...)`，以及旧 `mark_exception`、`cancel_link`、`update_bank_exception` action surface。
- 保留为受限只读兼容合同：后端 `GET /api/workbench` full payload read compat 不进入前端页面 runtime，不拥有写 I/O；生产 SQL runtime 必须读取 active generation 并 fail closed。
- 测试覆盖：更新 `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_api_routes_are_read_only_and_action_service_deleted`，防止旧 action service 或旧 action method 回流；成本统计测试改为显式准备已关联输入，不再通过 legacy confirm 写链路造数。
- 验证命令：见本轮最终说明。
- 未测风险：后端 `/api/workbench` full payload 仍是兼容迁移面；删除它需要继续迁移依赖 full payload contract 的后端测试和调用点。

## 2026-07-05 - full payload 前端旧客户端删除

- 目标：按 Grill/Ponytail/GSD 审计结论删除关联台前端旧 full-payload 客户端，避免 `fetchWorkbench` / `fetchWorkbenchWithProgress` 继续维护 `/api/workbench?month=...` 首屏旧链路。
- 影响范围：`web/src/features/workbench/api.ts`、`web/src/test/WorkbenchApi.test.ts`、`tests/test_platform_runtime_boundary_guards.py`、本模块边界 I/O 和测试矩阵。
- 关键发现：关联台页面与导入后 fallback runtime 已经只调用 `fetchWorkbenchInitialPage` + `/api/workbench/summary` + `/api/workbench/groups`；`fetchWorkbenchWithProgress` 只剩 API 模块导出和旧 mapper 测试维护面，属于可删除旧代码。后端 `GET /api/workbench` 仍由 `WorkbenchLegacyApiSqlReadProvider` 作为兼容迁移面承接，删除后端 route 需要单独迁移仍依赖 full payload 的后端集成测试。
- 已删除：前端 `fetchWorkbench`、`fetchWorkbenchWithProgress`、旧 full-payload `mapSummary` fallback helper，以及 23 个只覆盖旧 full-payload 客户端的前端测试块。
- 后续已收口：legacy Workbench action service、旧 `/workbench` HTTP 入口和旧 prototype 已在 2026-07-05 后续步骤删除；后端 `GET /api/workbench` 保留为受限只读兼容合同。
- 测试覆盖：更新 `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_full_payload_fetcher_stays_deleted_from_frontend_runtime`，禁止前端 API 和 runtime 重新出现旧 full-payload fetcher；既有 `web/src/test/App.test.tsx` 继续断言关联台首页不请求 `/api/workbench?`。
- 验证命令：见本轮最终说明。
- 未测风险：前端旧客户端删除不等于后端 legacy route 删除；后端 `/api/workbench` full payload 仍需独立 caller-removal、API contract 和集成测试迁移后才能移除。

## 2026-07-04 - OA 自带附件发票 source binding 不可拆分

- 目标：修复关联台中父 OA、自带附件发票和银行流水在导入/repair/撤回后被拆成不同行，或父 OA+自带附件发票只停留在 display-only candidate 的问题。
- 影响范围：`WorkbenchOaAttachmentRepairContextExecutor` source binding 创建/补齐、`WorkbenchCandidateGroupingService` paired/open 分区、`WorkbenchPairRelationService` withdraw 状态转换、`WorkbenchRelationCommandService` withdraw preview/submit guard、`WorkbenchWriteFacade` withdraw preview payload、关联台 preview 弹窗测试。
- 关键决策：普通 relation 没有可恢复 history 时仍撤到无关联；OA 自带附件发票不是普通可撤销配对，而是父 OA 的 source binding。raw payload repair 发现可证明的父 OA+自带附件发票但缺 active relation 时，必须通过 relation command service 创建 `CASE-OA-ATT-<oa_row_id>`；已有 relation 缺父 OA 或缺附件时必须在同一 case 补齐并写入 immutable binding metadata。两栏 OA+自带附件发票 active relation 是不可拆 source binding，仍留在 open；补齐银行流水形成三栏，或满足显式 relation metadata requirement 后，才允许进入 paired。完整关系撤回时只撤用户新增的银行/其他关系，必须保留或重建父 OA+附件发票 active relation；纯父 OA+附件发票撤回必须返回不可提交 preview 和业务错误。
- 文档影响：已同步 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md`，并同步 `docs/modules/workbench-relations/`。
- 测试覆盖：OA attachment repair executor、candidate grouping via Workbench v2 API、pair service、relation command service、Workbench v2 API、前端 preview 弹窗均有定向回归。
- 验证命令：见本轮最终说明。
- 未测风险：本地测试无法证明生产固定 145 样本的 worker drain 和 all-scope active generation 最终一致；发布后需要按生产操作步骤验证。

## 2026-07-03 - Workbench generation payload owner 去重

- 目标：删除 Workbench 月分片 refresh 写路径里的旧 grouped payload 放大，确保 snapshot/group/group_row 三层 owner 边界清晰。
- 影响范围：`PostgresReadModelRepository.save_workbench_read_models(...)`、旧 `/api/workbench` 兼容 view、groups page/detail、成本统计 Workbench 输入；不改变 Workbench active generation、freshness gate、页面 response shape 或业务 relation 规则。
- 关键决策：`workbench_rows.payload` 是行详情 owner，但 nested `object_identity` 仲裁对象不属于 row payload；canonical identity 由 `workbench_rows` / `workbench_group_rows` 结构化 `object_identity_*` 列和行 payload 顶层字段承载。`workbench_groups.payload` 只保留组级 metadata/sort/count/`workbench_group_rows_materialized` marker；`workbench_group_rows` 只保留成员关系、过滤、排序、搜索和 object identity 结构化列；`workbench_snapshots.payload` 只保留 metadata/summary shell 和 `workbench_groups_materialized=true` marker。旧 full view、groups page/detail、成本统计需要完整组时，只能从同一 active generation 的 `workbench_group_rows + workbench_rows` 重建。
- 旧逻辑删除：refresh 写路径不得恢复 snapshot 大 JSON、group payload 成员数组、group_rows 整行 payload、group_rows member payload、nested identity 或 group_rows source_versions；`_workbench_group_row_records(...)` 和 rows/groups 遍历阶段也不再 `serialize_value(row/group)` 整行/整组后再丢弃，grouping serialization 只做顶层浅拷贝并在最终 JSON 写入 helper 才序列化。过滤、排序、搜索和 identity 仍走结构化列，完整行详情只属于 `workbench_rows.payload`。
- 文档影响：已同步本模块 `boundary-io.md`、`tests.md`，以及 `docs/modules/read-models/`、`docs/architecture/persistence-and-read-models.md`、成本统计模块状态/实施记录。
- 测试覆盖：`tests/test_workbench_sql_runtime.py` 覆盖 lightweight snapshot 旧 view 从结构化表重建、月分片/all scope payload owner 和 group-row 最小 payload；`tests/test_cost_statistics_sql_runtime.py` 覆盖成本统计从 structured member rows 读取并禁止 `jsonb_path_exists(workbench_groups.payload, ...)`。
- 生产验证：release `pscip-l4-workbench-group-row-min-20260703` 上 Workbench warmed targeted 1s direct SLO `10/10` pass，p95/max `890.808ms`；active `workbench:2026-02` snapshot/group/group_rows payload 中旧成员数组/整行字段放大计数为 `0`。
- 验证命令：见本轮最终说明。
- 未测风险：full critical grouped 1s smoke 最新仍为 `15/16` pass，`search:2026-03` handler `3087.035ms` / enqueue `3399.122ms` fail；真实 Workbench confirm/withdraw/no-OA withdraw 当前 release 写样本仍缺失。

## 2026-07-02 - batch-accounting active relation paired 分区修复

- 目标：修复 batch-accounting active relation 已写入 canonical relation 后，关联台 SQL active generation 把 `relation_mode=batch_accounting` 行发布为 open `existing_case_candidate` 的分区错误。
- 影响范围：`WorkbenchCandidateGroupingService` paired 判定、Workbench SQL projection 多 OA/多发票回归、关联台/批量账务边界文档；不改变 confirm/withdraw API shape。
- 关键决策：`batch_accounting` 是 relation mode 边界合同，不是 legacy `fully_linked` 展示 code 的别名。Grouping 层必须直接识别 active `special_metadata.source=batch_accounting` + relation code `batch_accounting` 的行作为 paired row。
- 测试覆盖：`tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_keeps_active_batch_accounting_multi_oa_invoice_relation_paired`。
- 验证命令：见本轮最终说明。
- 未测风险：需部署后用生产 1273.06 链路重建/等待 workbench fresh，并验证 `/api/workbench/groups?zone=paired` 可见。

## 2026-07-02 - matching worker relation read bridge 复核

- 目标：复核此前标记的 matching worker snapshot bridge 是否仍是生产旧链路污染面。
- 影响范围：`WorkbenchMatchingDirtyScopeWorker`、`WorkbenchMatchingOrchestrator`、`WorkbenchReconciliationEngine`、`runtime_worker_handlers.WorkbenchMatchingWorkerFactory`、模块边界 I/O 文档。
- 关键决策：当前 production worker 已走 `job.workbench_matching_dirty_scopes` claim/complete/fail，matching/orchestrator 通过 `WorkbenchMatchingRelationReadPort` 读取 canonical active relation；worker 内构造的本地 `WorkbenchPairRelationService` 来自 PostgreSQL canonical state store snapshot，用于 command/read 支撑，不是页面 full payload 或 read model legacy fallback。
- 测试覆盖：既有 `tests.test_workbench_dirty_queue_wiring.WorkbenchDirtyQueueWiringTests.test_worker_wiring_uses_decoupled_dirty_scope_runner`、`tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_workbench_matching_dirty_scopes_do_not_use_runtime_snapshot`、`tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_reference_state_writes_stay_in_python_boundaries` 覆盖该边界。
- 验证命令：见本轮最终说明。
- 未测风险：仍需持续生产 worker lag/dirty scope drain 监控；这不是旧链路删除缺口。

## 2026-07-02 - full payload 后端生产 SQL fallback 守卫

- 目标：确认并锁定 `GET /api/workbench` full payload 兼容 API 在生产 SQL read model runtime 下只能读取 SQL active generation，不能回退 `_build_api_workbench_payload(...)` raw builder。
- 影响范围：`Application._handle_api_workbench(...)`、`WorkbenchLegacyApiSqlReadProvider` 静态边界 guard、模块边界 I/O 文档。
- 关键决策：`/api/workbench` 暂时保留为兼容迁移面；生产 SQL runtime 下 repository/provider 缺失时 fail closed 为 `read_model_unavailable`，raw builder 仅允许非 SQL/legacy 模式使用。
- 测试覆盖：更新 `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_legacy_api_sql_read_provider_extraction_stays_local`，要求 `_build_api_workbench_payload(...)` 位于 production SQL runtime guard 之后。
- 验证命令：见本轮最终说明。
- 未测风险：`/api/workbench` 兼容 API 本身尚未删除；删除需要迁移仍依赖该 full payload shape 的后端集成测试和外部调用方。

## 2026-07-02 - row detail 生产 SQL runtime 旧 route fallback 关闭

- 目标：关闭 `GET /api/workbench/rows/{row_id}` 在生产 SQL read model runtime 下的 legacy route fallback，避免旧 `WorkbenchApiRoutes.get_row_detail(...)` 和旧 query service 内存记录污染新 read model/query facade 链路。
- 影响范围：`WorkbenchRowDetailApiRoutes`、`Application._build_workbench_row_detail_api_routes(...)`、row detail SQL runtime 回归测试、平台边界静态 guard、模块边界 I/O 文档。
- 关键决策：非 SQL/legacy 模式仍保留本地兼容 fallback；生产 PostgreSQL runtime 命中 ETC/live/cache/query facade 失败后直接 fail closed，不再检查 `_records_by_id` 或 route query service。
- 测试覆盖：新增 `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_production_sql_runtime_blocks_route_fallback_even_with_in_memory_record`；更新 `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_contamination_surfaces_stay_quarantined`，禁止 row detail route owner 重新接入 query service provider 或 `_records_by_id`。
- 验证命令：见本轮最终说明。
- 未测风险：后端 `/api/workbench` full payload 兼容面尚未删除；需要独立 caller-removal 证据。

## 2026-07-02 - full payload 前端 runtime 回流守卫

- 目标：防止旧 `fetchWorkbenchWithProgress` / `/api/workbench?month=...` full payload 再次进入关联台首屏或导入后 fallback 运行链路。
- 影响范围：`web/src` runtime import/call 边界、`tests/test_platform_runtime_boundary_guards.py`、本模块测试矩阵。
- 关键决策：后端 `/api/workbench` 仍作为兼容迁移面和既有集成测试入口保留；当前生产首屏闭环先用 `fetchWorkbenchInitialPage` + summary/groups API 作为唯一 runtime 主链路，并用边界守卫禁止页面/组件重新调用 full payload fetcher。
- 测试覆盖：该守卫已在 2026-07-05 升级为 `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_full_payload_fetcher_stays_deleted_from_frontend_runtime`；既有 `web/src/test/App.test.tsx` 继续断言关联台首页不请求 `/api/workbench?`。
- 验证命令：见本轮最终说明。
- 未测风险：后端 legacy route 尚未删除；后续删除需要逐步迁移仍依赖 `/api/workbench` 的后端集成测试。

## 2026-07-01 - all-scope same-case paired/open 重复 owner 修复

- 目标：修复生产 `workbench:all` 新 generation 剩余 `duplicate_row_membership` consistency failure；同一自动 decision case 在部分月份为 paired、部分月份仍有 open candidate 残留时，all 视图不能同时发布 paired/open 两份相同行。
- 影响范围：`PostgresReadModelRepository` all-scope aggregate owner suppress、`WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION`、active generation consistency。
- 生产证据：`2026-04` parent month active generation 本身 consistent 且只含 open group；`all` 聚合后同一 `case:decision:2026-04:oa_bank_exact_amount:oa-exp-2004:txn_imported_0025` 同时出现在 paired 与 open，row `oa-exp-2004`、`txn_imported_0025` 触发 `duplicate_row_membership count=2`。同 case 的 active relation 已存在，且 2025-11/2025-12 shard 有 visible paired group。
- 关键决策：all aggregate 必须区分 visible paired group claim 与 canonical relation extra claim。visible paired group 是 strict owner，必须从 open 删除相同 row；same-case canonical relation 例外只用于没有 visible paired group、但 partial relation 仍需要 `case:<case_id>` open 展示的场景。
- 文档影响：更新本模块 boundary I/O、状态机、测试矩阵和本实施记录。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests.test_repository_all_scope_visible_paired_group_wins_over_same_case_open_candidate`，并保留 canonical open 保护测试。
- 验证命令：见本轮最终说明。
- 未测风险：需要部署后重建 `workbench:all`，确认 `duplicate_row_membership` 和 `active_relation_open_membership` 均为 0，并跑 API 耗时 smoke。

## 2026-07-01 - Workbench emergency retention 参数补齐

- 目标：补齐生产根分区 99% 且当天 superseded generation 堆积时的受控清理入口，避免 Workbench refresh 因磁盘不足持续失败。
- 影响范围：`PostgresReadModelRepository.preview_workbench_generation_retention(...)`、`fin_ops_platform.tools.prune_workbench_generations` 和 runtime worker 运维文档。
- 关键决策：默认 retention 保留每个 scope 最近 1 个非 active generation，其余当天 superseded/failed generation 也允许删除。repository 删除仍限定 `status <> 'active'`，不触碰 `app.*`、`job.*` 或业务事实表。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md`，记录 `--keep-days 0` 是默认策略，并修正 `workbench_generation_stats` 表名。
- 测试覆盖：新增 CLI 显式 `--keep-days 0` 合同测试和 repository preview 参数传递测试。
- 验证命令：见本轮最终说明。
- 未测风险：需要部署后执行 emergency prune、普通 `VACUUM (ANALYZE)`、重建 `2026-06`/`all` active generation，并跑生产 read/API smoke。

## 2026-07-02 - Workbench retention 生产 wrapper 漂移修正

- 目标：消除生产 `/usr/local/sbin/finops-prune-workbench-generations` 手写 wrapper 与 repository/CLI retention 策略不一致的问题，避免新代码默认 `keep_days=0` 被旧 wrapper 的 `keep_days=1`、`keep_recent=3` 覆盖。
- 影响范围：`deploy/oa/bin/finops-prune-workbench-generations.sh`、`deploy/oa/systemd/finops-prune-workbench-generations.*.example`、`deploy/oa/bin/finops-deploy-control.sh`、`scripts/deploy_oa.py`、runtime worker 运维文档和部署测试。
- 关键决策：Workbench generation retention 的生产入口必须版本化；release activate 时由 deploy-control 安装 helper/service/timer 并 enable timer。部署脚本 contract 会拒绝不支持 `install_workbench_generation_retention` 的旧 deploy-control，避免生产继续运行漂移脚本。
- 文档影响：更新 `docs/operations/runtime-worker-governance.md`、`docs/operations/postgresql-runtime.md` 和本模块测试矩阵。
- 测试覆盖：新增/更新 `tests/test_deploy_runtime_examples.py` 与 `tests/test_deploy_oa_script.py`，固定 wrapper 默认值、timer 安装链路和旧 deploy-control 拒绝合同。
- 验证命令：见本轮最终说明。

## 2026-07-01 - 跨月 active relation 月度投影漏读修复

- 目标：修复生产 `workbench:all` / `2026-06` 卡在 `active_relation_open_membership` consistency failure，导致关联台持续 refreshing、Load 变慢的问题。
- 影响范围：`WorkbenchSqlProjectionBuilder._active_pair_relations_for_month(...)`、Workbench SQL projection schema version、月度 active generation 重建和 all aggregate。
- 真实原因：生产样本显示 active relation 的 `month_scope` 可落在 2026-04/2026-05，但 relation 内的 invoice、OA 或 bank row 属于 2026-06 等其它月份。旧月度投影查询同时要求 `month_scope = 当前月` 和 `row_ids && 当前月源行`，把这些跨月 relation 漏掉；对应 row 继续按普通 open/temp group 发布，consistency checker 正确报 `active_relation_open_membership`。
- 关键决策：月度 Workbench 投影读取 active relation 时以 `row_ids && 当前月行集合` 为边界，去掉 `month_scope` 过滤；`month_scope` 只是 relation 创建归属，不是跨月成员投影范围。保留 `row_ids` GIN overlap 约束，不新增缓存或新 worker。同步 bump `WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION=2026-07-01-cross-month-active-relation-v1`，让旧 active generation 按 schema mismatch 重建。
- 文档影响：更新本模块实施记录、状态机、测试矩阵和 GSD planning 记录。
- 测试覆盖：新增 `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_reads_cross_month_active_relations_by_row_overlap`；既有 grouping/consistency 测试继续覆盖 relation 进入投影后必须进入 canonical `case:<case_id>` group 或合法 paired group。
- 验证命令：见本轮最终说明。
- 未测风险：需要部署后由 worker 重建生产 `2026-06` 和 `all` scope，再验证 `active_relation_open_membership` 清零、App Health 收敛和首屏 p95。

## 2026-07-01 - 关联台 Load 热路径收窄和生产 retention 证据

- 目标：按 GSD 主控 prompt 闭环分析并执行关联台首屏读取性能第一轮修复，优先消除请求线程内热路径重算和过宽 summary payload，同时用生产只读证据定位同步慢的真实阻塞。
- 影响范围：`PostgresReadModelRepository.get_workbench_summary(...)`、groups summary compaction、导入后 Workbench fallback 刷新、Workbench generation retention 工具和 runtime-worker 运维文档。
- 关键决策：`read_model.workbench_summary` 是 summary 读路径唯一事实源；缺 summary 时返回未完成，由 query facade/freshness 边界入队刷新，禁止在 API 请求内 join `workbench_group_rows` 或读取 `app.invoices` 补算。groups `detail_level=summary` 只输出首屏 UI 必需字段，剔除 `searchable_text`、debug/source/object identity、decision evidence 等重字段。生产 retention 收紧为每 scope 保留 1 个非 active generation、超过 1 天可删、每批最多 500，且永远不删 active generation。
- 生产证据：2026-07-01 生产 profiling 显示 `groups open summary page1` 响应约 2.2MB，其中 group `searchable_text` 约 1.26MB；根分区一度 100%，Workbench read model generation/TOAST 膨胀导致 `No space left on device`。已在生产执行 systemd journal 限额、一个 bounded 非 active generation 删除批次和普通 `VACUUM (ANALYZE)`，空间恢复到可继续诊断状态。
- 剩余阻塞：生产 `workbench:all` 与 `2026-06` 仍为 `refreshing`，当前 blocker 已从满盘转为 active generation consistency failure：`active_relation_open_membership`。下一轮必须定位 relation/projection 分区一致性，不能继续盲删 read model 行，也不能把旧 failed/dirty 状态手工改 fresh。
- 文档影响：更新本模块 `boundary-io.md`、`tests.md`、本实施记录、`docs/operations/runtime-worker-governance.md` 和 GSD planning 记录。
- 测试覆盖：新增/调整 Workbench SQL runtime 测试，覆盖 summary 只读物化结果、summary 缺失不热路径 repair、groups summary 重字段裁剪、retention CLI 默认合同；前端导入 fallback 改为 `fetchWorkbenchInitialPage(...)`，沿用 Workbench API 测试保护兼容面。
- 验证命令：见本轮最终说明。
- 未测风险：本地代码尚未部署到远程生产；生产 API p95、浏览器首屏可交互时间、Redis cache-hit/cold-cache 对比和 read_model enqueue-to-fresh 仍需部署后 smoke。生产剩余 `active_relation_open_membership` 一致性失败需要下一条 GSD prompt 专项修复。
- 后续事项：执行下一条主控 prompt：先修复 active relation open membership 一致性，再部署并跑生产 smoke；之后再删除 `/api/workbench` full payload、row detail legacy fallback，并复核 matching worker relation read bridge。

## 2026-06-30 - 自动匹配正式化和关系二态口径

- 目标：把关联台用户关系状态收敛为正式配对关系和无配对关系，取消“候选 OA/候选关系”作为下游业务状态。
- 影响范围：`WorkbenchReconciliationEngine`、matching orchestrator、decision store、relation SQL projection、withdraw/split copy、Workbench/Open 下游 E2E 和模块文档。
- 关键决策：free paired decision 满足金额 matched、无 active 冲突、同 row-set 未被撤回后直接通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写入 active relation；用户撤回过的 row-set 不再自动重新配对；未正式化 decision 只留在自动匹配内部，不再分发给待找发票、OA 待付款、进项/销项、银行明细等下游页面。
- 文档影响：同步 workbench-relations、reconciliation-workbench、产品规格、API contract、read model 边界和相关下游模块测试说明。
- 测试覆盖：`test_workbench_reconciliation_engine.py` 覆盖自动正式化和撤回抑制；`test_workbench_reconciliation_decision_store.py` 覆盖 suppressed decision 不复活；`test_workbench_relation_sql_projection.py` 覆盖 open decision 不再分发。
- 验证命令：见本轮最终说明。
- 未测风险：真实生产历史 active generation 需要发布后由 worker 重建收敛；本地已覆盖服务、API、前端和 deterministic Browser 回归。

## 2026-06-30 - 折叠批次计数文案重叠修复

- 目标：修复关联台折叠银行流水行中“当前显示 1 条摘要 / 实际 N 条流水”与日期、标签、摘要文字重叠的问题。
- 影响范围：`CandidateGroupGrid` 折叠控制渲染和样式；不改变后端 relation payload、workbench 分区、展开明细或确认/撤回逻辑。
- 关键决策：删除旧的绝对定位计数文案和 `.candidate-group-collapse-counts` 样式，只保留“展开 N 条/张明细”按钮作为入口；按钮文本已表达总明细数，额外文案属于重复信息且在表格行高内易重叠。
- 测试覆盖：`web/src/test/CandidateGroupGrid.test.tsx::renders bank-flow summary rows without overlapping collapsed count copy` 覆盖 `bank_flow_rule_batch` 折叠行不再渲染旧计数文案；原 no-OA/ETC 折叠测试同步断言旧文案不存在。
- 验证命令：`npm test -- --run src/test/CandidateGroupGrid.test.tsx`；`npm run build`。
- 未测风险：未跑浏览器截图回归；当前风险由组件测试和 build 覆盖，真实大屏/缩放视觉仍建议发布后抽查。

## 2026-07-06 - 折叠批次只展示完整明细

- 目标：修复已配对区 `bank_flow_rule_batch` 折叠摘要点击“展开 N 条明细”后，summary payload 的轻量/占位 `collapsed_rows` 被直接展开成 `-- / 待处理 / --` 明细的问题。
- 影响范围：`CandidateGroupGrid` 折叠摘要交互；不改变 Workbench group detail API、read model freshness gate、relation payload 或确认/撤回逻辑。
- 关键决策：移除 `collapsed_summary` 跳过预取的旧特判，改为按 `collapsedRows` 当前数量与后端总数判断是否需要补全；用户点击截断摘要时先保持摘要态并显示加载中，完整 group detail 成功写回后再展开，失败时保持折叠，由页面级 handler 暴露加载错误。
- 测试覆盖：`web/src/test/CandidateGroupGrid.test.tsx::auto-loads complete collapsed summary detail when summary response truncates collapsed rows`、`web/src/test/CandidateGroupGrid.test.tsx::waits for full collapsed detail before expanding truncated summary rows`、`web/src/test/CandidateGroupGrid.test.tsx::keeps truncated collapsed summary closed when full detail loading fails`。
- 验证命令：见本轮最终说明。
- 未测风险：未跑真实浏览器生产数据点击 smoke；组件测试覆盖 UI 状态和 detail 失败路径。

## 2026-06-24 - Workbench compute 生产证据门延期

- 目标：执行 `go-hot-path:workbench-compute-production-evidence-gate`，在不部署、不拷贝代码、不写生产数据、不输出 secret 的前提下，尝试收集 Workbench matching/grouping/check 的生产只读性能证据。
- 影响范围：Go hot-path admission、Workbench compute evidence、autonomous state/queue/next prompt；未改变 Workbench API、UI、matching 规则、relation 写入或 read model 刷新行为。
- 关键决策：本 slice 记录为 `production-evidence-deferred`，不是 admission 通过。原因是本地 collector 返回结构化 `configuration_missing`，生产当前 release 未部署 `workbench_compute_evidence.py`，且使用已部署 runtime/env 的只读 PostgreSQL 采样尝试无法建立连接。`go-hot-path:workbench-compute-admission` 继续 `blocked-by-prerequisite`。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-production-evidence-gate.md`，更新 autonomous state/queue/next prompt 和主控 prompt。
- 测试覆盖：更新 `tests/test_platform_runtime_boundary_guards.py`，要求生产证据门为 deferred、Go admission 继续 blocked、下一 prompt 禁止 Go 实现并回到安全边界选择。
- 验证命令：`env -u FIN_OPS_POSTGRES_DATABASE_URL -u DATABASE_URL PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.workbench_compute_evidence --json`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_compute_evidence tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v`；`bash scripts/verify.sh docs`；`git diff --check`。
- 未测风险：真实生产 Workbench p95/p99、row-count、candidate/decision、heartbeat、query timing、enqueue-to-fresh 和 shadow diff 仍缺失；Go/Fiber/Go Worker 仍不得开始实现。
- 后续事项：执行 `planning:post-workbench-compute-evidence-gate-next-boundary-selection`，从现有 roadmap/queue 中选择下一个非阻塞边界。

## 2026-06-24 - Workbench compute 性能证据 collector

- 目标：在 Go/Fiber/Go Worker admission 前补齐 `workbench:matching-grouping-check` 的只读性能证据采集路径，避免在缺少真实 p95/p99、heartbeat、row-count 和 query timing 证据时误启动 Go 实现。
- 影响范围：新增 `fin_ops_platform.tools.workbench_compute_evidence` 和对应 fake-connection 单元测试；不改变 Workbench matching、active generation、relation command、API、worker 或前端行为。
- 关键决策：collector 只读 `job.workbench_matching_dirty_scopes`、`job.runtime_worker_heartbeats`、`job.outbox_events`、`read_model.workbench_group_rows`、candidate/decision 表和 `pg_stat_statements`；缺 PostgreSQL 配置时返回结构化 `configuration_missing`，证据为空或不完整时返回 `partial` 并保持 Go admission blocked。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-evidence-collector-contract.md`，更新本模块测试矩阵和 autonomous state/queue/next prompt。
- 测试覆盖：新增 `tests/test_workbench_compute_evidence.py`，覆盖证据字段汇总、只读 SQL 约束、缺证据不放行 admission、缺 PG 配置结构化报告；同步更新 `test_workbench_compute_go_shadow_admission_remains_guarded`，使其继续断言 collector closed、production evidence gate pending、Go admission blocked。
- 验证命令：`python3 -m py_compile backend/src/fin_ops_platform/tools/workbench_compute_evidence.py`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_compute_evidence -v`；本 slice 最终还会运行 SLO/guard 回归、docs verify 和 `git diff --check`。
- 未测风险：未连接真实生产 PostgreSQL；真实 Workbench matching p95/p99、dirty-scope lag、worker heartbeat、active generation enqueue-to-fresh、CPU/内存和 high-row evidence 仍需下一条只读生产证据 gate。
- 后续事项：执行 `go-hot-path:workbench-compute-production-evidence-gate`；若无法安全获得真实 evidence，记录 `production-evidence-deferred`，不得进入 Go admission。

## 2026-06-24 - Workbench compute Python reference 守卫

- 目标：在 Go admission 前增加本地可执行守卫，锁定 Workbench compute 的 Python reference 状态写边界和 Go shadow forbidden-write 合同。
- 影响范围：`tests/test_platform_runtime_boundary_guards.py`、Go hot-path planning state；不改变 Workbench runtime、matching 规则、active generation、relation command、API 或前端行为。
- 关键决策：Python dirty worker/orchestrator/engine 仍是权威状态写边界；shadow compute 只能比较非权威输出，不能 claim/ack/complete/fail dirty scope，不能写 outbox/readiness/Redis/active generation/candidate/decision/relation/audit。`go-hot-path:workbench-compute-admission` 继续 blocked。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-python-reference-contract-guards.md`，并更新 autonomous state/queue/next prompt。
- 测试覆盖：新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_compute_reference_state_writes_stay_in_python_boundaries` 和 `test_workbench_compute_go_shadow_admission_remains_guarded`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_reference_state_writes_stay_in_python_boundaries tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded tests.test_workbench_matching_dirty_scope_worker tests.test_workbench_matching_orchestrator tests.test_workbench_reconciliation_engine -v`。
- 未测风险：本 slice 仍不采集真实 PostgreSQL/worker/App Status/high-row/browser/CPU/内存性能证据；下一步应补 read-only evidence collector contract/tooling。
- 后续事项：执行 `go-hot-path:workbench-compute-performance-evidence-collector-contract`，先补性能证据采集合同，再考虑 admission review。

## 2026-06-24 - Go hot path Workbench compute 准入合同

- 目标：在任何 Go/Fiber/Go Worker 实现前，先定义 `workbench:matching-grouping-check` 的 Python reference IO、性能基线、shadow-run、rollback 和 forbidden-write 合同。
- 影响范围：规划和准入合同；不改变 Workbench runtime、matching 规则、active generation、relation command、API 或前端行为。
- 关键决策：Workbench compute 当前不是单一纯函数。生产参考边界包括 `WorkbenchMatchingDirtyScopeWorker.run_once()`、`WorkbenchMatchingOrchestrator.run(...)`、`WorkbenchMatchingRules.generate_candidates(...)`、`WorkbenchFreeMatchingEngine.generate_decisions(...)`、`WorkbenchReconciliationEngine.run_scope(...)` 和 `WorkbenchAmountCheckService.check(...)`。Go shadow 只能使用同一输入生成非权威输出，禁止 claim/ack/complete/fail dirty scope，禁止写 outbox/readiness/Redis/active generation/candidate/decision/relation/audit。
- 文档影响：新增 `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-performance-baseline-contract.md`，并更新 autonomous state/queue/next prompt。模块状态定义不变；Go admission 仍 blocked。
- 测试覆盖：本 slice 不改运行时代码；以现有 Workbench matching/orchestrator/dirty worker/amount check/SLO 测试作为证据。下一 slice 应增加或收紧 reference-contract guard。
- 验证命令：本 slice 最终验证记录在提交说明和 autonomous journal。
- 未测风险：未连接真实 PostgreSQL、未采集生产 high-row matching p95/p99、CPU/内存、dirty-scope lag、shadow diff 或真实 authenticated HTTP SLO；这些都是 Go admission 前置证据，不是本 planning slice 的完成条件。
- 后续事项：执行 `go-hot-path:workbench-compute-python-reference-contract-guards`，先冻结本地 reference IO 和 shadow forbidden-write 合同，再决定是否允许 admission review。

## 2026-06-23 - Amount-check query contract 守卫

- 目标：锁定关联预览金额核对的输入优先级，防止新 read/query payload 已有 `reconciliation_amount` 时，被旧 `detail_fields.明细金额合计` fallback 反向覆盖。
- 影响范围：`WorkbenchAmountCheckService` 的 OA 金额取值合同；不改变 Workbench 业务状态、UI 状态、read model 状态、worker、SQL、API shape 或前端展示。
- 关键决策：`reconciliation_amount` 是新链路的可付款/可核销金额字段，必须优先；`detail_fields.明细金额合计` 只保留为旧 read model compat-only fallback，且只在显式字段缺失时使用。
- 文档影响：同步本模块 tests、state-machine、本实施记录，并在 `.planning/refactors/modular-io-boundaries/analysis/reconciliation-workbench-amount-check-query-contract.md` 记录全局/模块状态机 definition unchanged。
- 测试覆盖：新增 `tests/test_workbench_amount_check_service.py::WorkbenchAmountCheckServiceTests::test_explicit_reconciliation_amount_wins_over_legacy_detail_mismatch_fields`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_amount_check_service -v`；本轮最终验证还会覆盖 app check、docs check、diff/secret scan。
- 未测风险：本轮不连接生产 PostgreSQL，不回放真实 Workbench active generation；因为没有 runtime 行为或 read model 发布变更，生产验证不作为本 slice 完成条件。
- 后续事项：推进 `batch-accounting:legacy-route-contract`，聚焦旧 route/server.py 写链路和 Workbench relation fan-out 边界。

## 2026-06-23 - all scope 保留被 open owner 剥离后的未认领银行流水

- 目标：修复月分片中存在 `case:decision:*` 自动决策 open group，但 all scope 聚合后其中未被任何其他 group 认领的银行流水消失的问题。
- 真实原因：all-scope 聚合先按 open group owner 规则去重；当另一个更强 open group 拿走同一 OA row 后，自动决策 group 变成 partial。旧逻辑在“open group 之间去重”后也调用 `_drop_partial_all_scope_automatic_decision_group`，把剩余未被认领的银行流水一起清空。`txn_imported_1419` 属于该形状：`oa-pay-2068` 被 3 月 open group 拿走，4 月自动决策 group 里的银行流水没有其他 owner，却随 partial group 被清空。
- 影响范围：`PostgresReadModelRepository` all-scope aggregate 的 open-group 去重；paired shard/正式 relation 抢占时清空自动决策残片的保护保持不变。
- 关键决策：open group 之间的 owner 去重只移除被更强 open group 明确拥有的 row，不再清空自动决策 group 中剩余未被认领的事实行；当 paired group 或 canonical active relation claim 抢占 row 时，仍清空 partial automatic decision group，避免已配对流水回流到 open 区。
- 文档影响：同步本实施记录和 `tests.md`；产品口径不变，仍以 active all generation 为 all 视图事实源。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_keeps_unclaimed_bank_when_open_group_takes_automatic_decision_oa`，并保留 `test_repository_all_scope_drops_partial_automatic_decision_groups_claimed_by_paired_shards`。
- 验证命令：本轮最终说明列出完整命令。
- 未测风险：本地测试使用 synthetic active month shard；生产需要通过正式 Workbench refresh 重建 affected month/all active generation 后再确认 all 视图数量。

## 2026-06-23 - OA 附件 source-linked 三栏闭合分区修复

- 目标：修复截图中 OA、银行流水和多张 OA 附件发票三栏金额已经闭合，且页面显示“自动匹配”，但整组仍停留在未配对区的问题。
- 真实原因：`WorkbenchCandidateGroupingService` 的分区顺序先把 paired/open rows 分开，再从 open candidate context 中抽取 OA 附件 source-linked group。抽取过程把父 OA 和附件发票移到 `source_linked` open 证据组，银行流水留在原 candidate case；即使后续发票回挂后已经形成完整三栏，`source_linked` 在 `_split_promoted_and_candidate_groups()` 中被无条件留在 open，导致架构上无法进入 paired。
- 影响范围：关联台 grouping service 的 open/paired 分区、OA 附件发票父 OA 回挂、候选 case 三栏闭合展示；不改变发票池事实源、不改变 `app.workbench_pair_relations` confirmed fact 语义、不在前端做本地移动。
- 关键决策：source-linked 只是父 OA 归属证据的中间态，不是最终分区状态。抽取 OA 附件 source group 后，如果同一候选 case 中存在唯一银行流水，且 1 条 OA、1 条银行流水与 1 张或多张 OA 附件发票含税合计闭合，则把银行纳入该 source group 并重新执行 auto-close promotion。没有银行、金额不闭合或多个银行候选时仍保持 source-linked open。该变更属于 Workbench SQL projection/grouping 行为变化，必须 bump month projection 和 all-scope aggregate builder source version，避免旧 active generation 继续被当作 fresh。
- 文档影响：同步 README、state-machine、tests 和本实施记录。
- 测试覆盖：`tests/test_workbench_candidate_grouping.py::WorkbenchCandidateGroupingTests::test_candidate_case_oa_attachment_invoices_promote_with_matching_bank` 覆盖截图同构场景；既有 `test_oa_attachment_source_groups_248_oa_with_three_attachment_invoices_open`、`test_keeps_oa_and_multiple_invoices_open_when_bank_transaction_is_missing` 继续保护缺银行时不误进 paired。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping -v`、`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_sql_source_versions_include_matching_rules_version_for_freshness -v`。
- 未测风险：本地复现使用截图同构 payload，不直接读取生产登录态 Workbench API；发布后需要确认 Workbench month/all refresh worker 已重建 active generation，页面才会从旧 open generation 收敛到 paired。
- 后续事项：所有“回挂/补投影后变完整”的流程都应在后端 grouping 层重新走 paired/open policy，不能只在来源归属阶段修改 group_type。

## 2026-06-23 - 三栏 exact-sum 自动配对矩阵补齐

- 目标：把现有三栏自动配对从枚举式补丁补全为通用 exact-sum 证据闭环，覆盖截图中的 3 条 OA 合计 4450 + 1 条流水 4450 + 1 张发票 4450，以及单 OA 单流水多发票、多 OA/多流水/多发票等同类场景。
- 真实原因：前一版规则已补齐银行+发票 anchor 和两栏 active relation 补第三栏，但仍主要围绕 `1:1:1`、单 OA-bank 入口和多 OA-bank pair 到单发票这几类形状展开；缺少对“任意非空 OA 组、银行组、发票组总额相等”的通用搜索和证据图校验，因此多 OA 合计到单流水单发票、`1:1:N` 或 `N:M:K` 仍可能留在未配对。
- 影响范围：`WorkbenchFreeMatchingEngine` 三方候选生成、`workbench_matching_rules_version` freshness、matching dirty scope 自愈、关联台三栏 automatic decision，以及普通两栏 `manual_confirmed` active relation 自动补齐升级。
- 关键决策：保留现有具体规则优先级，不改变已有自动配对逻辑；新增 `oa_bank_invoice_exact_sum` 只作为补充规则。通用规则要求三栏同方向、五个月窗口、总额严格相等、预约付款日期兼容、正式发票非 OA 附件来源、每栏组合大小受上限保护、证据图连通且每个 row 至少有一条确定性边；仅金额相等、候选组合过多、证据断裂或多个候选竞争时 fail closed，保持 open/conflict。不使用 NLP，字段空格通过确定性归一化处理。
- 文档影响：同步本模块 README、state-machine、tests、implementation notes，以及 `workbench-relations` 事实源边界。
- 测试覆盖：新增多 OA 合计到单流水单发票、单 OA 单流水多发票无直接 OA-bank 文本、多 OA/多流水/多发票证据连通、金额-only 不提升三栏，以及多 OA+单流水 active relation 自动补齐发票的回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_reconciliation_engine -v`。
- 未测风险：自动配对不能也不应该保证所有“人眼觉得像”的场景都自动配；缺少确定性业务证据、金额不闭合、发票方向未知、组合超过边界或存在歧义时仍会留在 open。发布后仍需生产 worker 按新 rules version 重建 matching decision 和 Workbench month/all active generation。
- 后续事项：后续新增截图样例时，先归类为“已有 exact-sum 证据闭环被漏掉”还是“缺少可审计证据”；前者补规则/字段别名，后者保留人工确认或引入明确业务字段，不用 NLP 猜测。

## 2026-06-23 - 三方自动配对补齐银行发票 anchor 和空白字段归一

- 目标：修复截图中 OA、银行流水和发票金额一致且三方业务证据存在，但仍停留在未配对区的问题；同时处理字段里误输入空格导致自动配对证据读取失败的情况。
- 真实原因：三方 free matching 主要从 OA+银行强匹配进入，再找发票；当真实强证据边是银行+发票，且 OA 通过 OA+发票或文本证据可唯一补齐时，旧规则没有反向生成三方 `oa_bank_invoice` decision。另一个问题是 `row.data.get("counterparty_name") or row.data.get("counterparty")` 这类写法会把 `" "` 当成有效值，挡住后备字段，导致截图三 OA 栏可见空格时 matching 读不到真实对方名。
- 影响范围：`WorkbenchFreeMatchingEngine` 三方候选生成、文本 token 提取、`workbench_matching_rules_version` freshness、自愈重跑 completed matching scopes、关联台自动三栏 decision 与两栏 active relation 补齐升级。
- 关键决策：不引入 NLP；使用确定性文本归一化和空白缺失判断。新增银行+发票强证据 anchor，只允许补齐唯一一个具备 OA-银行或 OA-发票业务证据的 OA；仅金额相同的 OA 保持 open，避免误配。规则版本 bump 到 `2026-06-23-three-way-completion-v2`，让生产 worker 自动重投旧版本 completed scope。
- 文档影响：同步本模块 README、state-machine、tests、implementation notes，以及 `workbench-relations` 事实源边界。
- 测试覆盖：新增空白字段 fallback、银行+发票 anchor 补三方、金额-only 不提升三方三个核心回归；同时运行 free matching、legacy matching rules、reconciliation engine、matching orchestrator 和 matching dirty scope worker 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_rules tests.test_workbench_reconciliation_engine tests.test_workbench_matching_orchestrator tests.test_workbench_matching_dirty_scope_worker -v`；`python3 -m py_compile backend/src/fin_ops_platform/services/workbench_free_matching_engine.py backend/src/fin_ops_platform/services/workbench_matching_rules.py`。
- 未测风险：本地未直接连接生产数据库执行 worker drain；发布后需要确认 `workbench-matching` worker 已按新 rules version 把旧 completed scopes 转 dirty，并刷新 Workbench month/all active generation。
- 后续事项：若以后新增 invoice type、OA 字段别名或银行对方字段别名，必须先补充 `_first_text` 后备字段和规则测试；未知字段仍 fail closed。

## 2026-06-23 - ETC summary 优先读取 batch invoice links

- 目标：完成 Phase C 读取路径迁移，让关联台 ETC summary 优先以 `app.etc_batch_invoice_links` + canonical `app.invoices` 生成明细，避免 `app.etc_invoices` 与统一发票池长期竞争为发票事实源。
- 影响范围：`WorkbenchSqlProjectionBuilder._etc_invoice_summary_rows`、历史 submitted ETC summary、open invoice 排除和 Phase C backfill 工具。
- 关键决策：先读 active link table，再用旧 submission/biz ETC metadata 路径补充尚未 backfill 的历史数据；同一发票 identity 去重时 link table 先占位。删除旧 fallback 前必须先完成生产 backfill 和 smoke。
- 文档影响：同步 ETC 模块、发票池清理 runbook 和 Phase 18 GSD。
- 测试覆盖：`tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_etc_invoice_summary_rows_prefer_link_table_source` 断言 link table 是 ETC summary 的优先来源。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_etc_invoice_summary_rows_prefer_link_table_source -q`。
- 未测风险：未重建生产 active generation；发布后需刷新受影响 Workbench month/all scope 并回看截图中 ETC 批次。
- 后续事项：生产 `app.etc_batch_invoice_links` 覆盖所有 submitted 批次后，规划移除旧 ETC metadata summary fallback。

## 2026-06-23 - ETC batch invoice links 接入 open invoice 排除

- 目标：让关联台优先以 `app.etc_batch_invoice_links` 判断 ETC 批次归属，避免继续依赖 `app.etc_invoices` 与正式发票身份 join 作为长期事实源。
- 影响范围：`WorkbenchSqlProjectionBuilder._submitted_etc_overlap_exclusion_sql`、Phase 18 migration/repository/service，以及现有 ETC summary 兼容路径。
- 关键决策：Phase B 只把 link table 作为普通 open invoice row 的排除事实源，并保留旧 `app.etc_invoices` fallback；ETC summary 读取仍在 Phase C 迁移，避免一次性改动 summary 展开、relation metadata 和历史批次回放。
- 文档影响：同步测试矩阵和 Phase 18 记录。
- 测试覆盖：`tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_invoice_rows_excludes_visible_formal_invoices_already_bound_to_submitted_etc_batches` 现在同时要求 SQL 包含 `app.etc_batch_invoice_links` 与旧 ETC fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests -q`。
- 未测风险：尚未把 `_etc_invoice_summary_rows` 的事实源切到 link table，也未重建生产 active generation。
- 后续事项：Phase C backfill 后迁移 ETC summary 读取路径，再跑 Workbench rebuild/smoke。

## 2026-06-23 - submitted ETC 批次重叠发票 open 区防线

- 目标：即使历史 ETC metadata 尚未完全迁入统一 link table，也要阻止已属于 submitted/manual-submitted ETC 批次的正式发票作为普通 open invoice row 出现在关联台，避免截图中的同一真实发票双行。
- 影响范围：`WorkbenchSqlProjectionBuilder` 的 open invoice SQL、row-by-id SQL、ETC summary 与正式发票并存场景，以及 Phase 18 dry-run 修复工具的 Workbench scope enqueue。
- 关键决策：Phase A 的 SQL 防线只排除 submitted/manual-submitted/closed ETC business batch 下严格同身份的 canonical 发票 open 行，不改变 `etc_invoice_summary` 的生成逻辑；这保证历史批次仍能作为汇总发票展示，但同一真实发票不会在普通进项发票列再次出现。Phase B 会把排除事实源从 `app.etc_invoices` 迁到 `app.etc_batch_invoice_links`。
- 文档影响：同步本模块测试矩阵和 Phase 18 GSD 审计记录。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_invoice_rows_excludes_visible_formal_invoices_already_bound_to_submitted_etc_batches`，断言 open invoice SQL 包含 submitted ETC overlap 排除条件。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests -q`。
- 未测风险：未在生产执行 repair apply；当前真实库 dry-run 仅证明待处理 row set 和受影响 Workbench scopes。
- 后续事项：Phase B 新增 `app.etc_batch_invoice_links` 后，Workbench open invoice 排除和 ETC summary 都应改读 link table。

## 2026-06-23 - 发票方向归一化修复英文 output 伪冲突

- 目标：修复生产中英文 `invoice_type=output` 销项发票被自动匹配当作支出侧发票，导致正确 OA + 银行流水 + 进项发票三方闭合被 `multiple_three_way_candidates` 伪冲突挡住的问题。
- 真实原因：`WorkbenchFreeMatchingEngine`、legacy `WorkbenchMatchingRules`、special matching 和 candidate grouping 等路径都用“发票类型包含中文 `销` 则收入，否则支出”的本地判断；生产正式发票事实源实际存储 `input/output`，因此 `output` 被误判为支出侧，且 legacy counterparty 选择也会把销项发票错误按卖方匹配。
- 影响范围：新增 `workbench_invoice_direction` 统一 helper；接入 free matching、legacy matching、special rule detectors/service、candidate grouping 和 amount check；bump `workbench_matching_rules_version` 为 `2026-06-23-invoice-direction-normalization-v1`，由 matching dirty scope source-version 自愈触发生产重建。
- 关键决策：`input`、`进项*` 和 `source_kind=oa_attachment_invoice` 归为支出侧；`output`、`销项*` 归为收入侧并使用买方作为收入流水匹配对方；未知发票类型 fail closed，不再默认支出。OA 附件发票来源是已有受控输入事实，缺 `invoice_type` 时仍按 input 处理以保留附件三方闭合。
- 文档影响：更新本模块 README、state-machine、tests 和本实施记录；GSD quick prompt 落在 `.planning/quick/20260623-workbench-invoice-direction-normalization/`。
- 测试覆盖：新增生产事故形状回归、英文 output 收入流水配对、unknown fail closed、legacy counterparty 英文 output、reconciliation decision 持久化和 amount check unknown 防静默 matched 测试；同时运行 candidate grouping、matching orchestrator、matching dirty scope worker 与 dirty queue 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_rules tests.test_workbench_reconciliation_engine tests.test_workbench_amount_check_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_candidate_grouping tests.test_workbench_matching_orchestrator -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_dirty_scope_worker tests.test_workbench_reconciliation_dirty_queue -v`。
- 未测风险：未在本地执行真实生产 worker 写入重建；发布后需由常驻 `workbench-matching` worker 按新规则版本把 completed scope 重投 dirty，再刷新 Workbench active generation。不得手工改 decision 表替代重建。
- 后续事项：如未来导入层新增 `sales_invoice`、`purchase_invoice` 之外的新枚举，必须先扩展统一 helper 和测试；未知枚举保持 fail closed。

## 2026-06-23 - 多 OA 大组缺 source 时按唯一金额分段展示

- 目标：修复关联台已配对大组内缺少 `sourceOaId` 的 OA、银行流水和发票没有同排的问题；例如 29350 OA 应与 29350 流水/发票同行，88050 OA 应与两条合计 88050 的流水同行。
- 真实原因：`buildWorkbenchGroupDisplaySegments` 只在银行/发票 row 带有效 `sourceOaId` 且可归一到组内 OA 时才生成横向分段；截图中的相关银行流水没有 source link，因此函数返回 `null`，组件退回整组顺序渲染。
- 影响范围：前端关联台 group display model 和 `CandidateGroupGrid` 渲染；不改变后端 relation、read model、matching decision、确认/撤回逻辑或 API payload。
- 关键决策：source OA 仍是首选证据；缺 source OA 时只在同一个已返回 group 内做展示 fallback，先按唯一精确金额匹配，再按唯一 2 到 6 条金额合计闭合匹配；金额不唯一、无法唯一闭合或只能靠顺序/位置判断的行保持 group-level。
- 文档影响：同步本模块 README、state-machine、tests 和 implementation notes。
- 测试覆盖：新增 `web/src/test/groupDisplayModel.test.ts::builds amount fallback display segments for unlinked rows in multi-OA groups` 覆盖模型分段；新增 `web/src/test/CandidateGroupGrid.test.tsx::aligns unlinked same-amount and sum-matched rows inside a multi-OA group` 覆盖组件渲染。
- 验证命令：`cd web && npm test -- --run src/test/groupDisplayModel.test.ts`；`cd web && npm test -- --run src/test/groupDisplayModel.test.ts src/test/CandidateGroupGrid.test.tsx`。
- 未测风险：未连接生产数据回放截图中的真实 active generation；若生产 payload 中金额字段不是标准数字字符串，fallback 会保守跳过并保持 group-level。

## 2026-06-22 - OA 申请人时间 chip 统一使用申请时间 contract

- 目标：修复关联台 OA 栏申请人下方有些行显示时间 chip、有些行不显示的问题。
- 真实原因：前端 `applicationTime` mapper 曾优先读取 `detail_fields.审批完成时间`，并用 nullish fallback；当 OA 同步把缺失完成时间写成占位符 `—` 时，后续真实 `申请日期` 被挡住。SQL active generation 也只输出 `date`，没有把 OA 申请时间提升为顶层 `apply_time` / `application_time` contract；OA projection 写库还把 `application_date` 存成 `record.month` 月初，放大了新旧数据不一致。
- 影响范围：Workbench OA row DTO、SQL active generation schema/source freshness、OA projection sync version、前端 Workbench API mapper；不改变 OA 原始库、不改申请人列视觉结构、不用前端猜测时间。
- 关键决策：申请时间/申请日期是 applicant chip 的首选事实，审批完成/修改时间只作为兜底；`—`、`--` 等占位符必须视为缺失。后端 SQL 投影显式输出顶层时间字段并 bump schema；OA projection sync 使用 `detail_fields.申请日期` 写 `app.oa_applications.application_date`，并 bump `OA_PROJECTION_SYNC_VERSION` 触发后续重投。
- 文档影响：同步本模块 README、tests 和 implementation notes；OA projection 行为由 `oa-integration` 模块实施记录同步说明。
- 测试覆盖：`web/src/test/WorkbenchApi.test.ts` 覆盖占位完成时间不再挡住申请日期；`tests/test_workbench_sql_runtime.py` 覆盖 SQL OA row 顶层时间 contract；`tests/test_oa_projection_sync_service.py` 覆盖 projection 写库日期不再退化成月初。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlProjectionRelationPayloadTests.test_sql_oa_row_promotes_application_time_when_completed_time_is_placeholder tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_projection_application_date_uses_record_detail_date_not_month_start -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service tests.test_workbench_sql_runtime.WorkbenchSqlProjectionRelationPayloadTests tests.test_workbench_query_service -v`；`cd web && npm test -- --run src/test/WorkbenchApi.test.ts`。
- 未测风险：本地未连接生产 PostgreSQL 重建 active generation；发布后需让 OA projection sync / Workbench worker 重建相关 month/all scope，旧 active generation 才会带上新的顶层时间字段。

## 2026-06-22 - 关联预览 OA 主表金额差异使用明细合计核对

- 目标：修复关联预览中 OA 与流水实际金额一致，但页面显示“金额不一致 / 差额 270.00”的问题。
- 真实原因：日常报销聚合 OA row 的 `amount` 保留 OA 主表总金额，用于展示和审计；当 OA 解析已记录 `amount_source=header` 且主表金额与明细合计存在差异时，关联预览金额核对仍直接使用 `amount`，没有使用可付款/可核销的明细合计。
- 影响范围：`WorkbenchAmountCheckService` 的 OA 金额取值、`WorkbenchQueryService` 的 OA row payload、Workbench SQL active generation 的 OA row payload；不改变 OA 表格展示金额、不删除“金额差异”标签，也不放宽真实金额不一致的备注要求。
- 关键决策：新增/使用 `reconciliation_amount` 作为关联核对金额。新 OA row 由 query service 显式写出该字段；SQL projection 和金额核对服务兼容旧 read model，只要 `detail_fields` 中存在“金额来源=主表总金额”“明细金额合计”和“金额差异”，也按明细合计核对。
- 文档影响：同步本模块 README、tests 和 implementation notes。
- 测试覆盖：`tests/test_workbench_amount_check_service.py` 覆盖显式 `reconciliation_amount` 与旧详情字段兼容；`tests/test_workbench_query_service.py` 覆盖 OA row 保留主表 `amount` 并暴露 `reconciliation_amount`；`tests/test_workbench_sql_runtime.py` 覆盖 SQL projection 同口径。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_amount_check_service tests.test_workbench_query_service.WorkbenchQueryServiceTests.test_aggregated_expense_claim_row_exposes_detail_fields_tags_and_multiple_attachment_invoices tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_sql_projection_oa_row_keeps_header_amount_but_exposes_detail_sum_for_reconciliation -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_and_submit_require_note_for_amount_mismatch tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_directional_bank_total_for_mixed_bank_directions tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_batch_accounting_mismatch_note_projects_to_paired_bank_row -v`。
- 未测风险：未连接生产 PostgreSQL 回放真实 2026-03 数据；发布后需要重建对应 Workbench scope 并用截图中的 OA/流水重新打开确认预览。

## 2026-06-22 - 关联预览确认不再等待主 Workbench generation

- 目标：修复关联台内选择 OA 和多条流水后点击确认关联，关系已写入但弹窗报“关联台最新数据同步超过 10 秒，当前状态：refreshing”的问题。
- 影响范围：`ReconciliationWorkbenchPage` 的确认/撤回预览提交状态机、operation projection 应用路径、关联台前端回归测试；不改变后端 relation 写入、`workbench_relation` barrier、主 Workbench worker 或下游 read model fan-out 合同。
- 关键决策：`confirm-link` / `withdraw-link` 响应中的 `operation_projection` 是后端写后真实投影，不是前端本地乐观重排。预览提交成功后仍先等待受影响月份 `workbench_relation` operation barrier；barrier fresh 后若有 projection，直接应用投影并关闭预览，主 `workbench` active generation 后台追赶。只有缺少有效 projection 的旧动作才等待当前 Workbench fresh refetch 后释放。
- 文档影响：同步本模块 README、state-machine 和 tests，撤销“预览提交必须等待主 Workbench fresh refetch 才关闭”的旧页面口径。
- 测试覆盖：新增 `web/src/test/WorkbenchSelection.test.tsx::confirm link applies operation projection even when the main workbench generation is still refreshing`，并更新“提交进行中不移动行”的断言名称。
- 验证命令：`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx --testNamePattern "confirm link"`。
- 未测风险：本地 Vitest 使用 deterministic mock，不证明真实生产 worker drain、`workbench:all` active generation 或下游页面已经收敛；这些仍需 App Status/worker 监控和 staging/生产 smoke 单独验证。

## 2026-06-22 - Workbench active repair 不再污染 App Health 阻断

- 目标：修复关联台/Workbench 后台修复正在运行时，App Status 仍展示 `Workbench read model generation consistency failed.` 和红色阻断的问题。
- 影响范围：Workbench refresh status 到 `/api/app-health` 的聚合展示、App Status popover、关联台后台追赶时的用户可见状态；不改变 active generation 发布、paired/open 分区或写操作 barrier。
- 关键决策：`/api/workbench/refresh-status` 和 App Health 都采用 current-effective 语义。`read_model_status=refreshing/rebuilding` 时旧 consistency failure 只作为诊断，不能写 `workbench_read_model` unavailable dependency；没有 active repair 的 generation consistency failure 仍然保留为 failed/blocker。
- 文档影响：同步本模块 state-machine/tests，并在 read-models/runtime-workers 记录共享语义。
- 测试覆盖：新增 `tests/test_app_health_api.py::AppHealthApiTests::test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_app_health_api tests.test_app_status_overview_service -v`。
- 未测风险：本地测试不回放真实 Workbench month/all active generation；发布后需要看 App Status 是否从 blocked 降为 busy/refreshing，并等待 worker drain 到 fresh。

## 2026-06-22 - Workbench all view 使用 active all generation

- 目标：修复 `GET /api/workbench?month=all` 主视图和分页视图在 `workbench:all` active generation 已发布时仍从 month snapshots 临时合成 payload/summary 的问题。
- 影响范围：`PostgresReadModelRepository.get_workbench_view(scope_key="all")`、未分页 all 主视图、分页/过滤 all rows page、Workbench all-scope source_versions freshness 证明。
- 关键决策：all-scope 聚合器已经承担唯一 visible owner、paired/open 抑制、active relation occupancy 和 `workbench_matching_rules_version` 聚合；读路径必须消费已发布的 active all generation。未分页 all 先读 active all snapshot；分页/过滤 all 先读 active all summary，再通过 bounded `workbench_rows` page query 取行。只有没有 active all generation 时保留旧 month snapshot 合成 fallback，避免历史本地/测试环境直接不可用。
- 文档影响：同步本模块 README/tests 和 read-models 模块实施/回归记录。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_reads_all_scope_view_from_active_generation_snapshot`、`test_repository_reads_all_scope_filtered_page_from_active_all_summary`；保留 legacy fallback 回归 `test_repository_synthesizes_all_workbench_view_from_month_snapshots`、`test_repository_ignores_stale_all_workbench_snapshot_and_synthesizes_from_months`、`test_repository_reads_all_scope_filtered_page_without_full_snapshot_payloads`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v`。
- 未测风险：本地未连接真实生产 PostgreSQL/Redis/RabbitMQ；发布后需要 authenticated `/api/workbench?month=all` HTTP smoke 和 worker drain 观察，确认 active all generation 已重建且页面返回 fresh。

## 2026-06-22 - Group detail freshness gate 补齐

- 目标：修复关联台 group detail 接口在 active generation stale 或 dirty scope refreshing 时仍返回旧 group 并标 fresh 的问题。
- 影响范围：`GET /api/workbench/groups/detail`、`WorkbenchQueryFacade.group_detail(...)`、`PostgresReadModelRepository.get_workbench_group_detail(...)`、group detail 展开完整组详情的前端调用链。
- 关键决策：Workbench active generation 仍是展示事实源，但 group detail 不能只因来自 active generation 就视为 fresh。SQL repository 必须带出 active generation `source_versions`、`read_model_status` 和 `read_model_version`；facade 必须复用 Workbench source-version stale gate。non-fresh 时不返回旧 group，而是入队 Workbench refresh，并返回带 `read_model_status` 的 not-found 语义，让前端停止展开旧详情。
- 文档影响：同步本模块 README/tests，并在 read-models 模块记录通用回归。
- 测试覆盖：`tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_group_detail_stale_source_versions_do_not_return_stale_group`、`test_group_detail_refreshing_status_does_not_return_stale_group`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_group_detail_includes_active_generation_freshness_contract`、`tests/test_read_model_architecture_guards.py`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_read_model_architecture_guards -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_reads_only_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_group_detail_includes_active_generation_freshness_contract tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_group_detail_api_returns_full_group -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness tests.test_read_model_query_gateway tests.test_read_model_architecture_guards tests.test_workbench_query_facade tests.test_workbench_sql_runtime -v`。
- 未测风险：本地没有连接真实生产数据库或真实浏览器；发布后仍需 authenticated HTTP/worker drain smoke 验证旧 projection 已收敛。

## 2026-06-22 - 普通两栏 confirmed relation 留在未配对区

- 目标：修复关联台“已配对”区域出现大量普通 OA+银行、OA+发票、银行+发票两栏 `manual_confirmed` relation 的问题。任意两栏确认仍然允许，但只能表达 partial relation，等待第三栏补齐。
- 真实原因：`WorkbenchCandidateGroupingService._paired_group_has_enough_row_types()` 曾用 `row_type_count >= 2 and confirmed active relation` 作为宽泛 paired 条件，把 canonical active relation ownership 和三栏闭环展示混为一谈。confirm-link operation projection 也默认把确认后的 relation 放入 `paired_groups`，导致写后投影与 active generation 新规则不一致。
- 关键决策：`app.workbench_pair_relations.status='active'` 继续是 confirmed fact，用于 row occupation、撤回、审计和下游 `workbench_relation` linked distribution；关联台 paired/open 分区由 active generation/grouping 后端 policy 决定，前端不做本地重排。普通 `manual_confirmed` 两栏 relation 保留 canonical `case:<case_id>` open 待处理 group；OA + 银行 + 发票三栏完整进入 paired；no-OA、工资/个人自动闭合、内部转账、个人暂借款还清、OA invoice offset、批量账务、ETC summary/batch relation 和 processed/closed exception 等显式例外保持 paired。
- 文档影响：更新本模块 README、state-machine、tests、implementation notes，以及 `workbench-relations` 状态机，撤销 2026-06-21 “普通 active relation 两栏进 paired”的历史错误口径。
- 测试覆盖：新增/更新普通 OA+银行、OA+发票、银行+发票 active relation 留 open，三栏 active relation 留 paired，SQL projection canonical open owner，confirm-link 两栏 operation projection 走 `open_groups`、三栏走 `paired_groups`，前端 API mapper 和 selection model 对 open manual partial relation 的回归。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地未连接真实生产数据库；发布后需要重建受影响 Workbench month/all scope，并用只读 SQL 或页面 smoke 确认两栏 relation 从 paired 收敛到 canonical open group，且撤回预览仍走 `withdraw_relation`。

## 2026-06-22 - 外部往来闭环三栏分区纠偏

- 目标：修复贾小花三笔纯银行外部往来闭环进入关联台“已配对”区域，并被显示成“完全关联”的问题。
- 真实原因：2026-06-21 的修复把 active relation ownership 和 paired zone completeness 混为一谈；`WorkbenchCandidateGroupingService._paired_group_has_enough_row_types()` 对 bank-only `turnover_manual_closure` 放行到 paired，SQL projection 进入 paired serializer 后又把 chip 覆盖成“完全关联”。
- 关键决策：`turnover_manual_closure` 继续写 Workbench active relation，外部往来页继续显示“收支闭环”并支持撤回；关联台分区必须遵守 relation metadata requirement，bank-only / OA+bank-only 未满足 paired 条件时留在 canonical `case:<case_id>` open 待处理区，满足后进入 paired。generation consistency 允许 active relation row 出现在 canonical open owner，禁止的是非 canonical open/temp owner。
- 文档影响：同步产品规格、app architecture、本模块 README/state-machine/tests/implementation notes，以及 turnover-ledger 模块文档。
- 测试覆盖：新增/更新 `test_bank_only_turnover_manual_closure_rows_stay_open_until_three_way_complete`、`test_two_pane_turnover_manual_closure_rows_stay_open_until_invoice_exists`、`test_three_pane_turnover_manual_closure_rows_render_as_paired_case`、`test_sql_projection_keeps_turnover_manual_closure_bank_only_case_open_until_three_way_complete`、`test_manual_zero_difference_closure_creates_open_bank_only_workbench_relation_until_invoice_exists`、`test_manual_closure_accepts_three_bank_rows_and_keeps_workbench_case_open_until_invoice_exists`。

## 2026-06-21 - 外部往来 bank-only 闭环进入 paired（已被 2026-06-22 纠偏）

- 目标：修复生产 App Status 显示 `Workbench read model generation consistency failed`，且贾小花三笔外部往来闭环银行流水在关联台仍处于 open/temp、没有显示同一个 paired active case 的问题。
- 真实原因：`turnover_manual_closure` active relation 已经写入 `app.workbench_pair_relations`，但 Workbench grouping 仍沿用 2026-06-11 的 “bank-only 留 open” 规则；SQL projection 写入的银行 row relation code 是 `turnover_manual_closure`，`WorkbenchCandidateGroupingService._is_paired_row()` 不识别该 code，随后 `_paired_group_has_enough_row_types()` 又把纯银行 active relation demote 到 open。生产 consistency checker 正确发现 active relation row 被发布到非 canonical open/temp owner，报 `active_relation_open_membership` 并阻断 worker。
- 真实原因 2：第一次部署分组修复后，生产仍保留旧月度 active generation。`PostgresReadModelRepository.save_workbench_read_models(...)` 的 stale 写入护栏只比较 numeric `source_version`，没有比较 builder/schema 签名；当 dirty scope 已被清过或 source_version 低于旧 active generation 时，schema bump 后的新月度 generation 会被跳过，all scope 继续引用旧失败 parent generation。
- 关键决策（历史错误）：`turnover_manual_closure` 多银行 active relation 曾被视为外部往来完整闭环并展示在 paired 区；该 paired zone 口径已在 2026-06-22 撤销，当前规则要求未满足 paired 条件时留在 open 待处理区。
- 文档影响：同步更新产品规格、app architecture、本模块 README/state-machine/tests/implementation notes，以及 turnover-ledger 模块文档。
- 测试覆盖（历史，已由 2026-06-22 三栏分区测试替换）：当时新增/更新过 bank-only paired 断言；当前不再作为有效测试口径。

## 2026-06-21 - Workbench active repair 状态优先级修复

- 目标：修复 Workbench parent generation 已经入队/processing 重刷时，`/api/workbench/refresh-status` 和 App Status 仍优先展示旧 generation consistency failure，导致用户看到“刷新中”和“阻断”并存的问题。
- 影响范围：`PostgresReadModelRepository.get_workbench_refresh_status(...)`、App Status 读取 Workbench refresh status 的 blocked/busy 推导、外部往来闭环后的 Workbench month/all 后台追赶展示；不改变 Workbench active generation 发布事实或 relation 写入口。
- 关键决策：同一 Workbench scope 有 `pending`/`processing` dirty scope 或 building generation 时，当前 read model 状态为 `refreshing`；同一 immutable active generation 已缓存的 consistency failure 仍保留在 `consistency_status` 和 `read_model_stale_reasons` 中，尚无缓存 proof 时 `consistency_status=refreshing`，不能伪装 fresh，也不能为了诊断在 active repair 热路径重跑重型 generation audit。旧 `last_error` 不再作为当前失败弹窗/阻断原因。若没有 active repair，generation consistency failure 仍为 `failed`。
- 文档影响：同步本实施记录、`state-machine.md`、系统状态实施记录/状态机/测试矩阵和 runtime worker 测试矩阵。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_reports_inconsistent_workbench_generation_as_refreshing_during_active_repair`。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地测试证明 repository 状态优先级；真实生产仍需发布后等待 worker 消费 active dirty scopes，确认 `2026-02`、`2026-03` 和 `all` 收敛到 fresh。

## 2026-06-21 - Workbench all parent inconsistency 自愈

- 目标：修复外部往来闭环发布后 App Health 仍显示 `workbench_all_scope_parent_inconsistent`、1 failed、1 backlog、1 refreshing、两个同步中的问题，避免历史或可恢复的 all-scope parent inconsistency 长期阻断运行状态。
- 影响范围：`PostgresReadModelRepository` 的 all-scope aggregate 发布、`WorkbenchSqlProjectionBuilder.refresh_workbench_all_scope_from_active_shards(...)`、`RuntimeWorker` dependency-not-fresh defer、App Health 对后续 pending/retry 覆盖旧 failed 的展示链路。
- 关键决策：普通月 scope 发布时如果顺手聚合 all 发现 parent generation inconsistent，只跳过 all 聚合，不写新的 failed all generation，也不回滚已经发布的月 shard。aggregate-only `workbench:all` 事件发现 parent inconsistent 时抛 `workbench_read_model_not_fresh: parent_generation_inconsistent parent_scope_keys=...`；runtime worker 将 all 事件 defer，并强制补投对应 parent month scope，即使旧 readiness 仍显示 fresh，也要以 consistency failure 为准重建 parent。
- 文档影响：更新本实施记录和 `state-machine.md`；App Health 口径不变，继续以 current-effective dirty/outbox/readiness 判断左上角状态。
- 测试覆盖：新增/更新 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_aggregate_only_all_scope_defers_when_parent_generation_is_inconsistent`、`test_repository_does_not_publish_all_scope_when_month_generation_is_inconsistent`、`tests/test_runtime_worker.py::RuntimeWorkerTests::test_run_once_requeues_same_scope_parent_when_generation_is_inconsistent`。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地未直接操作生产队列；发布后需要让 runtime worker 消费当前 backlog，确认 parent month scope 被重建、aggregate-only all 发布新 active generation，旧 failed 被后续 pending/done/fresh 覆盖后 App Health 恢复。

## 2026-06-21 - OA 附件 item id 三方自动闭合修复

- 目标：修复未配对区仍出现“OA+银行自动匹配 + 发票同组展示”的 196 等三栏闭合场景；这些发票来自 OA 附件且 `derived_from_oa_id` 为 `oa-exp-*:item:*`，含税合计已闭合，但 free matching engine 没有生成三方 decision。
- 影响范围：`WorkbenchFreeMatchingEngine` 的 OA 附件发票父 OA 判断、matching dirty scope 重跑后的 `workbench_reconciliation_decisions`、Workbench month/all active generation 分区；不改变 `app.workbench_pair_relations` confirmed fact 语义，也不把页面展示 group 直接写成 active relation。
- 关键决策：OA 附件父 OA 归一必须复用 `oa_attachment_matches_oa` 统一 helper，禁止 matching engine 继续保留只比较父 OA row id 的旧逻辑。`display_state=paired` 的真实三方 automatic decision 可进入关联台已配对展示区，但仍不是 `app.workbench_pair_relations.status='active'` 的 confirmed fact；两栏 automatic decision 加 open 发票附着仍留 open。
- 文档影响：更新本模块 README、测试矩阵和 `workbench-relations` 状态机，明确 automatic paired display 与 confirmed active relation 的边界。
- 测试覆盖：新增 `tests/test_workbench_free_matching_engine.py::WorkbenchFreeMatchingEngineTests::test_oa_attachment_invoice_item_ids_close_three_way_candidate`，覆盖 `oa-exp-*:item:*` 明细项发票含税合计闭合生成 `oa_attachment_invoice_with_bank` 三方 paired decision。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_free_matching_engine.py::WorkbenchFreeMatchingEngineTests::test_oa_attachment_invoice_item_ids_close_three_way_candidate -q`。
- 未测风险：本地测试覆盖 matching root cause；发布后必须重跑 matching dirty scope 和 Workbench month/all scope，并用生产 SQL 验证目标 group 从 open 三栏附着变成 paired 三方 decision。

## 2026-06-21 - 已确认 active relation 两栏分区修复（已被 2026-06-22 撤销）

- 目标：修复关联台未配对区仍残留已确认 OA+银行 relation 的问题；这些行带 `完全关联`/`手动确认` 等事实字段，但因为缺少发票栏被分组层按“两栏不完整”降回 open。
- 影响范围：`WorkbenchCandidateGroupingService` 的 paired/open 分区、Workbench month/all active generation 重建结果、关联台页面分区展示；不改变 relation 写入口、自动匹配规则、发票补齐规则或下游页面事实源。
- 关键决策（历史错误）：当时把已确认 active relation 的 ownership 优先级提升为 paired zone 规则，认为同一 `case_id` 下带非 `automatic_decision` `relation_mode` 且 relation code 为 `fully_linked` 的多栏 relation，即使只有 OA+银行，也必须留在 paired 区。该结论已在 2026-06-22 撤销；当前规则要求含银行流水的 relation 只按 relation fact 中物化的 `requires_oa` / `requires_invoice` requirement 判定 paired/open，缺 metadata 时 fail closed。
- 文档影响：更新本模块 README 和测试矩阵，明确 canonical active relation、display tag、automatic decision 三者的分区优先级。
- 测试覆盖（历史，已由 2026-06-22 普通两栏 open 测试替换）：当时新增 `test_keeps_confirmed_active_oa_bank_relation_without_invoice_in_paired_section`；当前测试名和断言已反转为 open。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_candidate_grouping.py -q -k 'confirmed_active_oa_bank_relation_without_invoice or demotes_existing_two_type_case_id_rows_back_to_open_section or preserves_automatic_match_label_for_candidate_paired_groups'`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_candidate_grouping.py tests/test_workbench_sql_runtime.py tests/test_workbench_relation_sql_projection.py -q`。
- 未测风险：该历史验证不再代表当前口径；以 2026-06-22 新记录和最终验证为准。

## 2026-06-21 - 批量账务 active relation 投影归属修复

- 目标：修复关联台未配对区出现带 `完全关联`/`三栏已配对` tag 的行，但没有进入已配对区的问题；同时避免仅凭展示 tag 把没有 canonical active relation 的候选误提升为已配对。
- 影响范围：Workbench SQL active generation、批量账务写入的 OA+银行 active relation、relation metadata 指定的 ETC summary 同组展示、all/month active generation schema freshness；不改变 relation 写入口、下游 `workbench_relation` 分发合同或前端三栏组件。
- 关键决策：统一事实源仍是 `app.workbench_pair_relations`。SQL projection 必须在 grouped/open 分区前携带 active relation 的 `special_metadata`、`amount_check`、`display_tags`、`source_versions`；批量账务 relation 中的 `special_metadata.etc_batch_link.external_etc_batch_id` 也是 ETC summary 同组归属证据。UI chip 不是 confirmed fact，未正式化 automatic decision 只能保持 open/source-linked 展示。
- 文档影响：更新本模块 README、测试矩阵和 `workbench-relations` 状态机/实施记录，明确 Workbench active generation 与 `workbench_relation` 都是派生投影，不能互相造事实。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py` 两个回归，覆盖 active `batch_accounting` OA+银行 relation 进入 paired 区，以及 relation metadata 指定 ETC summary 后随同一 case 发布。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py -q -k 'keeps_active_batch_accounting_oa_bank_relation_paired or attaches_etc_summary_from_relation_metadata_batch_link'`；`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_sql_runtime.py tests/test_workbench_candidate_grouping.py tests/test_workbench_relation_sql_projection.py -q`；生产库只读 dry-run 验证 1935.45、2411.25 目标行进入 `paired/case:*`，196 目标行仍保持 open/source-linked。
- 未测风险：本轮不直接写生产库 active generation；发布后必须让 worker 按新的 Workbench SQL projection schema 重建对应 month/all scope，浏览器刷新后再做页面 smoke。

## 2026-06-21 - OA 附件发票必须与父 OA 同组

- 目标：修复生产发布后关联台仍显示 `OA附件` 发票行左侧 OA/银行流水为空的问题，确保 OA 附件解析出的正式发票在 Workbench 输出层一定与其 `derived_from_oa_id` 指向的父 OA 落在同一个 group。
- 影响范围：`WorkbenchCandidateGroupingService` 的最终分组输出、`workbench:all` 聚合发布、月份 read model 重建结果、关联台三栏展示；不改变统一发票池事实源、OA 附件 promotion 建票规则或 OCR 解析规则。
- 关键决策：之前的清理验收只证明 “父 OA 存在于同一个 active generation”，不足以证明 UI 同行展示。新增分组层不变量：只要 `source_kind=oa_attachment_invoice` 且父 OA 存在，输出前必须把该发票行移动到父 OA 所在 group；父 OA 已在普通候选、已有 case、已配对或跨月补投影 group 中时均适用。人工确认、已关闭、异常/忽略 group 不改 group 类型；普通 open/candidate group 被标记为 `source_linked`，避免附件发票继续以 invoice-only group 污染未配对区。`workbench:all` 不能只拼接 month shards，因为 OA 附件发票可能按发票月份进入 2026-01，而父 OA 按申请月份进入 2026-02/2026-03；all-scope 聚合必须再次执行同组归并，确保全局视图中 `parent_elsewhere=0`。
- 文档影响：本实施记录同步；长期业务口径不变，OA 附件发票仍是统一发票池里的进项发票，OA 附件 source link 是 OA 与发票的配对来源。
- 测试覆盖：更新 `tests/test_workbench_candidate_grouping.py`，覆盖父 OA 已在已有 case group 时附件发票回并父 OA group，以及父 OA 已在 paired group 时额外 OA 附件发票不再留在 open invoice-only group；更新 `tests/test_workbench_sql_runtime.py`，覆盖 all-scope 跨月聚合把附件发票移动到父 OA group。
- 验证命令：`PYTHONPATH=backend/src python -m pytest tests/test_workbench_candidate_grouping.py`；`PYTHONPATH=backend/src python -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_moves_cross_month_attachment_invoice_to_parent_oa_group tests/test_workbench_candidate_grouping.py`；`PYTHONPATH=backend/src python -m pytest tests/test_workbench_candidate_grouping.py tests/test_workbench_matching_rules.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_all_scope_moves_cross_month_attachment_invoice_to_parent_oa_group tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_keeps_synthetic_all_scope_groups_separate_by_month_shard tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_oa_projection_rows_exclude_attachment_invoice_rows tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_supplements_source_oa_for_attachment_invoice_rows tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_supplements_in_progress_source_oa_from_sql tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_rows_by_source_oa_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_item_rows_by_parent_oa_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_prefers_oa_attachment_source_link_with_context tests/test_oa_attachment_invoice_promotion_tool.py tests/test_workbench_pair_relation_integrity_repair.py`。
- 未测风险：本地自动测试覆盖分组/投影/聚合规则；真实浏览器截图仍需要发布后刷新确认三栏同行显示。真实库需重建 Workbench all-scope 并用 SQL 验证 `OA附件发票 parent_elsewhere=0`。

## 2026-06-21 - OA 附件发票父 OA 回连与关系完整性修复

- 目标：修复 OA 附件解析出的正式发票已进入统一发票池，但因 `derived_from_oa_id` 使用 `oa-exp-*:item:*` 明细项 ID 而没有回挂到父 OA 行的问题；同时清理清空重导发票后遗留的 active relation 旧发票 row id。
- 影响范围：Workbench candidate grouping、SQL projection、legacy matching rules、server payload repair、`repair_workbench_pair_relation_integrity` 工具、生产 `app.workbench_pair_relations` 数据。
- 关键决策：OA 附件发票匹配统一使用父 OA 规则：`oa-exp-xxx:item:n:hash` 归属 `oa-exp-xxx`；选择 OA 附件 source link 时优先使用带 `derived_from_oa_id/source_expense_item_id/source_workbench_row_id` 的有效上下文，避免历史空 source link 抢占。relation integrity repair 必须同步重算 `amount_check`，不能只改 `row_ids`。OA 附件 promotion 只接受 `app.oa_applications.row_id` 作为父 OA 主事实源，不能仅从 `source_expense_item_id` 字符串推断父 OA；SQL projection 需要为跨月份 OA 附件发票补投影父 OA 行。若父 OA 存在但 workflow_status 仍是 `in_progress`，只要 OA 附件发票指向该父 OA，也必须补投影该父 OA 上下文，避免附件发票在关联台成为 OA 为空的孤立行。
- 文档影响：同步本实施记录和 `workbench-relations` 模块实施记录/测试矩阵；长期事实源口径不变，仍以统一发票池和 Workbench active relation 为事实源。
- 测试覆盖：新增/更新 `tests/test_workbench_candidate_grouping.py`、`tests/test_workbench_matching_rules.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_oa_attachment_invoice_promotion_tool.py`，覆盖明细项回父 OA、source link 有效上下文优先、跨月份父 OA 补投影、`in_progress` 父 OA SQL fallback 补投影、promotion 不从缺失父 OA 的 item id 推断建票、relation repair 补附件和重算 amount_check。
- 验证命令：`PYTHONPATH=backend/src python -m pytest tests/test_workbench_candidate_grouping.py tests/test_workbench_matching_rules.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_rows_by_source_oa_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_item_rows_by_parent_oa_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_preserves_canonical_oa_attachment_source_metadata tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_invoice_row_prefers_oa_attachment_source_link_with_context tests/test_oa_attachment_invoice_promotion_tool.py tests/test_workbench_pair_relation_integrity_repair.py`；补充运行 `PYTHONPATH=backend/src python -m pytest tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_oa_projection_rows_exclude_attachment_invoice_rows tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_supplements_source_oa_for_attachment_invoice_rows tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_rows_by_source_oa_relation tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_pairs_materialized_attachment_item_rows_by_parent_oa_relation tests/test_oa_attachment_invoice_promotion_tool.py`。
- 未测风险：本地生产库 read model 重建脚本发布了 consistent active all generation，但脚本在后续 scope/status 阶段需要手动中断；真实 worker drain 和浏览器刷新仍需页面人工 smoke。既有数据库中已经晋级出的无父 OA `OA附件` 发票不能自动配对，必须单独审计后选择恢复父 OA 或撤销孤立晋级结果，不能伪造 OA 行。
- 数据修复：目标 A 清理已执行并备份到 `.runtime/fin_ops_platform/backups/target_a_20260621_154702/`。修复删除 122 张只有孤立 OA 附件来源的发票，8 张保留发票但移除坏 OA 附件 source link，删除 12069 条无法回到 `app.oa_attachments -> app.oa_applications` 的 cache source，并删除 6449 个已无 source 的 cache body。随后将 22 个已无事实源的旧 workbench month active generation 标为 superseded，强制重建受影响月份和 all-scope。验收结果：`app.invoices` 中 OA 附件 source link 缺父 OA 为 0，`app.oa_attachments` 缺父 OA 为 0，cache source 缺附件/OA 为 0，all-scope 中 196 个 OA 附件发票行全部能在 workbench 找到父 OA。

## 2026-06-21 - OA 附件 Promotion 不再默认读路径建票

- 目标：防止关联台 OA payload 构建或 OA 附件 cache update 在用户手工重导入发票池时，把 OA 附件 OCR 结果重新写入 `app.invoices`。
- 影响范围：Workbench OA row payload 构建触发的 promotion、OA sync dirty scope、设置页保存链路。
- 关键决策：promotion 入口统一读取 `OA附件发票晋级` 设置。默认 `link_existing_only` 不创建缺失发票；`disabled` 不调用 promotion upsert；`create_missing` 明确开启时才保留正式发票缺失创建能力。
- 文档影响：同步 `settings` 与 `oa-integration` 模块文档。
- 测试覆盖：`tests/test_workbench_v2_api.py` 覆盖默认不创建、禁用不调用、显式创建；`web/src/test/SettingsPage.test.tsx` 覆盖设置页保存。
- 验证命令：见本轮交付说明。
- 未测风险：真实生产 active generation 不在本地回放；发布后建议用一条含 OA 附件的月份做只读 smoke，确认设置为 `disabled` 时发票池数量不变。

## 2026-06-20 - 已配对现金流水特殊处理 Browser E2E

- 目标：把已配对现金流水的 `确认为过账`、`确认为买票`、`取消现金处理` 从权限只读拦截补齐为 full-access 真实浏览器主流程，避免“按钮能点但请求体、barrier、弹窗校验或成功后报错未覆盖”。
- 影响范围：`web/e2e/workbench-cash-special-flow.spec.ts`、deterministic API mock、`npm run e2e:smoke`、关联台 Spec-first E2E 文档；不改产品页面逻辑或后端业务逻辑。
- 关键决策：按业务规格断言 full-access 用户在已配对银行流水更多菜单执行三种现金特殊处理；每个 mutation 都必须携带完整 group row ids，买票必须校验买票成本和项目名称，写入后等待 `workbench_relation` operation barrier，通过 Workbench operation projection/background refresh 保持页面可继续操作，并由 strict Playwright fixture 捕获成功后的隐藏 UI/browser 错误。
- 文档影响：更新本模块 `e2e-spec.md`、`e2e-coverage.md`、`tests.md`、`implementation-notes.md`，同步 `docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-cash-special-flow.spec.ts`；扩展 `web/e2e/fixtures/apiMocks.ts` 的现金特殊处理 action result 与 mock routes；`web/e2e/permissions-role-matrix.spec.ts` 已覆盖 read-export 下同入口零 mutation。
- 验证命令：`cd web && npx playwright test e2e/workbench-cash-special-flow.spec.ts --project=chromium`；`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts --project=chromium -g "read-export users cannot trigger submitted-state write controls"`；`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`bash scripts/verify.sh docs`；`cd web && npx tsc --noEmit --pretty false`。
- 未测风险：本地 mock 不证明真实 PostgreSQL/worker 里现金特殊处理 command 的持久化、审计和成本统计下游结果；真实 worker drain 与成本/账务展示仍需 staging/production write-operation audit。

## 2026-06-19 - 关联台刷新提示归口 App Status

- 目标：移除关联台页内“刷新中/待刷新，当前结果可能不是完整最新数据”的横幅，避免同一运行状态在页面和状态框重复展示。
- 影响范围：`ReconciliationWorkbenchPage` 的 read model non-fresh 展示、stale empty 防 false-empty 断言、App Status popover 作为统一状态入口；不改变 Workbench active generation、freshness 判断、写入口 gate 或 read model refresh 行为。
- 关键决策：关联台页面继续用 `read_model_status` 防止 stale/refreshing 空 payload 被误显示为业务空态；但普通 stale/refreshing 不再渲染页内横幅。失败/不可用仍作为错误状态进入页面 status reason；全局运行状态框负责展示 read model/worker/import 的同步状态。
- 文档影响：本记录同步系统状态模块导入进度展示说明；长期 API/worker contract 不变。
- 测试覆盖：更新 `web/src/test/WorkbenchSelection.test.tsx`，锁定 stale empty payload 不显示全局空态且不再显示旧页内提示。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地前端测试覆盖 DOM contract；真实生产 App Status 是否足够醒目仍需发布后人工 smoke。

## 2026-06-18 - App Health write-safety Browser E2E

- 目标：补齐 `RECON-WB-E2E-012`，用真实 Chromium 覆盖 App Health 系统级写保护与关联台逐角色写入口组合。
- 影响范围：`web/e2e/workbench-permissions-flow.spec.ts`、deterministic API mock 的 `app_status.overall.write_safety.blocks_mutations` 开关、Spec-first E2E 覆盖文档；页面已有 `canWriteWorkbench` gate，未改业务页面逻辑。
- 关键决策：测试按业务规格断言：`overall.write_safety.blocks_mutations=true` 时，`read_export_only`、`full_access`、`admin` 仍可查看 open/paired/processed/ignored 读侧状态和诊断，但确认、撤回、split candidate、异常 apply/cancel、ignore/unignore 必须隐藏或 disabled；同时断言所有 Workbench mutation endpoint 和 operation barrier 均为零调用。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：扩展 `web/e2e/workbench-permissions-flow.spec.ts` 三个 Browser 场景；扩展 `web/e2e/fixtures/apiMocks.ts` 支持 `appHealthWriteSafetyBlocked`。
- 验证命令：`cd web && npx playwright test e2e/workbench-permissions-flow.spec.ts`。
- 未测风险：真实生产 App Health 状态源、真实角色同步、生产 active generation 全量回放和其他下游页面 fan-out 仍需 staging/生产只读 smoke；本地 deterministic Browser 已覆盖关联台 App Health write-safety blocker。
- 后续事项：`reconciliation-workbench` 当前 Spec-first E2E ID 已全量覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义，或 relation read model non-fresh 浏览器诊断。

## 2026-06-18 - 网络恢复与重复提交 Browser E2E

- 目标：补齐 `RECON-WB-E2E-011`，用真实 Chromium 覆盖关联预览的临时网络失败重试、409 stale preview 和重复提交防护。
- 影响范围：`ReconciliationWorkbenchPage` relation preview error/retry 状态机、`web/e2e/workbench-network-recovery-flow.spec.ts`、deterministic API mock 失败/冲突/延迟开关、`web/package.json` smoke 入口、Spec-first E2E 覆盖文档。
- 关键决策：测试按业务规格断言：临时网络失败不移动行、不启动 barrier，并允许在同一 preview 上重试；409/stale preview 不允许重试同一个 `preview_id`/`expected_versions`，只能关闭后重新预览；confirm/split_candidate/withdraw 在提交期间禁用关闭、取消、备注和主按钮，真实双击只产生一次 mutation。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-network-recovery-flow.spec.ts` 五个 Browser 场景；扩展 `web/e2e/fixtures/apiMocks.ts` 支持 confirm submit one-shot failure、409 conflict、confirm/withdraw submit delay；将该 spec 加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/workbench-network-recovery-flow.spec.ts`。
- 未测风险：真实断网/代理层重试、生产尾延迟和大数据下的同类重试体验仍需 staging/后续 Browser 场景；App Health write-safety 全局 blocker 已由后续 Browser 场景覆盖。
- 后续事项：下一轮转入 `workbench-relations` candidate/linked 负面语义，或 relation read model non-fresh 浏览器诊断。

## 2026-06-18 - 逐入口权限 Browser E2E

- 目标：补齐 `RECON-WB-E2E-008`，用真实 Chromium 覆盖 `read_export_only` 用户在关联台 open/paired/processed/ignored 状态下的写入口权限。
- 影响范围：`web/e2e/workbench-permissions-flow.spec.ts`、deterministic API mock 初始状态开关、`web/package.json` smoke 入口、Spec-first E2E 覆盖文档。
- 关键决策：测试按权限规格断言：read-export 用户仍可查看 Workbench 和辅助弹窗，但确认、撤回、split candidate、异常 apply/cancel、ignore/unignore 必须隐藏或 disabled；同时断言所有 Workbench mutation endpoint 和 operation barrier 均为零调用。为了不通过先执行写操作制造状态，mock 增加初始已配对、已处理异常和已忽略开关。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-permissions-flow.spec.ts` 三个 Browser 场景；扩展 `web/e2e/fixtures/apiMocks.ts` 支持 `workbenchInitialRelationConfirmed`、`workbenchInitialExceptionApplied` 和 `workbenchInitialRowIgnored`；将该 spec 加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/workbench-permissions-flow.spec.ts`；`cd web && npm run build`；`bash scripts/verify.sh docs`；`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`cd web && npm run e2e:smoke`。
- 未测风险：真实生产权限同步和审计查询仍属 staging/生产风险。网络恢复、重复提交、409 stale preview 和 App Health write-safety 已由后续 Browser 场景覆盖。
- 后续事项：下一轮转入 `workbench-relations` candidate/linked 负面语义，或 relation read model non-fresh 浏览器诊断。

## 2026-06-18 - 大数据三栏滚动 Browser E2E

- 目标：补齐 `RECON-WB-E2E-010`，用真实 Chromium 覆盖关联台大数据长列表、三栏横向滚动、分页、搜索过滤、详情抽屉和选择状态保持。
- 影响范围：`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts` large dataset mock、`web/package.json` smoke 入口、Spec-first E2E 覆盖文档。
- 关键决策：本地 deterministic E2E 不声称覆盖生产 P95/P99 性能；它覆盖用户可见的长列表 contract：205 个 open group 首屏分页、加载更多、搜索到第 65 组、详情打开/关闭、选择状态不丢、三栏 footer scrollbar 同步 header/body scrollLeft，并断言“加载更多/确认关联/关闭详情”等关键按钮在真实浏览器中未被遮挡。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-large-scroll-flow.spec.ts`；扩展 deterministic API mock 支持 `workbenchLargeDataset`、分页、搜索过滤和 `/api/workbench/rows/{row_id}` detail lookup；将该 spec 加入 `npm run e2e:smoke`。
- 验证命令：`cd web && npx playwright test e2e/workbench-large-scroll-flow.spec.ts`；`cd web && npm run build`；`bash scripts/verify.sh docs`；`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`cd web && npm run e2e:smoke`。
- 未测风险：真实生产库 P95/P99、大数据 SQL/worker drain、像素级截图基线仍需后续 Browser/staging 场景；网络恢复和重复提交/409 stale preview 已由后续 Browser 场景覆盖。
- 后续事项：App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义，或 relation read model non-fresh 浏览器诊断。

## 2026-06-18 - refreshing/stale false-empty Browser E2E

- 目标：补齐 `RECON-WB-E2E-006`，用真实 Chromium 覆盖 Workbench refreshing、stale false-empty 和 OA sync refreshing 写入口 gate。
- 影响范围：`ReconciliationWorkbenchPage` read model 状态提示与空态判断、`web/e2e/workbench-stale-error-flow.spec.ts`、deterministic API mock、Vitest mock、Spec-first E2E 覆盖文档。
- 关键决策：页面必须把 Workbench page 的 `read_model_status` 作为空态前置条件；只有 paired/open 首屏 page 都是 `fresh` 时，summary zero 才能显示“当前没有可展示记录”。`stale` 或 `refreshing` 返回空 rows 时只显示待刷新/刷新中诊断，不能把 false-empty 当业务结论。普通 Workbench refreshing 不全局禁用无关 group 写入口；OA sync refreshing 仍禁用 mutation。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：扩展 `web/e2e/workbench-stale-error-flow.spec.ts` 到 9 个 Browser 场景；扩展 `web/e2e/fixtures/apiMocks.ts` 支持 non-fresh/empty Workbench page payload；扩展 `web/src/test/apiMock.ts` 和 `web/src/test/WorkbenchSelection.test.tsx` 锁住 stale empty 不显示全局空态。
- 验证命令：`cd web && npx vitest run src/test/WorkbenchSelection.test.tsx`；`cd web && npx playwright test e2e/workbench-stale-error-flow.spec.ts`；`cd web && npm run build`；`bash scripts/verify.sh docs`；`PYTHONPATH=backend/src python3 -m unittest tests.test_nightly_ci -v`；`cd web && npm run e2e:smoke`；`git diff --check`。
- 未测风险：大数据三栏滚动、重复提交/409 stale preview、网络恢复和 App Health write-safety 已由后续 Browser 场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：下一轮转入 `workbench-relations` candidate/linked 负面语义，或 relation read model non-fresh 浏览器诊断。

## 2026-06-18 - 异常处理 apply/cancel/ignore Browser E2E

- 目标：补齐 `RECON-WB-E2E-009`，用真实 Chromium 覆盖关联台异常处理 apply/cancel/ignore/unignore 的用户主链路。
- 影响范围：`web/e2e/workbench-exception-flow.spec.ts`、deterministic API mock、`WorkbenchExceptionModal`、`ReconciliationWorkbenchPage` exception/ignore 操作顺序、`CandidateGroupGrid`/`CandidateGroupCell`/`WorkbenchRecordCard`/`RowActions` 默认 action column、前端 Workbench API mapper、`WorkbenchWriteFacade` exception apply response contract 和 Spec-first E2E 文档。
- 关键决策：测试按业务规格断言：异常 apply 写 API 成功后必须留在弹窗内 busy，等待 operation barrier 和当前 Workbench fresh refetch 后才展示 processed exception；写后同步失败不能引导重复提交。ignore/unignore 必须通过真实浏览器行按钮进入 ignored modal 并刷新辅助数据。审计过程中发现 open group 发票行有 ignore API 但默认三栏未暴露 action column、ignore 后 ignored 列表未刷新、exception apply response 未返回可等待的 scope/freshness targets，均已修复。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-exception-flow.spec.ts`；扩展 `web/e2e/fixtures/apiMocks.ts` 的 exception preview/apply/cancel 与 ignore/unignore mock；更新 `web/src/test/WorkbenchExceptionModal.test.tsx`、`web/src/test/WorkbenchApi.test.ts` 和 `tests/test_workbench_v2_api.py` 锁住前后端 contract。
- 验证命令：`cd web && npx vitest run src/test/WorkbenchApi.test.ts src/test/WorkbenchExceptionModal.test.tsx`；`cd web && npx playwright test e2e/workbench-exception-flow.spec.ts`；`cd web && npx vitest run src/test/WorkbenchSelection.test.tsx src/test/WorkbenchExceptionModal.test.tsx`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_exception_apply_api_creates_closed_case_and_pair_relation -v`；`cd web && npm run build`；`cd web && npm run e2e:smoke`。
- 未测风险：大数据三栏滚动、重复提交/409 stale preview、网络恢复和 App Health write-safety 已由后续 Browser 场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：`RECON-WB-E2E-006` refreshing/stale false-empty、`RECON-WB-E2E-010` 大数据三栏滚动、`RECON-WB-E2E-011` 网络恢复/重复提交和 `RECON-WB-E2E-012` App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义。

## 2026-06-18 - 关联预览 barrier/refetch failure Browser E2E

- 目标：补齐 `RECON-WB-E2E-007` 剩余缺口，用真实 Chromium 覆盖写成功后 operation barrier timeout 与 Workbench fresh refetch failure 的 committed error。
- 影响范围：`web/e2e/workbench-stale-error-flow.spec.ts`、deterministic API mock、`ReconciliationWorkbenchPage` 关联预览提交顺序、Spec-first E2E 覆盖文档。
- 关键决策：测试按业务规格断言：写 API 成功后若 barrier timeout 或 fresh refetch 失败，弹窗必须停留在错误状态，提示“关系已写入，关联台刷新未完成”，禁用备注和重试，只允许关闭；底层行在 fresh refetch 成功前不能被本页自己的 domain event 提前移动。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：扩展 `web/e2e/workbench-stale-error-flow.spec.ts` 两个 Browser 负面场景；扩展 `web/e2e/fixtures/apiMocks.ts` 的 operation barrier refreshing 和 Workbench fresh refetch failure mock；修复 `ReconciliationWorkbenchPage` 只在 barrier + fresh refetch 成功后才 clear selection 并 emit `workbenchRelationUpdated`。
- 验证命令：`cd web && npx playwright test e2e/workbench-stale-error-flow.spec.ts`。
- 未测风险：409 stale preview、重复点击、网络恢复和 App Health write-safety 已由后续 Browser 场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：`RECON-WB-E2E-009` 异常处理、`RECON-WB-E2E-006` refreshing/stale false-empty、`RECON-WB-E2E-011` 网络恢复/重复提交和 `RECON-WB-E2E-012` App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义。

## 2026-06-18 - 关联台 stale/error Browser E2E

- 目标：推进 `RECON-WB-E2E-006/007/012`，用真实 Chromium 覆盖关联台 stale、OA dirty、refresh failed 和写 API 失败的用户可见负面链路。
- 影响范围：`web/e2e/workbench-stale-error-flow.spec.ts`、deterministic API mock、`AppHealthStatusContext` 的 source 合成、`npm run e2e:smoke`、Spec-first E2E 覆盖文档。
- 关键决策：测试按业务规格断言：普通 Workbench stale 只能提示陈旧，不应全局禁用无关 group 写入口；OA dirty/refreshing 才禁用关联台写入口；refresh failed 必须提示但保留当前 active generation 可查看；写 API 失败必须停留在预览弹窗显示错误，不移动行、不启动 operation barrier。测试过程中发现 `app_status` 存在时前端 health context 会丢掉 `oa_sync.dirty_scopes`，已补回为单元回归和 Browser gate。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-stale-error-flow.spec.ts`；扩展 `web/e2e/fixtures/apiMocks.ts` 的 App Status / OA sync / Workbench health mock；更新 `web/src/test/AppHealthStatusContext.test.tsx` 锁住 `app_status + oa dirty` 组合契约。
- 验证命令：`cd web && npm test -- --run src/test/AppHealthStatusContext.test.tsx`；`cd web && npx playwright test e2e/workbench-stale-error-flow.spec.ts`；`cd web && npm run e2e:smoke`；`cd web && npm run build`；`bash scripts/verify.sh docs`。
- 未测风险：409 stale preview、重复点击、网络恢复和 App Health write-safety 已由后续 Browser 负面场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：barrier timeout / fresh refetch failure、`RECON-WB-E2E-009` 异常处理、`RECON-WB-E2E-006` refreshing/stale false-empty、`RECON-WB-E2E-011` 网络恢复/重复提交和 `RECON-WB-E2E-012` App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义。

## 2026-06-18 - 自动候选 split_candidate Browser E2E

- 目标：补齐 `RECON-WB-E2E-005`，用真实 Chromium 覆盖未配对区自动候选的统一撤回/拆分主链路。
- 影响范围：`web/e2e/workbench-candidate-split-flow.spec.ts`、deterministic API mock、`ReconciliationWorkbenchPage` relation preview submit 文案、`npm run e2e:smoke`、Spec-first E2E 覆盖文档。
- 关键决策：测试按业务规格断言：用户点击自动候选任意一行时 UI 显示显式选中 1 条、上下文带入 2 条；preview/submit 仍必须携带完整 group row ids。后端 preview 判定 `split_candidate` 后，submit 必须回传 `operation_type`、`preview_id` 和 `submit_expected_versions`，弹窗内 busy 锁定，等待 operation barrier 和当前 Workbench fresh refetch 后才关闭并隐藏候选。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`、`state-machine.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/nightly-ci.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/workbench-candidate-split-flow.spec.ts`；扩展 `web/e2e/fixtures/apiMocks.ts` 的 split_candidate preview/submit mock、候选 suppress 状态和请求体观测；修复 `ReconciliationWorkbenchPage` split 提交时被硬编码 withdraw loading 文案覆盖的问题。
- 验证命令：`cd web && npx playwright test e2e/workbench-candidate-split-flow.spec.ts`；`cd web && npm run e2e:smoke`；`cd web && npm run build`；`bash scripts/verify.sh docs`。
- 未测风险：stale/refreshing 页面 gate、重复点击、409 stale preview、网络恢复和 App Health write-safety 已由后续 Browser 负面场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：stale/error、refreshing/stale false-empty、barrier timeout、fresh refetch failure、异常处理、`RECON-WB-E2E-011` 网络恢复/重复提交和 `RECON-WB-E2E-012` App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义。

## 2026-06-18 - 关联台自身 withdraw Browser E2E

- 目标：补齐 `RECON-WB-E2E-004`，用真实 Chromium 覆盖从 paired group 发起撤回关联的用户主链路。
- 影响范围：`web/e2e/workbench-withdraw-flow.spec.ts`、deterministic API mock、`npm run e2e:smoke`、Spec-first E2E 覆盖文档；不改业务页面逻辑。
- 关键决策：测试按业务规格断言，而不是照当前实现自证。用例先建立 paired group，再执行 withdraw preview/submit；断言 preview 锁定 `operation_type`、`preview_id`、`submit_expected_versions`，提交时弹窗内 busy 并禁用关闭/取消/重复提交/备注，fresh refetch 前不做本地 optimistic 行移动，operation barrier 与当前 Workbench fresh refetch 完成后才关闭并恢复 open group。
- 文档影响：更新本模块 `e2e-coverage.md`、`tests.md`、`implementation-notes.md`，同步 `docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 Nightly CI 风险说明。
- 测试覆盖：新增 `web/e2e/workbench-withdraw-flow.spec.ts`；扩展 `web/e2e/fixtures/apiMocks.ts` 的 withdraw preview/submit mock 和请求体观测。
- 验证命令：`cd web && npx playwright test e2e/workbench-withdraw-flow.spec.ts`；`cd web && npm run e2e:smoke`；`bash scripts/verify.sh docs`。
- 未测风险：stale/refreshing 页面 gate、重复点击、409 stale preview、网络恢复和 App Health write-safety 已由后续 Browser 负面场景覆盖；真实生产 App Health 状态源仍属 staging/生产风险。
- 后续事项：stale/error、refreshing/stale false-empty、barrier timeout、fresh refetch failure、异常处理、`RECON-WB-E2E-011` 网络恢复/重复提交和 `RECON-WB-E2E-012` App Health write-safety 已由后续 Browser 场景覆盖；下一轮转入 `workbench-relations` candidate/linked 负面语义。

## 2026-06-18 - Spec-first E2E Audit 首轮基线

- 目标：把关联台 Browser e2e 从 smoke 覆盖升级为 Spec-first 审计，先明确页面应该如何工作，再映射现有 Playwright/Vitest/API/integration 覆盖。
- 影响范围：新增 `e2e-spec.md` 和 `e2e-coverage.md`；更新模块 README/tests 入口；不改业务代码或测试代码。
- 关键决策：现有 `workbench-relation-fanout.spec.ts`、`pending-invoices-fanout.spec.ts`、`batch-accounting-flow.spec.ts`、`turnover-ledger-flow.spec.ts` 不推翻重写。它们已经验证用户可见业务结果和跨页面 refetch，可保留；当时未覆盖 withdraw、split candidate、read model 负面状态、失败恢复、异常处理和大数据滚动等缺口。本记录之后已补充 withdraw、split candidate、stale/refreshing/false-empty、OA dirty/refreshing、refresh failed/write failure、barrier timeout/fresh refetch failure、exception apply/cancel/ignore、大数据三栏滚动、网络恢复、409 stale preview、重复提交和 App Health write-safety Browser smoke，剩余重点转为权限矩阵跨其他页面扩展和下游 relation 语义。
- 文档影响：同步 `docs/dev/spec-first-e2e-audit.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/modules/README.md`。
- 测试覆盖：本轮是审计文档基线，未新增测试。
- 验证命令：`bash scripts/verify.sh docs`。
- 未测风险：真实生产 active generation 回放、真实 worker drain、OA/iframe、大数据性能仍是 `external-risk`，不能计入本地 CI 覆盖。

## 2026-06-18 - 确认/撤回预览内阻塞直到 Workbench fresh refetch

- 目标：确认/撤回关联时，保留操作前/操作后三栏预览，并在用户点击确认后阻塞在同一个预览弹窗内，直到操作级 relation fresh 且当前关联台重新加载完成后才关闭。
- 影响范围：`ReconciliationWorkbenchPage` relation preview submit flow、关联预览弹窗 UI、`WorkbenchSelection.test.tsx` 前端交互回归；不改变后端 relation 写 contract。
- 关键决策：`runBlockingAction` 继续服务其他全局写操作；确认/撤回预览改用共享执行器但传入 `waitForFreshWorkbenchLoad=true`。预览路径先等待写 API 返回的 `workbench_relation` freshness targets fresh，再执行 Workbench fresh refetch；期间不应用本地 optimistic update 或 operation projection 移动底层行。弹窗 busy 时禁用关闭、取消、重复提交和备注编辑；写入后刷新失败时显示“关系已写入，关联台刷新未完成”，避免引导重复写入。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录；长期 API/worker contract 未变化。
- 测试覆盖：更新 `web/src/test/WorkbenchSelection.test.tsx`，覆盖预览内 busy、无全局 overlay、按钮禁用、operation-scoped barrier target、不等待 global/all scope、fresh refetch 前不移动行、撤回 refetch 后恢复 open group。
- 验证命令：`npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx`。
- 未测风险：未跑真实浏览器截图或生产数据回放；视觉细节仍需在真实数据量的预览弹窗里人工抽样检查。

## 2026-06-17 - 撤回关联 operation barrier 超时修复

- 目标：修复关联台撤回/确认后，写入已成功但全屏 overlay 报 `操作同步等待超时 · workbench_relation · 2026-03 · refresh outbox pending` 的问题。
- 影响范围：`ReconciliationWorkbenchPage` operation barrier 等待预算、`OperationFreshnessBarrierService` scope 判定、`RuntimeMonitoringRepository.app_status_runtime_snapshot` outbox payload、关联台测试矩阵和运行时调用链文档。
- 真实原因：生产只读证据显示截图对应时间 2026-06-17 18:49:43 同时入队 `workbench_relation` 2026-02 与 2026-03 refresh，分别在 7.19s 和 8.20s 后 `done`，当前无 active backlog。旧前端把关联台 operation barrier timeout 设为 2s，因此在 worker 正常完成前误报超时；这不是 relation 撤回写失败。排查还发现后端 barrier 读取的 outbox 状态按 `event_type` 聚合，存在其他 scope pending 误伤当前目标 scope 的风险。
- 关键决策：确认/撤回带 operation projection 的路径继续只等受影响月份 `workbench_relation`，但前端等待窗口改为覆盖生产 worker 尾延迟；完整 Workbench active generation fallback 使用独立预算。后端 runtime snapshot 保留 event_type 总览，同时暴露 `scopes[]`；operation barrier 只采纳目标 scope 的 outbox pending/failed，`all` scope 仍使用聚合状态。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md`、本实施记录，并同步 `docs/app-architecture/runtime-and-ownership.md`。
- 测试覆盖：新增/更新 operation barrier service、runtime snapshot 和 Workbench 前端交互测试，覆盖目标 scope pending、其他 scope pending 不阻断、snapshot scopes 明细，以及前端 pending 超过 2s 后仍等待最终 fresh。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_app_status_overview_service.AppStatusRuntimeRepositoryTests -v`；`cd web && npm test -- --run src/test/OperationBarrierApi.test.ts src/test/WorkbenchSelection.test.tsx`。
- 未测风险：本地测试不执行真实生产写入；发布后仍需用受控撤回/确认或只读队列观察验证生产 overlay 不再在 2s 报错，且 App Status scoped outbox payload 正常。

## 2026-06-17 - 确认预览金额方向核对与确认按钮可见性

- 目标：修复关联台确认预览把 mixed bank directions 的绝对流水合计误判为金额不一致，并让长预览中“确认关联”按钮持续可见。
- 影响范围：`WorkbenchAmountCheckService.check`、`/api/workbench/actions/confirm-link/preview` amount summary、`RelationPreviewTriPane` 金额状态展示、`RelationPreviewDialog` footer 样式、本模块测试矩阵。
- 关键决策：金额核对口径保留在后端 service。若 OA 或发票给出本次关系方向，银行流水只用同方向子合计参与本次确认金额比较；反向流水仍在预览明细里展示，但不计入可比 `bank_total`。前端预览只消费后端 `amount_summary.status/mismatch_fields`，不再用展示合计自行重算业务状态。预览弹窗改为中间内容区滚动、底部 actions 固定在 modal 内，长内容下保持“取消/确认”按钮可见。
- 文档影响：更新本模块 `tests.md` 和本实施记录；未改变 relation mode/state 或长期产品口径。
- 测试覆盖：新增后端金额 core 单测、confirm preview API contract 测试和前端交互回归，覆盖 1 条 OA 支付、1 条支出流水、2 条收入流水的截图形态。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_amount_check_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_and_submit_require_note_for_amount_mismatch tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_directional_bank_total_for_mixed_bank_directions tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_unbalanced_amounts -v`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx`；`cd web && npm run build`。
- 未测风险：未用生产真实截图数据做浏览器/数据库回放；发布后如仍看到 active relation 已占用的部分 row 让 confirm preview 变成 withdraw preview，需要按 canonical active relation 与 Workbench active generation display audit 单独排查。

## 2026-06-17 - 未配对自动 decision 撤回关联拆分

- 目标：修复未配对区银行流水+发票自动匹配候选点击“撤回关联”返回 `Workbench relation is not active or does not exist.` 的问题。
- 影响范围：`WorkbenchWriteFacade.preview_withdraw_link` / `withdraw_link`、`WorkbenchReconciliationDecisionStore` suppress 边界、`candidate_match_changed` 派生数据刷新事件、Application wiring、本模块测试矩阵。
- 关键决策：未配对区统一按钮仍由后端 preview 判定操作类型。优先查 canonical active relation；不存在 active relation 时，先兼容 legacy `WorkbenchCandidateMatchService`，再查当前 SQL `read_model.workbench_reconciliation_decisions` 中 active open/paired decision。命中 decision 时返回 `split_candidate` preview，submit suppress decision 并刷新 decision 所属月份，而不是把它当作可撤回 active relation。
- 真实原因：截图中选中的两行是 `automatic_decision` 展示组，事实源是 `read_model.workbench_reconciliation_decisions`；它没有写入 `app.workbench_pair_relations`，也不在 legacy candidate snapshot 中。旧 withdraw preview 因而只得到 relation command 的 not-found 错误，没有落到当前页面实际使用的 decision store。
- 文档影响：更新本模块 `tests.md`、本实施记录和 app runtime ownership 文档。
- 测试覆盖：新增 facade decision preview split、decision submit suppress 回归，新增 HTTP preview/submit contract 回归，并保留 legacy candidate split 回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_preview_splits_reconciliation_decision_when_no_active_relation tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_submit_suppresses_reconciliation_decision_candidate tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_link_splits_pure_candidate_group_without_relation_history -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_withdraw_link_preview_splits_reconciliation_decision_without_active_relation -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_reconciliation_decision_store -v`。
- 未测风险：本地测试使用 fake store/live rows，不直接回放生产 active generation；发布后仍需用真实数据抽样确认该自动 decision 被 suppress 后页面刷新为独立未配对行。

## 2026-06-16 - server.py boundary 守卫证据

- 目标：收敛 P2/P3 中 `server.py` broad dispatch / transitional delegate 风险，判断是否需要在本轮为关联台、税金抵扣、成本统计相关路径做大范围迁移。
- 影响范围：平台 runtime boundary guard、关联台 relation command boundary、downstream relation read model、read model refresh gateway；本轮不改业务代码。
- 关键决策：不在 P2/P3 性能闭环中扩大 `server.py` 重构。现有守卫已覆盖 service 不 import HTTP/auth、不直连 Redis/RabbitMQ、downstream relation read model 必须走 distribution/facade、server active relation repair 必须走 relation command boundary、Workbench write facade 使用显式依赖，以及 read model refresh producer 必须走 scope gateway 边界。
- 文档影响：更新 `.planning/P2P3-CLOSURE-PLAN.md`，本模块记录守卫证据；长期架构方向不变，`server.py` 仍只应承担 route/dependency wiring 和 HTTP 映射。
- 测试覆盖：复用 `tests/test_platform_runtime_boundary_guards.py` 中 8 个 boundary guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_services_do_not_import_http_auth_boundary_or_parse_cookie_token_headers tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_real_redis_and_rabbitmq_clients_are_confined_to_platform_adapters tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_read_models_use_workbench_relation_distribution tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_downstream_relation_query_services_do_not_accept_pair_relation_service tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_active_relation_repairs_use_relation_command_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_and_matching_services_do_not_import_external_clients_directly tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_write_facade_uses_granular_constructor_dependencies tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_read_model_refresh_producers_use_scope_gateway_boundary -v`。
- 未测风险：该证据不能证明 `server.py` 已完成所有长期瘦身；它只证明当前 P2/P3 目标相关的关键边界未回退。后续若做长期重构，需要单独 phase 和更宽回归。

## 2026-06-16 - all-scope groups page 性能护栏证据

- 目标：把 P2/P3 一秒级同步审计中发现的 Workbench all-scope/full-scope 慢查询风险，收敛成首屏 groups API 的本地回归护栏。
- 影响范围：`PostgresReadModelRepository.get_workbench_groups_page` 查询 contract、关联台测试矩阵、P2/P3 closure ledger；不改变生产数据、不执行 repair 或 deploy。
- 关键决策：当前首屏 groups API 必须保留 repository page 入口，`page_size` 上限为 200，并使用 SQL `limit/offset`。生产 `pg_stat_statements` 中的历史慢 SQL 继续作为投影/发布/full-scope profiling 风险处理，不能等同于当前首屏 API 无界读取。
- 文档影响：更新本模块 `tests.md`、read-models `tests.md` 和 `.planning/P2P3-CLOSURE-PLAN.md`。
- 测试覆盖：新增 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_bounds_all_scope_groups_page_query`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_bounds_all_scope_groups_page_query -v`。
- 未测风险：本地单测不证明真实生产 `workbench_rows/groups/group_rows` 投影和发布路径 P95 <= 1000ms；该部分仍需 staging/生产只读 profiling 和受控 SLO smoke。

## 2026-06-15 - Matching completed scope source-version 自愈闭环

- 目标：补齐规则版本发布后的后台闭环，确保 196、6868.55 这类历史 completed matching scope 在 `workbench_matching_rules_version` 变化后会自动重新入队并重建候选/decision。
- 影响范围：`WorkbenchMatchingDirtyScopeWorker`、`WorkbenchReconciliationDirtyQueue`、`PostgresReadModelRepository` matching dirty scope SQL、`RuntimeQueueRepository` transaction-bound JSONB adapter、Workbench all-scope aggregate source_versions、本模块文档。
- 关键决策：不新增前端补救逻辑，不手工 SQL 修指定月份，不把 OA/银行/发票事实池合并；把“completed scope 的 matching source_versions 是否覆盖当前版本”作为 durable queue/service 边界内的常驻 worker 自检。repository 使用 `for update skip locked` 原子挑出 stale completed rows 并转回 `dirty`，worker 之后按既有 claim/complete/fail 生命周期处理。
- 真实原因补充：前一轮修复把 `workbench_matching_rules_version` 纳入 month active generation freshness，但生产 `job.workbench_matching_dirty_scopes` 中 2026-01/02/03 等 scope 仍是旧版本 `completed`，常驻 worker 只 claim `dirty/retry`，因此不会自动重跑；重投后还暴露出 `RuntimeQueueRepository` 在绑定真实 `PostgresTransaction` 时没有把 read model refresh payload 包装成 JSONB，导致 decision expire 同事务入队失败；`all` active generation 还缺少 matching 版本传播，导致全局视图缺少 freshness 证明。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和 runtime worker 治理文档。
- 测试覆盖：新增 worker claim 前 stale completed scope 自检测试、dirty queue 内存重投测试、repository 原子 SQL 测试、RuntimeQueue transaction-bound JSONB adapter 测试，并扩展 all-scope 聚合版本传播测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_workbench_matching_dirty_scope_worker.py tests/test_workbench_reconciliation_dirty_queue.py tests/test_workbench_sql_runtime.py tests/test_workbench_reconciliation_decision_store.py -q`。
- 未测风险：本地测试未直接连接生产库；发布后需通过正常部署和 worker/read model contract 让生产 scope 重投，再只读验证目标月份分组。

## 2026-06-15 - 预约付款日期消歧与 Workbench active generation 刷新闭环

- 目标：修复 6868.55 多个月同金额同对方 OA-bank 不能自动配对，以及 196 等自动候选规则变更后旧 active generation 继续发布旧分组的问题。
- 影响范围：`WorkbenchFreeMatchingEngine`、legacy `WorkbenchMatchingRules`、`PostgresReadModelRepository` reconciliation decision 写入/过期、Workbench SQL projection/source version provider、本模块文档。
- 关键决策：不把 OA、银行流水、发票合并成一个源事实池；保留三类源事实和 `app.workbench_pair_relations` canonical relation 边界，只在后端匹配 service 中用统一候选/决策逻辑比较三栏事实。明确“预约 X 月 X 日转款/付款/支付/打款”是 OA-bank 强消歧证据，但必须与银行真实交易日期一致，且仍要求金额、方向和业务文本证据；无预约日期的重复同金额候选继续保持 conflict/open。
- 真实原因：6868.55 原先在五个月窗口内形成多 OA、多银行同金额同对方候选，互相不唯一，所以被安全地发布为 open；196 类问题叠加了 matching rule version 未进入 SQL active generation `source_versions`，以及 reconciliation decision 写入/过期只刷新 relation、不刷新主 `workbench` month generation，导致旧 generation 可以继续被 API 当 fresh。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录，并同步 read-models/workbench-relations 边界说明。
- 测试覆盖：新增/更新 free engine、legacy matching rules、decision repository 和 SQL runtime freshness 测试，覆盖预约日期消歧、无日期保持冲突、decision upsert/stale expire/missing expire 双刷新、matching rule version freshness。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_matching_rules tests.test_workbench_reconciliation_decision_store tests.test_workbench_sql_runtime -v`。
- 未测风险：未执行生产库写入或真实 active generation rebuild；发布后需要按运维 runbook 对受影响月份重建/刷新 Workbench active generation，并只读抽样验证 196 与 6868.55 分组。

## 2026-06-15 - 确认/撤回操作级 2 秒 SLO 与后台 cross-page SLO 拆分

- 目标：生产写操作验证显示 withdraw HTTP 成功且最终 fresh，但 `workbench` month shard 和下游 read model 仍有 2.7-11s 长尾，导致全屏 overlay 暴露给用户。将“当前关联台可见状态 2 秒内可用”的阻塞目标收敛为 canonical relation/operation projection + `workbench_relation` fresh，把 Workbench generation 和跨页面 fan-out 改为后台追赶与单独 SLO 监控。
- 影响范围：`WorkbenchWriteFacade` confirm/withdraw response contract、`ReconciliationWorkbenchPage` operation barrier fallback、Workbench 前端 mock、`write_operation_slo_audit` operation profile。
- 关键决策：确认/撤回写 API 返回的 `freshness_targets` 只包含受影响月份的 `workbench_relation`；同一写 API 返回的 `operation_projection` 是后端事务后真实 after-state，前端应用它更新受影响 group 后释放 overlay。`workbench_relation_confirm/withdraw` SLO profile 只代表操作级阻塞目标；新增 `*_cross_page` profile 保留 `workbench`、bank detail、invoice lifecycle、pending invoice、input usage、cost/search/tax 等后台追赶监控。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录，并同步 read-models 模块说明。
- 测试覆盖：`tests/test_workbench_auth_context_idempotency.py` 覆盖 response blocking targets；`tests/test_write_operation_slo_audit.py` 覆盖操作级与 cross-page profile 分离；`web/src/test/WorkbenchSelection.test.tsx` 覆盖 overlay barrier 只提交 `workbench_relation` target 且用后端 projection 更新 UI。
- 验证命令：见本轮最终执行记录。
- 未测风险：本地自动化证明 contract；生产 2 秒证明必须发布后用真实登录态再次执行受控 confirm/withdraw scenario。2026-06-17 生产证据显示真实 `workbench_relation` refresh 可达 7-8 秒，该 2 秒口径只能作为优化目标/监控指标，不能作为前端失败阈值。

## 2026-06-14 - 写操作全屏 overlay 与真实 freshness barrier

- 目标：把关联台确认、撤回、异常、忽略等写操作从前端本地 optimistic 重排切换为“写 API 成功后等待真实后端 freshness”的闭环，避免几秒内暴露旧关系或假同步。
- 影响范围：`ReconciliationWorkbenchPage` 写操作 gate、`GlobalOperationOverlayProvider`、`web/src/features/operationBarrier/api.ts`、`/api/operation-barrier/status`、`OperationFreshnessBarrierService`。
- 关键决策：前端不再用本地 `applyLocal*` / `updateWorkbenchAfter*` 逻辑伪造 paired/open 结果；写操作统一进入全屏 overlay，先等待 `workbench_relation` barrier，再重新读取 Workbench active generation，只有页面 payload fresh 后释放。barrier 只读 runtime snapshot，不写 readiness、不重建 read model。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md`，并同步 read-models、app-shell、app-architecture、批量账务、免 OA、往来款模块文档。
- 测试覆盖：新增 `GlobalOperationOverlayContext.test.tsx`、`OperationBarrierApi.test.ts`、`test_operation_freshness_barrier.py`；更新 `WorkbenchSelection.test.tsx` 覆盖写操作后等待 barrier 与 fresh reload，不再依赖本地 optimistic 重排。
- 验证命令：见本轮最终执行记录。
- 未测风险：真实生产登录态下的 P50/P95/P99 operation-to-fresh latency 仍需发布后用 approved mutating scenario 或安全 synthetic fixture 度量。

## 2026-06-14 - 撤回可恢复关系策略收敛

- 目标：彻底修复 withdraw preview/submit 中未恢复 row 仍在“操作后”显示成同一行的问题，避免未标记 manual history、自动候选或同 row-set snapshot 污染撤回链路。
- 影响范围：`WorkbenchPairRelationService`、`WorkbenchRelationCommandService` relation mode registry、Workbench withdraw preview API、PostgreSQL relation history replay dry-run。
- 关键决策：可恢复关系由统一策略 `workbench_relation_modes` 判定；真实 active before relation 写入 confirm history 时才由 PairRelationService 标记 `special_metadata.restorable_on_withdraw=true`。外部传入的 display/candidate/history snapshot 不再因为 `relation_mode != existing_case` 就默认恢复；同一 row-set snapshot 永不恢复。
- 清理：移除 withdraw preview 依赖 display/existing_case 的 OA 附件无 history 合成恢复路径；OA 附件 ID 解析不允许把任意旧显示归属恢复为 active relation。2026-07-04 起，父 OA + 自带附件发票改由关系状态机维护不可变 source binding，完整 relation 撤回后必须保留该 binding，纯 OA+自带附件发票撤回必须被阻止。
- 测试覆盖：新增/更新 PairRelationService、Workbench v2 API、relation command service 和 history replay 工具测试，覆盖 owned active snapshot 可恢复、未拥有 manual snapshot 不恢复、同 row-set 不恢复、API after groups 拆行、发布前 dry-run 报告非可恢复 history。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`，并同步 Workbench relation 模块测试/实施说明。
- 未测风险：真实生产数据 dry-run 需要发布前在目标环境执行；本轮本地 fake connection 覆盖审计输出结构，不读取生产库。

## 2026-06-14 - 撤回预览显示归属与可恢复关系边界收敛

- 目标：修复 withdraw preview/submit 把 `existing_case` 显示归属当成可恢复 relation，导致“操作后”银行流水+发票或 OA+发票仍显示在同一行的问题。
- 影响范围：`WorkbenchPairRelationService`、Workbench withdraw preview/submit API、批量账务 withdraw 回归、前端 Workbench mock 和本模块/批量账务文档。
- 关键决策：`relation_mode=existing_case` 默认是读侧 display ownership，不是 relation repository 的可恢复事实；只有真实 active relation snapshot 或显式 `restorable_on_withdraw` 的关系才能在撤回时恢复。历史中已污染的 `existing_case` before_relations 由运行时过滤，避免破坏旧数据。
- 文档影响：更新本模块 `README.md`、`tests.md`、`implementation-notes.md`，并同步批量账务模块 `README.md`、`state-machine.md`、`tests.md`、`implementation-notes.md`。
- 测试覆盖：新增/更新 pair relation service、Workbench v2 API 和 batch accounting API 回归，覆盖新历史写入过滤、旧污染历史过滤、银行+发票撤回后分行、真实上一 relation 仍可恢复。
- 验证命令：见本轮最终执行记录。
- 发布前审计：2026-06-14 已在生产执行只读 SQL 审计，`active_display_only_relation_count=0`、`display_only_history_before_relation_count=3`、`affected_history_case_count=3`，运行时过滤覆盖历史污染，不需要 backfill。
- 未测风险：未执行生产写入型 repair；本次审计结论为无需写入型 backfill。

## 2026-06-13 - Workbench 发票事实源收敛与列交互修复

- 目标：修复关联台三栏列布局、详情 icon 和 selection 高亮问题，同时把 OA 附件正式发票统一 promotion 到 Invoice repository / `app.invoices`，Workbench 发票栏不再从 OA 附件解析缓存临时生成发票行。
- 影响范围：`ImportNormalizationService.upsert_oa_attachment_invoice`、OA attachment cache update callback、Workbench SQL projection、legacy `WorkbenchQueryService`、Workbench relation SQL projection、前端 Workbench columns/selection。
- 关键决策：`app.oa_attachment_invoice_cache` 只保留解析缓存职责；正式发票事实必须以 canonical `Invoice` 写入 import service/repository，并通过 `source_links.source_type='oa_attachment_invoice'` 保留 OA/附件/费用项来源。Workbench SQL 发票行、relation projection、tax/cost 下游都从 canonical invoice/read model 读取。旧 `WorkbenchQueryService` 只在 OA detail 中展示附件解析摘要，不再发布 `source_kind=oa_attachment_invoice` 的 invoice row。
- 文档影响：更新本模块测试矩阵、税金抵扣/成本统计模块记录和运维监控说明。
- 测试覆盖：新增/更新 OA 附件 promotion、Workbench SQL projection、relation projection、legacy query service 不发布发票行、前端列布局和 selection hook 回归。
- 验证命令：见本轮最终执行记录。
- 未测风险：未对真实生产历史 `app.oa_attachment_invoice_cache` 做全量 backfill/dry-run；发布前应对存量 OA 附件正式发票做只读抽样，确认 canonical `app.invoices.source_links` 已补齐。

## 2026-06-18 - Workbench all 聚合等待 parent shard 收敛

- 目标：修复关联台确认关联已写入成功后，前端刷新弹出 `workbench_all_scope_parent_inconsistent: generation_metadata_actual_mismatch ... active_relation_open_membership count=4` 的问题。
- 影响范围：`WorkbenchReadModelRefreshService` 的 `workbench:all` aggregate-only refresh、runtime worker dependency-not-fresh defer、确认关联后 Workbench month/all 后台追赶链路。
- 根因：确认 OA 与两组已闭环外部往来银行流水时，canonical relation 已从旧 `turnover_manual_closure` case 升级为新的确认关系；同一事务也入队受影响月份 Workbench shard 与 `all` aggregate。旧 handler 对携带 `parent_scope_keys` 的 all aggregate 直接从当前 active month generation 聚合，没有先确认 parent month dirty scope 是否仍 pending/processing，于是用“旧月度 generation + 新 canonical relation”做 consistency 校验并把暂态不一致发布成 failed all generation。
- 第二轮复现补充：只检查 parent active 不够。若 parent month scope 已 failed/stale，`workbench:all` aggregate 仍会继续聚合旧 parent generation 并再次写出 parent inconsistent；同时 refresh-status normalization 先看 failed 再看 pending/processing，会让已重新入队的旧 failed 继续显示为当前失败。
- 关键决策：all aggregate 如果声明了 `parent_scope_keys`，必须先通过 durable dirty scope 判断这些 parent `workbench` scope 是否仍 active 或 not fresh；仍在 pending/processing/failed 时抛 `workbench_read_model_not_fresh`，交给 runtime worker 的短延迟 defer 和 dependency refresh 机制重试。真正 parent fresh 之后仍出现 generation inconsistency 才保持 failed，不吞掉坏投影。
- 附带修复：撤回 active relation 但没有历史 relation 快照时，提交路径先使用命令结果、预览和 active relation 的 affected row ids 推导 refresh scope；只有仍推不出时才解析 rows，避免写入已完成后因 scope 反推失败把请求误报为 400/500。
- 状态展示修复：Workbench refresh-status 中同一 scope 旧 failed 已被重新 pending/processing 覆盖时，当前状态必须是 `refreshing`，不再显示旧 `workbench_all_scope_parent_inconsistent` last_error。
- 测试覆盖：新增 `tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_refreshing`、`test_workbench_refresh_handler_defers_all_aggregate_while_parent_scope_failed`、`test_workbench_refresh_status_api_treats_requeued_failed_scope_as_refreshing`；补齐 Workbench v2 API mismatch 请求备注合同，并覆盖 `test_withdraw_link_without_history_falls_back_to_cancelling_active_relation`；前端新增 requeued refresh failure 不显示旧失败 banner 的回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api -q`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_repository tests.test_runtime_worker tests.test_turnover_workbench_integration tests.test_workbench_turnover_grouping tests.test_workbench_auth_context_idempotency -q`；`npm --prefix web test -- --run src/test/WorkbenchSelection.test.tsx src/test/OperationBarrierApi.test.ts src/test/GlobalOperationOverlayContext.test.tsx`。
- 未测风险：未连接真实生产 PostgreSQL 回放用户截图中的具体 case；发布后如仍存在旧 failed `workbench:all` outbox/generation，需要按 runtime worker runbook requeue/归档已覆盖历史 failure，并重跑 Workbench display audit。

## 2026-06-12 - 关联台撤回 preview 分组与后台刷新交互收敛

- 目标：修复撤回 preview “操作后”三栏仍按旧 `case_id` 合并的问题；提交成功后先做本地 optimistic update，后台刷新期间只锁定刚操作 row/group，避免全页面不可操作。
- 影响范围：`Application._relation_groups`、`WorkbenchWriteFacade._withdraw_relation_preview_payload`、`ReconciliationWorkbenchPage` 写操作 gate/pending row lock、`AppHealthStatusProvider` source mapping、Workbench 前端 mock。
- 关键决策：withdraw preview after 中没有进入 after relation 的 row 使用逐行独立 group，并清理 preview-only 旧 relation 展示字段；Workbench active generation stale/loading 只提示刷新，不映射为 `oaSync=dirty`，不全局禁用无关写；真正的 OA sync dirty/refreshing、无权限和 App Health blocked 继续阻断写。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和 `implementation-notes.md`。
- 测试覆盖：新增 backend facade preview 分组回归；新增前端 workbench stale 放行、OA dirty 阻断、提交后 pending group 局部锁；更新 App Health provider source mapping 断言。
- 验证命令：`PYTHONPATH=backend/src python -m unittest tests.test_workbench_auth_context_idempotency.WorkbenchAuthContextIdempotencyTests.test_withdraw_preview_after_groups_unrestored_bank_invoice_rows_individually`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx -t "workbench stale refresh does not globally disable selected group actions|OA dirty sync still disables selected group actions"`；`cd web && npm test -- --run src/test/WorkbenchSelection.test.tsx -t "confirm link locks only the operated group while the background refresh is pending"`；`cd web && npm test -- --run src/test/AppHealthStatusContext.test.tsx -t "reports yellow when the backend says the workbench read model is stale"`。
- 未测风险：尚未做真实浏览器截图/生产数据 smoke；后续如对所有 action 都加入更细粒度 row-scope stale 判断，需要继续补跨 group 并发交互测试。

## 2026-06-12 - 关联台 group 级统一撤回/拆分闭环

- 目标：已配对区和未配对区点击任意 row 都带入完整 group；统一撤回按钮先打开三栏 preview，再由后端判定 `withdraw_relation` 或 `split_candidate`。
- 影响范围：`WorkbenchRelationCommandService` withdraw preview/submit、`WorkbenchWriteFacade.withdraw-link` preview/submit、`WorkbenchCandidateMatchService` suppress 边界、前端 selection model/API mapper/关联预览提交。
- 关键决策：relation 撤回只通过 `WorkbenchRelationCommandService`，submit 使用 `operation_type`、`preview_id`、`submit_expected_versions` 锁定 preview。active relation 有 history 时恢复上一状态；无 history 时撤到无关联。纯自动候选不写 relation history，而是 suppress candidate 为 `manual_override`。
- 文档影响：更新本模块 `README.md`、`tests.md`，并同步 `workbench-relations` 模块文档。
- 测试覆盖：新增 `WorkbenchSelectionModel.test.ts`；更新 `WorkbenchSelection.test.tsx` group context/submit payload；新增 command service withdraw preview lock 和 facade withdraw/split tests；更新 API 无 history 撤回口径和 rollback characterization。
- 验证命令：`python -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_auth_context_idempotency.py -q`；`python -m pytest tests/test_workbench_v2_api.py -k "withdraw_link" tests/test_workbench_write_characterization.py -k "withdraw_link" tests/test_workbench_candidate_match_service.py -q`；`npm --prefix web test -- WorkbenchSelection.test.tsx WorkbenchSelectionModel.test.ts --run`；`npm --prefix web run build`。
- 未测风险：未做真实浏览器/staging smoke；多 group 禁止目前依赖后端 preview/前端单 group button 规则，后续如开放批量选择需要补更专门的交互测试。

## 2026-06-24 - T5 legacy contamination quarantine

- 目标：审计会污染新模块 IO 边界的旧路径，优先确认是否有可安全删除的 route/service/read model/frontend API 入口；证据不足时只做 quarantine，不改业务行为。
- 影响范围：`WorkbenchRowDetailApiRoutes.legacy_row_detail`、`BatchAccountingService.repair_legacy_case_id_collisions`、平台边界静态 guard、T5 handoff。
- 关键决策：`GET /api/workbench/rows/{row_id}` 的旧 row detail fallback 当时仍作为本地兼容路径保留；2026-07-02 后生产 SQL read model runtime 已完全关闭该 fallback。新增 guard 把该 link 限定为唯一 route-owner wiring，并继续禁止它获得 relation command、refresh gateway、dirty/outbox/readiness/cache/App Status 等副作用。`BatchAccountingService.repair_legacy_case_id_collisions` 的 CodeGraph caller 只命中测试，但它是财务关系修复行为，删除条件不足，本轮只记录为 test-observed compat repair surface。
- 文档影响：更新本模块实施记录，并新增 `.planning/refactors/modular-io-boundaries/parallel/handoffs/T5-legacy-contamination.md`；长期业务/API 口径未变化。
- 测试覆盖：新增 `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_legacy_contamination_surfaces_stay_quarantined`，证明新 route owner 没有新增未分类旧内部 link、旧 row detail fallback 不具备写/queue/cache/App Status 副作用、batch accounting repair 没有 app/service active caller。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_contamination_surfaces_stay_quarantined -v`；`python3 -m py_compile tests/test_platform_runtime_boundary_guards.py`；`git diff --check`。
- 未测风险：未跑完整 Workbench/Batch Accounting 回归；本轮无运行时行为变更。真实 PostgreSQL/worker/App Status/high-row/browser evidence 仍 deferred。

## 2026-06-12 - server active relation repair command 写入口收敛

- 目标：删除 `server.py` 中 OA invoice offset auto pair 和 OA 附件上下文 repair 对 `WorkbenchPairRelationService` 的直接写入，避免 Workbench payload build/repair 路径成为第二个 relation 写事实源。
- 影响范围：`Application._sync_oa_invoice_offset_auto_pair_relations`、`_repair_active_relations_with_oa_attachment_context`、`WorkbenchRelationCommandService` mode registry/history override、runtime boundary guard。
- 关键决策：本阶段只迁移 direct mutation，保留原有 read-build repair 触发点、scanned row 保护、外层 persist/lifecycle 行为；server relation 读/展示/persist helper 后续继续抽离。
- 文档影响：更新本模块 `implementation-notes.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_confirm_relation_allows_oa_invoice_offset_auto_match_mode`、`test_replace_existing_confirm_uses_requested_history_operation_type`、`test_server_active_relation_repairs_use_relation_command_boundary`，并运行 OA offset auto pair、source link、防误取消、missing attachment repair 回归。
- 验证命令：见 `workbench-relations` Phase 7J 记录。
- 未测风险：no-OA legacy repair/consolidation 和 batch accounting repair 仍待后续切片迁移或降级为 repair port。

## 2026-06-12 - Workbench exception apply relation command 写入口收敛

- 目标：删除 `WorkbenchExceptionApplicationService` closed apply 直接创建 pair relation 的写入口，把 `normal_match` / `oa_exempt` 纳入统一 relation command lifecycle。
- 影响范围：`WorkbenchExceptionApplicationService.apply`、`WorkbenchRelationCommandService` mode registry、`WorkbenchWriteFacade.apply_exception` rollback/error mapping、Application wiring、runtime boundary guard。
- 关键决策：closed action 在创建本地 exception case 前先执行 relation command preflight；缺 command service 或 relation read model non-fresh 时 fail fast，不留下半写入 case。成功路径通过 `confirm_relation(..., history_operation_type="workbench_exception_apply")` 写 relation，保留 OA exemption/evidence/display tags 等展示字段。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_apply_closed_exception_delegates_pair_relation_to_command_service` 和 `test_workbench_exception_application_uses_relation_command_boundary`，并运行三方闭环、自动/手动免 OA structured fields 回归。
- 验证命令：见 `workbench-relations` Phase 7I 记录。
- 未测风险：`server.py` active relation repair、no-OA legacy repair/consolidation 和 batch accounting repair 仍待后续切片迁移或降级为 repair port。

## 2026-06-12 - 个人暂借款 relation command 写入口收敛

- 目标：删除 `confirm_personal_advance_repayment` 直接调用 `WorkbenchPairRelationService.replace_with_confirmed_relation` 的写入口，把 `personal_advance_repayment_settlement` 纳入统一 relation command lifecycle。
- 影响范围：`WorkbenchWriteFacade.confirm_personal_advance_repayment`、`WorkbenchRelationCommandService` mode registry、Workbench personal advance API 回归、runtime boundary guard。
- 关键决策：缺少 relation command service 时先 fail fast，不创建 exception case；成功路径通过 `confirm_relation(..., replace_existing=True)` 写 relation，保留原有 amount summary、cost exclude metadata 和 response shape。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块文档。
- 测试覆盖：新增 `test_personal_advance_repayment_delegates_relation_write_to_command_service`、`test_personal_advance_repayment_fails_fast_without_relation_command_service`、`test_workbench_personal_advance_repayment_uses_relation_command_boundary`，并运行既有个人暂借款 API 成功/失败回归。
- 验证命令：见 `workbench-relations` Phase 7H 记录。
- 未测风险：其他 exception application relation mode 族仍待单独迁移，不能与个人暂借款混为同一切片。

## 2026-06-23 - 进销项发票方向修复生产权限闭环

- 目标：完成 `2026-06-23-invoice-direction-normalization-v1` 发布后的生产闭环，确保截图中的 5200、4900、400 三栏样例以及同类二栏/三栏自动配对项实际进入 paired。
- 真实原因：代码规则已在生产 release `main-6e8ed50d-20260623093156` 生效，但 Workbench matching worker 重建 scope 时以 `fin_ops_app_runtime` 读取 `app.etc_batch_invoice_links` 被 PostgreSQL 拒绝；`0074_etc_batch_invoice_links.sql` 建表后未给当前统一 runtime 角色授权，导致 12 个 matching scope 全部 failed。
- 处理结果：生产库用 migrator 身份补齐 `app.etc_batch_invoice_links` 对 `fin_ops_app_runtime` 的 `select, insert, update, delete` 权限，并重新排队权限失败的 12 个 `workbench_matching_dirty_scopes`；12 个 scope 最终全部 completed。新增 `0075_etc_batch_invoice_links_runtime_grants.sql` 固化该权限，避免新环境或后续迁移重放继续漏授权。
- 生产验证：`oa-pay-1982 + txn_imported_1258 + inv_imported_0208`、`oa-pay-2065 + txn_imported_1415 + inv_imported_0086`、`oa-pay-2079 + txn_imported_1456 + inv_imported_0070` 均生成 `paired / oa_bank_invoice_exact_amount / 2026-06-23-invoice-direction-normalization-v1`；旧 `multiple_three_way_candidates` 决策已 expired。
- 全局验证：生产新规则版本下 paired 覆盖 `bank_invoice`、`oa_bank`、`oa_bank_invoice`、`oa_invoice`；`job.workbench_matching_dirty_scopes` 状态为 `completed=12`，无 dirty/retry/processing/failed；生产 API、dispatcher、`workbench-matching`、`workbench-relation`、`workbench` worker 均 active。
- 测试覆盖：`tests/test_postgres_migrations.py` 增加 migration 列表和 runtime grant contract，防止 `app.etc_batch_invoice_links` 后续缺少 `fin_ops_app_runtime` 权限。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations.PostgresMigrationDiscoveryTests.test_expected_migration_files_are_present_and_ordered tests.test_postgres_migrations.PostgresMigrationSqlTests -v`；生产 SQL 权限验证、matching scope 重排轮询、目标 row decision 查询和 `sudo -n /usr/local/sbin/finops-deploy-control status`。
- 未测风险：未重新执行完整 `scripts/deploy-oa.sh` 发布包含 `0075` 的新 release；当前生产库已直接授权并完成重建，`0075` 将在下一次标准部署时作为幂等迁移记录进入 schema migration 链。

## 2026-06-23 - 多 OA active relation 后端行级归属证据闭环

- 目标：把三栏配对区域多 OA 大组内的同源同排能力从前端 fallback 提升为后端事实源，避免 active relation 只有大组 `row_ids` 而缺少 bank/invoice 对应 OA 的 row-level evidence。
- 影响范围：`WorkbenchRelationAlignmentService`、`WorkbenchSqlProjectionBuilder._group_payload`、Workbench SQL projection schema version、`audit_workbench_relation_display`、Workbench API mapper、关联台三栏分段展示。
- 关键决策：后端只发布可证明归属。证据优先保留 OA 附件发票 `derived_from_oa_id` 并归一 `oa-exp-*:item:*` 到父 OA；银行流水先做唯一同金额，再做唯一 2 到 6 条金额合计闭合。重复金额或多个可选组合不猜测，写入 unresolved/diagnostics 并由审计暴露。前端继续 source-first，金额 fallback 只作为同一 group 内的展示兜底。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和 `docs/dev/api-contracts.md`。
- 测试覆盖：新增 `tests/test_workbench_relation_alignment_service.py`；新增 SQL projection、relation command metadata、audit tool 和前端 API mapper 回归。
- 验证命令：`python -m pytest tests/test_workbench_relation_alignment_service.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_emits_source_oa_for_deterministic_multi_oa_relation_alignment tests/test_workbench_relation_command_service.py::WorkbenchRelationCommandServiceTests::test_confirm_relation_preserves_explicit_row_alignment_metadata tests/test_audit_workbench_relation_display_tool.py`；`cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/groupDisplayModel.test.ts src/test/CandidateGroupGrid.test.tsx`。
- 未测风险：未连接真实生产 PostgreSQL 回放截图 case；发布前需要先跑只读 relation display audit，并让 Workbench active generation 按新 schema 重建。歧义金额关系不会自动修复，必须人工确认或由上游写入显式 `row_alignment`。

## 2026-06-12 - confirm/cancel relation command 写入口收敛

- 目标：删除关联台 `confirm-link` / `cancel-link` 在缺少 `WorkbenchRelationCommandService` 时回退到 `WorkbenchPairRelationService` 直接写 pair snapshot 的 legacy fallback。
- 影响范围：`WorkbenchWriteFacade.confirm_link`、`_confirm_link_with_uow`、`cancel_link`、`_cancel_link_with_uow`、Workbench idempotency/UoW characterization tests、workbench relation boundary guard。
- 关键决策：非 UoW 路径缺 relation command service 返回 `workbench_relation_command_unavailable`；UoW handler 中也必须通过 transaction-bound command repository 写入，不再调用 `_persist_workbench_pair_relations_in_transaction` 旧 hook。idempotency replay/in-progress 判断仍优先于 handler 内 command 可用性。
- 文档影响：更新本模块 `README.md`、`tests.md` 和 `workbench-relations` 模块实施记录。
- 测试覆盖：`test_confirm_and_cancel_link_fail_fast_without_relation_command_service`、`test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback`，并更新 `tests/test_workbench_write_characterization.py` 的 UoW fakes 以记录 command repository 写入。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_auth_context_idempotency.py tests/test_workbench_write_characterization.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_workbench_confirm_and_cancel_link_have_no_direct_pair_write_fallback -q`。
- 未测风险：个人暂借款、exception application、server active relation repair 等 Workbench-adjacent relation 写入口仍待后续切片迁移。

## 2026-06-11 - 外部往来 bank-only 闭环保持 open

> 历史记录：本节的 paired 分区规则在 2026-06-22 重新成为当前口径；当前规则要求 `turnover_manual_closure` 未满足 paired 条件时留在 open 待处理区。

- 目标：修正外部往来手动闭环在关联台的分区语义，移除 `bank-only + turnover_manual_closure + exactly 2 bank rows` 进入 paired 的例外。
- 影响范围：Workbench candidate grouping、server pair relation display payload、Workbench read model schema version、外部往来 closure integration、关联台本地 optimistic update。
- 关键决策：`turnover_manual_closure` 仍是 Workbench active pair relation 事实源，但 bank-only 只表示外部往来款内部闭环和行占用；关联台 paired 仍要求 OA + 银行 + 发票三栏完整。外部往来页只可撤回 bank-only open relation，三栏 paired relation 必须在关联台撤回。
- 文档影响：更新本模块 `state-machine.md`、`tests.md` 和本实施记录；同时同步 turnover-ledger 模块与产品/API 文档。
- 测试覆盖：`tests/test_workbench_turnover_grouping.py` 覆盖 bank-only open；`tests/test_turnover_workbench_integration.py` 覆盖 confirm 后 open、bank-only withdraw cancel、三栏升级后拒绝外部往来页撤回；`web/src/test/WorkbenchSelection.test.tsx` 覆盖 turnover bank-only optimistic update 不进 paired。同步 bump Workbench SQL/legacy read model schema version，避免旧 active generation/cache 继续被当成 fresh。
- 验证命令：见本轮最终执行记录。
- 未测风险：未运行真实生产库 active generation 全量回放；发布前如存量 `turnover_manual_closure` paired 数据较多，应做只读抽样确认分区变化符合业务预期。

## 2026-06-11 - active relation 重复 OA 去重防线

- 目标：修复关联台 paired 详情中出现两个一模一样 OA 的问题，并防止后续 active relation payload 再携带重复 row id 或跨 active case 复用同一 row。
- 影响范围：`WorkbenchPairRelationService`、`Application._relation_groups`、relation integrity repair、pending invoice attach existing relation 合并逻辑、Workbench/Pending invoice 相关测试和模块文档。
- 关键决策：真实原因不是前端误渲染两条不同 OA，而是 active relation 的 `row_ids` 中存在重复 OA row id，后端 grouping 原样展开导致同一 OA summary 出现两次。修复点放在 relation 写入 normalize、snapshot normalize、repair plan 和 query grouping 四层；同一 row id 若出现冲突 row type 直接失败。
- 文档影响：更新本模块 `README.md`、`state-machine.md`、`tests.md` 和本实施记录。
- 测试覆盖：新增/更新 `tests/test_workbench_pair_relation_service.py`、`tests/test_workbench_pair_relation_integrity_repair.py`、`tests/test_workbench_api.py`，并通过 pending invoice service/API 回归保护 relation 合并路径。
- 验证命令：`pytest tests/test_workbench_pair_relation_service.py tests/test_workbench_pair_relation_integrity_repair.py tests/test_workbench_api.py -q`；`pytest tests/test_pending_invoice_service.py tests/test_pending_invoice_api.py -q`。
- 未测风险：未对生产历史库执行全量 repair dry-run；发布前如怀疑存量 relation payload 已污染，应先跑只读 repair plan 并抽样 paired 详情。
- 后续事项：后续所有写 active relation 的模块必须复用 pair relation service/repository，不在页面或 server handler 中手拼可重复 row payload。

## 2026-06-11 - 测试闭环矩阵与状态机补齐

- 目标：执行测试闭环 master goal 的 reconciliation-workbench 模块轮次，审计关联台页面/API/read model/worker/下游 fan-out 测试覆盖。
- 影响范围：本模块 `tests.md`、`state-machine.md`、`implementation-notes.md`；未改变产品业务口径。
- 关键决策：关联台最小闭环命令覆盖候选规则、matching orchestrator、query facade/cache、dirty queue/worker、active generation 关键 SQL runtime、核心 API action 和前端 Workbench API/selection/grid；完整历史回归由 nightly `verify.sh all` 和按改动选择的扩展命令承担。
- 文档影响：补齐影响面清单、场景覆盖清单、七类测试适用性、历史 bug 回归库、关键 smoke flows、验证命令和未测风险。
- 测试覆盖：沿用现有 Workbench 后端和前端测试；本轮未新增代码测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_rules tests.test_workbench_free_matching_engine tests.test_workbench_matching_orchestrator -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_query_facade tests.test_workbench_dirty_queue_wiring tests.test_workbench_matching_dirty_scope_worker -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_repository_groups_page_pins_versions_counts_and_rows_to_single_active_generation tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_workbench_refresh_status_api_exposes_dirty_scopes_and_worker_lag -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_get_api_workbench_keeps_oa_bank_exact_sum_candidate_in_one_open_group tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_and_cancel_link_defer_read_model_persistence_to_background -v`；`cd web && npm test -- --run src/test/WorkbenchApi.test.ts src/test/WorkbenchApiRuntimePath.test.ts src/test/WorkbenchSelection.test.tsx src/test/CandidateGroupGrid.test.tsx`。
- 未测风险：不运行真实生产库 active generation 全量回放；前端视觉/大数据性能需要浏览器或 staging smoke。
- 后续事项：下一模块继续处理 `bank-details`。

## 2026-06-10 - OA 与多银行流水合计候选

- 目标：支持 1 条 OA 与唯一一组 2 到 6 条同方向银行流水按分精度合计等于 OA 金额时自动形成 OA-bank 候选，继续等待发票。
- 影响范围：`WorkbenchMatchingRules` legacy candidate mode、`WorkbenchFreeMatchingEngine` decision mode、matching orchestrator、candidate grouping、Workbench API payload/read model invalidation。
- 关键决策：
  - 规则名为 `oa_bank_exact_sum`。
  - 单笔 `oa_bank_exact_amount` 优先；若已生成单笔 OA-bank 精确候选，不再生成多银行合计候选。
  - 每条银行流水必须复用现有 OA-bank evidence，不允许只靠金额。
  - 同一 OA 存在多个等额银行流水组合时不自动选择。
  - legacy candidate 生成 `candidate_type=oa_bank`、`status=incomplete`，让 OA 和多条银行流水进入同一个 open candidate group。
  - decision mode 生成 `WorkbenchDecision(match_shape=oa_bank, rule_code=oa_bank_exact_sum, payment_amount_closed=True)`，供 SQL decision/read model/worker 链路消费。
- 文档影响：已更新 `docs/product-specs/reconciliation-and-workbench.md`、本模块 `state-machine.md` 与 `tests.md`。
- 测试覆盖：
  - `tests/test_workbench_matching_rules.py` 覆盖 legacy 规则正例、唯一性、证据要求、单笔精确优先。
  - `tests/test_workbench_free_matching_engine.py` 覆盖 decision mode 正例、歧义、证据要求、单笔精确优先。
  - `tests/test_workbench_matching_orchestrator.py` 覆盖 legacy candidate 持久化、decision store 持久化和 read model invalidation。
  - `tests/test_workbench_v2_api.py` 覆盖 Workbench API payload/grouping 中 OA 与多条银行流水保持同一个 open candidate group。
- 验证命令：见 `tests.md` 的 Workbench 相关验证命令。
- 未测风险：未新增前端组件测试；当前变更沿用既有 open candidate group shape。未做真实生产库 worker dry-run。
- 后续事项：可单独评估 legacy candidate 与 decision/free engine 的规则收敛；不要和本规则混入无关旧逻辑删除。

## 2026-07-02 - active generation bulk persistence performance slice

- 触发事实：生产 `read_model_slo_smoke` 1s/5s 重采样显示 `workbench` handler 长尾；远端只读 profile 证明 `workbench:2026-03` 取数、补行、分组约 `2.23s`，但 worker handler 可到 `9-10s`，瓶颈集中在 active generation rows/groups 保存。
- 决策：不改变 Workbench active generation 模型、不改页面 payload、不恢复 legacy live fallback；只把 `read_model.workbench_rows` 和 `read_model.workbench_groups` 持久化加入 repository multi-values 批量写白名单，保持 `workbench_group_rows` 既有 bulk path。
- 测试覆盖：`tests/test_postgres_repositories_boundaries.py::test_read_model_bulk_insert_prefers_multi_values_path_for_allowlisted_tables`，以及 `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_batches_all_scope_generation_rows_when_supported`、`test_repository_batches_workbench_generation_rows_when_supported`。
- 发布后证据：release `pscip-l4-bulk-persistence-abcca6f78` 的 `workbench:2026-03` 5s run enqueue-to-fresh `5281.538ms`、handler `4946.075ms`；1s run enqueue-to-fresh `3873.533ms`、handler `3633.558ms`。相比部署前 `6.35s-9.64s` handler 有下降，但仍是 5s/1s 失败项。
- 未闭合：需要继续 profile Workbench active generation 的分组计算与保存阶段，确认 `workbench_rows/groups/group_rows` 写入后的剩余热点；24h write-operation audit 仍显示 Workbench relation confirm/withdraw cross-page fan-out p95 `19.6s-66.0s`，需受控真实写样本验证 UoW target fan-out 是否已缩短。

## 2026-07-02 - relation alignment bounded subset performance slice

- 触发事实：release `pscip-l4-bulk-persistence-abcca6f78` 发布后，`scripts/rehydrate-workbench-read-models.py --scope 2026-03 --profile-internal` 显示 month shard rebuild 约 `4.03s`，保存阶段约 `393ms`，剩余主要在 `_group_payload`；只读细分 profile 显示 `WorkbenchRelationAlignmentService.align_relation` 32 次中有单次约 `870ms`。
- 根因：`align_relation` 为了判断一个 OA 是否对应唯一 2-6 条银行流水合计，旧逻辑枚举 `itertools.combinations(indexed_bank_rows, size)`。大 active relation 中银行行较多时会出现组合爆炸，污染 Workbench read model handler。
- 决策：保持 relation alignment 输入/输出 payload 不变，删除全组合枚举，改为按金额的有界动态规划状态表。每个金额只保留唯一组合或 ambiguous 标记，超过最大目标金额直接剪枝，状态超过上限时保守返回 ambiguous，不猜测银行归属。
- 测试覆盖：`tests/test_workbench_relation_alignment_service.py` 新增大关系唯一合计与 ambiguous 合计不猜测回归；复跑 Workbench generation batching tests。
- 发布后证据：release `pscip-l4-alignment-d725fdb6d` 中 `workbench:2026-03` profile month shard rebuild `1299.692ms`，`builder._group_payload` `334.799ms`，保存阶段 `391.616ms`；targeted 1s SLO 仍 fail，`enqueue_to_fresh_ms=2801.281`、`handler_duration_ms=2559.983`。
- 未闭合：Workbench 已从 5s 失败项降到 5s pass，但仍不是稳定 1s；`all` parent aggregate profile 仍约 `13.97s`，真实 confirm/withdraw 写操作还缺受控 post-deploy 样本验证。

## 2026-07-02 - Workbench source_version 输入与 generation 明细旧 upsert 删除

- 触发事实：release `pscip-l4-main-poll-chunk-d51665816` 生产 profile 显示 Workbench worker handler 约 `1.94s`，其中存在 event 已携带 `source_version` 但 builder 仍查询 dirty scope source version 的冗余 I/O；后续 profile 证明剩余热点集中在 `save_workbench_read_models(changed_scope_keys=2026-02)` 的 generation 明细写入。
- 决策：保持 Workbench active generation 原子发布和 `workbench:all` parent aggregate 例外，不迁移成普通 read model gateway。handler 输入边界改为直接消费 durable queue event 的 `source_version`；repository 写入边界改为新 generation 明细 insert-only，删除 `workbench_rows/groups/group_rows` 上旧 `(generation_id, scope_key, ...) ON CONFLICT DO UPDATE` 分支。
- 代码影响：`WorkbenchSqlProjectionBuilder.rebuild_workbench_read_model_scope(...)` 只在 `source_version is None` 时查询 dirty scope source version；`PostgresReadModelRepository.save_workbench_read_models(...)` 和 `_refresh_workbench_all_scope_from_month_shards(...)` 的 rows/groups/group_rows 明细写入不再包含旧 conflict update。snapshot、summary、generation start/activate/fail 的状态机不变。
- 测试覆盖：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_sql_projection_month_rebuild_defers_all_scope_aggregation` 锁定传入 source_version 时不得查询 dirty scope；`test_repository_persists_workbench_groups_alongside_rows_and_snapshot`、`test_repository_persists_workbench_rows_alongside_snapshot` 锁定 generation 明细不再包含旧 conflict 分支；复跑 Workbench SQL runtime、runtime worker、SLO smoke 和 PostgreSQL connection tests。
- 生产证据：release `pscip-l4-workbench-insert-5f530d1b5` 部署后 backend/worker cwd 与 PYTHONPATH 均指向新 release，生产源码 `DETAIL_CONFLICT_COUNT=0`，scope contract default/invalid-scope 均 `ok=true`。一次 critical 5s gate 16/16 pass，max `3601.804ms`；最新重采样 14/16 pass，Workbench 在该 grouped run 中 `4183.895ms`，未成为 5s fail 项。
- 未闭合：Workbench 1s targeted smoke 仍 fail，最新样本 `1485.007ms`；按新 release 激活时间过滤后没有真实 confirm/withdraw/no-OA withdraw 写操作样本。关联台不能声明“非常高性能”闭环，下一步应以受控真实写样本或 handler profile 决定是否拆 Workbench 写 worker lane、压缩 snapshot payload 或继续优化 save transaction。

## 2026-07-02 - Workbench generation raw payload write amplification

- 触发事实：release `pscip-l4-workbench-insert-5f530d1b5` 当前 profile 显示 `workbench:all` aggregate handler 多次 `7.7s-16.3s`；active all generation 约 `1701` rows、`960` groups、`1941` group_rows。无写 shadow profile 为 `3309.583ms`，其中 `aggregate_payload=1104.259ms`、`iter_rows_and_groups=687.310ms`、`build_group_row_records=454.940ms`。
- 决策：不改变 all-scope active generation 语义，也不让页面动态回退 month shards；先删除新 generation 的重复 raw JSON 写入。`payload` 仍是前端/API/read model 的规范输出，`raw_payload` 只为历史数据 fallback 服务。
- 代码影响：`PostgresReadModelRepository.save_workbench_read_models(...)` 和 `_refresh_workbench_all_scope_from_month_shards(...)` 对 Workbench snapshot、summary、rows、groups、group_rows 的 `raw_payload` 写 `{}`，避免把同一 payload 再包一层 `normalized_payload` 写入 TOAST。
- 测试覆盖：`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_repository_writes_workbench_payload_without_duplicate_raw_payload` 和 all-scope batch test 断言 payload 保留、raw payload 为空。
- 发布后证据：release `pscip-l4-workbench-raw-51cba11e8` 上 `/health/ready` ready，runtime release 指向新路径；scope contract default/invalid-scope 均 `ok=true`。critical 5s SLO `16/16` pass，max enqueue-to-fresh `3581.490ms`；targeted `workbench:all` 1s SLO pass，enqueue-to-fresh `397.159ms`、handler `352.381ms`。
- 生产 raw payload 证明：active `workbench:all` generation 的 snapshot、summary、`1701` rows、`960` groups、`1941` group_rows 全部 `raw_payload={}`、`raw_has_normalized=0` 且 canonical `payload` 非空；active `workbench:2026-02` 同样满足该合同。
- 未闭合：当前 release 后没有真实 Workbench relation confirm/withdraw、bank-invoice/bank-turnover confirm/withdraw 或 no-OA withdraw 写样本；关联撤回和跨页面 fan-out SLO 仍需 Admin Token/authenticated HTTP 或受控真实写样本验证，不能只用 read model smoke 声明 full external PSCIP-L4 closed。

## 2026-07-05 - 关联操作与异常处理右侧抽屉改造

- 目标：把关联台“确认关联”“撤回关联”和“统一异常处理”的居中弹窗改为右侧抽屉，并让详情内容更紧凑、减少内部英文 code 和业务无关 ID 展示。
- 影响范围：`ReconciliationWorkbenchPage` 的 `RelationPreviewDialog`、`WorkbenchExceptionModal`、共用 `AppDrawer`、关联台前端样式和相关前端测试；不改变后端 API payload、relation 写入、read model scope 或 worker 合同。
- 关键决策：复用项目现有 `AppDrawer`/HeroUI Drawer，而不是新增平行抽屉壳；`AppDrawer` 增加 `ariaBusy` 与 `closeDisabled` 支持，保证提交中的确认/撤回抽屉不能误关闭，且忙碌态仍落在实际 dialog 元素上。
- UI 决策：关联预览抽屉保留“操作前/操作后”三栏核对表，标题区压缩为操作类型、OA/流水/发票计数和状态标签；统一异常处理抽屉把选择计数放入 header，金额摘要、识别依据、处理提示、动作和必填字段使用紧凑卡片。
- 字段口径：统一异常处理不再展示 `oa_equals_bank_missing_invoice`、`CASE-...`、`Warnings`、规则版本或 action code 这类内部英文标识；未知后端 code 在 UI 中降级为中文“待确认”类文案。
- 旧链路清理：删除未挂载的旧 `OaBankExceptionModal`、旧 `oaBankExceptionOptions`、旧前端 `submitOaBankException` client、旧测试 mock 分支、旧组件测试和旧 modal 样式；保留后端 `/api/workbench/actions/oa-bank-exception` 兼容 endpoint，因为它仍有独立后端合同测试，不属于本次前端抽屉链路。
- 测试覆盖：更新 `CommonPlatformComponents.test.tsx` 覆盖共用抽屉 busy/close disabled；更新 `WorkbenchExceptionModal.test.tsx` 覆盖中文关系展示、候选分组 ID 隐藏和抽屉提交；更新 `WorkbenchSelection.test.tsx` 覆盖确认/撤回抽屉忙碌态、模态抽屉背景不可访问语义、异常处理抽屉提交后已处理异常链路；更新 `workbench-exception-flow.spec.ts` 覆盖浏览器异常处理抽屉不展示内部 case id。
- 验证命令：`cd web && npm test -- --run src/test/CommonPlatformComponents.test.tsx src/test/WorkbenchExceptionModal.test.tsx src/test/WorkbenchSelection.test.tsx`；`cd web && npm run build`；`cd web && npm run e2e -- e2e/workbench-candidate-split-flow.spec.ts e2e/workbench-withdraw-flow.spec.ts e2e/workbench-exception-flow.spec.ts --project=chromium`；`bash scripts/verify.sh docs`。
- 未测风险：尚未人工验收所有屏宽下的视觉密度；E2E 已覆盖核心确认、撤回和异常处理流程，但未跑完整 `npm run e2e:smoke`。

## 2026-07-14 - decision-origin 正式关系被 open 列表误过滤

- 触发事实：进项发票使用情况可见云南立孚科技 `520.00` 发票 `inv_imported_0369`、已完成 OA `oa-pay-2169` 和 active linked relation；关联台 active generation 的精确 group detail 也存在，但 `month=all` / `2026-05` open groups list 均返回 0。
- 根因：matching engine 正式化自动决策时保留 `decision:*` 作为 case id，同时写入 `relation_mode=manual_confirmed`。旧 groups list SQL 与 all-scope classifier 仅凭 `case:decision:*` / `decision:*` 前缀把该正式关系当作 `automatic_decision` 删除，混淆了历史来源 identity 和当前 relation state。
- 决策：不改 canonical relation、active generation、worker 或下游 relation distribution。repository groups list/detail 与 all-scope classifier 改为当前正式状态优先；真正无正式 mode 或明确 `automatic_decision` / `automatic_match` 的旧组继续隐藏。删除列表 materialize 后的重复 Python filter，保持 SQL 层 count/pagination 与可见集合一致。
- Cache：复用 `WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION` 并让 API 与 worker warmer 使用同一 schema；部署后旧空列表 Redis payload 自动 miss，无需 bump projection schema 或重建数据。
- 测试覆盖：`test_repository_composed_all_open_page_keeps_formalized_decision_origin_group` 同时证明旧 automatic group 被移除、正式化 decision-origin group 被保留且 counts 正确；`test_repository_group_detail_distinguishes_formalized_decision_origin_relation` 保护 detail；`test_workbench_groups_api_redis_cache_key_includes_groups_page_schema_version` 保护 cache invalidation I/O。
- 旧链路清理：全仓扫描确认仅移除 repository groups list 的前缀-only SQL 和重复后置过滤；relation mode registry、downstream distribution、projection cleanup 与 withdraw 对未正式化 decision 的拒绝继续保留。
- 数据安全：修复是纯 read-side 查询和缓存键变更，不写 canonical facts、read model rows、dirty scope 或 outbox。生产恢复只需发布代码并只读复核目标 list/detail/page audit；不执行 repair SQL 或 read model rebuild。

## 2026-07-14 - 正式关系二态与确定性自动正式化

- 目标：关联台用户关系状态只保留 `paired` / `unpaired`；active 正式关系完整成员同组，其余 canonical facts 全部 singleton 可见。
- 完整根因：旧 candidate/decision/open 投影把计算结果混入展示 ownership；部分 repository/filter 又按历史 case 前缀判断可见性，既可能隐藏已正式化关系，也可能把无正式关系的事实合并或隐藏。
- 决策：删除 candidate/decision 表、service、store、engine、API 与前端组件；纯 `WorkbenchFreeMatchingEngine` 只生成可直接提交的 `FormalRelationPlan`，由 orchestrator 在单 relation UoW 中创建或扩展 active 正式关系。
- 安全规则：显式引用查全历史；组合证据 365 日；强证据图连通；币种、方向、各 pane 合计严格一致；支持有界任意 `N:M:K`；金额-only、模糊/date-only、竞争闭合、资源超限和无显式原始引用的红冲退款全部 fail closed。
- 分组不变量：`paired = active relation members`、`unpaired = canonical facts - paired`；旧 `case_id`、candidate metadata、输入 section 与来源 provenance 不能改变 membership。
- 迁移：未来 Release B 的旧状态 drop migration 只 forward-drop 派生旧状态，不触碰 canonical facts/relation/history；发布后必须全量 rehydrate、等待 durable scopes fresh 并执行页面 Audit。
- 固定验收：云南立孚 520 发票/OA active case 必须 paired；13 张合计 1709.49 元但无唯一强证据的发票必须完整显示为 13 个 unpaired singleton。

## 2026-07-15 - Release A 生产投影审计回滚与 v2 修复

- 生产证据：release `main-1f1ec5324-workbench-formal-relations-hotfix-20260715060112` 激活并完成受控 rehydrate 后，Workbench freshness 与 queue 均正常，但 page Audit 阻断：51 个 `workbench_etc_summary_details_mismatch`、2 个 `workbench_override_exception_fields_mismatch`，active group rows 从基线 1296 降为 1291。生产随即回滚到 `etc-import-e5d6e6a4e-20260714-visibility` 并重新 rehydrate，恢复 219 个 active relations、19 个 active generation scopes、876 个 relation row ids、1296 个 group rows、零审计问题；0001–0103 migration 状态未变化，未执行 0104。
- 根因一：二态 grouping 将未配对 ETC summary 当普通 singleton 输出，嵌入的 `etc_invoice_detail_rows` 没有转换成 `collapsed_rows`；paired ETC summary 又只存放于 group 的独立 `summary_row`，repository 的 row/group-row 迭代器未物化该独立行。因此 canonical ETC 明细存在，但结构化 read model 丢失 51 条展示成员。
- 根因二：没有 active relation ownership 的 canonical row 仍可能携带历史 `candidate:` / `decision:` / `temp:` case id、`automatic_decision` / `automatic_match` mode 与 reconciliation decision decoration，导致未配对行错误暴露旧候选归属，并与 canonical override 的空值不一致。
- 修复边界：纯 `WorkbenchRelationGroupingService` 负责把 ETC summary 映射成 paired/unpaired 对应的 collapsed display，并按当前 relation-mode registry 从 unpaired 输出剥离非正式 ownership；`PostgresReadModelRepository` 在既有 read-model sanitation 边界移除 retired decision decoration，并物化独立 summary row 与 collapsed detail rows。没有恢复 candidate service、第三种状态、fallback 或业务写链路。
- 版本与缓存：projection schema 升级为 `2026-07-15-formal-relation-partition-v2`，all-scope builder 升级为 `workbench_sql_projection.composed_active_month_shards.formal_relation_partition.v2`；groups page Redis cache 直接复用 month projection schema，确保旧 v1 payload 自动 miss。该变更无 schema migration，不修改 canonical facts、active relation/history、dirty scope 或 outbox。
- 回归保护：新增未配对旧 candidate ownership 清理、未配对 ETC summary 全明细保留、独立 ETC summary row/group-row 物化和 cache/projection schema 同步测试。新 release 只有在 full local gate、分支/main 精确 SHA CI、受控生产 rehydrate、page Audit 零阻断、520 paired、13 张发票完整 unpaired 和数据基线不变后才能保持 active；否则继续回滚旧 release。

## 2026-07-15 - v2 生产审计二次回滚与 v3 override 优先级修复

- 生产证据：PR #5 merge SHA `a127c58c7d3cdfc8fd0a34216eb9cf1523f30bef` 的分支/main 全量 CI 均通过；release `main-a127c58c7-workbench-audit-v2-20260715072607` 激活和 19-month rehydrate 后，51 个 ETC summary mismatch 已归零，但 Audit 仍阻断 5 个 `workbench_override_exception_fields_mismatch`。其中 3 个 active override 的 `relation_mode=pending_input_invoice` 被投影成 null，2 个 active override 的 `case_id=null` 被同 row 的历史 candidate exception projection 覆盖。生产立即回滚并 rehydrate `etc-import-e5d6e6a4e-20260714-visibility`，再次恢复 `pass/fresh/drained`、219 relations、19 scopes、876 relation rows、1296 group rows和零问题。
- 根因：纯 grouping 对所有未进入正式 mode registry 的 `relation_mode` 做了过宽删除，误伤 canonical active override；SQL projection 又先应用 row override、后应用 exception projection，而 page Audit 与 canonical 合同明确规定存在 active override 的 row 不再由 exception case 接管。
- v3 修复：未配对 grouping 只清除与 `candidate:` / `decision:` / `temp:` case ownership 绑定的 mode/amount 装饰，不对白名单外 override 字段做推断；projection 在 exception 成员集合中排除 active override row，使唯一 control owner 与 Audit SQL 一致。没有增加 I/O、fallback、第三种状态或新持久化路径。
- 版本：month projection 升级为 `2026-07-15-formal-relation-partition-v3`，all-scope builder 升级为 `workbench_sql_projection.composed_active_month_shards.formal_relation_partition.v3`，Redis groups cache 继续直接复用同一 month schema。仍无 schema migration，Workbench 旧状态 drop migration 不进入本 release。
- 回归保护：新增 `pending_input_invoice` active override 保留测试，以及 row override 与 exception case 同时命中时 override 胜出的 service 测试；生产必须再次通过完整本地/远端双 CI、受控 rehydrate 和零阻断 Audit 才能保持 active。

## 2026-07-15 - v3 生产审计三次回滚与 v4 正式关系优先级修复

- 生产证据：PR #6 merge SHA `427f8efac75d1dfbfa2d1d3f433a078c3afabe39` 的 branch/main 精确 SHA CI 均通过；release `main-427f8efac-workbench-audit-v3-20260715083006` 激活并完成 19-month rehydrate 后，51 个 ETC mismatch 与 3 个合法 override mode mismatch 均归零，但 Page Audit 仍阻断 `oa-pay-1982`、`txn_imported_1258` 两个 `case_id` mismatch。生产立即回滚并 rehydrate `etc-import-e5d6e6a4e-20260714-visibility`，恢复 `pass/fresh/drained`、219 relations、19 scopes、876 relation rows、1296 group rows和零问题；migration 仍只到 0103。
- 完整根因：这两个 row 已是同一 active formal relation 的成员，同时保留历史 active override/exception。v3 正确建立了未配对控制优先级，但 projection 仍在识别 formal members 前读取旧 controls，随后 relation enrichment 只覆盖部分 ownership 字段；Page Audit 又无条件把 override 当最高事实，因而把正式关系 case id 错报为应等于旧 override null。问题不在 repository JSON 持久化，而是 formal relation 与 legacy control 的边界优先级缺失。
- v4 修复：builder 从本次已经加载的 active relations 计算 member row ids，并在既有批量查询前从 override/exception 输入集合排除；Page Audit 同样从 active formal relation members 排除 control equality。统一优先级为 formal relation > override > exception，未配对 override/exception 行为不变。没有新增 SQL round trip、表、worker、fallback、第三种状态或 canonical 写入。
- 版本与验证：month projection 升级为 `2026-07-15-formal-relation-partition-v4`，all-scope builder 升级为 `workbench_sql_projection.composed_active_month_shards.formal_relation_partition.v4`。新增生产 identity 形状的 formal-relation/override/exception 冲突测试，并验证最终 repository row payload 不含旧 control decoration；Page Audit SQL 测试锁定同一 precedence。Workbench 旧状态 drop migration 仍不进入本 release。

## 2026-07-16 - 默认 all-scope 首屏批量读取

- 触发事实：可丢弃 PostgreSQL 受控数据集上，默认 combined initial 延迟虽低于本地门槛，但一次请求仍执行 20 条数据库语句；summary、paired、unpaired 重复读取 active generation/source/status，并分别执行两区 count/page/member 往返。
- 决策：只在 `PostgresReadModelRepository.get_workbench_initial_page(...)` 的私有边界内增加默认 `month=all` 批量路径。它在同一个 repeatable-read 事务中读取一次 generation/source/freshness context，复用既有 canonical summary 与 groups SQL owner，一次读取两区首页、一次批量物化两区可见成员。带搜索、筛选或排序的请求仍走既有窄查询，因此没有第二套 filter SQL。
- 复杂度约束：没有新增 projection、表、索引、缓存、worker、gateway、依赖或公共 repository port；独立 `/groups`、group detail、row detail 以及其他页面的 read model 合同不变。
- 受控证据：默认首屏从 20 条降为固定 7 条语句（包含两条事务设置），形状测试把上限锁定为 10；同规模第二个合成 fixture 的 60 次样本 p50/p95/p99 为 58.581/70.962/109.974ms，payload 341,319 bytes，paired/unpaired 各 200 groups、summary counts 与 generation version 一致。对应 Workbench SQL/query/routes 回归 191 passed。
- 证据边界：前后 fixture 结构相近但不逐字节相同，延迟对比只作方向性实现证据；数据为本机合成、单并发、未经过 Nginx/真实 Redis/浏览器，也未强制清空 PostgreSQL shared buffers，不能表述为生产 SLO 已通过。临时测试数据库已删除；按用户要求不部署、不访问生产，真实基数与并发性能在所有 thread 合并后统一发布验证。

## 2026-07-16 - combined initial 测试合同收口与延期发布

- 最终全量回归发现部分本地集成测试和 Playwright mock 仍依赖已删除的 full-payload/分区首屏行为：写后检查旧 `GET /api/workbench/groups`、combined initial 缺少 `page/page_size/total/row_counts/has_more/read_model_version`，并错误允许 `refreshing` generation 发起关系写入。
- 修复只发生在测试边界：本地状态测试使用 canonical rows + active formal relations 驱动现有纯 `WorkbenchRelationGroupingService`；浏览器 mock 返回当前 combined initial 分页/generation 合同，写后刷新断言改为 `GET /api/workbench`，non-fresh generation 明确禁写。没有恢复 legacy route、runtime fallback、第二 payload owner或新增生产抽象。
- 验证：Workbench SQL/query/routes 191 passed；前端全量测试与 production build 通过；全站 Playwright 179/179 passed；lint、docs、diff 校验通过。全仓后端 4073 个用例只剩 3 个可归属其他并行 thread 的 Pending Invoice、Cost Statistics 和 shared allowlist 失败，本模块/本目标失败为零。
- 发布状态：`deployment_status: deferred_by_user`。本轮未部署、未访问生产、未操作 worker/queue、未执行 Git 打包。所有 thread 合并后必须重新全量验证，再完成 external consumer access log、备份、旧 all-lane drain、统一部署、canary、真实生产性能/隔离性和回滚门。

## 2026-07-16 - unified release readiness 复审

- 当前判定：`implementation_status: verified`，`deployment_status: READY_FOR_UNIFIED_DEPLOYMENT`。该状态只表示关联台可进入已协调的统一部署，不表示已部署或已通过生产性能验收。
- 已闭合门禁：共享 `PlatformRuntimeBoundaryGuardTests` 201/201 通过，未放宽基线；`worker.py` 仅合并重复 import，运行时 service 数量和行为不变。Release A 不包含 Workbench 旧状态 drop migration；OA 专属 `0104_oa_pending_payment_source_snapshot.sql` 保持唯一 0104 owner，Workbench Release B 在证据齐全后使用当时下一个可用版本，不预留空 migration。
- 合并验证：后端无 PostgreSQL 环境矩阵 4084 passed / 35 skipped；一次性本地 PostgreSQL 从空库实际应用 0001–0107 后 4110 passed / 6 skipped；前端 72 files / 855 tests 与 production build 通过；全站 Playwright 179/179 通过；lint、docs、`git diff --check` 通过。一次性数据库均已删除。
- 验证资产修正：PostgreSQL 集成测试迁移到当前 import delta、银行自动标签 owner、Pending Invoice attach-existing owner 和 OA pending payment freshness 合同；删除混入 import 测试的旧 Workbench snapshot/search smoke。`truncate_test_database` 已覆盖迁移声明的全部正式表，防止跨测试 read model/queue/fact 泄漏。
- External-consumer 门禁：已闭合。全仓当前生产代码、前端 client、脚本、probe、worker 和部署文件对旧 summary/full-payload 调用方扫描为零；系统 owner 于 2026-07-16 确认，除官方前端外没有已知脚本、RPA、BI 或第三方系统直接调用 `/api/workbench*`，且该 API 从未作为公共集成合同对外承诺。因旧 full-payload 与当前 combined-initial 共用 `GET /api/workbench?month=...`，单纯 Nginx URL 聚合无法区分新旧 response 期望，因此不再把 35 天 Nginx 日志当作唯一或必要门禁。若未来发现未登记 consumer，停止发布并迁移明确 owner，不恢复 fallback。
- SHA 冻结：排除 `.planning/` 等非发布产物，将三页面的唯一 release commit 作为冻结 SHA；关联台只有在该精确 SHA 的后端、真实 PostgreSQL migrations、前端、E2E、lint、docs、architecture guard 全绿后才保持 `READY_FOR_UNIFIED_DEPLOYMENT`，任一门禁失败即撤回该状态。
- 生产动作：未部署、未迁移生产库、未操作生产 queue/worker、未写生产数据。统一部署后的备份、old all-lane drain、rehydrate、Audit、canary、真实基数/并发性能和三页面混合负载隔离性仍属于部署执行门，不属于本次 READY 判定的本地实现证据。

## 2026-07-17 - all-scope groups 精确统计热路径

- 生产根因：release `main-95f152be8-cost-unchanged-cas-20260717` 上，`GET /api/workbench/groups?month=all&zone=paired&page=1&page_size=50&detail_level=summary` 的 100 次样本 p50/p95/p99 为 5717.908/7482.528/9465.150ms；App Health 证明 handler p50 5540.828ms 中 PostgreSQL p50 5324.911ms。`pg_stat_statements` 将同一 all-scope `count(distinct workbench_group_rows...)` 定位为 108 calls、mean 5337.7ms。该旧 SQL 不仅每次重算，还会把历史 `scope_key='all'` active materialized generation join 回 query-composed month shards，造成 paired bank row count 1005；active-month-only canonical owner 口径为 541，与 combined initial summary 一致。等价轻量只读 SQL 的生产执行时间为 43.874ms。
- grill-me 收敛：不新增表、索引、缓存、worker、queue、公共 API 或共享 read model。复用既有 `read_model.workbench_generation_stats`，在月 generation publish 的同一事务、全部 scope 激活后，计算一次 canonical all summary，并以 active-month generation-set digest 为 `generation_id` 写 paired/unpaired 两条统计；旧 digest 统计同事务删除。
- 读合同：默认无筛选 all-scope groups 只读取精确 digest stats。统计缺失时 repository 返回 miss，现有 `WorkbenchQueryFacade` 返回 `202 refreshing` 并入队；查询末尾再次读取 generation-set digest，发布竞态时同样 fail closed。旧的默认动态 distinct count fallback 及其历史 all-generation join 污染已删除。带用户搜索/来源/列筛选时，单条 SQL 只 materialize 当前 1,407 个 active canonical group key 与 2,626 个 active member key，每个条件先生成去重 matching key 并相交，一次返回 total、row counts 和 matching ids；分页只按 matching ids 取 payload，不再重复成员筛选。
- 隔离性：变更仅位于 Workbench repository/query facade 的既有 I/O；没有修改 canonical facts、relation UoW、成本统计/OA read model、Redis、RabbitMQ、shared freshness gateway 或前端 shape。生产回填只允许通过现有 Workbench rehydrate/refresh 发布 generation，禁止直接 SQL 补 stats。
- 只读生产计划证据（部署前、经本机 SSH tunnel）：生产保留历史量为 groups 1,523,446 / members 2,853,632，active 量仅为 groups 1,407 / members 2,626；代表性银行列筛选 count 的 PostgreSQL `EXPLAIN ANALYZE` 从 2,267.947ms 降到 176.474ms，且计划不再读取历史 materialized all group。该只读证据不替代部署后 HTTP SLO。
- 测试：新增 exact stats hot-path、missing stats fail-closed、generation switch fail-closed、multi-scope 单次最终 digest publish、条件查询 active-key 单次计数/匹配 ids 分页、facade 202/enqueue 和真实 PostgreSQL 同事务写入/缺失 fail-closed。目标本地验证为 Workbench SQL/facade、完整后端、真实 PostgreSQL、前端/E2E、lint/docs；生产必须在部署后 rehydrate，再复验三页面 Audit、写操作后 Audit、关联台 p95 <= 1000ms、成本统计 p95 <= 300ms、OA 真实 page-size 20 p95 <= 250ms。

## 2026-07-21 - 已配对/未配对区域统一搜索

- UI：删除每个 pane 的三套搜索按钮、popover 与 draft/open 状态；已配对和未配对区域各使用一个 HeroUI `SearchField`，与区域标题同一 header 行。两区状态独立，输入继续复用现有 `useDeferredValue` 与 combined initial 请求，不新增 API、请求 fan-out 或搜索服务。
- 搜索合同：唯一 HTTP 字段为 `search`，最长 200 字符，trim 后按不区分大小写的普通文本匹配 active generation 的 OA/流水/发票结构化 `searchable_text`；SQL 显式转义 `%`、`_` 与反斜杠。任一成员命中即返回完整关联组；内部 row/group id 与 detail-only 字段不进入索引。隐藏 pane 或折叠明细仍可命中，摘要未展示命中值时显示“隐藏内容命中”，用户按既有 click-only group detail 链路展开后展示实际高亮。
- 性能与边界：复用 2026-07-17 的 active-member key join 和单次精确 count/matching ids 分页，不扫描 payload/raw payload、不新增表/索引/worker/queue/cache/read model。projection schema 升级为 `2026-07-21-unified-zone-search-v5`，all-scope composed schema 同步 v5，使新增展示字段索引和旧 Redis payload 自动重建/失效。
- Fresh Audit：关联台 Audit icon 的 reset key 绑定 active generation + 页面 read-model status；generation 或 status 改变立即清除旧绿色结果。`workbench_matching_scope_not_converged` 归类为 freshness+queue 阻断，`workbench_generation_source_versions_mismatch` 归类为 freshness 阻断；Audit 仍是 admin on-demand，只读 repeatable-read snapshot，不进入输入热路径。
- 旧链路清理：删除 `WorkbenchPaneSearch.tsx`、`search_mode`、`search_by_pane`、pane-local search state、旧 URL/cache/facade/repository 分支和 session v1；不保留 fallback 或兼容并行链。共享 TaxTable 的同名 CSS hooks仍由 TaxTable 使用，不属于已删除 Workbench 搜索路径。
- 回归责任：覆盖 200 字符 API 边界、ILIKE literal escaping、结构化索引字段/内部 ID 排除、完整组返回、隐藏详情提示与展开高亮、所有可见重复命中、两区搜索隔离、pending/error/retry、cache key、active generation/freshness Audit 失效，以及现有筛选/排序/分页/选择/权限/其它页面回归。
- 首屏竞态修复：生产只读浏览器验证发现搜索框已可操作但 combined initial 尚未完成时立即输入，旧 effect 会提前推进 `lastZoneServerPageQueryKeyRef`，导致首屏稳定数据安装后不再补发服务端全量查询。修复仅删除 loading 分支中的错误 query-key 消费；初始请求完成后，待执行 query 仍由同一 deferred combined-initial effect 发出，不新增状态、请求类型或兼容分支。`WorkbenchPaneFilter.test.ts` 增加延迟首屏期间输入的回归。
- 本地验证：Workbench 后端目标矩阵 400 passed，并包含 71 个子测试；前端 73 files / 870 tests、production build、Workbench Playwright 29/29 均通过。完整后端基线的 8 failures + 3 errors 与完整 Playwright 的 1 个 ETC 只读权限失败均在 clean HEAD 同样复现，和本模块改动无关；Workbench 单个全站 timing 用例单跑通过。
- 生产发布：release `main-23fce735-20260721224107` 已激活；API、dispatcher 与 22 个 required workers active。关联台 Page Audit 为 `pass / fresh / drained`，227 条 active relation、38 个 active generation scopes、909 个 relation row ids、1358 个 active group rows，issue/error/warning/blocking 均为 0；combined initial 为 fresh，paired 157、unpaired 1140，两区首屏各 50 groups。
- 生产浏览器证据：人为延迟首个 combined initial 1.5 秒并在响应前输入，随后观测到 paired 服务端 query；折叠流水仅隐藏内容命中时显示提示，展开后 1 处实际高亮；unpaired 独立查询产生 7 处可见高亮，paired 输入保持不变。两区各 1 个搜索框且与标题处于同一 header 行；全程 0 mutation request、0 browser error。管理员 App Health smoke 与 16 条核心 route-shell smoke 均通过且无写请求。
- 生产性能：浏览器等价 gzip 请求每区预热 2 次后各采样 20 次；paired p50/p95/max 为 `222.619/315.723/401.075ms`，unpaired 为 `514.499/617.169/625.768ms`，结果 total 稳定，均满足本轮 p95 `<=1000ms` 门禁。未压缩诊断请求不作为浏览器 SLO 样本。

## 2026-07-22 - Turnover active ownership 与完成分区纠偏

- 真实原因：`turnover_manual_closure` 在通用分组 policy 中仍有“active 即 complete”的旧特例，绕过 relation 创建时冻结的 OA/发票要求；因此外部往来确认只生成关系的动作，被错误解释为关联台业务资料已齐。
- 边界决策：删除该唯一 bypass，统一复用现有 relation requirement completion policy。active relation 继续拥有同组 case，不拆成 singleton；冻结 requirements 未满足时整组进入 unpaired，全部满足后进入 paired。未知、空或缺失 metadata fail closed。
- 隔离：`batch_accounting`、ETC 显式完成合同保留，普通 manual/deterministic 行为不放宽；不改变 projection schema、SQL shape、API response、cache、worker、queue、权限或前端生产组件。
- 回归：business matrix、SQL production-shape projection、Turnover UoW/integration、frontend mapper/render，以及 no-OA/bank-flow/普通 Workbench 回归共同保护跨页面边界。

## 2026-07-22 - Workbench v6 与可逆历史修复

- month generation 和 all composed schema 同步升级 v6；groups/initial cache 继续由 month schema 自动派生。旧 v5 generation/cache 经既有 freshness gate fail closed，不修改 `workbench_relation` schema、registry、manifest、worker/env 或 API shape。
- 历史 Turnover requirement snapshot 只通过现有 operator repair ops 与 canonical relation command 更新；forward/rollback 都绑定 original execute fingerprint，任一 current-state drift 在首写前终止，rollback 精确恢复完整 metadata preimage。
- 生产只允许 exact release、canonical relation/history 与 active generation restore point、approved fingerprint 和 test-owned 可恢复 scenario 齐全后执行；rehydrate 仍走现有 worker/active-generation 原子发布，禁止直接 SQL mark-fresh。

## 2026-07-22 - Turnover requirement 审计旧豁免清理

- 生产 v6 rehydrate 已把缺 OA 的 Turnover closure 正确投影到 unpaired，但 Page Audit 仍把 `turnover_manual_closure` 无条件列为 requirement exempt，产生“实际 unpaired、预期 paired”的假阳性。这是写链路 bypass 删除后遗漏的审计旧路径。
- 修复只删除 `_is_requirement_exempt_relation(...)` 中该 relation-mode 特例；审计和 projection 现在统一读取冻结的 `requires_oa/requires_invoice` 与实际 typed members。`batch_accounting`、ETC 的既有显式豁免保持不变，无新 I/O、API、schema、worker 或兼容分支。

## 2026-07-22 - matching 与展示投影版本解耦

- 生产事实：Workbench v6 只改变 active relation 的 paired/unpaired requirement 展示分区，但旧 matching source provider 同时携带 `workbench_read_model_schema_version`，导致所有历史 completed scope 被误判为规则过期；`2025-10` 在无关重算中按默认 10 秒 PostgreSQL timeout 连续失败并阻断关联台 freshness Audit。
- 边界修复：从 API/runtime matching provider 删除展示 schema 依赖；bank-flow/no-OA read-model provider 继续显式添加其真正消费的 Workbench projection schema。删除不再使用的 `WORKBENCH_READ_MODEL_SCHEMA_VERSION` alias，不保留兼容分支。
- 运维修复：新增只接受单个 failed month、先 dry-run 后 fingerprint-guarded execute 的 durable retry 工具；工具复用现有 repository mark-dirty I/O，实际处理仍由注册的 matching worker claim/UoW/complete。禁止直接 SQL 或相邻月份扩散。
- worker 修复：worker 入口在专用 matching polling worker 构造前应用 registration statement timeout，避免配置的 120 秒被独立运行路径绕过并退回 10 秒默认值。
- 回归：`tests/test_workbench_dirty_queue_wiring.py`、`tests/test_workbench_matching_scope_retry_ops.py`、`tests/test_deploy_oa_script.py` 与既有 Workbench/Turnover/Page Audit 套件。

## 2026-07-22 - 选择区写入门禁原因与快速恢复

- 目标：修复已选 OA + 银行流水时“确认关联”与“异常处理”只显示灰色、无法判断原因，并避免 OA 已同步后继续等待较慢的全局 App Health 聚合才恢复。
- 真实原因：页面按钮与点击守卫维护了两套重复条件；页面已有 3 秒 `/api/oa-sync/status` 轮询，但按钮只消费全局 App Health 的 OA 快照，导致专属状态已 synced 时仍可能被旧 dirty/refreshing 快照禁用。
- 关键决策：用无 I/O 的 `resolveWorkbenchWriteGate` 统一权限、系统写安全、OA、Workbench page freshness 和 active generation version；按钮、选择区提示和点击守卫消费同一个结果。OA 状态优先使用页面既有专属轮询，首次结果前才回退全局 App Health。删除 `useCanMutateWithHealth` 与页面内三段重复旧判断，不新增请求、worker、read model、API 或跨页面状态。
- 测试覆盖：新增 `WorkbenchWriteGate.test.ts`；扩展 `WorkbenchSelection.test.tsx` 覆盖旧全局 dirty 快照下的 3 秒自动恢复和选择保留；扩展 `WorkbenchZone.test.tsx` 与 `workbench-stale-error-flow.spec.ts` 覆盖可访问禁用原因及 dirty/refreshing 零写入。

## 2026-07-23 - 页面访问不能把缺 canonical 对象的 generation 标成 fresh

- 生产证据：`2026-07` active generation 创建于 OA projection 更新之前，Page Audit 报 `workbench_canonical_object_set_mismatch`，缺少一个已完成 OA 对象；normal Workbench GET 与 refresh-status 却返回 `fresh`。这证明旧 expected source vector 不完整，不是 worker 慢或队列堆积。
- 边界修复：沿用现有 `WorkbenchSqlProjectionBuilder` source-version I/O，month scope 增加该月和 active relation members 的 OA/银行/发票更新时间及 pending claim 版本；`all` query增加对应全量 proof。写命令仍只提交 canonical fact/version，不恢复写后页面 fan-out。
- all-scope composed proof 同步从 active month generations 汇总上述 canonical 字段；月分片发布后 all active-generation-set version仍按既有原子组合模型生成，不另建 `all` generation 或全局状态源。
- 性能约束：proof 仍是一条 bounded PostgreSQL query，不读取 payload、不 live rebuild、不新增网络 I/O；页面 non-fresh 时只 enqueue 当前 scope。生产发布后必须重新验证 Workbench month/all p95、System Audit 与 test-owned confirm/withdraw/recovery。

## 2026-07-25 - Workbench v7 complete proof 与并发读取合并

- `f8ad8b38` 生产三轮证明普通 relation 写约 `172–345ms` 且零 fan-out，但多个并发 consumer 会各自重复 Workbench canonical proof，Workbench/Cost/Turnover access-to-fresh 仍有超过 3 秒样本。队列和 worker 已并发，新增 worker 不是根因修复。
- 当前修复继续使用现有 `WorkbenchSqlProjectionBuilder`：proof 补齐 ETC submission/business/invoice/link、实际消费的银行规则和账户映射、所有 relation 状态、soft delete 与跨月成员；Application 只持有一个 builder，时间上重叠的同 scope proof 共享一个 stdlib `Future`。flight 完成即删除，独立访问重新查 canonical facts，失败可重试；没有 TTL cache、版本表、trigger、协调器或第二事实源。
- month/all schema 升级为 v7；migration `0125` 只增加两个测量后需要的 bank/invoice identity 表达式索引。20 万级本地 replay 中 exact proof 约 `250ms`、30 scope bulk proof 约 `0.77s`，8 个并发 all-scope consumer 只执行一次数据库 proof。v7、migration 与正式 rehydrate 已在 `main-719c9a34-20260725101310` 完成；当前生产矩阵验证最终 fresh/canonical correctness，超过 3 秒只登记为后续性能项。

## 2026-07-25 - Phase 30 关联台并发恢复共享根因优化

- 真实结论：Phase 29 的 `3.106–4.616s` 来自约 `1.8–1.9s` worker、轻量 freshness 轮询和首次 fresh 并发读取叠加，不是单条关联台页面 SQL 持续卡死；同时旧生产 runner 错把滚动分页 `/api/workbench/groups` 当成关联台首屏，性能口径与真实页面不一致。
- 共享修复：generation builder 通过既有 `WorkbenchQueryService` 的 exact/all `list_oa_rows(...)` 窄 I/O 一次读取已序列化 OA rows，不再先构建并丢弃 legacy `get_workbench(...)` summary/group payload后再次扫描、序列化。删除 whole-repo 零调用的 `_legacy_oa_rows(...)`，不保留 fallback。
- 验证合同：可逆 relation runner 改测真实 `GET /api/workbench` combined initial，并按 relation shape 选择业务 zone：完整关系 confirm 在 `paired`，冻结要求未满足的 active Turnover closure 及其 withdraw/recovery 在 `unpaired`。每个断言仍绑定 test-owned identity；`/groups` 只保留页面滚动分页职责。
- 不变项：canonical writes、relation UoW、scope、durable queue、worker registry、freshness gate、active-generation 原子发布、API response shape、前端和其它页面 I/O 均未改变；没有新增缓存、表、索引、migration、worker、协调器或第二 read model。
- 本地证据：608 项定向 service/read-model/API/runner/boundary 回归通过；10,000 OA-row 合成 characterization 的该段 CPU 中位数从 `145.809ms` 降至 `84.885ms`，约减少 `41.8%`。生产候选只允许一次部署，随后集中验证 worker、真实首屏、总恢复、zero fan-out、queue/worker drain 与 System Audit。
- 候选生产复核纠正了原结论：真实 combined initial 在六页面并发写后恢复中达到 `5.487–15.534s`；fresh 热读 exact 为 `0.747–1.625s`、all 为 `1.039–3.102s`，worker handler 多数只有 `57–91ms`，长尾来自无关月份排队而非页面 SQL 或 projection CPU。
- 并发根因：exact 请求先启动月份 refresh 后，all 请求看到 `active_refresh_in_progress=true`，freshness owner 为避免重复 canonical proof 原样返回暂态 stale status；旧 query facade 在没有 `refresh_scope_keys` 时把暂时未知目标回退为 `workbench:all`，进而展开全部月份。生产首次 status proof 证明真正受影响 scope 只有 `2026-03`、`2026-02`，stale reason 均为 `workbench_pair_relations_updated_at_mismatch`。
- 最终修复：`WorkbenchQueryFacade` 在已有 Workbench refresh 进行中且没有 explicit/failed exact target 时不再调用旧 `all` fallback。现有任务完成后，页面下一次轮询重新 proof 并精确补入剩余月份；stable missing/cold-start 的正式 `all` 恢复入口、failed exact scope、自愈和 fail-closed payload 均保留。没有新增状态、I/O、缓存、worker 或协调层。
- 第一候选继续暴露第二条同源旧入口：all freshness status 与 combined initial SQL 之间发生正常 generation-set 切换时，facade 已返回 `workbench_initial_page_version_drift` 并拒绝旧 payload，却额外 enqueue `workbench:all`，再次展开全部月份。最终删除该 enqueue；version drift 只由下一次页面请求重读新 generation 收敛，真正 missing/cold-start 的 all 自愈不变。

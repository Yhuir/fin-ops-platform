# 关联台模块边界与 I/O

日期：2026-07-29

## 职责

### 负责

- 查询 active generation，并把 canonical facts 精确划分为 `paired` / `unpaired`。
- 提供分页、搜索、详情、选择、正式配对、撤回和异常处理页面交互。
- 暴露 freshness/status/source versions，阻止 stale 数据伪装 fresh。
- relation mutation 成功后，只让当前可见关联台通过正常 GET 重校验其访问 scope；非 fresh 时显示 refreshing，不等待写路径扇出的 operation barrier。

### 不负责

- 不把 OA、银行流水、发票复制成新的统一写模型。
- 不持久化自动候选、matching decision 或 `open/proposed` 关系状态。
- 不根据金额、旧 `case_id`、UI metadata 或来源前缀在 route/前端本地推断关系。
- 不直接写 relation SQL、dirty scope SQL 或 outbox SQL。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| canonical rows | OA / bank / invoice repositories | 每行必须有稳定 `id`、`type`、`object_identity_key`；重复 typed identity fail fast |
| OA projection rows | PostgreSQL OA projection repository -> `WorkbenchQueryService.list_oa_rows(...)` | 读取边界把持久化历史值 `section=open` 和缺失值归一化为 `unpaired`；只有 `paired|unpaired` 可进入 Workbench core，未知值 fail fast。日常报销父 OA 可携带精简 `expense_items[{id,row_index,project_name,amount,fee_content,fee_description}]`；这些 item 只用于展示，不能进入 relation member ids。Workbench generation builder 只能通过该 exact/all scope 窄 I/O 读取已序列化 OA rows；禁止先调用 legacy grouped `get_workbench(...)` 构建并丢弃 summary/paired/unpaired payload 后再次扫描、序列化同一批 rows。 |
| active relations | workbench-relations | 只接受 `status=active` 的正式关系；row ids 必须存在且不可跨 case 重叠 |
| row overrides / exception cases | workbench control repositories | 仅对没有 active formal relation ownership 的 row 生效；优先级为 formal relation > override > exception，projection 与 Page Audit 必须共用该合同 |
| list query | Workbench API | `month`、zone=`paired|unpaired`、分页、区域级 `search`、排序、generation/source versions；已配对与未配对各自只有一个不超过 200 字符的搜索词，按普通文本、不区分大小写地查询该区所有 OA/流水/发票结构化展示字段；任一行命中即返回完整关联组，包含当前隐藏 pane 与折叠明细，内部 row/group id 和 detail-only 字段不属于搜索面；`%`、`_`、反斜杠不得成为 SQL 通配符。普通关系和 `no_oa_bank_batch` 的 summary page 必须返回全部可见行，不得截成三行 preview；只有 ETC 发票栏和银行流水规则批量处理的银行栏（成员数 `>3`）允许逐栏折叠。折叠栏的 summary 只返回摘要与权威 `collapsed_row_counts`，不得附带 `collapsed_rows` 搜索预览；搜索只决定完整关联组是否命中，不能自动加载、展开或显示折叠成员。完整 `collapsed_rows` 只由用户点击后调用 group detail 获得。默认无筛选 `month=all` 查询使用现有 canonical active-month group/member SQL 一次计算精确 total 与 row counts，分页继续只取有界 payload；查询开始和返回前复核 active-month generation-set digest，切换时 fail closed。带条件查询只物化 active generation 的窄 group keys；active member CTE 必须允许条件下推，禁止强制物化全部 active members 后再搜索。单条 SQL 一次得到精确 total、row counts 与匹配 group ids，分页按匹配 ids 取 payload，禁止重复扫描历史 generation；普通标量列同列多选按 OR，不同列/不同 pane 按 AND；银行金额表头的方向+付款账号复合筛选继续按 AND |
| row/group detail | Workbench read repository | 必须固定到同一 active generation；miss 不得合成占位行或回退旧 snapshot |
| confirm/withdraw command | Workbench action route / Turnover adapter | canonical row ids、actor、tenant、idempotency、expected versions、preview identity。通用页面调用保持原合同；Turnover cash-closure 撤回可在同一事务先调用 `prepare_withdraw_relation(case_id)`，以一次 case lock/scoped snapshot/freshness 得到 owner-bound preparation，再交给 `withdraw_relation(..., preparation=...)`，case、rows 或 aliases 不一致必须 fail closed，禁止重复加载关系 |
| matching scope | durable matching dirty queue | 合法 `YYYY-MM`；repository 读取 ±365 日组合窗口，显式引用可补载全部保留历史 |
| matching source versions | matching worker / orchestrator | 只跟踪会改变正式关系计算结果的输入；Workbench 展示投影 schema 不是 matching 输入，禁止因纯展示版本升级重算历史月份。 |
| generation source versions | Workbench normal GET / projection builder | expected 与 published generation 使用同一个 scope vector：所有状态的 relation/exception/override、active pending claim、requested month 与 relation 跨月成员的 OA/银行流水/发票 canonical `updated_at`、ETC submission/business/invoice/link 四类直接投影输入，以及 Workbench 实际消费的银行自动标签规则版本和账户映射 fingerprint。无关 settings 字段不进入 proof。relation 撤回、soft delete、跨月成员变化和 ETC link/owner 变化必须让每个真实受影响月份 stale；`turnover_manual_closure` 仍属于 Workbench 主 generation canonical proof，但不属于共享 `workbench_relation` distribution。`all` query 使用 active 月分片对应的完整 vector。canonical 变化只让被访问 scope 判 stale 并走现有 gateway，禁止恢复写后 fan-out。 |
| access refresh coalescing | Workbench normal GET / durable queue | normal GET 发现 stale 后只 ensure 当前 exact scope。当前 freshness view 已证明 exact scope 存在 `pending/processing` outbox event 时直接返回 `refreshing`，后续轮询不得重复执行全月份 canonical proof 或 schema scan；dirty 没有 active event 时必须标记 stale 并返回 exact scope 重新入队。Application 复用同一个 `WorkbenchSqlProjectionBuilder`，仅把时间上重叠的同 scope canonical proof 合并成一次数据库读取；完成后立即移除 flight，后续独立访问必须重新检查事实，失败 flight 也必须允许下一次访问重试。该进程内 flight 不是 freshness cache、durable truth 或第二套去重器。真实 relation/canonical mutation 和显式 repair 不适用 queue ensure 合并。 |
| page source freshness | `WorkbenchQueryFacade` -> `WorkbenchQueryFreshnessService` -> `WorkbenchSqlProjectionBuilder` + active generation repository | 关联台投影直接读取 canonical facts 与 `app.workbench_pair_relations`，不消费 `workbench_relation` distribution，因此 combined initial 不得阻塞或刷新 `workbench_relation`。月份请求只比较当前 Workbench generation 与该月 canonical source vector；`all` 用一次月份枚举、一次 canonical bulk proof 和一次 active-generation bulk proof 返回真正 mismatch 的 `refresh_scope_keys`，只 enqueue 这些 Workbench 月份。默认、搜索、筛选和排序请求都必须先经过同一 freshness gate；查询是否可使用 Redis 只影响 cache I/O，不得决定是否验证 source freshness。普通 relation 写后访问不得退化成 `workbench:all` 全月份重建，也不得产生 relation projection I/O；已有 exact refresh 进行中且暂时没有新的 exact target 时，`all` 访问必须等待现有任务完成并在下一次轮询重新 proof，禁止把暂时未知目标回退成 `all` fan-out。freshness status 与 combined initial 读取期间发生 generation-set 切换时，返回 version-drift fail-closed payload 并由下一次请求读取新 generation，禁止为这个正常并发切换 enqueue 任何 refresh。只有 active generation 全部缺失或稳定状态下仍无法得到 exact recovery scope 时，既有 `all` fan-out command 才作为冷启动/显式恢复入口。已有 active generation 时，non-fresh initial/groups 继续返回该稳定 generation 的 rows 与版本，同时显式标记 refreshing/stale/failed、禁止写入和 Redis payload 写缓存；前端不得用同 generation 的 non-fresh 响应覆盖刚提交的 operation projection。active generation 缺失时仍 fail closed，不合成 false-empty。后续 `/groups` 继续绑定 initial 返回的 generation version。`server.py` 只注入 Application 已持有的 shared projection builder、repository 和 stale-reason port，不创建 request-local builder，也不拥有 scope 比较或 mismatch 聚合。 |
| public refresh status | `WorkbenchQueryFacade` -> Workbench read repository | 页面 `/api/workbench/refresh-status` 与 SSE 使用 `get_workbench_groups_freshness_status(scope_key)` 的轻量 active-generation/dirty-scope view，再执行同一 canonical source freshness 与 status normalizer；完整 generation/outbox/worker consistency diagnostic 只属于 App Health/Audit，不得进入页面 150ms 等待热路径。旧 repository 缺少轻量 port 时允许使用既有 diagnostic port 作为显式兼容 fallback，但生产 repository 必须实现轻量 port。 |
| exact ETC relation enrichment scopes | `PostgresWorkbenchFormalRelationFactRepository` | candidate 只输出 OA 月份与 ETC batch 月份；已知月份时禁止附加 `all`。`month=all` 查询直接组合 active 月 generation，因此 exact enrichment 只需刷新受影响月份；只有完全无法解析月份的通用 relation 合同才允许 `all` fan-out command |

`/groups` 在 generation/version proof 不是 `fresh` 且已有 active generation 时，允许用 expected generation version 执行一次有界稳定 page SQL，但不得读取或写入 Redis；响应必须保留 non-fresh status，前端只能把它作为刷新诊断，不能覆盖更新的 operation projection。没有 active generation 才返回空 groups 与明确 missing/failed 状态，禁止伪造 fresh 空集合。

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| `paired.groups` | 前端 | 每组恰好对应一条冻结要求已满足的 active formal relation，`group_type=relation` |
| `unpaired.groups` | 前端 | 无 active owner 的 canonical fact 为 `group_type=unpaired` singleton；冻结要求未满足的 active relation 保持同 case、`group_type=relation`，并返回 `completion.is_complete=false` 与 `missing_row_types` |
| OA expense-item display | 前端 | 父 OA 是唯一可选/可撤回成员；投影在同一 active formal relation 内先用父 OA 自身字段及其 FK-owned 付款明细/附件的显式 source alias 识别附件，再用唯一 `source_expense_row_index` 把发票展示字段归一为 `expense_items.id`，前端以一次 item-id 索引按原付款项顺序构造复合展示带，并在“申请事由”列显示该项的费用内容/费用说明。canonical 发票事实仍保留原始 `source_expense_item_id`；冲突、缺失或重复 row index 保留在父 OA 摘要行，不按金额、项目名或顺序猜测。子项 UI 复用父 OA selection id，不能产生虚拟 canonical row、独立 action 或第二关系链路。 |
| combined initial | 前端/App Health | `GET /api/workbench` 在同一 active generation-set 快照返回 summary 与 paired/unpaired 各 50 组首页；summary 含 `paired_count`、`unpaired_count`、OA/流水/发票事实数与 exception count；用户滚动接近每区列表底部时，前端才通过既有 `/groups` 自动读取下一页，不显示“已加载 N / total”或手动“加载更多”；搜索仍由服务端查询该区全部 active generation 数据，不受前端当前已加载页限制 |
| operation recovery read | 前端 / 生产可逆写验证 | 缺少 backend operation projection、必须等待完整 generation 的操作只允许一次 combined initial 触发 exact recovery；若未 fresh，改用公开轻量 refresh status 等待，canonical proof 返回 fresh 后再读取一次 combined initial 并安装 payload。等待期间不得重复读取 paired/unpaired groups，最终 load 再次 non-fresh 时继续 fail closed。生产 relation confirm/withdraw 的页面 consumer 必须测量真实 `GET /api/workbench` combined initial，并在 `paired` / `unpaired` 根下绑定 test-owned identity；不得把滚动分页 `/groups` 的耗时登记为关联台首屏恢复耗时。 |
| formal relation write result | caller | before/after、version、affected months、audit；普通操作的 outbox/barrier targets 为空 |
| relation source version | Workbench/Cost/其他消费页 | canonical relation 事实提供可比较的版本证明。普通关系事务不直接投递 Cost 或任何其它页面；消费页只在自身访问时检测 mismatch 并投递精确 scope。 |
| matching summary | worker/App Health | planned/created/extended/preserved/ambiguous/resource-limited/unsafe counts；不输出候选 rows |
| read model generation | Workbench query | 新 generation 完整写入并校验后原子激活；building/failed 不可读为 fresh |
| all-scope query statistics | Workbench groups query | all-scope total、三类 row counts 与标题 statistics 直接从当前 active monthly generations 的 canonical group/member owner 集合计算；不写第二份 all-scope statistics，不把全历史聚合放进月份发布事务。查询返回前必须复核 generation-set digest，切换时 fail closed |
| superseded generation retention | `finops-prune-workbench-generations.timer` | 低峰期有界删除非 active generation；发布热路径不得同步扫描/删除旧 generation，清理失败不得影响 fresh generation 或页面写后可见性 |
| refreshing query status | Workbench initial/detail query | 返回 refreshing/遮罩状态；读入口不得再次补投 `all` refresh，只有真正 missing 或 freshness gate 已证明的 exact stale scope 才能请求恢复，避免读 I/O 扩成全月份写 fan-out |
| Search row context | 非 PostgreSQL 本地 Search | `list_workbench_search_rows(YYYY-MM)` 只返回 active generation 的 row/zone/group/project context；禁止复用 Workbench page/full payload |
| ignored rows | Workbench ignored API / write command | `list_workbench_ignored_rows(scope_key)` 只读取 active generation；repository 缺失时公开 API 返回 unavailable、写命令 fail fast，禁止回退旧 snapshot |
| relation action preview selection | confirm/withdraw preview | `WorkbenchQueryFacade.relation_preview_selection -> PostgresReadModelRepository.get_workbench_relation_preview_selection` 按 expected generation/generation-set 一次读取最多 20 个 selected rows 及必要 OA attachment context；month/all 都在读取前后复核 fresh/version。`month=all` 中同一 canonical row 被跨月 relation 投影到多个 active shard 时，规范化内容完全相同才合并为一个逻辑 row；同 row id 内容不一致、missing、跨 generation 或 drift 一律 fail closed。该 DTO 只供 preview group/amount/alias 投影，不进入正式 command/UoW，不读取 `workbench:all` 完整 payload、live builder 或 `workbench_relation` projection |

## 依赖方向

- route 只做 HTTP DTO/错误映射和依赖组装。
- `WorkbenchFreeMatchingEngine` 是纯函数边界，不读数据库、不写队列、不记录网络 I/O。
- `PostgresWorkbenchFormalRelationFactRepository` 是 matching 输入的唯一 SQL owner。
- `WorkbenchMatchingOrchestrator` 只编排 repository -> matcher -> 单次 relation UoW。
- 已失败 matching scope 的人工恢复只能先 dry-run 固定 scope/fingerprint，再通过 `workbench_matching_scope_retry_ops` 调用 durable repository 精确重排；禁止手工 SQL 改 queue 状态或扩散到相邻月份。
- `WorkbenchRelationCommandService` 拥有正式关系状态转换；repository/UoW 拥有 SQL 与事务，普通关系写入不拥有下游 durable outbox。
- `WorkbenchRelationGroupingService` 只消费 canonical rows + active relations；relation requirement snapshot 是唯一可改变关联台 zone 的业务 metadata，其他 display decorations 不得改变 membership 或 zone。
- 前端只消费 API，不读取 relation provenance 推断分区。

## Read model 与 worker

- `workbench` 使用 active-generation scoped publish；月分片发布必须原子。`workbench_rows`、`workbench_groups`、`workbench_group_rows` 三个已测量的大批量 generation 表通过 psycopg `COPY FROM STDIN` 写入，snapshot/summary/stats/active 切换仍复用原事务和既有表；COPY失败整体回滚，禁止引入第二 writer、staging 表或异步发布层。
- 不同月份的 generation payload计算与 staging/COPY允许并行；重型数据写完后，`workbench_generation_set` transaction advisory lock 只保护本次 active generation 切换，不再执行 all-scope canonical scan或统计写入。不得恢复按月份分别锁住重型写，也不得把全局统计重新塞回发布关键路径。
- `month=all` 查询组合 active 月分片，并在分页前做唯一 canonical owner 仲裁。
- 月 generation 原子发布事务只更新该月 generation 与该月 generation stats；不再更新 `workbench_generation_stats(scope_key='all')`。默认 `/api/workbench/groups` 在请求内使用现有 active-month canonical SQL 计算 counts，并在返回前复核 generation-set digest；generation-set 切换时 fail closed，由现有 facade 返回 `202 refreshing`。该路径不新增全局 generation、worker、queue、缓存或共享 read model。
- 默认 `month=all` combined initial 在同一个 repeatable-read 事务中只读取一次 active generation/source/freshness context，复用 canonical summary 的 zone counts，并批量读取 paired/unpaired 两区各 50 组首页与可见成员；包括事务设置在内最多 10 条数据库语句。active generation-set digest 必须先按 `(scope_key, generation_id)` 规范排序，不能依赖不同 SQL 调用方的升序或降序；首屏 SQL/Redis payload 的 `read_model_version` 必须与请求开始时 freshness gate 的 active generation-set version 完全一致。不一致时返回 `202 refreshing`，由下一次请求读取新 generation，不得额外入队、缓存或返回旧 groups。initial cache schema 必须在此合同变更时独立升级以淘汰旧 payload。带搜索、筛选或排序的首屏同样先走 freshness gate，再固定 50 组并走既有窄 `/groups` 查询；后续分页保持 `expected_read_model_version` 绑定，不复制筛选 SQL或忽略查询条件。
- 带搜索、来源或列筛选的 all-scope `/groups` 只在单条计数 SQL 内 materialize 当前 active generation 的 group keys 与过滤结果；active member CTE 使用 `NOT MATERIALIZED`，使区域搜索、来源和列/时间条件可以下推到既有结构化表与索引，而不是先复制全部 active members。各条件仍通过去重 member-key join 相交，总数、三类 row counts 和有界 matching group ids 一次返回，分页只按这些 ids 读取 canonical payload。历史 generation、历史 materialized all group 和 payload/raw payload 不得进入筛选计数。
- schema/version 由 `workbench_read_model_version.py` 统一提供；当前 month schema 为 `2026-07-30-etc-summary-relation-member-v15`，all composed schema 为 `workbench_sql_projection.composed_active_month_shards.etc_summary_relation_member.v15`。groups page cache 必须复用同一 projection schema；旧 generation 或旧 Redis page payload 不得冒充 fresh。ETC 折叠汇总通过 `app.etc_invoices.business_batch_id` 读取已提交 business batch 的直接成员归属，不再依赖 `raw_payload.invoice_ids` 镜像；严格 link 只补充 canonical invoice owner，不能因部分 link 已存在而截断同批旧成员。ETC 汇总是批次聚合对象，身份键固定为 `etc-summary-{batch_id}`；展示文案（例如“ETC发票 68 张”）不得参与单张发票强身份去重。摘要 ID 已持久化为正式 relation member 时必须保留 canonical 身份；只有关系外附加的摘要才使用 display-only role。人工确认必须持久化 batch identity，Page Audit 只认可 deterministic summary ID 与 canonical batch 同时成立。migration `0125_workbench_canonical_proof_identity_indexes.sql` 只为跨月 relation member 的既有 bank/invoice canonical identity lookup 建两个已测量表达式索引，不改变事实、scope、worker 或 publish 合同。
- Workbench worker 不预热 page cache。默认首屏缓存只由 `WorkbenchQueryFacade` 在 fresh gate 后按 active generation version read-through；cache miss/down 回同一 SQL repository cold path，不影响 generation 发布或 dirty scope 完成。
- 对外不存在独立 Workbench summary HTTP 合同。`PostgresReadModelRepository.get_workbench_summary(...)` 只是 combined initial 同快照组合所需的内部窄 I/O，不得重新从 route/facade 公开。
- collapsed-summary 是逐栏展示形态而不是第三种关系状态：repository 必须分别物化 `summary_row` 与全部 `collapsed_rows`，`collapsed_row_counts.<pane>` 是该栏是否折叠和详情完整性的唯一合同；组级 `display_mode` 不得使其它正常栏改读 `collapsed_rows`。未配对 ETC summary 仍是一个 canonical singleton owner，旧 candidate/decision `case_id` 或 relation mode 不得泄漏为关系归属。
- matching scope、workbench scope 和 workbench_relation scope 都以 PostgreSQL durable queue/state 为事实源；Redis 只缓存 fresh payload，RabbitMQ 只做可选唤醒。
- 历史 ETC 修复如果只改变已提交批次成员而不改变正式关系，matching completion 不足以发布新页面 generation；统一 historical ETC repair runtime port 必须通过 `ReadModelRefreshGateway` 额外 enqueue 修复报告中的精确月份 Workbench scope，不投 `all`、不直接写 active generation。
- relation UoW/turnover writer不拥有成本计算、存储或下游刷新I/O；repository、自动匹配命令和lifecycle registry不声明成本I/O。Workbench generation publish也不发布Cost fan-out。Cost访问先读取现有gate；gate已non-fresh时跳过canonical Workbench全量证明并使用gate返回的exact upstream/child scope。只有gate可fresh时才检查Workbench canonical expected/active generation版本；上游stale时，同次只ensure当前exact Workbench月份并stage当前project/page所需的exact Cost child，不stage parent或sibling。query把本次gate已验证的expected proof与token成对交给Workbench event；worker校验token/scope后复用proof，missing projection仍不附proof并走首次自愈。Cost child可携带同一Workbench proof作为active waiter target，但不能用历史done替代完整Cost freshness。Cost worker以manifest dependency fail closed/defer，依赖fresh后发布并由成功child收敛parent。Workbench访问刷新由共享PostgreSQL advisory-lock原子合并active/最新成功同target；missing projection与orphan dirty仍可重新入队。禁止写后fan-out、`workbench_shard_published`、旧进程内read-model persist、proof cache或第二协调链路。
- Search 本地即时查询与 ignored rows 是 repository 窄读接口，不是新的 read model/projection/cache；它们必须固定到 active generation，且不能反向依赖页面 assembler。
- Release A 上线后已通过全量 Workbench rehydrate 使旧 `open`/candidate/decision generation 被新的 paired/unpaired generation 原子替换；不得原地修改旧 active generation。当前 v7 已随 exact release `main-719c9a34-20260725101310` 激活，migration `0125` 和正式 `finops-deploy-control workbench-rehydrate` 均已完成；最终只需在同一 release 上关闭页面/Audit/queue/worker correctness 矩阵，不得重复执行 no-op 部署或 rehydrate。这类版本迁移维护操作不属于普通页面性能口径，也不得由普通页面隐式触发全量迁移。纯派生投影迁移不创建额外数据库备份，依赖既有 release rollback 与 test-owned fixture 恢复。Release B 的旧状态 drop migration 只在 A 的零访问和数据安全证据通过后创建，并使用届时下一个可用版本；不得复用已被 OA 使用的 0104。

## 旧链路删除合同

Release A 已删除运行时链路且禁止恢复；旧表物理存储只为短期回滚窗口保留，并由 Release B 删除：

- `workbench_candidate_matches` 与 `workbench_reconciliation_decisions` 的 repository/service/store/cleanup 和全部运行时访问。
- candidate grouping、special candidate rule、decision engine/models 和 candidate repair CLI。
- `automatic_decision` / `automatic_match` 作为 relation mode 或页面 group type。
- in-memory matching dirty-scope fallback 作为生产状态源。
- `CandidateGroupGrid` / `CandidateGroupCell` 组件和候选取消写入口。
- 仅凭 `case:decision:*`、row `case_id` 或旧 section 判断显示归属。
- legacy `GET /api/workbench` provider/API assembler 与所有跨页面 full-payload consumer；当前首屏只走 `WorkbenchQueryFacade.initial_page(...)`，Search、ignored、Batch Accounting、Cost Statistics 和 Settings 各自使用既有专属窄 I/O。
- 旧独立 summary HTTP handler/route/facade 与其 metric owner；运维 probe 和页面只能使用 combined initial 或已有窄查询。
- 默认无筛选 `month=all` groups 请求中的动态 `count(distinct workbench_group_rows...)` 旧慢路径及其把历史 materialized all generation join 回 active month shards 的污染；它不再作为 generation stats 缺失 fallback。带用户搜索/列筛选时重复执行 member `EXISTS`、分别计算 count/page、或把历史 physical groups join 回 active shards 的旧路径也已删除；精确条件计数只能使用当前 active key 集合。
- 已删除三栏 `WorkbenchPaneSearch`、`search_by_pane`、`search_mode`、pane-local draft/open/session 状态和对应 cache/repository 分支；不得恢复并行搜索路径或兼容 fallback。页面 session schema 为 v2，旧 v1 搜索状态直接失效。
- 已删除区域底部 `已加载 N / total`、手动 `加载更多` 按钮、`onLoadMore` 组件 I/O 与旧 footer 样式；下一页只由区域列表底部哨兵触发，并复用既有 `/groups`、query 和 `expected_read_model_version` 合同。失败后允许显式重试，但禁止恢复常驻手动分页入口或第二套分页路径。
- 已删除的旧链包括：无 row/case identity 的 direct full cost refresh、facade downstream-discovery 中的 cost scope、relation transaction delta、Workbench `workbench_shard_published` 成本收敛事件、自动匹配/lifecycle cost domain/job、relation repository 隐藏 scope expansion，以及写后 operation barrier。不得恢复兼容分支或第二套 fan-out。
- on-demand raw/live/OA/retained payload builders、read-time OA invoice-offset relation sync/repair executors、ETC summary DTO 重拼装、legacy `WorkbenchApiRoutes` 和 row-detail fallback；当前详情只走 `WorkbenchRowDetailApiRoutes -> WorkbenchQueryFacade -> active generation repository`，确认关联所需 OA 附件上下文只读取同 generation grouped rows。

保留但隔离的同名概念必须属于其他业务域，例如银行自动标签候选、待找发票搜索结果或异常分类 evidence；它们不能进入 Workbench relation membership。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/components/workbench/RelationGroup*.tsx`、`web/src/features/workbench/*` |
| Backend API | `backend/src/fin_ops_platform/app/routes_workbench.py`、`server.py` 的依赖组装 |
| Core | `workbench_relation_grouping.py`、`workbench_free_matching_engine.py` |
| Service/UoW | `workbench_query_facade.py`、`workbench_query_freshness_service.py`、`workbench_matching_orchestrator.py`、`workbench_relation_command_service.py`、`workbench_uow.py` |
| Repository | `postgres_repositories/workbench_formal_relation.py`、`workbench_relation.py`、`read_models.py`、canonical identity hot path migration `0125` |
| Worker | `workbench_matching_dirty_scope_worker.py`、`workbench_read_model_refresh.py`、runtime worker registry |
| Tests | `tests/test_workbench_*.py`、`web/src/test/RelationGroupGrid.test.tsx`、`web/src/test/Workbench*.test.*`、`web/e2e/workbench-*.spec.ts` |

`WorkbenchRelationGroupingService` 只接收 canonical rows 与 active formal relations，并按冻结 requirement snapshot 输出页面 `paired/unpaired` 精确分区；`WorkbenchRelationPreviewGroupingService` 复用同一判定，只接收写操作预览所需的 formal relations、selected rows 和显式 ungrouped mode，并输出预览 groups。二者都是无 I/O 的纯投影边界；route/server 只负责组装依赖，不能重新实现 membership、隐藏未分组行、回查当前规则或读取 repository/HTTP 状态。

confirm/withdraw preview 的行输入只能来自上述 relation-preview selection port，且每次请求只允许一次 selection load。preview 可输出 `group_type=selection` 与 `zone/status=unpaired`，但正式页面 active generation 仍只有 `paired/unpaired`；正式 confirm/withdraw 必须重新进入 canonical relation command/UoW，不能缓存、转交或信任 preview selection DTO。

前端只在 relation preview mapper 中接受 `selection`：必须同时满足 `zone=status=unpaired`，映射为页面 `groupType=unpaired` 并保留 `rawGroupType=selection`；`relation` 必须同时满足 `zone=status=paired`。普通 combined initial/groups mapper 继续拒绝 `selection`。confirm/withdraw preview 共用一个同步防重入边界，pending 期间 toolbar 与 inline 入口不得产生第二个 POST；selection、scope 或 active read-model version 变化后返回的旧成功响应不得打开 drawer。API 错误只通过 module-owned 安全类型向页面传递批准的中文文案，`status/code/requestId` 仅作为支持字段保留，后端 message、raw response 与 parser exception 不得直接进入 UI。

正式关系是关系 ownership 的唯一事实源。projection builder 必须在读取 override/exception 前先从已经加载的 active relations 计算 member row ids，并从 control I/O 集合排除这些成员；不能先把旧 candidate/exception ownership 写入正式成员，再依靠字段覆盖或 Audit 豁免掩盖冲突。未配对 row 仍按 active override > active exception 投影，两个查询继续由既有 repository SQL 边界批量完成。

## 数据恢复与回滚

- 发布前备份 relation facts、history、active generation metadata 和 queue 状态；candidate/decision 表是派生旧状态，不进入业务备份恢复源。
- Release B 的旧状态 drop migration 只做 forward drop 和旧 app-setting 清理，不改 canonical facts；Release A 不携带该 migration，也不提前预留空版本。
- 发布后运行 `scripts/rehydrate-workbench-read-models.py`，等待 matching/workbench/workbench_relation scopes fresh，再运行页面 Audit。
- 历史普通银行 relation 缺失冻结要求时，只走 root-owned `workbench-requirement-repair`：输入为
  active relation、fresh 银行标签和规则 payload，输出为带 dry-run fingerprint 的正式 relation
  metadata/history 与 durable refresh；禁止直接 SQL、任意 shell 或设置保存后的持续回扫。
- rehydrate 必须至少成功发布一个月 generation；all-scope 页面随后直接组合 active month generations，不要求或人工补写 all-scope stats。
- 回滚应用版本不得重新创建旧 candidate/decision 表；若必须回退展示代码，只能继续读取 active formal relations 和 paired/unpaired generation。
- 修复验收必须证明 520 关系进入 paired、13 张合计 1709.49 的发票各自 unpaired、canonical count 未减少、active relation/history 未损坏。

## 页面完整性统计合同

- 关联台既有 combined initial 响应增加 `statistics`，统计只组合当前 active monthly generations 中页面实际拉取的 OA、银行流水、进项/销项发票、已配对组和未配对对象；不读取统一事实源汇总，也不受页面筛选、排序或分页影响。
- all-period statistics 由 query repository 从当前 active monthly generations 的 canonical group/member owner 集合计算；combined initial 在 repeatable-read 快照内复用该结果，单月 summary 使用同一 set-based查询但不入队其它月份或 `all`。
- 单月页面只收敛自己访问的 exact month；全期间统计查询不是页面明细 freshness owner，也不能把统计计算变成写 I/O 或发布阻塞。
- Page Audit 证明 active generations、groups、members、summary 和 generation counts 的结构化 owner 一致；`month=all` 标题统计由正常页面查询在同一 active-generation 快照即时计算，不再读取或要求已退役的 `workbench_generation_stats(scope_key='all')` 发布值。生产 HTTP/SLO 验证负责证明该只读计算可用且满足耗时目标，不新增 endpoint、表、worker、队列或共享 I/O。

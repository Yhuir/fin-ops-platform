# 进项发票使用情况模块边界与 I/O

日期：2026-09-28

## 模块化状态

- 状态：`canonical-direct-read`
- 当前边界可信度：high
- Query owner：`InputInvoiceUsageCanonicalQueryService`
- PostgreSQL owner：`PostgresInputInvoiceUsageQueryRepository`
- 旧页面 read model：API/frontend、projection/repository、worker/registry/deploy 和 lifecycle 间接链均已删除。

## 职责边界

### 负责

- 进项发票使用 rows、summary、statistics、facets、筛选、排序和服务端分页。
- 发票/OA/银行流水/关联发票详情、当前筛选导出和 OA reverse preview。
- active relation component 聚合、金额合计和支付状态计算。
- OA reverse canonical batch、relation、审计、CAS/idempotency 写入及写后 GET。

### 不负责

- 不拥有 OA 登录和外部 OA 数据同步。
- 不拥有 `app.workbench_pair_relations` 的写模型。
- 不读取或刷新 Workbench、invoice lifecycle 或页面 read model。
- 不修改共享 worker、manifest、scope policy、dispatcher、deploy env 或 App Status registry。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| rows 查询 | `InputInvoiceUsagePage.tsx` | `page`、`page_size`、keyword、日期/月、filters、sort；非法值返回 400。纯金额 keyword 使用无千分位文本并查询价税合计、未税金额、税额和关联流水金额。 |
| canonical invoices | `app.invoices` | 只取非删除 input invoices；金额和日期保持 canonical 口径 |
| formal relations | `app.workbench_pair_relations` | 只取 `status='active'`；按 relation component 聚合 |
| bank/OA facts | `app.bank_transaction_units`、`app.oa_applications`、`app.oa_pending_payment_admissions` | 只读取已同步 PostgreSQL snapshot；OA summary 输出 canonical `workflowStatus=completed|in_progress`，重复 identity fail closed |
| OA detail id | rows DTO 的 `oa.id` | 只接受 canonical OA identity；repository 通过既有 OA workflow repository 定向查询，不经过进项发票使用行 hash |
| payment rules | `app.app_settings` | 使用现有 input invoice payment rule contract |
| OA reverse facts | `app.input_invoice_usage_oa_reverse_batches` | statistics、preview 和命令状态 |
| lifecycle command | 页面专属写 API | 保持原权限、审计、CAS/idempotency；成功后 GET |
| OA 草稿预填配置 | `GET/PUT /api/workbench/settings/oa-draft-prefill/input-invoice-usage` | 所有已授权 App 账户可见并可只读打开页面右上角抽屉，仅 admin 可编辑/保存独立 versioned family；创建 reverse batch 时固化当次配置快照，后续 OA draft 创建不受并发设置变更影响。多销方或缺失销方 fail closed |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `/rows` | 页面 | 同一 snapshot 返回 `rows`、`summary`、`statistics`、`pagination`、`filterConfig`、`filterOptions`；`payment_status` 候选排除自身状态条件后聚合，并按输出分类字典补齐零数量状态，选择状态不得缩减候选词表；所有 facet 数量按去重发票张数计算 |
| relation/details | drawer | row/invoice/bank 按 canonical id 定向读取，不存在返回 404；OA 详情按 canonical OA id 返回 `detailAvailable=true|false`，不可用时保持 200 的既有 drawer 合同 |
| OA 申请人列与详情 | frontend | 总览只显示申请人、申请类型、多 OA 数量和合计金额，不显示流程状态；原始 OA 详情只使用明确的来源 `detail_fields["流程状态"]`，不以内部 `workflowStatus` 或 linked/unlinked/unpaired 关系状态替代 |
| export preview/download | export drawer | 复用 canonical filters/sort；20,000 行上限和原错误合同不变 |
| OA reverse preview/command | OA reverse drawer | preview 只读 canonical snapshot，并分别返回 `permissions.canCreateDraft` 写能力与当前整组 `canCreateDraft` 业务可创建状态；前端对当前勾选集合只做同一非空销方的轻量可用性判断，提交前必须按精确发票集合重新 preview，并以新 preview 的权限、业务状态和 hash 为准。命令只写 canonical facts；候选金额展示与服务端搜索都使用无千分位文本。OA payload 动态写目标申请人、当天日期、所选总额和唯一销方，申请事由只显示发票数/发票号码，内部 reverse batch ID 仅保留结构化字段。 |
| write result | 页面 | 不含 refresh target/barrier；页面成功后重跑当前 GET |

`statistics` 只包含 canonical 进项发票总数、已完成/进行中 OA、支出/收入流水数量；同 ID OA 以已完成优先，旧付款、关系组和反提批次数量字段已删除。

`/rows` 不输出 `read_model_status`、`source_versions`、`refresh_enqueued`、scope 或 polling 字段。

## 一致性与性能合同

- 每个页面读请求开启一个 `REPEATABLE READ READ ONLY` transaction。
- rows、summary、statistics、facets 和用于组装当前页的 facts 都在该 transaction 中读取。
- rows/summary/facets 复用一次 materialized canonical CTE；付款规则从同一 request snapshot 交给有界行装配，禁止逐行重读 `app_settings`。整个请求最多 8 条批量 SQL statement，数量不随当前页行数或 relation 数增长。
- 支付状态的 self-excluding facet 在同一 SQL statement、同一 canonical CTE snapshot 内计算；禁止为保持完整候选额外请求 `/filter-options` 或增加数据库往返。
- 服务端完成筛选、排序、分页；Python 只组装当前页有界 facts。
- OA 详情使用一个独立只读 repeatable-read transaction 和一次有界 OA identity 查询；禁止加载页面 row group、发票或流水作为间接查找。
- 只有 EXPLAIN 或真实慢查询证据支持时才增加索引；查询优化不自行创建 migration；本次 0182 仅迁移现有规则配置，属于 settings 合同升级。
- 关联成员读取银行用途时，将每条用途的 canonical ID 与 legacy ID 展开为去重别名，再做等值关联；同一用途的相同别名只展开一次，不跨用途吞掉同名别名。替代旧双身份 `OR/IN` 全组合比较，保留原匹配、金额和分页语义，不增加 SQL 往返或持久化状态。

## 搜索控件展示边界

- 页面复用 `QuerySearch` 和 HeroUI `SearchField`，只控制工具栏排列与搜索区域宽度；内部输入、图标和清除按钮由原生组件管理。
- 搜索外框承担统一边框与聚焦反馈，页面不得通过后代 `input` 选择器再次添加边框、背景或聚焦阴影。旧原生输入框的普通、hover、focus-visible 样式已删除。
- 关键词草稿、提交、清除、分页和查询 API 合同保持不变。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，页面不得维护第二套详情 renderer。
- 单条和多条使用同一公开字段合同；多条只重复 `OA N`、`银行流水 N`、`发票 N` 分区，不输出关系概况、数量、是否多条或内部 case/source 信息。
- 仅展示详情 API 实际返回且具有文件/OA来源依据的字段；内部 ID、raw payload、批次字段和推导字段在共享边界过滤。
- 详情按需一次有界读取，不得逐成员 N+1；时间统一为 `Asia/Shanghai` 的无 `T`/`Z`/offset 格式。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend | `web/src/pages/InputInvoiceUsagePage.tsx`、`web/src/features/inputInvoiceUsage/*`、`web/src/features/oaDraftPrefill.ts`、`web/src/components/inputInvoiceUsage/*`、`web/src/components/common/OaDraftPrefillDrawer.tsx` |
| Route | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py` |
| Query service | `input_invoice_usage_canonical_query_service.py` |
| Business assembler | `input_invoice_usage_service.py` |
| Query repository | `postgres_repositories/invoice_usage_collection_query.py` |
| Commands/export | `input_invoice_usage_oa_reverse_service.py`、`input_invoice_usage_export_service.py` |
| Tests | `tests/test_input_invoice_usage*.py`、`tests/test_invoice_usage_collection_canonical_query.py`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` |

## 依赖方向

`frontend -> route -> canonical query service -> page query repository -> canonical PostgreSQL tables`

写路径为：

`frontend -> route -> command service -> canonical repository/audit -> current rows GET`

禁止依赖方向：

- route -> SQL
- query service -> HTTP/session
- page query repository -> read-model tables
- frontend -> filter-options/read-model refresh/status endpoint

## 跨页面清理结果

`InvoiceUsageCollectionSqlProjectionBuilder` 的 input projection、invoice-usage-collection worker/handler/registry/manifest/deploy、input read-model scope/App Status/audit/repair 注册项已删除。历史 migration/表暂留作回滚证据，没有运行时 reader/writer。

## 2026-09-15 日常报销子项展示修复

OA 详情 expenseItems 使用公共来源费用字段白名单（项目、金额、实际费用内容/说明、报销日期、支付方式、发票种类、票据张数；2026-09-27 移除推断费用类型和计算的附件数量），页面按顺序展示所有子项。canonical 及现有非 PG service 共用纯投影，禁止输出附件原始载荷。列表、关联写入和成本分配不变。

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 页面进入与时间范围（2026-09-21）

页面每次挂载在现有 query session 的 `restoreQuery` 清除 `month`、`invoiceDateFrom/To`、`invoice_date` 与 `bank_trade_time` 日期列条件，首个 rows/导出请求使用清理后的范围；不新增日期控件。保留 keyword、非日期 filters、sort 和 pageSize。旧范围确实含日期时，page 重置为 1，activeWorkflow/detailTarget 清空；原为全部时不无条件重置合法页码与流程。普通刷新、排序、分页、保存回读及抽屉关闭不执行 restore。

通用进入边界见 [时间范围实施约定](../../dev/date-range-default-all-plan.md)。HTTP schema、权限、业务资格与事实写入边界不因此改变。

## 2026-09-21 ETC 跨页面正式成员读取

- OA 待付款、进项使用及待找发票共用 `postgres_repositories/relation_invoice_members.py` 的只读成员展开：通过提交批次准确身份、active bridge 或既有 canonical `etc_invoice_id` 取得真实发票；同一 canonical 发票去重，软删除和撤回关系按当前事实处理。保留原关系 ETC summary，不另写一套关系，不把 ETC 原始票据伪造成正式发票。
- 读取在页面既有只读 snapshot 内集合执行；没有新增缓存、read model、worker 或逐票查询。进项合并组搜索覆盖全部成员，+N 与详情抽屉使用同一成员集合，流水/OA 金额按实体去重；汇总付款不按每张发票复制累计。
- 文件范围新增共享 repository SQL；各页面现有 query/assembler/API DTO 和权限保持各自 owner。旧的仅以显式 invoice row ID 读取 ETC 关系的路径已替换。回归入口：`tests/test_etc_relation_page_reads_postgres.py`，覆盖进行中 OA、47 张票、显式重复成员、成员搜索、删除、撤回与三页详情。

## 2026-09 流水拆分合同

银行原金融事实与导入身份不变；银行拆分 owner 的持久化子项通过用途视图进入业务关联。详情使用父交易，列表标签显示当前子项；金额统计不得父子重复相加。 具体输入/输出、跨模块消费、旧链路清理及测试见 [流水拆分 I/O](../../dev/bank-transaction-splits.md)。

## 2026-09-24 拆分流水的单据核对范围

同一现有 active 关联的用途比较复用 `bank_split_relation_scope` 的 SQL/Python 规则；银行金融事实、子项事实与关联成员不改写。只有全为拆分子项、同一收支方向，且单据目标金额恰好唯一等于完整本金用途组或完整其他用途组时，取该组核对。本金单据可以匹配本金，不再一律删除外部往来子项；金额相同的两组、金额不匹配、混合收支或包含未拆分流水时保留完整证据。

SQL 分页/筛选/汇总和 Python 行数据/详情组装使用相同范围，按集合执行，无逐行查询。OA 已付金额使用 OA 合计目标；发票页面使用当前发票组目标。进项含拆分的当前金额闭合不再依赖旧 relation.amount_check 的历史失败值，仍保留 OA 金额一致、正式关联与原支付规则约束；未拆分、无 OA 抵扣及销项超额收款/红蓝票规则不变。验证入口：`tests/test_bank_split_document_scope_postgres.py`，覆盖利息/本金单据、旧核对失败、金额歧义、未匹配、混合方向、未拆分兄弟流水，检查 SQL 汇总与行数据一致。

- 同一发票展示组可以包含不同 canonical 发票明细各自的独立正式关系；SQL 和 DTO 支付状态统一按整个展示组的去重流水证据、发票合计核对，不能把组总额逐个与单关系比较。各成员的占用关系不变。

## 2026-09-24 原始流水金额展示

银行列表聚合输出 `original_amount`、`original_transaction_count` 与按父身份去重的完整 `bank_split_parts`；单笔 summary 输出 `parent_row_id`、`original_amount`。用途金额与已付/已收业务字段保持原意，不能被原始金额覆盖。银行金额筛选/排序、导出和详情按对应原始流水口径，关键词仍可搜索用途金额；分页与批量查询不变。具体 DTO、导出列与旧路径删除合同见 [流水拆分 I/O](../../dev/bank-transaction-splits.md#2026-09-24-银行原始金额与用途金额展示合同)。没有新增 read model、worker 或持久化事实。


## 2026-09-27 原始详情来源隔离

OA、发票和银行右侧抽屉中的原始信息遵循[来源详情合同](../../dev/source-record-details.md)。详情投影只消费明确来源值，移除内部状态、推断费用类型、默认币种、日期替代及无来源的聚合信息；不从列表摘要或旧详情回退。银行使用父交易身份和真实交易日期，拆分操作仍由银行 owner 管理。模块列表、业务计算、导出、关系写入与原权限不变；公共成本核对信息不按原始字段规则全局删除。

文件范围包含共享 `services/source_record_details.py`、所属详情 query/assembler 与前端 API 映射；银行通用抽屉按 ID 读取 `/api/bank-transactions/{id}/source-detail`，复用既有有界银行读取。没有新增 read model、cache、worker、迁移或数据库备份。旧取值删除条件、测试矩阵及性能验证见集中合同；实际执行结果另记，不以本节表示验证通过。

## 2026-09-28 发票张数、反提候选与可编辑规则

- 主表增加 `relation_status` enum filter：`no_oa`、`oa_no_bank`、`oa_bank`，使用 active typed relation 成员判断关联是否存在；详情源记录暂不可用不能把已关联 OA 误判为反提候选。三个 facet 排除自身分类条件，同一只读快照统计 canonical invoice 身份，合计为当前其它条件下的“全部”。主表关系分组分页与发票张数分开表达。
- 反提 `preview` 默认候选是全部未关联 OA 的单张进项发票，输入 `page/pageSize/keyword/bankRelation`，先筛选再分页；不隐式继承主表 filters/month。输出完整 `invoiceCount/totalWithTax`、`pagination`、`relationCounts(all/linked/unlinked)` 和当前页 `invoiceRows`。显式 `invoiceIds` 走完整精确身份读取，任一不存在、已关联或被占用均禁止部分提交。
- canonical repository 通过同一 SQL builder 的 invoice-level 模式复用 active relations；无全量 Python 过滤、分页循环或逐票查询。金额比较事实随当前页 snapshot 进入 assembler，移除“任意单笔金额相等即可判整个组匹配”的旧路径。
- 目标申请人经 OA credential owner 的 `applicant_options()` 只读端口提供 code/name，仅 enabled 且有凭据者可选；不暴露密码或用户名。不使用固定六人名单。规则申请人选项独立来自 canonical OA 的真实 applicant。
- 未关联 OA 的已占用发票仍计入候选，行附带 `occupiedBatchId/occupiedBatchStatus` 并禁选。反提 repository 复用 relation owner 的成员锁及 invoice row lock，保存新 batch 前检查已有有效 OA 关系与其他未释放批次；复用现有状态和审计，不创建占用表或新状态。
- 支付规则支持新增、删除、修改申请人/条件。输出 code 为 `paid/cash_turnover/offset/waiting_payment`；同类输出统一显示名，多个冲规则合并为一个筛选项。未命中为显式 `pending/待核对`，不是可编辑兜底规则。原因由命中条件生成，列表、预览与导出一致。
- 规则 save 沿现有 app_settings family CAS，配置与审计同事务；读取不补回删除规则。Migration 0182 一次性转换旧配置（offset 合并、移除 pending_default/pendingDirections/手写原因），保留其它配置及 raw normalized 镜像。输出标签冲突则明确终止转换。旧程序不能消费新配置，发布失败应向前修复。
- 前端使用 HeroUI 原生 Tabs/Select/ListBox/Checkbox/Input/Button/SearchField 和已有 AppDrawer；仅删除本页重复边框、阴影及过期样式，不改全局组件。
- 文件范围增加 `0182_input_invoice_payment_rules_editable.sql`、OA credentials 的非敏感选项端口及 reverse repository 占用保护；无新 worker/read model/cache，无整库备份，不删除主数据库。

## OA reverse 请求 claim 与恢复合同

- 申请人选项由凭据 owner 返回启用且已配置的 `{code,name}`，不暴露账号密码或解密；无可用申请人可只读预览，禁止创建。候选服务端分页返回 `pagination`、`relationCounts` 和全量筛选摘要，精确选择必须全部有效。
- 外部 OA 创建前，repository 在既有 batch 事务内持久化 `draft_request`、version 和审计。复用 formal relation 成员锁与发票行锁，提交时再查 active OA 和其他 batch 占用；仅银行关联不禁止反提。
- `bankRelationStatus` 直接取 canonical typed relation 是否存在，禁止根据银行详情数组是否为空猜测关系状态。
- staged-drafts 返回所有 draft/failed/created/检测占用，新增 `draftRequestState` 和 `canRelease`；业务能力与接口写权限共同控制动作。`requesting` 禁止释放，失败/超过 HTTP timeout 两倍后只显示 `unknown`，人工核实与 reason 后可释放；不自动重试、释放或删除远端 OA。版本校验阻止并发发送和迟到完成覆盖释放。
- 真实 PostgreSQL 验证入口：`tests/test_oa_reverse_occupancy_postgres.py`，覆盖同票并发、同批外部调用一次、未知结果恢复、迟到结果拒绝、银行单独关联及事务回滚。状态只属于反提命令，不污染来源详情、普通列表或 read model/worker。

## 分段控件一致性（2026-09-28）

统计切换使用 `components/common/InvoiceCountSegments.tsx`（HeroUI 原生 Tabs/Indicator）。输入是页面提供的 key/label/count/selectedKey/pending，输出仅选择事件；共享组件不持有请求、缓存或业务状态。仍按发票张数，保留页面现有分类、筛选、导出与权限合同。删除页面旧的 tabs 私有 CSS；影响范围限三个显式使用此组件的发票页面。

## 2026-09-28 删除无消费的组数摘要

删除 `summary.matchedOaCount/matchedBankTransactionCount` 及 SQL、纯组装、前端类型/API 映射中的旧计算：它们原本统计有关联的展示组而非对象数量，且没有业务 UI 消费者。内部金额匹配使用的 matched_oa_count/matched_bank_count 属于支付判定，不受此次删除影响。发票张数、筛选、导出、分页和关系命令保持原合同。

## 2026-09-28 反提抽屉完整号码与筛选文案

- 待处理清单标题为“未关联 OA 的发票”，流水筛选为“全部 / 已关联流水 / 未关联流水”，计数沿用 `relationCounts` 的全量发票张数；未关联流水不代表未付款。“全部”包含另外两类，不是第三个互斥分类。
- 候选、暂存和已提交表格的发票号码列只在本抽屉内预留列宽并允许完整换行，保留原字符串与前导零；取消候选号码的 280px 限制和继承省略行为。公共 FinanceTable 的默认样式不改，无新增 API、统计、状态或网络请求。
- 组件测试覆盖完整号码、新文案与三个筛选参数；Playwright 覆盖 20/30 位号码、前导零、桌面/窄屏/150% 缩放等效视口的字形边界和分页筛选流程。既有预览、选择、占用及草稿流程回归继续运行。
- 测试责任：前端组件、关键流程集成与既有回归适用；业务规则、service、API 合同未修改，不新增对应测试。列表查询沿用现有合同并验证筛选刷新；独立 read model/cache/worker 不适用。生产只读 preview 与页面视觉核对，不创建或提交真实 OA，无迁移或数据库备份。


## 2026-09-28 独立导出筛选

本模块导出抽屉、统计与文件的当前合同见 [独立导出筛选与真实对象计数](../../dev/export-filters-and-counts.md)。原导出预览接口和样例数据不再作为运行时输出；统计与下载复用领域查询。页面权限不变，无持久化、worker 或 read model 变更。

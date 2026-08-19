# 关联台模块边界与 I/O

日期：2026-08-20

## 职责

### 负责

- 通过 direct canonical API 读取 OA、银行流水、发票、ETC 批次和正式关系，并把当前提交事实划分为 `paired` / `unpaired`。
- 提供同一只读快照内的首屏统计与两区首页、区域级搜索/筛选/排序、cursor 分页、filter options、group/row detail 和异常抽屉。
- 提供人工正式关联、关系级撤回和异常人工审阅；撤回关系恢复最近一次确认前的稳定拓扑，撤回异常放行只改变展示分区。
- 对“OA发票附件未解析”提供一个右侧录入抽屉：补充凭证只关联当前 OA 子付款项且不进发票池；手工录入整批进入统一发票池并原子扩展当前正式关系。
- 保持权限、审计、幂等、canonical member exact-set、preview fingerprint、relation/entity version 和稳定加锁顺序。
- 写成功后由页面执行一次普通 direct GET，读取已提交事实；页面不等待 projection worker。

### 不负责

- 不维护 Workbench 页面 read model、active generation、freshness/source-version gate、page Redis payload cache、refresh-status polling 或 page refresh worker。
- 不把 OA、银行流水、发票复制成新的统一写模型。
- 不持久化自动候选、matching decision 或 `open/proposed` 关系状态。
- 不根据金额、旧 `case_id`、UI metadata 或来源前缀在 route/前端本地推断正式关系。
- 不提供人工创建异常、逐行“标记异常”或发票“忽略/恢复忽略”入口；异常只能由 canonical 规则产生，再由 `/api/workbench/exceptions/review` 进行人工分类与分区决定。历史人工异常和 ignore/restore 记录只用于审计展示。
- 不直接写 relation SQL、matching dirty-scope SQL 或 outbox SQL；写入必须进入对应 command/UoW。
- 不拥有其它页面的读取副本；`workbench-matching` 是独立领域 worker。

## 读取链路

```text
ReconciliationWorkbenchPage
  -> Workbench HTTP routes
  -> WorkbenchQueryFacade
  -> PostgresWorkbenchPageQueryRepository
  -> PostgreSQL canonical facts + active formal relations
```

- route 只做认证、权限、参数验证和 HTTP 错误映射。
- facade 只编排 direct repository 和稳定 DTO；不得依赖 Redis、refresh gateway、runtime queue 或 read-model repository。
- repository 拥有 PostgreSQL 表结构、参数化 SQL、短 `REPEATABLE READ READ ONLY` 事务和 statement timeout。
- GET 必须是纯读：零 enqueue、零 RabbitMQ、零 page Redis、零 generation/read-model table I/O。
- DTO 组装可在取完原始结果并释放数据库连接后完成；禁止 assembler/service 隐藏额外 SQL。

## 输入 I/O

| 输入 | Owner | 合同 |
| --- | --- | --- |
| canonical OA | OA canonical repositories | 同一 tenant 下合并 completed OA 与 in-progress admission；输出稳定 typed identity、权威申请时间和 `workflow_status=completed|in_progress`。in-progress admission 的申请时间只从 source snapshot 的 `detail_fields.申请时间/申请日期`（兼容同义顶层字段）读取，并同时作为 OA 搜索、筛选和排序日期；不得回退到审批完成、创建、修改或更新时间。同一 OA 同时命中两源时 fail closed。费用子项仅用于展示和金额比较，不成为 relation member。 |
| canonical bank | bank canonical repositories | 使用稳定 typed identity、权威金额/方向/账号/交易日期和既有有效分类结果；页面查询不重新实现分类规则。 |
| canonical invoice / ETC | invoice / ETC canonical repositories | 只读取可见 canonical invoice、正式 OA attachment `source_links[]`、已提交 ETC business batch/link；同一发票在同一 OA 可携带多个子付款项来源边，direct DTO 去重发布 `source_expense_item_ids[]`，不得压回单值。ETC summary 把 canonical link 与 ETC business invoice 视为同一现代来源层：link 只覆盖相同发票身份，未桥接的 business 成员仍必须保留；只有完全没有现代来源时才回退 legacy submission。身份优先使用统一发票号命名空间，其次稳定 row id，禁止按“批次存在任意 link”淘汰其它成员或从 raw payload 猜 owner。 |
| active formal relations | workbench-relations | 只接受 `status=active` 的正式关系。成员以 `(row_type,row_id)` 精确匹配；parallel `row_types/row_ids` 长度不一致、typed owner 重复或缺 canonical member 时 fail closed。 |
| completion metadata | workbench-relations | 关系是否要求 OA/发票及 mode 豁免使用确认时持久化事实，不在 GET 中重跑当前规则。关系含 in-progress OA 时完整 case 保留在 `unpaired`。 |
| anomaly decisions | workbench exception repository | 当前 canonical group 同时计算 OA—流水、OA—发票、流水—发票按分差异，并保留付款项—发票连通分量及 `absent / unparsed / unassigned` 附件状态。普通付款关系的流水金额按同一正式关系内 `支出合计 - 收入/退款合计` 计算净额；经外部往来款正式确认的 `turnover_manual_closure` 零差额闭环改用付款本金侧与 OA 比较，避免把同额归还收入抵减成零。该特例只读取 relation mode，不解析备注。金额异常只有在唯一来源边证明具体单票与具体子付款项时才定位到发票；一项多票落 OA 子付款项，组级/流水—发票差异落 OA 或流水，禁止复制到任意发票。任一异常默认阻断进入已配对区；人工决定绑定当前 bundle fingerprint，接受后 DTO 的 chip 文案统一加 `已接受：` 并携带审阅审计字段。 |
| OA 补充凭证 | `app.workbench_oa_supporting_documents` + `app.file_objects` | 支持点击选择或拖拽 JPG/JPEG/PNG/PDF，校验扩展名、文件签名和 25MB 单文件上限；以 `oa_row_id + expense_item_id` 精确关联，并以目标付款项 + 内容哈希保证重试幂等，可列表、内联预览、软删除。上传/删除请求把关系目标、文件名/类型/大小、可用性与成功/失败结果固化到 operation audit；只有仍有效的成功文件可从详情预览。它不是 canonical invoice，不写 `app.invoices`、import session、relation member、matching 或 read model。 |
| OA 手工发票补录 | `POST /api/workbench/oa-invoice-supplements/manual` | 只接受当前用户完整的批量 manual import preview；确认全部发票、写 `oa_expense_item_invoice` 来源边并通过正式 relation command 创建/扩展目标 case，单事务同成同败；同一请求把最终 case、OA 子付款项及每张发票的号码、销购方、日期与金额快照固化到 operation audit。 |
| 历史发票来源修复 | `import_audit_repair_ops` | 只允许运维显式提交 invoice ids、case、OA row、expense item 和精确价税合计；先只读 dry-run 生成来源指纹与 rollback manifest，execute 在 serializable 事务、advisory lock、旧 `source_links` CAS 和操作审计内仅追加缺失的 `oa_expense_item_invoice` 来源边。冲突来源、数量/总额漂移或重复 identity 整笔拒绝；不是页面运行时 fallback。 |
| list query | Workbench API | `month`、`zone`、allowlisted sort、区域 search、column/time filters、可选 `exception_bucket`、`page_size` 和 opaque `cursor`。复合列只接受 `direction/account/bankTag`、`oaType/workflow/applicant`、`expenseType/project` 类型前缀；所有字符串和集合有界，SQL 参数化。 |
| write command | Workbench action routes | server-authenticated actor/tenant、canonical member exact-set、preview id/fingerprint、expected relation/entity versions、idempotency key。页面 read-model version 和 cursor 均不是写 CAS。 |

## Direct SQL 合同

### Scope-first group spine

查询固定遵循以下方向：

```text
requested tenant/scope
  -> scoped canonical fact seeds
  -> touched active relations
  -> typed relation members WITH ORDINALITY
  -> required canonical member ids
  -> narrow member/group spine
  -> completion + anomaly + structured filters/search
  -> exact stats + cursor page keys
  -> only-visible-page set-based hydration
```

- `tenant`、月份、可见状态必须在各源表入口下推；禁止先 materialize 全历史 OA/流水/发票/关系后再过滤 scope。
- 月份查询先找该月触及的正式关系，再补载关系的完整跨月成员；不能截断正式 case。
- GIN `row_ids` 只能做候选剪枝，最终必须按 `row_types/row_ids WITH ORDINALITY` 精确匹配。
- 只在查询计划证明一个小集合被重复消费时使用 `MATERIALIZED`；禁止把 giant canonical CTE 当通用事实层。
- group 指标一次 set-based 聚合得到 totals、三栏 row counts 和排序 min/max；禁止每组 correlated scan。
- hydration 只处理当前 `page_size + 1` keys，按 typed ids 批量取全组成员；SQL 条数不得随 group/member 数增长。

### 首屏与分页

- `GET /api/workbench` 在一个短 `REPEATABLE READ READ ONLY` transaction 内返回 summary、statistics、invoice inventory 与 paired/unpaired 各 10 组首页。精确 total 不变，后续使用 opaque cursor 自动续读。
- 首屏 candidate spine 只构建一次；禁止依次执行 summary、paired count/page、unpaired count/page 六套重复 canonical CTE。
- `GET /api/workbench/groups` 返回 `groups,total,row_counts,page_size,has_more,next_cursor`。
- compact summary group 保留组级 `amount_check`；每行不重复输出相同 `relation_amount_check`、对象身份仲裁字段、来源 identity aliases 或 detail-only metadata。ETC 发票栏首屏额外保留第一张真实 `source_kind=etc_invoice` 的窄行，隐藏 summary 锚点；其它发票只保留总数，用户展开时复用既有 group detail 一次加载全部成员。前端只把组级金额判断继承给可见行 chip，完整诊断仍由 detail I/O 提供。
- `total` 和 row counts 是当前 query 的精确值；统计发生在 cursor 条件前。cursor 只减少深页排序/hydration，不能把 exact count 伪装成常数复杂度。
- cursor 绑定 scope、zone、sort、search、filters、exception bucket 的规范化 query hash，并保存完整稳定排序 tuple 与 `group_key` tie-breaker。
- cursor 是 opaque pagination boundary，不是 MVCC snapshot、read-model version、permission token 或写 CAS。跨 HTTP 请求采用 latest-committed 语义；并发写时页面在 mutation 成功后清空 cursor/selection 并重读首屏。
- 禁止 OFFSET fallback 和客户端解析 cursor 内容。

### 搜索、筛选与 filter options

- search 只覆盖用户可见的 OA/流水/发票结构化字段。ETC summary 额外支持 external business batch ID、business batch ID、submission batch ID、成员发票号和批次精确金额；成员发票号用同一 `exists` 子查询命中后返回完整组，不把全部成员塞进 summary payload。内部 row/group id、`raw_payload`、`source_payload` 和其它 detail-only 文本不属于搜索面。
- `%`、`_`、反斜杠按 literal escape；金额先 canonicalize 后比较 numeric，日期使用显式表达式。
- 任一成员命中返回完整 group；不得只返回命中行。
- 同列多值 OR，不同列/不同 pane AND；同一 pane 的多个列条件必须由同一 member 满足。
- 银行金额复合筛选内，方向、付款账号、canonical 流水标签各自 OR，三类同时存在时彼此 AND，且必须由同一 bank member 满足。账号展示读取既有 `bank_account_mappings`；流水标签候选与过滤只对当前 eligible bank ids 批量复用银行明细 canonical 分类 owner，不复制分类规则。
- OA 申请人复合筛选固定提供“支付申请 / 日常报销”和“已完成 / 进行中”，申请人姓名仍来自当前候选域；OA 类型、流程状态、申请人各自 OR、跨组 AND，并由同一 OA member 满足。OA 项目复合筛选的费用类型与项目名称各自 OR、跨组 AND，并由同一 `expense_items[]` 元素满足；只有没有子项时才读取父 OA 顶层字段。
- `GET /api/workbench/filter-options` 保留其它条件、移除目标列自身条件，从 eligible groups 直接生成候选；`未填写` sentinel 统一。三个复合菜单返回带类型前缀的 `value` 和可选 `group`，旧无前缀复合值拒绝，不保留旧解析分支。
- options 按 `(label,value)` cursor 分页，默认 100、最大 200，返回 `options,page_size,has_more,next_cursor`；不计算无用 total，不读取当前浏览器已加载 rows，也不使用 Redis fallback。

### 异常与详情

- `/groups?exception_bucket=unpaired|paired` 在 SQL group spine 上应用 anomaly fingerprint 和人工决定，精确计数并有界分页；bucket 必须与 zone 相同，前端每次只读取当前 bucket，不得并行读取两区或 drain full-detail pages 后本地合并。
- SQL 候选分区和分页后 Python hydration 必须复用相同的流水净额口径；`1050` 支出与同关系 `35` 退款收入的银行总额为 `1015`，不得先按 gross `1050` 分入异常区再在 DTO 层改正。
- 历史 OA 附件 parent identity 必须在 SQL 候选分区与 hydration 两层都通过 OA 外部 identity + 明细 `row_index` 映射到当前 canonical 子付款项；不得让 summary/full 得出不同 zone，也不得按金额或展示顺序猜测。
- group detail 按 active case/group typed owner 窄查；row detail 按 typed identity 与 active relation membership 窄查。
- detail 读取 latest committed 事实，不接受 `expected_read_model_version`，不构建全 scope group CTE。
- summary 列表禁止携带 raw payload、OCR/附件全文和完整 detail fields；折叠内容只在用户展开后读取。

## 输出 I/O

- Workbench bank row DTO 对当前可见页银行流水输出 canonical `category_code`、`category_label`、`category_label_path`、path/source 字段与必有的 `category_resolution_status`；前端分类 chip 优先以 `category_label_path` 按 `主标签 / 子标签`（含更深层级时显示完整路径）展示，只有完整路径缺失时才回退 primary/sub 或 leaf label；未命中分类时状态为 `unmatched` 并显示“待分类”。分类投影只对分页后可见 bank typed IDs 在同一只读 snapshot 内批量执行一次，不读取 Bank Details 页面 payload、不复制分类规则、不逐行查询。

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| combined initial | 前端 | `month,scope_key,summary,statistics,invoice_inventory,paired,unpaired`；两区使用相同 zone page shape。`invoice_inventory.inventory_etc_summary_batch_count` 只统计 `oa_submitted/manually_marked_submitted/closed` 的 distinct ETC external batch，不把 draft/withdrawn 历史状态计成已提交批次。禁止 `read_model_status/read_model_version/active_generation_id/source_versions/refresh_enqueued/job`。 |
| zone page | 前端 | `groups,total,row_counts,page_size,has_more,next_cursor`；列表只含 compact summary DTO。 |
| filter options | 表头菜单 | `options[{value,label,missing,group?}],page_size,has_more,next_cursor`；菜单惰性读取并支持 abort/latest-wins，`group` 只控制分组标题。 |
| paired groups | 前端 | 冻结要求满足、OA workflow 已完成且无异常，或全部当前异常已由用户完成人工分类并明确 `accept_paired` 的 active formal relation；chip 显示人工选择的具体金额分类或“无异常”，系统检测项仍保留作审计。 |
| unpaired groups | 前端 | 无 active owner 的 singleton，以及要求未满足、含 in-progress OA、存在 pending/`keep_unpaired` 异常的完整 active relation；关系本身不被删除或拆散。 |
| OA expense/invoice display | 前端 | OA direct page DTO 输出 `expense_items[]` 及每项 `supporting_documents[]`；summary hydration 保持原有窄字段投影，录入抽屉通过专用列表 API 读取权威补充凭证。OA attachment/manual supplement invoice 输出复数 canonical `source_expense_item_ids[]`；一张发票只出现一次。只有附件数为零且没有通过 `oa_expense_item_invoice` 精确绑定到当前子付款项的正式发票时显示“无OA附件”；附件存在但未产生正式发票显示“OA发票附件未解析”和“录入发票”；已有父 OA 发票但缺子项来源显示“OA发票待归属”。APP 内正式发票来源边只补足归属证明，不改写 OA 原始附件数。补充凭证同行展示文件名与预览链接，但不得伪装成发票或进入金额合计；上传/删除成功后只局部更新当前子付款项，不触发关联台全量重读。 |
| write result | 前端 | 保留业务结果、affected ids/scopes、preview/CAS/idempotency信息；禁止 operation projection 和页面 freshness metadata。成功后恰好一次普通 direct refetch。 |
| shared relation refresh | `workbench_relation` worker / other pages | confirm/withdraw 等 canonical relation 写入仍按 shared relation 合同标记精确 scope；这不是 Workbench 页面读取依赖。 |
| matching dirty scope | `workbench-matching` | 会改变确定性正式关系的 canonical write 继续标记精确月份；页面 GET 不触发 matching。 |

- `workbench-matching` 的运行事实仅来自 `job.workbench_matching_dirty_scopes`、worker heartbeat 和错误字段；它不是 Workbench 页面 read model，也不创建 `workbench_matching` BackgroundJob 或全局页面进度。
- Page Audit 对每个已提交 ETC external batch 独立检查正式 OA 的 `normalized_payload.etc_batch_id` 与 active relation：缺 OA 输出 `submitted_etc_batch_oa_missing` warning，有 OA 但未挂入关系输出 `submitted_etc_batch_relation_missing` warning，只有 metadata marker 但 exact `etc-summary-*` invoice member 未进入关系输出 `submitted_etc_batch_relation_member_missing` warning；active relation 的无效 canonical 成员仍是 error。只有 marker 与真实成员同时存在才算 ETC 归属闭合，warning 用于暴露可修复链路缺口，不把未配对事实伪装成完整关系。

## 写入与一致性

- 页面是否可写只由 session/permission、global mutation block 和 OA sync safety gate 决定；不再存在 page read-model freshness/version gate。
- 发票行只提供详情入口，不挂载逐行三点菜单。正式关联与撤回由区域顶部 selection action 负责；自动异常由右侧异常抽屉负责人工审阅。旧 `exception/preview`、`exception/apply`、`mark-exception`、`update-bank-exception`、`oa-bank-exception`、`cancel-exception`、`ignore-row` 和 `unignore-row` HTTP 入口均已退役并返回 `404`，禁止重新引入兼容分支。
- preview 从 canonical typed selection 一次有界读取所选成员和必要 OA attachment context；不读取完整页面 payload。
- submit 在 relation UoW 内重读并锁定 canonical rows，验证 exact-set、case owner、版本、preview/topology fingerprint 和幂等。
- deterministic matching 按 OA 的 exact `normalized_payload.etc_batch_id` 发现 submitted ETC batch，并在读取 fact batch 前把候选 OA 申请月份并入请求 scope；新建或补全正式关系时必须把 deterministic `etc-summary-*` 作为 `invoice` member，同步持久化 `etc_batch_link`。仅有 metadata 不构成完整关系；summary 已由其它 active relation 拥有时 fail closed。
- confirm 接受至少两个不同 canonical 成员，允许同类型组合；仅 `amount_check.requires_note=true` 时要求备注。
- withdraw 只接受一个完整可撤回 active relation 的精确成员集合，恢复最近一次确认前的稳定拓扑；当前与前序关系锁集合一次全局稳定排序后加锁。
- 写事务成功不 enqueue `workbench.read_model.refresh`。前端不应用本地 operation projection，不轮询 generation；direct refetch 失败时明确显示“写已提交、页面刷新失败”，不得重试 mutation。

## 前端请求拓扑

- mount：一个 combined initial、权威 OA sync status、settings；不请求 `/api/workbench/refresh-status`。
- query/filter/sort 变化：abort 上一请求，只重取受影响 zone 并清空该区 cursor；不重复读取 summary 和另一 zone。
- pagination/filter options/detail：每个 owner single-flight 或 latest-wins，有界 payload。
- mutation：一个 POST；成功后清 selection/cursor，并执行一次 normal direct GET。异常审阅把列表返回的可选 `detail_key` 原样提交以精确定位组；跨月关系写入全局决定，随后只读取决定对应的一个异常 bucket。
- 保留 OA sync safety poll、全局 App Health 与 background jobs provider；它们不是 Workbench page read model，不能借本迁移删除。
- OA 父记录的申请人栏始终显示时间 chip：有权威申请时间时只做原字符串格式化（包括移除 PostgreSQL `+08`/标准 offset 后缀，不做浏览器时区换算），缺失时明确显示“时间缺失”；日常报销子付款项不重复显示父 OA 申请人和时间。
- OA 子付款项/附件发票同行只在当前页 DTO 内做纯函数图分组；禁止为此新增逐项 API、React effect、read model、worker 或页面缓存。异常 chip 的 OA 跳转使用普通 `<a target="_blank" rel="noopener noreferrer">`，禁止轮询或操纵 OA SPA DOM 自动点击详情。
- 页面 rows 不写入 session storage/长期 cache。长列表继续分页；DOM virtualization 属于独立前端性能任务，不用 read-model 迁移夹带新框架。

## 统一详情展示合同

- OA、银行流水和发票详情统一使用共享 `EntityDetailContent` 与 HeroUI `Table`/`Chip`；标签在左、真实值在右，关联台不得再维护私有摘要表或嵌套圆角容器。
- 单条详情和多条详情使用同一字段合同；多条只按 `OA N`、`银行流水 N`、`发票 N` 重复单条分区，不输出关系概况、关系数量或“是否多条”。
- 仅展示 row detail API 实际返回且已登记为用户可见的 canonical 字段；内部 ID、raw/source 字段、关系元数据和推导字段必须在共享展示边界过滤。
- 点击先打开抽屉，再执行一个有界 row detail GET；禁止按成员 N+1。所有详情日期时间统一为 `Asia/Shanghai` 的 `YYYY-MM-DD`、`YYYY-MM` 或 `YYYY-MM-DD HH:mm:ss`，不得显示 `T`、`Z` 或 `+08:00`。

## 共享边界与跨页面隔离

必须保留：

- `workbench-matching` dirty scopes、worker、orchestrator 和正式 relation command。
- canonical identity、active formal relation、history、异常 decision、preview/UoW、审计和幂等。
- 独立 no-OA API/service；Workbench confirm 不恢复内部转账到 no-OA batch 的旧分流。
- 其他页面自己的 direct APIs、领域 workers、integration cache、RabbitMQ events 和 App Status entries。

Workbench direct repository 不得被其他页面当通用 fact gateway。其他页面在下一次自身 API 读取中，通过自己的 query repository 观察相同 canonical write。

## 页面 read model 退役合同

同一 release 的 active runtime 必须删除：

- Workbench page manifest/scope policy/App Status entry。
- `workbench.read_model.refresh` enqueue、handler、Rabbit dispatcher event 和 worker registration/env/unit。
- page generation projection/freshness/status/cache/version owners及其生产 wiring。
- `/api/workbench/refresh-status`、前端 poll/reload/forced-fresh/operation projection。
- generation rehydrate/convergence/prune active tooling和 prune timer。
- SLO probe、deploy gate、tests 和长期文档中的 page-generation 当前事实。

Migration `0149_remove_read_model_runtime.sql` 在确认遗留 schema 只含 allowlist 对象后，forward-only 删除整个 `read_model` schema 与 dirty-scope 表，并终止旧 refresh 事件。它不删除 `app.workbench_pair_relations` 或主数据库；迁移后不能回滚到依赖 projection 的旧 release，只能向前修复。

## 性能合同

- 当前生产硬合同：authenticated bounded GET 错误为 0，Workbench blocking probe P95 `<=1000ms`、P99 `<=2000ms`，连接池无 timeout/backpressure。
- 优化目标：P50 `<=600ms`、P95 `<=800ms`、P99 `<=1200ms`；目标未达到时必须如实报告，不能因为低于硬合同就宣称比旧 read model 更快。
- 每个 endpoint 的 SQL 数量必须有界且无 N+1。当前 direct page repository 的固定业务 SQL 上限（不计 `SET TRANSACTION` / `SET LOCAL` 两条事务控制语句）为：initial `<=9`、groups `<=7`、filter options `=1`、group detail `<=7`、row detail `<=5`、preview `<=6`、exception page `<=8`。这些是防 N+1 的回归上限，不是延迟目标；2026-08 disposable PostgreSQL 小型 fixture 实测 initial `9`、groups `7`、filter options `1`、group detail `7`、row detail `5`、preview `6`，主 candidate SQL 约 `5–16ms`，ETC page hydration 已从 `5` 条合并为 `1` 条。生产验收仍以本节 p95/p99、pool hold time、buffer/temp-spill 和目标规模 EXPLAIN 为准；不得用固定条数替代性能证据。
- all-scope candidate spine 必须集合式复用 relation member rollup 和 in-progress OA relation set，不得按 relation 重复 correlated scan；请求事务禁用单请求 PostgreSQL gather worker，避免多个相同页面请求争抢数据库 CPU。该执行参数只属于关联台 direct repository 的只读事务，不污染其它页面连接或全局数据库设置。
- 先重写 query shape，再用测试库 `EXPLAIN (ANALYZE, BUFFERS)` 判断索引；禁止先堆索引或引入第二套物化结构。
- 生产只运行 bounded authenticated GET 和 plain `EXPLAIN`；不在生产运行 `EXPLAIN ANALYZE`。
- `month=all + exact total + 任意 substring search` 的成本不可能与数据规模无关。若重写和证据索引后仍不达 SLO，必须显式调整产品合同或重新评估物化读取，不能暗加 Redis/fallback 冒充 direct。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Routes / wiring | `backend/src/fin_ops_platform/app/routes_workbench.py`、`backend/src/fin_ops_platform/app/server.py` |
| Query service | `backend/src/fin_ops_platform/services/workbench_query_facade.py`、`workbench_filter_options.py`、`workbench_page_cursor.py` |
| Direct repository | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py`、`workbench_page_hydration.py`、`workbench_page_selection.py`、`workbench_oa_supporting_document.py` |
| Relation writes | `workbench_write_facade.py`、`workbench_relation_command_service.py`、`workbench_uow.py`、`workbench_invoice_supplement_service.py`、relation repositories |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/features/workbench/`、`web/src/components/workbench/WorkbenchInvoiceEntryDrawer.tsx`、`web/src/components/imports/ManualInvoiceBatchEditor.tsx` |
| Runtime/deploy | page retirement portions of runtime registry/manifest/worker/deploy；shared relation/matching files不属于删除范围 |
| Tests | `tests/test_workbench_*`、`web/src/test/Workbench*`、`web/e2e/workbench-*` 及跨页面 regression |

## 测试与验证

- 业务核心：typed identity、任意类型组合、不完整 relation、三组按分差异、三类附件状态、金额异常精确显示目标、手工补录整批原子性、exact-set、withdraw 前序拓扑、异常 accept/keep/withdraw。
- repository/service：单请求 RR/RO、scope-first、fixed query count、batch hydration、exact totals、cursor/query hash、search/filter/facet/exception 等价、timeout/rollback。
- API：direct response shape、不含 RM 字段、refresh-status 不存在、GET 零 queue/cache、权限和稳定错误映射、action 无 expected RM version。
- runtime：page `workbench` registry/manifest/event/worker/timer 为零；`workbench_relation` 与 matching 正常。
- frontend：mount 无 status poll、zone-only query、cursor pagination、单 bucket bounded exception drawer、单一录入抽屉内两种模式、多发票本地保存后整批提交、OA/global gates、每次写一次 mutation + 一次 canonical refetch。
- E2E：direct load、confirm/refetch、withdraw 恢复、incomplete relation、异常、权限、no-OA 隔离、direct failure 不 fallback。
- 跨页面：bank details、pending invoices、OA、cost/turnover、batch accounting、no-OA、App Health 和 operations 不产生回归或污染 I/O。

## 数据与回滚安全

- 主切换不创建任务专属数据库备份，不 drop canonical facts、page generation tables 或主数据库。
- 发布只从合并后 exact remote-main SHA 的干净 release checkout 激活。
- 自动/人工回滚必须先进入维护模式，使用上一 immutable release 对保留的 page generation 表执行全 scope rehydrate 和 audit，验证 fresh 后再同时开放旧 backend/frontend/worker；禁止把 stale old generation 先暴露给用户。
- 若未来为物理表清理单独创建临时逻辑备份，只能删除该任务明确记录并核验的临时文件；平台 PITR/组织级备份不属于任务临时备份，不得删除。

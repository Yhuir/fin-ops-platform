# 关联台模块边界与 I/O

日期：2026-08-29

## 职责

### 负责

- 通过 direct canonical API 读取 OA、银行流水、发票、ETC 批次和正式关系，并把当前提交事实划分为 `paired` / `unpaired`。
- 提供同一只读快照内的首屏统计与两区首页、区域级搜索/筛选/排序、cursor 分页、filter options、group/row detail 和异常抽屉。
- 提供人工正式关联、关系级撤回和系统异常审阅；撤回关系恢复最近一次确认前的稳定拓扑，撤回异常放行只改变展示分区。
- 对“OA发票附件未解析”提供一个右侧录入抽屉：默认发票录入通过强身份创建或复用 canonical invoice 并原子扩展当前正式关系；次级补充凭证只关联当前 OA 子付款项且不进发票池、不参与配对。
- 对 active relation 内“发票待归属”的 relation invoice 提供显式费用明细归属：用户只可选择同关系内一个或多个真实 OA expense item；写入 `oa_expense_item_invoice` 来源边，不改变 relation membership 或 canonical amount。
- 对 active relation 内“无 OA + 全部收入流水 + 全部销项发票”的关系提供收据草稿编辑和打印：无论关系位于 paired/unpaired，都以当前 canonical 事实生成可编辑草稿和 A5 横向一联 PDF，保存不可变快照并记录生成/打印请求审计，不把收据写入统一发票池或关系成员。
- 保持权限、审计、幂等、canonical member exact-set、稳定加锁顺序，以及各 action 自己的并发合同：confirm 在提交事务内重解析并锁定 exact typed selection；withdraw 使用 preview fingerprint 与 relation/entity version。
- 写成功后由页面执行一次普通 direct GET，读取已提交事实；页面不等待 projection worker。

### 不负责

- 不维护 Workbench 页面 read model、active generation、freshness/source-version gate、page Redis payload cache、refresh-status polling 或 page refresh worker。
- 不把 OA、银行流水、发票复制成新的统一写模型。
- 不持久化自动候选、matching decision 或 `open/proposed` 关系状态。
- 不根据金额、旧 `case_id`、UI metadata 或来源前缀在 route/前端本地推断正式关系。
- 不根据金额、项目名称或展示顺序推断发票的 OA 费用明细归属，也不以新选择覆盖既有冲突或不完整的显式归属。
- 不提供人工创建异常、逐行“标记异常”或发票“忽略/恢复忽略”入口；异常只能由 canonical 规则产生，再由 `/api/workbench/exceptions/review` 进行审阅与分区决定。历史人工异常和 ignore/restore 记录只用于审计展示。
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
| canonical bank | bank canonical repositories | 使用稳定 typed identity、权威金额/方向/账号/交易日期和既有有效分类结果；同一次批量分类投影同时携带非空的 canonical `turnover_role / turnover_action_type / turnover_family`，不新增查询。页面查询不重新实现分类规则。 |
| canonical invoice / ETC | invoice / ETC canonical repositories | 展示读取可见 canonical invoice、正式 OA attachment `source_links[]`、已提交 ETC business batch/link；统计读取请求 scope 内统一发票池的全部 canonical invoice。ETC summary 仍是一个展示对象，但统计必须通过 canonical row id 或明确 `etc_invoice_id` 展开到批次真实 canonical 成员，并按 canonical row id 去重；禁止按金额、名称或顺序猜测成员。同一发票在同一 OA 可携带多个子付款项来源边，direct DTO 去重发布 `source_expense_item_ids[]`，不得压回单值。DTO 另以稳定、去重的 `source_kinds[]` 发布完整来源证据，并保留单值 `source_kind` 兼容结构；前端主来源只显示“OA附件”或“人工导入”，`oa_expense_item_invoice` 另显示“明细归属”，来源标签不得参与正式 relation owner 计算。source-owned 展示分组只接受 normalize 前的 untouched `source_expense_item_id` 精确命中当前 OA item：显式 `oa_expense_item_invoice` 优先，否则才接受当前 `oa_attachment_invoice`；任一有效边缺 item、多 OA、多 owner 或已正式属于其它 relation 均 fail closed。历史 parent alias/`row_index` 只可继续服务异常/单元格对齐，绝不能创建或移动展示分组。ETC summary 把 canonical link 与 ETC business invoice 视为同一现代来源层：link 只覆盖相同发票身份，未桥接的 business 成员仍必须保留；只有完全没有现代来源时才回退 legacy submission。身份优先使用统一发票号命名空间，其次稳定 row id，禁止按“批次存在任意 link”淘汰其它成员或从 raw payload 猜 owner。 |
| active formal relations | workbench-relations | 只接受 `status=active` 的正式关系。成员以 `(row_type,row_id)` 精确匹配；parallel `row_types/row_ids` 长度不一致、typed owner 重复或缺 canonical member 时 fail closed。 |
| completion metadata | workbench-relations | 关系是否要求 OA/发票及 mode 豁免使用确认时持久化事实，不在 GET 中重跑当前规则。关系含 in-progress OA 时完整 case 保留在 `unpaired`。 |
| anomaly decisions | workbench exception repository | 当前 canonical group 在三栏金额完整、方向明确时自动归为七种互斥金额分类，并保留 `absent / unparsed / unassigned` 附件状态；未知方向、冲突或缺栏不得猜测。relation 存在 OA expense item 时，每张无有效 item edge 的 relation invoice 生成且只生成一个 row-scoped `unassigned` item；没有 OA expense item 的关系不生成该异常。分页前的 SQL 状态只用三栏总额、成员/附件事实计算 review fingerprint 与分区，当前页 hydration 再以纯内存付款项—发票连通分量确定精确落点，禁止在全量 group spine 递归重算定位图。普通付款关系按净额比较，`turnover_manual_closure` 仅按 canonical mode 使用付款本金侧。只有唯一来源能证明具体明细时才输出行级定位，否则输出 group scope。异常审阅客户端只提交 group/bundle fingerprint 和决定；发票明细归属客户端提交目标 `unassigned` item fingerprint，二者不得混用。repository 持久化服务端推导的 evidence fingerprints、detected codes，以及已认证 actor id/account/name 快照与审阅时间；OA 账户缺失时 fail closed，禁止接收客户端 actor/人工分类或在页面读取时反查账户。 |
| OA 补充凭证 | `app.workbench_oa_supporting_documents` + `app.file_objects` | 支持点击选择或拖拽 JPG/JPEG/PNG/PDF，校验扩展名、文件签名和 25MB 单文件上限；以 `oa_row_id + expense_item_id` 精确关联，并以目标付款项 + 内容哈希保证重试幂等，可列表、内联预览、软删除。上传/删除请求把关系目标、文件名/类型/大小、可用性与成功/失败结果固化到 operation audit；只有仍有效的成功文件可从详情预览。另向发票导入页提供 active-only 全局只读 gallery：`(created_at,id)` keyset、每页最多 9 条、无 count/offset/blob，图片或 PDF 首页缩略图最长边 360px 并私有缓存。它不是 canonical invoice，不写 `app.invoices`、import session、relation member、matching 或 read model。 |
| OA 发票录入 | `POST /api/workbench/oa-invoice-supplements/manual/preview` + `POST /api/workbench/oa-invoice-supplements/manual` | 只接受当前用户完整的批量 manual import preview；preview 允许新发票或强身份唯一命中的 canonical 既有发票，疑似重复/歧义整批拒绝。确认全部发票、写 `oa_expense_item_invoice` 来源边并通过正式 relation command 创建/扩展目标 case，单事务同成同败；同一请求把最终 case、OA 子付款项及每张发票的号码、销购方、日期与金额快照固化到 operation audit。 |
| 无 OA 收入收据草稿与打印 | `POST /api/workbench/actions/receipt-draft` + `POST /api/workbench/actions/print-receipt` | 只接受一个当前 active relation，且该关系没有 OA、至少一条银行流水并全部为 `inflow`、至少一张发票并全部为 `output`；金额必须为正，流水交易日期、发票号与付款方必须完整，付款方规范化后必须唯一，币种必须唯一且为 CNY。一个 relation 固定返回一张收据，金额取全部收入流水合计，默认日期取最新收入交易日期；不得按每笔流水日期拆分或按发票购买方猜测归组。draft 只读，返回可编辑明细、关系版本、来源指纹、精确红蓝票冲销结果和异常。红票只解析备注中的 `被红冲蓝字数电发票号码：<20位号码>`；目标查询批量且号码精确，完整冲销剔除红蓝票，部分冲销保留蓝票净额，缺失/歧义/超额不得模糊兜底。print 重读同一 canonical 事实并校验关系版本、来源指纹、异常确认和明细合计；编辑后文档指纹相同才复用不可变 PDF，旧快照只保留审计用途。 |
| relation invoice 明细归属 | `POST /api/workbench/actions/assign-invoice-expense-items` | 只接受当前 active case 内一张 `invoice` 与 1～100 个去重的 `(oa_row_id, expense_item_id)` targets，并要求每个 OA member/item 仍属于同一关系；请求携带该发票行 `oa_invoice_attachment_unassigned` item fingerprint 和幂等键。UoW 先锁关系成员和 invoice source links，再重验 canonical rows、既有显式/历史来源、fingerprint 与 CAS；不同或不完整显式归属、已存在其它有效归属、成员或证据漂移均零写冲突。成功保留非显式历史来源、追加用户明确选择的 `oa_expense_item_invoice` 边并写 operation audit；相同 targets 重放为幂等成功。 |
| 历史发票来源修复 | `import_audit_repair_ops` | 只允许运维显式提交 invoice ids、case、OA row、expense item 和精确价税合计；先只读 dry-run 生成来源指纹与 rollback manifest，execute 在 serializable 事务、advisory lock、旧 `source_links` CAS 和操作审计内仅追加缺失的 `oa_expense_item_invoice` 来源边。冲突来源、数量/总额漂移或重复 identity 整笔拒绝；不是页面运行时 fallback。 |
| list query | Workbench API | `month`、`zone`、allowlisted sort、区域 search、column/time filters、可选 `exception_bucket`、`exception_view=amount|document_only`、七分类白名单 `exception_code`、`page_size` 和 opaque `cursor`。`exception_view` 必须与 bucket 同时使用，`exception_code` 只允许用于金额视图。复合列只接受 `direction/account/bankTag`、`oaType/workflow/applicant`、`expenseType/project` 类型前缀；所有字符串和集合有界，SQL 参数化。 |
| write command | Workbench action routes | server-authenticated actor/tenant、canonical member exact-set 和 idempotency key。confirm 提交在同一 UoW 内重解析并锁定 exact typed selection；withdraw 提交使用 preview id/fingerprint 与 expected relation/entity versions。页面 read-model version 和 cursor 均不是写 CAS。选择含 OA 且全部银行成员为显式 canonical `external_turnover` 时，preview/submit 复用 `TurnoverRelationService.preview_zero_difference_closure(...)`；只有同 family/counterparty/business semantics、本金与结算两侧齐全且零差额时才写 `turnover_manual_closure`，并按 OA 同方向本金侧计算。单边或非零差额选择仍是普通 `manual_confirmed`；缺 action/family/counterparty 等结构化字段 fail closed，禁止摘要、备注、显示标签或金额形态兜底。 |

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
- source-owned 展示归属必须在 search/filter/exact count/cursor/LIMIT 前一次 set-based 计算；无 active relation owner 时生成同一 `unpaired` OA+发票展示组，OA 已在 active relation 时只把发票作为 display-only 行带入该组。该计算不得改写持久化 relation，也不得把 display-only 发票用于 completion、anomaly、version、withdraw 或正式成员 action。
- hydration 只处理当前 `page_size + 1` keys，按 typed ids 批量取全组成员；SQL 条数不得随 group/member 数增长。

### 首屏与分页

- `GET /api/workbench` 在一个短 `REPEATABLE READ READ ONLY` transaction 内返回 summary、statistics、invoice inventory 与 paired/unpaired 各 10 组首页。精确 total 不变，后续使用 opaque cursor 自动续读。
- `statistics` 只返回 canonical OA/流水/进项/销项总数，以及已完成/进行中 OA、支出/收入流水、手工导入发票和 OA 解析新增发票数量；顶部进项/销项不得使用 ETC 折叠后的可见对象数。旧配对组、缺关系组和未配对对象统计字段已删除。
- 两区 `row_counts` 同时返回 `invoice` 与 `canonical_invoice`：`invoice` 只表示分页和布局使用的展示对象数，`canonical_invoice` 表示该区去重后的统一发票池 canonical ID 数。无区域筛选时，若同一 canonical 发票存在 paired owner 则只计入 paired，否则只计入 unpaired；两区 `canonical_invoice` 必须互斥且合计等于 `statistics.invoice_total_count`。ETC 折叠、展开或重复勾选真实成员不得改变该统计。
- 首屏 candidate spine 只构建一次；禁止依次执行 summary、paired count/page、unpaired count/page 六套重复 canonical CTE。
- `GET /api/workbench/groups` 返回 `groups,total,row_counts,page_size,has_more,next_cursor`；异常 bucket 请求 additive 返回 `selected_exception_code` 与 `exception_counts={total,amount_total,document_only,by_code}`，`by_code` 固定包含七个 code（包括零值）。
- compact summary group 只在组级保留 `amount_check`；row DTO 不再输出 `relation_amount_check` 或 `relation_note`，前端也不得把组级金额判断复制成流水行三角形、行级 tooltip 或其它第二异常入口。折叠栏以现有 `summary_row` 作为唯一闭合态展示 I/O；ETC 发票栏首屏只返回 canonical `source_kind=etc_invoice_summary` 汇总行和真实成员总数，不返回第一张真实发票。用户展开时复用既有 group detail 一次加载全部 `source_kind=etc_invoice` 成员，展开态不混入汇总行，收起恢复同一汇总行；汇总行缺失时前端显示明确空态，禁止从 `rows` 或详情成员推断兜底。完整金额诊断和确认备注只通过组级统一异常 I/O 提供。
- `total` 和 row counts 是当前 query 的精确值；统计发生在 cursor 条件前。cursor 只减少深页排序/hydration，不能把 exact count 伪装成常数复杂度。
- cursor 绑定 scope、zone、sort、search、filters、exception bucket/view 和调用方显式请求的 exception code 的规范化 query hash，并保存完整稳定排序 tuple 与 `group_key` tie-breaker。首屏未传 code、由服务端自动选中首个非零分类时，opaque cursor 内部同时封存该 resolved code；后续 cursor 请求继续省略 code，服务端强制复用 cursor 分类，即使期间 counts 变化也不得切换分类。客户端不得把响应中的自动选中 code 回填为新的 query 条件。
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

- `/groups?exception_bucket=unpaired|paired` 在 SQL group spine 上应用 anomaly fingerprint 和审阅决定，精确计数并有界分页；bucket 必须与 zone 相同，前端每次只读取当前 bucket，不得并行读取两区或 drain full-detail pages 后本地合并。
- `exception_view=amount` 按一个服务端权威金额 code 过滤；未显式传 `exception_code` 时按固定七分类顺序选择当前第一个非零 code。`exception_view=document_only` 只返回没有金额 code、但至少有一个 `absent|unparsed|unassigned` 附件异常的关系。金额与资料并存的关系只属于唯一金额分类；同一关系有多个资料 item 仍只计数和返回一次。`exception_counts` 基于当前 bucket 及其它 search/filter 条件计算，但不受当前 view/code 自身过滤影响；`page.total` 只表示当前筛选列表总数。
- SQL 候选分区和分页后 Python hydration 必须复用相同的流水净额口径；`1050` 支出与同关系 `35` 退款收入的银行总额为 `1015`，不得先按 gross `1050` 分入异常区再在 DTO 层改正。
- 历史 OA 附件 parent identity 仍可在 matching、异常定位与 hydration 的单元格对齐中共用 alias 边界；但 source-owned 展示分组必须在任何 alias/`row_index` normalize 之前读取原始 source links，并只认当前 item exact ID。`id / row_id / expense_item_id` 有多个非空值时必须全部相同，否则该 item fail closed。summary/full/detail 必须输出相同展示归属；不得按金额、项目、文件名、历史 row index 或展示顺序猜测 owner。
- group detail 按 active case/group typed owner 窄查；row detail 按 typed identity 与 active relation membership 窄查。`scope=all` 的 source-owned group 和 relation detail 必须先以目标 OA 的 exact-current item 集合一次性发现来源发票月份，再按这些有限月份集合水合全部 display-only 发票；不得退回全 scope group spine、cache fallback 或逐成员查询。
- detail 读取 latest committed 事实，不接受 `expected_read_model_version`，不构建全 scope group CTE。
- 发票 row detail 的用户可见关系状态只认 `invoice_bank_relation`。前端 Workbench API 映射必须从发票 `detail_fields` 删除通用原始键 `status`，并把已知 `invoice_type=input|output`、`invoice_source=manual_invoice_entry` 转为中文展示值；不得改共享详情组件、翻译 `pending` 或删除明确命名的其它发票状态字段。
- summary 列表禁止携带 raw payload、OCR/附件全文和完整 detail fields；折叠内容只在用户展开后读取。

## 输出 I/O

- Workbench bank row DTO 对当前可见页银行流水输出 canonical `category_code`、`category_label`、`category_label_path`、path/source 字段与必有的 `category_resolution_status`；前端分类 chip 优先以 `category_label_path` 按 `主标签 / 子标签`（含更深层级时显示完整路径）展示，只有完整路径缺失时才回退 primary/sub 或 leaf label；未命中分类时状态为 `unmatched` 并显示“待分类”。分类投影只对分页后可见 bank typed IDs 在同一只读 snapshot 内批量执行一次，不读取 Bank Details 页面 payload、不复制分类规则、不逐行查询。

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| combined initial | 前端 | `month,scope_key,summary,statistics,paired,unpaired`；两区使用相同 zone page shape。`statistics` 的发票统计只输出统一发票事实总数、进项、销项、人工导入、OA 解析新增入池；`invoice_inventory` 及普通可见、已提交 ETC 隐藏、额外 ETC、ETC 折叠批次、宽泛 OA 附件来源等旧诊断合同已删除。禁止 `read_model_status/read_model_version/active_generation_id/source_versions/refresh_enqueued/job`。 |
| zone page | 前端 | `groups,total,row_counts,page_size,has_more,next_cursor`；`row_counts.invoice` 是展示对象数，`row_counts.canonical_invoice` 是按 canonical ID 去重的业务统计数，`row_counts.rows` 继续只服务展示分页。列表只含 compact summary DTO。异常 bucket 请求 additive 返回服务端选中 code 和按唯一关系计算的双视图/七分类 counts。 |
| selection summary | 前端工具栏 | 数量按去重后的 canonical typed members；先由 OA/发票确定付款或收款主方向，银行金额按同向金额减反向金额计算。正式关系通常读取组级 `amount_check.oa_total/bank_total/invoice_total`，包括 `turnover_manual_closure` 的本金侧口径；`amount_check.direction=unknown` 的纯银行正式关系只有在组合主方向明确且全部正式银行成员已加载时按该方向计算净额，否则显示 `--`。禁止退回绝对值合计。 |
| filter options | 表头菜单 | `options[{value,label,missing,group?}],page_size,has_more,next_cursor`；菜单惰性读取并支持 abort/latest-wins，`group` 只控制分组标题。 |
| paired groups | 前端 | 冻结要求满足、OA workflow 已完成且无异常，或当前服务端异常 bundle 已明确 `accept_paired` 的 active formal relation；圆形感叹号是关系异常的唯一入口，原始系统分类 Chip、审阅审计及 `manual_confirmed` 的非空确认备注都只在该 Popover 展示。审阅人格式为 `操作账户（姓名）`，时间格式为 Asia/Shanghai `YYYY-MM-DD HH:mm:ss`，不得显示内部 actor id 或原始 ISO offset。精确归属于组内 OA、但不是正式 relation member 的发票可作为 `source_owned_display` 展示；它不改变正式成员、状态或动作。 |
| unpaired groups | 前端 | 无 active owner 的 singleton、由精确当前 item owner 证明的 OA+发票 source-owned 展示组，以及要求未满足、含 in-progress OA、存在 pending/`keep_unpaired` 异常的完整 active relation；正式关系本身不被删除或拆散，展示组也不伪装为正式配对。 |
| OA expense/invoice display | 前端 | OA direct page DTO 输出 `expense_items[]` 及每项 `supporting_documents[]`；summary hydration 保持原有窄字段投影，录入抽屉通过专用列表 API 读取权威补充凭证。OA attachment/manual supplement invoice 输出复数 canonical `source_expense_item_ids[]`；一张发票只出现一次。附件数为零且无精确正式发票来源时为“发票附件缺失”；附件存在但未产生正式发票为“发票附件未解析”并保留“录入发票”；同 relation 存在 OA expense items、但发票没有有效 item edge 时为 row-scoped“发票待归属”并只保留“选择 OA 明细”。唯一例外是 `batch_accounting + canonical etc_invoice_summary`：其发票归属事实源是 ETC 批次，不进入 OA 附件资料异常规则，金额仍按三栏 canonical totals 校验。这些分类不直接平铺，只通过对应明细的感叹号 Popover 展示。APP 内正式发票来源边只补足归属证明，不改写 OA 原始附件数。显式归属后的同行由下一次 canonical DTO 的 `source_expense_item_ids[]` 决定，前端不得本地挪行。 |
| relation receipt action / draft / PDF | 前端、浏览器打印 | paired/unpaired 的合格 active relation 都在 OA 栏显示唯一“编辑并打印收据”，singleton 不显示；动作遵循 Workbench 写权限。点击先读取 draft 并打开单一右侧抽屉，按 `银行收据!A1:J12` 一联版式编辑付款单位、日期、摘要、金额、备注、主管和经手人，实时显示与收入固定金额的差额；不平衡、字段无效或冲销异常未确认时禁止打印。最终点击必须同步打开打印窗口，再提交编辑内容；成功后加载 A5 横向 PDF blob 并触发浏览器原生打印，失败关闭空窗口并显示明确错误。动作不改变 relation、canonical invoice、统计或分区。 |
| write result | 前端 | 保留业务结果、affected ids/scopes、preview/CAS/idempotency信息；禁止 operation projection 和页面 freshness metadata。成功后恰好一次普通 direct refetch。 |
| shared relation refresh | `workbench_relation` worker / other pages | confirm/withdraw 等 canonical relation 写入仍按 shared relation 合同标记精确 scope；这不是 Workbench 页面读取依赖。 |
| matching dirty scope | `workbench-matching` | 会改变确定性正式关系的 canonical write 继续标记精确月份；OA authoritative snapshot 对 admission/completed OA 的匹配相关变化在同一事务标记实际月份及前后各两个月，payment-status-only 变化不触发；页面 GET 不触发 matching。 |

- `workbench-matching` 的运行事实仅来自 `job.workbench_matching_dirty_scopes`、worker heartbeat 和错误字段；它不是 Workbench 页面 read model，也不创建 `workbench_matching` BackgroundJob 或全局页面进度。
- Page Audit 对每个已提交 ETC external batch 独立检查正式 OA 的 `normalized_payload.etc_batch_id` 与 active relation：缺 OA 输出 `submitted_etc_batch_oa_missing` warning，有 OA 但未挂入关系输出 `submitted_etc_batch_relation_missing` warning，只有 metadata marker 但 exact `etc-summary-*` invoice member 未进入关系输出 `submitted_etc_batch_relation_member_missing` warning；active relation 的无效 canonical 成员仍是 error。只有 marker 与真实成员同时存在才算 ETC 归属闭合，warning 用于暴露可修复链路缺口，不把未配对事实伪装成完整关系。

## 写入与一致性

- 页面是否可写只由 session/permission、global mutation block 和 OA sync safety gate 决定；不再存在 page read-model freshness/version gate。
- 发票行不挂载逐行三点菜单；除详情外，只有 row-scoped“发票待归属”能从异常 Popover 发起“选择 OA 明细”。正式关联与撤回由区域顶部 selection action 负责；自动异常由右侧异常抽屉负责人工审阅。旧 `exception/preview`、`exception/apply`、`mark-exception`、`update-bank-exception`、`oa-bank-exception`、`cancel-exception`、`ignore-row` 和 `unignore-row` HTTP 入口均已退役并返回 `404`，禁止重新引入兼容分支。
- preview 把全部 typed selection 一次交给 canonical repository；不设业务数量上限、不截断，也不读取完整页面 payload。repository 只水合 selected rows 与正式关系描述符已经证明的同组成员，不再扫描 OA `source_links` 或隐式补附件成员。
- submit 在 relation UoW 内重读并锁定 canonical rows，验证 exact-set、case owner、版本、preview/topology fingerprint 和幂等。撤回提交从同一事务内已校验且已水合的 typed rows 严格构建 OA source alias map，不在事务外二次扫描；alias 歧义返回结构化 `workbench_write_conflict`，不得 first-wins、ID 自映射或继续写入。前端按 `canonical_selection_changed|canonical_selection_ambiguous|stale_relation_identity|stale_relation_version` 显示对应安全中文原因及 request id。
- invoice assignment 在独立 action UoW 内锁定并重验 active relation、typed members、OA expense items 和 invoice source links；只在当前 row anomaly fingerprint 与 CAS 均一致时追加明确 targets。成功不修改 relation topology；既有不同或 malformed 显式边不能被删除、替换或隐藏。
- deterministic matching 按 OA 的 exact `normalized_payload.etc_batch_id` 发现 submitted ETC batch，并在读取 fact batch 前把候选 OA 申请月份并入请求 scope；新建或补全正式关系时必须把 deterministic `etc-summary-*` 作为 `invoice` member，同步持久化 `etc_batch_link`。仅有 metadata 不构成完整关系；summary 已由其它 active relation 拥有时 fail closed。相同 typed members、mode、scope、actor、金额、metadata、rule 与 evidence 的重复计划必须是真 no-op：不刷新 relation `updated_at`、不追加 history、不上报 changed case；repository 对仅 normalized `updated_at` 不同的 payload 同样不得执行 upsert update。任何业务字段变化仍按现役正式关系写边界更新。
- deterministic matching 的 OA fact 输入同时读取 completed `app.oa_applications` 与 in-progress `app.oa_pending_payment_admissions`；两类事实共用 canonical 申请日期 SQL，缺失的可选日期回退权威申请日期，权威日期无效时按 OA row id fail closed。不得恢复只匹配 completed OA 的旧输入链，也不得把 payment status 当作匹配事实。
- confirm 接受至少两个不同 canonical 成员，允许同类型组合；仅 `amount_check.requires_note=true` 时要求备注。
- withdraw 只接受一个完整可撤回 active relation 的精确成员集合，恢复最近一次确认前的稳定拓扑；当前与前序关系锁集合一次全局稳定排序后加锁。
- 页面可以一次选择 20 条以上记录确认，也可以从 paired/unpaired 选择一个大成员关系并带入其全部成员撤回；多条互不相关 active relation 仍不得合并成一次撤回。
- 写事务成功不 enqueue `workbench.read_model.refresh`。前端不应用本地 operation projection，不轮询 generation；direct refetch 失败时明确显示“写已提交、页面刷新失败”，不得重试 mutation。

## 前端请求拓扑

- mount：一个 combined initial、权威 OA sync status、settings；不请求 `/api/workbench/refresh-status`。
- query/filter/sort 变化：abort 上一请求，只重取受影响 zone 并清空该区 cursor；不重复读取 summary 和另一 zone。
- pagination/filter options/detail：每个 owner single-flight 或 latest-wins，有界 payload。
- selection：只消费当前已加载 DTO 与正式关系 `amount_check`，按成员数 `O(n)` 纯计算；点击、取消或整组展开选择都不新增 HTTP、数据库、read model、cache 或 worker I/O。
- mutation：一个 POST；成功后清 selection/cursor，并执行一次 normal direct GET。异常审阅把列表返回的可选 `detail_key` 原样提交以精确定位组；跨月关系写入全局决定，随后只刷新用户当前可见的一个异常 bucket，并保留当前 bucket/view/code，不自动读取或切换到关系迁入的目标 bucket。异常抽屉展开态默认仍是只读三栏；具备写权限时，“发票附件未解析”开放既有 `enter-invoice`，“发票待归属”开放 `assign-invoice-expense-items`。两者都必须先关闭异常抽屉再打开各自单一 action drawer，禁止双 overlay/focus trap。归属抽屉默认零选择、允许多选同 relation OA 明细；成功后只走上述一个 POST + 一个 canonical GET，不应用本地 operation projection。
- 保留 OA sync safety poll、全局 App Health 与 background jobs provider；它们不是 Workbench page read model，不能借本迁移删除。
- OA 父记录的申请人栏始终显示时间 chip：有权威申请时间时只做原字符串格式化（包括移除 PostgreSQL `+08`/标准 offset 后缀，不做浏览器时区换算），缺失时明确显示“时间缺失”；日常报销子付款项不重复显示父 OA 申请人和时间。
- OA 子付款项/附件发票同行只在当前页 DTO 内做纯函数图分组；禁止为此新增逐项 API、React effect、read model、worker 或页面缓存。共享异常感叹号组件通过 HeroUI `Link`（`target="_blank" rel="noopener noreferrer"`）打开 OA，禁止轮询或操纵 OA SPA DOM 自动点击详情。
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
| Routes / wiring | `backend/src/fin_ops_platform/app/routes_workbench.py`、`routes_workbench_actions.py`、`backend/src/fin_ops_platform/app/server.py` |
| Query service | `backend/src/fin_ops_platform/services/workbench_query_facade.py`、`workbench_filter_options.py`、`workbench_page_cursor.py` |
| Direct repository | `backend/src/fin_ops_platform/services/postgres_repositories/workbench_page_query.py`、`workbench_page_hydration.py`、`workbench_page_selection.py`、`workbench_oa_supporting_document.py` |
| Relation / invoice ownership writes | `workbench_write_facade.py`、`workbench_relation_command_service.py`、`workbench_uow.py`、`workbench_invoice_supplement_service.py`、`workbench_invoice_expense_item_assignment_service.py`、`invoice_expense_item_links.py`、relation/core repositories |
| 派生收据 | `workbench_relation_receipt_eligibility.py`、`workbench_relation_receipt_service.py`、`workbench_relation_receipt_pdf.py`、`postgres_repositories/workbench_relation_receipt.py`、`app.workbench_relation_receipts`、`app.file_objects` |
| Frontend | `web/src/pages/ReconciliationWorkbenchPage.tsx`、`web/src/features/workbench/`、`web/src/components/workbench/RelationGroupGrid.tsx`、`ResizableTriPane.tsx`、`WorkbenchZone.tsx`、`WorkbenchInvoiceEntryDrawer.tsx`、`WorkbenchInvoiceAssignmentDrawer.tsx`、`WorkbenchReceiptDrawer.tsx`、`web/src/components/imports/ManualInvoiceBatchEditor.tsx` |
| Cross-page gallery consumer | `web/src/components/imports/SupportingDocumentGalleryDrawer.tsx`、`ImportWorkflowPage.tsx`；只读，不取得资源写 ownership |
| Runtime/deploy | page retirement portions of runtime registry/manifest/worker/deploy；shared relation/matching files不属于删除范围 |
| Tests | `tests/test_workbench_*`、`web/src/test/Workbench*`、`web/e2e/workbench-*` 及跨页面 regression |

## 测试与验证

- 业务核心：typed identity、任意类型组合、不完整 relation、三组按分差异、三类附件状态、逐 relation invoice 的 row-scoped 待归属、金额异常精确显示目标、无 OA 收入收据的双分区资格、精确红蓝票净额、草稿平衡与单联 PDF 合同、手工补录整批原子性、exact-set、withdraw 前序拓扑、异常 accept/keep/withdraw。
- repository/service：单请求 RR/RO、scope-first、fixed query count、batch hydration、exact totals、cursor/query hash、search/filter/facet/exception 等价、invoice source-links CAS、显式多 target、幂等、冲突零写、timeout/rollback。
- API：direct response shape、不含 RM 字段、refresh-status 不存在、GET 零 queue/cache、权限和稳定错误映射、归属 action 的 relation/member/item/fingerprint 合同、收据 draft/print 的 active relation/version/source fingerprint/编辑文档/PDF 响应/审计合同、action 无 expected RM version。
- 补充凭证 gallery：active-only 稳定 cursor、每页 9 条、列表无 blob、图片/PDF 缩略图、损坏预览降级、只读用户可见，以及既有 scoped upload/list/delete/content 契约不变。
- runtime：page `workbench` registry/manifest/event/worker/timer 为零；`workbench_relation` 与 matching 正常。
- frontend：mount 无 status poll、zone-only query、cursor pagination、单 bucket bounded exception drawer、录票/归属互斥单抽屉、多发票本地保存后整批提交、归属默认零选择及显式多选、收据动作在两个分区的合格 active relation OA 栏各只出现一次、抽屉编辑/平衡/异常确认和最终同步打开打印窗口、OA/global gates。
- E2E：direct load、confirm/refetch、withdraw 恢复、incomplete relation、待归属发票显式选择后同行/消除对应异常、权限、no-OA 隔离、direct failure 不 fallback。
- 跨页面：bank details、pending invoices、OA、cost/turnover、batch accounting、no-OA、App Health 和 operations 不产生回归或污染 I/O。

## 数据与回滚安全

- 主切换不创建任务专属数据库备份，不 drop canonical facts、page generation tables 或主数据库。
- 发布只从合并后 exact remote-main SHA 的干净 release checkout 激活。
- 自动/人工回滚必须先进入维护模式，使用上一 immutable release 对保留的 page generation 表执行全 scope rehydrate 和 audit，验证 fresh 后再同时开放旧 backend/frontend/worker；禁止把 stale old generation 先暴露给用户。
- 若未来为物理表清理单独创建临时逻辑备份，只能删除该任务明确记录并核验的临时文件；平台 PITR/组织级备份不属于任务临时备份，不得删除。

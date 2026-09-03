# OA 集成模块边界与 I/O

日期：2026-08-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：OA 集成负责 OA identity、固定菜单投影、Mongo adapter、projection sync、附件识别、OA 凭证和 OA 相关页面/API 的外部系统边界。
- 当前缺口：OA 相关能力横跨 OA 待付款、ETC、进项反提、设置和权限，变更必须声明受影响模块；生产周期性自动读取必须由运维层定时 enqueue durable `oa.sync`，不能恢复 HTTP 进程内 polling。
- 旧代码删除条件：旧 Mongo 直读/手写 projection path 不再被业务页面直接调用。

## 职责边界

### 负责

- OA token → canonical username 身份适配；roles/permissions 仅作为信息字段。
- 把 Settings canonical ACL 投影到唯一 `finops:app:view` menu 的两个专用 OA role members：有至少一个页面的普通账号进入 `finops_app_user`，固定 005 进入 `finops_admin`。
- OA Mongo 读取、OA projection sync、OA 附件发票识别和 OA applicant credentials。
- 对 OA 待付款、ETC、进项反提等模块提供外部系统 adapter。

### 不负责

- 不拥有业务页面状态机。
- 不直接确认业务关联或付款。
- 不把外部 OA 数据直接当作页面 fresh read model。
- 不从 OA role/permission/menu 或 retired env 授予 APP access；APP evaluator 属于 permissions-and-audit。
- runtime 不清理 menu/role/binding；历史 non-dedicated binding cleanup 已退休，deploy 只读验证 exact topology 并对漂移 fail closed。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| OA session/token | `auth.py`、session API | 只认证 canonical username；roles/permissions 仅为信息，不能 grant APP access |
| OA password reauthentication | Settings data reset | 复用 OA login client 获取新 token，再经 identity endpoint 解析；只有 user id 与 canonical username 都等于当前 session 才成功。登录失败返回 false，配置/网络/未知响应 fail closed；禁止复用改密接口或凭 message/code 猜测成功。 |
| Canonical ACL snapshot | Settings owner | casefold-preserve-canonical 的 page-access accounts，加固定 `YNSYLP005` admin；是 role sync 唯一输入 |
| Fixed menu target | fixed OA selector env、OA MySQL | selector 必须精确为 `finops:app:view`；唯一 menu、三个唯一专用 role和 exact 三 binding 必须在任何 DML 前成立 |
| Deployment ACL preflight artifact | preflight/deploy control | 显式专项验收可接受 release-bound、secret-safe、SHA-256 绑定的 canonical ACL、migration/env 与 OA exact topology 只读证据；标准发布的任何 profile 都不消费 006 或该 artifact |
| OA Mongo/query | `mongo_oa_adapter.py` | projection sync 只调用 `load_sync_application_batch(scope_key, retention_cutoff_month=...)`：每个启用 form/scope 单次读取；`all` 在字段校验和附件解析前排除 retention cutoff 以前的文档，然后输出 `projection_records` 与 `admission_records` 两个不可变视图。前者遵守通用 OA form/status 配置；后者固定接纳 completed + in-progress，不受通用 status filter 污染。任一 form 读取失败或保留期内 status/identity 无法稳定判定时整批 fail-closed，不得提交部分集合。合法 in-progress 草稿允许未填写 amount/applicant/reason，仍按稳定 identity 进入 admission，空金额持久化为 `NULL`；保留期内 completed 缺既有必填业务字段仍 fail-closed。费用类型必须按表单精确读取：支付申请父记录读取 `EtcOAFormFieldMapping.category` 对应的顶层字段（默认 `category`，环境可覆盖），日常报销明细只读取 `schedule[].purposeType`；不得恢复两种表单共用候选键或递归同名字段搜索。两者都复用 `oa_draft_prefill.OA_APPLICATION_TYPE_OPTIONS` 映射为真实中文费用类型。`schedule[].category`、`schedule[].feeType` 和 `data.detailReimbursementType` 均不得污染日常报销费用类型。只有 OA 显式返回 `13s` 时才是“其他”，未知码或无法从既有确定性文本规则判断时保持空值。 |
| OA sync event | `job.outbox_events(event_type='oa.sync')` / runtime worker | 普通同步使用 month/all scope；设置页精确附件刷新复用同一 event type，并显式携带 `operation=refresh_attachments + row_ids[]`。两者都必须入 durable queue；HTTP 进程不得 inline sync、自行轮询 Mongo、执行 OCR 或承担附件发票 canonical promotion。精确刷新只处理请求中的 completed OA 或 `in_progress + expense_claim`，不执行权威 snapshot stale deletion。 |
| OA attachment/import | `untrusted_document_policy.py`、OA attachment services | 下载后的附件必须先统一校验后缀、签名、类型和资源上限，再进入 PDF/DOCX/JPEG/PNG 解析或 OCR；图片只允许 JPEG/PNG 并先规范化，DOCX 内嵌图片逐个走同一边界。未知二进制、伪装后缀、PSD 和超限文件 fail closed，禁止 raw bytes OCR。PDF 正式发票识别只有一个按页 representation 边界：每页先解析文本，文本没有形成正式发票强 identity 时才渲染同一页并 OCR；OA 解析保留全部页面并按正式 identity 去重，人工录入只消费首个正式发票证据。禁止保留 OA text-only 与人工 PDF OCR 两套分叉实现，也禁止把相邻计数拼出的 21 位数字截断猜成 20 位数电发票号。正式税票金额必须同时满足两位小数边界和 `未税金额 + 税额 = 价税合计`，压平文本形成的伪金额不一致时 fail closed。单文件逐页保留解析 segment；同一子付款项允许绑定多张正式发票，同一物理附件也允许在同一 OA 的多个子付款项保留多条来源边。解析 cache 以 OA 内物理附件身份去重，重复出现只解析一次，输出再绑定当前 expense item；识别结果必须保留 attachment、expense item 与 OA row 来源并可追踪。铁路电子客票由现有 `railway_e_ticket_invoice` 模板解析并通过正式发票准入；`票价: ¥145.00` 后紧邻长电子客票号时，金额只允许读取两位小数，禁止把客票号吞入金额。安全边界版本包含在 parser cache version 中，旧 cache 自动失效并在正常精确解析时重建；不得在普通发布时触发全历史重放。 |
| ETC OA attachment upload response | `HttpEtcOAClient` | 外部 upload adapter 在返回 ETC service 前把同源或 OA 内部 absolute `/fileManager/` / `/profile/` 地址归一为根相对路径；已有根相对路径与 opaque file id 保持不变，未知 absolute host/path fail closed。业务 service、页面和 Nginx 不得各自实现 URL 修补 |
| OA source alias | canonical OA row 的 `row_id`、`normalized_payload` 显式身份字段，以及该 OA 通过 FK 拥有的 `app.oa_application_items` / `app.oa_attachments` 来源付款项身份；`app.oa_source_aliases`。已审阅历史身份只能由一次性 fail-closed 迁移核对 owned attachment 与 indexed `app.oa_attachment_invoice_cache_sources` 的 exact key bridge | Mongo 文档 ID、OA/流程请求 ID、来源付款项 parent ID 与 canonical row id 必须由同一纯函数生成确定性 alias map；同一 alias 指向多个 canonical row 时 fail closed。cache bridge 只用于已知案例的迁移时证据校验，禁止加入页面热查询，也不得按金额、文件名、申请人、项目或顺序猜测。`app.oa_source_aliases` 仍只允许 `active` alias 参与 runtime canonicalization |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| OA projection rows | canonical repositories | 带 source version；完成态 workflow status 由 OA projection边界统一归一/识别，必须兼容 canonical `completed` 和历史完成态别名（如 `已完成`、`approved`、`2`），下游 read model 不得各自实现完成态判断。按 row id 水合已完成 OA 时，既有单条查询必须同时输出该 canonical OA 的权威 `source_aliases`，供 Workbench full/detail 与 summary 使用同一历史身份合同，禁止另发逐行查询。日常报销每个 schedule item 必须生成稳定 `expense_item_id=父OA: item:row_index:fingerprint`，保留原 OA source/row index，并分别保真保存来源 `purposeType -> expense_type`、`feeContent -> fee_content` 与 `detailCostStatement -> fee_description`；子付款项费用类型缺失时保持为空，repository 不得用父 OA 费用类型回填。既有 `expense_content` 继续按 `fee_content / fee_description / parent notes` 首个非空值兼容成本统计等现有消费者。附件证据的 `source_expense_item_id` 必须显式绑定到该项；不得用金额或项目名推断。repository 以业务列与规范 JSON 的 `IS DISTINCT FROM` 判定真实变化；相同 snapshot 不更新 `app.oa_applications.updated_at`，不重写 item/attachment。snapshot output 保留 change summaries 供审计/诊断，但 repository 和 sync service 均不据此 enqueue 任何页面 refresh。 |
| OA authoritative snapshot deletion | canonical OA repository -> Workbench relation command / OA payment worker | 完整 `all` 权威 snapshot 是 stale OA 的唯一源删除 owner；source adapter 对两个已配置财务 OA 表单读取 lifecycle identity，即使其中一个被 App projection filter 隐藏，也在 lifecycle arbitration 后、local retention 前输出其 Mongo document flow ID。只有该集合确认真实消失时才删除支付状态。删除必须保留 typed row identity，并在同一事务清理其 active relation、PG payment snapshot，按 exact flow IDs 登记外部状态删除事件。worker 执行 MySQL delete 前按候选 raw document 的业务编号重读同组流程并复用 lifecycle arbitration，再合并 completed + admitted canonical flow；只有候选本身仍是 current canonical OA 时才跳过，被新流程取代的历史 document 必须继续删除。month sync 与 retention prune 不具备源删除证明。Workbench formal relation 写事务必须再次锁定并验证 OA canonical row 仍存在，使事务外读取的 matching plan 不能在删除后重新创建关系；禁止用页面刷新、后台补偿或 cache 作为一致性边界。 |
| OA sync status/run facts | AppHealth/AppStatus/operations dashboard | `app.oa_sync_runs(sync_type='oa_projection')` 是每次 Mongo/projection run 的事实源；成功、失败都必须落 run，失败不得提交部分 projection/snapshot。`job.outbox_events` 和 worker heartbeat 表示 refreshing/error，不得使用进程内内存状态或行级 `app.oa_applications.synced_at` 覆盖运行事实 |
| in-progress attachment handling | OA pending admission / explicit attachment refresh | 普通 month/all `oa.sync` 对唯一的 `in_progress + expense_claim` 复用 completed 日常报销的同一附件下载、证据解析、发票识别、OCR、parser cache 与正式发票 promotion 边界；Settings 精确刷新复用该链并只强制重解析指定 row。读取/搜索只消费已生成的 cache，不得在 HTTP 进程自建解析链。进行中结果必须先提交到 pending OA/子付款项 owner，再按明确 `source_expense_item_id` 关联或受设置控制地创建 canonical 发票并触发 matching reconciliation；精确提交必须在与全量快照相同的 tenant 锁内证明同 ID、同月份的 pending owner 恰好一条，否则失败并禁止把已失去全量准入资格的 OA 复活。普通同步只对 admission 事实真实变化的 scope 执行 promotion，支付状态单独变化不得重复扫描附件。流程变为 completed 后，由同一正常同步/精确刷新链原子迁移 owner并继续复用唯一 promotion 边界。`in_progress + payment_request` 不获得附件解析能力。相同 canonical OA ID 同时出现 completed 与 in-progress 时，必须在 cache/parser/OCR 前选择 completed；同一胜出状态仍有多份来源时 fail closed，不按时间、内容或金额猜测。PDF 必须逐页保留全部正式发票；只对文本未形成正式 identity 的页面执行 OCR。OCR 依赖初始化或推理失败必须中止本次任务且不得保存 current cache，禁止伪装成 `no_evidence`。 |
| OA identity payload | frontend session | canonical username + 信息性 roles/permissions，不泄露 secret；normalized APP page set 来自独立 ACL evaluator |
| Dedicated role assignments | OA `sys_user_role` | 只替换 `finops_app_user` 与 `finops_admin` members；menu/role/binding、业务 role/member 与其他 menu 零写 |
| ACL preflight/post-deploy evidence | root-owned release artifact | identity/page-access/topology counts、hashes、fingerprints 与 restore 结果；不含 raw IDs、业务 role key、token、密码、DSN 或非受保护用户名 |
| Attachment invoice result | invoice/ETC/input usage modules | 经 service 边界传递 |
| Eligible OA attachment invoice promotion | canonical invoice repository / Workbench | parser cache 与 `app.oa_attachments` 无论谁先落库，都必须调用同一个 `oa_attachment_identity_bridge` 集合式 repository 边界：cache 写入按单个 cache key 修复，completed OA projection 只在真实变化记录的附件落库后按 OA row ids 修复；OA row scope 必须先收敛为受影响 cache keys，再仅对这些 keys 做全局 current-owner 唯一性判断和 stale derived bridge 清理，无关 key/row 不得被改写。bridge 要求 current attachment 的 item 存在于同一 `app.oa_application_items`，并以 parser 输出的每个 attachment occurrence 分组证明唯一 current attachment owner；一个 occurrence 即使候选都在同一 OA，只要对应多个 current attachment/item owner 也必须 fail closed。相同物理附件在同一 canonical OA 的多个 item occurrence 具有各自稳定 occurrence key 时仍合法并全部保留。重复执行零 bridge rewrite，禁止页面或周期任务全表扫描。桥接完成后，普通 `oa.sync` 只对本轮 completed projection 或 in-progress expense admission 真实变化 scope 内的 records 调用统一 promotion service；相同 snapshot 与仅支付状态变化必须零调用。设置页精确 `refresh-attachments` 由 OA worker 强制重解析指定 records：completed 与 `in_progress + expense_claim` 在各自 owner 提交后交给同一个 promotion service，并显式 `ensure_matching=true`。API 不持有 Mongo/OCR/promoter，也不维护第二套识别或写入规则。正式发票导入确认还必须只按本批强身份集合式反查当前 parser/schema 的 `attachment_identity_invoice` bridge，并在读取时再次验证 current `app.oa_applications + app.oa_attachments + app.oa_application_items`；raw `invoice/evidence/artifact` source 仅是 occurrence 输入，不能直接授权 promotion。该路径让 OA 先到、Excel 后到也能在同一导入事务补齐来源；不得下载/OCR、逐票查询、全库扫描或消费 stale / 未识别 cache。显式 `digital_invoice_no` 与 20 位纯数字 `invoice_no` 必须归一为同一强身份并一次批量加载 canonical 发票，依据 Settings mode link/create，保留每条 `derived_from_oa_id + source_expense_item_id + source_attachment_key` 来源边。结构化 expense item 是当前 owner 事实；外层 item id/row index 必须覆盖附件解析 payload 中残留的历史 owner 字段，同时保留其它 parser 字段。既有导入 provenance、OA 来源和显式明细归属必须合并保留；同一发票在同一 canonical OA 的不同非空 expense item 不再视为冲突，所有来源边都必须保留。只有 `app.oa_source_aliases.status='active'` 才能把 OA 系统的 ongoing/completed 生命周期重复归一为同一 canonical OA；历史 `derived_from_oa_id` 无论保存父 OA ID 还是 `父OA ID:item:...`，进入 alias 查询和冲突判断前都必须先归一为父 OA ID。未激活 alias 或不同 canonical OA 仍 fail closed，因为它可能代表重复报销。promotion 每批只做一次 alias 集合查询，禁止逐候选查询。重复同步/刷新/导入确认零重复来源写。promotion 异常使所属 event 失败重试，不得只报解析或导入成功。 |
| ETC OA form attachment value | OA form draft | 同一规范化引用同时写入 `response.data` 与 `response.extra.filePath`；历史错误 absolute 引用只能由受控 dry-run/backup/CAS repair 操作修改，不重新提交 OA、不改金额、流程或附件成员 |
| OA source alias canonicalization | formal matching、Workbench relation alignment、object identity audit / downstream duplicate classifier | 附件来源引用先去掉 `:item:` 子项后缀，再以父 OA 自身显式 alias 归一到 canonical OA row id；原始 `source_expense_item_id` 保留在发票 canonical fact。页面只在同一正式 relation 内按显式 alias + 唯一 `source_expense_row_index` 映射 canonical item id；冲突或缺失保持父 OA 级证据 |
| OA manual import mutation result | settings/workbench frontend | `refresh-attachments` POST 返回 `202 + event_id + row_ids + affected_scope_keys`；同资源的 event GET 只暴露受控的 durable `pending/processing/done/failed/dead_lettered` 状态。只有 `done` 才返回解析计数、`promotion_summary`、逐 row error 和 affected scope hints；前端随后必须以 exact row ID、原 form type、`statuses=completed,in_progress` 唯一回读，0/多条均 fail closed，不得以旧 projection 或宽搜索 fallback 伪造成功。`manual-imports` create/remove 仍只遵守 completed-only 正式导入合同并返回业务结果与 affected scope hints。freshness targets 和 operation barrier targets 为空，当前/后续页面通过正常 GET 收敛。 |

## 持久化与投影

- Own read model：无单一页面 read model；影响 `oa_pending_payment`、`input_invoice_usage`、`invoice_lifecycle` 等。
- OA manual import/create/remove 逻辑上影响 `workbench`、`workbench_relation`、invoice lifecycle、tax offset 和 cost statistics，但普通写路径不 enqueue、不等待 operation barrier；消费页面访问时按 owner contract 读取。唯一例外是管理员显式 `refresh-attachments`：Settings request service 只校验 canonical OA row、登记现有 `oa.sync` 精确 operation 并提供状态读取。OA worker 对 selected completed OA 与 selected `in_progress + expense_claim` 强制重解析、owner 提交、统一 promotion 和 matching reconciliation。该操作不广播其它页面，其状态由 event status 和通用队列指标单独观测，不参与全量 `oa_projection` freshness、App Health OA 状态或发布 readiness。
- OA projection sync 由 runtime worker 一次读取 dual-view source batch、条件写 `app.oa_*` projection；batch 额外输出 lifecycle arbitration 后、local retention 前的完整 payment flow identity 集合，只供 `all` lifecycle deletion 比较，不扩大页面 canonical retention。真实变化记录写完 item/attachment 后，在同一事务按 OA row ids 执行一次 indexed identity bridge，再由 Worker 主链路对 `completed_projection_changed_scopes` 内的 completed records 和 `pending_admission_changed_scopes` 内的 `in_progress + expense_claim` records 提升已解析正式附件发票到 canonical invoice pool，随后记录 `app.oa_sync_runs` / `app.oa_sync_watermarks`。cache 保存入口按 cache key 复用同一 bridge，因此 OA facts/cache 任一到达顺序都闭环。设置页精确刷新也由同一 worker-owned source adapter/persistence 边界完成，但只 upsert 指定记录且不执行 stale snapshot deletion；两条入口复用同一强身份、冲突、模式和批量持久化合同，不允许 route/Application 私有 Mongo、OCR 或 promotion。自动同步只在 OA owner 或 canonical 发票真实变化时写发票来源并触发 matching；支付状态单独变化和周期性相同输入必须零重复 projection/invoice/source write。管理员精确刷新 eligible record 即使 canonical 发票不变也显式补发 matching reconciliation；`all` 替换必须全范围清理 stale canonical projection，并把旧 watermark scopes 纳入变化比较，不能漏掉整月或最后一条 completed 被删除的月份。
- `OA_PROJECTION_SYNC_VERSION=2026-08-18-workflow-number-v9` 触发一次存量重投，继续确保支付申请 `category -> expense_type`、历史日常报销 `purposeType -> expense_type`、item/source binding 与 `fee_content` / `fee_description` 符合当前合同，并把 adapter 权威 `detail_fields.OA单号` 写入 `app.oa_applications.workflow_no`；重投仍由 durable `oa.sync` worker 执行且必须幂等，不允许直接修补 PostgreSQL normalized payload。
- External system：OA Mongo / OA app。
- Repository：`postgres_repositories/oa_projection.py`、`postgres_repositories/oa_attachment_identity_bridge.py`、`postgres_repositories/oa_attachment_invoice.py`、`oa_applicant_credentials.py`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Auth/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts`；runtime 只接受真实 OA token，不提供 synthetic dev/test identity |
| Menu projection | `backend/src/fin_ops_platform/services/oa_role_sync_service.py`、`backend/src/fin_ops_platform/tools/settings_access_control_preflight.py` |
| Deployment verification / repair | `backend/src/fin_ops_platform/tools/settings_access_control_preflight.py`、`backend/src/fin_ops_platform/postgres/migrations/0153_oa_source_alias_attachment_identity_repair.sql`、`deploy/oa/bin/finops-deploy-control.sh` |
| Adapter/projection | `mongo_oa_adapter.py`、`oa_projection_sync.py`、`oa_attachment_invoice_promotion_service.py`、`postgres_repositories/oa_projection.py`、`postgres_repositories/oa_attachment_identity_bridge.py`、`postgres_repositories/oa_attachment_invoice.py`、`runtime_worker_registry.py` |
| OA services | `oa_identity_service.py`、`oa_manual_import_service.py`、`oa_attachment_refresh_request_service.py`、`oa_attachment_invoice_service.py`、`oa_attachment_invoice_promotion_service.py`、`oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py` |
| Related routes | `routes_oa_pending_payments.py`、`routes_etc.py`、`routes_input_invoice_usage_oa_reverse.py`、`server.py` |
| Related modules | OA pending payments、ETC、input invoice usage、settings、permissions |
| Tests | `tests/test_oa_*.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_session_api.py` |

## 依赖方向

- 允许依赖：external adapter、credential repository、Settings normalized ACL snapshot。
- 必须通过：OA adapter/service boundary。
- 禁止绕过：业务页面直接查 OA Mongo；service 直接读取 HTTP cookie/header；OA role/permission/menu 反向成为 APP authority；runtime broad cleanup。

## 测试与验证

- `tests/test_mongo_oa_adapter.py`
- `tests/test_oa_projection_sync_service.py`
- `tests/test_oa_attachment_invoice_service.py`
- `tests/test_oa_attachment_invoice_promotion_service.py`
- `tests/test_oa_attachment_invoice_promotion_tool.py`
- `tests/test_oa_pending_payment_postgres_integration.py`
- `tests/test_rehydrate_workbench_read_models.py`
- `tests/test_oa_manual_import_api.py`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_target_oa_applicant_token_provider.py`
- `tests/test_oa_role_sync_service.py`
- `tests/test_settings_access_control_preflight.py`
- `tests/test_deploy_oa_script.py`

## 当前缺口和删除条件

- OA token/credential 变更必须同步 permissions/security docs。
- sync service 的多次 list/month 扫描、adapter fingerprint polling、queue/search/matching collaborators 与 downstream fan-out 已删除；架构 guard 禁止恢复第二套 Mongo 扫描、部分结果 fallback 或混合变化集合 fan-out。
- ACL role sync 输入只允许 settings canonical snapshot；输出仅为 OA `finops_app_user`、`finops_admin` assignments。它不写 PostgreSQL、不解析 HTTP、不决定页面权限。
- disabled/missing/selector/menu/role/binding drift 和 connect/read/write timeout 必须在 runtime mutation 前失败。稳态 deployment 不提供 menu/role/binding cleanup；禁止恢复删除业务 role/member、其他 menu/binding 或任何宽目标的旧路径。
- protected admin 固定为 `YNSYLP005`；generic settings、semantic no-op 和失败的输入校验不得触发 OA executor。

## Canonical facts ownership

- Owned facts: `app.oa_applications`、`app.oa_application_items`、`app.oa_attachments`、`app.oa_sync_runs`、`app.oa_sync_watermarks`、`app.oa_attachment_invoice_cache*`、`app.oa_source_aliases`、`app.manual_oa_imports`、`app.oa_applicant_credentials`。
- Allowed writes: OA sync worker、manual OA import service、OA credential service、受控 attachment repair/alias tools。
- Allowed reads: OA projection adapters/read ports、OA integration APIs。
- Downstream outputs: canonical/source versions 与信息性 changed scopes；各消费页自己的 access-time freshness gateway 决定是否创建精确 dirty scope。
- Forbidden paths: production API 不得直接读 OA Mongo；HTTP 进程不得启动 OA polling、热重建 Workbench read model 或 fallback inline sync；OA cache 不得当作正式发票池；OA source alias 不得由弱业务指纹自动激活；OA credential 不得通过 settings snapshot fallback 写入。
- Old code deletion: direct Mongo runtime adapter fallback、OA snapshot fallback、进程内 `OASyncService` polling/hot rebuild、HTTP `Application` 附件发票 promotion、无调用方 fingerprint polling、sync service 多 list 扫描、snapshot repository queue dependency 和 sync downstream fan-out 必须保持删除；migration/audit/rollback 工具保留不算 closure。

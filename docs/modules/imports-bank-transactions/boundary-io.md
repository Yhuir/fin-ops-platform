# 银行流水导入模块边界与 I/O

日期：2026-08-28

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：银行流水导入通过 import file/service/job queue 进入预览、确认和后台处理；确认只提交 canonical facts、source version、审计与必要领域任务，不写页面 read model，也不扇出页面 refresh job。
- 当前缺口：App 已核对文件内可提取的行数与借贷 control total；银行渠道导出范围是否完整、上传前字节真实性和未提供的控制字段仍须独立来源证据，不能由 App 文件登记 hash 推导。
- 旧代码删除状态：生产与前端只保留 `/imports/files/*` file/session I/O。旧 `/imports/preview`、`/imports/confirm` JSON route/handler/entrypoint、六套按银行精确表头识别/parser 分支、无生产者的 `general_import.confirm` worker 类型、processor、preview-only orchestration dependencies 和无 session 范围的 preview 全量 snapshot writer已删除；`FileImportService.snapshot/from_snapshot` 只保留为跨进程恢复 I/O，不作为增量写入接口。

## 职责边界

### 负责

- 管理已完成银行流水导入的撤回：只删除该 batch 的 `created` 且仍由该 batch 独占拥有的银行流水；保留 import batch/file/row provenance 并标记 `withdrawn`。
- 账户选择冲突必须在 confirm 前后端双重阻断；识别结果只用于校验，不能让误选 mapping 覆盖文件中的真实完整账号。

- 银行流水文件上传、模板识别、预览、确认导入、导入任务状态。
- 银行流水手工录入的表单归一与预览：只接受设置中存在的账户 mapping，校验完整本方账号尾号、秒级时间和 canonical 必填字段，再进入同一 file/session 导入链。手工输入不接收或生成银行流水标识；使用正式 identity service 的弱指纹执行保守判重。
- 导入完成后返回精确 affected scopes；direct-canonical 下游页面下次请求在同一只读 snapshot 直接看到新 facts，只有保留的 `workbench_relation` read-model consumer 使用自己的 freshness gateway，关联台页面不使用。
- 记录导入预览审计。
- 以服务端 session/file/batch/job 事实恢复当前用户待确认预览；用户显式放弃时，只允许在同一事务内将未确认 preview session/file/batch 终结为 `reverted`。
- 以 SHA-256 阻断同批或历史已确认的同内容文件；文件名变化不绕过文件级防重。
- 银行有官方参考号时默认使用 `bank-v3`：账户、官方参考号种类/值和业务字段指纹摘要共同形成强 identity。若既有 `bank-v3` 键冲突，但双方非空余额或币种明确证明是不同账单位置，只为该冲突事实生成确定性的 `bank-v4` statement-position 键；重放同一位置必须命中同一 `bank-v4`，不得穿透数据库 `source_unique_key` 唯一约束。若历史 canonical 行尚无 `bank-v4` 键，仅当账户、秒级交易时间、方向、金额、账后余额、币种六项全部存在且只命中一条时，才作为 legacy statement-position duplicate；多条命中进入 `suspected_duplicate`，缺字段不自动合并。历史 `bank-v2` 只在业务指纹一致、双方官方参考号存在唯一交集时迁移判重；缺失或多义证据进入 `suspected_duplicate`。没有官方参考号时业务字段指纹仍只产生人工复核。
- `preview_stale` 不只比较汇总计数。confirm 前必须逐行比较 decision、linked object type 和 linked object id；即使总重复数/可导入数未变，只要任一行换了 canonical owner 也必须拒绝旧预览。错误只报告变化字段及数量，不输出业务值或内部 ID。
- 一个银行文件的 preview/confirm 必须先对当前 canonical 事实做有界批量 identity preload：一次读取 canonical/fingerprint 候选，一次读取完整 statement-position 候选，再在内存中逐行决定并把本批新建事实写入同一批缓存；不得逐行查询数据库，同文件重复项也不得穿透 confirm。
- 普通 confirm 不得把 `suspected_duplicate` 解释为用户授权新建。弱指纹命中必须保持未写入并使 batch 收敛为 `completed_with_errors`；preview 可暂存候选 canonical 引用用于复核，但 terminal row 的 `linked_object_type/id`（包括 normalized payload）必须清空。只有 `created`、`status_updated`、`duplicate_skipped` 可以保留正式 canonical 引用。
- 在有界资源内验证 XLS/XLSX 签名与容器结构；文件声明的行数/借贷合计与解析结果不一致时禁止确认。
- 通过统一 page Audit 在同一只读 snapshot 证明 file object、session/file、batch/row、canonical bank transaction、当前 import job/outbox 的集合、字段、引用与 queue 状态。
- 受控重放必须为新 session/file 生成新的归档对象登记；不得让新 `app.import_files` 复用旧 `stored_file_path` 却缺少 `file_object_id`。历史已存在的缺失链接只能由维护工具按唯一 storage URI、登记 SHA-256、对象大小和非 tombstone 生命周期证明后修复。
- 受控重放的 `duplicate_skipped` 行可以保留原上传文件的 source key/fingerprint，同时引用旧 canonical 流水；page Audit 仅在登记 reason 属于三类受控重放、去重恢复工具写入的唯一 owner-reclassification reason，或普通确认的 canonical duplicate reason，且账户、秒级交易时间、方向、金额、账后余额完整相等时接受该引用。币种有值时必须相等；历史 canonical 币种为空时，仅接受 row 同为空，或银行解析器按既有合同补出的 `CNY`。owner-reclassification 与普通确认 reason 只属于历史 page Audit provenance，不进入受控重放 reason map；普通确认仍由正常 importer 决定，不获得重放覆盖能力。row 缺失但 canonical 有值、非 `CNY` 的单边缺失或显式值不同仍必须阻断。普通导入、前五项缺字段/漂移仍必须阻断。
- 退休版本的普通确认 reason 仅允许证明“row 有 source key、canonical 缺 source key”的历史迁移形态：row/canonical 数据指纹必须非空且相等，该指纹在 canonical 流水池中必须只有一个 owner，同时账户、秒级交易时间、方向、金额和标准化对方名仍须相等。该 reason 不进入受控重放 provenance 集合或运行时 reason map；指纹多 owner、任一基础字段漂移或相反的 key 缺失形态继续阻断。
- 历史正式 file/session audit 计数只允许从 durable `app.import_batch_rows` 重算；维护工具必须 dry-run 冻结精确 file-object link 数、payload update 数、row relink 数、terminal `suspected_duplicate` row unlink 数和 source fingerprint，execute 在 serializable transaction + advisory lock 下逐行 CAS，记录 operation audit。row unlink 只允许正式、终态、`source_record_type=bank_transaction` 且当前仍错误引用 `bank_transaction` 的行，并且只清空 typed link 与 normalized payload link；数量、行主键、batch/row、decision/reason、source key、fingerprint、旧 link 与原 payload 任一漂移必须整批拒绝。历史普通确认错误引用优先要求数据指纹、账户、秒级交易时间、方向、金额、余额、币种与标准化对方名全部一致；若历史 parser 造成 fingerprint 漂移，只允许以上严格 statement-position 与对方名在全库唯一命中时作为二级证据。零命中、多命中或任一严格字段缺失必须整批拒绝。不得扫描并改写其它 import 类型，也不得伪造缺失对象。
- Audit 比较交易时间时必须比较同一时间点：银行文件中无时区的 `trade_time` 按 `Asia/Shanghai` 解释，PostgreSQL `timestamptz` 与带时区 ISO 值统一归一到 UTC 后比较；禁止把同一时刻的本地时间与 UTC 表示误报为漂移，也禁止忽略真实的时间差异。
- `duplicate_skipped` 的受控重放 statement-position 审计失败时，admin-only issue 必须返回 decision/reason 登记状态、无业务原值的完整性标志和字段级 `mismatch_fields`，以区分未登记 reason、缺失位置与账户、时间、方向、金额、余额、币种漂移；不得只返回派生 source key 让生产门禁依赖推断。
- 导入确认结果或完成后的 job result 必须透出 write result envelope；普通导入的 `freshness_targets` 与 `operation_barrier_targets` 固定为空，不要求当前写操作等待任意页面重建。

### 不负责

- 不直接维护银行明细页面投影。
- 不负责 no-OA、turnover 或 workbench 业务状态机。
- 不绕过 import job queue 执行长任务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportBankTransactionsPage.tsx` | 文件只进入 import API/service |
| 文件预览确认 | `ImportWorkflowPage.tsx`、`features/imports/api.ts` | 银行流水文件只能调用 `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/sessions/*`；`preview_ready` 只证明解析完成，前端仅提交 `audit.confirmable_count > 0` 且账户无冲突的文件；全量已存在时不调用 confirm、不创建 job |
| 手工流水预览 | `POST /imports/bank-transactions/manual/preview` | body 为 `{transactions:[...]}`，1–50 笔。每笔必须绑定现有 `bank_mapping_id`，填写与 mapping 尾号一致的完整本方账号、收支、正金额、余额、秒级交易时间、三位币种和对方户名；不接收银行流水标识。服务端一次批量预载 canonical identities，再为每笔生成独立 preview file。既有弱指纹命中为 `suspected_duplicate`，同批弱指纹重复在 session 创建前拒绝；只返回 `created` 文件的 `file_ids`。 |
| 预览恢复/放弃 | `GET /imports/files/sessions?mode=bank_transaction`、`POST /imports/files/discard` | 只返回当前认证用户的可恢复会话。放弃必须校验 owner，对已确认文件或 pending/processing/succeeded job fail closed，重复放弃幂等。 |
| 复核明细分页 | `GET /imports/files/sessions/{session_id}/review-rows?kind=duplicate|unimported&offset&limit` | `limit` 最大 100；返回当前 session 的稳定切片和 `total/has_more`。session 摘要不携带无界 `row_results`、`normalized_rows` 或 `duplicate_groups`，页面不得从摘要恢复全量复核列表。 |
| 不完整表头字段映射 | `ImportWorkflowPage.tsx`、`features/imports/api.ts` | 后端返回 `header_signature`、`mapping_candidates`、`mapping_fields`、`field_mapping`；页面只向 `/imports/files/retry` 提交当前文件的 canonical 字段到源列映射，不提交已解析交易事实。 |
| 页面手动刷新 | `ImportWorkflowPage.tsx` | 重新读取银行映射配置；有持久化 preview session 时同时精确重读该 session，保留当前草稿和文件选择，不执行浏览器 reload 或跨页面 refresh。 |
| Job event | runtime worker handlers | 后台处理必须可恢复；相同 import idempotency key 只接受相同 request fingerprint。瞬时失败归还 pending 并由 durable outbox 重试，达到最大次数才终态失败；用户再次确认同一请求时，terminal failed/partial job 必须原子复用原 job id 并重新 queued/pending，禁止新建冲突 job；活跃 processing lease 不得被并发 worker 接管。 |

preview/confirm/retry 都属于 canonical 导入写链，必须在 multipart/JSON 解析前通过共享 mutation guard；`imported_by` 与 background job owner 只取已认证 session username，客户端 form/body 同名字段不具有身份语义。

preview 首次登记 `app.import_files` 时必须同时写入认证 username 到 `uploaded_by` 与 `raw_payload.normalized_payload.imported_by`，最终 session delta 必须保持同值；恢复、列出和放弃只使用该服务端 owner 事实。session/file/batch/canonical candidate ID 使用带业务前缀的 UUID，不使用进程内顺序号或“先查询再递增”的多 worker 竞态分配。

Import worker 注册 handler 时只固定 processor 类型，不得把启动时的 `FileImportService` / canonical import snapshot 长期缓存到后续 job。每次 `import.process.requested` 执行前必须从 PostgreSQL durable facts 重新构造 processor，使 worker 启动后新创建的 session/file 以及最新 canonical 去重事实可见。

生产 API 的 session GET、confirm、retry 与 background retry 在进入 file/session service 前同样必须从 `load_imports_snapshot` + `load_file_imports_snapshot` 显式恢复当前 PostgreSQL import runtime；该恢复只属于导入操作边界，不得重新启用 `state:imports`、`state:file_imports` 或 full-state bootstrap fallback。

file/session preview/retry 只允许输出当前 `session_id`、files 与其 `preview_batch_id` 的精确 delta，且不得包含 canonical invoice/transaction facts。confirm 的持久化输出必须是本次所选 session、正式 batch 及其新建/状态更新 canonical facts 的精确 delta。合法重复行只引用既有 transaction，不重新拥有或回写该 transaction；两条链都不得回写其它 session 或未受影响 facts。调用方必须通过 `ApplicationStateStoreProtocol.save_import_delta(...)` 写入；PostgreSQL 在同一事务写 batch 与 file/session，本地实现按 batch/entity/session id 合并且计数器只增不减，二者共享“未出现在 delta 中的事实保持不变”语义。

confirm 的 I/O 顺序必须是 `save_import_delta` 原子提交在先，必要的 Workbench auto-matching 领域任务 enqueue 在后。batch 与 file/session 任一写入失败必须整体回滚且不得发布领域任务；普通 confirm 禁止发布 tax/read-model refresh，禁止让 worker 在 canonical facts 可见之前消费 scope，也禁止后台状态写入与 confirm 形成丢失更新窗口。

批次明细持久化必须复用 PostgreSQL connection 的 bounded `execute_many_values` chunk，不得按行建立数据库
round-trip；`ON CONFLICT` 的 legacy batch owner 条件和 affected-row 数必须保持 fail closed。缺少 batch capability
的 transaction 必须 fail fast，不得回退为逐行 SQL；同一事务继续承担 owner guard 与整体回滚。

通用 `Application._persist_state()` 已从 import canonical/session 写链隔离，不得再包含 `imports`、`file_imports` 或调用其全量 snapshot。preview/retry 只通过 `_persist_import_preview_delta(session_id)` 写当前 session-scoped delta，confirm 只通过上述 selected-files delta 边界持久化正式事实；OA 附件发票晋升和 ETC metadata 关联分别使用 `save_invoices` 与 `save_invoice_etc_metadata` 窄端口。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| `POST /api/imports/bank-transaction-batches/{batch_id}/withdraw` | 系统状态导入历史抽屉 | admin + mutate；同事务清理普通 Workbench active relation、分类/候选/本行 override，再删除 batch 独占创建的流水；OA、发票、导入历史和 append-only 审计保留。已核销、updated import 或其它 active business owner 返回 `409`。重复撤回幂等返回 `idempotent_replay=true`。 |
| `withdrawn` lifecycle | 导入历史与重复文件判断 | batch/file 保留并显示“已撤回”；已撤回 file 不再作为 confirmed duplicate owner，因此允许用正确银行重导原文件。 |

`bank_transaction_relation_claims` 已由迁移 `0136` 收敛为只读历史证明。撤回链路不得更新或删除该旧表，也不得为此恢复生产写权限；当前 Workbench relation 的解除只走 `WorkbenchRelationCommandService`。

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览结果 | 前端导入页面 | 不持久化为业务事实直到确认；无法安全归一的银行表头返回显式字段映射合同，不生成 preview rows。复核表按服务端分页读取银行专属字段，不一次性映射全部结果。 |
| 手工录入预览结果 | 前端录入抽屉 | 返回不含银行流水标识的规范化 `values`、逐笔 file/row decision 与可确认 `file_ids`；用户返回修改或关闭抽屉时走既有 discard 终结 preview，确认继续调用 `/imports/files/confirm` 并进入 durable job。 |
| 来源控制证据 | 前端导入页面 | `source_control.status` 只允许 `verified/mismatch/unavailable/not_applicable`；mismatch 文件不可确认。 |
| 错误明细 | `/imports/batches/{batch_id}/errors.csv` | 仅输出用户可读字段，不输出内部对象 ID。 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入 job status | background job/app status | 可查询、可失败恢复 |
| 导入生命周期 | AppHealth / 导入页 | 统一输出 `awaiting_confirmation/queued/processing/succeeded/failed/discarded/inconsistent`；页面不得直接展示 batch 原始 `pending/completed` 并猜测含义。 |
| Affected scope | 页面 freshness gateway / 必要领域任务 | 返回本次写入影响的精确月份；不在写路径展开成页面 refresh jobs |
| Write result envelope | 前端导入页面/job result | 返回 `affected_scope_keys`，普通写的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空。前端立即结束写操作；后续访问页面由该页 freshness/status/enqueue 边界收敛 |
| Page Audit | `/api/operations/app-health/page-audit?page=imports.bank-transactions` | admin-only、只读、`read_model_keys=[]`、`relation_proof_required=false`；expected-set 同时包含本次正式 batch 拥有的 transaction 与 duplicate row 引用的历史 canonical transaction，反向 owner 唯一性只约束本批次拥有的 transaction；受控历史重放允许 row/canonical 币种同时缺失，也允许解析器默认 `row=CNY` 对历史 `canonical=空`，但账户、秒级时间、方向、金额、余额仍必须完整相等，反向缺失、非 CNY 单边缺失或显式值不同继续失败；下游 read model 只登记为 impact targets，不冒充页面 consumer |

失败但仍可重试的 import job 必须在 admin-only Audit issue 中返回 `attempt_count/max_attempts`、`last_error`、`session_id` 和 `selected_file_ids`，使运维只能通过正式 file/session retry/confirm I/O 定位和恢复；恢复必须复用同一 import/background job id，重置失败租约与错误并写入新的 durable outbox，且 request fingerprint 不同返回结构化 `409 idempotency_conflict`。不得要求直接查询或改写 `job.import_jobs`。

worker 更新导入 background job 的 running/progress/terminal 状态时，只允许按 canonical `job_id` 单行读写；不得把全量历史 background job snapshot 回写到 PostgreSQL。历史 raw payload 内的旧 `job_id` 不能覆盖正式表主键，否则下游成本统计、Workbench 等副作用的旧任务会污染本次导入事务。

若已部署旧版本在 background job 全量回写阶段把同一 `file_import.confirm` 事件推进到 dead letter，且 session/file 仍完整停留在 `preview_ready`、对应 preview batch 为 `pending`、正式银行流水写入为零，只允许通过候选 release 的 `import-audit-repair` 精确恢复模式处理。只读 discovery 可从一个明确 import job id 推导唯一 outbox/background job/session/file 白名单，但存在多个 dead letter 或任何坐标缺失时必须拒绝；执行时仍必须显式提供完整 target，并先取得同一 repeatable-read snapshot 的 fingerprint。候选 processor 只有在上述事实全部一一匹配时才复用原 import/background job id 执行。正式 batch/file/job 全部成功后才允许把该条 dead letter 标记完成；任一业务事实不闭环时保留 dead letter，不得假完成或扫描其它失败任务。

已确认文件的生产恢复只能走 `import-audit-repair --repair-bank-source` 受控模式。dry-run 必须显式绑定全部 source session/file、恢复 cohort 数、保护 cohort 数、精确重复删除数、预期重放新增数、预期受控跳过数和预期释放的错误 canonical reference 数，并验证原文件 SHA-256、精确 batch owner、业务指纹与官方参考号唯一匹配、零核销和零 canonical relation。释放数不得超过本次 source files 实际拥有的 canonical reference evidence。唯一例外是显式 `--cleanup-related-bank-duplicates` 恢复合同：只允许精确数量的 duplicate-owned `单标签 + 单事件`，以及精确一条由指定 duplicate transaction id 拥有的 `银行流水 + 进项发票` active Workbench relation；不得包含 OA、确认、核销、批次、claim、override、exception 或其它关系。dry-run 必须冻结 category/event 全部 CAS 字段、relation case/version/preview、发票成员，并证明撤回不会恢复旧关系。execute 使用相同 fingerprint、serializable transaction 和 advisory lock，先通过正式 Workbench command/repository 撤回关系并追加 history，再删除精确 category/event，最后才处理导入审计：每个待删副本必须恰好有一条 `created` owner，可同时有零到多条已存在的 `duplicate_skipped` 引用；全部引用都重定向到原正确流水，只有 `created` owner 转换计入正式 batch 的 success→duplicate 计数，原 `duplicate_skipped` 的 decision/reason 保持不变。`import_files.raw_payload` 是原始预览证据，不是最终 row audit；工具只冻结其 SHA-256，不得用最终决策覆盖。完成正式 row/batch 审计重定向后才删除错误副本；全部事实写在同一事务内，任何一步漂移整体回滚。随后复用正式 preview/confirm processor 重放归档文件。重放的权威行证据必须来自 dry-run 已冻结的 `app.import_batch_rows`，并按 source file、row_no、record type、data fingerprint 和 canonical ID 传入 processor；禁止从 `import_files.raw_payload` 的旧预览 decision 推断最终 owner。证据分为三类：已修复的重复引用绑定保护 cohort keeper；仍保留在恢复 cohort 中的原始 `created` owner 绑定当前 canonical 流水；既有 `duplicate_skipped` 行绑定修复后仍保留的 canonical 流水。只有当前预览仍匹配同一证据的行才能受控转为 `duplicate_skipped`，三类证据必须分别精确计数且不得行号重叠，历史判重引用不得指向本次待删除事实；普通疑似行、不同 fingerprint、缺失 owner、不同原因或计数漂移全部拒绝。canonical reference 证据还必须在回放时按冻结 ID 重读 canonical 流水并比较账户、秒级交易时间、方向、金额、余额、币种；六项任一不一致时不得强绑旧 ID，而是释放该行并保留普通 importer 的当前 decision。目标缺失则 fail closed。真正缺失的行不在其余受控证据中，仍必须由正式 importer 判定为 `created`。首轮和幂等重放都必须精确命中授权释放数；受控重放创建新的审计 session/file，原已确认会话不可修改；重复重放必须得到零新增并保持相同受控跳过与释放计数。确认前 stale gate 不得关闭；持久化后的受控行仍须带已登记的受控 reason。普通去重重算为 `duplicate_skipped` 或 `suspected_duplicate` 时，只有指向完全相同的 canonical transaction ID 才允许维持权威重复分类；若因历史 parser/identity 漂移重算为 `created`，则必须在确认瞬间按冻结 canonical ID 重新读取事实，并证明账户、秒级交易时间、方向、金额、余额、币种六项全部存在且完全相同，才允许维持重复分类。canonical ID 缺失、六项任一缺失/变化、类型变化或其它 decision 仍必须报 `preview_stale`。read model 月份 scope 必须规范为 `YYYY-MM`。任何歧义、额外关系、hash、计数、preview/version 或 owner 漂移均在删除前失败。

恢复工具的“同一事务”包含清理、首轮正式 preview/confirm processor 重放、幂等重放、审计和 read-model refresh outbox；它们必须通过保留 `PostgresTransaction` JSON 参数适配契约的 connection-shaped 适配器复用同一 serializable advisory-lock 写事务，内部 repository 不得另开并提交独立事务。任一计数、证据、幂等或 scope 门禁失败时整体回滚为零业务写入。旧的“清理事务提交后再由根连接自主重放”分裂路径必须保持删除。

上述恢复合同的二级证据例外仅用于历史 parser 导致 fingerprint/reference 漂移的行：候选与保护事实必须在同一授权 cohort 内按账户、秒级交易时间、方向、金额、余额、币种全部相同且双方唯一地一一对应。任一字段缺失、多义、数量不一或关系超出已授权集合时仍在写入前拒绝。

## 持久化与投影

- Own read model：无独立 manifest entry。
- 逻辑影响消费者：bank detail/account balance、`workbench`、`workbench_relation`、invoice lifecycle、pending invoice、OA pending payment、cost statistics；这些影响不等于写后立即入队，各 owner 在访问时读取已提交 facts。
- Worker：import job/runtime worker handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportBankTransactionsPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx`、`ManualBankTransactionBatchEditor.tsx`、`ManualBankTransactionEntryDrawer.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `manual_bank_transaction_entry_service.py`、`import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py`、`import_lifecycle_service.py` |
| Lifecycle persistence | `services/postgres_repositories/import_lifecycle.py`；只读聚合既有 import facts，放弃只在单事务内终结未确认 preview，不写 canonical transaction。 |
| Persistence | `services/postgres_repositories/core.py` 保存正式导入事实；`services/postgres_repositories/bank_import_dedup_repair.py` 只服务显式生产恢复计划；不新增模板事实表。 |
| Audit owner | `services/postgres_repositories/bank_transaction_import_page_audit.py`、`services/postgres_repositories/import_audit_repair.py`、`services/page_audit_registry.py` |
| Controlled repair | `services/import_audit_repair_service.py`、`services/bank_import_dedup_repair_service.py` 与 `services/bank_import_audit_contract_repair_service.py` 输出纯 plan；`services/postgres_repositories/bank_import_audit_contract_repair.py` 只执行精确 CAS；`tools/import_audit_repair_ops.py` 仅编排 dry-run/execute I/O |
| Worker/runtime | `runtime_worker_handlers.py`、`app_status_job_registry.py` |
| Tests | `tests/test_manual_bank_transaction_entry_service.py`、`tests/test_import*.py`、`web/src/test/ManualBankTransactionBatchEditor.test.tsx`、`web/src/test/ImportsApi.test.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |

## 依赖方向

- 允许依赖：import job queue、background job service、明确的 Workbench auto-matching 领域任务端口。
- 必须通过：`ImportWorkflowPage` file/session API、`FileImportService`、`ImportProcessingService`、import job queue。
- 禁止绕过：银行流水页面回到 `/imports/preview` / `/imports/confirm` JSON 入口；导入确认时直接写 read model；长任务直接跑在 HTTP request 中；`server.py` 重新持有 import confirm processor 业务逻辑。

## 测试与验证

- `tests/test_import_api.py`
- `tests/test_import_job_queue.py`
- `tests/test_import_processing_service.py`
- `tests/test_audit_bank_transaction_import_page.py`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_no_longer_owns_import_confirm_processors`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_no_longer_exposes_legacy_json_import_write_routes`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_transaction_import_frontend_uses_file_session_api_only`
- `web/src/test/BackgroundJobProgress.test.tsx`
- `web/src/test/ImportsApi.test.ts`
- `tests/test_import_lifecycle_service.py`
- `web/src/test/ImportCenterPage.test.tsx`
- `web/e2e/imports-bank-transactions-flow.spec.ts`

## 当前缺口和删除条件

- 模板识别变更必须覆盖预览、确认、失败恢复，以及导入后首次访问受影响页面时的 downstream freshness。
- 银行表头只有在 canonical 核心字段完整时才能解析；未知字段不得用字符串相似度、列位置或模型猜测自动写入。相同标准化表头签名可复用最近一次成功人工映射；签名变化必须重新确认。
- 六套银行专用 exact-header parser 已删除，禁止以兼容名、隐藏 fallback 或并行模板注册重新引入；银行差异只能作为有证据的字段别名或明确的金额符号规则进入单一解析器。
- 旧 JSON import API 及其 `general_import.confirm` worker 链已删除；测试造数只能调用保留的 service-level normalization ports，HTTP 行为必须走 file/session API。
- 删除任何 file/session snapshot 持久化前，必须先提供 import worker 跨进程恢复替代方案；不能把 `FileImportService.snapshot/from_snapshot` 误判为旧 full snapshot fallback。
- Audit pass 只证明已登记 App 内部事实闭包；外部银行 control evidence 与下游受影响页面各自的 Audit 仍是独立 gate。
- `app.import_batch_rows.legacy_mongo_id` 必须是 `batch_row:<batch_id>:<row_no>`；repository upsert 只能更新同一 `legacy_batch_id` 的行。任何跨 batch 冲突必须回滚整个事务，禁止恢复 process-global row counter 或 `ON CONFLICT` 重挂 owner 的旧逻辑。
- 历史严格合同银行批次的 row evidence 只能由已登记 import file payload 与 canonical transaction owner 共同恢复；受控工具必须先做 repeatable-read dry-run、输出 fingerprint/rollback manifest，再在 serializable advisory-lock 事务内执行。

## Canonical facts ownership

- Owned facts: `app.bank_transactions` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的银行流水导入事实。
- Allowed writes: bank transaction import preview/confirm/job、import processing service、受控去重/正式化 repository。
- Allowed reads: bank transaction repository/query ports、bank detail/import API。
- Downstream outputs: bank detail/account balance、workbench、turnover ledger、no-OA batch 可比较的 canonical source-version 变化；保留 read model 的访问 gateway 创建精确 dirty scope，其他页面直接查询 canonical facts。
- Forbidden paths: 银行流水页面不得调用旧 JSON `/imports/preview`、`/imports/confirm`；production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或前端 payload 直接补写银行流水。
- Old code deletion: 已删除旧 JSON HTTP route/handler/entrypoint、`general_import.confirm` job producer/processor 及只为该链服务的 preview scope dependencies；snapshot 银行流水 fallback、直接跨模块写银行事实路径必须保持删除。migration/audit/rollback 工具和 file/session worker restore 端口保留不算 closure。
- Import file batch binding: migration 0097 已删除 `app.import_files.import_batch_id`；批次撤回必须按 `raw_payload.normalized_payload.batch_id/preview_batch_id` 定位文件，不得恢复旧列依赖。

## Audit v19 provenance 版本边界（2026-07-12）

- migration 0101 为新 `app.import_files` 设置 `audit_contract_revision=import-page-audit.v1` 默认值，但不回填历史行。
- 当前 revision 的新导入必须严格证明 file object/hash/session/batch/row/canonical transaction 全链路与双向 expected-set；任何缺失均阻断 Audit。
- revision 为 NULL 的 pre-contract 历史只输出 `legacy_provenance_unproven` warning；不得补造文件对象、hash 或 session。历史 canonical 银行流水仍由银行明细及下游页面 Audit 证明。

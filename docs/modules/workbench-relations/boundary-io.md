# Workbench 正式关系边界与 I/O

日期：2026-08-20

## Owner

| 事实 | Owner | 说明 |
| --- | --- | --- |
| `app.workbench_pair_relations` | workbench-relations | 当前/历史关系实体；只有 active 拥有成员 |
| `app.workbench_pair_relation_history` | workbench-relations | confirm/extend/replace/cancel/withdraw/repair 审计历史 |
| `read_model.workbench_relation_*` | read-models + workbench-relations projection | 下游 linked/unlinked 投影，不是写事实源 |

Release A 已移除旧 `read_model.workbench_candidate_matches`、`read_model.workbench_reconciliation_decisions` 和 `state:workbench_candidate_matches` 的全部运行时依赖，但暂不删除其物理存储，以保留应用回滚能力。只有 Release A 的运行时零访问、数据哈希、freshness、queue 和 Audit 证据全部通过后，Release B 才可创建只做 forward-drop 的旧状态 migration，并使用届时下一个可用版本；不得复用已被 OA 使用的 0104。任何生产调用方都不得重新依赖这些旧状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| manual command | Workbench/业务 owner API | normalize 后至少 2 个不同 requested canonical row ids、actor、tenant、idempotency、expected versions、既有 `note`；每个 exact requested id 都必须重读为 `oa|bank|invoice`，成员可同栏或跨栏，金额/方向和材料完整性不作为人工创建门槛。`amount_check.requires_note=true` 时 `note` 必填并写 relation/history；浏览器为一次 preview/confirm 或 withdraw 意图生成稳定 key，并在 ambiguous 网络重试中复用，缺失时 API fail closed。重复 identity、canonical 缺失/未知类型、active overlap/version drift 和非法 summary 仍 fail closed。银行分类不是 command router：mixed 或全 `internal_transfer` 银行成员仍生成 `manual_confirmed` command，不得转交 no-OA batch owner。 |
| OA manual invoice supplement | `WorkbenchInvoiceSupplementService` | 输入为完整 manual import session、全部 file ids、精确 OA row、expense item、可选 active case、actor/request id。在同一 PostgreSQL 事务确认整批 canonical invoices、写 import facts/source links，再复用正式 relation command 创建或扩展目标 `manual_confirmed` case；目标 case 存在时必须包含该 OA。任一步失败同时恢复 import 与 relation 进程镜像，禁止半批发票或半关系。 |
| in-progress OA bank link | OA pending payment command | canonical OA/bank ids、workflow snapshot、actor、scope；只允许创建新 formal case 或扩展唯一 active case并保留其发票成员，多个 owner/冲突 fail closed |
| formal auto plan | matching orchestrator | immutable `FormalRelationPlan`：case/member set/fingerprint/rule/evidence/amount/scope/batch hash；涉及银行成员时，fact repository 对计划银行 IDs 一次批量读取 Bank Details owner 的 canonical effective-category projection，再冻结 requirement metadata；OA 显式 source reference 必须先经父 OA 自身字段及其 FK-owned 付款明细/附件的 alias map 归一为 canonical typed identity，计划携带由 `attachment_source` 直接证明的 exact `(parent OA row id, invoice row id)` binding |
| current snapshot | relation repository | active + relevant historical facts，必须在 UoW transaction 中加载 |
| active case validation | relation repository | 只按 canonical case id 读取一条 active relation，不加载 history；只供进入事务前的 scope/owner 校验，真正 mutation 仍在事务内加锁并加载相关 history |
| active member overlap validation | relation repository | confirm 按目标 row ids/case ids 一次读取 active relations，不读取 cancelled relation 或 history；不得用通用 current+history snapshot 代替 |
| withdraw command | owner API | paired/unpaired active case identity、完整 member set、preview id、expected versions、reason；preview 与 submit 都要求请求的 canonical member set 和该 case 当前完整 active member set 精确相等，子集、超集、跨 case 混选统一返回 `workbench_relation_exact_selection_required`。只允许关系级撤回；submit 按 canonical history 恢复上一可证明的稳定拓扑，不能从 row metadata/display group 猜测 predecessor。 |
| confirm/withdraw preview rows | Workbench direct canonical selection owner | preview 只把 untrusted scope 与完整 typed row ids 交给 relation-preview selection port；业务层不设置成员数量上限，也不截断。repository 只返回 selected rows 与正式关系描述符已经证明的同组 context，不再按 OA `source_links` 扫描或隐式扩展附件成员；HTTP request body、statement timeout 等平台资源边界仍保留。正式 relation command、repository adapter 和 UoW 不接收页面 DTO，并在事务内重读 canonical facts、active relation/version 与 idempotency。 |
| read request | downstream facade | scope keys、row ids、`require_fresh`、source version contract |
| page scope proof request | Workbench / 银行明细页面 query boundary | `source_versions_for_scopes(scope_keys)` 通过 `workbench_relation_scope_summaries(...)` 一次读取全部 concrete month scope 的 published proof/current-effective dirty status，再用一次 bulk canonical expected-version I/O 比较；只 enqueue mismatch/missing 的 exact scopes。`all` 先一次枚举 canonical object、active relation 与已有 projection 月份，再执行相同批量 proof，禁止逐月 N+1 或持久化伪 `all` scope |
| OA canonical snapshot changed | OA integration transactional writer | 只提交 OA canonical snapshot/source version。关系页或消费页下一次请求直接读取 canonical facts 与 active relation，不产生页面任务。 |
| persisted bank category changed | Bank Details / Turnover category closure | effective category 实际变化后，在分类事务内按 changed bank member 锁定 active 普通 relation，复用当前 canonical classifier 与同一 settings policy snapshot 重冻结 requirement metadata 并追加 history。ETC/批量账务关系排除；无变化或无 active relation 时零 relation 写。 |
| historical category source proof | requirement repair tool runtime port | 只读 PostgreSQL canonical category fact，同时返回 UUID/legacy transaction identity alias；仅用于证明 persisted confirmation 并修复旧 requirement snapshot，不作为在线分类或页面事实源。 |
| requirement recalculation event | settings-maintenance worker | 规则保存事务产生的 job id、owner、目标版本和真实变化 tag codes；只读取 tag proof 命中的 active 正式 relation，并以完整 tag set 和当前规则重算。repository 在同一集合查询中按关系成员批量返回 canonical 银行流水月份，旧关系主记录缺少 `month_scope` 时也不得猜测或降级为 `all`。`candidate:` / `decision:` / `temp:` 历史候选标识不属于正式关系写事实，必须由集合查询排除并交给 matching/read model 按当前规则重建。上线收敛重试可携带一个失败旧 job id，只有替代任务完成关系写入和精确 refresh enqueue 后才把旧任务标记 superseded。 |
| canonical relation members | requirement repair tool runtime port | 按 relation 原始 typed member ids 一次批量读取 canonical OA/流水/发票行；用于重算金额和证明成员未漂移，缺行/错类型立即失败。 |
| repair refresh output | durable runtime queue | 仅 enqueue 受影响月份的 `workbench_relation` scope，并把相同月份标记 matching dirty；关联台下一次 direct GET 自然读取提交结果，禁止 page Workbench event 与 `all` fan-out。 |
| completed ETC OA marker | `app.oa_applications.normalized_payload.etc_batch_id` + submitted `app.etc_business_batches` | 仅允许精确相等且 OA/batch owner 各自唯一；写入前在关系 UoW 内锁定 external batch identity 并重验 OA 状态、批次状态、数量、金额和 active relation owner。禁止金额、名称、OCR 或模糊匹配。 |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| active relation | Workbench/downstream | deduped aligned `row_ids`/`row_types`，一个 row 只属于一个 active case |
| persisted completion requirement | reconciliation-workbench | 普通 relation 必须同时含银行流水才可能进入 `paired`；OA+发票的 active immutable ownership 在缺银行时保持同 case但进入 `unpaired`，并返回 `missing_row_types=["bank"]`。含银行流水的普通 relation 创建时写 `requires_oa`、`requires_invoice`、tag codes 和规则版本；关联台据此判定其余缺项，缺失 fail closed。材料满足后，关系内全部 OA 仍须 `workflow_status=completed`；任一进行中 OA 返回 `blocking_reasons=["oa_in_progress"]` 并保持原 case 在 `unpaired`。只有显式 `relation_mode=batch_accounting` 保留已登记完成豁免；ETC batch identity 只证明汇总行的 canonical owner，不绕过 requirements 或实际成员类型。持久化分类事实变化继续原子更新既有关系；规则语义变化由 durable incremental job 更新命中关系并追加 history。下游 linked ownership 仍只由 active status 决定。 |
| history | Audit/withdraw/operation-history | before/after、actor、event、timestamp、reason、rule/provenance；人工确认附带服务端 request id 与选择项 before/after 业务投影，供操作历史详情读取，不改变 relation 事实 |
| command result | caller | relation/version/affected rows/months/idempotent replay；relation topology 的 status 或 typed member set 每次发生变化时 version 单调推进，新关系从 1 开始，取消在当前 version 上 +1，恢复 predecessor 使用 `max(数据库当前 predecessor version, history snapshot version)+1`。普通关系操作的 `freshness_targets` / `operation_barrier_targets` 为空，月份/scope 只作读侧重校验提示。 |
| ETC relation enrichment | Workbench direct query/Audit | 人工确认折叠 ETC summary 时，relation UoW 在同一事务重读 canonical selected rows，并把唯一 `external_etc_batch_id` 写入 `special_metadata`；自动补全继续由 `special_metadata.etc_batch_link` 保存 external/business/submission/OA identity、发票数量与金额。一个 external batch 只能有一个 active relation owner，Audit 只认可 batch identity 与确定性 `etc-summary-<batch>` row id 同时匹配。 |
| access-time refresh request | durable runtime | 普通 confirm/withdraw/split/exception/ignore/cash/relation 写入不 enqueue 任何页面 read model。消费页的正常 GET 比较 canonical relation source version 与已发布证明，只对当前访问 scope 通过正式 gateway 入队 |
| read distribution | downstream pages | 只有 `linked` / `unlinked`；non-fresh 不能返回为业务空集合 |

## 合法 relation modes

Mode 只描述业务 owner/provenance，不形成第三种页面状态。当前 registry 包括普通确认、exception closed、OA exempt、个人暂借还清、OA/附件冲抵、pending invoice、bank-flow batch、no-OA、turnover、batch accounting、ETC、input invoice OA reverse 等已登记 mode。新增 mode 必须进入 registry、状态转换测试、下游刷新矩阵和模块文档。

`manual_confirmed` 与 no-OA mode 的选择由入口/业务 owner 决定，不由成员银行分类决定。独立 no-OA batch 可以继续使用其已登记 mode；关联台人工 `confirm-link` 即使包含部分或全部 `internal_transfer` 银行成员，也只能产生 `manual_confirmed` command。

`automatic_decision`、`automatic_match`、`existing_case` 不是可新增的正式写入 mode。系统自动关系使用登记的正式 mode并以 actor/rule metadata 记录系统来源。

## 事务与一致性

- command service 必须接收明确 repository/idempotency/freshness 依赖，不接收整个 `Application`。
- relation、history、idempotency 与 audit 的业务事务必须原子；失败不得留下半关系。普通关系写入不承担下游 dirty/outbox 事务，页面访问通过 canonical version drift 发现并收敛。
- OA 手工补录是唯一受限的 import+relation 组合 UoW：只编排既有 import normalization/persistence 和正式 relation command，不直接 SQL 写 relation/history，不创建第二发票池、专用 worker、read model、fallback 或异步补偿。
- PostgreSQL 生产运行时固定使用 durable idempotency repository；旧 feature flag 和生产内存幂等路径已删除，本地非 PostgreSQL 测试只使用显式内存适配器。
- 分类关系闭环只能通过 category writer + relation command/repository 的同一事务完成；提交后只发布 changed-case 进程镜像增量。禁止恢复写后 callback、页面通知、第二条 metadata writer 或事务外补偿。
- repository adapter 持久化 scoped snapshot 后，只能通过 domain service 的 changed-case delta I/O 更新进程内镜像；禁止读取并重建全局 relation/history snapshot，也禁止 adapter 直接写 domain service 私有状态。
- 单 case active relation 读取必须走显式窄 I/O；禁止 adapter fallback 先复制全局 snapshot 再筛 case，禁止为只读校验加载该 case 全部 history。
- 在线 command 持久化必须走显式 changed-case delta I/O：relation upsert/delete 与本次新 history event 在同一事务写入，history 只能 append/idempotent upsert，不得先删除再重写该 case 的完整历史。全量 relation/history replacement 只用于 migration、restore 或 repair，不得重新进入 confirm/cancel/withdraw 热链。
- confirm/withdraw preview 的 direct canonical selection 不是 relation fact source。preview route 可以用它构造 selection groups、金额与 OA alias；submit 必须丢弃该 DTO，并保留服务端 actor/tenant、preview identity、expected relation versions、canonical repository 与 UoW 原子写合同。
- case id 重用、active member overlap、row type 对齐、expected version 和 idempotency fingerprint 必须在写入边界校验。withdraw preview fingerprint 必须覆盖 `operation_type`、current active relation 的 case/version/status/排序后 typed members、全部 after relations 的同结构 topology，以及选中的 confirm history identity（operation id/type/created at）；任一 topology/history 漂移都拒绝旧 preview。
- Workbench 人工确认只要求 normalize 后至少 2 个不同 requested canonical row ids，并逐个精确解析为已支持类型；不得再用“至少两个 pane”“必须含银行”“材料完整”或金额相等作为通用 confirm gate。金额/方向检查继续输出既有 `amount_check.requires_note`，只有其为 `true` 时才要求 `note`；关系创建后由 reconciliation-workbench 完整性合同决定 `paired|unpaired`。该人工规则不进入 `FormalRelationPlan`，也不放宽任何自动匹配条件。
- 人工 confirm/withdraw 的单个正式关系成员数没有业务上限；preview、submit、canonical revalidation、relation/history 持久化和 response 都必须保留完整 typed member set。性能通过集合式数组 I/O、固定 SQL 形状和一次关系级 mutation 控制，不能用静默截断、分页提交或拆成多条关系换取速度。
- Workbench 人工确认不按 persisted/derived bank category 分流。mixed 或全 `internal_transfer` 银行选择必须复用同一 canonical revalidation、command 与 UoW；禁止在 facade 调用独立 no-OA batch submit callback，或返回 no-OA batch 专属 conflict/response。
- paired/unpaired active relation 的关系级 withdraw 使用相同 preview/submit、exact full active member set、case lock、expected versions、topology fingerprint、idempotency 和 history 边界。恢复候选必须来自 current case 最近一次 confirm history 的 canonical `before_relations`。submit 在同一 UoW 内先锁 current active case/members，再按稳定顺序锁 predecessor case/members；随后按 current+restored scope 重载事实并重算 target topology，恢复前重验 canonical member 存在与类型、restored case 未被复用且每个成员只有唯一 active owner。缺 canonical 返回 `workbench_relation_canonical_member_missing`，case/owner 冲突返回 `workbench_relation_restore_conflict`。任一证明失败整笔回滚，不得恢复部分关系或隐藏 fallback。
- OA source snapshot 发现某 OA 已不在 completed 或 admitted 集合时，通过 `remove_rows_from_active_relations` 从 relation 中移除该成员；剩余至少两个成员且无 immutable attachment parent binding 时保留同 case并追加 history，否则取消 relation。该清理不得直接 SQL、不得创建新 case。
- 任意 `N:M:K` member set 都合法，只要上游业务规则已证明安全并且成员非空、唯一、typed。
- 自动扩展既有 active case 必须使用 `target_case_id` 并原子 replace；显式引用保持既有扩展口径。组合证据只允许补全缺少至少一个 pane 的 active relation，候选搜索只接纳该关系当前缺失 pane 的新事实，避免同一强证据下其它已存在 pane 的未配对事实扩大或污染搜索空间；缺失 pane 内仍允许有界一对多/多对一/多对多精确合计。扩展后所有已出现 pane 必须按分合计完全相等、currency/direction 一致、证据图连通、候选唯一且不占用其他 active case；三栏已完整的 active relation 不再自动追加成员。不得创建重叠的第二条 active relation。
- 精确 typed member set 的人工撤回历史阻止 deterministic engine 自动重建同一关系。
- OA 附件 binding 写入 `special_metadata.oa_attachment_bindings`；纯 OA+附件关系不可撤回，混合关系撤回或扩展时必须恢复 exact binding。canonical invoice row id 不要求 `oa-att-inv-*` 前缀，旧前缀识别只作为历史兼容，不得替代显式 binding metadata。
- 历史普通关系的人工撤回 fingerprint 继续阻止同一成员集合被自动重建；仅成员类型严格为 OA+invoice 且全部连边均为显式 `attachment_source` 的不可拆分归属关系不受旧撤回 fingerprint 污染。
- matching 事实 repository 先把 `CNY`、`RMB`、`人民币`、`人民币元`、`元` 统一为 `CNY`，未知币种保持原值并继续隔离；随后按 currency、direction 与强 evidence 建索引，只生成跨 pane 的候选边。同类型事实比较既不生成边，也不得消耗搜索状态预算。公司对方户名、税号、业务号、项目号和发票号仍只在 365 天窗口内比较跨类型事实；日常报销额外把 OA 申请人与银行对方户名归一为 `employee_reimbursement_payee` 强证据，该专用证据允许至少 2 个有效字符、使用 OA 完成/审批日期（缺失才回退申请日期）与银行交易日期，并严格限制在 30 个自然日内。通用 `counterparty` 至少 4 字的保护不放宽，员工证据不依赖银行标签。active case 缺一个 pane 时，先按缺失类型、币种、方向和任一既有 pane 合计查找唯一同额单笔，再校验强证据与日期窗口；唯一命中直接补全，重复同额或跨 case 争用 fail closed。只有单笔路径未命中时才进入原有组合搜索，组合扩展继续按 case 使用独立有界预算；全局建图或单个高密度 case 资源受限不得丢弃已证明安全的单笔计划，也不得阻断同批其它独立 case。禁止恢复对全部 canonical facts 的 O(n²) 两两扫描或整批共享 active-extension 状态预算。
- requirement recalculation 必须先由 repository 集合查询排除 `candidate:` / `decision:` / `temp:` 非正式标识，并从 relation member 对应 canonical 银行流水 `txn_month` 得到一个或多个精确月份，再完整预验证本 job 命中的全部 active 正式 relation；任一正式关系缺 case、canonical 银行月份、持久化 tag proof 或当前 tag rule 时整批零写并失败。关系 payload 的历史 `month_scope` 不得替代 canonical 月份证明。写入保留 case id、成员和金额事实，只替换 requirement metadata（包括目标规则版本），追加 `bank_relation_requirement_recalculated` history。重放同一 job 必须零新增写；只刷新实际写入关系的精确 `workbench_relation` 月份并标记相同 matching dirty scopes，禁止 page Workbench event 与 `all` fan-out。替代失败 rollout 时，旧任务必须在新任务成功后才 supersede；新任务失败时两条失败证据都保留为 attention。
- 同轮 deterministic relation 创建/扩展必须在首次保存前合并 ETC metadata；已有 active relation 的补全必须是一次 changed-case save。canonical revalidation 冲突时整批回滚，不允许部分写。
- manual confirm 必须在 relation UoW 写入前，通过既有 bank-tag read facade 的一次批量 fresh I/O 冻结 requirement metadata。deterministic matching 由 fact repository 对计划银行 IDs 一次读取当前 settings 和有界 canonical SQL 分类投影；任一 bank row 缺失时整批不写。两条路径都不得逐行读取标签、使用旧 category snapshot 或在 orchestrator 内自行分类。

## Read facade

- `require_fresh=True` 时，missing/stale/source mismatch 必须返回非 fresh 并受控 enqueue，调用方不得把空 rows 当作无关系。
- 下游只有 active relation 是 linked 证据。历史关系、显示 tags、候选搜索结果、matching evidence 都不是支付/关联/成本证据。
- downstream read models 必须记录并比较 relation source versions，relation mutation 后旧 payload 不得继续 fresh。当前访问只能 enqueue 本页面所需的精确 scope；未访问/隐藏页面不得由 relation 写路径提前 fan-out。
- 共享 relation projection 的 exact-scope canonical proof 必须包含 eligible active relation 数量与稳定 typed membership digest，不能只使用 `max(updated_at)`。relation-only delta 在覆盖旧 group 前必须通过 repository 一次批量解析银行流水/发票 canonical UUID 与 legacy ID aliases；任一 alias overlap 都属于同一 logical member。无法证明完整 alias/affected scope 时 fail closed 为 full rebuild，不得发布局部结果为 fresh。
- 银行明细、待找发票、进项/销项等实际消费 relation distribution 的页面，继续把共享 relation projection 作为各自访问时依赖并精确收敛。关联台自身不消费 `workbench_relation`：它在一次 read-only snapshot 中直接读取 canonical facts 与 active relation，因此 combined initial 不得为 relation distribution 阻塞、入队或输出 dependency status。该隔离禁止把 consumer projection 重新接回 relation command/UoW 或关联台页面热路径。
- 批量账务页面不消费本 read facade/projection。它通过页面专属 PostgreSQL query repository 在同一 repeatable-read snapshot 直读 canonical facts 与 active `relation_mode=batch_accounting` 关系；成员唯一事实源是对齐的 `row_ids + row_types`。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Domain/command | `workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_modes.py` |
| UoW/repository | `workbench_uow.py`、`workbench_relation_command_repository_adapter.py`、`workbench_invoice_supplement_service.py`、`postgres_repositories/workbench_relation.py`、`bank_relation_requirement_recalculation.py` |
| Read/projection | `workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Auto formalization | `workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`、`workbench_etc_batch_link.py`、`postgres_repositories/workbench_formal_relation.py` |
| Tests | `tests/test_workbench_relation_*.py`、`test_workbench_formal_relation_repository.py`、`test_workbench_matching_orchestrator.py` |

## 禁止路径与删除条件

- 禁止 route/service/worker 直接 SQL 写 relation/history。
- 禁止 `Application` snapshot、`app_settings state:*`、Redis、RabbitMQ、read model 或前端 event 成为 relation 事实源。
- 禁止 candidate/decision service/store/table/API、隐藏 fallback 或双写重新进入调用图。
- 禁止恢复旧人工 confirm gate（至少两个 pane、必须有银行、金额相等或材料完整）和未配对“撤回候选”路径；禁止把 relation-level stable-topology restore 降级为 row `case_id`/display metadata 拼组。
- 禁止恢复人工 `confirm-link` 的 internal-transfer 特判与 no-OA batch 分流；旧 `submit_internal_transfer_rows_from_workbench` 注入以及 `_bank_only_internal_transfer_confirm_status` / `_confirm_internal_transfer_rows_via_no_oa_batch` helper 必须从 facade 组装和调用图删除。独立 no-OA batch 的专属入口、service 和登记 mode 不在删除范围。
- 禁止历史 `app.oa_pending_payment_bank_relations`、`app.bank_transaction_relation_claims`、promotion service 或 pending claim 排除重新成为运行时 relation owner；migration `0136` 后它们只读审计。
- 旧 generic `MatchingEngineService` 仅可服务其独立 legacy reconciliation/内部转账备注上下文；它的 result 不得决定 Workbench membership、zone、linked status 或正式关系写入。该隔离由 boundary guards 和 grouping tests 保护。
- migration/repair 工具必须 dry-run、精确 scope、审计和 rollback manifest，且只能调用正式 command/repository adapter。失效 canonical OA 成员修复复用固定 `workbench-requirement-repair` 控制入口；dry-run 为每个 case 输出独立 fingerprint，execute 以该 fingerprint 唯一定位并重验单 case，再通过 `WorkbenchRelationCommandService.remove_rows_from_active_relations(...)` 删除成员并复用正式持久化边界。禁止直接 SQL 改 relation/read model；若仍有至少两个无附件父级冲突的成员则保留关系，否则取消关系。
- 银行导入撤回同样只能调用 `remove_rows_from_active_relations(...)`；保留关系时记录 `remove_withdrawn_bank_import_fact`，不足两个成员时记录 `cancel_relation_for_withdrawn_bank_import_fact`。关系、流水删除、claim release、batch lifecycle 与 audit 位于同一数据库事务，禁止 App Health 页面直接 SQL 改 relation。
- 旧的人工 `--reapply-case-id` / `--expected-rule-version` 运维白名单路径已删除，不得恢复。规则要求迁移只能由设置事务产生的 durable job 驱动，并按变化 tag proof 集合式定位；历史 repair 工具继续只处理缺失/损坏 proof，不承担正常规则传播。
- 银行导入 duplicate 恢复只能对 dry-run 冻结的唯一 `bank + invoice` active case 调用 `prepare_withdraw_relation` / `withdraw_relation`；必须逐项校验 case、version、preview id、expected versions、成员和发票事实，且 `after_relations=[]`。relation 表/history 不得直接 SQL 删除或改写，撤回审计历史必须保留。
- 已删除 `ExistingEtcBatchLinkService`、`HistoricalEtcBusinessBatchMigrationService` 及其 CLI；禁止恢复这两条 operator-only 平行写链。历史数据补全由同一 matching worker + formal relation UoW 收敛。

# Workbench 正式关系边界与 I/O

日期：2026-08-05

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
| manual command | Workbench/业务 owner API | canonical typed row ids、actor、tenant、idempotency、expected versions、note |
| formal auto plan | matching orchestrator | immutable `FormalRelationPlan`：case/member set/fingerprint/rule/evidence/amount/scope/batch hash；OA 显式 source reference 必须先经父 OA 自身字段及其 FK-owned 付款明细/附件的 alias map 归一为 canonical typed identity，计划携带由 `attachment_source` 直接证明的 exact `(parent OA row id, invoice row id)` binding |
| current snapshot | relation repository | active + relevant historical facts，必须在 UoW transaction 中加载 |
| active case validation | relation repository | 只按 canonical case id 读取一条 active relation，不加载 history；只供进入事务前的 scope/owner 校验，真正 mutation 仍在事务内加锁并加载相关 history |
| active member overlap validation | relation repository | confirm 按目标 row ids/case ids 一次读取 active relations，不读取 cancelled relation 或 history；不得用通用 current+history snapshot 代替 |
| withdraw command | owner API | active case identity、preview id、expected versions、reason |
| confirm/withdraw preview rows | Workbench active generation read owner | preview 只把 untrusted scope/row ids/expected version 交给有界 relation-preview selection port；返回 selected rows、必要 attachment context 与 generation proof。正式 relation command、repository adapter 和 UoW 不接收该 DTO，并在事务内重读 canonical facts、active relation/version 与 idempotency |
| read request | downstream facade | scope keys、row ids、`require_fresh`、source version contract |
| page scope proof request | Workbench / 银行明细页面 query boundary | `source_versions_for_scopes(scope_keys)` 通过 `workbench_relation_scope_summaries(...)` 一次读取全部 concrete month scope 的 published proof/current-effective dirty status，再用一次 bulk canonical expected-version I/O 比较；只 enqueue mismatch/missing 的 exact scopes。`all` 先一次枚举 canonical object、active relation 与已有 projection 月份，再执行相同批量 proof，禁止逐月 N+1 或持久化伪 `all` scope |
| OA canonical snapshot changed | OA integration transactional writer | 只提交 OA canonical snapshot/source version，零 `workbench_relation`/`oa_pending_payment` dirty/outbox。关系页或消费页访问时按自己的 source dependency 精确收敛；OA projector 直接读 canonical relation，不等待本 read model。 |
| completed ETC OA marker | `app.oa_applications.normalized_payload.etc_batch_id` + submitted `app.etc_business_batches` | 仅允许精确相等且 OA/batch owner 各自唯一；写入前在关系 UoW 内锁定 external batch identity 并重验 OA 状态、批次状态、数量、金额和 active relation owner。禁止金额、名称、OCR 或模糊匹配。 |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| active relation | Workbench/downstream | deduped aligned `row_ids`/`row_types`，一个 row 只属于一个 active case |
| frozen completion requirement | reconciliation-workbench | 普通 relation 必须同时含银行流水才可能进入 `paired`；OA+发票的 active immutable ownership 在缺银行时保持同 case 但进入 `unpaired`，并返回 `missing_row_types=["bank"]`。含银行流水的普通 relation 创建时写 `requires_oa`、`requires_invoice`、tag codes 和规则版本；关联台据此判定其余缺项，缺失 fail closed。只有显式 `relation_mode=batch_accounting` 保留已登记完成豁免；ETC batch identity 只证明汇总行的 canonical owner，不绕过冻结要求或实际成员类型。规则保存不得追溯改写；下游 linked ownership 仍只由 active status 决定。 |
| history | Audit/withdraw | before/after、actor、event、timestamp、reason、rule/provenance |
| command result | caller | relation/version/affected rows/months/idempotent replay；普通关系操作的 `freshness_targets` / `operation_barrier_targets` 为空，月份/scope 只作读侧重校验提示 |
| ETC relation enrichment | Workbench projection/Audit | 人工确认折叠 ETC summary 时，relation UoW 在同一事务重读 canonical selected rows，并把唯一 `external_etc_batch_id` 写入 `special_metadata`；自动补全继续由 `special_metadata.etc_batch_link` 保存 external/business/submission/OA identity、发票数量与金额。一个 external batch 只能有一个 active relation owner，Audit 只认可 batch identity 与确定性 `etc-summary-<batch>` row id 同时匹配。 |
| access-time refresh request | durable runtime | 普通 confirm/withdraw/split/exception/ignore/cash/relation 写入不 enqueue 任何页面 read model。消费页的正常 GET 比较 canonical relation source version 与已发布证明，只对当前访问 scope 通过正式 gateway 入队 |
| read distribution | downstream pages | 只有 `linked` / `unlinked`；non-fresh 不能返回为业务空集合 |

## 合法 relation modes

Mode 只描述业务 owner/provenance，不形成第三种页面状态。当前 registry 包括普通确认、exception closed、OA exempt、个人暂借还清、OA/附件冲抵、pending invoice、bank-flow batch、no-OA、turnover、batch accounting、ETC、input invoice OA reverse 等已登记 mode。新增 mode 必须进入 registry、状态转换测试、下游刷新矩阵和模块文档。

`automatic_decision`、`automatic_match`、`existing_case` 不是可新增的正式写入 mode。系统自动关系使用登记的正式 mode并以 actor/rule metadata 记录系统来源。

## 事务与一致性

- command service 必须接收明确 repository/idempotency/freshness 依赖，不接收整个 `Application`。
- relation、history、idempotency 与 audit 的业务事务必须原子；失败不得留下半关系。普通关系写入不承担下游 dirty/outbox 事务，页面访问通过 canonical version drift 发现并收敛。
- repository adapter 持久化 scoped snapshot 后，只能通过 domain service 的 changed-case delta I/O 更新进程内镜像；禁止读取并重建全局 relation/history snapshot，也禁止 adapter 直接写 domain service 私有状态。
- 单 case active relation 读取必须走显式窄 I/O；禁止 adapter fallback 先复制全局 snapshot 再筛 case，禁止为只读校验加载该 case 全部 history。
- 在线 command 持久化必须走显式 changed-case delta I/O：relation upsert/delete 与本次新 history event 在同一事务写入，history 只能 append/idempotent upsert，不得先删除再重写该 case 的完整历史。全量 relation/history replacement 只用于 migration、restore 或 repair，不得重新进入 confirm/cancel/withdraw 热链。
- confirm/withdraw preview 的 derived active-generation selection 不是 relation fact source。preview route 可以用它构造 selection groups、金额与 OA alias；submit 必须丢弃该 DTO，并保留服务端 actor/tenant、preview identity、expected relation versions、canonical repository 与 UoW 原子写合同。
- case id 重用、active member overlap、row type 对齐、expected version 和 idempotency fingerprint 必须在写入边界校验。
- 任意 `N:M:K` member set 都合法，只要上游业务规则已证明安全并且成员非空、唯一、typed。
- 自动扩展既有 active case 必须使用 `target_case_id` 并原子 replace；显式引用保持既有扩展口径。组合证据只允许补全缺少至少一个 pane 的 active relation，候选搜索只接纳该关系当前缺失 pane 的新事实，避免同一强证据下其它已存在 pane 的未配对事实扩大或污染搜索空间；缺失 pane 内仍允许有界一对多/多对一/多对多精确合计。扩展后所有已出现 pane 必须按分合计完全相等、currency/direction 一致、证据图连通、候选唯一且不占用其他 active case；三栏已完整的 active relation 不再自动追加成员。不得创建重叠的第二条 active relation。
- 精确 typed member set 的人工撤回历史阻止 deterministic engine 自动重建同一关系。
- OA 附件 binding 写入 `special_metadata.oa_attachment_bindings`；纯 OA+附件关系不可撤回，混合关系撤回或扩展时必须恢复 exact binding。canonical invoice row id 不要求 `oa-att-inv-*` 前缀，旧前缀识别只作为历史兼容，不得替代显式 binding metadata。
- 历史普通关系的人工撤回 fingerprint 继续阻止同一成员集合被自动重建；仅成员类型严格为 OA+invoice 且全部连边均为显式 `attachment_source` 的不可拆分归属关系不受旧撤回 fingerprint 污染。
- matching 先按 currency、direction 与强 evidence 建索引，只生成跨 pane 的候选边；同类型事实比较既不生成边，也不得消耗搜索状态预算。公司对方户名、税号、业务号、项目号和发票号仍只在 365 天窗口内比较跨类型事实；日常报销额外把 OA 申请人与银行对方户名归一为 `employee_reimbursement_payee` 强证据，该专用证据允许至少 2 个有效字符、使用 OA 完成/审批日期（缺失才回退申请日期）与银行交易日期，并严格限制在 30 个自然日内。通用 `counterparty` 至少 4 字的保护不放宽，员工证据不依赖银行标签。active case 缺一个 pane 时，先按缺失类型、币种、方向和任一既有 pane 合计查找唯一同额单笔，再校验强证据与日期窗口；唯一命中直接补全，重复同额或跨 case 争用 fail closed。只有单笔路径未命中时才进入原有组合搜索，组合扩展继续按 case 使用独立有界预算；全局建图或单个高密度 case 资源受限不得丢弃已证明安全的单笔计划，也不得阻断同批其它独立 case。禁止恢复对全部 canonical facts 的 O(n²) 两两扫描或整批共享 active-extension 状态预算。
- 同轮 deterministic relation 创建/扩展必须在首次保存前合并 ETC metadata；已有 active relation 的补全必须是一次 changed-case save。canonical revalidation 冲突时整批回滚，不允许部分写。
- manual confirm 与 deterministic matching 必须在 relation UoW 写入前，通过 bank-tag read facade 的一次批量 fresh I/O 冻结 requirement metadata；non-fresh 或任一 bank row 缺失时整批不写。读投影不得回查 settings、不得按 row 逐条读取标签。

## Read facade

- `require_fresh=True` 时，missing/stale/source mismatch 必须返回非 fresh 并受控 enqueue，调用方不得把空 rows 当作无关系。
- 下游只有 active relation 是 linked 证据。历史关系、显示 tags、候选搜索结果、matching evidence 都不是支付/关联/成本证据。
- downstream read models 必须记录并比较 relation source versions，relation mutation 后旧 payload 不得继续 fresh。当前访问只能 enqueue 本页面所需的精确 scope；未访问/隐藏页面不得由 relation 写路径提前 fan-out。
- 共享 relation projection 的 exact-scope canonical proof 必须包含 eligible active relation 数量与稳定 typed membership digest，不能只使用 `max(updated_at)`。relation-only delta 在覆盖旧 group 前必须通过 repository 一次批量解析银行流水/发票 canonical UUID 与 legacy ID aliases；任一 alias overlap 都属于同一 logical member。无法证明完整 alias/affected scope 时 fail closed 为 full rebuild，不得发布局部结果为 fresh。
- 银行明细、待找发票、进项/销项等实际消费 relation distribution 的页面，继续把共享 relation projection 作为各自访问时依赖并精确收敛。关联台自身不消费 `workbench_relation`：它直接从 canonical relation 构建 Workbench active generation，因此 combined initial 不得为 relation distribution 阻塞、入队或输出 dependency status；关联台自己的 bulk canonical/active-generation proof 只刷新 exact Workbench 月份。该隔离禁止把 consumer projection 重新接回 relation command/UoW 或关联台页面热路径。
- 批量账务页面不消费本 read facade/projection。它通过页面专属 PostgreSQL query repository 在同一 repeatable-read snapshot 直读 canonical facts 与 active `relation_mode=batch_accounting` 关系；成员唯一事实源是对齐的 `row_ids + row_types`。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Domain/command | `workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_modes.py` |
| UoW/repository | `workbench_uow.py`、`workbench_relation_command_repository_adapter.py`、`postgres_repositories/workbench_relation.py` |
| Read/projection | `workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Auto formalization | `workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`、`workbench_etc_batch_link.py`、`postgres_repositories/workbench_formal_relation.py` |
| Tests | `tests/test_workbench_relation_*.py`、`test_workbench_formal_relation_repository.py`、`test_workbench_matching_orchestrator.py` |

## 禁止路径与删除条件

- 禁止 route/service/worker 直接 SQL 写 relation/history。
- 禁止 `Application` snapshot、`app_settings state:*`、Redis、RabbitMQ、read model 或前端 event 成为 relation 事实源。
- 禁止 candidate/decision service/store/table/API、隐藏 fallback 或双写重新进入调用图。
- 旧 generic `MatchingEngineService` 仅可服务其独立 legacy reconciliation/内部转账备注上下文；它的 result 不得决定 Workbench membership、zone、linked status 或正式关系写入。该隔离由 boundary guards 和 grouping tests 保护。
- migration/repair 工具必须 dry-run、精确 scope、审计和 rollback manifest，且只能调用正式 command/repository adapter。
- 已删除 `ExistingEtcBatchLinkService`、`HistoricalEtcBusinessBatchMigrationService` 及其 CLI；禁止恢复这两条 operator-only 平行写链。历史数据补全由同一 matching worker + formal relation UoW 收敛。

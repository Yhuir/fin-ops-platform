# Workbench 正式关系边界与 I/O

日期：2026-07-23

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
| formal auto plan | matching orchestrator | immutable `FormalRelationPlan`：case/member set/fingerprint/rule/evidence/amount/scope/batch hash |
| current snapshot | relation repository | active + relevant historical facts，必须在 UoW transaction 中加载 |
| active case validation | relation repository | 只按 canonical case id 读取一条 active relation，不加载 history；只供进入事务前的 scope/owner 校验，真正 mutation 仍在事务内加锁并加载相关 history |
| active member overlap validation | relation repository | confirm 按目标 row ids/case ids 一次读取 active relations，不读取 cancelled relation 或 history；不得用通用 current+history snapshot 代替 |
| withdraw command | owner API | active case identity、preview id、expected versions、reason |
| confirm/withdraw preview rows | reconciliation-workbench canonical query repository | preview 只把 untrusted scope/row ids 交给有界 selection port；返回最多 20 条 selected rows 和最多 100 条必要 attachment context，不返回 generation proof。正式 relation command、repository adapter 和 UoW 不接收该 DTO |
| read request | downstream facade | scope keys、row ids、`require_fresh`、source version contract |
| page scope proof request | Workbench / 银行明细页面 query boundary | `source_versions_for_scopes(scope_keys)` 通过 `workbench_relation_scope_summaries(...)` 一次读取全部 concrete month scope 的 published proof/current-effective dirty status，再用一次 bulk canonical expected-version I/O 比较；只 enqueue mismatch/missing 的 exact scopes。`all` 先一次枚举 canonical object、active relation 与已有 projection 月份，再执行相同批量 proof，禁止逐月 N+1 或持久化伪 `all` scope |
| batch-accounting read request | `BatchAccountingService` via facade/port | 候选 row ids + 明确年份；使用一个批量账务专用 bundle 返回候选 rows、referenced groups、候选/年度 bulk scope proof 和 `submitted_count`，固定查询次数并保留等价 freshness/status；年度聚合只允许命中 batch-accounting partial expression index，不得改变其他页面通用 reader 行为 |
| OA canonical snapshot changed | OA integration transactional writer | 只提交 OA canonical snapshot/source version，零 `workbench_relation`/`oa_pending_payment` dirty/outbox。关系页或消费页访问时按自己的 source dependency 精确收敛；OA projector 直接读 canonical relation，不等待本 read model。 |
| completed ETC OA marker | `app.oa_applications.normalized_payload.etc_batch_id` + submitted `app.etc_business_batches` | 仅允许精确相等且 OA/batch owner 各自唯一；写入前在关系 UoW 内锁定 external batch identity 并重验 OA 状态、批次状态、数量、金额和 active relation owner。禁止金额、名称、OCR 或模糊匹配。 |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| active relation | Workbench/downstream | deduped aligned `row_ids`/`row_types`，一个 row 只属于一个 active case |
| frozen completion requirement | reconciliation-workbench | 含银行流水的普通 relation 创建时写 `requires_oa`、`requires_invoice`、tag codes 和规则版本；关联台据此判定 paired/unpaired，缺失 fail closed。规则保存不得追溯改写；下游 linked ownership 仍只由 active status 决定。 |
| history | Audit/withdraw | before/after、actor、event、timestamp、reason、rule/provenance |
| command result | caller | relation/version/affected rows/months/idempotent replay；普通关系操作的 `freshness_targets` / `operation_barrier_targets` 为空，月份/scope 只作读侧重校验提示 |
| ETC relation enrichment | Workbench projection/Audit | `special_metadata.etc_batch_link` 保存 external/business/submission/OA identity、发票数量与金额；一个 external batch 只能有一个 active relation owner。 |
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
- confirm/withdraw preview 的 canonical query snapshot 不是 command 事实源。preview route 可以用它构造 selection groups、金额与 OA alias；submit 必须丢弃 rows DTO，只保留服务端 actor/tenant、preview identity、expected relation business versions、idempotency fingerprint，并在同一 UoW transaction 内一次有界查询重验 canonical identities/types，再由 relation repository 锁定并重验 active ownership/version。
- case id 重用、active member overlap、row type 对齐、expected version 和 idempotency fingerprint 必须在写入边界校验。
- 任意 `N:M:K` member set 都合法，只要上游业务规则已证明安全并且成员非空、唯一、typed。
- 自动扩展既有 active case 必须使用 `target_case_id` 并原子 replace；不得创建重叠的第二条 active relation。
- 精确 typed member set 的人工撤回历史阻止 deterministic engine 自动重建同一关系。
- 同轮 deterministic relation 创建/扩展必须在首次保存前合并 ETC metadata；已有 active relation 的补全必须是一次 changed-case save。canonical revalidation 冲突时整批回滚，不允许部分写。
- manual confirm 与 deterministic matching 必须在 relation UoW 写入前，通过 bank-tag read facade 的一次批量 fresh I/O 冻结 requirement metadata；non-fresh 或任一 bank row 缺失时整批不写。读投影不得回查 settings、不得按 row 逐条读取标签。

## Read facade

- `require_fresh=True` 时，missing/stale/source mismatch 必须返回非 fresh 并受控 enqueue，调用方不得把空 rows 当作无关系。
- 下游只有 active relation 是 linked 证据。历史关系、显示 tags、候选搜索结果、matching evidence 都不是支付/关联/成本证据。
- downstream read models 必须记录并比较 relation source versions，relation mutation 后旧 payload 不得继续 fresh。当前访问只能 enqueue 本页面所需的精确 scope；未访问/隐藏页面不得由 relation 写路径提前 fan-out。
- 共享 relation projection 的 exact-scope canonical proof 必须包含 eligible active relation 数量与稳定 typed membership digest，不能只使用 `max(updated_at)`。relation-only delta 在覆盖旧 group 前必须通过 repository 一次批量解析银行流水/发票 canonical UUID 与 legacy ID aliases；任一 alias overlap 都属于同一 logical member。无法证明完整 alias/affected scope 时 fail closed 为 full rebuild，不得发布局部结果为 fresh。
- 银行明细、待找发票、进项/销项等实际消费 relation distribution 的页面，继续把共享 relation projection 作为各自访问时依赖并精确收敛。关联台自身不消费 `workbench_relation` 或 Workbench active generation：页面专属 repository 在一个只读快照内直接组合 canonical facts 与 active relations，不阻塞、不入队、不输出 dependency status。该隔离禁止把 consumer projection 重新接回 relation command/UoW 或关联台页面热路径。
- 批量账务未提交列表专用 `get_batch_accounting_by_row_ids(..., submitted_year=...)` 必须在同一 bundle 中读取所有候选/年度 scopes 的 current-effective dirty status、候选 rows、referenced groups 和年度 `submitted_count`，保留原 status/reason/source-version 合同；12 个月 canonical expected proof 必须由 projection builder 的一次 bulk SQL 返回逐 scope 映射，facade 仍逐 scope 精确比较，不能恢复 12 次单月 source-version N+1、独立 count port 或通用逐 scope查询。`workbench_relation_groups_batch_accounting_year_scope_group_idx` 只覆盖 linked batch-accounting 年度聚合谓词，不改变其他 consumer 的查询或数据。已提交年度 list 继续使用自己的固定 I/O。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Domain/command | `workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_modes.py` |
| UoW/repository | `workbench_uow.py`、`workbench_relation_command_repository_adapter.py`、`postgres_repositories/workbench_relation.py` |
| Read/projection | `workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py`；关联台页面专属读取见 `postgres_repositories/workbench_canonical_query.py` |
| Auto formalization | `workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`、`workbench_etc_batch_link.py`、`postgres_repositories/workbench_formal_relation.py` |
| Tests | `tests/test_workbench_relation_*.py`、`test_workbench_formal_relation_repository.py`、`test_workbench_matching_orchestrator.py` |

## 禁止路径与删除条件

- 禁止 route/service/worker 直接 SQL 写 relation/history。
- 禁止 `Application` snapshot、`app_settings state:*`、Redis、RabbitMQ、read model 或前端 event 成为 relation 事实源。
- 禁止 candidate/decision service/store/table/API、隐藏 fallback 或双写重新进入调用图。
- 旧 generic `MatchingEngineService` 仅可服务其独立 legacy reconciliation/内部转账备注上下文；它的 result 不得决定 Workbench membership、zone、linked status 或正式关系写入。该隔离由 boundary guards 和 grouping tests 保护。
- migration/repair 工具必须 dry-run、精确 scope、审计和 rollback manifest，且只能调用正式 command/repository adapter。
- 已删除 `ExistingEtcBatchLinkService`、`HistoricalEtcBusinessBatchMigrationService` 及其 CLI；禁止恢复这两条 operator-only 平行写链。历史数据补全由同一 matching worker + formal relation UoW 收敛。

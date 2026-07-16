# Workbench 正式关系边界与 I/O

日期：2026-07-16

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
| withdraw command | owner API | active case identity、preview id、expected versions、reason |
| read request | downstream facade | scope keys、row ids、`require_fresh`、source version contract |
| OA canonical snapshot changed | OA integration transactional writer | 只允许在提交 OA canonical snapshot 的同一事务中按精确月份标记 `workbench_relation` dirty/outbox；该 target 必须先于同事务的 `oa_pending_payment` consumer target，使 OA worker 对旧 relation fail-closed。它不写 relation fact，也不改变本模块 owner。 |

## 输出 I/O

| 输出 | Consumer | 合同 |
| --- | --- | --- |
| active relation | Workbench/downstream | deduped aligned `row_ids`/`row_types`，一个 row 只属于一个 active case |
| history | Audit/withdraw | before/after、actor、event、timestamp、reason、rule/provenance |
| command result | caller | relation/version/affected rows/months/idempotent replay/outbox ids/barrier targets |
| dirty/outbox | durable runtime | 同事务 enqueue `workbench_relation`、`workbench` 和明确下游 scope |
| read distribution | downstream pages | 只有 `linked` / `unlinked`；non-fresh 不能返回为业务空集合 |

## 合法 relation modes

Mode 只描述业务 owner/provenance，不形成第三种页面状态。当前 registry 包括普通确认、exception closed、OA exempt、个人暂借还清、OA/附件冲抵、pending invoice、bank-flow batch、no-OA、turnover、batch accounting、ETC、input invoice OA reverse 等已登记 mode。新增 mode 必须进入 registry、状态转换测试、下游刷新矩阵和模块文档。

`automatic_decision`、`automatic_match`、`existing_case` 不是可新增的正式写入 mode。系统自动关系使用登记的正式 mode并以 actor/rule metadata 记录系统来源。

## 事务与一致性

- command service 必须接收明确 repository/idempotency/freshness 依赖，不接收整个 `Application`。
- relation、history、idempotency、audit/dirty/outbox 的业务事务必须原子；失败不得留下半关系或漏刷新。
- case id 重用、active member overlap、row type 对齐、expected version 和 idempotency fingerprint 必须在写入边界校验。
- 任意 `N:M:K` member set 都合法，只要上游业务规则已证明安全并且成员非空、唯一、typed。
- 自动扩展既有 active case 必须使用 `target_case_id` 并原子 replace；不得创建重叠的第二条 active relation。
- 精确 typed member set 的人工撤回历史阻止 deterministic engine 自动重建同一关系。

## Read facade

- `require_fresh=True` 时，missing/stale/source mismatch 必须返回非 fresh 并受控 enqueue，调用方不得把空 rows 当作无关系。
- 下游只有 active relation 是 linked 证据。历史关系、显示 tags、候选搜索结果、matching evidence 都不是支付/关联/成本证据。
- downstream read models 必须记录并比较 relation source versions，relation mutation 后旧 payload 不得继续 fresh。

## 文件范围

| 层 | 文件 |
| --- | --- |
| Domain/command | `workbench_pair_relation_service.py`、`workbench_relation_command_service.py`、`workbench_relation_modes.py` |
| UoW/repository | `workbench_uow.py`、`workbench_relation_command_repository_adapter.py`、`postgres_repositories/workbench_relation.py` |
| Read/projection | `workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Auto formalization | `workbench_free_matching_engine.py`、`workbench_matching_orchestrator.py`、`postgres_repositories/workbench_formal_relation.py` |
| Tests | `tests/test_workbench_relation_*.py`、`test_workbench_formal_relation_repository.py`、`test_workbench_matching_orchestrator.py` |

## 禁止路径与删除条件

- 禁止 route/service/worker 直接 SQL 写 relation/history。
- 禁止 `Application` snapshot、`app_settings state:*`、Redis、RabbitMQ、read model 或前端 event 成为 relation 事实源。
- 禁止 candidate/decision service/store/table/API、隐藏 fallback 或双写重新进入调用图。
- 旧 generic `MatchingEngineService` 仅可服务其独立 legacy reconciliation/内部转账备注上下文；它的 result 不得决定 Workbench membership、zone、linked status 或正式关系写入。该隔离由 boundary guards 和 grouping tests 保护。
- migration/repair 工具必须 dry-run、精确 scope、审计和 rollback manifest，且只能调用正式 command/repository adapter。

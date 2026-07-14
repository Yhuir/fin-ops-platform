# Phase 21 执行与闭环状态

日期：2026-07-14
状态：本地实现与自动化验证完成；生产 cutover 未执行

## 已锁定产品合同

- Workbench 只有 `paired` 与 `unpaired` 两种页面关系状态。
- 任意 active 正式关系的全部 canonical members 都进入一个 paired group；历史 case 前缀、人工/历史/系统来源和业务 mode 只可作为审计/动作 metadata，不能改变可见分区。
- 没有 active 正式关系的每个 canonical fact 都必须作为 typed identity singleton unpaired 显示，不能合并、隐藏或形成第三种候选状态。
- 确定性匹配跨月读取 OA、银行流水和发票，支持有界 N:M:K；只有强证据闭合、唯一且无冲突的结果才通过正式 command/UoW 创建或扩展 active relation。弱证据、歧义、冲突和资源中止均零写入。
- 自动候选/decision 不再是业务持久化、API 或 UI 状态；旧 service/store/engine、repair CLI、前端组件和运行时分支已删除。旧表物理存储仅在 Release A 回滚窗口保留，Release B 才删除。

## 模块边界与 I/O

| 边界 | 输入 | 输出 | I/O 责任 |
| --- | --- | --- | --- |
| formal fact repository | scope、source versions、canonical tables、active/history relations | immutable typed fact batch | 唯一 SQL 读取 owner；bulk、bounded |
| pure matcher | immutable fact batch、budget | zero or more deterministic `FormalRelationPlan` | 无 I/O；fail closed |
| matching orchestrator | plan、tenant/actor、UoW dependencies | active relation command result、audit/history/outbox | 不读 HTTP，不写 SQL |
| relation command/UoW | typed members、expected versions、idempotency | atomic relation/history/dirty/outbox | repository 承担持久化 |
| grouping projection | canonical rows、active relations | exact paired/unpaired partition | 无 I/O；不得隐藏 ungrouped rows |
| API/UI | fresh read model DTO | paired/unpaired list/detail/actions | 不推断关系、不恢复候选状态 |

## 已完成的旧链路删除

- 删除 Workbench candidate grouping/match/rules、reconciliation decision engine/models/store/cleanup、special candidate adapters/detectors、repair decision CLI。
- 删除 candidate/decision HTTP/UI 语义、CandidateGroup components/tests 和 candidate Browser flow。
- Release A 不携带 migration 0104；Release B 在零访问和数据安全门通过后，才 forward-drop `read_model.workbench_candidate_matches`、`read_model.workbench_reconciliation_decisions` 与精确旧 app-setting，且不修改 canonical facts 或 active relations。
- runtime guard 禁止旧模块/import/状态术语重新进入 app/service/tool；仅允许 read-boundary 对旧 payload 字段做剥离，避免历史缓存泄漏到新 DTO。

## 本地证据

- `python3 -m pytest -q`：4216 passed、48 skipped、605 subtests passed。
- `cd web && npm test -- --run`：833 passed。
- `cd web && npm run build`：成功。
- 关键 Chromium 业务流：6 passed，覆盖 Workbench confirm/withdraw、银行明细、进项发票和 OA 待付款 fan-out。
- migration contract：56 passed、19 subtests passed。
- 520 fixture：`oa-pay-2169` + `inv_imported_0369` + 发票号 `26532000000716859331` 保留原 active relation，历史 `decision:*` identity 仍显示 paired，不新建关系。
- 13-row fixture：13 个 canonical invoice identities 各自 unpaired singleton，minor units 合计 170949，无隐藏/重复/伪配对。
- lint、docs 和旧链路静态 guard 通过。

## 未完成的生产门

- 当前环境未设置 `FIN_OPS_TEST_DATABASE_URL`，因此没有执行真实 disposable PostgreSQL migration/catalog/data-hash 集成；Release A 不包含 schema 变更，Release B 在补齐真实 0001–0104 disposable PostgreSQL 证据前不得发布。
- Release A 已隔离到干净 `codex/workbench-formal-relations-release-a` 分支；0104 保留在独立 Release B 候选提交，不进入 A。
- 2026-07-14 对当前生产 release 的只读复核仍显示 520 group 为 unpaired；production migration、rehydrate、worker drain、System Audit 和 13 个真实 identities 的恢复证据尚未执行。
- 本轮没有执行任何生产写入、migration、read-model rebuild 或部署。

## 生产闭环门

1. 从经过审阅的干净 `codex/*` commit 构建 release；先运行 lint、backend、frontend、build、Chromium 和 disposable PostgreSQL migration gates。
2. 发布前在同一只读 snapshot 记录 canonical OA/invoice/bank counts/hashes、active relation/history hashes、520 relation ID/members 和真实 13 invoice identities/金额。
3. 仅通过 `./scripts/deploy-oa.sh` 发布不含 0104 的 Release A；保留旧表，确认 API/frontend/required workers 都来自同一 release。
4. 通过正式 refresh gateway/queue rehydrate `workbench`、`workbench_relation` 及注册下游，等待 dirty/outbox/dead-letter drained、workers 同 release、read models fresh。
5. 运行对象 identity、Workbench page Audit 和 System Audit；证明 520 paired、13 identities 各自恰好一次 unpaired、`P=R`、`U=C-R`、无 overlap/omission、下游 linked/unlinked 一致，并在稳定窗口证明旧表运行时零访问。
6. 只有 Release A 全部证据通过，才从独立、经过审阅的 Release B 提交发布 migration 0104；先在 disposable PostgreSQL 证明精确 drop 和数据哈希不变，再在生产确认旧 catalog objects 消失、canonical/relation hashes 不变并复跑 freshness/Audit。
7. 只有上述两个发布的证据全部通过，才能把 Phase 21 与用户任务标记为 complete。

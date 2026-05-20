# 数据库迁移文档

本目录记录 `fin-ops-platform` 从 app MongoDB 迁移到 PostgreSQL 的当前有效方案。迁移目标是：

- app 自身业务事实、设置、任务状态和读模型迁入 PostgreSQL。
- OA 系统 MongoDB 保持只读源，不修改、不写入、不作为 app 写库。
- 迁移完成后，app 主读写接入 PostgreSQL；需要 OA 源数据时仍通过 OA Mongo 只读 adapter 读取，或读取由只读同步生成的 PostgreSQL 投影。

## 阅读顺序

1. `00-current-state-inventory.md`：当前代码、服务器、MongoDB 和 PostgreSQL 盘点结果。
2. `code-evidence-index.md`：迁移前需要引用的代码证据索引。
3. `01-production-backup-staging.md`：生产只读盘点、app Mongo 备份、staging restore 和 PostgreSQL 基础检查结果。
4. `01-target-postgresql-design.md`：目标 PostgreSQL schema、表、索引、迁移映射和 OA 边界。
5. `02-postgresql-schema-migration.md`：阶段 02 migration runner、SQL migration、本地验证和服务器 apply gate。
6. `03-normalized-export-staging-import.md`：阶段 03 app Mongo 规范化导出和 PostgreSQL staging 导入。
7. `04-staging-transform-reconciliation.md`：阶段 04 staging 转正式表和对账报告。
8. `05-postgresql-repository-tests.md`：阶段 05 PostgreSQL repository、app 接入和测试。
9. `06-postgresql-integration-repository-closure.md`：阶段 06 真实 PostgreSQL integration、repository 缺口闭合和 API smoke。
10. `07-postgresql-domain-repository-completion.md`：阶段 07 PostgreSQL domain repository 闭合执行记录。
11. `08-postgresql-domain-repository-final-closure.md`：阶段 08 tax/ETC/historical/event-history 正式表闭合和 Gate 判定。
12. `09-postgresql-repository-extraction-transaction-boundary.md`：阶段 09 repository package 拆分、transaction boundary 收口、search runtime 决策和 Gate 判定。
13. `10-shadow-dualwrite-cutover-preflight.md`：阶段 10 shadow-read、dual-write 和 cutover preflight 基础设施、守卫、验证和 Gate 判定。
14. `11-production-shadow-read-rehearsal.md`：阶段 11 production shadow-read rehearsal runner/CLI、生产只读盘点、blocked artifact 和 Gate 判定。
15. `12-production-shadow-read-oneoff.md`：阶段 12 授权后的 production one-off shadow-read rehearsal、真实 report、Gate 和 blocker。
16. `13-shadow-mismatch-remediation-backfill-repair.md`：阶段 13 production mismatch 修复、PostgreSQL app-owned repair、final one-off shadow-read 和 Gate 判定。
17. `14-runtime-state-policy-mirror-rehearsal.md`：阶段 14 runtime state policy、controlled mirror-write rehearsal planning、policy artifact 和 Gate 判定。
18. `15-production-controlled-mirror-write-rehearsal.md`：阶段 15 production controlled mirror-write one-off rehearsal 前置检查、runtime live 分类、阻断原因和 Gate 判定。
19. `15A-workbench-p0-remediation.md`：阶段 15A workbench P0 根因确认、production repair dry-run、授权 repair、post-repair shadow-read 和后续 Gate。
20. `16-worktree-postgres-test-onboarding.md`：阶段 16 worktree disposable PostgreSQL test DB、真实 integration、production export 导入、本地 app/API smoke 和 post-main pending invoice 覆盖缺口。
21. `17-pending-invoice-postgres-coverage.md`：阶段 17 pending invoice command log PostgreSQL 正式表、export/transform/shadow-read 和 app PostgreSQL mode 覆盖。
22. `18-worktree-0008-full-data-revalidation.md`：阶段 18 在 `0008` schema 下复跑阶段 16 production export dataset 的 full-data import、transform、reconcile、app smoke 和 shadow-read smoke。
23. `19-main-production-fresh-import-reconcile.md`：阶段 19 production fresh export、staging import、`0008` migration、transform natural-key blocker 和 Gate 判定。
24. `19A-production-transform-natural-key-remediation.md`：阶段 19A transform natural-key upsert / event refresh / history order 修复，以及 production transform retry、reconcile、read-only shadow-read 结果。
25. `20-production-controlled-runtime-mirror-write-rehearsal.md`：阶段 20 production controlled runtime mirror-write rehearsal dry-run、用户授权 execute、post-execute validation 和剩余 runtime P2。
26. `21-precutover-readonly-p2-closure.md`：阶段 21 production pre-cutover read-only validation、post-execute runtime P2 接受和下一阶段 gate。
27. `22-production-read-switch-cutover-plan.md`：阶段 22 production read switch / cutover planning、release/runtime credential 前置条件、执行授权边界和回滚策略。
28. `23-release-runtime-credential-prep.md`：阶段 23 release candidate、production PostgreSQL runtime role/credential、no-traffic PostgreSQL mode check 和 Gate 判定。
29. `24-controlled-read-switch-rehearsal.md`：阶段 24 controlled production read switch rehearsal、same-run gates、no-traffic check、cutover preflight 和执行授权前置结论。
30. `25-controlled-read-switch-execute.md`：阶段 25 用户授权后的 controlled read switch execute、same-run gates、production service PostgreSQL read switch、post-switch validation 和 Gate 判定。
31. `25A-actual-postgres-store-shadow-remediation.md`：阶段 25A 真实 PostgresStateStore blocker 修复、生产只读复核和剩余 workbench candidate runtime snapshot repair blocker。
32. `25B-workbench-candidate-runtime-snapshot-repair.md`：阶段 25B 授权后的 production PostgreSQL `workbench_candidate_matches` runtime snapshot repair、full-domain shadow-read 和 read switch gate。
33. `07-shadow-dualwrite-production-cutover.md`：shadow、dual-write、生产切换、回滚和观察期规划。
34. `02-execution-plan.md`：完整阶段工作、并行/串行拆分、验收标准、回滚和阻断条件。

## 迁移硬约束

- 禁止修改 OA MongoDB。所有 OA 访问必须走 `MongoOAAdapter` 或后续只读同步器。
- 禁止在没有 app Mongo 可恢复备份和 staging 恢复演练前进入正式迁移。
- 禁止直接把 Mongo pickle/binary payload 手写解析后入库；必须复用现有 Python `ApplicationStateStore` 或业务 service 规范化导出。
- 禁止一次性切换全部读写路径；必须按 `expand -> backfill -> dual write / shadow read -> switch read -> contract` 推进。
- PostgreSQL 写入成为事实源后，不允许用旧 app Mongo 全量覆盖新库，只能通过补偿脚本修复差异。

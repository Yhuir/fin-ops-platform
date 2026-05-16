# 正式迁移 Go/No-Go 门禁报告 - 20260516

本文对应 P4-12：正式 app Mongo -> PostgreSQL 迁移和切换前门禁。本次只做证据复核、批次计划、对账模板和 go/no-go 结论，不迁移生产数据，不冻结 app Mongo，不切换 API，不访问 OA 源数据库。

## 结论

| 项目 | 结论 |
| --- | --- |
| go/no-go | `NO_GO` |
| 是否允许正式迁移生产数据 | 否 |
| 是否允许冻结 app Mongo | 否 |
| 是否允许生产 API 切换 | 否 |
| 是否允许进入 P4-11 生产切流执行 | 否 |
| 是否访问 OA 源数据库 | 否 |
| 是否需要用户生产切换授权 | 当前不应请求授权，门禁未通过 |

`NO_GO` 的直接原因：当前唯一 dry-run 报告 `migration-dry-run-report-20260516.md` 结论为 `NO_GO`，且正式迁移硬性前置中的 PostgreSQL PITR、文件 checksum、API 影子验证、压测和监控告警验证均缺少通过证据。

## 自动复核入口

仓库内提供只读脚本复核 P4-12 证据：

```bash
python3 scripts/tools/backend_refactor_readiness_gate.py --format markdown --fail-on-no-go
```

该脚本只读取证据文件，不迁移生产数据、不冻结 app Mongo、不切换 API。只要 PostgreSQL PITR、06A/06B/06C/06D dry-run、API shadow validation、监控告警验证、压测或回滚演练任一证据缺失或为 `NO_GO`，脚本就必须返回 `NO_GO`。

## 复核输入

| 输入 | 复核结果 |
| --- | --- |
| `docs/exec-plans/active/backend-refactor-prompts/12-formal-migration-and-cutover-gates.md` | 已读取。该 prompt 明确不能单独触发生产切流。 |
| `docs/exec-plans/active/backend-refactor-prompts/00-current-state-and-gates.md` | 已读取。当前仍列出 dry-run、文件迁移、read model、API 迁移、PITR、压测、影子读等未完成项。 |
| `docs/operations/backend-refactor/production-readiness-checklist.md` | 已读取。P4-10 当前结论仍为 `NO_GO`，并要求 staging 证据和 P0/P1 告警验证。 |
| `docs/operations/backend-refactor/migration-dry-run-report-20260516.md` | 已读取。报告结论为 `NO_GO`，没有可审计 dry-run 和实际对账数据。 |
| `docs/exec-plans/active/backend-refactor-progress.md` | 已读取。App Mongo 备份/恢复和 PostgreSQL schema 空库验证已完成；迁移工具 dry-run 仍是下一步。 |
| `docs/operations/backend-refactor/app-mongo-backup-runbook.md` | 已读取。App Mongo 备份、checksum、restore dryRun、恢复测试库和 GridFS 抽样已完成。 |
| `docs/operations/backend-refactor/server-postgresql-runbook.md` | 已读取。PostgreSQL 只监听 localhost，但未配置 PITR，未执行 PostgreSQL 逻辑备份演练。 |
| `docs/operations/backend-refactor/cutover-and-rollback-runbook.md` | 已读取。进入影子读前要求 readiness 无阻断、迁移对账无差异、文件 checksum、压测和回滚演练通过。 |
| `docs/operations/backend-refactor/data-migration-runbook.md` | 已读取。明确没有 dry-run 对账报告不允许生产数据迁移。 |
| `docs/operations/backend-refactor/migration-validation-report-template.md` | 已读取。阻断码和差异定位维度已具备模板。 |
| `docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md` | 已读取。P4-11 必须在门禁通过且用户明确授权后执行。 |

## 门禁状态表

| 门禁项 | 状态 | 证据 | 结论 |
| --- | --- | --- | --- |
| App Mongo 最新备份存在 | 已通过 | `app-mongo-backup-runbook.md` 记录 `2026-05-16 01:29:00 CST` 备份，checksum 为 `1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a`。 | 非阻断 |
| App Mongo 恢复演练 | 已通过 | 恢复到 `fin_ops_platform_app_restore_test_20260516`，collection count `total=50 diff=0`，GridFS 抽样 `integrity=OK`。 | 非阻断 |
| PostgreSQL schema migration | 部分通过 | `0001` 到 `0007` 已在 PostgreSQL 16.12 临时空库验证；尚缺 staging/带数据环境验证记录。 | 阻断正式迁移 |
| PostgreSQL 逻辑备份 | 未通过 | `server-postgresql-runbook.md` 明确未执行 PostgreSQL 逻辑备份演练。 | 阻断 |
| PostgreSQL PITR/恢复演练 | 未通过 | `server-postgresql-runbook.md` 明确未配置 PITR。 | 阻断 |
| PostgreSQL 网络暴露面 | 当前通过 | `listen_addresses: localhost`，当前未开放 PostgreSQL 公网访问。 | 非阻断，需持续守住 |
| 数据迁移 dry-run | 未通过 | `migration-dry-run-report-20260516.md` 结论为 `NO_GO`。 | 阻断 |
| count/hash/amount/month/status 对账 | 未通过 | 缺少实际 source、staging、target dry-run 数据和报告。 | 阻断 |
| file checksum 对账 | 未通过 | 文件内容 checksum 属于 06D，当前没有 MinIO/S3 dry-run 抽样下载校验通过记录。 | 阻断 |
| legacy id 覆盖率 | 未通过 | 缺少 staging -> facts dry-run 结果和 `legacy_id_map` 覆盖报告。 | 阻断 |
| API 影子读或契约比对 | 未通过 | 只有 API 契约和部分 Axum route 骨架/测试，未发现生产影子读窗口或旧 Python vs Axum 差异报告。 | 阻断 |
| NATS/outbox/Worker 链路 | 未通过 | 有 runbook 和部分实现/测试，但缺少 staging stream、consumer、DLQ、dead letter、人工重放闭环验证记录。 | 阻断 |
| read model/search 增量重建 | 未通过 | 有设计和 API 只读路径；当前门禁仍要求增量重建实现和 stale 指标验证。 | 阻断 |
| 监控和告警 | 未通过 | 已有指标和告警草案；缺少 exporter/staging 采集、Grafana、P0/P1 告警触发验证和值班绑定证据。 | 阻断 |
| 压测基线 | 未通过 | 未发现 staging 压测报告或 P50/P95/P99、错误率、DB/NATS/Worker 指标记录。 | 阻断 |
| 生产维护窗口 | 未确认 | 未发现变更窗口记录。 | 阻断 |
| 回滚演练 | 未通过 | 有 cutover runbook 模板；未发现读回滚、写回滚、文件回滚实际演练记录。 | 阻断 |

## 阻断项

| ID | 阻断项 | 影响 | 修复 prompt |
| --- | --- | --- | --- |
| `P4-12-BLOCK-001` | 缺少实际 06A manifest/NDJSON 导出产物。 | 无法建立 app Mongo source baseline。 | `docs/exec-plans/active/backend-refactor-prompts/06a-mongo-export-tooling.md` |
| `P4-12-BLOCK-002` | 缺少 06B staging import 执行报告。 | 无法证明导入 PostgreSQL staging 后失败记录保留且数量/hash/金额/月/状态可对账。 | `docs/exec-plans/active/backend-refactor-prompts/06b-postgres-import-validation-tooling.md` |
| `P4-12-BLOCK-003` | 缺少 staging -> facts dry-run 和 count/hash/amount/month/status/file checksum 实际对账。 | 正式迁移事实不可信。 | `docs/exec-plans/active/backend-refactor-prompts/06c-data-migration-dry-run.md` |
| `P4-12-BLOCK-004` | 缺少 GridFS -> MinIO/S3 dry-run、上传后抽样下载 SHA-256 和 `legacy_gridfs_id -> file_object_id` 映射通过报告。 | 文件迁移不可验证，切换后附件/导入文件可能不可恢复。 | `docs/exec-plans/active/backend-refactor-prompts/06d-gridfs-minio-migration.md` |
| `P4-12-BLOCK-005` | PostgreSQL 未配置 PITR，未执行逻辑备份和恢复演练。 | 新事实源不可恢复，生产迁移无安全退路。 | `docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md` |
| `P4-12-BLOCK-006` | NATS/outbox/Worker 链路缺少 staging 验证。 | read model 重建、文件处理、OA 同步和 dead letter 重放链路不可靠。 | `docs/exec-plans/active/backend-refactor-prompts/07-outbox-queue-worker.md` |
| `P4-12-BLOCK-007` | read model/search 增量重建缺少端到端验证。 | 切读后页面可能 stale 或无法从事实表恢复。 | `docs/exec-plans/active/backend-refactor-prompts/08-read-models-and-search.md` |
| `P4-12-BLOCK-008` | API 影子读、旧 Python vs Axum 契约比对和差异报告缺失。 | 不能证明新 API 与前端和旧契约兼容。 | `docs/exec-plans/active/backend-refactor-prompts/09a-low-risk-read-apis.md`、`09b-import-file-apis.md`、`09c-workbench-read-apis.md`、`09d-reconciliation-write-apis.md` |
| `P4-12-BLOCK-009` | 压测基线和 Grafana/Prometheus/P0/P1 告警验证缺失。 | 切换窗口内无法判断性能、队列、备份和 read model 风险。 | `docs/exec-plans/active/backend-refactor-prompts/10-observability-security-readiness.md` |
| `P4-12-BLOCK-010` | 生产维护窗口、回滚演练和用户切换授权均不存在。 | 不能进入 P4-11。 | `docs/exec-plans/active/backend-refactor-prompts/11-cutover-and-rollback.md`，但只能在上述阻断项全部清除后执行 |

## 正式迁移批次计划

以下计划只作为后续 `GO` 前的执行顺序模板。当前 `NO_GO` 状态下不得执行这些批次。

| 批次 | 范围 | 进入条件 | 对账要求 | 阻断规则 |
| --- | --- | --- | --- | --- |
| 1 | 基础导入、manifest、legacy id map、文件元数据 | 06A/06B/06C dry-run 无阻断；PostgreSQL 备份/PITR 可恢复 | count、NDJSON hash、manifest checksum、legacy id 覆盖率 | 任一对象缺映射或 hash/count 差异未解释即停 |
| 2 | 银行流水 | 分区已按 manifest 月份准备 | count、金额合计、月份分布、状态分布、legacy id | 金额、月份或状态差异未解释即停 |
| 3 | 发票、税金、税额口径 | 发票枚举和金额精度映射已验证 | count、价税合计、税额、月份、状态 | 金额或状态差异未解释即停 |
| 4 | OA 归一化缓存和附件映射 | 不访问 OA 源库；只使用已迁移 app 缓存和既有只读同步输出 | count、月份、水位、附件映射、legacy id | 需要人工查询 OA 源库才能解释差异即停 |
| 5 | 核销、异常、免 OA、往来款 | audit、outbox、幂等和事务边界已验证 | count、金额、状态、审计事件、outbox event、read model scope | 缺 audit/outbox 或幂等冲突即停 |
| 6 | read model 和 search index 重建 | facts 已对账通过；worker 可重建指定 scope | scope_month 覆盖、stale_seconds、search coverage、页面样本 | stale 超阈值或搜索覆盖不足即停 |
| 7 | job/outbox 需要保留的任务状态 | NATS/Worker staging 验证通过 | worker_tasks、attempts、dead_letters、outbox status | 任务事实源和 NATS 状态不一致即停 |

## 正式迁移对账报告模板

正式迁移每批次必须生成报告。报告不得包含 secret、完整 URI、token 或带签名 URL。

```text
report_id:
change_id:
batch_no:
batch_name:
started_at:
finished_at:
operator:
source_snapshot:
  app_mongo_backup_id:
  source_manifest_id:
target_snapshot:
  postgres_database:
  migration_version:
  migration_run_id:
pre_checks:
  postgres_backup_id:
  pitr_drill_id:
  minio_versioning_status:
  monitoring_snapshot:

counts:
  expected:
  actual:
  diff:
amounts:
  expected:
  actual:
  diff:
hashes:
  source_manifest_sha256:
  target_aggregate_hash:
  diff:
month_distribution:
  expected:
  actual:
  diff:
status_distribution:
  expected:
  actual:
  diff:
file_checksums:
  sampled:
  matched:
  mismatched:
legacy_id_coverage:
  expected:
  mapped:
  missing:

findings:
  - severity:
    code:
    object_type:
    month:
    status:
    legacy_id:
    row_no:
    expected:
    actual:
    owner:
    disposition:

decision:
  go_no_go:
  reason:
  next_batch_allowed:
  rollback_required:
  approver:
```

## 切换前检查清单

当前所有未通过项都必须在进入 P4-11 前变为通过，并附证据链接或执行记录。

- [ ] App Mongo 最新冻结点备份、checksum、恢复演练通过。
- [ ] PostgreSQL 逻辑备份、PITR 或等价时间点恢复演练通过。
- [ ] MinIO/S3 versioning 或等价恢复策略通过，GridFS 文件抽样下载 checksum 通过。
- [ ] 06A/06B/06C/06D dry-run 报告均为 `GO`，且无未解释差异。
- [ ] 每个正式迁移批次都有可定位到 object_type、month、status、legacy_id 的对账报告模板和执行计划。
- [ ] Axum API staging 契约测试、旧 Python vs Axum 影子读差异报告通过。
- [ ] NATS JetStream、outbox publisher、Worker retry/backoff/dead letter 和人工重放通过。
- [ ] read model/search index 可按 scope_month 增量重建，并有 stale 指标和告警。
- [ ] 核销确认、撤销、异常处理、免 OA 批次等高风险写 API 有事务、audit、outbox 和幂等验证。
- [ ] Prometheus/Grafana/P0/P1 告警已接入并经过 staging 触发验证。
- [ ] 压测报告记录 P50/P95/P99、错误率、DB pool、慢查询、NATS backlog、Worker retry/dead letter。
- [ ] 生产维护窗口、负责人、观察窗口、回滚截止点和审批人已确认。
- [ ] P4-11 切换和回滚 runbook 已演练，并明确旧 Python/app Mongo 在回滚窗口内保留。

## 禁止事项确认

- 本次未迁移生产数据。
- 本次未冻结 app Mongo。
- 本次未切换 API。
- 本次未访问、备份、导出、恢复、修改、压测或人工查询 OA 源数据库。
- 本次未开放 PostgreSQL 公网。
- 本次未写入 secret、URI、密码、token、S3 credential 或 NATS credential。
- 当前 `NO_GO` 结论不得被解释为生产切换授权。

# 回滚演练记录 - 20260517

本文是 p4-15 的机器可读配对证据。当前任务未执行生产切流、未开启双写、未冻结或删除 app Mongo、未访问 OA 源数据库，也未写入 secret、完整 URI、密码或 token。

## 结论

| 项 | 值 |
| --- | --- |
| Gate | **NO_GO** |
| go/no-go | `NO_GO` |
| generated_at | `2026-05-17T10:12:00+08:00` |
| evidence author | Codex |
| execution operator | `pending_named_finops_backend_operator` |
| rollback owner | `pending_named_rollback_owner` |
| business owner | `pending_named_business_owner` |
| change approver | `pending_named_change_approver` |
| production cutover authorized | no |
| dual-write authorized | no |
| app Mongo freeze authorized | no |
| OA source database accessed | no |

结论为 `NO_GO`，原因是本次只生成演练和审批证据，没有获得受控 staging 或 production 演练窗口，也没有命名负责人、回滚负责人、业务负责人和审批人。

## 最新 app Mongo 备份确认

| 字段 | 值 |
| --- | --- |
| checked evidence | `docs/operations/backend-refactor/app-mongo-backup-restore-report-20260517.json` |
| source database | `fin_ops_platform_app` |
| backup time | `2026-05-16 01:29:00 CST` |
| checksum algorithm | `sha256` |
| checksum | `1968e81888dd359ba7d9d8424cdef399744d81a6d5e7305db1f8222404b9422a` |
| restore drill status | `GO` |
| freeze-point backup confirmed | no |
| freeze performed by this task | no |

既有 app Mongo 备份恢复证据可作为最近备份参考，但它不是切换窗口内创建并审批的 freeze-point backup。因此回滚门禁仍为 `NO_GO`。

## 演练步骤记录

| step | start/end | operator | metric | rollback point | expected result | actual result | go/no-go |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shadow_read_rollback | `not_executed` / `not_executed` | `pending_named_finops_backend_operator` | API shadow status, 5xx, P95, stale seconds | `shadow_read_enabled=false` | 关闭影子读，不影响用户可见旧 Python API。 | 未获审批窗口，未执行。 | `NO_GO` |
| small_scope_read_rollback | `not_executed` / `not_executed` | `pending_named_finops_backend_operator` | route error rate, P95, PG pool, stale seconds | 小范围读路由回旧 Python | 低风险读流量可回旧路径，PostgreSQL 保留现场。 | 缺少 route snapshot、流量 scope 和回滚负责人，未执行。 | `NO_GO` |
| dual_write_disable_plan | `not_executed` / `not_executed` | `pending_named_finops_backend_operator` | dual-write diff, idempotency conflict, outbox backlog, audit success | `dual_write_enabled=false` | 关闭双写，冻结差异，不删除业务事实。 | 本任务未启用双写，也无 staging replay 记录，未执行。 | `NO_GO` |
| full_read_switch_rollback | `not_executed` / `not_executed` | `pending_named_finops_backend_operator` | global 5xx, P95, PG pool, NATS backlog, stale seconds | 全量读路由回旧 Python | 全量读切换可通过路由配置回滚，app Mongo 不动。 | 缺少全量读切换演练和 route snapshot，未执行。 | `NO_GO` |
| old_write_resume_plan | `not_executed` / `not_executed` | `pending_named_finops_backend_operator` | old write success, Mongo health, compensation queue, audit gaps | PostgreSQL 成为唯一事实源前恢复旧写 | 回滚窗口内可恢复旧写，差异走审计补偿，不覆盖 PostgreSQL。 | 缺少写回滚演练和业务验收窗口，未执行。 | `NO_GO` |
| app_mongo_archive_freeze_rollback_constraints | `not_executed` / `not_executed` | `pending_named_dba_or_ops_owner` | collection count, backup checksum, fact source status, retention | app Mongo 保留为归档和回滚参考 | 不删除 app Mongo；PostgreSQL 成为事实源后禁止旧 Mongo 全量覆盖。 | 未授权冻结，也未创建 freeze-point backup，未执行。 | `NO_GO` |

## 阻塞项

- 未提供已审批的回滚演练窗口。
- 未提供命名执行 operator、cutover owner、rollback owner、business owner 和 change approver。
- 未捕获 route configuration snapshot 或 feature flag snapshot。
- 六项回滚场景均未在 staging 或 production 形成执行记录。
- 现有 app Mongo 备份恢复证据为最近备份参考，但不是切换窗口 freeze-point backup。
- 总体 readiness gate 仍有其他生产就绪证据未通过。

## 安全边界

- 未切流、未双写、未冻结 app Mongo、未删除 app Mongo。
- 未访问 OA 源数据库。
- PostgreSQL 成为事实源后，禁止旧 Mongo 全量覆盖 PostgreSQL。
- 旧 Python 和 app Mongo 必须在回滚窗口内保留，直到单独的归档和下线审批完成。

# PostgreSQL PITR 恢复演练报告模板

本文是 PostgreSQL backup、WAL/PITR 和 isolated restore drill 的证据模板。真实报告由 `scripts/tools/postgres_pitr_restore_drill.py` 生成，并以 `postgres-pitr-drill-YYYYMMDD.json` 和 `postgres-pitr-drill-YYYYMMDD.md` 成对提交。

## 边界

- 只允许在受控 staging 或明确授权的生产运维窗口执行真实备份和恢复演练。
- PostgreSQL 不得为了演练开放公网。
- Secret 只从环境变量读取，不写入报告、日志或 git。
- 不访问 OA 源数据库。
- 不修改业务事实数据。
- 恢复演练必须落到 isolated restore instance，不能覆盖生产 PostgreSQL。

## 必填字段

| field | requirement |
| --- | --- |
| `started_at` / `finished_at` | 备份和恢复演练的开始、结束时间。 |
| `operator` | 执行人或自动化身份。 |
| `source_instance` | 脱敏后的源 PostgreSQL 环境标签，不是完整连接串。 |
| `restore_instance` | 脱敏后的 isolated restore instance 标签。 |
| `backup_artifacts` | 至少包含 logical backup 和 base backup 记录。 |
| `wal_archive_status` | WAL archive 状态、base backup id、WAL archive range。 |
| `restore_target_time` | PITR restore target time。 |
| `sample_counts` | sample count checks，至少覆盖 migration 版本、关键事实表、read model 可重建性。 |
| `checksum_results` | checksum 或 pg_restore list validation 结果。 |
| `rpo_seconds` / `rto_seconds` | 恢复点和恢复时间指标。 |
| `GO/NO_GO` | 总体门禁结论。 |

## Markdown 摘要模板

```text
Gate: **GO/NO_GO**
operator:
started_at:
finished_at:
source_instance:
restore_instance:
restore_target_time:
base backup:
logical backup:
WAL archive:
WAL archive range:
checksum:
sample count checks:
RPO:
RTO:
blockers:
```

## GO 条件

- logical backup 已生成，且 checksum 或 `pg_restore --list` 校验通过。
- base backup 已记录，WAL archive 连续且可用于 restore target time。
- PITR 已恢复到 isolated restore instance。
- sample count checks 无无法解释差异。
- RPO/RTO 已记录且满足变更单目标。
- 报告为成对 JSON + Markdown，均为 `GO`，且不包含 secret、完整 URI、密码、token、S3 credential 或 NATS credential。

## NO_GO 条件

- 缺少受控 staging 环境变量。
- 只完成 `pg_dump`，但没有 WAL/PITR 或 isolated restore drill。
- restore target time、base backup、WAL archive range、checksum/list validation、sample count checks、RPO/RTO 任一缺失。
- 恢复演练覆盖生产实例或需要开放 PostgreSQL 公网。
- 任一 secret、完整 URI、密码、token 或 credential 出现在报告中。

## failure handling

1. 任一命令失败时保持 `NO_GO`。
2. 保留已生成的脱敏报告和 blocker，不重试生产操作。
3. 修复 staging 环境、WAL archive、backup dir 或 isolated restore instance 后重新生成报告。
4. 不得把人工口头确认或模板文件标记为 `GO`。

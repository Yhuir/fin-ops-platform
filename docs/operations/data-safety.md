# 数据安全、重置、备份与对象存储

本文合并维护数据重置、备份恢复、对象存储和高风险数据操作的运维口径。

## 数据安全原则

- 生产级数据操作必须考虑权限、审计、回滚、数据一致性和验证方式。
- PostgreSQL 是 app 主读写事实源；OA MongoDB 继续只读接入。
- Redis 只服务明确的 integration/session cache，不保存页面财务事实；RabbitMQ 只作为可选 transport/wakeup。
- 对象存储保存文件对象，数据库保存对象引用、checksum、大小、文件名和来源。

## 数据重置

数据重置必须限定范围并记录：

- 操作者、时间、原因、环境、影响模块和影响对象。
- 是否清理通用 outbox、领域 dirty scope、integration cache、对象存储引用。
- 重置前备份和重置后验证命令。
- 是否需要暂停 worker 或 drain queue。
- reset job 状态必须进入 `BackgroundJobService` / runtime job 状态面，不能恢复旧内存 `DataResetJob` / `_data_reset_jobs` 路径。

重置后必须确保页面 canonical API 不返回重置前事实，且 integration cache 不回灌旧数据。

生产执行数据重置前，必须由 root 运维入口创建与动作绑定的恢复点：

```bash
sudo /usr/local/sbin/finops-deploy-control settings-data-reset-restore-point \
  <release-name> <run-id> reset_bank_transactions|reset_invoices|reset_oa_and_rebuild <operator>
```

该命令复用 `write-operation-restore-point` 的 custom `pg_dump`、`pg_restore --list`、SHA-256 manifest 和固定目录约束，并在备份前后重算包含目标行版本的影响 fingerprint。数据范围变化、dump/manifest 不一致或数据库登记失败均不签发短时 receipt。设置页只能使用 action/fingerprint 精确匹配且未过期、未撤销、未消费的 receipt；API 创建任务时原子消费，worker 锁表后再次重算 fingerprint。不得直接插入 receipt、复用其他动作/任务的 receipt，或绕过设置页/worker 执行 SQL 清理。

## 备份与恢复

备份至少覆盖：

- PostgreSQL schema/data。
- 对象存储 bucket 或兼容存储路径。
- 部署 env、systemd/manifest、Nginx 配置和可恢复的 runtime 配置。

恢复必须验证：

- app check 可通过。
- 关键 API 返回 JSON 而不是 HTML。
- canonical 页面 API 与 System Audit 正常。
- worker/queue 可观测且没有 orphan 领域任务。

## 对象存储

- MinIO/S3 只保存文件对象，不作为业务状态事实源。
- 文件上传需要 checksum、大小、MIME/扩展名校验和来源记录。
- GridFS 或 legacy 文件路径只作为迁移观察期回滚/审计来源，不作为新增写入目标。
- backfill 需要 dry-run、checksum 校验、失败重试和短期回滚路径。

## 高风险操作清单

| 操作 | 必要检查 |
| --- | --- |
| 清库/重置 | 备份、权限、审计、worker 暂停、领域队列/integration cache 清理 |
| 对象存储迁移 | checksum、引用完整性、dry-run、回滚路径 |
| 批量撤回/repair | affected objects、审计、跨页刷新、回滚说明 |

## 统一事实源合同只读审计

发布前后可通过 root-owned helper 运行
`sudo /usr/local/sbin/finops-deploy-control domain-contract-audit <release-name>`。
该命令连接 activation 将迁移的 PostgreSQL primary，并在强制只读会话中只统计 canonical 发票、银行流水、关联关系、后台任务和
durable outbox 的结构合同违规数，
不返回业务样本、不执行修复；`summary.blocking_issue_count` 非零时退出码为 1，
数据库配置缺失时退出码为 2，均不得视为通过。

## 银行分类历史 `unknown` 修复

`tools/repair_unknown_bank_transaction_categories.py` 只处理旧人工撤销错误留下的 active `category=unknown, source=manual`。工具默认拒绝写入；生产操作必须依次执行：

1. 确认 active release 后，通过 root-owned helper 运行 `sudo /usr/local/sbin/finops-deploy-control bank-transaction-category-repair <release-name> --dry-run`，记录 `strict_candidate_count` 与 `manual_review_candidate_count`。
2. 只有同时满足可解析 canonical bank transaction/精确月份、raw payload 标明人工补标签、且 category event 明确证明“从非空人工标签清除为 null”的记录进入 strict 集合；证据不足记录只进入人工复核，不自动修改。
3. 使用同一 helper 追加 `--apply --operator <审计操作者> --expected-candidate-count <dry-run数量>` 执行。数量变化立即失败，禁止扩大 predicate 或跳过 count gate。
4. 工具在一个事务内把 strict category 标为 `cleared`，写 event/audit，并通过正式 writer 输出必要领域任务；任一写入或入队失败全部回滚。
5. 等待 durable queue drain 后再次 dry-run；strict 必须为 0。随后验证银行明细显示待分类、可重新打标签、自动标签无撤销按钮，并检查 BankDetails/Workbench/外部往来等受影响页面 freshness/Page Audit。

不得直接 `UPDATE` read model、把 `unknown` 改成任意业务标签、忽略 manual review，或以兼容 fallback 保留旧撤销路径。数据库备份/PITR 是灾难回滚边界；单条业务恢复应重新人工补标签，保留审计历史。

## 相关文档

- PostgreSQL runtime：`postgresql-runtime.md`
- Worker 与已退役 read model 防回归：`runtime-worker-governance.md`
- 部署：`deployment.md`
- 监控：`monitoring.md`

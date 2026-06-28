# 运维文档索引

- `deployment.md`：发布路径、环境和部署检查。
- `data-safety.md`：数据重置、备份恢复、对象存储和高风险数据操作。
- `etc-business-batches.md`：ETC 业务批次、OA 自动检测、迁移 dry-run、回滚和 Nginx/API smoke。
- `invoice-pool-cleanup.md`：统一发票池清理、备份、dry-run、soft reference gate 和重导验收。
- `object-identity-dedup.md`：业务对象 identity/dedup 统一规则审计、blocking issue、人工 repair 原则。
- `postgresql-runtime.md`：当前 PostgreSQL primary runtime、queue/background jobs、direct API、备份、回滚和验证边界。
- `read-model-production-evidence-runbook.md`：历史 Read Model 生产证据归档；当前页面读取不再使用该 runbook 作为验收入口。
- `runtime-worker-governance.md`：真实 worker manifest、systemd、deploy readiness、App Health、durable queue、backfill、hardening 和运维修复边界。
- `runtime-sync-baseline-2026-06-12.md`：历史同步基线归档；记录旧 read-model SLO 差距和 repair 优先级，不作为当前 direct API 验收入口。
- `runtime-sync-repair-2026-06-12.md`：历史 scope repair 归档；当前页面读取不再使用 scope repair 发布流程。
- `runtime-sync-slo-baseline-2026-06-13.md`：历史全 app 同步 SLO 基线归档；其中 read model/page 覆盖是迁移前证据。
- `runtime-sync-stage1-2026-06-13.md`：历史 Stage 1 生产 SLO 采集归档；read model smoke 工具不再作为当前入口。
- `runtime-sync-stage2-2026-06-13.md`：历史 Stage 2 direct-scope/read-model smoke 归档；critical read model 5 秒 SLO 已被 direct API 迁移取代。
- `runtime-sync-stage3-2026-06-13.md`：历史 Stage 3 dispatcher/read-model SLO 归档；bank-account-balance required worker 已下线。
- `runtime-sync-stage4-2026-06-13.md`：历史 Stage 4 全页面 HTTP SLO 归档；保留登录态生产验收命令参考。
- `runtime-sync-stage5-2026-06-13.md`：历史 Stage 5 写操作 durable outbox SLO 审计归档。
- `runtime-sync-stage6-2026-06-13.md`：历史 Stage 6 受控写操作 E2E smoke 归档；写后 outbox/readiness 口径需按当前 direct API 文档重新解释。
- `runtime-sync-stage7-2026-06-13.md`：历史 Stage 7 全 app 同步闭环 gate 归档；`direct read model` 术语不作为当前架构入口。
- `runtime-sync-stage8-2026-06-13.md`：历史 Stage 8 写操作 E2E scenario 只读 discovery 归档。
- `runtime-sync-stage9-2026-06-13.md`：历史 Stage 9 写操作闭环 profile 扩展归档。
- `monitoring.md`：健康状态、后台任务和告警。

部署资产和 OA 联调细节见 `../../deploy/oa/README.md`。

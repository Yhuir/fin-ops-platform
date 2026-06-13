# 运维文档索引

- `deployment.md`：发布路径、环境和部署检查。
- `data-safety.md`：数据重置、备份恢复、对象存储和高风险数据操作。
- `etc-business-batches.md`：ETC 业务批次、OA 自动检测、迁移 dry-run、回滚和 Nginx/API smoke。
- `object-identity-dedup.md`：业务对象 identity/dedup 统一规则审计、blocking issue、人工 repair 原则。
- `postgresql-runtime.md`：当前 PostgreSQL primary runtime、queue/read model、备份、回滚和验证边界。
- `runtime-worker-governance.md`：Worker + Read Model manifest、systemd、deploy readiness、App Health、durable queue、backfill、hardening 和运维修复边界。
- `runtime-sync-baseline-2026-06-12.md`：2026-06-12 生产只读同步基线、SLO 差距、repair 优先级和后续阶段判断。
- `runtime-sync-repair-2026-06-12.md`：2026-06-12 生产 scope repair 发布、dry-run/apply、audit、replacement scope 收敛和剩余风险。
- `runtime-sync-slo-baseline-2026-06-13.md`：2026-06-13 全 app 同步 SLO 基线、read model/page 覆盖、组件取舍和下一阶段执行入口。
- `runtime-sync-stage1-2026-06-13.md`：2026-06-13 Stage 1 生产 SLO 采集、PostgreSQL/RabbitMQ 观测、read model smoke 工具和下一阶段执行入口。
- `runtime-sync-stage2-2026-06-13.md`：2026-06-13 Stage 2 direct-scope smoke、optional worker 缺口、critical read model 5 秒 SLO 结果和下一阶段执行入口。
- `monitoring.md`：健康状态、后台任务和告警。

部署资产和 OA 联调细节见 `../../deploy/oa/README.md`。

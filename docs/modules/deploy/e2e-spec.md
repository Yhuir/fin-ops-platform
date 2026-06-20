# Deploy Spec-first E2E Spec

部署模块的 Spec-first E2E 目标是证明发布、CI、Nginx、systemd、worker、readiness、rollback 和 production smoke 能支撑页面级 E2E 目标。它没有业务页面，但直接决定所有 Browser E2E 和 runtime gate 的可信度。

## Spec IDs

| Spec ID | 运维可观察合同 | 必须证明 |
| --- | --- | --- |
| `DEPLOY-E2E-001` | `bash scripts/verify.sh all` 不能漏跑 backend、frontend、build、Playwright smoke 和 docs。 | nightly/verify contract tests。 |
| `DEPLOY-E2E-002` | release-based deploy 上传、check、activate、health ready、public session route smoke 顺序正确。 | deploy script tests + staging/production release smoke。 |
| `DEPLOY-E2E-003` | systemd API、dispatcher、required workers 指向同一 active release。 | deploy-control status、systemd WorkingDirectory、runtime health。 |
| `DEPLOY-E2E-004` | Nginx `/fin-ops/` SPA、`/fin-ops-api/` 和 `/fin-ops/api/` 不互相吞路由，session API 返回 JSON。 | Nginx config tests + live route smoke。 |
| `DEPLOY-E2E-005` | 发布后 `/health/ready`、App Health、worker/read model readiness 通过，runtime blocker 为 0。 | health ready + runtime_sync_closure_gate。 |
| `DEPLOY-E2E-006` | 生产/staging rollback、backup/PITR、secret/env、old release cleanup 有可执行证据。 | runbook/smoke；本地单测只能保护脚本合同。 |

## 外部风险

真实 SSH/sudo/root-owned helper、systemd restart、PostgreSQL migration、Nginx live config、Redis/RabbitMQ、OA cookie、GitHub Actions 启用状态和浏览器缓存都属于 `external-risk`。

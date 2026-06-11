# 部署 模块维护入口

- Module key: `deploy`
- 类型: 跨环境发布与验证边界
- Route: 无业务页面；发布后依赖 `/health/ready`、`/api/session/me`、App Health/App Status
- Page key: `N/A`

## 修改前必读

- `docs/dev/nightly-ci.md`
- `docs/dev/testing.md`
- `docs/operations/index.md`
- `docs/operations/postgresql-runtime.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/operations/monitoring.md`
- `docs/operations/data-safety.md`
- `deploy/oa/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/app-health-operations/README.md`
- `docs/modules/permissions-and-audit/README.md`

## 代码入口

- 本地发布入口：`scripts/deploy-oa.sh`
- Python 发布脚本：`scripts/deploy_oa.py`
- 统一验证入口：`scripts/verify.sh`
- GitHub Actions：`.github/workflows/nightly-ci.yml`
- 生产控制 helper：`deploy/oa/bin/finops-deploy-control.sh`
- worker 安装 helper：`deploy/oa/bin/finops-ensure-runtime-workers.sh`
- Nginx 示例：`deploy/oa/nginx.fin-ops.conf.example`
- systemd 示例：`deploy/oa/systemd/*.service.example`
- env 示例：`deploy/oa/env/*.env.example`
- worker manifest：`backend/src/fin_ops_platform/tools/runtime_worker_manifest.py`
- runtime registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

生产发布入口是：

```bash
./scripts/deploy-oa.sh
```

默认生产路径是 release-based 部署，不直接覆盖 `/opt/fin-ops/current/backend`：

1. 本地构建 `web/dist`，打包 `backend + web/dist + scripts + deploy/oa`。
2. 上传到 `/opt/fin-ops/releases/<release-name>/src`。
3. 远端先执行 deploy-control contract check、release layout check、storage preflight、`check-release`。
4. 激活时由 root-owned `finops-deploy-control` 执行依赖安装、PostgreSQL migration、legacy current archive、systemd drop-in、runtime worker ensure、frontend publish、service restart、worker readiness wait。
5. 发布脚本等待本机 `/health/ready`，再检查公网 `/fin-ops-api/api/session/me` 和 `/fin-ops/api/session/me` 都作为 JSON API 被代理。
6. 旧 release 默认保留最近 4 个，并保护 active release references。

Nightly CI 入口是：

```bash
bash scripts/verify.sh all
```

它覆盖后端 `--check`、后端 unittest discovery、前端 Vitest、前端 build、docs 结构检查。

## 影响面

部署改动不能只看脚本本身，必须列出影响面：

- 发布包：backend、web/dist、scripts、deploy/oa、`RELEASE.json`。
- 运行时：PostgreSQL DSN、migration-only DSN、Redis、RabbitMQ、S3/MinIO、OA integration env。
- systemd：API、worker template、RabbitMQ dispatcher/topology、drop-in reset `EnvironmentFile=`。
- worker：required/optional worker 矩阵来自 registry/manifest，不能在 runbook 维护第二份清单。
- Nginx：`/fin-ops/` SPA、`/fin-ops-api/` API、`/fin-ops/api/` relative API、assets cache、index no-store。
- readiness：`/health/ready` 是发布 readiness 边界；systemd active 不等于 release ready。
- App Health：worker missing/stale/mismatch、dirty scopes、RabbitMQ backlog、PostgreSQL runtime unavailable 必须可观测。
- 权限/session：发布后 `/api/session/me` 必须保持 JSON API，不能被 SPA fallback 吃掉。
- 数据安全：发布前备份、migration、rollback/PITR、runtime config 需要 staging 或生产 runbook，不能只靠 unittest。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 修改 `scripts/deploy_oa.py`、`scripts/deploy-oa.sh`、`scripts/verify.sh` 或 nightly workflow。
- 修改 `finops-deploy-control`、`finops-ensure-runtime-workers`、systemd/env/Nginx 模板。
- 新增 worker、read model refresh event、RabbitMQ dispatch event、runtime dependency 或 required env。
- 修改 `/health`、`/health/ready`、App Health/App Status、session route 或 OA 同域路径。
- 修改 PostgreSQL migration、backup/rollback、runtime secret、部署用户 sudo contract。
- 线上或手工发现部署、CI、worker readiness、Nginx proxy/cache、release rollback 相关 bug。

## 本目录文件

- `state-machine.md`：维护 CI、release、migration、activation、readiness、rollback 和 worker 状态。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

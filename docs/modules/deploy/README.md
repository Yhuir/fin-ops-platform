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
- Settings ACL preflight collector：`backend/src/fin_ops_platform/tools/settings_access_control_preflight.py`
- OA exact cleanup/rollback：`deploy/oa/fin_ops_role_binding.mysql.sql`

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

旧覆盖式 `legacy-current` deploy mode 已移除；`scripts/deploy-oa.sh` 不再接受 `--mode`，
也不再生成覆盖 `/www/wwwroot/fin-ops/dist` 或 `/opt/fin-ops/current/backend` 的 payload。
runtime env 事实源是 `deploy/oa/env/*.env.example` 和生产 `/etc/fin-ops/*` split env，
不再维护仓库根部单文件 `deploy/oa/fin_ops.env.example`。

Nightly CI 入口是：

```bash
bash scripts/verify.sh all
```

它覆盖后端 `--check`、后端 unittest discovery、前端 Vitest、前端 build、deterministic Playwright browser smoke、docs 结构检查。

## Settings ACL release-prep 边界

当前仓库已实现以下发布准备合同；真实 remote preflight、helper bootstrap、candidate activation 和 post-deploy evidence 仍需受控执行，本文不声称生产已部署：

- existing collector 盘点 canonical PostgreSQL ACL、root env、唯一 `finops:app:view` menu、三个专用 roles/bindings/members，并输出 release-bound salted exact artifact。三项 APP admission env 已退役，任一 key 存在即阻断；fixed OA selector env 必须保留并精确指向 `finops:app:view`，但只定位 OA menu，不能 grant APP access。精确 env key 清单只由 canonical deploy runbook/preflight owner 维护。
- 普通 `eligible` 与 `cleanup_eligible` 分开。只有 fixed-menu non-dedicated bindings 可进入 approved before-image 约束的 exact cleanup；selector/menu/role/member/env/identity/fingerprint drift 全部零写阻断。
- release 上传不得更新 root helper。首次/升级 deploy-control 必须走 manual-root、candidate hash-pinned、同文件系统 temp + atomic `mv` 流程，并证明 runtime-worker helper、active release、service、DB/OA/ACL fingerprint 不变；禁止 legacy `self-update`。
- candidate-bound remote preflight artifact/SHA-256 经批准后，激活前必须 just-in-time 重跑；任一事实/hash变化回审批 gate。current runtime checkpoint 通过后才 quiesce API/workers，再执行 migration/CHECK 和 ACL-safe candidate。
- candidate 只通过 `./scripts/deploy-oa.sh --activate-existing --release-name <release>` 激活；该路径不 build/upload/replace/helper self-update。previous release 只有具备同等 ACL-safe capability/source/migration fingerprint 才可恢复。
- cleanup/rollback/restore/router-session read-back 或 evidence hash 任一失败都保持 maintenance 并 forward repair；不能跳过审批继续 post-deploy，也不能启动 vulnerable previous binary。

完整命令、artifact 路径、secret stdin 和 operator gate 只以 `deploy/oa/README.md` 为 runbook，本模块不复制第二套操作步骤。

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
- ACL 安全：preflight/cleanup/cutover/post-deploy 必须绑定同一 candidate、approved artifact/hash 和 safe fingerprint；APP session/API 与 fresh OA router/role restore 必须分别 read-back。

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

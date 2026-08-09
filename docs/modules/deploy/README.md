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

## 当前边界

生产发布入口是：

```bash
./scripts/deploy-oa.sh
```

默认生产路径是 release-based 部署，不直接覆盖 `/opt/fin-ops/current/backend`：

1. 本地构建 `web/dist`，打包 `backend + web/dist + scripts + deploy/oa`。
2. 上传到 `/opt/fin-ops/releases/<release-name>/src`。
3. 远端先执行 deploy-control contract check、release layout check、storage preflight、`check-release`。
4. 激活前由 root-owned `finops-deploy-control` 计算 candidate schema plan；存在 pending migration 时必须先验真“上一 release 代码 + 每个候选中间 schema head”的 PostgreSQL 写入证据。证据缺失时在停止服务、执行 migration 前失败关闭。
5. 通过兼容门禁后执行依赖安装、PostgreSQL migration、legacy current archive、systemd drop-in、runtime worker ensure、frontend publish、service restart、worker readiness wait。
6. 发布脚本等待本机 `/health/ready`，再检查公网 `/fin-ops-api/api/session/me` 和 `/fin-ops/api/session/me` 都作为 JSON API 被代理。
7. 旧 release 默认保留最近 4 个，并保护 active release references。

旧覆盖式 `legacy-current` deploy mode 已移除；`scripts/deploy-oa.sh` 不再接受 `--mode`，
也不再生成覆盖 `/www/wwwroot/fin-ops/dist` 或 `/opt/fin-ops/current/backend` 的 payload。
runtime env 事实源是 `deploy/oa/env/*.env.example` 和生产 `/etc/fin-ops/*` split env，
不再维护仓库根部单文件 `deploy/oa/fin_ops.env.example`。

Nightly CI 入口是：

```bash
bash scripts/verify.sh all
```

它覆盖后端 `--check`、后端 unittest discovery、前端 Vitest、前端 build、deterministic Playwright browser smoke、docs 结构检查。

## 自动发布风险门禁

- `release-gate-profile` 比较 exact candidate 与当前唯一 active release 的实际包内容，自动判定 `frontend`、`runtime`、`acl`；没有手工 profile 或 skip 参数，无法证明纯前端时 fail-safe 为 `runtime`。
- 三类发布都要求 exact SHA/fingerprint、strict runtime env、required worker inventory、`YNSYLP005` admin session、原子激活和 release evidence；标准激活不读取或要求 `YNSYLP006`。
- `frontend` 只执行 pre/T+0 的 ready、005 session、公开 shell/asset、发布目录哈希和 active release 检查，不执行 RabbitMQ topology apply、全页面 canonical audit、read-model smoke 或 T+60/T+300 等待。切换前固定捕获已通过 preflight 的 active worker 集合，切换与回退都必须重启同一集合，不得在 stop 之后重新从 active 状态推导。
- `runtime` 保留 production-equivalent pre/T+0/T+60/T+300；`acl` 使用相同的 005-only 门禁，并在失败后保持 maintenance、仅允许 forward repair。
- `RELEASE.json.schema_contract` 绑定候选 migration count/head/fingerprint。无 pending migration 时沿用原快速路径；有 pending migration 时只接受与 exact candidate、exact previous、PostgreSQL major、全部中间 schema heads 及固定写操作矩阵一致的 root-owned evidence。候选失败后若该证据缺失或漂移，禁止激活 previous binary，生产保持 maintenance 并 forward repair。
- 三项 retired admission env 和 legacy admin env 已完成一次性清理；稳态发布只读断言它们缺席。历史 OA non-dedicated binding cleanup/rollback SQL 与激活代码已经删除，migration 0132/0133 作为不可变历史保留。
- release 上传不得更新 root helper。deploy-control 变更仍使用 candidate hash-pinned、同文件系统 temp + atomic `mv` bootstrap；禁止 `self-update`。

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
- ACL 安全：真正的鉴权、权限 route/service、OA role sync 或 ACL migration 变更才分类为 `acl`；标准激活仍只验证 005、strict env、migration/CHECK、数据库 guard 与完整 runtime closure。005/006 双身份 preflight/post-deploy 保留为显式专项验收工具，不再是任何发布的激活前置条件。

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

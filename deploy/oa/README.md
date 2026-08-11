# OA 同域部署与联调说明

日期：2026-04-07

## 目标

把 `fin-ops-platform` 作为 OA 域下的受控子系统部署，并满足：

- 前端页面挂载在 `/fin-ops/`
- Python 后端挂载在 `/fin-ops-api/`
- 页面通过 OA 菜单 iframe 进入
- 直接复用 OA 的 `Admin-Token`
- 账户按“不可见 / 只读导出 / 全操作 / 管理员”分层
- 菜单可见性与 app 内权限模型保持同步

## 部署路径约定

- OA 主系统：`https://www.yn-sourcing.com/oa`
- fin-ops 前端：`https://www.yn-sourcing.com/fin-ops/`
- fin-ops 后端：`https://www.yn-sourcing.com/fin-ops-api/`
- OA 菜单内链：`https://www.yn-sourcing.com/fin-ops/?embedded=oa`

这两个子路径不要改成别的前缀。当前前端构建、iframe 嵌入态、菜单载荷和文档都已经按这组路径对齐。

## 同域部署原因

这套方案必须优先走同域部署，而不是跨域独立域名。

原因：

- 浏览器能直接携带 OA 的 `Admin-Token` cookie
- `fin-ops` 前端可以从同域 cookie 中读取 `Admin-Token`
- 前端请求 `/api/session/me` 时会自动带 `Authorization: Bearer ...`
- iframe、下载、跳转和会话失效处理都更简单

如果改成不同域名，需要额外处理：

- cookie 域共享
- iframe 跨域限制
- token 透传
- 下载与登出失效行为

不建议作为第一阶段方案。

## 账户类型与同步总规则

从 `2026-04-07` 开始，真实口径不再是“只有一个 `finops:app:view` 权限”。

现在必须同时维护：

1. OA 菜单是否可见
2. app 内是否允许访问
3. app 内是只读导出还是全操作
4. 是否是唯一管理员 `YNSYLP005`

统一规则如下：

| 账户类型 | OA 菜单 | app 访问 | app 写操作 | 权限管理 |
| --- | --- | --- | --- | --- |
| 不可见用户 | 不可见 | 不可访问 | 不允许 | 不允许 |
| 只读导出用户 | 可见 | 可访问 | 不允许 | 不允许 |
| 全操作用户 | 可见 | 可访问 | 允许 | 不允许 |
| 管理员 `YNSYLP005` | 可见 | 可访问 | 允许 | 允许 |

运行时存储与 OA 同步规则：

- `allowed_usernames`：所有可访问账户的并集
- `readonly_export_usernames`：只读导出账户子集
- `admin_usernames`：第一阶段固定只允许 `YNSYLP005`
- `full_access_usernames`：由后端自动推导，不单独保存

强制要求：

- `allowed_usernames` 之外的账户，必须同时从 OA 菜单角色中移除
- `readonly_export_usernames` 与全操作用户都属于可访问账户
- `YNSYLP005` 必须同时存在于：
  - OA 可见角色
  - app `allowed_usernames`
  - app `admin_usernames`

## OA 菜单可见性角色建议

推荐在 OA 中准备三类角色，并全部绑定同一个 `财务运营平台` 菜单：

- `finops_read_export`
  - 只负责“在 OA 看得见并能进入”
- `finops_full_access`
  - 负责普通全操作用户的菜单可见性
- `finops_admin`
  - 负责管理员 `YNSYLP005`

说明：

- 这三个角色都应绑定 `finops:app:view` 对应菜单
- 是否是只读 / 全操作 / 管理员，最终仍以 `fin-ops` 后端运行时判断为准
- OA 菜单层只负责“看不看得见入口”

已提供模板：

- `deploy/oa/fin_ops_user_role_sync.mysql.sql`

## OA token 复用链路

当前代码已经按这条链路工作：

1. 用户先登录 OA
2. OA 域下存在 `Admin-Token`
3. `fin-ops` 前端读取该 cookie
4. 前端调用 `/api/session/me` 和其他 `/api/*` 时，自动加：
   - `Authorization: Bearer ${Admin-Token}`
5. `fin-ops` 后端调用 OA 的 `/system/user/getInfo`
6. 后端解析当前用户、角色、权限
7. 后端要求具备 `finops:app:view`
8. 无权限时：
   - `/api/session/me` 返回 `allowed = false`
   - 其他核心 API 返回 `403`

当前代码不依赖自己发 token，也不需要额外登录页。

## fin-ops 部署环境变量

以下是 OA 集成链路必须确认的环境变量：

```bash
FIN_OPS_OA_BASE_URL=https://oa.company.com
FIN_OPS_OA_USER_INFO_PATH=/system/user/getInfo
FIN_OPS_OA_LOGIN_PATH=/auth/login
FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view
FIN_OPS_OA_REQUEST_TIMEOUT_MS=5000
FIN_OPS_OA_LOGIN_REQUEST_TIMEOUT_MS=5000
FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS=30
FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY=<root-only long random secret>
FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY=<OA login public key PEM or base64 DER>
FIN_OPS_OA_PAYMENT_STATUS_ENABLED=0
FIN_OPS_OA_PAYMENT_STATUS_HOST=127.0.0.1
FIN_OPS_OA_PAYMENT_STATUS_PORT=3306
FIN_OPS_OA_PAYMENT_STATUS_DATABASE=smart_oa
FIN_OPS_OA_PAYMENT_STATUS_USERNAME=<least-privilege mysql user>
FIN_OPS_OA_PAYMENT_STATUS_PASSWORD=<least-privilege mysql password>
FIN_OPS_OA_PAYMENT_STATUS_CONNECT_TIMEOUT_SECONDS=5
FIN_OPS_PROMETHEUS_BEARER_TOKEN=<root-only long random metrics token>
VITE_APP_BASE_PATH=/fin-ops/
```

补充说明：

- `FIN_OPS_OA_BASE_URL` 必须指向 OA 网关对外地址
- `finops-deploy-control check-release` 会在发布前校验 PostgreSQL DSN 以及
  `FIN_OPS_OA_BASE_URL / FIN_OPS_OA_USER_INFO_PATH / FIN_OPS_OA_REQUIRED_PERMISSION` 和 OA role sync，
  缺任一项都会停止发布，避免上线后才出现“未配置 OA 用户信息服务地址”
- `FIN_OPS_OA_REQUIRED_PERMISSION` 必须精确为 `finops:app:view`，它只定位 OA 菜单，不授予 APP 权限
- `FIN_OPS_OA_LOGIN_PATH` 默认 `/auth/login`；`创建 OA 草稿` 会用目标 OA 申请人的账号密码登录 OA，并用返回 token 创建 `isDraft=true` 草稿
- `FIN_OPS_OA_APPLICANT_CREDENTIAL_KEY` 用于 PostgreSQL `pgcrypto` 加密/解密目标 OA 申请人密码，必须放在 root-only secret env，且上线后保持稳定，轮换前需要先设计迁移方案
- `FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY` 是 OA 登录接口使用的 RSA 公钥，可配置 PEM 或 base64 DER；后端登录目标申请人前会用该公钥加密密码，不发送明文密码
- 服务器 runtime 必须能执行 `openssl`，用于目标申请人登录密码 RSA 加密；缺失时 `创建 OA 草稿` 会返回目标 OA 登录不可用
- `FIN_OPS_OA_PAYMENT_STATUS_*` 用于进行中 OA “确认已支付”写回 OA MySQL `t_payment_simple`。2026-06-17 实机验证显示 `t_payment_simple.flow_id` 对应 OA Mongo `form_data._id`，不是 Flowable `PROC_INST_ID_`。应用正常运行时直接通过 MySQL 连接写回，不需要 SSH 登录 OA 服务器；如果 MySQL 只允许服务器本机访问，应将 app 部署在可访问该 MySQL 的同机/内网，或配置受控隧道/专用网络。未启用时页面仍可读取 OA 待付款数据，但 confirm-paid 会返回写回未配置。
- `FIN_OPS_ALLOWED_USERNAMES / FIN_OPS_ALLOWED_ROLES / FIN_OPS_READONLY_EXPORT_USERNAMES` 已退休；
  新 runtime 的 strict contract 要求三项及 legacy admin env 全部缺席。升级旧 runtime 时，read-only preflight
  只允许这三个精确 retired key，以及 legacy admin 恰好为空或仅为固定 `YNSYLP005`；它们会在 current-runtime
  checkpoint 通过后、停止旧进程前按 before-image 原子清除，不能作为候选 runtime 的 APP admission。APP
  admission 只来自 Settings ACL；管理员固定为 `YNSYLP005`，不接受环境变量或普通 settings payload 覆盖
- `FIN_OPS_TEST_DEFAULT_AUTH / FIN_OPS_DEV_ALLOW_LOCAL_SESSION / FIN_OPS_DEV_USERNAME / FIN_OPS_DEV_OA_PASSWORD` 已退休且运行时完全不读取；即使遗留配置存在，也不能创建登录态或授予管理员权限。运行时不存在本地固定 token 或默认数据重置密码。
- `FIN_OPS_PROMETHEUS_BEARER_TOKEN` 用于 `/metrics` Prometheus scrape；未配置时 `/metrics`
  返回 `404`，配置后必须带 `Authorization: Bearer <token>`
- 如果希望“访问账户管理”保存后自动同步 OA 菜单角色，还需要配置：
  - `FIN_OPS_OA_ROLE_SYNC_ENABLED=1`
  - `FIN_OPS_OA_ROLE_SYNC_HOST / PORT / DATABASE / USERNAME / PASSWORD`
  - `FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS=5`
  - `FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS=10`
  - `FIN_OPS_OA_ROLE_SYNC_WRITE_TIMEOUT_SECONDS=10`
  - `FIN_OPS_OA_ROLE_SYNC_READONLY_ROLE_KEY / FULL_ACCESS_ROLE_KEY / ADMIN_ROLE_KEY`
- `VITE_APP_BASE_PATH` 必须是 `/fin-ops/`
- 业务数据相关的 Mongo 配置仍按现有 `fin-ops` 运行说明提供，不在这里重复展开

仓库里已补充一份环境变量模板：

- `deploy/oa/env/fin-ops.common.env.example`
- `deploy/oa/env/fin-ops.secrets.env.example`
- `deploy/oa/env/fin-ops.postgres-migrator.env.example`
- `deploy/oa/env/fin-ops.worker.oa-sync.env.example`
- `deploy/oa/env/fin-ops.worker.workbench.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-*.env.example`

## 生产 Browser Route-Shell Smoke Bundle

生产 route-shell browser smoke 使用独立 runner 输入，不属于 OA app release archive。需要准备 bundle 时，在本地执行：

```bash
python3 scripts/package_production_browser_smoke.py \
  --release-name <active-release-name> \
  --output /tmp/fin-ops-production-browser-smoke.tar.gz
```

该 bundle 只包含批准的生产 route-shell spec、strict diagnostics fixture、Playwright 配置、package metadata/lockfile 和 manifest。它不包含 `web/dist`、`node_modules`、Playwright browser binaries、admin production spec、截图、trace、video、HTML report、token、cookie 或 secret env。生成 bundle 不会上传、部署、安装依赖、下载浏览器、登录 OA 或访问生产。

正常 OA release 仍由 `scripts/deploy_oa.py` 打包 backend、`web/dist`、scripts、deploy helpers 和选定根文档；不要为了 browser smoke 修改正常 release archive 去携带 `web/e2e`、`node_modules` 或浏览器二进制。真正执行生产 browser evidence 前，必须先有独立 runner runtime、内存 token broker、脱敏 artifact contract，以及执行前后的 `/health/ready`、dirty scope、App Status readiness、read-model outbox 和 dead-letter 聚合检查。

### OA 支付状态 MySQL 写回解锁

生产启用“进行中 OA 确认已支付”前，必须由 DBA 或具备 MySQL 管理权限的运维账号创建最小权限用户。不要复用 SSH 密码、宝塔面板密码或 PostgreSQL 密码作为 MySQL 应用密码。

2026-06-17 文件层检查确认当前生产 MySQL datadir 下存在 `smart_oa/t_payment_simple.ibd`，因此目标库名按 `smart_oa` 配置；如果后续迁移数据库，先重新执行表定位查询：

```sql
SELECT table_schema
FROM information_schema.tables
WHERE table_name = 't_payment_simple'
ORDER BY table_schema;
```

推荐授权方式：

```sql
CREATE USER 'finops_oa_payment_status'@'127.0.0.1'
  IDENTIFIED BY '<long-random-password>';

GRANT SELECT,
      INSERT (flow_id, pay_status),
      UPDATE (pay_status)
ON `smart_oa`.`t_payment_simple`
TO 'finops_oa_payment_status'@'127.0.0.1';
```

写入 root-only secret env：

```bash
sudoedit /etc/fin-ops/fin-ops.secrets.env
```

```bash
FIN_OPS_OA_PAYMENT_STATUS_ENABLED=1
FIN_OPS_OA_PAYMENT_STATUS_HOST=127.0.0.1
FIN_OPS_OA_PAYMENT_STATUS_PORT=3306
FIN_OPS_OA_PAYMENT_STATUS_DATABASE=smart_oa
FIN_OPS_OA_PAYMENT_STATUS_USERNAME=finops_oa_payment_status
FIN_OPS_OA_PAYMENT_STATUS_PASSWORD=<long-random-password>
FIN_OPS_OA_PAYMENT_STATUS_CONNECT_TIMEOUT_SECONDS=5
```

配置后重启 API，使 `MySQLOAPaymentStatusRepository.from_environment()` 重新读取环境变量：

```bash
sudo -n /usr/local/sbin/finops-deploy-control restart
```

只读连通性 smoke 不应输出密码；可用一个不存在的 sentinel `flow_id` 验证连接、表权限和读取路径：

```bash
set -a
source /etc/fin-ops/fin-ops.common.env
source /etc/fin-ops/fin-ops.secrets.env
set +a
release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
cd "$release_src"
PYTHONPATH="$release_src/backend/src" /opt/fin-ops/venv/bin/python - <<'PY'
import json
from fin_ops_platform.services.oa_payment_status_service import MySQLOAPaymentStatusRepository

repo = MySQLOAPaymentStatusRepository.from_environment()
payload = {"configured": repo is not None, "read_ok": False}
if repo is not None:
    payload["sentinel_found"] = repo.get_payment_status("__finops_payment_status_probe__") is not None
    payload["read_ok"] = True
print(json.dumps(payload, ensure_ascii=False))
PY
```

最终生产闭环必须使用一条真实非敏感进行中 OA：确认支出流水后核对 `t_payment_simple.flow_id=<OA Mongo form_data._id>` 的最新记录 `pay_status=1`，同时页面行显示 `oaPaymentWriteback.label=已写回`。

systemd 模板位于：

- `deploy/oa/systemd/fin-ops.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`
- `deploy/oa/systemd/finops-prune-runtime-queue-history.service.example`
- `deploy/oa/systemd/finops-prune-runtime-queue-history.timer.example`
- `deploy/oa/systemd/finops-enqueue-oa-sync.service.example`
- `deploy/oa/systemd/finops-enqueue-oa-sync.timer.example`

这些 `.service.example` 中的 `REPLACE_WITH_RELEASE` 只是 bootstrap 占位；标准发布只允许由
`finops-deploy-control release-gate-activate` 的内部受控激活阶段写入 `99-deploy-release.conf`，把 API、worker 和 dispatcher 指向
实际 `/opt/fin-ops/releases/<release>/src`。不要把 systemd unit 重新指回旧
`/opt/fin-ops/current/backend`。

关联台自动配对必须单独启用 `workbench-matching` worker。它消费
`job.workbench_matching_dirty_scopes`，批量读取 canonical OA、流水、发票和 active relation，
仅把满足确定性安全规则的结果通过 Workbench relation UoW 写成正式 active relation；不生成或读取
候选/decision 状态。`workbench-read-model` worker 只负责把 active relation 与逐条未配对事实投影到
页面读模型，不能替代自动配对。
生产实例配置示例：

- `deploy/oa/env/fin-ops.worker.workbench-matching.env.example`

该实例使用 `0.25s` idle poll；ETC business-batch status 与 completed OA canonical 变化可用零 debounce 标记 exact dirty scope，其他 matching 事件继续使用默认 debounce。它仍是同一个 PostgreSQL durable dirty-scope worker，不新增 lane 或旁路写入。

生产部署时，API、worker、RabbitMQ dispatcher 和 RabbitMQ topology bootstrap 应使用不同的 `EnvironmentFile`。`FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`、`RABBITMQ_URL`、Redis、MinIO/S3 和 OA role sync 密码只能放在服务器 root-only secret 文件中，不要写入仓库模板或 systemd inline `Environment=`。migrator DSN 只能用于手动/受控 migration，不要加载到 API 或 worker unit。

发布激活会安装一个版本化 retention timer 和一个 OA sync enqueue timer：

- `finops-prune-runtime-queue-history.timer`：清理 `job.outbox_events` /
  `job.read_model_dirty_scopes` 的完成态历史。默认 `keep_days=30`、
  `keep_recent_per_type=512`、`limit=20000`，只删除 `status='done'`，并为每个 exact
  dirty scope 保留最新 done source_version；helper 读取
  `/etc/fin-ops/fin-ops.postgres-migrator.env`，不扩大 API/worker delete 权限。
- `finops-enqueue-oa-sync.timer`：默认每 5 分钟 enqueue 一条 durable
  `oa.sync` / `scope=all` 事件；实际 Mongo 读取仍由 `worker-oa-sync` 执行。

PostgreSQL migration 示例：

```bash
sudo install -m 0600 -o root -g root \
  deploy/oa/env/fin-ops.postgres-migrator.env.example \
  /etc/fin-ops/fin-ops.postgres-migrator.env
sudoedit /etc/fin-ops/fin-ops.postgres-migrator.env

set -a
source /etc/fin-ops/fin-ops.postgres-migrator.env
set +a

release_src="$(systemctl show fin-ops.service -P WorkingDirectory)"
PYTHONPATH="$release_src/backend/src" \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.postgres apply
```

RabbitMQ 切换不是发布脚本的默认副作用。先保持 `FIN_OPS_QUEUE_BACKEND=postgres`，完成 topology apply 和 dispatcher shadow publish 观察，再按 worker 族灰度到 `FIN_OPS_QUEUE_BACKEND=rabbitmq`。完整 topology 只覆盖 runtime worker registry 中声明的 RabbitMQ eligible event；生产发布范围由 `RABBITMQ_DISPATCH_EVENT_TYPES` 控制。运行前置检查见 `docs/operations/postgresql-runtime.md`，worker/read model 运维口径见 `docs/operations/runtime-worker-governance.md`。

RabbitMQ 生产 env 拆分：

- `/etc/fin-ops/fin-ops.rabbitmq-topology.env`：bootstrap-only，用于 `rabbitmq_topology --apply`，不加载到 API 或 worker。
- `/etc/fin-ops/fin-ops.rabbitmq-dispatcher.env`：dispatcher shadow publish/real publish 配置。同步 SLO 发布默认
  `RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.5`，避免 outbox 写入后最多等待 5 秒才投递到 RabbitMQ；
  如生产需要临时降频，可在该 env 文件中覆盖，但必须用 `rabbitmq_dispatcher_lag_seconds` 和
  read model enqueue-to-fresh smoke 证明仍满足页面 SLO。
- `/etc/fin-ops/fin-ops.rabbitmq-monitoring.env`：API 只读 management metrics 配置。
- `/etc/fin-ops/fin-ops.rabbitmq-worker.env`：worker consumer 共享 `RABBITMQ_URL` 凭据；该文件不得设置 `FIN_OPS_QUEUE_BACKEND`。
- `/etc/fin-ops/fin-ops.worker.<instance>.env`：单 worker 实例配置。只有灰度到 RabbitMQ 的实例才把本文件切为 `FIN_OPS_QUEUE_BACKEND=rabbitmq`。

最小生产正确性不依赖 RabbitMQ。标准 release 发布会通过服务器 root-owned helper
`/usr/local/sbin/finops-ensure-runtime-workers`，安装/更新 worker systemd 模板，补齐缺失的
worker env，并启用、重启 registry 声明的 required worker。仓库内的
`deploy/oa/bin/finops-ensure-runtime-workers.sh` 是该 helper 的源文件，不能由 `finops-deploy`
从 release 目录直接 `sudo /bin/bash` 执行，也不能在每次 release 发布中用原始 `sudo install`
覆盖 `/usr/local/sbin`；helper 安装/升级属于一次性 bootstrap 或受控运维动作，release 发布只校验
已安装 helper 的合同并调用固定 helper：

worker 实例、event types、env 模板和 smoke check 命令均从
`python -m fin_ops_platform.tools.runtime_worker_manifest` 推导。不要在生产 runbook 中维护第二份
worker 清单；新增 worker 或 read model refresh event 时先改 registry，再让部署和监控从 registry
收敛。完整运维口径见 `docs/operations/runtime-worker-governance.md`。

这些实例分别加载 `/etc/fin-ops/fin-ops.worker.<instance>.env`。如果仍使用
PostgreSQL polling，这些文件应保持 `FIN_OPS_QUEUE_BACKEND=postgres`。

生产 systemd worker 使用 registration contract：

```bash
python -m fin_ops_platform.app.worker \
  --registration <instance> \
  --worker-instance <instance>
```

发布激活阶段会在服务重启后等待 `/health/ready` 同时返回 HTTP 200 和 `status=ready`；HTTP 503
表示 PostgreSQL、必需 worker、critical read model 或 release/runtime guard 仍有权威 blocker。systemd
active 只代表进程存在，不代表 API 已经加载正确 release identity 和 readiness 边界。

## 一键发布脚本

仓库根目录已提供一套只发布 `fin-ops`、不触碰 OA 源码的一键发布脚本。默认路径是 release-based 部署：

```bash
./scripts/deploy-oa.sh
```

脚本会完成：

- 本地重新构建 `web/dist`
- 打包生产运行所需的 `backend + web/dist + scripts + deploy/oa`
- 生成 `src/RELEASE.json`，记录 release 名称、Git commit、分支、`settings-access-control-v1` capability、0133 migration sha256、deploy-control sha256，以及全量 PostgreSQL migration count/head/fingerprint
- 通过 `finops-prod` 免密 SSH 推送到：
  - `/opt/fin-ops/releases/<release-name>/src`
- release 上传路径不自更新 `/usr/local/sbin`。deploy-control 变更必须使用下文 hash-pinned、同文件系统 temp、`mv -f` 原子 bootstrap；禁止旧 `self-update`，也禁止在 bootstrap 中触碰 runtime-worker helper
- 调用服务器 root-owned helper：
  - `/usr/local/sbin/finops-deploy-control check-release <release-name>`
  - `/usr/local/sbin/finops-deploy-control release-gate-activate <release-name>`
- `check-release` 会在隔离临时 venv 中安装锁定的 `backend/requirements-audit.txt`，审计候选 `backend/requirements.txt`；存在已知漏洞或审计失败时停止发布，审计工具不进入 API/worker runtime venv。
- `schema-compatibility-plan` 只读生产 `public.schema_migrations`，验真候选包内 migration fingerprint、checksum 和生产 applied head。无 pending migration 时不要求额外 evidence；有 pending migration 时，必须先在 disposable PostgreSQL 上用 exact previous release 代码逐个验证每个候选中间 schema head，并通过 `schema-compatibility-evidence-install <release> --stdin` 安装绑定 exact plan 的 root-owned `0600` 证据。固定探针覆盖已有发票/流水 upsert、import enrichment、settings reset、correction 与 audit 同事务。
- `release-gate-activate` 是唯一正常激活入口；公开 `activate` 命令已删除。helper 比较 exact candidate 与唯一 active release 的实际包内容，自动判定 `frontend`、`runtime` 或 `acl`，没有手工 profile/skip。所有 profile 的标准激活都只读取 005，不读取 006，也不依赖双身份 artifact。`runtime`/`acl` 先对当前 release
  执行 production-equivalent pre checkpoint，再用 `/etc/fin-ops/fin-ops.postgres-migrator.env`
  停止旧 API 和 runtime workers，执行 PostgreSQL schema migration/validated CHECK，
  成功后才激活 API、RabbitMQ worker 和 dispatcher 指向该 release；`frontend` 只原子发布候选 dist 并重启已有 runtime。重启前都会以 release registry
  为白名单 stop/disable 已启用、运行或失败的未注册 `fin-ops-worker@*.service`，避免历史/WIP unit
  继续消费队列或 crash-loop。该动作不删除实例 env，保留受控回滚能力
- API 和 dispatcher release drop-in 会先清空基础 unit 继承的 `EnvironmentFile`，再加载
  `/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env`，避免历史
  `/opt/fin-ops/fin-ops.env` 覆盖 release `PYTHONPATH` 导致新服务仍导入 `/opt/fin-ops/current`
  旧代码
- API drop-in 固定创建 `/run/fin-ops`；包含 `app/wsgi.py` 与 `app/gunicorn_conf.py` 的 release
  使用 Gunicorn，回滚到不包含这两个模块的历史 release 时只对该目标 release 恢复其原生
  `app.main` 启动入口。API drop-in 损坏时仅允许执行无参数的 `repair-active-api-runtime`，该命令
  只重写当前唯一 active release 的 API drop-in 并验证 readiness，不能指定或激活其它 release
- 门禁内部受控激活阶段会把历史 `/opt/fin-ops/current` 归档到 `/opt/fin-ops/legacy-current-archives/current-<timestamp>`；
  release 模式只允许从 `/opt/fin-ops/releases/<release-name>/src` 运行，`current` 目录不再参与运行时
- `/health` 是轻量 liveness，暴露 runtime identity，包括工作目录、实际 `fin_ops_platform.__file__`、
  `PYTHONPATH` 和 `RELEASE.json`，不会跑 workbench read model self-test；release 运行时若实际导入路径
  不在当前 release 的 `backend/src` 下，健康状态必须是 `not_ready`
- `/health/ready` 是部署 readiness 边界；`/health/deep` 才执行较重的 workbench API self-test，
  不作为发布脚本的快速就绪检查
- 门禁内部通过 `/usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/<release-name>/src`
  确保常驻 worker 矩阵已安装、开机自启并重启到当前 release；外层发布脚本不再重复调用该 helper
- 验证前端 `index.html` 与激活 release 的 `web/dist/index.html` 哈希一致
- 清理可删除的旧 release，默认保留最近 4 个，并始终保护当前 active release
- 激活发布会在创建新 release 目录前先执行一次旧 release 清理，并检查 release 所在文件系统至少有
  512MB 可用空间；空间不足时会输出 `df` 和关键目录大小后停止，不会继续解包到半失败状态
- `runtime`/`acl` 激活前运行 `preflight`：用候选 gate 代码检查当前 stable runtime、worker/queue/RabbitMQ 收敛、
  隔离 PostgreSQL 可逆写探针和只读页面 canonical audit，不执行业务 mutation。候选 gate 读取旧
  stable API 时，完整 registry 可作为候选 registry 的无重复保序严格子集，以覆盖候选新增页面及 migration
  尚未激活的窗口，但响应 summary、system page 与逐页 proof 必须对该旧 registry 完全自洽；未知页面、字段
  部分缺失、顺序漂移或 proof 不完整仍 fail closed。T+0 起恢复候选 registry exact match，不再接受子集
- `preflight` 的 worker readiness 使用当前 stable release 的 required worker inventory；新增 required
  worker 由激活阶段的 ensure helper 安装，并从 T+0 起按候选 registry 严格校验，避免候选 registry 在
  激活前把尚未部署的新 worker 误报为旧 runtime 故障
- `runtime`/`acl` 候选激活后 T+0 运行只读 `stability`：连接真实 PostgreSQL 与 RabbitMQ，检查 exact worker inventory、
  queue/dirty/dead-letter 收敛、真实页面 read-model freshness、隔离事务写入能力、domain/page canonical
  audit 及 API/health 性能。自动发布门禁不 enqueue synthetic read-model refresh；workbench 的 active generation
  是全局原子发布边界，局部 smoke scope 不能污染 `month=all` 等真实页面 scope
- `runtime`/`acl` 在 T+60s、T+300s 继续运行只读 `stability`：重跑性能、domain audit 和 runtime 收敛检查，
  不 enqueue read-model smoke，也不执行 confirm/withdraw；单个无错误、fresh、p99
  合格但 p95 超标的三样本窗口只允许重采样一次，第二个窗口仍超标即失败。最终证据以 T+300 证明异步拓扑持续稳定
- `frontend` 只执行 pre/T+0 的 exact dist、active release、worker inventory、ready、005 session 和公开 shell/首个 hashed asset；不执行 RabbitMQ apply、runtime closure、page audit 或 T+60/T+300 等待
- 页面 shell 探针固定使用公开站点 origin；API 探针固定使用当前 release 的内部服务 origin，
  防止内部地址页面 404 或公开 Nginx fallback 被误判为业务 API 结果
- 自动 release gate 不读取受控业务 scenario、standing approval，也不修改真实业务关系。隔离写探针只在
  当前 PostgreSQL 连接的 `pg_temp` 临时表内执行 insert/read/delete/rollback，不接触 canonical facts、
  relation、read model、outbox 或 dirty scope
- 固定 `test_owned` 可逆业务 scenario 只保留为显式 operator 工具，不属于自动激活门禁
- 更新标准 scenario 时先把候选文件放到
  `/tmp/finops-write-e2e-<run-id>.json`，再执行
  `sudo /usr/local/sbin/finops-deploy-control write-operation-e2e-scenario-install <release-name> <temporary-scenario-path>`。
  helper 使用候选 release 的严格合同校验后原子安装 root-owned `0600` 文件，并保留一份 `.previous`；
  不允许直接覆盖标准 scenario、跟随符号链接或绕过候选代码校验
- runtime health 在 canonical audit 之前完成收敛；`stability` 还要在所有检查完成后
  之后再次采样。canonical audit 始终作为每个 checkpoint 的最终只读证明，保证它看到的是 durable
  queue、dirty scope、worker 与 dead-letter 已收敛的状态。closure gate 允许幂等收敛一次已完成的
  durable publish 终态，但必须记录
  reconciliation 并在同一 checkpoint 内再取得一个无残留、无再次 reconciliation 的干净采样；持续复发
  按 dispatcher/状态机故障 fail closed，部署 shell 不得在 gate 外隐式清理
- 门禁按 systemd 的既有边界分别加载 `/etc/fin-ops/fin-ops.rabbitmq-topology.env` 与
  `/etc/fin-ops/fin-ops.rabbitmq-monitoring.env`，任一缺失或不可读都 fail closed
- 最终 PASS evidence 写入
  `/opt/fin-ops/runtime-smoke/release-gates/<release-name>/evidence.json`，绑定 release 与 Git commit；
  `frontend`/`runtime` 失败只有在 schema 未前移，或 previous release 已通过 exact candidate schema（包含全部中间 migration head）兼容证据时才可自动恢复；否则保持 API maintenance/fail-closed 并 forward repair，绝不启动未证明兼容的新 schema/旧 binary 组合。`acl` 失败继续只允许 forward repair。pre checkpoint 失败不改任何 helper

常用参数：

```bash
./scripts/deploy-oa.sh --dry-run
./scripts/deploy-oa.sh --skip-build
./scripts/deploy-oa.sh --release-name main-abcdef12-20260524170000
./scripts/deploy-oa.sh --no-activate
./scripts/deploy-oa.sh --activate-existing --release-name main-abcdef12-20260524170000
./scripts/deploy-oa.sh --keep-releases 12
./scripts/deploy-oa.sh --remote-min-free-mb 1024
```

生产修复需要读取 `/etc/fin-ops` runtime env 时，不要把 DB secret 暴露给
`finops-deploy`，也不要手写 SQL 改 `job.read_model_dirty_scopes`。先确认 active release 名称：

```bash
sudo /usr/local/sbin/finops-deploy-control status
```

然后通过 root-owned helper 运行受控命令：

```bash
sudo /usr/local/sbin/finops-deploy-control workbench-audit-identity <release-name> \
  --json \
  --limit 20
sudo /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --promote-oa-attachment-invoices --dry-run --json
sudo /usr/local/sbin/finops-deploy-control workbench-rehydrate <release-name> \
  --promote-oa-attachment-invoices --apply-repair --confirm-apply-oa-attachment-invoices \
  --expected-fingerprint <dry-run-candidate-fingerprint> --json
sudo /usr/local/sbin/finops-deploy-control workbench-requirement-repair <release-name> \
  --dry-run
sudo /usr/local/sbin/finops-deploy-control workbench-requirement-repair <release-name> \
  --execute \
  --expected-fingerprint <dry-run-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control workbench-requirement-repair <release-name> \
  --rollback-dry-run \
  --expected-fingerprint <executed-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control workbench-requirement-repair <release-name> \
  --rollback \
  --expected-fingerprint <executed-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control workbench-etc-summary-repair <release-name> \
  --case-id <case-id> --external-etc-batch-id <batch-id> --dry-run
sudo /usr/local/sbin/finops-deploy-control workbench-etc-summary-repair <release-name> \
  --case-id <case-id> --external-etc-batch-id <batch-id> \
  --execute --expected-fingerprint <dry-run-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control workbench-etc-summary-repair <release-name> \
  --case-id <case-id> --external-etc-batch-id <batch-id> \
  --rollback-dry-run --expected-fingerprint <executed-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control workbench-etc-summary-repair <release-name> \
  --case-id <case-id> --external-etc-batch-id <batch-id> \
  --rollback --expected-fingerprint <executed-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control batch-accounting-metadata-cleanup <release-name> \
  --dry-run
sudo /usr/local/sbin/finops-deploy-control batch-accounting-metadata-cleanup <release-name> \
  --execute \
  --expected-fingerprint <dry-run-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control batch-accounting-metadata-cleanup <release-name> \
  --rollback-dry-run \
  --expected-fingerprint <executed-source-fingerprint>
sudo /usr/local/sbin/finops-deploy-control batch-accounting-audit <release-name>
sudo /usr/local/sbin/finops-deploy-control batch-accounting-read-smoke <release-name> \
  --bank-year <YYYY> --iterations 10
sudo /usr/local/sbin/finops-deploy-control workbench-matching-retry <release-name> \
  --scope-month <YYYY-MM> \
  --dry-run
sudo /usr/local/sbin/finops-deploy-control workbench-matching-retry <release-name> \
  --scope-month <YYYY-MM> \
  --execute \
  --expected-fingerprint <dry-run-fingerprint>
sudo /usr/local/sbin/finops-deploy-control etc-deleted-batch-restore <release-name> \
  --business-batch-id <id> --expected-invoice-count <n> --expected-total-amount <amount> \
  --expected-oa-row-id <oa-id> --dry-run
sudo /usr/local/sbin/finops-deploy-control etc-submitted-batch-member-repair <release-name> \
  --business-batch-id <id> --submission-batch-id <id> --external-etc-batch-id <id> \
  --invoice <invoice-number=plate> --expected-target-total <amount> \
  --expected-result-count <n> --expected-result-total <amount> --dry-run
sudo /usr/local/sbin/finops-deploy-control etc-batch-invoice-link-backfill <release-name> \
  --business-batch-id <id> --limit <n> --dry-run
sudo /usr/local/sbin/finops-deploy-control read-model-scope-contract <release-name> --json
sudo /usr/local/sbin/finops-deploy-control read-model-scope-contract <release-name> \
  --apply \
  --reason production_scope_contract_repair \
  --json
sudo /usr/local/sbin/finops-deploy-control read-model-slo-smoke <release-name> \
  --json \
  --critical-only \
  --target-ms 1000
sudo /usr/local/sbin/finops-deploy-control write-operation-restore-point <release-name> \
  <run-id>
sudo /usr/local/sbin/finops-deploy-control write-operation-restore-point-delete <run-id> \
  <expected-sha256>
sudo /usr/local/sbin/finops-deploy-control write-operation-e2e-smoke <release-name> \
  /tmp/finops-write-e2e-<run-id>.json --dry-run
sudo /usr/local/sbin/finops-deploy-control write-operation-e2e-smoke <release-name> \
  /opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json --apply-stdin 10
sudo /usr/local/sbin/finops-deploy-control api-request-error <request-id>
sudo /usr/local/sbin/finops-deploy-control api-request-trace <request-id>
sudo /usr/local/sbin/finops-deploy-control api-request-timing <request-id>
sudo /usr/local/sbin/finops-deploy-control read-model-refresh <release-name> \
  --scope workbench_relation=all --dry-run
sudo /usr/local/sbin/finops-deploy-control settings-normalize <release-name> --dry-run
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> --dry-run
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --batch-id <batch-id> --file-id <file-id>
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --retire-etc-session-id <session-id> [--retire-etc-session-id <session-id> ...]
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --normalize-reverted-batch-id <batch-id> [--normalize-reverted-batch-id <batch-id> ...]
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --discover-recover-import-job-id <job-id>
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --recover-import-job-id <job-id> --recover-event-id <event-id> \
  --recover-background-job-id <background-job-id> --recover-session-id <session-id> \
  --recover-file-id <file-id> [--recover-file-id <file-id> ...]
sudo /usr/local/sbin/finops-deploy-control import-audit-repair <release-name> \
  --dry-run --repair-bank-source <session-id>=<file-id>[,<file-id>...] \
  [--repair-bank-source <session-id>=<file-id>[,<file-id>...] ...] \
  --expected-bank-target-count <n> --expected-bank-protected-count <n> \
  --expected-bank-replay-create-count <n> --operator-id <operator>
sudo /usr/local/sbin/finops-deploy-control bank-transaction-category-repair <release-name> \
  --dry-run
sudo /usr/local/sbin/finops-deploy-control bank-transaction-category-repair <release-name> \
  --apply --operator <actor> --expected-candidate-count <dry-run-count>
sudo /usr/local/sbin/finops-deploy-control runtime-queue-resolve-covered <release-name> \
  --limit 100 --dry-run
```

`import-audit-repair` 只用于恢复已登记严格合同 import facts：先运行 `--dry-run` 保存
`source_fingerprint` 与 rollback manifest；确认期间数据未变化后，使用
`--execute --expected-fingerprint <source_fingerprint>`。fingerprint 不一致、batch owner 冲突、
来源明细冲突或 canonical owner 变化都会在事务写入前失败；禁止跳过 dry-run。
候选银行导入死信恢复模式必须在 dry-run 和 execute 中重复提供同一组完整 job/event/session/file
白名单。它只处理已知 `background_jobs_idempotency_uidx` 旧错误、仍为 untouched preview 且正式流水
为零的请求；候选 processor 完成并验证 batch/file/job 后才 resolve 原 dead letter，失败时保留原证据。
只知道失败 import job id 时，可先运行只读 `--discover-recover-import-job-id`；它只在唯一 dead letter、
payload 中完整 background job/session/file 坐标且全部预检通过时输出完整 target，不执行写入。
银行 identity v3 恢复模式必须在 dry-run/execute 中重复提供完整 source session/file、目标/保护 cohort
数量、预期重放新增数和 operator。dry-run 验证归档文件 SHA-256、cohort 精确不相交、业务指纹与官方
参考号唯一匹配、零核销及 OA/发票/标签/批次/关联关系零引用；execute 只把这些错误 created 行改为
引用原 canonical 的 duplicate、同步 batch/file 审计并删除错误副本，然后通过正式 preview/confirm processor
创建新恢复审计会话。任何关系、歧义、计数、owner、hash 或 fingerprint 漂移都在删除前失败；执行前必须
先创建动作绑定的生产恢复点，执行后相同源文件再次受控重放必须新增 0。
修复历史 batch/file 生命周期时，dry-run 与 execute 都必须同时传入同一组精确
`--batch-id` / `--file-id`；工具仅在 succeeded job、registered row counters、canonical invoice owner
和 `manual_invoice_import` source-link 全部闭环时允许把精确的 `pending/preview_ready` 降级态恢复为
`completed/confirmed`，并按 batch + source identity 一对一恢复被旧 preview 清空的 import row link。
它不修改 canonical invoice/source-link，不扫描或修改其它生命周期记录，也不重新发布 read model 事件。
当 ETC 对账任务已正式删除、导入 job/outbox 已完全收敛，但其严格导入 session 仍保留历史证据时，
可以显式重复传入精确 `--retire-etc-session-id`。工具只把这些 session 的审计 revision 原子标记为
`etc-import-page-audit.v1.deleted-task-retired`，不删除 session、ZIP 文件关系、对象文件或导入结果；
task 未处于 canonical/payload 双重 `deleted`、session 非稳定态、存在活动 job/outbox、目标缺失或指纹变化时一律拒绝。
该模式不得与 batch/file 生命周期修复组合，execute 仍必须复用同一 dry-run fingerprint。
历史 discard 若只写入 batch canonical `reverted` 而 formal payload 仍为 `pending`，必须显式传入
`--normalize-reverted-batch-id`。工具只在 strict file/session 已全部 reverted、无 active/succeeded job、
无 linked import row、无 canonical invoice/source-link 时把该 batch payload status 改为 `reverted`；
目标缺失、多义、状态漂移或 fingerprint 变化均在写前失败。该模式不得与其它 repair mode 组合。

`etc-submitted-batch-member-repair` 只用于已有 submitted ETC 批次的已证明缺失成员。dry-run 必须同时绑定
business/submission/external 三个 ID、全部精确发票号与车牌、目标/结果金额；execute 还必须传入同一
fingerprint、operator 和 reason。它只补 canonical ETC member/link、归一化原批次汇总并写审计，
不改 OA 草稿、已关闭对账任务或附件；完成后由既有 historical ETC lifecycle 让 Workbench 收敛。

`workbench-audit-identity` 只运行 `fin_ops_platform.tools.audit_object_identity`，
用于查看强身份跨区重复、OA alias 和孤儿关系样本。
`read-model-scope-contract` 只运行 release 内的 `scripts/check-read-model-scope-contracts.py`，
用于只读检查或受控清理 legacy/invalid read model scope。以上命令都只接受固定脚本/模块参数，
由 helper 加载 runtime env，不提供任意 shell 执行能力。
`workbench-requirement-repair` 修复普通银行正式关系缺失的冻结要求、active Turnover 旧 source/缺 tag/version，
以及“关系已冻结但之后发生了有持久化来源证据的 effective category 变更”造成的 snapshot drift。规则推导或
未知来源差异只进入 `manual_review_*` 报告，不自动写。dry-run 使用一次 fresh 银行标签批量读取，fingerprint 同时绑定
完整 metadata preimage 与 intended after；execute 通过 fingerprint-bound history 重建 original plan，支持
中断后幂等续跑。`rollback-dry-run` / `rollback` 只选择同 fingerprint 的 execute history，在首写前检查
after-image drift，并通过 `WorkbenchRelationCommandService` 原地精确恢复完整 `special_metadata` preimage；
不 cancel/recreate relation。ETC 与批量账务不在修复范围；命令不开放 SQL、任意脚本或常驻回扫。
`workbench-etc-summary-repair` 只修复一个明确 case 与 external ETC batch 的 durable relation marker。
dry-run 要求 active relation 精确包含由 batch ID 确定性生成的 invoice summary row，fingerprint 绑定
case、batch、scope、mode 和有序 row ids/types；冲突 marker、缺 summary 或类型不一致全部 fail closed。
execute/rollback 只走正式 relation command、history、idempotency 和 changed-case persistence，不修改
OA、流水、发票或 ETC canonical facts，也不开放通配扫描或 SQL。
`batch-accounting-metadata-cleanup` 只选择 active `relation_mode=batch_accounting` 且仍含
`bank_row_id`、`oa_row_ids`、`invoice_row_ids` 或旧 `year` alias 的关系。dry-run fingerprint 绑定完整
relation preimage 与清理后的 metadata；execute/rollback 复用正式 relation command、history 和
idempotency 边界，禁止 SQL 直写、cancel/recreate 或扫描其它 relation owner。
`read-model-slo-smoke` 只运行 release 内的 `fin_ops_platform.tools.read_model_slo_smoke` dry-run，
用于在不暴露 PostgreSQL DSN 的情况下发现 critical read model scopes；该 helper 明确拒绝 `--apply`，
真实 enqueue-to-fresh 只能在单独批准的 root session 中执行。
`write-operation-e2e-smoke` 只运行 release 内的固定 relation runner；scenario 接受 root-owned `0600`
标准文件 `/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json`，或受限 `/tmp` JSON，
并登记 `bank_flow_rule_batch` 的 submit -> withdraw -> resubmit 三个 checkpoint 与 inactive recovery；该 shape 只接受显式 `test_owned` 流水，最终必须恢复未提交状态。
apply 的 Admin Token 与 approval ticket 只从 stdin 的前两行读取，固定走公网 `/fin-ops-api`，
不提供任意命令或 SQL 能力；第二行为空时在任何业务写请求前失败。可选第四参数只接受 `1..20`
的 preview sample count（默认 1），只重复只读 canonical preview，不重复正式 mutation。standing correctness helper
将同步 relation 写响应门禁固定为 `5000ms`，exact receipt 绑定的异步 refresh 收敛门禁为
`30000ms`（总等待上限 `120s`），consumer HTTP 仍为 `1000ms`；三者是独立合同，该配置不构成
“所有页面一秒级真同步”的性能声明。
`api-request-error` 只接受 API 返回的 32 位小写十六进制 request ID，并按结构化 JSON
`request_id` 字段从最近两小时 `fin-ops.service` journal 返回匹配的单行异常摘要；它不开放任意
journal 参数或日志全文。
`api-request-trace` 使用同一严格 request ID，从该摘要开始最多返回 64 行，并在 traceback 的异常终止行
立即停止；它不包含 locals、不接受任意时间窗或 journal 参数，用于把生产 500 精确定位到文件和行号。
`api-request-timing` 使用同一 request ID，只返回最近两小时最多 32 条结构化
`workbench_action_timing` 记录；它不返回业务 payload，也不开放时间窗或 journal 参数。

Nginx 的 `/fin-ops-api/`、`/api/` 和兼容 `/fin-ops/api/` location 必须显式转发
`If-None-Match`。OA 待付款等页面依赖标准 ETag/304 快路径；若公网相同 ETag 仍返回
完整 `200`、而本机 API 返回 `304`，先对照 `nginx.fin-ops.conf.example` 修正 live location
并执行 `nginx -t` 后 reload，禁止在应用层增加自定义 query ETag 或旧 payload cache fallback。

说明：

- 这套脚本只发布 `fin-ops` 自己的前后端
- 不会改 OA Java/Vue 源码
- 也不会自动改 OA 数据库菜单；菜单和角色仍按本文后面的 SQL/菜单配置执行
- `git push main` 只更新远端仓库，不会自动改变服务器；服务器生效必须执行发布脚本并激活 release
- 默认拒绝从 dirty worktree 发布；确需发布未提交代码时必须显式加 `--allow-dirty`，但生产发布不建议这样做

历史服务器首次接入或本次 ACL control-plane 升级时，需要 root 一次性原子安装固定 helper。release 上传和激活都不允许 helper 自更新；
`/usr/local/sbin/finops-ensure-runtime-workers` 继续按独立固定 root helper 管理。API 与 worker 必须共用
`/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env`，不要再让 API helper
引用历史 `/root/fin_ops_stage23_postgres_runtime.env`。否则 API 和 worker 会读取不同 secret 来源，
release 激活后可能出现 worker 正常但 `fin-ops.service` 因缺少 PostgreSQL DSN 反复退出。
`scripts/deploy-oa.sh --no-activate` 只上传并运行 release 校验，不会覆盖 `/usr/local/sbin` helper；
`--activate-existing --release-name <exact-release>` 不 build、不 upload、不 replace、不 self-update，只调用 root release gate。

一次性 bootstrap 必须绑定已上传 exact release 和预先批准的 candidate helper sha256。所有 temp/backup 都放 `/usr/local/sbin` 同一文件系统；bootstrap 只改变 deploy-control，不能 restart service、运行 migration、修改 DB/OA/ACL 或覆盖 runtime-worker helper：

```bash
release=<已上传的-release-name>
approved_sha256=<已批准的-64位-sha256>
candidate="/opt/fin-ops/releases/${release}/src/deploy/oa/bin/finops-deploy-control.sh"
temp="/usr/local/sbin/.finops-deploy-control.${release}.tmp"
backup="/usr/local/sbin/.finops-deploy-control.${release}.previous"

test "$(sha256sum "$candidate" | awk '{print $1}')" = "$approved_sha256"
sudo install -m 0755 -o root -g root "$candidate" "$temp"
sudo bash -n "$temp"
sudo "$temp" contract-version --require settings-access-control-v1
sudo cp -p /usr/local/sbin/finops-deploy-control "$backup"
sudo chown root:root "$backup"
sudo chmod 0600 "$backup"
sudo mv -f "$temp" /usr/local/sbin/finops-deploy-control
sudo test "$(sudo sha256sum /usr/local/sbin/finops-deploy-control | awk '{print $1}')" = "$approved_sha256"
sudo /usr/local/sbin/finops-deploy-control contract-version --require settings-access-control-v1
sudo /usr/local/sbin/finops-deploy-control candidate-status "$release" --json
```

若 post-validation 失败，不能直接把 0600 backup 移回 live：把 backup `install` 到同目录 rollback temp，设为 `root:root 0755`，核验旧 approved hash 和 `bash -n` 后再 `mv -f` 原子恢复。整个 bootstrap 要记录 deploy-control before/after hash、runtime-worker helper hash、active release、service、DB/OA/ACL fingerprint 到 root-owned `/opt/fin-ops/evidence/<release>/settings-access-control-bootstrap.json` 并生成 sha256；任一非 helper 事实变化立即停止。

`release-gate-activate` 先验证 candidate/active fingerprint 未漂移并自动判定 profile。三项 retired admission key 与 legacy admin key 的一次性清理已经完成；稳态发布只执行 strict env assertion，发现任一旧 key 立即失败关闭，不再重写 env。历史 OA binding cleanup/rollback SQL 与激活代码也已删除；OA topology 漂移只能阻断并由独立修复处理。`runtime`/`acl` 通过 current checkpoint 后才停止 API 和上一版本 workers、执行 migration/validated CHECK、安装 runtime assets、发布候选并恢复服务；`frontend` 只发布 exact dist 并重启已有 runtime。frontend 切换前会固定捕获 preflight 已验证的 active worker 集合，候选激活和自动回退都精确重启该集合，避免 stop 后的空 active 列表遗留 workers inactive。`0127_direct_canonical_page_runtime_retirement.sql` 只是 no-op 标记，不会改写 pending backlog、readiness 或回滚 projection 证据。不要手工创建业务表、
不要用运行时账号代替 migrator 账号，也不要让旧 `/opt/fin-ops/fin-ops.env` 或 `/opt/fin-ops/current`
参与 release 运行时。
覆盖式 `legacy-current` 部署入口已经移除；`scripts/deploy-oa.sh` 只生成 versioned release payload，
不再提供覆盖 `/www/wwwroot/fin-ops/dist` 或 `/opt/fin-ops/current/backend` 的发布模式。

release 会占用服务器磁盘。生产策略不是无限保留，而是默认保留最近 4 个 release，并保护当前 active release 和 deploy-control status 中仍被引用的 release。旧 root-owned 历史 release 如果当前部署用户没有权限删除，脚本会跳过并输出原因，需要单独做一次 root 清理。

磁盘空间治理规则：

- release 自动清理只管理 `/opt/fin-ops/releases`，不能替代服务器根分区治理。
- runtime queue 历史由 `finops-prune-runtime-queue-history.timer` 治理；如果 job/read_model schema 异常增长，先跑
  dry-run/状态统计，不要手工删除 pending/processing/failed/dead-lettered queue 行。
- 如果部署在 `storage preflight` 失败，应先用服务器 root 检查 `/var/log`、systemd journal、面板日志、对象存储、缓存和已删除但仍被进程占用的文件；不要用 `finops-deploy` 手工删除不可确认来源的系统文件。
- 建议在生产机配置持久的 journald/logrotate 上限，避免 `/var/log/messages` 或 `/var/log/journal` 持续增长后把 `/` 填满。
- 只有在确认业务影响后，才把 `--keep-releases` 降到 4 以下；降低 release 保留数只能释放 release 目录空间，不能解决日志或系统目录导致的根分区满。

按当前业务要求，唯一受保护管理员固定为 `YNSYLP005`，无需且禁止通过 env 配置第二管理员；生产必须启用并完整配置 OA role sync。

后续再通过关联台里的“访问账户管理”维护：

- 可访问账户
- 只读导出账户
- 全操作账户

注意：生产 `FIN_OPS_OA_ROLE_SYNC_ENABLED` 缺失、禁用或连接参数不完整都会 fail closed；不存在手工同步或 env allowlist fallback。

权限与菜单的 SQL 模板：

- `deploy/oa/fin_ops_menu.mysql.sql`

## 反向代理示例

仓库里已补充 Nginx 示例：

- `deploy/oa/nginx.fin-ops.conf.example`

这份示例覆盖了：

- `/fin-ops/` -> 前端静态资源
- `/fin-ops/*` -> React Router history fallback 到 `/fin-ops/index.html`
- `/fin-ops-api/` -> Python 后端
- `/api/` 和 `/imports/` 在 `/fin-ops/` 页面内反代到 `/fin-ops-api/`

注意：

- `fin-ops` 前端页面内部实际仍然请求 `/api/*`
- 因为页面和 API 都在同域下，所以浏览器 cookie 仍然能被携带
- 前端还会主动附带 `Authorization`
- `location ^~ /fin-ops/` 必须放在官网/OA 兜底 location 之前；否则刷新 `/fin-ops/cost-statistics`、`/fin-ops/settings` 这类深层路由会被外层站点接走，浏览器拿到的不是 fin-ops 的 `index.html`，页面会空白或显示错误站点。
- `/fin-ops/assets/` 必须单独 `try_files $uri =404`，不要 fallback 到 `index.html`。Vite 的 hashed asset 可以长期缓存；HTML shell 必须 `no-store`，确保发布后刷新能拿到最新 asset manifest。
- `/fin-ops/api/` 必须在 `/fin-ops/` React fallback 之前代理到后端 `/api/`。否则旧标签页或相对 API 路径会拿到 `index.html`，前端会显示“会话校验失败”。

## OA 菜单配置

OA 菜单按当前同域 iframe 口径配置：

- 名称：`财务运营平台`
- 路径：`https://www.yn-sourcing.com/fin-ops/?embedded=oa`
- 菜单类型：`C`
- 外链：`1`
- 内嵌打开：`1`
- 权限标识：`finops:app:view`

菜单模板文件：

- `deploy/oa/fin_ops_menu_payload.json`

如果生产环境更适合通过 DBA 执行 SQL，而不是通过 OA 菜单管理页面手工录入，可直接使用：

- `deploy/oa/fin_ops_menu.mysql.sql`
- `deploy/oa/fin_ops_user_role_sync.mysql.sql`

## ACL 安全发布与生产证据

所有 `frontend`/`runtime`/`acl` 的标准激活都只需要 005。以下双身份步骤是权限链路发生变化后可显式运行的专项验收，不是 `release-gate-activate` 的前置条件，也不能用于手工指定或降级 profile。

1. 本地全回归和 clean commit 后上传但不激活：`./scripts/deploy-oa.sh --no-activate --release-name <release>`，并用 `release-gate-profile <release> --json` 确认自动结果为 `acl`。
2. 若候选包含 deploy-control 变更，按上文 manual-root 流程原子 bootstrap；禁止 `self-update`，并证明 runtime-worker helper、active release、service、DB、OA、ACL 不变。
3. 本地 0600 token 文件同时提供 005 admin token 和 006 专用、初始 denied bearer token。两者经 SSH stdin 传递，不进入 argv、artifact 或日志：

```bash
./scripts/with-production-admin-token.sh --require-bearer sh -c '
  printf "%s\n%s\n" "$FIN_OPS_HTTP_SLO_ADMIN_TOKEN" "$FIN_OPS_HTTP_SLO_BEARER_TOKEN" |
  ssh -o StrictHostKeyChecking=accept-new -o ControlMaster=no finops-deploy@finops-prod \
    "sudo -n /usr/local/sbin/finops-deploy-control settings-access-control-preflight <release> --http-tokens-stdin --dry-run --json"'
ssh -o StrictHostKeyChecking=accept-new -o ControlMaster=no finops-deploy@finops-prod \
  'sudo -n sha256sum --check /opt/fin-ops/evidence/<release>/settings-access-control-preflight.json.sha256'
```

Preflight 要求 admin session 精确为 `YNSYLP005/admin`；专用 bearer 精确为 `YNSYLP006`、非 admin，并从 canonical Settings ACL 的 allowed/readonly/full/admin 四个集合全部缺席。006 必须是 `denied` 且不带 `finops:app:view`；0133/CHECK 必须已全部生效，retired/legacy admission env 必须全部缺席，OA selector、唯一 menu、三 dedicated roles/bindings/members 必须与 canonical ACL 精确一致。artifact 只含非敏感 state/blockers、salted hashes/counts/fingerprints。任何 token、identity、canonical ACL、DB、env、OA 或 fingerprint 漂移都阻断且零写。历史 cutover/cleanup 状态不再被稳态发布接受。

4. 只用 exact candidate 零重传激活：`./scripts/deploy-oa.sh --activate-existing --release-name <release>`。顺序固定为 current runtime checkpoint → strict env assertion → API/worker quiesce → migration/CHECK read-back → runtime sync/install → safe candidate → T+0/T+60/T+300 evidence。ACL 激活失败保持 maintenance 并 forward repair，不回滚到可能不具备当前 ACL 安全能力的旧 binary。
5. 激活成功后用相同双 token 运行 `settings-access-control-post-deploy`。它把 `YNSYLP006` 专用 bearer 依次改为 full、read、denied，验证 generic save、两条直接提权攻击、AppHealth/OA credentials/data reset admin-only、OA 三角色、fresh OA router 菜单可见性、durable audit/request id 和 ACL GET/PUT latency，并在 finally/read-back 中恢复原 accounts/OA/denied session：

```bash
./scripts/with-production-admin-token.sh --require-bearer sh -c '
  printf "%s\n%s\n" "$FIN_OPS_HTTP_SLO_ADMIN_TOKEN" "$FIN_OPS_HTTP_SLO_BEARER_TOKEN" |
  ssh -o StrictHostKeyChecking=accept-new -o ControlMaster=no finops-deploy@finops-prod \
    "sudo -n /usr/local/sbin/finops-deploy-control settings-access-control-post-deploy <release> --http-tokens-stdin --json"'
ssh -o StrictHostKeyChecking=accept-new -o ControlMaster=no finops-deploy@finops-prod \
  'sudo -n sha256sum --check /opt/fin-ops/evidence/<release>/settings-access-control-post-deploy.json.sha256'
```

post-deploy 不接受旧 runtime 切换态作为最终结果。初始 `YNSYLP006` 必须同时为 canonical denied、非 admin、无 `finops:app:view` 且 fresh OA router 不可见；只有 strict env contract、`status=pass`、restore 全 true（包括 OA router 恢复为 denied 不可见）、migration/CHECK true、三档角色和攻击矩阵全通过、fresh OA router 只在 full/read 阶段可见、ACL GET p95≤1000ms、ACL PUT max≤5000ms 才完成。restore 失败必须非零并立即人工核对 DB/OA/session。

## 权限同步操作顺序

当 `YNSYLP005` 在 app 的“访问账户管理”里修改权限后，生产环境必须按这个顺序同步：

1. 通过 admin-only `PUT /api/workbench/settings/access-control` 保存；普通 settings POST 不承载 ACL
2. 记录本次变更后的三类名单：
   - 只读导出账户
   - 全操作账户
   - 管理员账户（当前固定 `YNSYLP005`）
3. 在 OA 数据库或 OA 角色管理后台同步用户角色：
   - 只读导出账户 -> `finops_read_export`
   - 全操作账户 -> `finops_full_access`
   - `YNSYLP005` -> `finops_admin`
4. 把不再出现在 `allowed_usernames` 内的账户，从以上三类 OA 角色全部移除
5. 用对应账号重新登录 OA 验证菜单和页面行为；这是验收，不是生产同步 fallback

如果只改了 app 设置、没同步 OA 角色，会出现两类不一致：

- 账户在 OA 菜单里还能看见，但进 app 后被拒绝
- 账户在 app 里已被放行，但 OA 菜单里还看不见

## 发布顺序

推荐按这个顺序发布，避免菜单先暴露但应用未准备好：

1. 部署 fin-ops 后端到 `/fin-ops-api/`
2. 配置后端环境变量并确认 `/api/session/me` 可用
3. 部署 fin-ops 前端到 `/fin-ops/`
4. 在测试账号下直连访问 `/fin-ops/?embedded=oa`
5. 在 OA 中创建 `finops:app:view`
6. 给目标角色或账号授权
7. 在 OA 菜单中新增 `财务运营平台`
8. 用授权账号联调 iframe、搜索、导出、税金抵扣、成本统计
9. 用未授权账号验证菜单不可见和 `403`
10. 再正式面向生产用户开放

### 深层路由刷新验收

生产 nginx 配置完成后，必须验证这些 URL 都返回 fin-ops 的 HTML shell，而不是公司官网/OA 外层页面：

```bash
curl -s https://www.yn-sourcing.com/fin-ops/ | grep '银企核销工作台'
curl -s https://www.yn-sourcing.com/fin-ops/cost-statistics | grep '银企核销工作台'
curl -s https://www.yn-sourcing.com/fin-ops/settings | grep '银企核销工作台'
curl -sI https://www.yn-sourcing.com/fin-ops/assets/not-exist.js | grep '404'
curl -sI https://www.yn-sourcing.com/fin-ops-api/api/session/me | grep -Ei '401|application/json'
curl -sI https://www.yn-sourcing.com/fin-ops/api/session/me | grep -Ei '401|application/json'
```

如果 `/fin-ops/cost-statistics` 返回公司官网标题或 `js/app.*.js`、`css/app.*.css`，说明该请求没有命中 fin-ops 的 `location ^~ /fin-ops/`，需要调整 nginx location 优先级后 `nginx -t && nginx -s reload`。

## 联调验收清单

### 账户分层前置检查

- [ ] `allowed_usernames` 与 OA 三类 fin-ops 角色成员一致
- [ ] `readonly_export_usernames` 是 `allowed_usernames` 子集
- [ ] `admin_usernames` 只有 `YNSYLP005`
- [ ] `YNSYLP005` 同时存在于 app 管理员名单与 OA `finops_admin` 角色

### 会话与权限

- [ ] 已登录 OA 后，访问 `/fin-ops/?embedded=oa` 不出现自己的登录页
- [ ] `/api/session/me` 返回当前 OA 用户信息
- [ ] 授权账号 `allowed = true`
- [ ] 未授权账号 `allowed = false`
- [ ] 未授权账号直接访问核心 API 返回 `403`
- [ ] OA 登出后，再进入 `fin-ops` 会显示会话失效

### 菜单与 iframe

- [ ] 授权账号在 OA 菜单中能看到 `财务运营平台`
- [ ] 未授权账号在 OA 菜单中看不到该入口
- [ ] 点击菜单后在 OA 内容区内嵌打开，不新开窗口
- [ ] `fin-ops` 嵌入态不显示自己的全局头部
- [ ] 收起/展开 OA 左侧菜单后，iframe 高度正常

### QA：不可见用户

- [ ] 在 OA 菜单里看不到 `财务运营平台`
- [ ] 直接访问 `/fin-ops/` 或核心 API 返回 `403`
- [ ] 搜索、导出、详情、工作台都无法进入

### QA：只读导出用户

- [ ] 在 OA 菜单里能看到 `财务运营平台`
- [ ] 能进入 `关联台 / 税金抵扣 / 成本统计`
- [ ] 能搜索、看详情、导出
- [ ] 看不到导入按钮
- [ ] `确认关联 / 取消配对 / 异常处理 / 忽略 / 撤回忽略 / 保存设置` 均不可用
- [ ] 税金抵扣 `已认证发票导入` 不可用
- [ ] 任意写接口返回 `403`

### QA：全操作用户

- [ ] 在 OA 菜单里能看到 `财务运营平台`
- [ ] 关联台、税金抵扣、成本统计均可正常读写
- [ ] 能导入、确认关联、异常处理、忽略、保存普通设置
- [ ] 看不到或不能使用“访问账户管理”
- [ ] 权限管理接口返回 `403`

### QA：管理员 `YNSYLP005`

- [ ] 在 OA 菜单里能看到 `财务运营平台`
- [ ] 具备所有业务写操作能力
- [ ] 能进入 `设置 -> 访问账户管理`
- [ ] 能维护：
  - 可访问账户
  - 只读导出账户
  - 全操作账户
- [ ] 保存后 app 内权限立即生效
- [ ] 保存后 OA role sync 自动完成，并用 fresh OA router/session 验证菜单可见性一致

### 功能可用性

- [ ] 关联台可正常加载
- [ ] 税金抵扣可正常加载和试算
- [ ] 成本统计可正常加载与导出
- [ ] 工作台导出、成本统计导出都可正常下载
- [ ] 已授权用户可访问 `workbench / tax / cost / export`

## 自动化回归建议

当前这轮变更主要依赖：

- 后端：
  - `tests.test_session_api`
  - `tests.test_app_settings_service`
- 前端：
  - `web/src/test/SessionApi.test.ts`
  - `web/src/test/SessionGate.test.tsx`
  - `web/src/test/WorkbenchSelection.test.tsx`
  - `web/src/test/TaxOffsetPage.test.tsx`

建议在每次权限模型变更后至少执行：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_session_api tests.test_app_settings_service -v
cd web && npm run test -- --run src/test/SessionApi.test.ts src/test/SessionGate.test.tsx src/test/WorkbenchSelection.test.tsx src/test/TaxOffsetPage.test.tsx
cd web && npm run build
```

## 回滚方案

如果上线后发现问题，按这个顺序回滚：

1. 先在 OA 菜单中隐藏或下线 `财务运营平台`
2. 撤销目标角色的 `finops:app:view`
3. 只有 previous release 的安全 capability/source fingerprints 有效，且 schema 未变化或 exact schema compatibility evidence 覆盖所有已应用候选 migration head 时，才允许 release gate 自动恢复其前后端
4. previous 不安全、不存在或 schema compatibility 未证明时保持 API maintenance；保留已应用 migration，使用新的安全 candidate forward repair，禁止手工启动旧 binary
5. 如需要，再回滚 iframe 高度修复或 OA 菜单配置

不要先回滚后端再保留菜单入口，否则用户会进入一个失效页。

## 常见故障定位

### 进入后显示无权访问

检查：

- OA 当前账号是否具备 `finops:app:view`
- `FIN_OPS_OA_REQUIRED_PERMISSION` 是否被改掉
- 当前账号是否仍在 `allowed_usernames`
- 当前账号是否仍然绑定了 OA 的 fin-ops 可见角色
- `/api/session/me` 返回的 `permissions` 是否包含目标权限

### 显示 OA 会话已失效

检查：

- 浏览器同域 cookie 里是否有 `Admin-Token`
- OA 登录是否已过期
- `FIN_OPS_OA_BASE_URL` 是否能成功访问 `/system/user/getInfo`

### 页面能打开但 API 403

检查：

- 前端是否真的附带了 `Authorization: Bearer ...`
- 请求是否被代理到了正确的 `/fin-ops-api/`
- 后端读取到的用户是否和 OA 当前用户一致

## 相关文档

- `ARCHITECTURE.md`
- `docs/architecture/oa-integration.md`
- `docs/architecture/deployment.md`
- `docs/product-specs/oa-integration.md`
- `docs/archive/legacy-dev/oa-menu-iframe-integration.md`
- `docs/operations/deployment.md`

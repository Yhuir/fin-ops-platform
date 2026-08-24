# OA 同域生产部署

本目录是 `fin-ops-platform` 的生产部署事实源。正式入口是仓库根目录的：

```bash
./scripts/deploy-oa.sh
```

部署只发布 fin-ops 前后端和自己的 runtime assets，不修改 OA Java/Vue 源码，不自动修改 OA 菜单数据，
不删除主数据库。

## 路径与服务

| 对象 | 生产路径/名称 |
| --- | --- |
| Versioned release | `/opt/fin-ops/releases/<release-name>` |
| Active symlink | `/opt/fin-ops/current` |
| Public frontend | `/fin-ops/` |
| Public API | `/fin-ops-api/` |
| API service | `fin-ops.service` |
| Worker template | `fin-ops-worker@.service` |
| Deploy control | `/usr/local/sbin/finops-deploy-control` |
| Worker helper | `/usr/local/sbin/finops-ensure-runtime-workers` |

Nginx 示例是 `deploy/oa/nginx.fin-ops.conf.example`。`/fin-ops-api/`、`/api/` 和兼容
`/fin-ops/api/` location 必须转发认证 header/cookie、request ID、`If-None-Match`，并采用仓库声明的
body/timeout 限制。深层前端路由刷新必须回到 `index.html`。

## 运行环境

API 与 worker 共用：

- `/etc/fin-ops/fin-ops.common.env`
- `/etc/fin-ops/fin-ops.secrets.env`

实例专属 env 仅放 worker 自己的 transport/poll/lease 配置，不复制数据库或 OA secret。文件必须是
root-owned，secret 文件 mode `0600`，不得打印到 terminal、evidence 或仓库。

激活时 Worker helper 会保留实例现有的 poll/lease/timeout/吞吐调优，同时原子移除 per-worker env 中遗留的
RabbitMQ/Redis 覆盖并强制 `FIN_OPS_QUEUE_BACKEND=postgres`。这一步发生在 registration check 与服务启动前，
防止旧环境值把当前 Worker 重新接回已退役 transport。

生产必须使用 PostgreSQL storage backend、独立 migrator 凭据、只读 OA Mongo adapter、启用 OA role sync。
唯一权限 selector 是 `FIN_OPS_OA_REQUIRED_PERMISSION`；以下历史 admission env 必须缺席：

- `FIN_OPS_ALLOWED_USERNAMES`
- `FIN_OPS_ALLOWED_ROLES`
- `FIN_OPS_READONLY_EXPORT_USERNAMES`

访问账户、只读导出账户和全操作账户由 App 设置页维护。受保护管理员为 `YNSYLP005`。

## 当前 worker

`runtime_worker_registry.py` 是唯一事实源。生产必须且只能运行：

- `fin-ops-worker@oa-sync.service`
- `fin-ops-worker@workbench-matching.service`
- `fin-ops-worker@import.service`
- `fin-ops-worker@settings-maintenance.service`

发布会 stop/disable registry 外实例。不要手写第二份 worker 清单，也不要保留旧实例“备用”。

## 发布前本地验证

```bash
bash scripts/verify.sh lint
bash scripts/verify.sh backend
bash scripts/verify.sh frontend
bash scripts/verify.sh docs
git diff --check
git status --short
```

正式发布默认拒绝 dirty worktree。release 必须来自已提交、已推送的 `main`。

## 一键发布

```bash
./scripts/deploy-oa.sh
```

常用受控模式：

```bash
# 只 build/upload/validate，不激活
./scripts/deploy-oa.sh --no-activate

# 激活服务器上已验证的 exact release
./scripts/deploy-oa.sh --activate-existing --release-name <release-name>
```

脚本构建前端、打包 versioned release、上传、运行候选校验，然后调用 root deploy control。不要直接覆盖
`web/dist`、`current/backend` 或 systemd unit。

## 激活顺序

Runtime/ACL profile 的激活顺序固定为：

1. 校验 candidate、active release、env/ACL、storage 和 migration plan；
2. 进入 maintenance，停止 API 和当前 worker；
3. 执行 migration 与 schema check；
4. 安装当前 worker helper/unit/env，退役 registry 外资产；
5. 原子切换 `/opt/fin-ops/current`；
6. 安装并 enable OA sync enqueue timer，但在发布门禁期间保持 stopped；
7. 启动四个 worker 和 API；
8. 运行 T+0 与 T+30 release checkpoint；
9. 写入 root-owned、脱敏且带 SHA-256 的 evidence，验证成功后再启动 OA sync enqueue timer。

Frontend-only profile 不执行 migration，也不改变 worker registry。

## Canonical direct-read 迁移

Migration `0149_remove_read_model_runtime.sql` 是 forward-only 的旧 projection 退役：它先确认遗留 schema
没有未知 relation，再终止历史 `%.read_model.refresh` 非终态事件，删除旧 dirty-scope 表与 projection
schema。它不会删除主数据库或其它业务 schema。

同一次激活还会精确删除旧 Workbench generation timer/service/helper 和已知旧 worker env，并 stop/disable
未登记 worker。生产运行时只保留 canonical API reads、通用 outbox/attempt/heartbeat、OA sync、import、
settings maintenance 与 Workbench matching。应用专属 dispatcher/topology unit 和 env 会被精确退役，共享服务器上的
broker 软件不在本应用部署脚本的删除范围内。历史 outbox RabbitMQ 列暂时只作为上一版本回滚兼容面保留；当前
API、Worker、监控和部署链路均不读写这些列，不再存在 RabbitMQ 双传输。物理删列必须在上一版本回滚窗口结束后
作为独立 schema maintenance 执行，不能与运行时切换绑定。

一旦 0149 已执行，不允许自动切回依赖旧 schema 的 previous release。后验证失败时保持 maintenance，使用
当前 release 向前修复；这是避免旧代码重新污染链路的必要限制。

## Release checkpoint

每个 checkpoint 必须同时证明：

- `/health/ready` 成功且 response contract 完整；
- worker exact-set、registration 与 heartbeat 正确；
- PostgreSQL outbox backlog/failed/dead-letter 没有恶化；
- canonical page/system audit 通过；
- 核心 GET 全部 2xx JSON，p95 <= 1000ms、p99 <= 2000ms；
- 可逆临时数据库写成功并完成清理；
- 没有新产生的退役 projection event。

Release gate 不自动执行真实业务 confirm/withdraw，不伪造业务数据，也不清空失败队列来获得绿色状态。
候选激活和自动回滚都会先停止 OA sync enqueue timer，避免 `Persistent=true` timer 在 worker 切换窗口创建
随后失去 lease owner 的 `oa.sync` 任务；timer 只在候选或 previous release 已完成验证后恢复。

## 生产验证

Admin token 通过本机受控 wrapper 加载：

```bash
scripts/with-production-admin-token.sh \
  python3 -m fin_ops_platform.tools.http_slo_probe --json

scripts/with-production-admin-token.sh \
  python3 -m fin_ops_platform.tools.runtime_sync_closure_gate --profile stability --json
```

不要把 token 粘贴到命令、聊天或日志。生产验证至少保存 release/commit、时间窗、endpoint 样本、
p50/p95/p99、canonical audit、health、worker、PostgreSQL outbox/dead-letter 和负向旧事件审计。

受控业务写 smoke 只接受固定 scenario、root-owned `0600` 输入、Admin Token 与 approval ticket；测试数据必须
明确归工具所有，结束时恢复原状态。不得对任意真实业务记录做“试验性”写入。

## 回滚与恢复

- Migration 尚未执行或 frontend-only 发布：deploy control 可切回已验证 previous immutable release。
- Forward-only migration 已执行：禁止自动回滚，保持 maintenance 并 forward repair。
- 不通过恢复旧 worker/env、重建旧 projection、手写 SQL 或删 queue 行解阻。
- repair 工具必须先 dry-run，绑定 source fingerprint、精确计数、operator 和 reason；任何漂移在写前失败。银行 Audit terminal suspected link 修复还必须显式提供 `--expected-bank-audit-row-unlink-count`，只允许候选 release 按计划逐行 CAS 清空该引用。
- 已审阅的历史 OA 身份迁移通过一次性、fail-closed 数据迁移修复；迁移只接受 exact attachment key bridge、旧 item ID、row index 和指定 canonical 发票完全一致的证据。运行时只读取 indexed active alias，禁止把 cache bridge 放回 Workbench 页面热查询。

本次 runtime 退役不创建数据库备份。如果独立数据修复明确创建 task-specific recovery artifact，完成验证后按
工具合同删除该 artifact；禁止删除主数据库。

## OA 会话、角色与菜单

- OA 页面通过同域 cookie/token broker 复用会话；后端不向浏览器暴露 OA 密钥。
- OA Mongo 只读；需要向 OA MySQL 写回的动作走专用 adapter、权限、幂等与审计边界。
- OA 菜单模板：`deploy/oa/fin_ops_menu.mysql.sql`。
- 菜单至少授予 `finops:app:view`；App 内细分权限来自同步后的账户 tier。
- 不可见用户、只读导出用户、全操作用户和管理员都要做路由、API、隐藏/禁用按钮回归。

## 首次安装控制面

服务器首次接入时，root 只安装仓库提供的固定 helper。候选 helper 必须绑定 exact release 和预批准 SHA-256，
先 `bash -n`/contract check，再以同文件系统 temp + atomic rename 安装。bootstrap 不得顺带运行 migration、
重启服务、修改 OA/ACL 或数据库。

## 磁盘与日志

- 自动清理只管理 `/opt/fin-ops/releases`，默认保留最近 4 个并保护 active/previous 引用。
- Queue retention 只清理完成历史，不碰 pending/processing/failed/dead-lettered。
- 根分区不足时先检查 journal、面板日志、对象存储和已删除但仍占用的文件；不要让 deploy script猜测删除。
- 建议给 journald/logrotate 设置明确上限。

## 常见故障顺序

1. `systemctl status fin-ops.service` 与 `/health/ready`。
2. 四个 required worker 的 systemd/heartbeat/registration。
3. PostgreSQL outbox backlog、failed/dead-lettered。
4. API request ID 对应的结构化 error/timing。
5. canonical page/system audit 与 endpoint DB timing/query count。
6. OA session、role sync 和 Nginx header/cookie forwarding。

详细 worker 治理见 `docs/operations/runtime-worker-governance.md`，PostgreSQL 运行边界见
`docs/operations/postgresql-runtime.md`，权限合同见 `docs/product-specs/permissions.md`。

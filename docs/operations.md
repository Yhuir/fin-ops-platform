# 部署与运行

本文是 `fin-ops-platform` 的生产部署事实源。正式入口是仓库根目录的：

```bash
./scripts/deploy-oa.sh
```

部署只发布 fin-ops 前后端和自己的 runtime assets，不修改 OA Java/Vue 源码，不自动修改 OA 菜单数据，
不删除主数据库。

## 路径与服务

| 对象 | 生产路径/名称 |
| --- | --- |
| Versioned release | `/opt/fin-ops/releases/<release-name>` |
| Active API/worker source | systemd `99-deploy-release.conf` 指向 `/opt/fin-ops/releases/<release-name>/src` |
| Frontend files | `/www/wwwroot/fin-ops/dist` |
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

访问账户及其页面集合由 App 设置页维护。受保护管理员为 `YNSYLP005`；旧的只读/全操作层级不属于运行时合同。

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
线上前端目录、release 内容或 systemd unit。

## 激活顺序

Runtime/ACL profile 的激活顺序固定为：

1. 校验 candidate、active release、env/ACL、storage 和 migration plan；
2. 进入 maintenance，停止 API 和当前 worker；
3. 执行 migration 与 schema check；
4. 安装当前 worker helper/unit/env，退役 registry 外资产；
5. API/worker drop-in 指向 exact release，前端从该 release 的 `web/dist` 暂存后切换到发布目录；
6. 安装并 enable OA sync enqueue timer，但在发布门禁期间保持 stopped；
7. 启动四个 worker 和 API；
8. 运行 T+0 与 T+30 release checkpoint；
9. 写入 root-owned、脱敏且带 SHA-256 的 evidence，验证成功后再启动 OA sync enqueue timer。

Frontend-only profile 不执行 migration，也不改变 worker registry。

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
同 schema 且无 pending migration 的发布，preflight 只读 closure 使用候选审计代码，避免旧审计缺陷阻断其自身修复；有迁移时继续使用 active 代码。实时 HTTP、worker、队列以及 T+0/T+30 检查不变。

候选激活和自动回滚都会先停止 OA sync enqueue timer，避免 `Persistent=true` timer 在 worker 切换窗口创建
随后失去 lease owner 的 `oa.sync` 任务；timer 只在候选或 previous release 已完成验证后恢复。

## 生产验证

Admin token 通过本机受控 wrapper 加载：

```bash
PYTHONPATH=backend/src scripts/with-production-admin-token.sh \
  python3 -m fin_ops_platform.tools.http_slo_probe --base-url https://www.yn-sourcing.com --api-prefix /fin-ops-api --json

PYTHONPATH=backend/src scripts/with-production-admin-token.sh \
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
- OA 附件发票当前子付款项全量审计/修复复用固定 helper：`import-audit-repair <release> --dry-run --repair-all-oa-attachment-invoice-links --rollback-manifest-path /opt/fin-ops/runtime-smoke/import-audit-repair-artifacts/<task>.json`；artifact 路径只能位于硬编码的 root-owned `0700` 目录，helper 明确拒绝通过环境变量重定向该目录，文件以 `O_EXCL/O_NOFOLLOW` 创建且权限固定为 `0600`。为兼容尚未刷新到当前版本的 root-owned helper，CLI 仅在有效 UID 为 root 且未提供配置时自建并使用这一硬编码目录；非 root 直调仍必须显式配置受控 artifact root，缺失时失败关闭。执行必须复用同一 artifact 并追加 dry-run fingerprint、operator 与 reason。报告只输出 artifact 指纹与恢复条数；验证幂等和页面闭环后，优先使用 `import-audit-repair-artifact-delete <task>.json <rollback-manifest-fingerprint>` 校验指纹并精确删除；若 root-owned helper 尚未更新到该命令，则通过同一受控入口执行 `import-audit-repair <release> --delete-rollback-manifest-artifact <task>.json --expected-rollback-manifest-fingerprint <rollback-manifest-fingerprint>`。两条删除路径都只接受安全文件名、root-owned `0700/0600` 工件和精确内容指纹。不得删除平台 PITR、组织级备份或主数据库。
- OA 来源身份只读取 indexed active alias，页面热查询不扫描附件 cache bridge；身份修复必须具备精确来源与 canonical 对象证据。

仅在数据修复确有需要时建立任务专属恢复工件；完成验证后按工具合同精确删除，不触碰平台常规备份或主数据库。

## OA 会话、角色与菜单

- OA 页面通过同域 cookie/token broker 复用会话；后端不向浏览器暴露 OA 密钥。
- OA Mongo 只读；需要向 OA MySQL 写回的动作走专用 adapter、权限、幂等与审计边界。
- OA 菜单模板：`deploy/oa/fin_ops_menu.mysql.sql`。
- 菜单至少授予 `finops:app:view`；App 内页面权限只来自 canonical `page_access_accounts`，OA 角色不反向授予页面。
- 无页面用户、单/多页面授权用户和固定 005 管理员都要做路由、API、侧栏过滤与 direct URL 回归。

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

模块职责见[worker](modules/runtime-workers/README.md)、[权限](modules/permissions-and-audit/README.md)和[数据安全](modules/data-safety-reset/README.md)。

### 访问账户发布验证

既有 `assert_settings_access_control_database_guard` 通过 `--verify-oa-topology` 同时验证 OA 实际两角色结构；frontend profile 激活前也执行这一检查。数据库 guard 正常不能代替 OA 配置正确。检查只读，标准发布不会自动迁移 OA 菜单。

旧三角色迁移使用专项工具并核对真实引用。只允许本 App 入口及直接父菜单；保留父菜单关系与旧只读角色成员，只摘除旧只读角色的 App 入口绑定。运行时不保留旧角色兼容路径。

## 后到发票历史 scope 重扫

`finops-deploy-control workbench-matching-retry <release> --scope-month YYYY-MM --dry-run` 也可检查 completed scope，并输出当前同组可补齐归属及正式关系计划数。执行仍沿用 `--execute --expected-fingerprint`，只登记正常 worker 任务，不由 CLI 写发票来源。processing/dirty 不重复运行。

### ETC 发票数据修复

复用固定 helper `import-audit-repair <release> --dry-run --repair-etc-invoice-payload` 发现目标；该独立模式不扫描无关银行历史。限定 `--invoice-id <canonical-id>`（可重复）并附 `--rollback-manifest-path` 生成既有受控私有恢复工件后，以相同目标、工件、`--expected-fingerprint`、`--operator-id`、`--reason` 执行 `--execute`。只允许原导入税率明确为空、正式税率为空、payload 税率等于对应 ETC 来源的记录；缺证据或并发变化明确拒绝，事务内写审计。修复后重跑必须零更新，发票页 Audit 不再有正式列/副本冲突，ETC 票数金额不变。完成验证后按上文 artifact-delete 精确删除本任务工件，不触碰主数据库或平台备份。


## 数据与恢复边界

迁移目录和部署代码维护结构兼容性、forward-only 版本集合及恢复条件；它们是可执行系统的一部分，不能按过程文档删除。未执行结构变更时可以使用已验证 previous release；已经发生不兼容结构变更时只能向前修复。不得通过删迁移记录、恢复已失效字段、删除主数据库或业务队列“消除报错”。

现金使用同一生产 PostgreSQL 与登录账号，只通过 cash 自有 service/repository 访问 cash schema；现金配置和连接池不走普通业务的全局设置/审计/任务。现金上线验证必须包含连接池超时、业务隔离和跨账号权限。

常规 PITR/组织备份由数据库运维负责，任务不擅自更改保留策略。一次性修复工件与常规备份区分；仅删除本任务创建且已经验证不再需要的工件，保留审计。

生产浏览器只读验证在 `web/` 中执行：

```bash
../scripts/with-production-admin-token.sh bash -c 'export FIN_OPS_E2E_OA_TOKEN="$FIN_OPS_E2E_ADMIN_TOKEN"; npm run e2e:production-shell'
../scripts/with-production-admin-token.sh npm run e2e:production-admin
```

`production-shell` 使用 OA cookie token 变量，wrapper 加载后在子进程内赋值，不打印凭据。公网耗时包含网络与代理，若超标需结合服务器本地 API/SQL 耗时定位，不能单看 HTTP 200 判断性能。

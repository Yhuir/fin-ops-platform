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

- `deploy/oa/fin_ops_role_binding.mysql.sql`
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
FIN_OPS_OA_REQUIRED_PERMISSION=finops:app:view
FIN_OPS_OA_REQUEST_TIMEOUT_MS=5000
FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS=30
FIN_OPS_ALLOWED_USERNAMES=YNSYLP005
FIN_OPS_READONLY_EXPORT_USERNAMES=
FIN_OPS_ADMIN_USERNAMES=YNSYLP005
FIN_OPS_ALLOWED_ROLES=
VITE_APP_BASE_PATH=/fin-ops/
```

补充说明：

- `FIN_OPS_OA_BASE_URL` 必须指向 OA 网关对外地址
- `finops-deploy-control check-release` 会在发布前校验 PostgreSQL DSN 以及
  `FIN_OPS_OA_BASE_URL / FIN_OPS_OA_USER_INFO_PATH / FIN_OPS_ALLOWED_USERNAMES / FIN_OPS_ADMIN_USERNAMES`，
  缺任一项都会停止发布，避免上线后才出现“未配置 OA 用户信息服务地址”
- `FIN_OPS_OA_REQUIRED_PERMISSION` 默认就是 `finops:app:view`
- `FIN_OPS_ALLOWED_USERNAMES / FIN_OPS_READONLY_EXPORT_USERNAMES / FIN_OPS_ADMIN_USERNAMES`
  是启动期兜底配置，真实长期口径仍以 app 设置持久化为准
- 如果希望“访问账户管理”保存后自动同步 OA 菜单角色，还需要配置：
  - `FIN_OPS_OA_ROLE_SYNC_ENABLED=1`
  - `FIN_OPS_OA_ROLE_SYNC_HOST / PORT / DATABASE / USERNAME / PASSWORD`
  - `FIN_OPS_OA_ROLE_SYNC_READONLY_ROLE_KEY / FULL_ACCESS_ROLE_KEY / ADMIN_ROLE_KEY`
- `VITE_APP_BASE_PATH` 必须是 `/fin-ops/`
- 业务数据相关的 Mongo 配置仍按现有 `fin-ops` 运行说明提供，不在这里重复展开

仓库里已补充一份环境变量模板：

- `deploy/oa/fin_ops.env.example`
- `deploy/oa/env/fin-ops.common.env.example`
- `deploy/oa/env/fin-ops.secrets.env.example`
- `deploy/oa/env/fin-ops.postgres-migrator.env.example`
- `deploy/oa/env/fin-ops.worker.oa-sync.env.example`
- `deploy/oa/env/fin-ops.worker.workbench.env.example`
- `deploy/oa/env/fin-ops.rabbitmq-*.env.example`

systemd 模板位于：

- `deploy/oa/systemd/fin-ops.service.example`
- `deploy/oa/systemd/fin-ops-worker@.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-topology.service.example`
- `deploy/oa/systemd/fin-ops-rabbitmq-dispatcher.service.example`

关联台自动配对必须单独启用 `workbench-matching` worker。它消费
`job.workbench_matching_dirty_scopes`，生成 `read_model.workbench_reconciliation_decisions`；
`workbench-read-model` worker 只负责把已有关系和自动决策投影到页面读模型，不能替代自动配对。
生产实例配置示例：

- `deploy/oa/env/fin-ops.worker.workbench-matching.env.example`

生产部署时，API、worker、RabbitMQ dispatcher 和 RabbitMQ topology bootstrap 应使用不同的 `EnvironmentFile`。`FIN_OPS_POSTGRES_DATABASE_URL`、`FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL`、`RABBITMQ_URL`、Redis、MinIO/S3 和 OA role sync 密码只能放在服务器 root-only secret 文件中，不要写入仓库模板或 systemd inline `Environment=`。migrator DSN 只能用于手动/受控 migration，不要加载到 API 或 worker unit。

PostgreSQL migration 示例：

```bash
sudo install -m 0600 -o root -g root \
  deploy/oa/env/fin-ops.postgres-migrator.env.example \
  /etc/fin-ops/fin-ops.postgres-migrator.env
sudoedit /etc/fin-ops/fin-ops.postgres-migrator.env

set -a
source /etc/fin-ops/fin-ops.postgres-migrator.env
set +a

PYTHONPATH=/opt/fin-ops/current/backend/src \
  /opt/fin-ops/venv/bin/python -m fin_ops_platform.postgres apply
```

RabbitMQ 切换不是发布脚本的默认副作用。先保持 `FIN_OPS_QUEUE_BACKEND=postgres`，完成 topology apply 和 dispatcher shadow publish 观察，再按 worker 族灰度到 `FIN_OPS_QUEUE_BACKEND=rabbitmq`。完整 topology 已覆盖 workbench、search/pending、发票使用/收款、cost/tax、oa-sync 和 file migration；生产发布范围由 `RABBITMQ_DISPATCH_EVENT_TYPES` 控制。完整步骤见 `docs/operations/runtime-read-model-hardening.md`。

最小生产正确性不依赖 RabbitMQ。标准 release 发布会通过服务器 root-owned helper
`/usr/local/sbin/finops-ensure-runtime-workers`，安装/更新 worker systemd 模板，补齐缺失的
worker env，并启用、重启以下 PostgreSQL polling worker。仓库内的
`deploy/oa/bin/finops-ensure-runtime-workers.sh` 是该 helper 的源文件，不能由 `finops-deploy`
从 release 目录直接 `sudo /bin/bash` 执行：

```bash
sudo systemctl enable --now fin-ops-worker@oa-sync.service
sudo systemctl enable --now fin-ops-worker@workbench.service
sudo systemctl enable --now fin-ops-worker@workbench-matching.service
sudo systemctl enable --now fin-ops-worker@bank-detail.service
sudo systemctl enable --now fin-ops-worker@search-pending.service
sudo systemctl enable --now fin-ops-worker@invoice-usage-collection.service
sudo systemctl enable --now fin-ops-worker@cost-tax.service
sudo systemctl enable --now fin-ops-worker@import.service
```

这些实例分别加载 `/etc/fin-ops/fin-ops.worker.<instance>.env`。如果仍使用
PostgreSQL polling，这些文件应保持 `FIN_OPS_QUEUE_BACKEND=postgres`。
`file-migration` 是可选迁移 worker，只有 legacy GridFS 和对象存储 secret 已配置时才加入
`FINOPS_OPTIONAL_WORKERS=file-migration`。

## 一键发布脚本

仓库根目录已提供一套只发布 `fin-ops`、不触碰 OA 源码的一键发布脚本。默认路径是 release-based 部署：

```bash
./scripts/deploy-oa.sh
```

脚本会完成：

- 本地重新构建 `web/dist`
- 打包生产运行所需的 `backend + web/dist + scripts + deploy/oa`
- 生成 `src/RELEASE.json`，记录 release 名称、Git commit、分支和构建信息
- 通过 `finops-prod` 免密 SSH 推送到：
  - `/opt/fin-ops/releases/<release-name>/src`
- 调用服务器 root-owned helper：
  - `/usr/local/sbin/finops-deploy-control check-release <release-name>`
  - `/usr/local/sbin/finops-deploy-control activate <release-name>`
- `activate` 会先用 `/etc/fin-ops/fin-ops.postgres-migrator.env` 执行 PostgreSQL schema migration，
  成功后才激活 API、RabbitMQ worker 和 dispatcher 指向该 release
- API 和 dispatcher release drop-in 会先清空基础 unit 继承的 `EnvironmentFile`，再加载
  `/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env`，避免历史
  `/opt/fin-ops/fin-ops.env` 覆盖 release `PYTHONPATH` 导致新服务仍导入 `/opt/fin-ops/current`
  旧代码
- `activate` 会把历史 `/opt/fin-ops/current` 归档到 `/opt/fin-ops/legacy-current-archives/current-<timestamp>`；
  release 模式只允许从 `/opt/fin-ops/releases/<release-name>/src` 运行，`current` 目录不再参与运行时
- `/health` 会暴露 runtime identity，包括工作目录、实际 `fin_ops_platform.__file__`、`PYTHONPATH`
  和 `RELEASE.json`。release 运行时若实际导入路径不在当前 release 的 `backend/src` 下，健康状态必须是
  `not_ready`
- 自动执行 `/usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/<release-name>/src`，确保常驻 worker 矩阵
  已安装、开机自启并重启到当前 release
- 验证前端 `index.html` 与激活 release 的 `web/dist/index.html` 哈希一致
- 清理可删除的旧 release，默认保留最近 8 个，并始终保护当前 active release

常用参数：

```bash
./scripts/deploy-oa.sh --dry-run
./scripts/deploy-oa.sh --skip-build
./scripts/deploy-oa.sh --release-name main-abcdef12-20260524170000
./scripts/deploy-oa.sh --no-activate
./scripts/deploy-oa.sh --keep-releases 12
```

说明：

- 这套脚本只发布 `fin-ops` 自己的前后端
- 不会改 OA Java/Vue 源码
- 也不会自动改 OA 数据库菜单；菜单和角色仍按本文后面的 SQL/菜单配置执行
- `git push main` 只更新远端仓库，不会自动改变服务器；服务器生效必须执行发布脚本并激活 release
- 默认拒绝从 dirty worktree 发布；确需发布未提交代码时必须显式加 `--allow-dirty`，但生产发布不建议这样做

历史服务器首次接入 release 自动化时，需要 root 一次性安装固定 helper。API 与 worker 必须共用
`/etc/fin-ops/fin-ops.common.env` 和 `/etc/fin-ops/fin-ops.secrets.env`，不要再让 API helper
引用历史 `/root/fin_ops_stage23_postgres_runtime.env`。否则 API 和 worker 会读取不同 secret 来源，
release 激活后可能出现 worker 正常但 `fin-ops.service` 因缺少 PostgreSQL DSN 反复退出。

```bash
sudo install -m 0755 -o root -g root \
  deploy/oa/bin/finops-deploy-control.sh \
  /usr/local/sbin/finops-deploy-control
sudo install -m 0755 -o root -g root \
  deploy/oa/bin/finops-ensure-runtime-workers.sh \
  /usr/local/sbin/finops-ensure-runtime-workers
printf '%s\n' \
  'finops-deploy ALL=(root) NOPASSWD: /usr/local/sbin/finops-deploy-control' \
  'finops-deploy ALL=(root) NOPASSWD: /usr/local/sbin/finops-ensure-runtime-workers /opt/fin-ops/releases/*/src' |
  sudo tee /etc/sudoers.d/finops-release-helpers >/dev/null
sudo visudo -cf /etc/sudoers.d/finops-release-helpers
```

安装后先验证 helper 合同，再发布：

```bash
grep -q '/etc/fin-ops/fin-ops.secrets.env' /usr/local/sbin/finops-deploy-control
! grep -q '/root/fin_ops_stage23_postgres_runtime.env' /usr/local/sbin/finops-deploy-control
sudo /usr/local/sbin/finops-deploy-control check-release <已上传的-release-name>
```

`scripts/deploy-oa.sh` 会在激活前检查服务器 helper 是否仍引用历史 root env；如果检查失败，会在
`activate` 之前中止，避免前端已发布但后端无法监听 `127.0.0.1:18001`。helper 的 `activate`
还必须先执行 schema migration、reset 旧 `EnvironmentFile` 并归档 legacy `/opt/fin-ops/current`；不要手工创建业务表、
不要用运行时账号代替 migrator 账号，也不要让旧 `/opt/fin-ops/fin-ops.env` 或 `/opt/fin-ops/current`
参与 release 运行时。
- `--reload-nginx` 只对旧 `legacy-current` 模式有意义；默认 release 模式不修改 nginx 配置，静态文件变更不需要 reload nginx
- 旧覆盖式部署仍保留为显式模式：

```bash
./scripts/deploy-oa.sh --mode legacy-current --host 139.155.5.132 --user root --reload-nginx
```

该模式会覆盖 `/www/wwwroot/fin-ops/dist` 和 `/opt/fin-ops/current/backend`，只用于历史兼容，不作为生产主发布路径。

release 会占用服务器磁盘。生产策略不是无限保留，而是默认保留最近 8 个 release，并保护当前 active release 和 deploy-control status 中仍被引用的 release。旧 root-owned 历史 release 如果当前部署用户没有权限删除，脚本会跳过并输出原因，需要单独做一次 root 清理。

按当前业务要求，初始配置至少要包含：

- `FIN_OPS_ALLOWED_USERNAMES=YNSYLP005`
- `FIN_OPS_ADMIN_USERNAMES=YNSYLP005`

后续再通过关联台里的“访问账户管理”维护：

- 可访问账户
- 只读导出账户
- 全操作账户

注意：

- 默认情况下，当前 app 设置保存后不会自动改 OA 数据库角色绑定
- 如果已配置 `FIN_OPS_OA_ROLE_SYNC_ENABLED=1` 和 OA MySQL 连接参数，则保存后会自动同步 OA 用户角色
- 未启用自动同步时，仍需要按下文“权限同步操作顺序”手工同步

权限与菜单的 SQL 模板：

- `deploy/oa/fin_ops_menu.mysql.sql`
- `deploy/oa/fin_ops_role_binding.mysql.sql`

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
- `deploy/oa/fin_ops_role_binding.mysql.sql`
- `deploy/oa/fin_ops_user_role_sync.mysql.sql`

## 权限同步操作顺序

当 `YNSYLP005` 在 app 的“访问账户管理”里修改权限后，生产环境必须按这个顺序同步：

1. 先保存 app 设置
2. 记录本次变更后的三类名单：
   - 只读导出账户
   - 全操作账户
   - 管理员账户（当前固定 `YNSYLP005`）
3. 在 OA 数据库或 OA 角色管理后台同步用户角色：
   - 只读导出账户 -> `finops_read_export`
   - 全操作账户 -> `finops_full_access`
   - `YNSYLP005` -> `finops_admin`
4. 把不再出现在 `allowed_usernames` 内的账户，从以上三类 OA 角色全部移除
5. 用对应账号重新登录 OA 验证菜单和页面行为

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
- [ ] 保存后按手工同步步骤更新 OA 角色，再验证菜单可见性一致

### 功能可用性

- [ ] 关联台可正常加载
- [ ] 搜索弹窗可正常搜索、详情、跳转定位
- [ ] 税金抵扣可正常加载和试算
- [ ] 成本统计可正常加载与导出
- [ ] 工作台导出、成本统计导出都可正常下载
- [ ] 已授权用户可访问 `workbench / tax / cost / export / search`

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
3. 回滚 `/fin-ops/` 前端静态资源
4. 回滚 `/fin-ops-api/` 后端服务
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

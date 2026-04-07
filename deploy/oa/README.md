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

## 一键发布脚本

仓库根目录已提供一套只发布 `fin-ops`、不触碰 OA 源码的一键发布脚本：

```bash
./scripts/deploy-oa.sh --reload-nginx
```

脚本会完成：

- 本地重新构建 `web/dist`
- 打包 `dist + backend`
- 通过 SSH 推送到 OA 服务器
- 覆盖：
  - `/www/wwwroot/fin-ops/dist`
  - `/opt/fin-ops/current/backend`
- 重启 `fin-ops.service`
- 可选执行 `nginx -t && nginx -s reload`

常用参数：

```bash
./scripts/deploy-oa.sh --dry-run
./scripts/deploy-oa.sh --skip-build
./scripts/deploy-oa.sh --skip-pip
./scripts/deploy-oa.sh --host 139.155.5.132 --user root --reload-nginx
```

说明：

- 这套脚本只发布 `fin-ops` 自己的前后端
- 不会改 OA Java/Vue 源码
- 也不会自动改 OA 数据库菜单；菜单和角色仍按本文后面的 SQL/菜单配置执行

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
- `/fin-ops-api/` -> Python 后端
- `/api/` 和 `/imports/` 在 `/fin-ops/` 页面内反代到 `/fin-ops-api/`

注意：

- `fin-ops` 前端页面内部实际仍然请求 `/api/*`
- 因为页面和 API 都在同域下，所以浏览器 cookie 仍然能被携带
- 前端还会主动附带 `Authorization`

## OA 菜单配置

OA 菜单仍然按 Prompt 29 的口径配置：

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

- `OA 集成当前 app 技术方案.md`
- `docs/dev/oa-menu-iframe-integration.md`
- `docs/superpowers/specs/2026-04-03-oa-shell-auth-visibility-design.md`
- `docs/superpowers/plans/2026-04-03-oa-shell-auth-visibility.md`

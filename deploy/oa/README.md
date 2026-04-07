# OA 同域部署与联调说明

日期：2026-04-03

## 目标

把 `fin-ops-platform` 作为 OA 域下的受控子系统部署，并满足：

- 前端页面挂载在 `/fin-ops/`
- Python 后端挂载在 `/fin-ops-api/`
- 页面通过 OA 菜单 iframe 进入
- 直接复用 OA 的 `Admin-Token`
- 没有 `finops:app:view` 的用户在菜单和 API 两层都被拒绝

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
VITE_APP_BASE_PATH=/fin-ops/
```

补充说明：

- `FIN_OPS_OA_BASE_URL` 必须指向 OA 网关对外地址
- `FIN_OPS_OA_REQUIRED_PERMISSION` 默认就是 `finops:app:view`
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

按当前业务要求，初始放行账号可先配置为：

- `FIN_OPS_ALLOWED_USERNAMES=YNSYLP005`

后续再通过关联台里的“访问账户管理”继续维护白名单。

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

### 功能可用性

- [ ] 关联台可正常加载
- [ ] 搜索弹窗可正常搜索、详情、跳转定位
- [ ] 税金抵扣可正常加载和试算
- [ ] 成本统计可正常加载与导出
- [ ] 工作台导出、成本统计导出都可正常下载
- [ ] 已授权用户可访问 `workbench / tax / cost / export / search`

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

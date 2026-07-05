# 外部系统边界

## OA 系统

OA 提供：

- 登录态。
- 菜单和 iframe 容器。
- 用户信息和权限。
- 付款申请、报销单、项目等源数据。

本系统不修改 OA 源业务数据，只读取、映射、缓存和投影。

## MongoDB

当前有两类 Mongo：

- OA Mongo：外部只读源。
- App Mongo：本系统状态、文件、缓存和 read model。

不要混淆两者权限。生产环境 app 对 OA Mongo 应保持只读。

## 部署资产

OA 同域部署相关文件在 `deploy/oa/`：

- `README.md`
- `nginx.fin-ops.conf.example`
- `env/*.env.example`
- `fin_ops_menu.mysql.sql`
- `fin_ops_role_binding.mysql.sql`
- `fin_ops_user_role_sync.mysql.sql`

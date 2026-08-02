# 外部系统边界

## OA 系统

OA 提供：

- 登录态。
- 菜单和 iframe 容器。
- 用户信息和权限。
- 付款申请、报销单、项目等源数据。

本系统不修改 OA 源业务数据，只读取、映射、缓存和投影。

## MongoDB 与 PostgreSQL

- OA Mongo：外部只读源，只允许同步 owner 读取后写入 PostgreSQL canonical facts。
- PostgreSQL：生产 app 状态、业务事实、关系、任务和 read model 的唯一读写库。
- 历史 App Mongo：离线迁移遗留物，不属于 runtime、回滚、审计、缓存或 read model 链路。

生产环境 app 对 OA Mongo 必须保持只读，也不得回退读取历史 App Mongo。

## 部署资产

OA 同域部署相关文件在 `deploy/oa/`：

- `README.md`
- `nginx.fin-ops.conf.example`
- `env/*.env.example`
- `fin_ops_menu.mysql.sql`
- `fin_ops_user_role_sync.mysql.sql`

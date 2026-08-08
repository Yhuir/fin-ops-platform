# 安全与权限基线

`fin-ops-platform` 作为 OA 内嵌财务子系统，不单独暴露登录体系。OA 登录态只证明当前账号身份；APP 访问级别由固定管理员和 Settings canonical ACL 独立决定。

## 登录与会话

- 前端从 OA 同域 cookie 读取 `Admin-Token`。
- 请求后端时携带 `Authorization: Bearer <token>`。
- 后端通过 OA 会话接口识别当前用户，不信任前端菜单可见性。
- OA 身份中的 roles、permissions（包括 `finops:app:view`）仅是信息字段，不授予 APP 访问。历史 `FIN_OPS_ALLOWED_*` / `FIN_OPS_READONLY_EXPORT_*` admission 环境名单已退役，也不构成 fallback。
- 未登录或 token 失效返回 `401`；已登录但无权限返回 `403`。
- 运行时不提供 synthetic dev/test identity。本地开发同样必须携带真实 OA token；历史 dev/test auth 环境变量已从运行时代码删除，遗留值不会被读取，也不能创建登录态或授予权限。
- 受保护 API 在请求体解析和业务 route 之前统一执行写权限策略：`GET/HEAD/OPTIONS` 与登记的纯计算/preview POST 可读，其余 `POST/PUT/PATCH/DELETE` 默认视为写入并要求 `can_mutate_data=true`；未知新写 route 同样 fail closed。

## 权限分层

当前长期口径：

- 拒绝：除 `YNSYLP005` 外，账号不在 canonical ACL `accounts` 中即为 `denied`，页面、直接 URL 和受保护 API 均不可访问。
- 只可看和只可导出：允许查询和导出，不允许写操作。
- 所有操作均可：允许业务处理操作。
- 管理员：`YNSYLP005` 固定拥有管理能力，包括访问账户管理和数据重置。
- `YNSYLP005` 是唯一受保护管理员；应用的任何 HTTP 请求都不能新增、删除、提升、降级或轮换管理员。
- 普通设置 `GET/POST /api/workbench/settings` 不读取、返回或写入 ACL；提交任何历史 ACL key 返回 `400 access_control_write_forbidden`。
- 只有受保护管理员可调用 `GET/PUT /api/workbench/settings/access-control` 管理其他账户。可分配 tier 只有 `full_access` 和 `read_export_only`；删除条目才表示 `denied`。写入使用 `expected_version`、数据库 CAS、同事务 durable audit；`409` 不覆盖新版本。
- `/settings` 的“访问账户权限”是唯一人工 ACL 输入。用户名等值与去重使用 casefold comparison key，对外保留 OA `sys_user.user_name` canonical spelling；大小写冲突、跨 tier 重复和非 canonical 管理员均 fail closed。
- 非管理员每次权限判断最多取一次 canonical ACL snapshot；snapshot 缺失、格式错误或 provider 失败均返回 `denied`，不使用 OA role/permission/env 恢复权限。ACL 删除后，同一 OA 身份的下一次 session/API 判断立即拒绝，不等待 identity cache 过期。
- ACL 真实变化才投影到 `finops_read_export` / `finops_full_access` / `finops_admin` 三个专用 OA 角色。`finops:app:view` 只定位 OA 菜单，菜单可见性不能反向成为 APP 授权证据；历史非专用角色绑定的精确清理与回滚由受控部署负责。
- ACL semantic no-op 不写 PostgreSQL/audit，不调 OA。真实变化在 OA 目标失败时返回 `502 oa_role_sync_failed`；已投影后 PostgreSQL 失败要求补偿，补偿无法确认时返回 `503 access_control_sync_inconsistent`，不得伪报成功。
- 写入 actor、导入 owner 和后台任务 owner 只从后端已认证 session 派生，不接受 body/form 中的 `actor`、`createdBy`、`imported_by` 冒充身份。
- 已删除未进入正式模块边界的 legacy HTTP families：`/integrations/oa*`、`/projects*`、`/ledgers*`、`/reminders*`、`/matching/*`；正式 OA 同步只通过 durable queue/runtime worker 运维入口，项目设置使用 `/api/workbench/settings/projects*`。
- PostgreSQL migration `0132` 把唯一管理员约束固化为 validated CHECK。发布必须先停止旧 API，再执行 migration，禁止自动回滚到没有 `settings-access-control-v1` 指纹的 release。

## 数据保护

- 不在日志中输出 OA token、数据库密码、导入文件敏感内容或完整附件正文。
- 导入文件和附件应存储在受控存储中，生产环境优先使用独立对象存储或受控 GridFS。
- 数据重置、权限修改、批量撤回等高风险操作必须记录操作者、时间、参数摘要和结果。
- 数据重置必须由真实 OA admin session 并通过当前 OA 密码复核；应用不存在固定 token 或默认重置密码。

## 相关文档

- `docs/architecture/oa-integration.md`
- `docs/product-specs/settings-and-access-control.md`
- `deploy/oa/README.md`

# 权限与审计模块维护入口

- Module key: `permissions-and-audit`
- 类型：资源模块 / 横切安全边界
- Route: `N/A`
- Page key: `N/A`

## 修改前必读

- `SECURITY.md`
- `docs/product-specs/platform-settings-health.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/dev/testing-closure-dependency-map.md`
- `docs/modules/settings/README.md`
- `docs/modules/app-health-operations/README.md`

## 代码入口

- `SECURITY.md`
- `backend/src/fin_ops_platform/app/auth.py`
- `backend/src/fin_ops_platform/services/access_control_service.py`
- `backend/src/fin_ops_platform/services/audit.py`
- `backend/src/fin_ops_platform/app/server.py` 中 session、read session、mutation session、admin-only route helpers
- `web/src/features/session/api.ts`
- `web/src/contexts/SessionContext.tsx`
- `web/src/components/auth/SessionGate.tsx`
- `web/src/contexts/AppHealthStatusContext.tsx`
- 各页面 `useSessionPermissions()` / `useOptionalSessionPermissions()` 调用点
- 各业务 service / UoW 中写入 audit log 的边界

## 当前边界

权限与审计是横切安全边界，不属于单个页面，也不走 read model 分发。当前边界包括：

- OA 会话：前端从 `Admin-Token` cookie 读取 token 并发送 `Authorization: Bearer ...`；后端只信任 OA identity service 和 access control 判断。应用运行时不存在 synthetic dev/test session；本地开发也使用真实 OA token，假身份仅存在于测试夹具。
- 页面访问：精确 `YNSYLP005` 固定为权限管理员并拥有全部页面；其他账号每次只从一份 canonical Settings ACL snapshot 得到 `allowed_page_keys`。账号缺席、页面未勾选或 provider 缺失/非法/失败均拒绝访问。OA role/permission、退役 env 和 `finops:app:view` 不授予 APP 页面权限。
- 后端 guard：所有 protected API 必须先解析 OA session，并由 `route_access_policy.py` 将 API 路由映射到页面 key；未登记的受保护路由 fail closed。访问账户、OA 凭据、数据重置和操作历史等 control plane 额外要求 `can_admin_access`。
- 前端权限：侧栏只展示 `allowed_page_keys` 中的页面，直达未授权页面会跳转到首个可访问页面；前端仅改善体验，不能替代后端校验。
- 页面内能力：被授权页面沿用现有完整业务规则，不再区分“只读/导出”和“所有操作”。系统健康写门禁独立于账户页面权限。
- 现金页面：独立 `cash` key，005 才能给其他账号配置；现金写操作不进入全局操作历史，现金权限不授予普通后台任务或 System Audit 数据访问。具体双审计排除与后端先行范围见 `boundary-io.md`。
- 审计：高风险动作、设置变化、标签规则、关系确认/撤回、批量提交/撤回、数据重置、导出等必须记录 actor、动作、对象、金额或参数摘要。
- 敏感数据：不得在 API、日志、audit metadata、前端 state 中泄露 OA token、密码、数据库 DSN、凭据密文、导入文件敏感正文或完整附件正文。

## 权限模型

| 决策 | canAccessApp | canAdminAccess | 页面能力 |
| --- | --- | --- | --- |
| 无任何页面 | false | false | API 403 / 前端 forbidden |
| 至少一个页面 | true | false | 只进入勾选页面；页面内执行正常业务流程 |
| 固定 `YNSYLP005` | true | true | 全部页面及 admin-only control plane |

Settings ACL 不提供可写管理员字段，也不存在操作层级；普通账号只有 `username + page_keys`。

## 维护触发器

## Protected administrator contract

- `YNSYLP005` 是代码和数据库约束固定的唯一管理员；permissions 模块不提供动态 admin provider、环境变量 admin list 或可写 admin tier。
- `AccessControlService` 每次非管理员 session/API 决策最多获取一次带 `access_control_version` 的 normalized ACL snapshot；provider 失败时 fail closed，protected admin 不读取 provider并保留恢复入口。ACL 删除后同一 OA identity 的下一次判断立即撤权。
- permissions 只拥有 identity/session/page-set 判定和 audit 合同，不保存 ACL。ACL command/persistence 归 settings；OA 角色写入归 OA integration。
- `finops:app:view` 只是 OA fixed-menu selector；permissions evaluator 不读取该 marker，OA integration 不能反向决定 APP 页面权限。
- 成功 ACL audit 与 canonical ACL/version 同事务，使用后端 session actor 和受信 HTTP adapter request id；客户端 body actor 或不受信 request-id header 不能成为权威事实，no-op/409/502/503 不留下成功 audit。

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护权限与审计横切 Spec-first Browser/API 验收合同。
- `e2e-coverage.md`：维护权限与审计 Spec-first 合同到自动化覆盖的映射。
- `write-entry-inventory.md`：维护 `PERM-E2E-003` 页面写入口权限矩阵和 Browser 覆盖缺口。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

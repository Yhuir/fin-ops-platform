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

- OA 会话：前端从 `Admin-Token` cookie 读取 token 并发送 `Authorization: Bearer ...`；后端只信任 OA identity service 和 access control 判断。
- 访问层级：`denied`、`read_export_only`、`full_access`、`admin`。
- 后端 guard：所有 protected API 必须先解析 OA session；写入 API 必须二次判断 `can_mutate_data`；高风险 admin API 必须判断 `can_admin_access`。
- 前端权限：页面按钮、drawer、导入、数据重置、运维入口按 session 权限隐藏或禁用，但不能替代后端校验。
- 导出权限：只读导出用户可以查询和导出，不能写入、重置或运维修复。
- 审计：高风险动作、设置变化、标签规则、关系确认/撤回、批量提交/撤回、数据重置、导出等必须记录 actor、动作、对象、金额或参数摘要。
- 敏感数据：不得在 API、日志、audit metadata、前端 state 中泄露 OA token、密码、数据库 DSN、凭据密文、导入文件敏感正文或完整附件正文。

## 权限层级

| 层级 | canAccessApp | canMutateData | canAdminAccess | 典型能力 |
| --- | --- | --- | --- | --- |
| `denied` | false | false | false | API 403 / 前端 forbidden |
| `read_export_only` | true | false | false | 查询和导出；不能写入、导入确认、数据重置 |
| `full_access` | true | true | false | 业务写入；不能访问账户管理、数据重置、运维 dashboard、OA 凭据 |
| `admin` | true | true | true | 管理账户、数据重置、AppHealth 运维、OA 凭据 |

`YNSYLP005` 是固定 admin；settings 中的 admin 用户也必须自动进入 allowed。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

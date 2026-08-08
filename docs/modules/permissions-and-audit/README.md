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
- 访问层级：精确 `YNSYLP005` 固定为 `admin`；其他账号每次只从一份 canonical Settings ACL snapshot 得到 `read_export_only` / `full_access`，列表缺席或 provider 缺失/非法/失败均为 `denied`。OA role/permission、三项退役 env 和 `finops:app:view` 不授予 APP tier。
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

`YNSYLP005` 是唯一固定 admin；Settings ACL 不提供可写 admin tier，其他账号只能由完整 full/read memberships 或列表缺席分别得到 full/read/denied。

## 维护触发器

## Protected administrator contract

- `YNSYLP005` 是代码和数据库约束固定的唯一管理员；permissions 模块不提供动态 admin provider、环境变量 admin list 或可写 admin tier。
- `AccessControlService` 每次非管理员 session/API 决策最多获取一次带 `access_control_version` 的 normalized ACL snapshot；provider 失败时 fail closed，protected admin 不读取 provider并保留恢复入口。ACL 删除后同一 OA identity 的下一次判断立即撤权。
- permissions 只拥有 identity/session/tier 判定和 audit 合同，不保存 ACL。ACL command/persistence 归 settings；OA 角色写入归 OA integration。
- `finops:app:view` 只是 OA fixed-menu selector；permissions evaluator 不读取该 marker，OA integration 不能反向决定 APP tier。
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

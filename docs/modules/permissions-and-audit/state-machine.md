# 权限与审计状态机

> 修改权限、会话、审计、敏感数据、API guard 或 UI 权限状态前必须读取本文件。权限事实必须来自后端 session/access control；前端隐藏/禁用不能替代后端校验。

## 业务状态

### Session

- `loading`：前端正在请求 `/api/session/me`。
- `authenticated`：后端返回 allowed 且包含 user、roles、permissions、access tier。
- `forbidden`：后端识别身份，但 `allowed=false`。
- `expired`：无 token、token 过期或 OA session invalid；API 返回 401。
- `error`：OA 会话接口超时、网络失败或未知错误；前端提供 retry。

### Access tier

- `denied`：不可访问 app，不能读写。
- `read_export_only`：可读、可导出；`can_mutate_data=false`。
- `full_access`：可读写普通业务；`can_admin_access=false`。
- `admin`：可读写、可管理账户、OA 凭据、数据重置、AppHealth 运维。

允许流转：

- settings 保存 allowed/readonly/admin 后，下一次 session resolve 根据新配置产出新 tier。
- dynamic provider 失败时，如果用户已有 required permission，仍允许 full access，并记录 warning。
- local dev auth 仅在显式 env 开启；unittest default auth 仅测试场景。

禁止流转：

- 前端 request body 中的 actor 覆盖后端 session actor。
- read-only 用户执行写入、导入确认、数据重置、规则保存或 admin 运维。
- full access 非 admin 维护 OA 凭据、访问账户管理、数据重置、AppHealth dashboard。
- worker/service 直接 import HTTP auth、解析 cookie/header 或依赖 Flask response。

### Audit

- `pending`：写入 service/UoW 构造 audit event。
- `recorded`：业务事实、audit、dirty/outbox 在同一事务或等价原子边界内提交。
- `rolled_back`：业务写入失败时 audit 不应单独留下。
- `failed`：audit 或 outbox 失败应回滚对应业务事实，不能产生半写入。

## UI 状态

- loading：SessionGate 显示 OA 会话校验；权限未确认前不渲染业务页面。
- empty：权限配置列表为空时允许 admin 添加；非 admin 不展示管理入口。
- error：session 校验失败显示 retry；API 403/401 显示明确权限或会话错误。
- stale/refreshing：权限本身不走 read model；如果 App Status blocked，`useCanMutateWithHealth` 会阻断写入。
- permission disabled/hidden：readonly 隐藏/禁用写入；full access 隐藏 admin-only；admin 显示高风险入口。
- export：readonly export 用户可进入导出流程；写入型 drawer/dialog 不可用。

## Read Model / Worker 状态

## ACL 权限判定

| tier | generic settings POST | access-control GET/PUT | admin-only health/credentials/reset |
| --- | --- | --- | --- |
| `admin`（仅 `YNSYLP005`） | 允许 | 允许 | 允许 |
| `full_access` | 允许；ACL key 明确 400 | 403 | 403 |
| `read_export_only` | 403 | 403 | 403 |
| `denied` | 403 | 403 | 403 |

页面隐藏只用于体验，所有状态都必须由后端再次判定。管理员身份没有 APP 内状态迁移。

- 权限和审计本身不生成 read model freshness。
- App Status 会消费 session/permission 作为全局 blocked/red 的一部分，但不替代后端 API guard。
- Worker/service 不得依赖 `Application`、`app.server`、`app.auth`、HTTP response、cookie/header。
- 失败恢复：权限配置错误通过 settings 修正；审计/事务失败通过业务 UoW rollback 和对应 service tests 定位；真实 OA role sync 失败按 settings/operations runbook 处理。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| - | 初始骨架 | 待补充 | - |
| 2026-06-17 | 补齐 Browser 权限角色矩阵 | 新增 read_export_only/full_access/admin 真实 Chromium 矩阵；只读用户逐页可读且不触发 mutation API，settings/tax/import/no-OA 写入口受控；同步修复导入页和免 OA 页 UI 权限门禁 | `cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`、`cd web && npm test -- --run src/test/ImportCenterPage.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/WorkbenchSelection.test.tsx src/test/App.test.tsx src/test/SessionGate.test.tsx src/test/SessionApi.test.ts` |
| 2026-06-11 | 补齐权限与审计测试闭环状态机 | 将 session、access tier、UI 权限、API guard、audit 原子性和敏感数据保护纳入统一维护边界 | `tests.test_auth_guard`、`tests.test_session_api`、`tests.test_audit_service`、`web/src/test/SessionGate.test.tsx`、`web/src/test/SettingsPage.test.tsx` |

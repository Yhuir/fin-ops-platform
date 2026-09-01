# 权限与审计状态机

> 修改权限、会话、审计、敏感数据、API guard 或 UI 权限状态前必须读取本文件。权限事实必须来自后端 session/access control；前端隐藏/禁用不能替代后端校验。

## 业务状态

### Session

- `loading`：前端正在请求 `/api/session/me`。
- `authenticated`：后端返回 allowed 且包含 user、roles、permissions、`allowed_page_keys`。
- `forbidden`：后端识别身份，但 `allowed=false`。
- `expired`：无 token、token 过期或 OA session invalid；API 返回 401。
- `error`：OA 会话接口超时、网络失败或未知错误；前端提供 retry。

### Page access

- `denied`：普通账号没有任何 `allowed_page_keys`，不可访问 app。
- `page_authorized`：普通账号至少有一个页面 key，只能进入勾选页面，页面内按原业务规则执行。
- `admin`：固定 `YNSYLP005` 拥有全部页面，并可管理账户、OA 凭据、数据重置和操作历史。

允许流转：

- 精确 `YNSYLP005` 在 provider 前直接产出 `admin`；该状态不能通过 APP 流转。
- 其他账号在同一 `access_control_version` snapshot 中按 `page_access_accounts[].page_keys` 产出允许页面集合；账号缺席或页面集合为空产出 `denied`。
- Settings ACL commit 后，下一次 session/global guard/module guard 读取新 snapshot；删除账号立即从允许层级流转到 `denied`，不等待 OA identity cache。
- snapshot provider 缺失、payload 非法或调用失败均流转为 `denied` 并记录固定 secret-safe warning；OA role/permission/env 不提供恢复边。
- local dev auth 仅在显式 env 开启；unittest default auth 仅测试场景。

禁止流转：

- 前端 request body 中的 actor 覆盖后端 session actor。
- 普通账号访问未勾选页面或 admin-only control plane。
- worker/service 直接 import HTTP auth、解析 cookie/header 或依赖 Flask response。

### Audit

- `pending`：写入 service/UoW 构造 audit event。
- `recorded`：业务事实、audit、dirty/outbox 在同一事务或等价原子边界内提交。
- `rolled_back`：业务写入失败时 audit 不应单独留下。
- `failed`：audit 或 outbox 失败应回滚对应业务事实，不能产生半写入。

ACL command 的审计与 Settings 状态机使用同一 snapshot version/outcome：

- `no_op` / `conflict` / `oa_target_failed`：无成功 audit。
- `committed` / `commit_recovered`：canonical version 恰为 `expected_version + 1` 且 mutation audit 存在，actor/request id 与当前 command 一致。
- `persistence_failed_compensated` / `commit_rolled_back_compensated`：canonical version 保持旧值、无成功 audit，OA 恢复旧 memberships。
- `compensation_failed_or_unknown`：返回 `access_control_sync_inconsistent` 并 fail closed，不能从 OA marker 或不完整 audit 猜测成功。

## UI 状态

- loading：SessionGate 显示 OA 会话校验；权限未确认前不渲染业务页面。
- empty：权限配置列表为空时允许 admin 添加；非 admin 不展示管理入口。
- error：session 校验失败显示 retry；API 403/401 显示明确权限或会话错误。
- stale/refreshing：权限本身不走 read model；如果 App Status blocked，`useCanMutateWithHealth` 会阻断写入。
- permission hidden：普通账号隐藏未授权页面和 admin-only control plane；被授权页面不再按账户拆分读写能力。
- health blocked：系统健康状态可以独立阻断写入，但不改变账户的页面授权。

## Read Model / Worker 状态

## ACL 权限判定

| session decision | 已授权页面 API | access-control GET/PUT | admin-only credentials/reset/history |
| --- | --- | --- | --- |
| `admin`（仅 `YNSYLP005`） | 允许 | 允许 | 允许 |
| `page_authorized` | 页面 key 命中时允许 | 403 | 403 |
| `denied` | 403 | 403 | 403 |

页面隐藏只用于体验，所有状态都必须由后端再次判定。管理员身份没有 APP 内状态迁移。

| evaluator 输入 | 结果 |
| --- | --- |
| username 精确为 `YNSYLP005` | `admin`；零 snapshot provider I/O |
| username 在 snapshot 且 page keys 非空 | `page_authorized` + 精确页面集合 |
| username 缺席 | `denied` |
| provider 缺失、payload 非法或失败 | `denied`；固定 secret-safe warning |
| OA role/permission、三项退役 env、`finops:app:view` marker | 信息/selector only；不得改变上述结果 |

- 权限和审计本身不生成 read model freshness。
- App Status 会消费 session/permission 作为全局 blocked/red 的一部分，但不替代后端 API guard。
- Worker/service 不得依赖 `Application`、`app.server`、`app.auth`、HTTP response、cookie/header。
- 失败恢复：权限配置错误通过 settings 修正；审计/事务失败通过业务 UoW rollback 和对应 service tests 定位；真实 OA role sync 失败按 settings/operations runbook 处理。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-09-02 | 页面级访问替代账户权限层级 | 普通账户只保存页面集合；勾选页面内保留正常业务能力；005 固定全页与管理控制面；旧权限字段只允许在一次性迁移/切换预检中读取 | `tests.test_auth_guard`、`tests.test_session_api`、`tests.test_route_access_policy`、`web/e2e/permissions-role-matrix.spec.ts` |
| 2026-08-02 | 收敛 fixed 005 + canonical ACL evaluator 与审计结果 | 删除 permission/role/env grant；single snapshot fail closed；Settings 与 permissions 共用 version/no-op/conflict/projection/persistence/compensation outcome | `tests.test_session_api`、`tests.test_auth_guard`、`tests.test_permissions_write_entry_inventory`、`web/e2e/permissions-role-matrix.spec.ts` |
| - | 初始骨架 | 待补充 | - |
| 2026-06-17 | 历史：补齐旧角色矩阵 | 当时覆盖旧的读写分层；该模型已由 2026-09-02 页面级访问模型取代，不是当前合同 | 历史记录 |
| 2026-06-11 | 补齐权限与审计测试闭环状态机 | 将 session、access tier、UI 权限、API guard、audit 原子性和敏感数据保护纳入统一维护边界 | `tests.test_auth_guard`、`tests.test_session_api`、`tests.test_audit_service`、`web/src/test/SessionGate.test.tsx`、`web/src/test/SettingsPage.test.tsx` |

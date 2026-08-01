---
phase: 13
slug: settings-improvements
status: complete
researched: 2026-08-02
research_mode: constrained-local-fallback
---

# Phase 13 — T0-01 Settings ACL 提权修复研究

## 结论

T0-01 不是一个只补 `can_admin_access` 的 route bug，而是同一份 ACL 同时混入普通 settings DTO、`AppSettingsService.update_settings(...)`、三组动态鉴权 provider、OA role sync、两个前端设置入口和整行 JSON settings writer 后形成的完整越权链。

最小生产级修复是：

1. `YNSYLP005` 保持唯一、不可由 APP 修改的 protected administrator；本 phase 不新增管理员配置系统。
2. 普通 `GET/POST /api/workbench/settings` 完全移除 ACL I/O；旧 ACL 字段出现时明确拒绝。
3. 复用 `SettingsApiRoutes` 与现有 admin session resolver，新增唯一的 admin-only `GET/PUT /api/workbench/settings/access-control`。
4. 复用 `app.app_settings`，新增独立 `access_control_version`；repository 在 `SELECT ... FOR UPDATE` 后只合并 ACL keys，并在同一 PostgreSQL 事务写 `audit.events`。
5. 所有普通 settings writer 在 state-store/repository 这一公共持久化边界保留最新 ACL，避免并发旧 snapshot 覆盖。
6. 只有真实 ACL 变化调用现有同步 OA role sync；普通 settings 保存和 ACL semantic no-op 都是零 OA I/O。
7. 鉴权每次只取一份 ACL snapshot；删除动态 admin provider 和三次分散读取。
8. 删除设置页全局保存、关联台列顺序自动保存、`WorkbenchSettingsModal`、pending-invoice fallback、mocks/E2E 中的旧 ACL payload。

不需要新表、新 service 层、新 worker、新 outbox event、新 cache、新状态库或通用权限框架。

## 研究过程说明

`gsd-phase-researcher` 因本会话协作槽位被既有审计 Agent 占满而无法按角色新建；三次复用已完成 Agent 的受限研究均异常阻塞且未生成文件，已全部终止并确认无半成品。因此本文件按 GSD fallback 由主 Agent 使用 CodeGraph、模块边界文档和目标代码直接完成。该降级不改变事实结论，但计划 checker 必须把“研究未由独立 Agent 交付”作为审阅背景。

## 当前漏洞链（code-proven）

### HTTP 入口

- `backend/src/fin_ops_platform/app/routes_settings.py::SettingsApiRoutes.update_settings`
  - 普通 `POST /api/workbench/settings` 读取 `allowed_usernames`、`readonly_export_usernames`、`admin_usernames`，缺省均为 `[]`。
  - `_resolve_settings_mutation_session(...)` 只校验 `session.can_mutate_data`。
  - full-access 的权限合同正是 `can_mutate_data=true`、`can_admin_access=false`。
- 因此 full-access 用户可直接构造 ACL 字段；前端是否隐藏访问账户区不构成后端安全边界。

### Service 与外部同步

- `backend/src/fin_ops_platform/services/app_settings_service.py::AppSettingsService.update_settings`
  - 签名直接接受三组 ACL 数组。
  - `_normalize_settings(...)` 把所有 `admin_usernames` 与 `DEFAULT_ADMIN_USERNAME` 合并，再把 admin 自动加入 allowed。
  - 每次普通 settings 保存都会先调用 `OARoleSyncService.sync_access_control(...)`，即使 ACL 未变化。
  - OA sync 成功后才保存 app settings；保存失败时尝试同步回旧 snapshot。这是当前跨库补偿语义。
- `backend/src/fin_ops_platform/services/oa_role_sync_service.py`
  - `_build_assignments_from_snapshot(...)` 信任 snapshot 中三组用户名。
  - `MySQLOARoleSyncExecutor.apply(...)` 在 OA MySQL 一个事务内删除旧 fin-ops 角色并逐项插入目标角色。

### 下一次鉴权立即生效

- `backend/src/fin_ops_platform/app/server.py` 把：
  - `get_allowed_usernames`
  - `get_readonly_export_usernames`
  - `get_admin_usernames`
  分别注入 `AccessControlService.from_environment(...)`。
- `backend/src/fin_ops_platform/services/access_control_service.py::evaluate`
  - 同时合并固定 admin、env admin 与 dynamic admin。
  - username 命中 admin 集合后返回 `can_admin_access=true`。
- 所以被写入的动态 admin 在下一次 session 解析时直接获得 App Health、OA credential、data reset 等 admin 能力。

### 缺省清空与并发覆盖

- Route 对三组 ACL 使用 `payload.get(..., [])`。
- Service 用整份 normalized snapshot 覆盖持久化 settings。
- `PostgresOpsTaxEtcRepository._save_settings_with_executor(...)` 是整行 JSONB upsert；当前没有 ACL family 级 merge/CAS。
- 因此旧前端、部分 payload 或并发普通 settings 写均可清空/覆盖 ACL；仅在 route 加 admin guard不能解决该问题。

## 已发现的原计划遗漏

### 1. 关联台列顺序自动保存仍携带 ACL

`web/src/pages/ReconciliationWorkbenchPage.tsx::handleReorderPaneColumns` 调用 `saveWorkbenchSettings(...)` 时复制 `nextSettings.accessControl` 三组数组。若后端严格拒绝旧字段但不改此 caller，关联台列拖拽保存会立即回归失败。

### 2. `WorkbenchSettingsModal` 是第二套旧 ACL UI

`web/src/components/workbench/WorkbenchSettingsModal.tsx` 自己维护 `managedAccessAccounts`、`adminUsernames`、访问账户 section 和普通 settings 保存。它与 `/settings` 页面重复拥有 ACL 编辑职责。目标态必须删除该 modal 中的访问账户 section、draft/state/helper/prop/callback，不得把它改接新 ACL endpoint 后继续保留第二入口。

### 3. pending-invoice fallback 会重放 ACL

`backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py::AppSettingsPendingInvoiceRulesGateway.update_pending_invoice_rule_groups` 保留一个 `getattr` fallback：先从 generic settings response 取 `access_control`，再调用 `update_settings(...)` 重放三组 ACL。当前正式 service 已有专属 `update_pending_invoice_rule_groups(...)`，这个 fallback 是旧链路，应删除，不应适配新合同。

### 4. 普通 settings 的所有 writer 都要在持久化边界保留 ACL

除了 HTTP route，`AppSettingsService` 的项目、标签规则、成本/往来设置，以及 `turnover_ledger_write_adapters.py`、`bank_flow_rule_batch_application_service.py`、`input_invoice_usage_payment_rules.py`、`settings_normalization_ops.py` 等均可写 `app.app_settings`。逐 caller 补 copy 是不可靠的；公共 state-store/repository writer 必须默认保留当前 ACL family，专属 ACL command 才能修改它。

### 5. 旧 env admin 是第二管理员事实源

`AccessControlService.from_environment()` 当前读取 `FIN_OPS_ADMIN_USERNAMES`，同时代码又固定 `DEFAULT_ADMIN_USERNAME`，DB settings 还持久化 `admin_usernames`。目标态不能保留三份管理员 authority。

本 phase 的最小口径：`YNSYLP005` 由代码/部署合同固定为唯一 protected administrator；退休 `FIN_OPS_ADMIN_USERNAMES` 的运行时授权作用，DB 中 `admin_usernames` 只保留固定派生值和 CHECK 约束，不再是可写业务输入。未来管理员轮换是独立的受控 migration/deploy，不在本 phase 做通用配置。

## 目标模块边界与 I/O

| 模块 | 负责 | 输入 | 输出 | 禁止 |
| --- | --- | --- | --- | --- |
| `settings` | generic settings command、专属 ACL command、version/CAS 编排 | 普通 settings DTO；admin-only accounts DTO；session actor | generic settings payload；ACL payload；canonical settings + audit | route 写 SQL；generic command 接受 ACL；跨模块整 snapshot rollback |
| `permissions-and-audit` | session 解析、admin/mutation guard、一次 ACL snapshot 评估、audit contract | OA identity；ACL snapshot | `AccessDecision`；durable audit schema | 前端-only auth；动态 admin provider；service 读 cookie/header |
| `oa-integration` | 消费归一 ACL snapshot并同步 OA roles | readonly/full accounts + fixed admin | OA MySQL role assignments | 从 HTTP/body决定 actor或 admin；普通 settings 触发同步 |
| state store/repository | row lock、family merge、CAS、settings+audit 原子提交 | normalized payload / ACL command | committed snapshot or conflict | 决定业务权限；静默覆盖并发 ACL |
| frontend settings | admin-only ACL load/edit/save；普通 settings save | session capability + two API payloads | 独立 feedback/conflict state | global save 混写 ACL；第二套 modal ACL UI |

## 目标 API 合同

### Generic settings

- `GET /api/workbench/settings`
  - response 不含 `access_control`、`allowed_usernames`、`readonly_export_usernames`、`admin_usernames`。
- `POST /api/workbench/settings`
  - 保持 full-access 可用。
  - body 出现上述任一旧 ACL key 或 `access_control` 时返回 `400 access_control_write_forbidden`。
  - omission 不再等于清空；service 也不再接收 ACL 参数。

### Dedicated ACL

- `GET /api/workbench/settings/access-control`
  - 必须先走现有 admin session resolver。
  - response：
    - `version: integer`
    - `administrator: {username: "YNSYLP005", access_tier: "admin", protected: true}`
    - `accounts: [{username, access_tier: "full_access"|"read_export_only"}]`
- `PUT /api/workbench/settings/access-control`
  - admin-only；先鉴权，再解析/校验 body。
  - request 仅接受 `expected_version` 和 `accounts`。
  - actor 只来自 session；拒绝 body actor、`admin` tier、`YNSYLP005` 出现在 accounts、空 username、重复 username、未知 tier/未知字段。
  - omission 表示账户被移除，即 denied。
  - version conflict 返回 `409 access_control_version_conflict` 并返回 current version，不自动覆盖。

## 持久化、并发与审计设计

### 复用现有表

- canonical row：`app.app_settings(settings_key='app_settings')`。
- ACL keys：
  - `allowed_usernames`
  - `readonly_export_usernames`
  - `admin_usernames`（固定派生 `['YNSYLP005']`，不对 API 开放）
  - `full_access_usernames`（派生）
  - `access_control_version`
- audit：复用 `audit.events`，不复用当前仅内存的 `AuditTrailService` 作为 durable proof。

### 专属 ACL commit

repository/state-store 增加窄方法，不新增通用 repository 抽象：

1. 开 PostgreSQL transaction。
2. `SELECT settings_payload ... FOR UPDATE`。
3. 读取并比较 `access_control_version`。
4. 归一目标 accounts；若语义相同则返回 no-op，不 UPDATE、不 audit。
5. 仅 merge ACL keys，保留所有其它 setting family。
6. version + 1。
7. 更新 formal `settings_payload` 与 `raw_payload.normalized_payload`。
8. 在同一 transaction 插入 `audit.events`。
9. commit 后返回 canonical ACL payload。

audit 至少记录 event type、session actor、before/after tier 摘要、changed usernames、old/new ACL version、request/trace id（现有 request context 能提供时）；不得记录 token、密码或请求完整 body。

### 普通 writer 的并发保护

公共 `save_app_settings(...)` / transaction helper 默认在 row lock 下从数据库复制最新 ACL family，再保存 caller 的非 ACL setting families。这样项目、标签、列布局、normalization tool 等旧 snapshot 都不能覆盖 ACL。

本地 `ApplicationStateStore` 用现有 `RLock` 保持同样 family-preserving 语义，并提供测试/开发用的专属 ACL commit；不新增本地锁框架。

### Database invariant

新增 migration：

- 先把历史非 `YNSYLP005` admin fail-closed 归一为固定 admin；把固定 admin 加入 allowed、从 readonly/full 派生中移除；初始化 `access_control_version`。
- 同步 formal payload 与 `raw_payload.normalized_payload`。
- 写 migration audit，只记录计数/哈希和被清理用户名摘要。
- 添加并 validate CHECK：canonical admin 数组只能是 `['YNSYLP005']`，allowed 必须包含该账号，readonly/full 不得包含该账号，version 为正整数。

该约束能在误回滚到旧 binary 时阻断“写入其它 admin”的 T0 路径。它不能代替应用层 admin guard；安全版本不得回滚到重新开放 generic ACL 的代码。

## OA role sync 与失败语义

保留当前同步+补偿，不新增 worker：

- ACL no-op：不调用 OA。
- 目标 OA sync 失败：本地 canonical ACL 不提交，返回 502。
- OA sync 成功但本地 CAS/保存失败：同步回 previous ACL；返回 conflict/persistence error。
- 补偿也失败：返回明确 `access_control_sync_inconsistent`，critical log 只写 actor/version/错误类别，不写凭据；发布 runbook 要求人工核对 OA 三角色与 canonical ACL。
- 普通 settings 保存：永远不调用 OA，也不进入补偿链。

`OARoleSyncService` 继续接受一份归一 snapshot，但 admin assignment 由固定 protected admin 注入，不能从业务请求或动态 DB admin provider取得。

## 鉴权热路径

现状最多读取三次动态 provider。目标：

- `AppSettingsService.get_access_control_snapshot()` 一次返回 normalized allowed/readonly/full/version。
- `AccessControlService` 只保留一个 dynamic ACL snapshot provider；protected admin 在 provider 之外固定判定。
- provider 异常时非 protected admin fail closed；`YNSYLP005` 保持可恢复管理入口。
- 不加 Redis/cache；每次权限判断至多一次 snapshot load。后续只有测量证明该 DB read 成为热瓶颈时才另开缓存设计。

本 phase 不重定义 OA `required_permission` / allowed roles 与本地 allowlist 的整个优先级，只保证任何来源都不能产生非 `YNSYLP005` admin。characterization tests 必须锁住现有 non-admin access behavior，避免安全修复顺带改变所有页面可见性。

## 精确旧代码删除清单

### Backend

- `routes_settings.py` generic route 中三组 ACL parse/type-check/service args/error message。
- `AppSettingsService.update_settings(...)` 的 ACL 参数、普通 save 的 OA role sync/compensation。
- generic `get_settings_payload()` 的 `access_control` block。
- `get_allowed_usernames()` / `get_readonly_export_usernames()` / `get_admin_usernames()` 三 provider，替换为一个 snapshot provider；删除 dynamic admin。
- `AccessControlService` 的 `admin_usernames` env/runtime list、`dynamic_admin_usernames_provider` 和三 provider 读取方式。
- `auth.py` local clone 对旧 provider/admin list 的复制；保留显式 dev/test-only behavior。
- `server.py` 三 provider wiring 与 `FIN_OPS_ADMIN_USERNAMES` 运行时 authority。
- `pending_invoice_rules_application_service.py` 的 `getattr` + generic settings fallback。
- state-store default/normalizer 中“admin 可来自 payload”的行为，改为固定派生；专属 ACL commit 是唯一写口。

### Frontend

- `WorkbenchSettingsUpdatePayload` 和 `saveWorkbenchSettings(...)` body 的三组 ACL 字段。
- generic API DTO/map 的 `access_control`。
- `WorkbenchSettings.accessControl` 旧字段；新增独立 `WorkbenchAccessControl` DTO/type。
- `SettingsPageContent` 全局 `onSave` ACL args。
- `SettingsPage` 普通 save ACL args；新增 admin-only load/save state。
- `ReconciliationWorkbenchPage` 列顺序保存的 ACL copy。
- `WorkbenchSettingsModal` 的 access accounts section、state、helpers、props 和 imports；不保留第二 ACL UI。
- deterministic component mock 与 Playwright fixture 对 generic POST ACL 的解析/回显。

### Tests/docs/deploy

- 以 generic `update_settings(... ACL ...)` 作为权限 seed 的测试改走专属 ACL test helper/command。
- role matrix 中“admin generic POST 携带三 ACL 数组”的正向断言删除，改为 dedicated PUT；新增 full-access 直接 API 提权负向断言。
- column-layout 与 pending-invoice tests 移除 ACL payload expectation。
- deploy env/example/script/readme 退休 `FIN_OPS_ADMIN_USERNAMES` 作为运行时管理员来源，并写明唯一管理员固定合同。
- 更新 settings、permissions-and-audit、oa-integration boundary/tests/state-machine、SECURITY/API/deploy 文档。

## 最小文件影响矩阵

| 责任 | 主要文件 | 说明 |
| --- | --- | --- |
| HTTP | `routes_settings.py` | generic 拒绝旧字段；新增 admin-only GET/PUT |
| Service | `app_settings_service.py` | 独立 ACL command/snapshot；generic 无 ACL/OA |
| Auth | `access_control_service.py`, `auth.py`, `server.py` | 单 snapshot provider；固定 admin；删旧 wiring |
| Persistence | `state_store_protocol.py`, `state_store.py`, `postgres_state_store.py`, `postgres_repositories/ops_tax_etc.py` | family-preserving generic save；ACL CAS+audit |
| DB | 新 migration + migration tests | 清理、version、CHECK、audit |
| OA | `oa_role_sync_service.py` | 固定 admin assignment；仅 ACL command调用 |
| Frontend | `SettingsPage.tsx`, `SettingsPageContent.tsx`, `SettingsAccessAccountsSection.tsx`, `WorkbenchSettingsModal.tsx`, `ReconciliationWorkbenchPage.tsx`, workbench `api.ts/types.ts` | 独立 ACL load/save；删除重复入口/旧 payload |
| Fallback | `pending_invoice_rules_application_service.py` | 删除旧 generic fallback |
| Mocks/E2E | `web/src/test/apiMock.ts`, `web/e2e/fixtures/apiMocks.ts`, Settings/Workbench tests, role matrix | 新 endpoint、直接提权回归 |
| Docs/deploy | 三模块 docs、`SECURITY.md`, API docs, `deploy/oa/*` | 单一 authority、runbook、回滚 |

不需要修改其它业务页面 response、read model manifest、worker registry、dirty scope、Redis 或 RabbitMQ。

## 性能 I/O 预算

不声明未经测量的毫秒 SLO，使用可机械证明的 I/O 上限：

| 链路 | 目标预算 |
| --- | --- |
| 普通 settings save | 零 OA I/O；一次 family-preserving settings transaction；无 queue/read-model/cache I/O |
| 普通 settings semantic no-op | 零 DB write、零 audit、零 OA I/O |
| session 权限判断 | 最多一次 ACL snapshot provider 调用；无 admin 二次 provider |
| ACL GET | 一次 ACL snapshot read；无 OA I/O |
| ACL PUT 真变化 | 一次目标 OA transaction + 一次 app settings/audit transaction；失败补偿最多再一次 OA transaction |
| ACL PUT no-op | 一次 snapshot/CAS read；零写、零 audit、零 OA I/O |

ACL 是低频 control plane。除非 staging/prod 采样证明用户量导致 OA 逐项 insert 成为问题，本 phase 不增加 bulk framework或异步 worker。

## Validation Architecture

### 七类测试适用性

| 类别 | 适用性 | 最小覆盖 |
| --- | --- | --- |
| 1. Business core unit | 适用 | fixed admin、full/read/denied矩阵；ACL normalize；非法 admin/duplicate/unknown tier；no-op；version conflict |
| 2. Service/repository | 适用 | generic preserve concurrent ACL；row-lock CAS；settings+audit同事务；失败 rollback；local/Postgres parity；OA target/compensation/no-op |
| 3. API contract | 适用 | generic ACL keys 400；full/read dedicated GET/PUT 403；admin GET/PUT 200；409；错误 shape；actor body拒绝；OA 502；response 不再含 ACL |
| 4. Read model/cache/worker | 仅负向适用 | 断言无新 manifest/registry/outbox/dirty/cache；普通 save 不 fan-out |
| 5. Frontend component | 适用 | admin 独立 load/save/conflict；full-access普通保存；访问区权限；modal旧入口消失；列拖拽 body 无 ACL |
| 6. E2E integration | 适用 | full-access 直接 API 提权被拒；admin 改他人 tier 后新 session 生效；普通 settings/column layout/OA credential/data reset 回归 |
| 7. Existing regression | 适用 | session role matrix、Settings、Workbench、pending rules、AppHealth、OA credentials/data reset、代表性只读/导出/业务写 |

### 高风险验证顺序

1. 先写红测：full-access 直接 POST generic ACL、自提 dedicated PUT、缺省 payload 清空、旧 column-layout payload。
2. repository/local-store 原子性与并发测试。
3. service + OA compensation/no-op tests。
4. API contract + session matrix。
5. frontend component + API mock。
6. role-matrix Browser direct API 与 admin flow。
7. lint、docs、全 backend/frontend suite；最后才做 staging OA/生产只读 smoke。

### 推荐命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app_settings_service \
  tests.test_session_api \
  tests.test_auth_guard \
  tests.test_workbench_settings_sync_api \
  tests.test_oa_role_sync_service \
  tests.test_state_store_contract \
  tests.test_postgres_state_store \
  tests.test_postgres_repositories_boundaries \
  tests.test_postgres_migrations \
  tests.test_permissions_write_entry_inventory -v

cd web && npm test -- --run \
  src/test/SettingsPage.test.tsx \
  src/test/WorkbenchSelection.test.tsx \
  src/test/WorkbenchColumnLayout.test.tsx \
  src/test/SessionApi.test.ts

cd web && npx playwright test e2e/permissions-role-matrix.spec.ts
bash scripts/verify.sh lint
bash scripts/verify.sh docs
bash scripts/verify.sh all
```

生产/staging 使用 `scripts/with-production-admin-token.sh`，不得把 token 输出到日志或对话；本 phase 的计划和本轮分析不执行生产写入。

## D-01～D-19 可行性复核

| Decision | 结论 | 研究纠正/补充 |
| --- | --- | --- |
| D-01～D-03 | 可行 | 固定 admin 不进可写 accounts；删除即 denied |
| D-04～D-07 | 可行 | generic GET 也要删 ACL；必须处理 Workbench modal/column caller |
| D-08～D-11 | 可行 | 复用现有 row-lock pattern与 audit table；当前内存 AuditTrailService不够 |
| D-12～D-14 | 可行 | 当前同步补偿可复用；no-op 和 generic 必须零 OA；单 snapshot provider |
| D-15～D-16 | 可行 | 独立 ACL save 不能与 global save 串成双请求；删除 modal 第二入口和 pending fallback |
| D-17～D-18 | 可行但需 production checkpoint | 必须先盘点当前 DB/env/OA roles；本轮不猜生产事实 |
| D-19 | 可行 | 无需 read model/worker/cache/page response 变更；仅关联台 settings body regression需改 |

## Blockers 与开放问题

### 计划无 blocker

代码中已有 route owner、admin resolver、settings table、row-lock transaction pattern、audit table、OA sync service和权限 E2E，可形成闭环。

### 执行/发布 checkpoint

1. 生产 `app.app_settings` 是否存在非 `YNSYLP005` admin。
2. 生产 env 是否仍配置多个 `FIN_OPS_ADMIN_USERNAMES`，以及 allowed/readonly/roles 的实际成员。
3. OA 三类 fin-ops role 当前成员和被同步用户是否全部存在。
4. 若生产事实与唯一 admin 合同冲突，先输出 dry-run 清理清单并由用户确认发布窗口；不得静默保留或直接写生产。

## Sources

- `SECURITY.md`
- `docs/product-specs/platform-settings-health.md`
- `docs/modules/settings/{README,boundary-io,tests,state-machine}.md`
- `docs/modules/permissions-and-audit/{README,boundary-io,tests,write-entry-inventory}.md`
- `docs/modules/oa-integration/{README,boundary-io,tests}.md`
- `backend/src/fin_ops_platform/app/{routes_settings.py,auth.py,server.py}`
- `backend/src/fin_ops_platform/services/{app_settings_service.py,access_control_service.py,oa_role_sync_service.py,state_store.py,postgres_state_store.py}`
- `backend/src/fin_ops_platform/services/postgres_repositories/ops_tax_etc.py`
- `backend/src/fin_ops_platform/postgres/migrations/{0001_extensions_and_schemas.sql,0005_tax_etc_turnover_settings_jobs.sql}`
- `web/src/pages/{SettingsPage.tsx,ReconciliationWorkbenchPage.tsx}`
- `web/src/components/settings/*`
- `web/src/components/workbench/WorkbenchSettingsModal.tsx`
- `web/src/features/workbench/{api.ts,types.ts}`
- 相关 backend/frontend/E2E tests 与 deploy files 的 whole-repo `rg` 扫描。

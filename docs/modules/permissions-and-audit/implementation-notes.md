# 权限与审计 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 权限事实源在后端 OA session + `AccessControlService`。前端权限 hook 只负责用户体验，不能作为安全边界。
- 权限层级固定为 `denied`、`read_export_only`、`full_access`、`admin`；`YNSYLP005` 固定 admin，settings 中 admin 用户必须自动进入 allowed。
- 写入 API 必须检查 `can_mutate_data`；数据重置、OA 凭据、访问账户管理、AppHealth 运维 dashboard 等高风险入口必须检查 `can_admin_access`。
- 审计是 command/service 边界的一部分。重要业务写入应在同一事务或等价原子边界内提交业务事实、audit、dirty scope/outbox。
- 本模块首轮闭环状态为 `documented-risk`：本地测试覆盖 session/auth/API/UI/audit contract，真实 OA 菜单、角色同步、生产 token 行为和全页面全角色矩阵仍需 staging/生产 smoke。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-17 - Browser role matrix 权限闭环

- 目标：把权限矩阵从组件/API 层推进到真实 Chromium，覆盖 read_export_only/full_access/admin 在全页面导航和高风险写入口上的可见行为。
- 影响范围：`web/e2e/permissions-role-matrix.spec.ts`、`web/src/components/imports/ImportWorkflowPage.tsx`、`web/src/pages/NoOaBankBatchPage.tsx`、`web/src/test/NoOaBankBatchPage.test.tsx`、`web/package.json` smoke。
- 关键决策：不改变后端权限 contract；前端继续使用 `/api/session/me` 的 `can_mutate_data/can_admin_access` 作为 UI 门禁。read_export_only 在浏览器里可打开所有非 admin 页面，但不应触发 mutation API；full_access 可用普通业务写入口但不能进 AppHealth；admin 可进入 settings 高危区和 AppHealth。
- 文档影响：更新权限模块测试矩阵、状态机、全局测试说明、Nightly CI 风险和 closure state。
- 测试覆盖：新增 Playwright role matrix；新增 NoOaBankBatchPage read-only unit regression；相关 Vitest 覆盖 ImportCenter、NoOa、WorkbenchSelection、App、SessionGate、SessionApi。
- 验证命令：`cd web && npx playwright test e2e/permissions-role-matrix.spec.ts`；`cd web && npm test -- --run src/test/ImportCenterPage.test.tsx src/test/NoOaBankBatchPage.test.tsx src/test/WorkbenchSelection.test.tsx src/test/App.test.tsx src/test/SessionGate.test.tsx src/test/SessionApi.test.ts`。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期语义、真实导出下载与代理层 header、生产审计查询/导出仍需 staging/生产 smoke。
- 后续事项：新增页面或新增写入口时，必须把 read_export_only 行为加入本 role matrix 或对应页面 e2e。

## 2026-06-16 - access tier 聚合矩阵 gate

- 目标：把分散的 readonly/full/admin/denied 权限证据压成一个后端 session contract 聚合测试，降低 17 个页面 P2/P3 推进时权限口径漂移风险。
- 影响范围：`/api/session/me`、settings access control、`AccessControlService` 动态 provider 组装、默认 admin、权限码用户和未授权用户。
- 关键决策：不修改权限逻辑；新增 `test_get_session_me_projects_access_tier_matrix_from_settings` 走真实 app 组装后的 `/api/session/me`，同时校验 `read_export_only`、`full_access`、settings admin、默认 admin、permission-code full access、`denied` 的 `access_tier/can_access_app/can_mutate_data/can_admin_access`。
- 文档影响：更新 `tests.md` 和 P2/P3 closure ledger，把“全角色矩阵缺少单测”收敛为“session contract 已有聚合矩阵；页面级按钮/导出/写入交互仍由各模块和 nightly 覆盖”。
- 测试覆盖：新增后端 API contract / business core 聚合测试；复跑 auth guard。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_session_api.SessionApiTests.test_get_session_me_projects_access_tier_matrix_from_settings -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard -v`。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期语义、代理层真实导出下载、生产审计查询/导出仍需 staging/生产 smoke。
- 后续事项：发现具体页面权限绕过时，先在对应页面模块补最小 regression，再回链本模块矩阵。

## 2026-06-16 - readonly export 路由聚合 smoke

- 目标：补齐 P2/P3 台账中“导出权限 smoke 分散”的本地聚合证据，保证只读导出用户可读/可导出但不能写入或进入 admin 操作。
- 影响范围：protected API guard、cost statistics export、turnover ledger export、pending invoice export auth pass-through、pending/input invoice rules、turnover tag selection、bank auto-tag reapply、settings data reset。
- 关键决策：不把缺少 SQL read repository 的 pending export 误判为权限失败；测试只断言 readable/export routes 不返回 `401/403` 或 auth/admin 错误，并对可稳定生成 XLSX 的 cost/turnover 下载断言 content type。
- 文档影响：更新 `tests.md` 和 P2/P3 closure ledger。
- 测试覆盖：新增 `test_readonly_export_user_can_export_but_cannot_mutate_or_admin`，覆盖 API contract / existing regression 的 representative smoke。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard.AuthGuardTests.test_readonly_export_user_can_export_but_cannot_mutate_or_admin -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_auth_guard -v`。
- 未测风险：真实浏览器下载、反向代理 `Content-Disposition`/`Access-Control-Expose-Headers`、生产 OA session 和审计导出查询仍需 staging/production smoke。
- 后续事项：新增页面导出时应加入本聚合 smoke 或对应模块的权限测试。

## 2026-06-11 - permissions-and-audit 测试闭环首轮

- 目标：补齐权限与审计横切边界的影响面、七类测试矩阵、状态机、验证命令和真实环境风险。
- 影响范围：`auth.py`、`AccessControlService`、`AuditTrailService`、`SessionContext`、`SessionGate`、settings access control、各 API mutation/admin guard、导出权限、业务 UoW audit。
- 关键决策：不新增低价值代码测试；已有测试已经覆盖 session、auth guard、access tier、write/admin 403、前端权限 UI、audit 原子性和敏感数据保护。本轮补齐文档闭环。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 auth/session/audit/settings/data reset/OA credential/tax/pending/turnover/bank tag/runtime boundary；前端覆盖 SessionGate、SessionApi、Settings、Workbench、AppHealth、AppStatus、TaxOffset。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期、全页面全角色矩阵、审计查询/导出、代理层导出下载权限。
- 后续事项：发现权限绕过或审计遗漏时，先补最小 regression test，再登记到 `docs/dev/regression-bug-bank.md`。

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

## 2026-06-11 - permissions-and-audit 测试闭环首轮

- 目标：补齐权限与审计横切边界的影响面、七类测试矩阵、状态机、验证命令和真实环境风险。
- 影响范围：`auth.py`、`AccessControlService`、`AuditTrailService`、`SessionContext`、`SessionGate`、settings access control、各 API mutation/admin guard、导出权限、业务 UoW audit。
- 关键决策：不新增低价值代码测试；已有测试已经覆盖 session、auth guard、access tier、write/admin 403、前端权限 UI、audit 原子性和敏感数据保护。本轮补齐文档闭环。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`implementation-notes.md` 和全局 `testing-closure-dependency-map.md`。
- 测试覆盖：后端覆盖 auth/session/audit/settings/data reset/OA credential/tax/pending/turnover/bank tag/runtime boundary；前端覆盖 SessionGate、SessionApi、Settings、Workbench、AppHealth、AppStatus、TaxOffset。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实 OA 菜单/角色同步、生产 token 过期、全页面全角色矩阵、审计查询/导出、代理层导出下载权限。
- 后续事项：发现权限绕过或审计遗漏时，先补最小 regression test，再登记到 `docs/dev/regression-bug-bank.md`。

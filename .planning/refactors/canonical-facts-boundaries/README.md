# Canonical Facts Boundaries

日期：2026-06-28

本目录是 GSD 执行工作区，用于推进“统一事实源”模块化。长期事实必须同步到 `docs/architecture/module-boundaries/canonical-facts.md` 和 `docs/modules/canonical-facts/`。

## 范围

- PostgreSQL `app.*` 业务事实 owner、I/O、禁止路径和旧代码移除。
- `job.*` / `audit.*` 只作为 runtime/audit facts 管理，不作为业务事实 owner。
- `read_model.*` 只作为派生投影。本工作流不接管 07 read model closure 的 runtime 文件。

## 当前策略

- 先做 owner matrix 和模块合同。
- 旧生产 source-of-truth 路径必须删除，不能仅标记兼容。
- migration/audit/rollback 工具如果暂时不能删除，必须隔离在生产 API/worker 主链路之外；它们是 deferred/blocker，不算闭环。

## 文件

- `ANALYSIS.md`：当前事实源分析。
- `PLAN.md`：macro-wave 计划和验收。
- `autonomous/STATE.md`：当前执行状态。
- `autonomous/JOURNAL.md`：执行日志。
- `autonomous/NEXT-PROMPT.md`：下一步可执行 prompt。
- `analysis/`：每波 reconciliation、wave report、closure report。

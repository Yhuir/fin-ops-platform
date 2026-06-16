---
status: resolved
trigger: "外部往来款管理中 workbench linked 状态把 OA 关联和多笔流水闭环混在一起；已关联 OA 的流水应仍可与其他流水确认外部往来闭环，确认后 OA 与流水成员收敛为一个 active case，撤回闭环只撤回多笔流水闭环语义并保留/恢复 OA 关系。"
created: "2026-06-17"
updated: "2026-06-17"
---

# Debug Session: turnover-oa-closure-chips

## Symptoms

- Expected behavior:
  - 外部往来款管理每条流水分别展示 OA 关联状态与多笔流水闭环状态。
  - `已关联 OA` 只展示流水与 OA 的关联，不参与确认/撤回闭环按钮判断。
  - `已闭环` / `未闭环` 表示多笔流水之间的外部往来闭环，决定确认/撤回闭环入口。
  - 如果流水 1 已配对 OA1、流水 2 已配对 OA2，选择流水 1、2、3 确认闭环后应形成一个 active case，包含 OA1、OA2、流水 1、2、3。
  - 外部往来页撤回闭环时只撤回多笔流水闭环语义，保留或恢复原 OA 关系。
- Actual behavior:
  - `workbench_relation_status=linked` 被展示为“关联台已关联/关联台手工闭环”，语义模糊。
  - 前端 `确认闭环` 被任何 `linked` relation 阻断，即已关联 OA 的流水不能参与外部往来闭环。
  - 撤回路径当前按 bank-only `turnover_manual_closure` 设计，不能表达合并已有 OA case 后的恢复。
- Error messages:
  - 无直接报错，主要是 UI 误导和业务链路被错误阻断。
- Timeline:
  - 2026-06-16 用户截图发现。
- Reproduction:
  - 外部往来款管理中选中已与 OA 关联但未做多笔流水闭环的银行流水，观察 chip 与 toolbar。
  - 选择已分别与 OA1/OA2 关联的流水 1/2 加流水 3 确认闭环。

## Current Focus

- hypothesis: 前端把 Workbench linked 当作闭环事实，后端 turnover manual closure 写入没有合并已有 OA active relations 并保存可恢复 before_relations。
- test: 新增/更新前后端回归测试覆盖 OA-linked rows can confirm closure、withdraw restores OA relations、chip labels split OA linked vs closure linked。
- expecting: 失败测试先复现当前阻断/冲突，再通过 relation replace_existing + withdraw restore 和 UI 判断拆分修复。
- next_action: add failing tests and implement minimal backend/frontend changes.

## Evidence

- timestamp: "2026-06-17"
  observation: "web/src/pages/TurnoverLedgerPage.tsx 使用 selectedRowsContainLinkedWorkbenchRelation 阻断确认闭环；web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx 对 linked 非 turnover_manual_closure 显示“关联台已关联”。"
- timestamp: "2026-06-17"
  observation: "WorkbenchRelationCommandService.confirm_relation 默认拒绝 active row conflict；replace_existing=True 可通过 WorkbenchPairRelationService.replace_with_confirmed_relation 保存 before_relations 并取消旧 relation。"
- timestamp: "2026-06-17"
  observation: "WorkbenchRelationCommandService.withdraw_relation 可通过 WorkbenchPairRelationService.withdraw_latest_for_row_ids 从 confirm history 恢复 before_relations；当前 turnover withdraw port 仍调用 cancel_relation。"

## Eliminated

- hypothesis: "只改 chip 文案即可"
  reason: "按钮决策和后端 active case 合并/撤回恢复也受影响。"

## Resolution

- root_cause: 外部往来台账把 Workbench `linked` 状态直接当成闭环事实展示和参与按钮判断，导致 OA 关联与多笔流水 `turnover_manual_closure` 闭环语义混淆；后端确认闭环也没有把已有 OA-bank active case 合并进同一个可恢复的闭环 case。
- fix: 后端确认闭环通过 `WorkbenchRelationCommandService` 读取选中银行流水的 active relations，将仅包含 `oa`/`bank` 且含 OA 的关系合并为一个 `turnover_manual_closure` case，并把被替换关系写入 confirm history；撤回闭环改用 withdraw/recover 语义恢复原 OA-bank relations。前端拆分 `已关联 OA`/`已关联业务单据` 展示 chip 与 `已闭环`/`未闭环` 闭环 chip，确认/撤回按钮只看 `turnover_manual_closure`。
- verification:
  - `PYTHONPATH=backend/src python3 -m unittest -q tests.test_workbench_pair_relation_service tests.test_workbench_relation_command_service tests.test_turnover_ledger_uow_contract tests.test_turnover_workbench_integration tests.test_workbench_turnover_grouping tests.test_turnover_ledger_read_model_refresh tests.test_turnover_ledger_api` passed: 272 tests.
  - `cd web && npm test -- --run src/test/TurnoverLedgerApi.test.ts src/test/TurnoverLedgerPage.test.tsx src/test/domainEvents.test.ts src/test/OperationBarrierApi.test.ts src/test/GlobalOperationOverlayContext.test.tsx` passed: 38 tests.
  - `bash scripts/verify.sh docs` passed.
  - `git diff --check` passed.
- files_changed:
  - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
  - `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
  - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
  - `web/src/components/turnoverLedger/TurnoverLedgerGroupedTable.tsx`
  - `web/src/pages/TurnoverLedgerPage.tsx`
  - `tests/test_turnover_ledger_uow_contract.py`
  - `tests/test_turnover_workbench_integration.py`
  - `tests/test_workbench_pair_relation_service.py`
  - `web/src/test/TurnoverLedgerPage.test.tsx`
  - `docs/modules/turnover-ledger/README.md`
  - `docs/modules/turnover-ledger/state-machine.md`
  - `docs/modules/turnover-ledger/tests.md`
  - `docs/modules/turnover-ledger/implementation-notes.md`
  - `docs/modules/workbench-relations/state-machine.md`
  - `docs/product-specs/bank-turnover-and-no-oa.md`
  - `docs/dev/api-contracts.md`
  - `docs/app-architecture/pages.md`

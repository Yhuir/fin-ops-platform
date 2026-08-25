---
status: diagnosed
trigger: "外部往来款页面点击确认闭环后提示操作失败：Previous Workbench relation topology can no longer be restored safely. 只分析，不实现。"
created: 2026-08-25
updated: 2026-08-25
---

# GSD Debug: turnover-confirm-close-topology

## Symptoms

- Expected behavior: 在外部往来款页选择同组、收支相抵的流水后，“确认闭环”应成功建立闭环关系。
- Actual behavior: 点击操作后弹出“操作失败”，关系未按用户预期闭环。
- Error message: `Previous Workbench relation topology can no longer be restored safely.`
- Timeline: 用户未提供首次发生时间或是否曾成功；当前截图日期为 2026-08-25，会话中直接复现。
- Reproduction: 打开 `/turnover-ledger` 的个人往来页签，选择同一往来组中的流水并触发闭环操作。

## Current Focus

- hypothesis: CONFIRMED — 本次实际操作是撤回闭环。撤回 preview 要恢复的 predecessor relation 与当前 active relation 使用完全相同的 case id；稳定拓扑保护将其判为 `workbench_relation_restore_case_reused`，随后对外折叠为截图中的英文安全冲突消息。
- test: 已完成生产 canonical GET、操作历史 GET、Workbench row detail GET，以及 route policy 明确标记只读的 withdraw preview；结果与 `_assert_restored_relation_ownership_available` 的首个 guard 精确匹配。
- expecting: 已观察到 active/restored case id 相同；代码会在检查其它 owner 前确定性抛出 `workbench_relation_restore_case_reused`。
- next_action: Return root-cause-only diagnosis; do not implement or mutate production state.

## Evidence

- 2026-08-25 screenshot: 前端显示后端业务消息 `Previous Workbench relation topology can no longer be restored safely.`，不是通用网络错误。
- 2026-08-25 code: 该精确消息仅位于 `WorkbenchRelationCommandService._lock_and_revalidate_withdraw_topology(...)`，并映射为 `workbench_relation_restore_conflict`。
- 2026-08-25 code: 校验只在待恢复 case 被复用/成员变化，或待恢复成员已被其它 active relation 占用时失败。
- 2026-08-25 code: 正常 `/api/turnover-ledger/closures/confirm` 走 `confirm_zero_difference_closure` -> `prepare_confirm_relation` -> `confirm_relation`；静态路径不调用 withdraw topology restore 校验。
- 2026-08-25 code: 页面会根据所选行是否全部带 `cashClosureLinked`，把主按钮切换为“撤回闭环”并调用 `/api/turnover-ledger/closures/withdraw`；未闭环选择才显示“确认闭环”并调用 `/closures/confirm`。
- 2026-08-25 code: 主按钮 `onPress` 与文案使用同一个 `selectedRowsAllCashClosure` 判定；为 true 时直接调用 `handleWithdrawSelectedCashClosure`，现代闭环走 `/closures/withdraw`，为 false 时只打开确认 drawer，最终由 `handleConfirmClosure` POST `/closures/confirm`。不存在“按钮显示确认但 handler 静态调用 withdraw”的分支。
- 2026-08-25 codegraph: `_lock_and_revalidate_withdraw_topology` 只有 `prepare_withdraw_relation` 和 `withdraw_relation` 两个调用方；从 `confirm_zero_difference_closure` 到该函数不存在静态调用路径。
- 2026-08-25 code: 底层 `workbench_relation_restore_case_reused` 与 `workbench_relation_restore_owner_conflict` 都被折叠为相同的公开英文 message；Turnover HTTP error payload 会过滤内部 `reason`，仅保留 `error/message`（以及特定 row/case 列表），因此截图本身不能区分这两个底层原因。
- 2026-08-25 production read-only GET: `counterparty:personal:杨丽萍` 当前共有四条 flow rows（`txn_imported_0105/0077/0076/0058`），全部 `cash_closure_linked=true`，全部共享 `cash_closure_case_id=turnover:turnover_rel_36266274e9235566`，`cash_closure_relation_id` 为空，source 为 `turnover_ledger`；组汇总也是同一 closed case。该运行时事实证明选中截图中的已闭环流水时主操作分支是 withdraw。
- 2026-08-25 production read-only GET: Workbench row detail endpoint 对 `txn_imported_0105` 只返回 top-level `month,row,row_id,scope_key`；`row` 含当前 `case_id/relation_mode/status/special_metadata`，不直接返回 history 或 predecessor relations 数组。
- 2026-08-25 production read-only GET: `txn_imported_0105` 当前 Workbench row 为 `status=paired`、`relation_mode=turnover_manual_closure`、`case_id=turnover:turnover_rel_36266274e9235566`；public `special_metadata` 只含 current relation/source/requirements 等字段，没有 `before_relations` 或 restorable predecessor topology。
- 2026-08-25 production audit GET: 本日 `page_key=turnover-ledger` 有三次相邻失败（12:18:47、12:19:07、12:19:31），三条均明确记录 `action_code=turnover.closure.withdraw`、`action_label=撤回往来闭环`、`outcome=failed`。这直接解决“用户说点击确认，但静态错误仅属于撤回”的矛盾：实际 HTTP 业务动作是撤回。
- 2026-08-25 production audit detail GET: 三条失败详情均 `failure=null`、无 target/records/changes 且 `legacy_evidence_missing=true`；Operation History 可证明动作类型，但不能恢复内部 `payload.reason` 或 predecessor topology。
- 2026-08-25 production read-only withdraw preview: 当前 active relation 为 `case_id=turnover:turnover_rel_36266274e9235566`，成员是四条银行流水 `txn_imported_0105/0077/0076/0058` 加 `oa-pay-2209`；preview 的 `restored_relations[0]` 却使用完全相同的 case id，成员是原 bank-only 四条流水，`relation_mode=turnover_manual_closure`、`restorable_on_withdraw=true`，创建于 2026-06-23。
- 2026-08-25 code + production preview: `_assert_restored_relation_ownership_available` 在 owner 扫描前先检查 `case_id == active_case_id`，此处条件确定为 true，因此底层原因确定为 `workbench_relation_restore_case_reused`，不是 `workbench_relation_restore_owner_conflict`。

## Eliminated

- 已排除普通前端渲染/网络异常：消息来自明确的后端 Workbench relation 安全冲突分支。
- 已排除金额不平、版本 token 缺失等常规确认前置错误：这些分支使用不同的中文错误消息，不能产生截图中的精确英文消息。
- 已排除本次实际请求为 confirm：生产操作历史连续三次记录为 `turnover.closure.withdraw`。
- 已排除 `workbench_relation_restore_owner_conflict`：same-case guard 在 owner conflict 检查之前已确定性触发。

## Resolution

- root_cause: 用户选中的杨丽萍流水已经属于同一 active 外部往来闭环，所以页面实际执行的是撤回。该 active case 后续从原 bank-only 四条流水扩展为四条银行流水加 `oa-pay-2209`，但撤回 history/preview 将原 bank-only snapshot 作为待恢复 relation，并保留了与当前 active relation 完全相同的 `case_id=turnover:turnover_rel_36266274e9235566`。稳定拓扑校验禁止把当前 active case id 作为 predecessor 再恢复，确定性抛出 `workbench_relation_restore_case_reused`；该内部 reason 被 Turnover API 折叠为 `turnover_relation_conflict` 和英文消息 `Previous Workbench relation topology can no longer be restored safely.`。
- fix: diagnose only; no implementation authorized.
- verification: 生产只读 grouped GET 证明目标组已闭环；生产操作历史证明实际动作是 withdraw；只读 withdraw preview 证明 active/restored case id 相同；代码 guard 顺序证明必然命中 `case_reused`。
- files_changed: `.planning/debug/turnover-confirm-close-topology.md` (diagnostic session artifact only).

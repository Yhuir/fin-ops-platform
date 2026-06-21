---
status: resolved
trigger: "贾小花三笔外部往来款流水确认闭环后进入关联台已配对区域；用户明确要求已配对区域必须满足 OA、银行流水、发票三栏关系。"
created: 2026-06-22
updated: 2026-06-22
---

# GSD Debug: Workbench Turnover Paired Zone

## Symptoms

- Expected behavior: 外部往来款确认闭环后，外部往来台账显示“收支闭环”；关联台保留同一个 `turnover_manual_closure` active case/evidence，但未补齐发票前不得进入“已配对”区域。
- Actual behavior: 贾小花三笔纯银行流水进入了关联台“已配对”区域，并显示“完全关联”。
- Error messages: 无后端错误；这是业务分区语义错误。
- Timeline: 2026-06-21 为修复 Workbench generation consistency failure 增加了 `turnover_manual_closure` bank-only paired 例外。
- Reproduction: 在外部往来款选择贾小花两收入一支出三笔流水确认闭环，然后在关联台搜索“小花”查看已配对区域。

## Current Focus

- hypothesis: 上一轮修复把 active relation ownership 和 paired zone completeness 混为一谈；`turnover_manual_closure` 纯银行 active case 应保留 canonical `case:*` owner，但 zone 必须保持 open/candidate 直到 OA+银行+发票三栏完整。
- test: 后端 grouping、SQL projection 和外部往来集成测试必须断言 bank-only / OA+bank-only turnover closure 留在 open；三栏 turnover closure 才进入 paired。
- expecting: Workbench consistency checker 不再因为 canonical open `case:<case_id>` 报 `active_relation_open_membership`，同时贾小花三笔纯银行流水不在 paired。
- next_action: 修改 grouping、projection schema/chip、测试和文档，运行相关测试并部署后重建生产 Workbench scopes。

## Evidence

- timestamp: 2026-06-22
  finding: `WorkbenchCandidateGroupingService._paired_group_has_enough_row_types()` 对 `turnover_manual_closure` bank-only 返回 True，且 `_is_paired_row()` 先把这些行放进 paired 候选。
- timestamp: 2026-06-22
  finding: `WorkbenchSqlProjectionBuilder._active_relation_payload()` 对非 `manual_confirmed` relation 返回通用“已关联”；进入 paired serializer 后又被覆盖成“完全关联”，造成纯银行闭环视觉上像三栏完成。
- timestamp: 2026-06-22
  finding: generation consistency SQL 只禁止 active relation row 出现在非 canonical open owner；如果 open group_id 是 `case:<case_id>`，不会触发 `active_relation_open_membership`。

## Eliminated

- hypothesis: 外部往来不应写 Workbench relation。
  reason: 外部往来页需要共同事实源、撤回和跨页刷新；问题是 Workbench zone，不是 relation 写入。
- hypothesis: 前端本地把行移动到了已配对。
  reason: 分区来自 backend active generation payload，当前测试和代码都在后端把 bank-only turnover 提升为 paired。

## Resolution

- root_cause: 2026-06-21 的修复把 `turnover_manual_closure` active relation ownership 和 Workbench paired zone completeness 混为一谈；bank-only active case 被提升到 paired，paired serializer 又把 chip 覆盖为“完全关联”。
- fix: `turnover_manual_closure` 行仍保留 active relation/canonical case，但 `_paired_group_has_enough_row_types()` 只有在 OA + 银行 + 发票三栏完整时才允许进入 paired；demoted rows 的 payload status 统一回 `open`；SQL projection 对 turnover closure chip 显示“收支闭环”；WorkBench schema bump 到 v2 并重建生产 `2026-02`、`2026-03`、`all`。
- verification: 本地 `tests/test_workbench_turnover_grouping.py tests/test_workbench_sql_runtime.py tests/test_turnover_workbench_integration.py tests/test_workbench_candidate_grouping.py` 通过；生产 `queue_backlog={}`、`failed_jobs=0`、outbox/dirty 非 done 为空；贾小花三笔流水在 `2026-02`、`2026-03`、`all` 均为 `zone=open`、`group_row_status=open`、`relation_label=收支闭环`，active relation 仍为 `turnover_manual_closure`。
- files_changed: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`、`backend/src/fin_ops_platform/services/workbench_sql_projection.py`、`backend/src/fin_ops_platform/app/server.py`、相关 Workbench/Turnover 测试和模块文档。

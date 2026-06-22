---
status: investigating
trigger: "关联台已配对区域出现大量两栏 OA+银行配对组；期望除特殊情况外只有 OA+银行+发票三栏完整才能进入已配对区域。用户要求使用 GSD 先分析，不实现。"
created: 2026-06-22
updated: 2026-06-22
goal: find_root_cause_only
---

# GSD Debug Session: reconciliation-two-pane-paired

## Symptoms

- Expected behavior: 关联台已配对区默认只展示 OA + 银行流水 + 进销项发票三栏完整闭环；两栏关系应留在未配对/open/candidate，除明确业务例外。
- Actual behavior: 截图中已配对区存在大量 OA + 银行流水两栏组，发票栏为空。
- Error messages: 无报错，属于分区/业务口径异常。
- Timeline: 用户反馈为“现在”出现大量此类行；代码与文档历史显示 2026-06-21 曾引入“已确认 active relation 两栏也留在 paired”的决策，2026-06-22 又对外部往来改回三栏口径。
- Reproduction clue: 选择/确认过 OA+银行关系，或已有 `app.workbench_pair_relations.status='active'` 且 `relation_mode=manual_confirmed` 的 OA+银行 relation；Workbench SQL active generation 会把对应行标为 paired。

## Current Focus

- hypothesis: 普通 active relation 的两栏 paired 不是前端渲染错误，而是后端 grouping 逻辑有一个通用 `confirmed active relation + 至少两类 row` 豁免；同时 confirm-link 写入口允许任意两栏确认并写 `relation_mode=manual_confirmed`。
- test: 阅读 WorkbenchCandidateGroupingService、WorkbenchSqlProjectionBuilder、WorkbenchWriteFacade、server `_can_confirm_link_row_types`、相关 tests/docs。
- expecting: 找到 `row_type_count >= 2 and _is_confirmed_active_relation_group(...)` 之类条件；找到 confirm-link 只要求至少两个 pane；找到文档/测试对两栏 active relation paired 的互相冲突口径。
- next_action: 若进入实现阶段，先与产品口径确认“特殊情况”白名单，再改分区规则、confirm/preview 写入门槛和回归测试。

## Evidence

- timestamp: 2026-06-22T11:30+08:00
  source: `docs/modules/reconciliation-workbench/README.md`
  finding: 当前模块 README 写明自动 decision 必须覆盖真实三栏 row set 才能进入 paired；旧 display tag、旧 case_id、两栏 automatic_decision 或候选应留在 open。文档也明确批量账务等外部 owner 是 OA+银行 paired 业务例外。

- timestamp: 2026-06-22T11:32+08:00
  source: `backend/src/fin_ops_platform/services/workbench_candidate_grouping.py`
  finding: `_paired_group_has_enough_row_types()` 对 `turnover_manual_closure` 要求三栏，但对其他 confirmed active relation 只要 `row_type_count >= 2` 就返回 true。

- timestamp: 2026-06-22T11:35+08:00
  source: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
  finding: active relation 投影会把 relation row 标为 `status="paired"`、写入同一 `case_id` 和 `relation_mode`，并对普通 `manual_confirmed` 返回 `{"code": "fully_linked"}`；随后交给 grouping 做 paired/open 分区。

- timestamp: 2026-06-22T11:38+08:00
  source: `backend/src/fin_ops_platform/app/server.py`
  finding: `_can_confirm_link_row_types()` 只要求 known row types 数量至少为 2，或 bank-only 平衡；因此普通 confirm-link 允许 OA+银行、OA+发票、银行+发票写入 active relation。

- timestamp: 2026-06-22T11:40+08:00
  source: `docs/modules/reconciliation-workbench/tests.md`
  finding: 测试矩阵仍把 `test_keeps_confirmed_active_oa_bank_relation_without_invoice_in_paired_section` 标为 covered，并说明 `manual_confirmed` 两栏 relation 即使缺第三栏也留在 paired；这与 README 当前口径冲突。

- timestamp: 2026-06-22T11:42+08:00
  source: `docs/modules/reconciliation-workbench/implementation-notes.md`
  finding: 2026-06-21 的实施记录把“active relation ownership 优先于三栏展示完整度”作为关键决策；2026-06-22 的 state-machine 又纠正了外部往来两栏/bank-only 不得进 paired。

## Eliminated

- hypothesis: 前端把 open group 错渲染到 paired 区。
  evidence: API/grouping payload 本身会输出 `paired.groups`；前端 `CandidateGroupGrid` 只是消费 zoneId 和 groups。

- hypothesis: 仅自动 matching decision 导致截图问题。
  evidence: 自动 decision 的两栏 case 被文档和 tests 约束为 open/candidate；截图 chip `已关联流水/已关联OA` 更符合 active relation 投影后的 `fully_linked` two-pane group。

## Root Cause Candidate

当前最可能根因是 2026-06-21 为了修复“已确认 OA+银行 active relation 残留 open 区”而引入了过宽规则：所有非 `automatic_decision`、同 case、relation code 为 `fully_linked` 的 confirmed active relation，只要覆盖两类 row type，就被视为合法 paired。随后普通 confirm-link 本身也允许两栏确认，因此生产/当前数据里已有的大量 OA+银行 active relation 会被成批提升到已配对区。

这个规则只对 `turnover_manual_closure` 做了三栏收紧，未对普通 `manual_confirmed` 应三栏完整、批量账务/no-OA/个人暂借款/ETC/OA待付款等例外白名单做统一 policy。

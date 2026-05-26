# Bank Invoice Free Matching Execution Prompt

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` if subagents are available; otherwise use `superpowers:executing-plans` and execute the serial tasks inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `WorkbenchFreeMatchingEngine` production-ready for income bank transaction to output invoice matching, including one-bank-to-many-invoices sum matching, deterministic strongest-evidence selection, and structured ambiguity blockers.

**Architecture:** Keep `WorkbenchDecision` as the only backend decision fact source. Add income `bank_invoice` matching inside `WorkbenchFreeMatchingEngine`, with explicit bank counterparty to invoice buyer subject evidence, summary/remark as supporting evidence, amount-closure rules, and structured `open` decisions for ambiguity. Do not move matching logic to frontend or SQL read models.

**Tech Stack:** Python backend, `unittest`, existing `fin_ops_platform.services.workbench_*` modules, existing docs under `docs/product-specs/` and `docs/dev/`.

---

## Final Prompt To Run In Codex

```text
/goal 在 /Users/yu/Desktop/fin-ops-platform 的 main 上完整修复 WorkbenchFreeMatchingEngine 的收入流水 + 销项发票自由匹配。不要创建 worktree，不要创建 branch。必须生产级实现，不要救急/临时方案。最终要有测试、文档、验证结果和清晰提交边界。

你正在 /Users/yu/Desktop/fin-ops-platform 工作。先读取：
- AGENTS.md
- README.md
- ARCHITECTURE.md
- docs/index.md
- docs/superpowers/specs/2026-05-26-bank-invoice-free-matching-design.md
- docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md

硬性约束：
- 在 main 上工作，禁止创建 worktree/branch。
- 保护现有 dirty worktree：先运行 `git status --short`，识别已有 staged/unstaged 改动；不要 reset、checkout、stash 或 revert 任何你没有明确负责的改动。
- 只修改本任务相关文件。预期相关文件主要是：
  - backend/src/fin_ops_platform/services/workbench_free_matching_engine.py
  - tests/test_workbench_free_matching_engine.py
  - tests/test_workbench_reconciliation_engine.py
  - docs/product-specs/workbench.md
  - docs/dev/reconciliation-workbench-v2-data-contracts.md
  - docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md
- 如果发现这些文件里已有别人改动，先读懂并在其基础上继续，不要回滚。
- 如果需要提交或暂存，只 stage 本任务文件；不要带入 bank details、internal transfer、frontend、migration report 等无关改动。
- 使用 `apply_patch` 手工编辑文件；不要用 shell 写文件技巧。
- 先写/补失败测试，再改实现，再跑验证。

业务需求：
1. 收入银行流水应能自动匹配销项发票。收入方向的发票主体必须使用销项发票购方 `buyer_name` / `buyer_tax_no`，不能用销方作为收入流水主体。
2. 银行对方户名/对方税号与销项发票购方名称/购方税号是主体证据。主体证据是自动 paired 的准入条件。
3. 银行摘要/备注中出现购方名称、发票号码、数电票号、合同号、订单号、项目号是有效补强证据；但摘要/备注不能替代主体证据。没有银行对方户名/税号主体证据时，摘要/备注命中购方也不能自动关闭。
4. 一笔收入流水金额等于一张销项发票价税合计，且主体证据成立、候选唯一时，输出 `paired`，`match_shape=bank_invoice`，`rule_code=bank_invoice_exact_amount`，`payment_amount_closed=true`，`invoice_amount_closed=true`。
5. 一笔收入流水金额等于多张同购方销项发票价税合计，且组合唯一时，输出一个 `paired` decision：`bank_row_ids` 一笔流水，`invoice_row_ids` 多张发票，`rule_code=bank_invoice_exact_sum`，两个 amount_closed 都为 true。
6. 一笔收入流水金额等于多张同金额销项发票各自金额时，不能把所有发票都标记已收款。只能在唯一最强证据候选存在时自动选择一张；若最高证据并列，必须输出结构化 `open` decision 和 blocker。
7. 最强证据评分只在主体证据成立的候选之间比较。建议排序：
   - 税号匹配：100
   - 摘要/备注命中发票号码、数电票号或发票代码：80
   - 摘要/备注命中合同号、订单号、项目号：60
   - 对方户名与购方名称完全规范化匹配：50
   - 摘要/备注命中购方名称：20
   - 日期距离最短且唯一：10
   只有最高分唯一才能 paired。不能靠导入顺序、row id、数据库 id 或无业务含义排序来裁决。
8. 无法唯一裁决时不能静默不配。必须输出结构化 `open` decision，保留银行流水、候选发票、amount_relation、candidate_rows、evidence_summary、reason。blocker code 至少覆盖：
   - `multiple_bank_invoice_candidates`
   - `same_score_bank_invoice_candidates`
   - `multiple_bank_invoice_sum_candidates`
9. active 手工关系、特殊规则已占用 row、已自动 paired 且 source version 未过期的发票不能被同一轮新的 bank_invoice paired 重复占用。遵循现有 claimed row 机制，不要破坏三方 OA-银行-发票逻辑。
10. SQL read model 和前端只消费 `WorkbenchDecision`，不能新增前端推断逻辑。

建议实现边界：
- 在 `WorkbenchFreeMatchingEngine` 内新增专门的 bank-invoice 候选/评分逻辑，不要把收入 bank_invoice 的复杂规则硬塞进泛用 `_pair_candidates`。
- 保留现有支出侧 OA/银行/发票三方逻辑和普通两方 `oa_bank`、`oa_invoice` 逻辑。
- 可以新增小型内部 dataclass，例如 `_BankInvoiceCandidate`、`_BankInvoiceGroup` 或类似结构，前提是只服务当前匹配规则。
- 可以新增 helper：
  - `_bank_invoice_decisions(...)`
  - `_bank_invoice_candidates(...)`
  - `_bank_invoice_subject_evidence(...)`
  - `_bank_invoice_supporting_evidence(...)`
  - `_bank_invoice_score(...)`
  - `_paired_bank_invoice_decision(...)`
  - `_open_bank_invoice_conflict_decision(...)`
- `_two_way_decisions` 中不要再让泛用 `(bank_rows, invoice_rows, "bank_invoice", "bank_invoice_exact_amount")` 直接处理 bank_invoice，避免它把冲突拆成单行 open 或只做 mutual unique。
- 决策 evidence 必须可审计，至少包含 `scope_window`、`uniqueness_scope`、`subject_evidence`、`supporting_evidence`、`score` 或 `candidate_scores`、`amount_relation`。
- `RULE_VERSION` 需要 bump 到能标识本次规则变化的值，例如 `2026-05-26-bank-invoice-scored-sum`.

并行/串行执行结构：

Phase 0 串行：准备和保护现场
- [ ] 运行 `git status --short`，记录已有 unrelated staged/unstaged 改动。
- [ ] 读取上述文档和目标代码。
- [ ] 确认不创建 worktree/branch。

Phase 1 可并行：只读审阅
- [ ] Explorer A：审阅 `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`，回答当前 bank_invoice 流程、claimed row、open decision 的真实行为和最小修改点。
- [ ] Explorer B：审阅 `tests/test_workbench_free_matching_engine.py`、`tests/test_workbench_reconciliation_engine.py`、`docs/dev/reconciliation-workbench-v2-data-contracts.md`，列出应新增/调整的测试和文档断言。
- [ ] 如果没有 subagent，就在本会话顺序完成 A/B。

Phase 2 串行 TDD：补失败测试
- [ ] 在 `tests/test_workbench_free_matching_engine.py` 新增/调整测试：
  1. `test_income_bank_matches_multiple_output_invoices_by_exact_sum`
  2. `test_income_bank_selects_unique_invoice_by_invoice_number_in_remark`
  3. `test_income_bank_same_score_candidates_remain_open_with_structured_blocker`
  4. `test_income_bank_invoice_requires_counterparty_subject_not_summary_only`
  5. `test_income_bank_summary_buyer_name_supports_scoring_after_subject_match`
  6. `test_income_bank_invoice_sum_multiple_combinations_remain_open`
  7. `test_income_bank_invoice_tax_no_subject_evidence_scores_above_name_only`
- [ ] 在 `tests/test_workbench_reconciliation_engine.py` 新增/调整持久化测试，证明 `bank_invoice_exact_sum` 和结构化 open blocker 会写入 decision store。
- [ ] 运行：
  `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_reconciliation_engine -v`
  预期：新增测试因实现未完成而失败；旧测试不应出现无关破坏。

Phase 3 串行实现：引擎
- [ ] 修改 `backend/src/fin_ops_platform/services/workbench_free_matching_engine.py`。
- [ ] 把 bank_invoice 从泛用两方 mutual unique 分支中拆出来，改为专门 matcher。
- [ ] 对收入 bank_invoice 使用银行对方主体字段和销项发票购方字段作为 subject evidence。
- [ ] 把摘要/备注作为 supporting evidence，不作为准入主体证据。
- [ ] 实现单流水多发票合计唯一组合：唯一则 `paired`，多组合则 structured `open`。
- [ ] 实现同金额多候选评分：唯一最高分则 `paired`，并列则 structured `open`。
- [ ] 让 open blocker 包含 `code`、`candidate_rows`、`amount_relation`、`evidence_summary`、`reason`，不要静默返回空列表。
- [ ] 确保同一轮 claimed row 不重复占用。
- [ ] 不破坏支出方向和 OA 三方匹配。

Phase 4 串行文档
- [ ] 更新 `docs/product-specs/workbench.md`：说明收入流水 + 销项发票自动匹配、合计闭合、同金额歧义和 open blocker。
- [ ] 更新 `docs/dev/reconciliation-workbench-v2-data-contracts.md`：补充 `bank_invoice_exact_sum`、scored single candidate、structured blocker 的契约。
- [ ] 如需要，更新 `docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md`，保持与 2026-05-26 细化设计一致。

Phase 5 串行验证
- [ ] 运行定向测试：
  `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_reconciliation_engine tests.test_output_invoice_collection_service -v`
- [ ] 运行应用检查：
  `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- [ ] 尝试全量后端回归：
  `PYTHONPATH=backend/src python3 -m unittest discover -s tests -v`
  如果全量仍因既有无关失败失败，必须列出失败模块和与本任务的关系，不要谎称全量通过。

Phase 6 审阅和提交边界
- [ ] 运行 `git diff -- backend/src/fin_ops_platform/services/workbench_free_matching_engine.py tests/test_workbench_free_matching_engine.py tests/test_workbench_reconciliation_engine.py docs/product-specs/workbench.md docs/dev/reconciliation-workbench-v2-data-contracts.md docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md`，自审是否满足全部需求。
- [ ] 运行 `git status --short`，确认没有误改无关文件。
- [ ] 如需暂存/提交，只使用精确路径 stage 本任务文件，不能 `git add .`。
- [ ] 最终回复必须包含：
  - 改动摘要
  - 关键规则如何满足 1-10
  - 测试/检查结果
  - 未解决风险，尤其是全量回归是否仍有既有失败
  - 没有关联的流水/发票为什么现在会有 paired 或 structured open 解释
```

## Prompt Review Checklist

- [x] Includes `/goal`.
- [x] States no worktree/branch and main-only execution.
- [x] Protects current dirty worktree and staged unrelated files.
- [x] Captures subject evidence vs summary/remark supporting evidence.
- [x] Covers one bank to one invoice, one bank to many invoice sum, same-amount duplicate candidates, and structured open blockers.
- [x] Requires TDD before implementation.
- [x] Names exact implementation, test, and documentation files.
- [x] Gives serial/parallel execution structure without creating overlapping write ownership.
- [x] Requires verification and honest reporting of existing unrelated full-suite failures.

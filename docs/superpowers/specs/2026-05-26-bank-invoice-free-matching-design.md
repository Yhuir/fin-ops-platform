# 收入流水与销项发票自由匹配设计

日期：2026-05-26

关联设计：`docs/superpowers/specs/2026-05-25-workbench-reconciliation-engine-design.md`

## 背景

关联台统一配对引擎已经承担自动决策入口，`WorkbenchFreeMatchingEngine` 负责普通自由匹配。现有收入侧规则需要补齐：

- 一笔收入流水可以对应一张销项发票。
- 一笔收入流水也可以对应多张销项发票合计。
- 多个同金额销项发票同时命中同一笔收入流水时，不能随机选择，也不能把金额重复闭合。
- 银行摘要、备注中的购方、发票号、合同号、项目号等文字是有效证据，但必须纳入可解释的优先级体系。

本设计只覆盖收入流水与销项发票的 `bank_invoice` 自由匹配，不改变支出 OA-银行-发票规则，不改变特殊规则和手工关联事实源。

本设计是对 2026-05-25 关联台引擎设计的收入侧细化：仍以 `WorkbenchDecision` 作为唯一后端决策事实源，前端和 SQL read model 不重新推断匹配关系。

## 目标

- 让收入流水和销项发票在证据充分时自动进入 `paired`。
- 支持一笔流水匹配多张销项发票合计金额闭合。
- 同金额多候选时允许自动选择最强证据候选。
- 无法唯一裁决时输出结构化 `open` 决策和 blocker，不静默丢弃。
- 决策必须可复现、可解释、可审计。

## 非目标

- 不按导入顺序、发票 ID 或简单开票日期随机选择。
- 不让摘要/备注单独替代主体证据。
- 不把一笔 `13440` 流水同时关联两张各 `13440` 发票并标记金额闭合。
- 不在前端推断或修正匹配关系。
- 不把旧 `workbench_candidate_matches` 扩展成新的展示事实源。

## 方案比较

| 方案 | 规则 | 优点 | 风险 |
| --- | --- | --- | --- |
| A 严格唯一 | 多个同金额候选全部 open | 最安全 | 自动化不足，财务仍需处理大量可区分候选 |
| B 确定性评分 | 有唯一最强证据时自动选，否则 open | 自动化和审计平衡 | 需要清晰评分和测试覆盖 |
| C 固定排序 | 同金额候选按日期或 ID 选一个 | 实现简单 | 不可解释，误配风险高 |

采用方案 B。

## 候选准入

银行收入流水与销项发票进入候选池必须满足：

1. 方向一致：银行流水为收入，发票为销项。
2. 月份在完整 `T-2 / T / T+2` 候选窗口内。
3. 主体证据存在：银行对方户名或对方税号，与销项发票购方名称或购方税号可以匹配。
4. 金额关系可能成立：
   - 单张发票价税合计等于流水金额。
   - 多张同购方发票价税合计等于流水金额。

摘要和备注不能单独让候选进入自动关闭，但可以作为主体证据成立后的补强证据。换句话说，银行摘要或备注里出现购方名称是有效证据，但它不能替代银行对方户名或对方税号；自动 paired 必须先证明银行对方主体与销项发票购方主体一致。

## 证据模型

### 主体证据

主体证据用于确认“这笔钱和这个购方是同一个业务主体”：

- 银行对方户名命中销项发票购方名称。
- 银行对方税号命中销项发票购方税号。
- 银行明细结构化字段中的 `对方户名` 命中销项发票购方名称。

主体证据是自动配对准入条件。

主体证据只来自银行对方主体字段和发票购方主体字段，不从摘要、备注、用途、附言中提取。摘要和备注里的购方名称只作为补强证据记录和排序。

### 补强证据

补强证据用于在多个同主体同金额候选之间做确定性排序：

- 银行摘要或备注命中发票号码、数电票号、发票代码。
- 银行摘要或备注命中合同号、订单号、项目号。
- 银行摘要或备注命中购方名称。
- 税号匹配优先于名称匹配。
- 交易日期与开票日期距离更近。
- 候选发票未被 active relation、自动 paired decision 或已作废/红冲状态占用。

补强证据必须进入 decision evidence，供页面、审计和后续排查解释。

补强证据用于回答“同一个主体、同一金额下应选哪一张发票”。它不能回答“这个主体是不是同一个主体”。

## 匹配优先级

### 1. 多发票合计闭合优先

如果一笔收入流水金额等于多张同购方销项发票价税合计，且组合唯一，则输出一个 `bank_invoice` paired decision：

- `bank_row_ids` 包含一笔流水。
- `invoice_row_ids` 包含多张发票。
- `payment_amount_closed = true`。
- `invoice_amount_closed = true`。
- `rule_code = bank_invoice_exact_sum`。

如果存在多个可行组合，输出 `open` 决策，blocker 为 `multiple_bank_invoice_sum_candidates`。

### Runtime 集成

PostgreSQL decision-store 路径直接持久化 `WorkbenchFreeMatchingEngine` 的 `bank_invoice` 决策。Mongo/legacy candidate 路径也必须复用同一引擎：`WorkbenchMatchingRules` 只做决策到 legacy candidate 的适配，`paired` 转为 `auto_closed`，`open` 冲突转为 `conflict`，并在 `special_metadata.workbench_reconciliation_decision` 中保留原始 evidence/blockers。legacy 路径不得继续使用独立的旧银行-发票精确金额或多发票合计规则。

### 2. 单发票精确匹配

如果只有一张销项发票金额等于流水金额，且主体证据成立，则自动输出 `paired`：

- `rule_code = bank_invoice_exact_amount`。
- `match_shape = bank_invoice`。

### 3. 多张同金额发票选择最强候选

如果一笔收入流水金额等于多张销项发票各自金额，先对候选评分：

| 证据 | 分值 |
| --- | --- |
| 税号匹配 | 100 |
| 摘要/备注命中发票号码、数电票号或发票代码 | 80 |
| 摘要/备注命中合同号、订单号、项目号 | 60 |
| 对方户名与购方名称完全规范化匹配 | 50 |
| 摘要/备注命中购方名称 | 20 |
| 日期距离最短且唯一 | 10 |

若最高分候选唯一，则自动选择该发票并输出 `paired`。若最高分并列，则输出 `open`，blocker 为 `same_score_bank_invoice_candidates`。

评分只在主体证据已成立的候选之间比较；没有主体证据的候选不能靠摘要或备注进入自动关闭。

当最高分唯一时，选择该发票不是按行号兜底，而是基于可解释证据裁决。若唯一性只来自导入顺序、row id、数据库 id 或没有业务含义的排序，必须视为并列并输出 open。

## 冲突和 open 决策

无法唯一裁决时必须输出 `open` 决策，而不是返回空结果。blocker 至少包含：

- `code`：如 `multiple_bank_invoice_candidates`、`multiple_bank_invoice_sum_candidates`、`same_score_bank_invoice_candidates`。
- `candidate_rows`：相关流水和发票 row id。
- `amount_relation`：`single_exact_amount` 或 `invoice_sum_exact_amount`。
- `evidence_summary`：主体证据、补强证据、分值。
- `reason`：无法自动关闭的具体原因。

一个无法裁决的业务冲突应输出一个结构化 `open` decision，保留银行流水、候选发票和 evidence 的完整上下文。页面可以据此展示“为什么没关联”，审计可以追溯候选集合；不要静默跳过，也不要把同一个冲突拆成多个互相看不见的 open 行。

## 数据流

1. `WorkbenchReconciliationEngine` 按 dirty scope 提供五个月窗口行。
2. `WorkbenchFreeMatchingEngine` 归一化收入银行流水和销项发票。
3. `bank_invoice` matcher 先生成候选，再按金额关系分组。
4. 多发票合计 matcher 优先尝试唯一组合。
5. 单发票 matcher 对候选评分并裁决。
6. 确定关系写入 `WorkbenchDecision`。
7. 冲突写入 `open` decision。
8. SQL read model 只消费 decision，不重新判断业务规则。

## 边界和占用

- active 手工关系中的 row 不进入新的自动匹配。
- 已由特殊规则占用的 row 不进入自由匹配。
- 已自动 paired 且 source version 未过期的发票，不参与同一轮其他 bank_invoice paired decision。
- source version 变化时，旧 decision 由 `WorkbenchReconciliationDecisionStore` 过期，重新裁决。

## 测试计划

新增或调整后端测试：

1. 一笔 `26880` 收入流水自动匹配两张各 `13440` 销项发票，金额闭合。
2. 一笔 `13440` 收入流水命中两张各 `13440` 发票，其中摘要命中一张发票号，自动选择该张。
3. 一笔 `13440` 收入流水命中两张同级 `13440` 发票，输出 open 和 blocker。
4. 摘要/备注命中购方名，但银行对方户名/税号为空时，不自动关闭。
5. 税号匹配优先于名称和摘要命中。
6. 被 active relation 占用的发票不参与新自动匹配。
7. 多发票合计存在多个组合时输出 open。
8. 所有 paired 和 open decision 都包含可审计 evidence。
9. 一笔流水金额等于两张同金额发票时，只选择唯一最强证据候选；若没有唯一最强证据，不自动选择。
10. 摘要/备注命中购方名称且主体证据成立时，该命中作为补强证据参与评分。

验证命令：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_free_matching_engine tests.test_workbench_reconciliation_engine tests.test_output_invoice_collection_service -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

全量回归仍使用：

```bash
PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
```

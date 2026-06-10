# 关联台 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- `oa_bank_exact_sum` 属于后端自动候选规则，必须同时覆盖 legacy candidate mode 和 decision/free engine mode；不能只在 `server.py` 或前端补展示逻辑。
- Workbench matching 仍保留 legacy candidate 与 SQL decision 两条生产相关链路。新增规则时先复用现有 service/helper/test 工具，后续再单独规划匹配逻辑收敛。
- 旧逻辑清理不和业务规则变更混做。`WorkbenchMatchingRules`、`WorkbenchFreeMatchingEngine`、`WorkbenchReconciliationEngine`、工资/内部转账 legacy rule code 仍有 orchestrator、worker、免 OA、分组和异常投影调用或兼容引用，不能无测试删除。

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

## 2026-06-10 - OA 与多银行流水合计候选

- 目标：支持 1 条 OA 与唯一一组 2 到 6 条同方向银行流水按分精度合计等于 OA 金额时自动形成 OA-bank 候选，继续等待发票。
- 影响范围：`WorkbenchMatchingRules` legacy candidate mode、`WorkbenchFreeMatchingEngine` decision mode、matching orchestrator、candidate grouping、Workbench API payload/read model invalidation。
- 关键决策：
  - 规则名为 `oa_bank_exact_sum`。
  - 单笔 `oa_bank_exact_amount` 优先；若已生成单笔 OA-bank 精确候选，不再生成多银行合计候选。
  - 每条银行流水必须复用现有 OA-bank evidence，不允许只靠金额。
  - 同一 OA 存在多个等额银行流水组合时不自动选择。
  - legacy candidate 生成 `candidate_type=oa_bank`、`status=incomplete`，让 OA 和多条银行流水进入同一个 open candidate group。
  - decision mode 生成 `WorkbenchDecision(match_shape=oa_bank, rule_code=oa_bank_exact_sum, payment_amount_closed=True)`，供 SQL decision/read model/worker 链路消费。
- 文档影响：已更新 `docs/product-specs/reconciliation-and-workbench.md`、本模块 `state-machine.md` 与 `tests.md`。
- 测试覆盖：
  - `tests/test_workbench_matching_rules.py` 覆盖 legacy 规则正例、唯一性、证据要求、单笔精确优先。
  - `tests/test_workbench_free_matching_engine.py` 覆盖 decision mode 正例、歧义、证据要求、单笔精确优先。
  - `tests/test_workbench_matching_orchestrator.py` 覆盖 legacy candidate 持久化、decision store 持久化和 read model invalidation。
  - `tests/test_workbench_v2_api.py` 覆盖 Workbench API payload/grouping 中 OA 与多条银行流水保持同一个 open candidate group。
- 验证命令：见 `tests.md` 的 Workbench 相关验证命令。
- 未测风险：未新增前端组件测试；当前变更沿用既有 open candidate group shape。未做真实生产库 worker dry-run。
- 后续事项：可单独评估 legacy candidate 与 decision/free engine 的规则收敛；不要和本规则混入无关旧逻辑删除。

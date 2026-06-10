# 进项发票使用情况 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 默认 all scope 查询不得因为月份间嵌套 `workbench_relation_source_versions` 不同而清空基础 `source_versions`；API freshness 只要求服务端期望的基础 source version 字段匹配。

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

## 2026-06-10 - all scope source_versions 聚合修复

- 目标：修复“进项发票使用情况”默认不传 `month` 时页面没有加载数据的问题。
- 真实原因：生产 read model 行数据和月 scope 均存在且 fresh，但 repository 在 all scope 聚合时要求所有月份的完整 `source_versions` 字典完全相等；不同月份的 `workbench_relation_source_versions` 嵌套时间戳不同，导致 all scope 返回 `{}`，API 随后以 `api_source_versions_stale` 返回 `202/refreshing` 和空 rows。
- 影响范围：`PostgresReadModelRepository._invoice_relation_scope_row` 的 all scope source_versions 聚合；输入发票使用页面 rows API；同 helper 也服务于 output invoice collection all scope。
- 关键决策：all scope 仍要求各月 cache status 为 fresh；版本聚合改为保留各月份共同一致的顶层 source version 字段，差异字段从 all scope source_versions 中剔除。
- 文档影响：更新 `state-machine.md` 的 read model 状态规则与 `tests.md` 的测试矩阵。
- 测试覆盖：新增 repository 回归测试和 API 正向契约测试；保留 source version 缺失返回 refreshing 的反向测试。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v`；`cd web && npm test -- --run src/test/InputInvoiceUsagePage.test.tsx`；`cd web && npm run build`。
- 未测风险：本地验证已完成；生产仍需部署后只读验证默认 rows API 是否返回 `fresh` 与非空分页总数。
- 后续事项：发布必须走 `./scripts/deploy-oa.sh` 或现有运维流程，不直接在服务器热改代码。

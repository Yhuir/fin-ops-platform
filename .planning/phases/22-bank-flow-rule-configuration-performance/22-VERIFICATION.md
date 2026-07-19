# 第 2 项验证记录：流水规则配置链路

## 功能与边界

- 目标后端组：160 passed，另有 15 个 subtests passed。
- no-OA、Workbench、turnover、queue 相关回归：204 passed，另有 287 个 subtests passed。
- 前端既有回归：3 files / 53 tests passed；本项没有前端代码变化。
- lint、docs、Python compile、migration 静态合同与 `git diff --check` 均通过。
- 空白真实 PostgreSQL 已按顺序应用 0001–0111。
- 真实 PostgreSQL migration fixture 证明：bank-flow 变成 canonical shape、no-OA payload 不变、0111 可重复执行。
- 真实 PostgreSQL integration test 证明：no-op 无 version/audit/dirty 变化；actual change 只有 1 个 bank-flow all dirty scope 和 1 条 audit。

## 真实 PostgreSQL 性能

20 次采样：

| 路径 | p50 | p95 | max |
| --- | ---: | ---: | ---: |
| 同值 no-op 保存 | 29.578ms | 34.002ms | 35.446ms |
| 实际规则变化 | 51.688ms | 83.475ms | 88.024ms |

隔离证据：

- `bank_flow_rule_batch/all` dirty scope count：1。
- relation history count：0。
- audit count：20（20 次实际变化各 1 条）。

结果显著低于 `<500ms` 保存门槛，并且运行时复杂度不再随 active relation 数量增长。

## 全量后端结果与归因

全量后端修正后复跑：4200 passed、64 skipped、716 subtests passed；其中发现的 2 个本项测试期望遗漏已修正并定向复跑通过。

剩余历史问题在未改动基线 SHA `3c80361db` 上可独立复现：

- historical ETC migration refresh-month 断言失败；
- PostgreSQL workbench relation repository 仍期待已移除的 direct cost fan-out；
- write-operation cost fan-out matrix 断言失败；
- cost-statistics SQL runtime fixture 收集错误。

它们不位于本项变更文件或调用链，不作为本项修复范围，也不通过放宽断言隐藏。

## 尚待发布门禁

- 提交并推送唯一 SHA。
- 使用标准部署入口应用 migration 0111。
- 验证生产服务/worker exact SHA。
- 复测页面壳、GET tag-rules、Page Audit。
- 使用生产当前规则执行安全 no-op PUT，验证 version 不变且响应 `<500ms`。
- 验证 bank-flow Audit pass/fresh/drained，并检查 Workbench、银行明细、turnover 与 no-OA 隔离。

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

## 生产门禁结果

- SHA `182c29be4d6b1f9fd91001d88600fddd411bf2ef` 已推送并部署为 `main-182c29be-20260720015418`。
- migration 0111 生产应用成功；API、dispatcher、22 个 workers active 且 workdir 一致。
- 页面壳 / GET / Page Audit p95 分别为 `139.570ms` / `258.567ms` / `370.022ms`。
- 生产同值 PUT 20 次测量 p95 `275.186ms`、max `431.232ms`，version `11 → 11`。
- bank-flow、关联台、银行明细、turnover Audit 均 `pass / fresh / drained`、0 issue。
- 详细证据见 `22-PRODUCTION-VALIDATION.md` 与 `22-PRODUCTION-POST-READ.json`。

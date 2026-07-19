# 第 3 项生产验证结论

## 发布身份

- code SHA：`a5e5b795a`
- release：`main-a5e5b795-20260720032959`
- runtime：API、dispatcher、22 workers active；migration 0001–0111 current

## 读取性能

| 场景 | 样本 | p50 | p95 | p99 | 门槛 | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 页面壳 | 20 | 90.804ms | 130.237ms | 153.685ms | p95 ≤ 500ms | pass |
| all list / page 50 | 20 | 212.436ms | 272.284ms | 310.522ms | p95 ≤ 500ms | pass |
| 2026-07 list / page 50 | 20 | 164.600ms | 260.943ms | 264.238ms | p95 ≤ 500ms | pass |
| Page Audit | 20 | 248.573ms | 322.560ms | 447.076ms | p95 ≤ 1000ms | pass |
| 1-row detail | 20 | 158.752ms | 175.940ms | 176.821ms | p95 ≤ 500ms | pass |
| 33-row detail | 20 | 233.745ms | 337.446ms | 352.301ms | p95 ≤ 500ms | pass |

列表 40/40 均返回 `fresh` 且零 enqueue；全体 120 个读取/Audit 样本均通过对应门槛。

## 隔离 Audit

`bank-flow-rule-batches`、`reconciliation-workbench`、`bank-details`、`turnover-ledger`、`cost-statistics` 均返回：

- `overall_status=pass`
- `integrity=pass`
- `freshness=fresh`
- `queue=drained`
- `proof_availability=ready`
- `contract_revision=page-audit-contract.v25`
- `issues=0`

## 写验证门禁

生产可逆写计划是单行普通批次的 `submit-selection → month fresh → withdraw → month fresh → 五页面 Audit`，command 门槛 `≤1000ms`，committed-to-fresh p95 门槛 `≤2000ms`、hard max `3000ms`。

执行前的强制全系统预检 `page=app-health-operations` 返回 `issues_found`。失败归属是 `tax-offset`、`input-invoice-usage`、`output-invoice-collections`、`settings`，不是本模块或本模块五个直接影响页面；系统 freshness 为 fresh、queue drained。脚本在候选读取和任何 mutation 之前终止，因此生产业务状态零变更。

处理决定：不绕过全系统写门禁，不在第 3 项跨界修复其它页面；待主控流程完成相关页面并使全局预检通过后，在最终系统门补做同一个受控可逆写场景。当前结论只声明代码、读性能、详情性能与只读隔离通过，不把未执行的写场景误报为通过。

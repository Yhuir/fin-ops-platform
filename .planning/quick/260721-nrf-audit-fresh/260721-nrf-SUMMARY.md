---
status: complete
quick_id: 260721-nrf
date: 2026-07-21
commit: fc5babd5b16c427ca7bf027e2af81f9b980188e1
release: main-fc5babd5b-bank-flow-audit-202607211740
---

# Quick Task 260721-nrf Summary

## Result

- 流水规则批量处理的候选生成与提交校验统一读取 PostgreSQL canonical active relation，不再依赖可能滞后的 Workbench relation read model。
- 2026-07 生产未提交从 4 批收敛为 3 批；错误留在未提交区的手续费 1 批/13 条已退出，手续费已提交历史 5 批/28 条保持不变。
- 页面 Audit 绑定当前 read-model status/version；版本或刷新 token 变化会立即清除旧结果并取消旧请求。Audit v26 新增 draft member 被其它 active case 占用的阻断证明。
- 页面不再显示 `bank_flow_rule_batch_*` 内部 relation case id，只显示“已有未撤回关联”与 OA/发票数量。

## Architecture And I/O

- 复用既有 `workbench_relation_source_bundle_from_source(...)`，单次 SQL snapshot 返回目标 bank row 的 active relation rows 与 source versions。
- worker 固定为 scope bank rows -> canonical relation bundle -> source-version unchanged gate -> 必要时分类与投影；没有 N+1、没有新表、没有新 queue、没有同步页面重建。
- production worker 删除全量 `load_workbench_pair_relations()` 和 relation read-model facade；no-OA 的独立旧模块链路不变。
- API 增加稳定 `read_model_version`，occupied 冲突使用 HTTP 409；内部 relation IDs 继续保留在机器 DTO/Audit 中，不进入展示层。

## Verification

- 定向后端 146 passed、1 skipped；定向前端 30 passed。
- 相关回归 285 passed；前端全量 73 files / 864 tests、生产 build、Chromium bank-flow 9/9、lint、docs、diff check 全部通过。
- 全量后端运行 4248 tests；与改动前登记基线相同，仍有 8 failures + 3 errors + 50 skipped，没有新增失败。
- production release、强制重建、API、Page Audit、Chromium DOM 和 20 次 SLO 样本均通过；详细证据见 `260721-nrf-VERIFICATION.md`。

## Residual System Evidence

System Audit 仍报告 5 个本任务范围外的既有页面 integrity 阻断；这些页面均 fresh、queue drained，问题属于各自 canonical/read-model/历史导入数据合同。本任务未扩大为跨模块修复，最终结论仅覆盖 bank-flow-rule-batches 及其明确上下游边界。

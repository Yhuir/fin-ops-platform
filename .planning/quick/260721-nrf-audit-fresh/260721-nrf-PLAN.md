---
status: complete
mode: quick-validate
date: 2026-07-21
---

# 修复流水规则批量处理关系事实源、Audit fresh 闭环并生产验证

## Must haves

- `bank_flow_rule_batch` 的候选生成与提交前校验只使用 PostgreSQL canonical active relation，不再读取可能滞后的关系 read model。
- worker 在同一次固定次数 I/O 中取得关系 rows 与 source version；source version 预检不得先于真实候选行范围，且不得产生 N+1 查询。
- Audit 能发现未提交批次与任意其他 active bank-flow relation 的流水交集；页面 read model 状态或版本变化后旧的绿色 Audit 立即失效。
- 删除本链路中被替代的旧关系投影读取，不改变 no-OA 批次和其他页面的 I/O。
- 回归、性能、构建、文档检查通过；提交推送后使用正式发布入口部署，并对 2026-07 生产 scope 强制重建和只读验收。

## Task 1：收紧 canonical relation 与 read model worker 边界

- files: bank batch application/worker/service wiring、相关单元与服务层测试
- action: 复用现有 `workbench_relation_source_bundle_from_source`，将 rows 与 source versions 作为一次 canonical bundle 贯穿生成和提交校验；提升 schema version 并移除 bank-flow 旧投影读取。
- verify: canonical relation 已占用流水不会出现在未提交批次；unchanged 快路径和固定查询次数保持；no-OA 回归通过。
- done: 生成与提交的事实源一致，旧关系 read model 不再污染 bank-flow 链路。

## Task 2：补齐 Audit 与页面 fresh 生命周期

- files: page business audit、bank-flow API DTO/UI、Audit 组件调用、相关 API/前端测试
- action: Audit 对 canonical batch/read model 做完整集合核对，并检查 submitted/non-submitted 关系状态及跨 case overlap；API 输出稳定 read model version，页面以 status+version 使旧 Audit 结果失效；占用冲突映射为明确 409。
- verify: 旧投影重叠用例使 Audit fail；刷新后新版本才能重新显示 fresh；错误契约与交互测试通过。
- done: 绿色 Audit 只代表当前页面版本且已登记的不变量全部通过。

## Task 3：文档、全量验证与生产闭环

- files: bank-flow/read-model/runtime-worker 边界文档、GSD summary/verification
- action: 更新事实源与 Audit 合同；运行定向测试、全量 lint/docs/build/回归；提交并推送；正式部署后强制重建 `2026-07` scope，验证错误批次消失、Audit v26 fresh、队列清空。
- verify: 所有命令成功，并保留生产只读证据与耗时。
- done: 生产页面不再拉入已提交流水，且无其他页面回归。

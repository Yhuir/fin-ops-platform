# 成本统计 模块维护入口


- Module key: `cost-statistics`
- 类型: 页面模块
- Route: `/cost-statistics`
- Page key: `cost-statistics`

## 修改前必读

- `docs/product-specs/cost-tax.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`

## 代码入口

- `web/src/pages/CostStatisticsPage.tsx`
- `web/src/components/cost-statistics/*`

## 当前边界

关注项目范围、费用归因、导出 shape 和 cost read model freshness。成本统计 read model refresh scope 必须是 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 或 `all:all`；旧的裸月份/裸 `all` 只能在统一 read model refresh scope gateway 中归一化，不能直接进入 durable queue。生产旧 readiness、dirty scope 或 outbox 中残留的裸 scope 使用 `scripts/check-read-model-scope-contracts.py` 检查和受控清理。

生产刷新由专用 `cost-statistics` RabbitMQ consumer 承担独立性能 lane；旧 `cost-tax` 成本统计兼容消费者已移除，`cost-tax` 只保留税金抵扣兼容链路。当前 P2/P3 closure 按首屏 API 或 direct refresh p95 <= 1000ms 验收，写操作链路还要求 operation-to-fresh p99 <= 3000ms。`cost_statistics` freshness 仍以 PostgreSQL dirty scope/outbox/readiness 为事实源，不能为了达标把 stale 伪装成 fresh。

月度 scope projection 必须把对应 `read_model.workbench_generations` active generation 的 `source_versions` 纳入自身 `source_versions`。当 SQL read model 已经 fresh 且 `source_versions` 完全一致时，worker 可以返回 `skipped/source_versions_unchanged`，不得扫描 `read_model.workbench_groups` 或重写 payload；缺少读取接口、状态非 fresh 或版本不一致时必须按原路径重建。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护成本统计页面 Spec-first Browser E2E 验收合同。
- `e2e-coverage.md`：维护成本统计 Spec ID 到自动化测试的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

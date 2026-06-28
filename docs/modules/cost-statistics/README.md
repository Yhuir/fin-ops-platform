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

关注项目范围、费用归因、导出 shape 和 direct API 页面读路径。成本统计页面不再生产旧成本统计刷新事件，不绑定 `cost-statistics` / `cost-tax` 页面派生 worker，也不通过旧就绪记录证明页面数据可读。旧 cost/tax SQL projection 已删除；历史 `read_model.cost_statistics_*` 表仅作为迁移清理对象存在。

当前 P2/P3 closure 按 direct API 首屏 p95 <= 1000ms 验收。写操作链路通过 direct refetch / cache warmup 影响页面，不再等待旧成本统计页面派生 worker；页面不消费 explorer/export 的旧同步诊断字段。

历史月度 SQL projection/source-version 规则已退出当前架构；新页面读取不得依赖该旧同步结果。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或旧同步诊断字段删除变化。
- 业务状态、UI 状态、legacy projection/worker 下线状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、affected scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护成本统计页面 Spec-first Browser E2E 验收合同。
- `e2e-coverage.md`：维护成本统计 Spec ID 到自动化测试的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。

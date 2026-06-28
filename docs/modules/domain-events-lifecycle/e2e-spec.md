# Domain Events Lifecycle Spec-first E2E Spec

Domain event 和 derived lifecycle 的 Spec-first 目标是证明跨页面刷新提示和后端派生数据影响面不会脱节。前端 finance domain event 只是刷新提示；最终数据事实必须来自后端 direct API、canonical facts 和 worker 派生数据状态。

## Spec IDs

| Spec ID | 用户可观察合同 | 必须证明 |
| --- | --- | --- |
| `DOMAIN-E2E-001` | 页面 A 执行业务写入后，受影响页面 B/C 能刷新或提示刷新，但不会把前端 event 当成最终事实。 | 页面重新读取 direct API；event 只触发刷新。 |
| `DOMAIN-E2E-002` | 每个后端 lifecycle event 都能生成安全、可序列化、不会删除 protected target 的影响计划。 | `DerivedDataLifecycleService` plan 覆盖所有声明事件。 |
| `DOMAIN-E2E-003` | 新增/改名前端 finance event 不会破坏页面监听、跨 tab 和 inactive 页面行为。 | event contract、BroadcastChannel、active page subscription 测试。 |
| `DOMAIN-E2E-004` | import、relation、tax、settings、no-OA、turnover 等高 fan-out 动作必须把 affected domains/scopes 传到 runtime/worker 边界。 | lifecycle -> affected scopes/outbox/background job -> direct API 收敛证据。 |
| `DOMAIN-E2E-005` | startup stale scan 不能在默认启动时刷新用户可见页面派生数据或放大同步窗口。 | 默认 disabled；启用时只处理指定 matching scope。 |

## 外部风险

本模块不单独证明每个页面在每个 event 后的 UI 细节。页面行为必须由页面模块 Playwright 和组件测试覆盖；本模块只保护 event/lifecycle 合同。

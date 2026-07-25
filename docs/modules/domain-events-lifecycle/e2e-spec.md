# Domain Events Lifecycle Spec-first E2E Spec

Derived lifecycle 的 Spec-first 目标是证明显式维护 fan-out 与普通页面访问 freshness 不会混淆。前端不提供 finance domain event；最终数据事实来自后端 canonical facts、read model/worker freshness。

## Spec IDs

| Spec ID | 用户可观察合同 | 必须证明 |
| --- | --- | --- |
| `DOMAIN-E2E-001` | 页面 A 执行普通写后立即完成；B/C 即使已打开也不自动 GET。 | B/C 只在 route 重进、查询变化、浏览器手动刷新或明确重试时读取 API/read model。 |
| `DOMAIN-E2E-002` | 每个后端 lifecycle event 都能生成安全、可序列化、不会删除 protected target 的影响计划。 | `DerivedDataLifecycleService` plan 覆盖所有声明事件。 |
| `DOMAIN-E2E-003` | focus/visibility/BFCache、跨 tab 写入和旧业务事件不会产生页面业务 I/O。 | PageRouteHost 行为测试与旧 symbol/source guard。 |
| `DOMAIN-E2E-004` | import、relation、规则、no-OA、turnover 等普通写必须零下游页面 fan-out；逐个消费页被访问时独立收敛。 | canonical commit -> zero downstream jobs -> page GET -> exact dirty/outbox -> worker -> fresh。 |
| `DOMAIN-E2E-005` | startup stale scan 不能在默认启动时刷新用户可见 read model 或放大同步窗口。 | 默认 disabled；启用时只处理指定 matching dirty scope。 |

## 外部风险

本模块不单独证明每个页面在每个 event 后的 UI 细节。页面行为必须由页面模块 Playwright 和组件测试覆盖；本模块只保护 event/lifecycle 合同。

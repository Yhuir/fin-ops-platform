# 覆盖状态

| Spec ID | 执行入口 | 本轮证据 |
| --- | --- | --- |
| CASH-E2E-001 | web/e2e/cash-module-flow.spec.ts | 沿用并扩充本轮几何/业务视图断言；实际结果见实施计划§16 |
| CASH-E2E-002 | web/e2e/cash-real-api-flow.spec.ts | 由真实HTTP fixture启动；本轮运行结果见§16 |
| CASH-E2E-003 | web/e2e/cash-module-flow.spec.ts、web/e2e/cash-real-api-flow.spec.ts | 前端交互与真实API分层验证，结果见§16，不把mock等同生产写入 |
| CASH-E2E-004 | web/e2e/production-cash-readonly.spec.ts | 发布后显式只读核验；结果及限制见§16 |

统一UI与多选扩展已实现；实际验证和发布状态以实施计划§14为准。实施§12是上一轮历史，不能替代本轮展开态/多选验收。

| 范围 | 本轮状态 | 证据归属 |
| --- | --- | --- |
| 原四子页/既有合成写链/生产只读 | 历史已覆盖 | 实施§12 |
| 新表头多选/排序与Portal开关几何 | 用例已实现，最终结果见实施§14 | CashFilters/Books/Flows/Tasks/Settings及cash-module-flow.spec.ts |
| 新多选SQL/余额/旧单值API | 已通过真实PG/API回归 | test_cash_queries.py、test_cash_api.py、test_cash_http_integration.py |
| 浏览器→真实本地现金API→PG | 已接通真实写链，不以两份分层测试代替 | cash-real-api-flow.spec.ts，复用现有HTTP fixture，实施§14.2 |
| 新SQL规模、生产对照与旧页回归 | 6400规模样本已完成；生产和浏览器结果按实际记录 | 实施§14.2–14.3 |

后端测试入口见[tests.md](tests.md)；实际运行证据、失败项与生产只读核验结果在[实施计划](../../dev/cash-module-implementation-plan.md)维护，避免多份状态漂移。

# 导入中心测试

| 类别 | 适用性 | 证据 |
| --- | --- | --- |
| 业务核心 | 不适用 | 页面不定义导入业务规则 |
| Service/Repository | 适用 | import facts 分页、组合 Page Audit |
| API contract | 适用 | 摘要字段、错误 CSV、分页 |
| Read model/worker | 不新增 | 只展示既有 durable import 状态 |
| Frontend interaction | 适用 | loading/error/empty、tab、刷新、导航 |
| E2E business flow | 复用 | 三个既有导入工作流 E2E |
| Regression | 适用 | page registry、权限、App Status、三个旧导入页面 |

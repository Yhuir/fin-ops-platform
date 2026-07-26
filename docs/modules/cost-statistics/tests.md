# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_sql_projection_rules.py` | 标签、方向、金额、项目/费用分配规则 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单事务 repeatable-read、canonical 表读取、关系与标签输入 |
| Service/API | `tests/test_cost_statistics_api.py` | 五种视图、详情、导出、错误、标签保存后重新读取 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_business_read_model_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` | 首次加载、刷新、失败重试、筛选、导出、抽屉保存 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. production runtime 扫描不得发现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、详情、预览、导出、标签读取和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。

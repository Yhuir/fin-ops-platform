# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 支付申请当前金额、日常报销逐子付款项、三 OA/两流水、单/多账户、OA 完成时间范围、无效单元可见排除、重复归集冲突、收入隔离、银行事实视图 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单事务 repeatable-read、OA `approved_at` 范围下推、bank-flow 跳过 OA I/O、跨范围关系成员完整性、bank query 不读取未消费 payload、账户解析器每个 snapshot 只构造一次 |
| Service/API | `tests/test_cost_statistics_api.py` | 五种视图、bank transaction/allocation 两类详情、关系撤回、导出、错误、标签保存后重新读取、后续请求跳过全局统计、query 长度/游标合同 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_canonical_data_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` | 首次加载、五视图、OA 成本归集文案和金额列、两类详情 endpoint/抽屉、付款证据、局部 loading/error/retry、范围切换、搜索、自动分页、导出及银行事实视图回归 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. production runtime 扫描不得发现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、query 搜索、cursor 下一页、详情、预览、导出、标签读取和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。
7. 生产数据验证 `project / bank / expense_type` 按 OA 完成时间和 OA/子付款项当前金额归集；抽样核对归集金额、付款证据与关系组差异，不要求 OA 归集合计等于银行流水合计。
8. 生产数据验证时间行不输出 OA 占位项目/费用类型，标签顺序符合支出/混合/收入合同。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。
## 2026-08-10 视觉回归

- `web/src/test/CostStatisticsPage.test.tsx` 保护 HeroUI 导出中心的类型切换、字段选择和原有导出链；`DesignTokens.test.ts` 保护共享 token 完整性。

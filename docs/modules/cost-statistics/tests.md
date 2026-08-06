# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 标签、方向、支付申请、日常报销付款明细、金额守恒、无效/歧义 fail-closed、项目/费用分配规则、聚合前当前视图搜索、标签稳定排序、时间行真实银行字段 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单事务 repeatable-read、canonical 表读取、范围下推、bank-flow 跳过 OA I/O、跨月关系成员完整性、bank query 不读取未消费 payload、账户解析器每个 snapshot 只构造一次 |
| Service/API | `tests/test_cost_statistics_api.py` | 五种视图、详情、导出、错误、标签保存后重新读取、后续请求跳过全局统计、query 长度/游标合同 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_business_read_model_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` | 首次加载、局部 surface/children/rows 加载、当前视图搜索与过期请求保护、单次交互只发一个 explorer 请求、范围切换清除旧筛选、标签笔数/金额/顺序、主/子标签零金额方向项整体隐藏且零笔数保留、时间真实字段、自动分页与局部失败重试、无手动加载按钮、导出、流水详情抽屉即时打开/局部 loading/局部失败重试/关闭 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. production runtime 扫描不得发现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、query 搜索、cursor 下一页、详情、预览、导出、标签读取和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。
7. 生产数据验证 `project / bank / expense_type` 及详情、导出不出现 `多项目` / `多费用类型`，并确认分配前后银行流水总额守恒。
8. 生产数据验证时间行不输出 OA 占位项目/费用类型，标签顺序符合支出/混合/收入合同。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。

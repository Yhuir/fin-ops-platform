# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | 五视图同一银行成本事件、银行日期、逐流水按 OA 权重最大余数分摊、同关系“付错退款”负成本、普通收入隔离、进行中 OA 整组排除、零权重保护、无 OA 虚拟项目逐笔判断、缺失费用类型保留桶、重复关系冲突 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单事务 repeatable-read、五视图银行日期范围下推、范围银行命中 relation 后批量读取 OA、范围外银行成员隔离、bank query 不读取未消费 payload、账户解析器每个 snapshot 只构造一次 |
| Service/API | `tests/test_cost_statistics_api.py` | 五视图净额对账、逐流水详情、无 OA 候选/保存/CAS/逐笔隔离、进行中 OA 排除、关系撤回、预览/导出字段、错误、后续请求跳过全局统计、query 长度/游标合同 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_canonical_data_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| OA 归一化 | `tests/test_mongo_oa_adapter.py` | 支付申请精确读取可配置 `category`、日常报销明细精确读取 `purposeType`、表单字段互不覆盖、空/未知值不伪造“其他” |
| Settings | `tests/test_app_settings_service.py` | 无 OA 项目名/标签默认空、选择标签必须命名、schema v3 迁移、CAS、候选校验、标签归档不静默改写选择 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx` | 首次加载、五视图、`按费用类型`、成本明细、行级详情类型、OA 原额/比例/差额、无 OA 抽屉编辑校验/空候选/保存、局部 loading/error/retry、范围切换、搜索、自动分页和导出 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. whole-repo 扫描不得保留 OA-first 金额、OA 日期 scope、“混合支付账户”、默认全选、按 view 推断详情或标签归档静默删除选择的运行时旧链；production runtime 也不得出现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、query 搜索、cursor 下一页、两类详情、预览、导出、无 OA 候选/空默认和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。
7. 生产数据在相同 scope 下验证五视图根层净额一致，并抽样核对每条银行事件分摊和按分闭合；1050 支出与同关系 35“付错退款”应以 1015 实际现金成本参与比例分摊。
8. 生产验证进行中 OA 整组不统计；无 OA 候选只含实际无 active OA 的支出标签，同标签已有 OA 流水不进入虚拟项目；默认项目名和选择均为空。
9. OA v8 同步后核对支付申请有效 `category` 恢复标准费用类型；残余空/非法源字段保持“未填写 OA 费用类型”，不以“归零 115”作为无证据硬门槛。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。
## 2026-08-10 视觉回归

- `web/src/test/CostStatisticsPage.test.tsx` 保护 HeroUI 导出中心的类型切换、字段选择和原有导出链；`DesignTokens.test.ts` 保护共享 token 完整性。

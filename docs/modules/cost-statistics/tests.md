# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | time/bank_tag 原始银行事实与三个归因视图隔离、银行日期、关系净支出两级最大余数分摊、同关系/跨月“付错退款”只冲减支出归因、多支出多账户、OA 与净支出不等时的比例方向、进行中 OA 只从归因排除、partial OA fail-closed、零权重保护、多无 OA 虚拟项目逐笔判断、缺失费用类型保留桶、重复关系冲突 |
| 标签边界 | `tests/test_cost_statistics_bank_tags.py` | 无 effective code 的候选文案保持“未标记”；单层内部往来款只生成一个稳定主/子标签路径 |
| Repository | `tests/test_cost_statistics_canonical_repository.py` | 单事务 repeatable-read、time/bank_tag 快路径跳过 OA/relation I/O、无 OA 候选快照排除已有 OA/收入且不读取 OA payload、空银行集合跳过分类查询、银行 owner 规范分类投影映射、归因 scope 命中 relation 后批量读取完整银行/OA 成员、范围外事件不输出、bank query 不读取未消费 payload、账户解析器每个 snapshot 只构造一次 |
| Service/API | `tests/test_cost_statistics_api.py` | 两个视图人口各自对账、退款只进入净归因与详情证据、不生成退款 allocation、原始流水方向不变、逐流水详情、按标签/按时间 all/custom 规则、无 OA 多项目候选/保存/CAS/互斥/空项目拒绝且版本不推进/逐笔隔离、进行中 OA 隔离、关系撤回、预览/导出字段、错误、query 长度/游标合同 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_canonical_data_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| OA 归一化 | `tests/test_mongo_oa_adapter.py` | 支付申请精确读取可配置 `category`、日常报销明细精确读取 `purposeType`、表单字段互不覆盖、空/未知值不伪造“其他” |
| Settings | `tests/test_app_settings_service.py` | time/tag 默认 all 与独立 CAS、无 OA 项目数组默认空、稳定 ID/名称/至少一个标签/标签互斥、旧单项目配置一次性归一化、候选校验、历史标签不静默丢失 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx`、`CostExplorerList.test.tsx`、`CostEntryDetailPanel.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | 首次加载、五视图、`按费用类型`、成本明细、行级详情类型、本项净成本/OA 原额/支出原额/关系净支出、退款负数证据、两个独立规则抽屉、全选/清空、无 OA 主子标签层级/单层叶子/空项目禁存、多虚拟项目折叠编辑与互斥、只读权限、局部 loading/error/retry、搜索、自动分页、导出、长文本实际溢出检测、固定行高展开/折叠、单列表单 Popover、Escape/选择/尺寸变化关闭，以及时间选择器在桌面和窄内容区不压缩、不截断、不横向溢出 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. whole-repo 扫描不得保留 OA-first 金额、OA 日期 scope、“混合支付账户”、按 view 推断详情、旧单抽屉 `/tag-rules` 或 `bank_flow_rows -> cost allocations` 耦合；production runtime 也不得出现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、query 搜索、cursor 下一页、两类详情、预览、导出、无 OA 候选/空默认和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。
7. 生产数据在相同 scope 下分别验证 time/bank_tag 原始流水总额一致、project/bank/expense_type 归因净额一致，并抽样核对关系净支出两级分摊和按分闭合；1050 支出与同关系 35“付错退款”应只生成真实支出锚定的 1015 净成本，OA 合计同为 1015 时住宿费 710 保持 710，抽屉显示 -35 退款证据。
8. 生产验证进行中 OA 只出现在原始流水视图；无 OA 候选只含实际无 active OA 的支出标签，同标签已有 OA 流水不进入虚拟项目；默认虚拟项目数组为空。
9. OA v8 同步后核对支付申请有效 `category` 恢复标准费用类型；残余空/非法源字段保持“未填写 OA 费用类型”，不以“归零 115”作为无证据硬门槛。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。
## 2026-08-10 视觉回归

- `web/src/test/CostStatisticsPage.test.tsx` 保护 HeroUI 导出中心的类型切换、字段选择和原有导出链；`DesignTokens.test.ts` 保护共享 token 完整性。

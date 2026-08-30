# 成本统计测试矩阵

## 自动化测试

| 类别 | 文件 | 保护内容 |
| --- | --- | --- |
| 业务核心 | `tests/test_cost_statistics_policy.py` | time/bank_tag/bank 的真实净支出 `N` 与 project/expense_type 成本 `C` 隔离、`O=N` 任意拓扑自动归因、`O!=N` 待人工、`N=0` 排除、`N<0` 冲突、支付申请整单/日常报销逐明细单元、逐单元人工金额与 `C+X=N`、不伪造来源映射、最新支出时间只作确定性事件锚点、进行中 OA 隔离、partial OA fail-closed、多无 OA 虚拟项目、缺失费用类型、重复关系冲突 |
| 标签边界 | `tests/test_cost_statistics_bank_tags.py` | 无 effective code 的候选文案保持“未标记”；单层内部往来款只生成一个稳定主/子标签路径 |
| Repository / migration | `tests/test_cost_statistics_canonical_repository.py`、`tests/test_postgres_migrations.py` | 单事务 repeatable-read、银行事实快路径跳过 OA/manual I/O、人工分配批量读取、单 case 锁定、schema 从旧多维分配列收敛为 `unit_allocations/non_cost_amount/non_cost_reason`、旧 signed aggregate 数据迁移、约束/角色权限/versioned update、运行时无 DELETE |
| Service/API | `tests/test_cost_statistics_api.py` | GET pending/allocated 全量计数、搜索/cursor；PUT 逐 OA 单元 DTO，拒绝 `source_kind/source_id`、缺项/重复/负数/精度错误；`X=0` 禁止原因、`X>0` 要求原因且 `C+X=N`；有效保存/编辑/审计、source/version 409、权限失败、关系撤回、导出待分配说明、两个事实集合各自对账、query 长度/游标合同 |
| Audit | `tests/test_cost_statistics_page_audit.py`、`tests/test_audit_page_canonical_data_tool.py` | 直接事实源合同与关系成员完整性 |
| Runtime regression | `tests/test_platform_runtime_boundary_guards.py`、registry/manifest/scope/worker tests | 旧 Cost read-model 链路保持删除 |
| OA 归一化 | `tests/test_mongo_oa_adapter.py` | 支付申请精确读取可配置 `category`、日常报销明细精确读取 `purposeType`、表单字段互不覆盖、空/未知值不伪造“其他” |
| Settings | `tests/test_app_settings_service.py` | time/tag 默认 all 与独立 CAS、无 OA 项目数组默认空、稳定 ID/名称/至少一个标签/标签互斥、旧单项目配置一次性归一化、候选校验、历史标签不静默丢失 |
| Frontend | `web/src/test/CostStatisticsApi.test.ts`、`CostStatisticsPage.test.tsx`、`CostExplorerList.test.tsx`、`CostEntryDetailPanel.test.tsx`、`web/e2e/cost-statistics-flow.spec.ts` | 初始 loading/empty/error、标题行 tabs、紧凑 HeroUI 时间 Popover、Disclosure 懒展开、支付申请整单/日常报销逐明细输入、每关系独立保存、`X` checkbox 条件展示与原因校验、400/409 保留草稿、已分配编辑、正常上海时间、五视图右侧明细显式 cursor 分页、分页错误局部重试、滚动不触发请求、搜索/权限/窄屏、五视图口径、导出与旧规则抽屉回归 |

## 候选发布门禁

1. 后端定向测试、前端定向测试、lint、build 全部通过。
2. 全仓 pytest collection 不得引用已删除模块。
3. whole-repo 扫描不得保留 OA mismatch 自动缩放、默认项目/首项兜底、OA-first 金额、OA 日期 scope、“混合支付账户”、按 view 推断详情、旧单抽屉 `/tag-rules` 或 `bank_flow_rows -> cost allocations` 耦合；production runtime 也不得出现 Cost read-model event/worker/gateway/manifest。
4. 部署后验证 explorer 五种视图、query 搜索、右侧明细显式 cursor 上一页/下一页、两类详情、预览、导出、无 OA 候选/空默认和 Audit。
5. 多次测量 API duration，报告 p50/p95/max。
6. 验证 Cost 请求前后没有新增 Cost outbox/dirty scope，其他关键页面 smoke 正常。
7. 生产数据在相同 scope 下验证 `project/expense_type=C`、`bank/bank_tag/time=N`；抽样验证 `O=N` 的 1×1、3×3、3×2 关系都不进入待分配，`O!=N` 全量进入 pending，人工保存满足 `C+X=N`。确认支付申请只输入一次、日常报销逐明细输入一次、各关系独立保存，项目/费用时间锚点不被解释为银行来源归属。
8. 生产验证进行中 OA 只出现在原始流水视图；无 OA 候选只含实际无 active OA 的支出标签，同标签已有 OA 流水不进入虚拟项目；默认虚拟项目数组为空。
9. OA v8 同步后核对支付申请有效 `category` 恢复标准费用类型；残余空/非法源字段保持“未填写 OA 费用类型”，不以“归零 115”作为无证据硬门槛。

不运行 183 个浏览器测试或无关全量 CI；只运行成本统计及直接受影响的回归门禁。

## 七类测试适用性

1. **业务核心：适用。** 金额等式、状态分类、退款、非成本金额、零/负净支出和来源归属禁令都必须有正反例。
2. **Service/Repository：适用。** 保护单事务保存+审计、乐观冲突、迁移、幂等重试和无半写入。
3. **API 合同：适用。** 保护 GET/PUT shape、400/403/409、非法来源字段及刷新后新快照。
4. **Read model/cache/job：不适用。** 本模块直接 canonical read；测试以“无 outbox/dirty scope/cache/worker I/O”的负面断言代替刷新测试。
5. **前端组件与交互：适用。** 覆盖 Drawer、Disclosure、每关系保存、条件字段、时间格式、搜索/分页/权限/错误。
6. **端到端业务流：适用。** 至少覆盖 mismatch pending→保存含 X→allocated→编辑，以及 equal 自动、409 冲突与关系撤回。
7. **既有功能回归：适用。** 五视图金额口径、详情/导出、无 OA、标签/时间规则、权限、过滤排序分页均受影响。
## 2026-08-10 视觉回归

- `web/src/test/CostStatisticsPage.test.tsx` 保护 HeroUI 导出中心的类型切换、字段选择和原有导出链；`DesignTokens.test.ts` 保护共享 token 完整性。

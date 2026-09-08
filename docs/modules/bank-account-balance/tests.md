# 银行账户余额测试矩阵

> 账户余额不再是独立 read model。它是银行明细页面 canonical accounts query 的聚合结果。

## 当前合同

- 直接从 canonical 银行流水按账户聚合可靠组末余额、来源日期和范围笔数；完整逐笔顺序与组末余额独立判断。
- 不读取 `read_model.bank_account_balances`，不等待 `bank_account_balance:all`，不 enqueue。
- 账户结果不受 transactions 当前页分页限制；筛选和权限由银行明细 route/query 合同负责。
- 历史 migration 文件只作不可变记录；migration `0149` 已删除 projection schema。
- `balance_status` 必填；confirmed/last_known 可展示原值，unresolved/missing 为 null。币种完整合计只包括全部账户均 confirmed 的币种，null 不补零，真实零保留。
- 同账户多币种优先 unresolved 且展示币种为 null，各底层币种总额均不完整；单币种全历史无余额为 missing。账户 metadata 一致性、既有 identity 和空币种按 CNY 归一继续保护。

## 测试责任

| 七类测试 | 适用性与入口 |
| --- | --- |
| 1. 业务核心 | 适用：`tests/test_bank_same_time_ordering_postgres.py` 通过真实 SQL 验证唯一链、分支终点、断链/闭环、缺时间/余额、signed amount 冲突、真实零、币种和账号边界。 |
| 2. Service/repository | 适用：同一真实 PG 文件及 `tests/test_bank_details_canonical_query.py`，覆盖 snapshot、完整组、日期仅影响笔数、metadata 一致性、来源 ID 可空、固定查询数和账户不丢失。 |
| 3. API contract | 适用：`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`，覆盖状态、null、来源、旧字段/参数/权限和缺状态错误。 |
| 4. Read model/cache/job | 无新增正向测试：本次仅请求内查询，无对应 runtime；`tests/test_read_model_runtime_removal.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py` 保留退役负向回归。 |
| 5. 前端交互 | 适用：`web/src/test/BankDetailsPage.test.tsx`，覆盖 loading/empty/error/账户选择、last_known 来源日期、待核实/缺失、null 不显示零、真实零、切账户晚返回、账户失败不被流水成功清除，以及旧 header 刷新不覆盖新规则响应。 |
| 6. 端到端业务集成 | 适用：`tests/test_bank_same_time_ordering_postgres.py` 的正式 import/withdrawal owner 闭环；浏览器入口为 `web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts`。完整文件预览/确认至实际下载验收和 mock E2E 分别记录，不能混称真实 PG 闭环。 |
| 7. 既有回归 | 适用：原账户 identity/metadata、范围/总笔数、分类/关系/导出字段、权限和现金隔离；Bank Details 模块矩阵包含其共享调用方。 |

最新组全部缺余额只检查最近有余额历史组，可靠则 last_known；该历史组有冲突时必须 unresolved，禁止越过它找更老数字。部分缺余额不能沿用历史余额。分支组终点固定但末笔身份不唯一时，金额/时间可用而 ID 为 null。上述断言必须通过真实 SQL，不仅检查 SQL 文本。

旧账户 reader/helper/state-store wrapper 和独占 fake 删除后，其余额来源、日期仅影响笔数、范围外无余额账户、真实账号和一致 metadata 断言已迁入 `tests/test_bank_same_time_ordering_postgres.py`，该文件当前 29 项。账户只对最新/最后非空目标组运行复杂判定，候选整日精度证据仍须完整；该优化不能改变原断言。

2026-09-08 真实 PostgreSQL 29 项已有一轮通过；最新重跑与性能测量由修复计划记录。前端完整轮次及最后竞态修复后的专项/build/浏览器结果见银行明细测试矩阵。本地验证中，未发布。

验证命令复用[银行明细测试矩阵](../bank-details/tests.md)。真实 PostgreSQL 使用隔离测试库；固定查询数不代表性能通过，执行计划、扫描量、尾延迟和部署结果见[修复计划](../../dev/bank-same-time-ordering-repair-plan.md)的实际记录。

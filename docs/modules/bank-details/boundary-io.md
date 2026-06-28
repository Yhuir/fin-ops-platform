# 银行明细模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：银行明细页面直接读取 accounts/transactions/rules/export API DTO；标签、分类、自动规则写成功后直接重读交易列表。
- 当前缺口：页面与下游标签读取已改为 direct facts；历史 PostgreSQL migration / 运维记录中仍会保留旧 `bank_detail` 表名作为历史上下文。
- 旧代码删除条件：当前 runtime 已删除 `bank_detail` / `bank_account_balance` 投影、worker、manifest、deploy env 和 repository port；未来只在显式 migration/schema 清理任务中处理历史表定义。

## 职责边界

### 负责

- 银行流水列表、账户筛选、标签/分类展示、自动标签规则、导出。
- 维护银行明细 direct API 页面合同。
- 标签/分类/自动规则写操作的后端响应仅保留 scope-only envelope 作为影响范围诊断；当前前端写成功后直接刷新银行流水，mapper 不再暴露 旧投影状态/target fields，也不再消费旧操作屏障做写后等待。
- 为下游 workbench/no-OA/turnover 关系提供银行流水身份和标签读取边界。

### 不负责

- 不拥有银行流水导入流程。
- 不直接维护 no-OA、外部往来款或关联台关系事实。
- 不绕过 bank detail service/UoW 直接写标签副作用。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面过滤、月份、账号、标签操作 | `BankDetailsPage.tsx`、`features/bankDetails/api.ts` | API 入参必须映射到明确查询/filter contract |
| 标签/分类写操作 | route/service | 通过 write UoW 触发受影响 month scope |
| 自动标签规则保存/重跑 | `BankDetailsApplicationService` | 响应只暴露 `affected_scope_keys`；前端只消费保存结果并直接重读交易 |
| 旧刷新范围 | 不适用 | bank_detail 不再有 active 旧投影 旧刷新范围；页面和下游直接重读银行流水/分类事实 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 银行明细列表/账户/标签 payload | 前端页面 | direct payload；后端页面 GET/export 不读取 SQL 旧投影、Redis page cache 或旧投影同步字段 |
| 自动标签规则写入结果 | 前端页面 | 写成功后直接重新请求银行流水；前端 mapper 不暴露 旧投影状态 或 target arrays |
| 标签副作用 | turnover/workbench/audit 下游 | 通过 direct side-effect port 和 lifecycle 传播；不入队 `bank_detail` 旧刷新事件 |
| 导出文件 | 用户下载 | 复用当前查询边界，不绕过权限 |

## 持久化与投影

- Page query：`BankDetailsApplicationService` -> `BankDetailsService`
- Downstream category read：`BankTransactionEffectiveCategoryProvider`
- Legacy projection / worker / repository owner：已从当前 runtime 删除；历史 migration/table 只作为历史记录。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BankDetailsPage.tsx` |
| Frontend feature | `web/src/features/bankDetails/*`、`web/src/components/BankAccountValue.tsx` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_details.py`、`bank_detail_category_api.py` |
| Backend service | `bank_details_application_service.py`、`bank_details_service.py`、`bank_detail_*`、`bank_transaction_*`、`bankdetail_write_uow.py` |
| Repository / SQL | direct bank facts/category repositories and `postgres_repositories/read_models.py` for remaining non-bank-detail 旧投影 |
| Worker/旧投影 | 无 active bank_detail 旧投影 worker |
| Tests | `tests/test_bank_details*.py`、`tests/test_bank_detail*.py`、`web/src/test/BankDetails*.test.*`、`web/e2e/bank-details-*.spec.ts` |

## 依赖方向

- 允许依赖：bank transaction identity/category service、导出 service、direct effective category provider。
- 必须通过：BankDetailsApplicationService 和 write UoW。
- 禁止绕过：直接写 旧投影表、直接从前端推断同步状态、在导入模块里改银行明细页面投影。

## 测试与验证

- Service/direct provider：`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_service.py`。
- API/frontend：`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`。
- E2E：`web/e2e/bank-details-*.spec.ts`。
- 后端 scope-only envelope 回归：`BankDetailSqlRepositoryTests.test_category_mutation_response_returns_bank_detail_scope_keys_only`；`web/src/test/BankDetailsApi.test.ts` 只覆盖前端业务 mapper，不再暴露 旧投影目标 arrays；前端页面回归断言不再请求旧操作屏障。

## 当前缺口和删除条件

- 将本文件补齐的后端入口同步到模块 README。
- 页面 read path 已不再依赖 SQL 旧投影；后续删除后台兼容投影前，必须验证写标签、自动规则、导出、下游 relation tag、后台任务收敛和运维工具。
- bank_detail runtime deletion 已覆盖 producer/worker/manifest/deploy/repository/SQL helper；前端不再保留 unknown-status fail-closed 断言。

# 银行明细模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：银行明细页面读取 `bank_detail` read model；标签、分类、自动规则等写操作通过 service/UoW 触发 scoped dirty refresh。
- 当前缺口：模块 README 只登记了前端入口，后端 service/read model 文件已在本文件补齐，后续应同步回 README。
- 旧代码删除条件：没有 API 或页面继续走旧的非 fresh-gated 查询路径。

## 职责边界

### 负责

- 银行流水列表、账户筛选、标签/分类展示、自动标签规则、导出。
- 维护 `bank_detail` scoped read model freshness。
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
| Refresh scope | `bank_detail` manifest | month or `all`；`all` 只允许 fan-out 到 month shards |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 银行明细列表/账户/标签 payload | 前端页面 | 必须带 freshness/status |
| 标签副作用 | relation/downstream read models | 通过 lifecycle/gateway 传播 |
| 导出文件 | 用户下载 | 复用当前查询边界，不绕过权限 |

## 持久化与投影

- Read model：`bank_detail`
- Projection：`partitioned_scoped_incremental`
- Worker：`bank-detail`
- Query owner：`BankDetailsApplicationService`
- Repository owner：`BankDetailReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BankDetailsPage.tsx` |
| Frontend feature | `web/src/features/bankDetails/*`、`web/src/components/BankAccountValue.tsx` |
| Backend route | `backend/src/fin_ops_platform/app/routes_bank_details.py`、`bank_detail_category_api.py`、`bank_detail_backfill.py` |
| Backend service | `bank_details_application_service.py`、`bank_details_service.py`、`bank_detail_*`、`bank_transaction_*`、`bankdetail_write_uow.py` |
| Repository / SQL | `bank_detail_read_model_repository.py`、`bank_detail_sql_projection.py`、`postgres_repositories/read_models.py` |
| Worker/read model | `bank_detail_read_model_refresh.py`、`bank_detail_read_model_refresh_producer.py`、`bank_detail_derived_lifecycle_executor.py` |
| Tests | `tests/test_bank_details*.py`、`tests/test_bank_detail*.py`、`web/src/test/BankDetails*.test.*`、`web/e2e/bank-details-*.spec.ts` |

## 依赖方向

- 允许依赖：read model repository、bank transaction identity/category service、runtime queue。
- 必须通过：BankDetailsApplicationService 和 write UoW。
- 禁止绕过：直接写 read model 表、直接从前端推断 fresh、在导入模块里改银行明细页面投影。

## 测试与验证

- Service/read model：`tests/test_bank_details_sql_runtime.py`、`tests/test_bank_details_service.py`。
- API/frontend：`tests/test_bank_details_routes.py`、`web/src/test/BankDetailsApi.test.ts`、`web/src/test/BankDetailsPage.test.tsx`。
- E2E：`web/e2e/bank-details-*.spec.ts`。

## 当前缺口和删除条件

- 将本文件补齐的后端入口同步到模块 README。
- 删除旧查询路径前，必须验证写标签、自动规则、导出和 stale/refreshing UI。

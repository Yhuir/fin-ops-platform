# 批量账务模块边界与 I/O

日期：2026-07-01

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：批量账务页面通过 BatchAccounting service 操作批量关系和账务候选，关系事实写入必须走 workbench relation 边界。
- 当前缺口：批量账务依赖 workbench relation read/write 和 lifecycle，模块本身没有独立 read model manifest。
- 旧代码删除条件：旧 server.py 批量账务入口不再承载业务逻辑，所有关系写入走 command service。

## 职责边界

### 负责

- 批量账务页面、批量选择、批量关系操作和账务候选展示。
- 调用 workbench relation 事实源完成关系写入。
- 触发相关 derived lifecycle/read model refresh。
- 定义右侧 OA 候选：日常报销 OA 主单，且没有关联银行流水；仅发票关系或无流水候选关系不排除该 OA，不再按 OA 年份过滤。

### 不负责

- 不拥有 workbench relation 表。
- 不直接维护 bank/invoice/turnover 源事实。
- 不直接写 read model projection。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面批量选择/操作 | `BatchAccountingPage.tsx`、`features/batchAccounting/api.ts` | 进入 batch accounting API/service |
| 批量账务候选 payload | Workbench SQL active read model，fallback 为 Workbench payload builder | GET 列表和 submit 行校验都应优先走 `load_batch_accounting_workbench_payload(bank_year=...)`，不能在提交热路径默认扫描全量旧工作台 |
| workbench row context | `BatchAccountingService._build_workbench_row_context` | 只解析 row/index/invoice links，不读取整页 relation distribution |
| list context | `BatchAccountingService._build_list_context` | 仅列表读取使用，先构造 Workbench row context，再通过候选级 relation distribution 产出 eligible bank/OA |
| unsubmitted relation context | `BatchAccountingService._context_with_candidate_relation_distribution` | 未提交列表只把批量账务银行候选和日常报销 OA 候选传入 `workbench_relation` facade；禁止把 Workbench 全量 open OA 当作 relation lookup 输入 |
| submitted relation count | `WorkbenchRelationReadFacade.count_batch_accounting_relations_by_year` | 未提交列表 summary 只读取年份级 batch-accounting relation count；不能为了 `submitted_count` 扫描 12 个月完整 relation DTO |
| submit context | `BatchAccountingService._build_submit_context` | 仅提交使用，禁止读取整页 relation distribution；relation readiness 只按本次 row ids 校验 |
| 关系写入请求 | `BatchAccountingService` | 必须委托 workbench relation command boundary |
| lifecycle trigger | derived data lifecycle | 更新下游 read model scopes |
| OA 候选事实 | Workbench active read model + `workbench_relation` read facade | 不接收 OA 年份；“没有流水”表示 relation distribution 中该 OA 没有 `linked_bank_transactions`，仅发票关系或无流水候选关系仍可进入批量账务右侧 OA 栏 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 批量账务操作结果 | 前端页面 | 返回成功/失败、受影响对象、`affected_months`、`affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Relation dirty scopes | workbench relation/read model | 不直接写下游 payload |
| Audit/result | audit/job status | 重要批量操作可追踪 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Downstream read model：主要影响 `workbench_relation` 和其下游 fan-out。
- Worker：依赖 runtime worker registry 中的 workbench relation/read model workers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/BatchAccountingPage.tsx` |
| Frontend feature | `web/src/features/batchAccounting/api.ts`、`types.ts` |
| Backend route | `backend/src/fin_ops_platform/app/routes_batch_accounting.py`、历史 `server.py` |
| Backend service | `backend/src/fin_ops_platform/services/batch_accounting_service.py` |
| Relation dependency | `workbench_pair_relation_service.py`、`workbench_relation_read_facade.py`、`workbench_relation_sql_projection.py`、`workbench_relation_read_model_refresh.py` |
| Lifecycle/worker | `derived_data_lifecycle_service.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |

## 依赖方向

- 允许依赖：workbench relation command/read facade, derived lifecycle service。
- 必须通过：BatchAccountingService then relation boundary。
- 禁止绕过：直接写 relation/read model 表；在页面批量合成业务状态。
- 未提交列表 relation lookup 必须以页面可展示/可提交候选行为输入；`submitted_count` 必须走 relation facade 的轻量 count I/O，不能回退到 submitted relation 明细扫描污染首屏读路径。
- submit 写操作必须经过 `_build_submit_context`，只按本次选中的银行/OA/发票 row ids 请求 relation readiness 和 active relation；不能调用 `_build_list_context` 或为了校验一次提交扫描整页银行/OA relation distribution。

## 测试与验证

- `tests/test_batch_accounting_api.py`
- `web/src/test/BatchAccountingApi.test.ts`
- `web/src/test/BatchAccountingPage.test.tsx`
- `web/e2e/batch-accounting-flow.spec.ts`

## 当前缺口和删除条件

- 如果新增独立 read model，必须先登记 manifest/scope policy/worker/tests/docs。

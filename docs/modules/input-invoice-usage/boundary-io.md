# 进项发票使用情况模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：high
- 目标边界：进项发票使用情况通过 `input_invoice_usage` read model 查询；OA 反提和规则写入通过 service 边界产生受影响 scope。
- 当前缺口：OA reverse、applicant credentials 和 workbench relation 依赖交织，变更时必须同步权限和 freshness。
- 旧代码删除条件：旧 service 直读路径不再被 API 调用，fresh gate tests 覆盖。

## 职责边界

### 负责

- 进项发票使用情况页面列表、筛选、明细、OA 反提和使用规则。
- `input_invoice_usage` scoped read model。
- 与 invoice usage collection worker 的 event 合同。
- OA reverse 创建草稿、撤回本地草稿绑定等写操作返回 `input_invoice_usage` write target envelope，用于页面或调用方等待受影响月份 fresh。

### 不负责

- 不拥有 OA 登录/凭证的底层认证事实。
- 不直接维护关联台关系事实源。
- 不处理销项发票收款业务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/明细 | `InputInvoiceUsagePage.tsx`、`features/inputInvoiceUsage/api.ts` | 进入 read model service/fresh gate |
| OA reverse 写操作 | `input_invoice_usage_oa_reverse_service.py` | 必须带 OA applicant context 和审计 |
| OA reverse target envelope | `InputInvoiceUsageOaReverseService.batch_payload(...)` | 从 batch invoice display rows 提取 invoice month；无月份时退回 `all`，并返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` |
| Refresh scope | `input_invoice_usage` manifest | month or `all`；`all` 是 fan-out command |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 使用情况 rows/details | 前端页面 | fresh/status 可见 |
| OA reverse 结果 | API/OA | 业务写后触发 dirty scope |
| OA reverse 写后 freshness target | API/frontend/operation barrier | `read_model_key=input_invoice_usage`、`scope_key=<invoice month>` |
| Dirty scope | runtime queue | `input_invoice_usage.read_model.refresh` |

## 持久化与投影

- Read model：`input_invoice_usage`
- Projection：`scoped_incremental`
- Worker：`invoice-usage-collection`
- Query owner：`InputInvoiceUsageReadModelService`
- Repository owner：`InputInvoiceUsageReadModelRepositoryPort`

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/InputInvoiceUsagePage.tsx` |
| Frontend feature/components | `web/src/features/inputInvoiceUsage/*`、`web/src/components/inputInvoiceUsage/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`、`routes_input_invoice_usage_oa_reverse.py` |
| Backend service | `input_invoice_usage_service.py`、`input_invoice_usage_oa_reverse_service.py`、`input_invoice_usage_payment_rules.py`、`input_invoice_usage_read_model_*` |
| Repository / SQL | `input_invoice_usage_read_model_repository.py`、`invoice_usage_collection_sql_projection.py`、`postgres_repositories/input_invoice_usage_oa_reverse.py` |
| OA dependencies | `oa_applicant_credentials.py`、`target_oa_applicant_token_provider.py`、`postgres_repositories/oa_applicant_credentials.py` |
| Tests | `tests/test_input_invoice_usage*.py`、`web/src/test/InputInvoiceUsage*.test.*`、`web/e2e/input-invoice-*.spec.ts` |

## 依赖方向

- 允许依赖：OA credential provider, workbench relation read facade, invoice usage projection。
- 必须通过：InputInvoiceUsage service/read model service。
- 禁止绕过：service 直接读取 HTTP cookie/header；页面绕过 fresh gate。

## 测试与验证

- `tests/test_input_invoice_usage_api.py`
- `tests/test_input_invoice_usage_read_model_fresh_gate_service.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_input_invoice_usage_oa_reverse_service.py` 覆盖 OA reverse 创建/撤回后的 target envelope。
- `web/e2e/input-invoice-usage-flow.spec.ts`

## 当前缺口和删除条件

- OA reverse 变更必须覆盖权限、凭证、审计和 read model recovery。

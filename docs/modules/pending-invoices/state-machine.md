# 待找发票状态机

> 页面状态由 canonical facts 和后端 policy 给出；前端不得自行推断发票获取状态。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 方向 | `expense` | canonical bank `txn_direction=outflow` | 支出流水查找进项发票。 |
| 方向 | `income` | canonical bank `txn_direction=inflow` | 收入流水查找销项发票。 |
| 规则组 | `requires_invoice` | active bank tag complement | 由 active 标签减去可编辑 no-invoice/cash/statement 分组实时派生。 |
| 规则组 | `bank_statement_as_invoice` | expense pending invoice rules | 只适用于支出。 |
| 规则组 | `no_invoice_required` | expense/income rules | 支出或收入都可配置。 |
| 规则组 | `cash_income` | income rules / income status override | 只适用于收入现金场景。 |
| 行状态 | `paid_pending_invoice` / `paid_invoiced` / `invoice_not_fully_paid` / `no_invoice_required` / income variants | canonical bank/invoice/OA/relation facts + `pending_invoice_status_payload` | 页面只展示 API 返回的 `invoice_acquisition_status`。 |
| 选择已有发票 | `attach_previewed` / `attach_confirmed` | existing application service + canonical relation command | 只允许 expense 行选择 input invoice；confirm 保留权限、冲突、幂等、audit 和 command log。 |
| 收入状态覆盖 | `income_no_invoice_required` / `cash_income` | `app.pending_invoice_manual_invoice_commands` | 只适用于未关联销项发票的收入行。 |
| command log | `created` / `relation_created` / `finalized` / `failed_terminal` | command repository | confirm 中断后可重试，不重复创建关系。 |

关键规则：

- `filter=requires_invoice` 是最终状态桶，不是 `filter_group='requires_invoice'` 条件。
- 正式关系只读取 active `app.workbench_pair_relations`；`turnover_manual_closure` 不属于待找发票事实。
- relation 可跨月；同一 relation 的银行、invoice、OA members 一次批量展开并折叠成页面行。
- 支出已有关联进项发票时可为 `paid_invoiced` 或 `invoice_not_fully_paid`；收入关联销项发票优先于收入 override。
- `pending_invoice_tag_groups.version` 与 `pending_output_invoice_tag_groups.version` 独立。
- candidates 的 `candidate_status`、`bank_relation_status` 和 `linked_bank_transaction_count` 由 canonical active relation 计算，前端不得用金额推断。
- 写 API 成功后重新 GET canonical facts，不等待 pending/search/invoice-lifecycle read-model barrier。

禁止流转：

- 禁止前端根据缺失字段猜测 status 或 primary action。
- 禁止读取 pending/bank-detail/workbench-relation/search read model 作为页面事实。
- 禁止恢复 refresh enqueue、polling、202、stale/fallback 或双读。
- 禁止候选 relation case id 被当作真实 OA id。
- 禁止收入规则污染支出规则，或支出规则污染收入规则。
- 禁止 attach existing 重复创建 relation 或绕过 canonical version/occupation conflict。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | rows/filter-options/detail/rules 请求进行中 | 展示加载态；abort/unmount 后清理。 |
| empty | 成功响应且 total 为 0 | 当前 query 的合法真实空集。 |
| error | rows/detail/rules/attach/income status/export 请求失败 | 展示可重试业务错误；不能伪装 empty。 |
| rules drawer | 用户打开规则配置 | 读取当前 direction rules；stale version 仍返回 conflict。 |
| attach existing drawer | 用户选择 eligible expense rows | canonical candidates；preview 展示 conflicts/warnings；confirm 成功后 refetch。 |
| expense selection | 用户勾选支出流水 | 仅有 `attach_existing_invoice` action 的行可进入批量选择。 |
| income selection | 用户勾选收入流水 | 仅有 `mark_income_status` action 的行可批量标记。 |
| relation member list | 用户点击 kind 明细 | 只展示 `bank|invoice|oa` 对应成员。 |
| permission disabled/hidden | session permissions | 只读用户不能规则保存、attach 或 income override。 |

页面没有 `refreshing` 或 `stale` UI 状态。返回 route、query 变化、明确刷新、写成功或错误重试时发起一次正常 GET；不启动定时 polling，也不监听 read-model worker 状态。

## 一致性状态

| 状态 | 判定 | 页面行为 |
| --- | --- | --- |
| snapshot success | repository 在 `REPEATABLE READ / READ ONLY` 中完成 settings + bounded query | 返回 rows、summary、statistics、facets/counts。 |
| canonical empty | snapshot 成功且 total=0 | 返回 200 empty。 |
| invalid query | service 参数验证失败 | 返回 400，不执行页面 SQL。 |
| permission denied | read/write session 无权限 | 返回 401/403。 |
| canonical unavailable | PostgreSQL query/connection 失败 | 返回 error；不读旧 read model fallback。 |
| policy divergence | SQL status 与 `pending_invoice_status_payload` 不一致 | fail closed；不返回混合口径。 |

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-07-27 | 页面改为 canonical PostgreSQL 直读，删除 read-model/polling/202/fallback UI 状态 | page API/service/repository/frontend/docs | canonical repository/API tests、PendingInvoices Vitest、真实 PostgreSQL smoke |
| 2026-07-07 | 多流水展示真实对方户名，发票/OA 多成员保持分区明细 | table/API mapper | `PendingInvoicesPage.test.tsx` |
| 2026-06-17 | 候选关系 chip 和 attach active case restore | candidate/application service | pending invoice service/API/frontend tests |

# Spec-first E2E Inventory

本文维护页面、功能和跨页面链路的 Spec-first E2E 审计队列。页面清单以 `web/src/app/pageRegistry.tsx` 和 `docs/modules/README.md` 为准；覆盖状态以模块 `e2e-coverage.md` 为准。

状态说明见 `spec-first-e2e-audit.md`。

## 页面模块 inventory

| Priority | Module | Route | Page key | 关键功能域 | 当前 Spec-first 状态 | 当前 Browser e2e |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `reconciliation-workbench` | `/` | `reconciliation-workbench` | 三栏候选、确认、撤回、异常处理、active generation、跨页 relation fan-out | `covered` | `web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/workbench-withdraw-flow.spec.ts`、`web/e2e/workbench-candidate-split-flow.spec.ts`、`web/e2e/workbench-stale-error-flow.spec.ts`、`web/e2e/workbench-network-recovery-flow.spec.ts`、`web/e2e/workbench-exception-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/e2e/workbench-permissions-flow.spec.ts`、`web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/batch-accounting-flow.spec.ts`、`web/e2e/turnover-ledger-flow.spec.ts` |
| 2 | `bank-details` | `/bank-details` | `bank-details` | 流水列表、标签、关系标签、导出、候选/已确认关系 | `covered` | `web/e2e/bank-details-initial-state.spec.ts`、`web/e2e/workbench-relation-fanout.spec.ts`、`web/e2e/bank-details-export-download.spec.ts`、`web/e2e/bank-details-stale-refreshing.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/bank-details-large-scroll-flow.spec.ts`、`web/e2e/bank-details-category-flow.spec.ts`、`web/e2e/bank-details-auto-tag-rules-flow.spec.ts`、`web/e2e/workbench-relations-candidate-semantics.spec.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |
| 3 | `imports-bank-transactions` | `/imports/bank-transactions` | `imports.bank-transactions` | 银行流水上传、预览、账户冲突、确认、下游刷新 | `partial` | `web/e2e/imports-bank-transactions-flow.spec.ts` |
| 4 | `imports-invoices` | `/imports/invoices` | `imports.invoices` | 进/销项发票上传、预览、确认、关联台刷新 | `partial` | `web/e2e/imports-invoices-flow.spec.ts` |
| 5 | `imports-etc-invoices` | `/imports/etc-invoices` | `imports.etc-invoices` | ETC zip 预览、任务确认、后台 job | `partial` | `web/e2e/imports-etc-invoices-flow.spec.ts` |
| 6 | `pending-invoices` | `/pending-invoices` | `pending-invoices` | 待找发票列表、候选/已开票状态、人工补票/选择已有发票、导出 | `partial` | `web/e2e/pending-invoices-fanout.spec.ts`、`web/e2e/workbench-relations-candidate-semantics.spec.ts`、`web/e2e/workbench-relations-nonfresh-diagnostics.spec.ts` |
| 7 | `tax-offset` | `/tax-offset` | `tax-offset` | 税金试算、保存、已认证导入、发票使用状态 | `partial` | `web/e2e/tax-offset-flow.spec.ts` |
| 8 | `no-oa-bank-batches` | `/no-oa-bank-batches` | `no-oa-bank-batches` | 免 OA 提交、撤回、历史、标签选择、权限 | `partial` | `web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` |
| 9 | `batch-accounting` | `/batch-accounting` | `batch-accounting` | 批量账务选择、提交、撤回、relation barrier、窄屏可读性 | `partial` | `web/e2e/batch-accounting-flow.spec.ts` |
| 10 | `turnover-ledger` | `/turnover-ledger` | `turnover-ledger` | 外部往来闭环、撤回、分组、成本/搜索 fan-out | `partial` | `web/e2e/turnover-ledger-flow.spec.ts` |
| 11 | `input-invoice-usage` | `/input-invoice-usage` | `input-invoice-usage` | 进项使用、relation candidate/linked 证据、OA reverse、草稿、提交历史 | `partial` | `web/e2e/input-invoice-relation-fanout.spec.ts`、`web/e2e/input-invoice-usage-flow.spec.ts` |
| 12 | `output-invoice-collections` | `/output-invoice-collections` | `output-invoice-collections` | 销项收款状态、提醒、红蓝票关系、正式收据、历史 | `partial` | `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` |
| 13 | `oa-pending-payments` | `/oa-pending-payments` | `oa-pending-payments` | OA 待付款、筛选排序、OA/银行/发票/规则抽屉 | `partial` | `web/e2e/oa-pending-payments-flow.spec.ts`、`web/e2e/workbench-relations-candidate-semantics.spec.ts` |
| 14 | `cost-statistics` | `/cost-statistics` | `cost-statistics` | 项目/费用下钻、流水详情、导出 row-limit、Workbench 成本关系 fan-out | `partial` | `web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/cost-statistics-relation-fanout.spec.ts` |
| 15 | `etc-tickets` | `/etc-tickets` | `etc-tickets` | ETC 业务批次、发票明细、OA 草稿、提交 bucket | `partial` | `web/e2e/etc-tickets-flow.spec.ts` |
| 16 | `settings` | `/settings` | `settings` | 数据重置、OA 密码复核、规则配置、权限 | `partial` | `web/e2e/settings-data-reset-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` |
| 17 | `app-health-operations` | `/operations/app-health` | `app-health-operations` | 系统状态、worker/read model/queue、admin gate | `partial` | `web/e2e/app-shell.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` |

## 资源/共享模块 inventory

| Priority | Module | 范围 | 当前 Spec-first 状态 | 当前 Browser e2e |
| --- | --- | --- | --- | --- |
| 1 | `workbench-relations` | canonical relation write model、distribution read model、跨页面 relation fan-out | `partial` | `workbench-relation-fanout`、`bank-details-export-download`、`workbench-relations-candidate-semantics`、`workbench-relations-nonfresh-diagnostics`、`output-invoice-red-relation-fanout`、`input-invoice-relation-fanout`、`cost-statistics-relation-fanout`、`workbench-withdraw-flow`、`workbench-candidate-split-flow`、`pending-invoices-fanout`、`batch-accounting-flow`、`turnover-ledger-flow` |
| 2 | `permissions-and-audit` | session、role matrix、高风险写入口、审计 | `partial` | `web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/workbench-permissions-flow.spec.ts`、`web/e2e/bank-details-filtered-export-permissions.spec.ts`、`web/e2e/app-shell.spec.ts` |
| 3 | `app-shell-navigation` | shell、route、sidebar、mobile drawer、embedded OA shell | `partial` | `web/e2e/app-shell.spec.ts`、`web/e2e/app-shell-responsive.spec.ts` |
| 4 | `finance-table-system` | 表格排序、分页、筛选、列宽、滚动、下载 | `missing` | 页面级 smoke 间接覆盖，缺共享大数据/滚动/下载 Spec-first e2e |
| 5 | `read-models` | freshness/status/enqueue/read boundary | `partial` | 页面 smoke 间接覆盖，真实 worker drain 为 `external-risk` |
| 6 | `runtime-workers` | durable queue、worker registry、runtime health | `external-risk` | 本地 e2e 只 mock 状态，真实 systemd/RabbitMQ/Redis 需 staging |
| 7 | `domain-events-lifecycle` | 前端刷新提示、后端 derived lifecycle | `partial` | 页面 smoke 间接覆盖，事件本身不是事实源 |
| 8 | `oa-integration` | OA Mongo、OA 登录、iframe/cookie、OA 草稿 | `external-risk` | 本地 mock 覆盖页面流程，真实 OA 需 staging/manual |
| 9 | `data-safety-reset` | 数据重置、备份、worker drain、恢复 | `partial` | `settings-data-reset-flow` 覆盖 UI/job polling，真实恢复为 `external-risk` |
| 10 | `deploy` | release、Nginx、systemd、runtime env | `external-risk` | `app-shell` 间接覆盖 shell，发布流程需 staging |

## 跨页面高风险链路

| Spec group | 链路 | 当前状态 | 当前覆盖 |
| --- | --- | --- | --- |
| `REL-FANOUT` | 关联台 confirm/withdraw/split_candidate/exception apply/cancel/ignore、候选关系不驱动 linked-only 状态、relation-backed non-fresh 诊断、销项红蓝票 relation overlay、进项发票使用 candidate/linked relation fan-out、成本统计 candidate/confirmed relation fan-out、网络恢复/409/重复提交、大数据分页/搜索/详情/滚动、read-export 权限、App Health write-safety blocker -> `workbench_relation` fresh、页面长列表 contract 或零 mutation 权限 contract -> 银行明细/待找发票/批量账务/往来款/关联台自身最终一致 | `partial` | Workbench Playwright smoke + 后端 integration；关联台本页 Spec-first ID 已覆盖，candidate/linked 负面语义、non-fresh 诊断、销项红蓝票 relation overlay、进项发票使用 fan-out 和成本统计 fan-out 已覆盖，跨下游下载和税金/search 等更多页面 fan-out 继续按 `workbench-relations` 推进 |
| `IMPORT-FANOUT` | 导入 preview/confirm -> import job/read model -> 关联台/银行明细/税金/发票页面刷新 | `partial` | 银行/发票/ETC 导入 smoke |
| `PERMISSION-MATRIX` | read_export_only/full_access/admin/forbidden/expired 在所有页面的读写 gate | `partial` | role matrix smoke 覆盖全页面读取和高风险入口；关联台已补逐入口 read-export 零 mutation 和 App Health write-safety blocked 三角色组合；银行明细已补 `read_export_only` 可导出、分类/自动标签写入口禁用和零 mutation、`admin` 分类写入、forbidden/expired session gate 零 protected API；其他页面仍未到每按钮全矩阵 |
| `DOWNLOAD-EXPORT` | 各页面导出下载、row-limit、失败反馈 | `partial` | 成本 row-limit 反馈已覆盖；银行明细 relation 字段真实 download event、账户/自定义日期/关键字/分类筛选导出、分页状态不限制导出和 `read_export_only` 下载已覆盖；其他页面和真实 XLSX 完整解析仍缺系统覆盖 |
| `STALE-REFRESHING` | read model stale/refreshing/error/fresh 页面状态 | `partial` | 关联台已有 `web/e2e/workbench-stale-error-flow.spec.ts` 覆盖 stale/refreshing/false-empty、OA dirty/refreshing、refresh failed/write failure、barrier timeout 和 fresh refetch failure；银行明细已有 `web/e2e/bank-details-stale-refreshing.spec.ts` 覆盖 transaction refreshing/stale/missing false-empty、account schema_mismatch retry、network recovery 和导出业务错误，`web/e2e/bank-details-auto-tag-rules-flow.spec.ts` 覆盖自动标签规则保存/reapply 等待 `bank_detail` freshness 与 blocked warning；其他页面仍缺 Browser 负面场景 |
| `MOBILE-EMBEDDED` | mobile drawer、窄屏表格、OA iframe embedded shell | `partial` | app-shell responsive、batch accounting narrow desktop、bank details narrow table/export/filter overlays |
| `NETWORK-RECOVERY` | API 失败、网络恢复、重复提交防护 | `partial` | 关联台已覆盖 confirm transient failure retry、409 stale preview 和 confirm/split/withdraw duplicate-submit；其他页面仍缺系统化 Browser 负面链路 |

## 下一轮队列

1. `workbench-relations`：继续补更多下游页面 fan-out（税金、搜索等）和导出权限/筛选组合。
2. `imports-bank-transactions`：账户冲突、重复行、任务失败、下游多页面刷新。
3. `pending-invoices`：人工补票/选择已有发票、候选不参与 linked-only 计算。
4. `finance-table-system`：共享表格大数据、水平滚动、列宽、下载。
5. `input-invoice-usage` / `output-invoice-collections`：继续补 stale/refreshing、下载和权限组合。

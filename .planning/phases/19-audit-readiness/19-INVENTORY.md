# Phase 19 当前事实与证明缺口盘点

**基线 commit:** `2a9c5a6aa`
**盘点日期:** 2026-07-11
**性质:** 只读代码/文档盘点；不是生产数据结论

## 1. 页面覆盖矩阵

当前 `web/src/app/pageRegistry.tsx` 登记 17 页。

| # | Page key | Route | 当前 Audit | Runtime 链路 | 结论 |
|---|---|---|---|---|---|
| 1 | `reconciliation-workbench` | `/` | 无页面统一 Audit | 独立 `audit_workbench_relation_display.py` | 未纳入统一 snapshot/freshness/queue/version |
| 2 | `cost-statistics` | `/cost-statistics` | 有 | generic page audit | 已登记，但 expected set 依赖 Workbench/bank-detail projection |
| 3 | `bank-details` | `/bank-details` | 有 | generic page audit | 已登记 |
| 4 | `oa-pending-payments` | `/oa-pending-payments` | 有 | generic page audit | 已登记；readiness 历史 parent failure 语义有缺口 |
| 5 | `bank-flow-rule-batches` | `/bank-flow-rule-batches` | 有 | generic page audit | 已登记 |
| 6 | `batch-accounting` | `/batch-accounting` | 有 | generic page audit | 已登记 |
| 7 | `turnover-ledger` | `/turnover-ledger` | 有 | generic page audit | 已登记，但 canonical 计算读取 bank-detail projection |
| 8 | `etc-tickets` | `/etc-tickets` | 无 | 无等价页面 Audit | 未登记 |
| 9 | `tax-offset` | `/tax-offset` | 无 | 无等价页面 Audit | 未登记 |
| 10 | `pending-invoices` | `/pending-invoices` | 有 | generic page audit | 已登记 |
| 11 | `input-invoice-usage` | `/input-invoice-usage` | 有 | specialized invoice audit | 并行旧链路；无 outbox check |
| 12 | `output-invoice-collections` | `/output-invoice-collections` | 有 | specialized invoice audit | 并行旧链路；无 outbox check |
| 13 | `settings` | `/settings` | 无 | 无等价页面 Audit | 未登记 |
| 14 | `app-health-operations` | `/operations/app-health` | 无系统级证明 Audit | 页面内另有进项 specialized audit | 未登记且职责混杂 |
| 15 | `imports.bank-transactions` | `/imports/bank-transactions` | 无 | 无等价页面 Audit | 未登记 |
| 16 | `imports.invoices` | `/imports/invoices` | 无 | 无等价页面 Audit | 未登记 |
| 17 | `imports.etc-invoices` | `/imports/etc-invoices` | 无 | 无等价页面 Audit | 未登记 |

覆盖结论：9 页显示 Audit 控件，其中 7 页走 generic contract，2 页走 specialized contract；8 页没有等价证明合同。

## 2. 当前 Audit 实现

| 实现 | 页面 | Snapshot | Dirty | Outbox | Relation proof | Consumer projection proof | Version-bound result |
|---|---|---|---|---|---|---|---|
| `page_business_audit.py` | 7 | 单页 repeatable-read | 有 | 有 | canonical == shared groups == shared rows | 无 | 无 |
| `invoice_read_model_audit.py` | 进项、销项 | 单页 repeatable-read | 有 | **无** | canonical == shared groups == shared rows | 仅检查 invoice members 同行/候选污染，不证明全量 OA/bank/invoice edge equality | 无 |
| `audit_workbench_relation_display.py` | Workbench 工具 | 独立 | 独立 | 独立 | 检查部分 display invariants | 仅 Workbench 专项 | 无统一页面合同 |

### 已机械确认的错误证明

1. `audit_report.py` 只有出现 `read_model_outbox_not_drained` issue 才把 queue 标成 backlog。
2. generic audit 调用 `_outbox_backlog_issues`。
3. specialized invoice audit 的 checks 列表没有 outbox check。
4. 因此 specialized audit 的 `queue=drained` 可以仅表示“没有生成 queue issue”，不是“查询后证明 outbox drained”。

## 3. Relation 证明缺口

`workbench_relation_edge_equality_issues(...)` 当前证明：

```text
app.workbench_pair_relations canonical edges
  == read_model.workbench_relation_groups edges
  == read_model.workbench_relation_rows edges
```

它没有读取以下 consumer projection：

- Workbench active generation rows/groups。
- pending-invoice collapsed summaries。
- input-invoice-usage OA/bank/invoice summaries。
- output-invoice-collections OA/bank/invoice summaries。
- OA pending payment page relation summaries。
- bank-details relation/tag projection。
- cost/turnover/batch/tax/ETC 等页面实际展示关系。

因此“共享 relation 正确”不能推出“每个页面消费了完整 relation”。

## 4. Expected-set 和字段证明缺口

- `PAGE_AUDIT_CONTRACTS` 的 metadata 声明 key fields，但实际 SQL 覆盖范围因页面不同，metadata 本身不是证明。
- turnover expected/field proof 依赖 `read_model.bank_detail_rows`；若 bank-detail 与 turnover 同源遗漏，存在相关遗漏风险。
- cost expected proof读取 Workbench active generation和 bank-detail read model；它不是完全独立 canonical fact proof。
- pending/OA 的 collapsed member proof覆盖业务集合，但不证明页面所有 relation consumer edges。
- specialized invoice audit重算 invoice total，但没有证明页面所有 OA/bank/relation summary 字段。
- 现有结果没有 `audit_revision`、`source_version_set`、`relation_version`、`read_model_generation/version` 或结果有效期指纹。
- 前端只持有本次 payload 和独立页面 `readModelStatus`；无法判断 payload 生成后事实版本是否变化。

## 5. Readiness/current-effective 缺口

`read_model_manifest.py` 已正式区分：

- `fan_out_command`
- `queryable_parent_aggregate`
- `active_month_shard_aggregate`
- `forbidden_bare_all`

但当前：

- `ReadModelReadinessReporter.record_event_success` 遇到 `enqueued_scope_keys` 且没有显式 `readiness_status` 时直接返回。
- failure 会为 event scope（通常 `all`）写 failed readiness。
- `RuntimeMonitoringRepository._app_status_readiness_statuses` 聚合所有 readiness rows，不读取 manifest `all_scope_semantics`。
- `read_model_slo_smoke` 直接按精确 scope 读取 readiness，也没有统一 manifest current-effective policy。
- generic/specialized Audit 自行查 dirty/outbox，不复用 App Status 的 current-effective policy。

结果：`fan_out_command/all` 的历史 failure 可以长期污染 App Status，而月 shard 和页面实际读路径已经 fresh。

## 6. 旧/并行 runtime 路径 ledger

### 目标为迁移后删除

- `services/postgres_repositories/input_invoice_usage_audit.py`
- `services/postgres_repositories/output_invoice_collection_audit.py`
- `services/postgres_repositories/invoice_read_model_audit.py` 的 specialized orchestration/runtime contract
- `tools/audit_input_invoice_usage_read_model.py`
- `tools/audit_output_invoice_collection_read_model.py`
- `tools/invoice_read_model_audit_cli.py`
- `/api/operations/app-health/input-invoice-usage-audit`
- `/api/operations/app-health/output-invoice-collection-audit`
- 对应 OperationsAuditRepository/Service methods
- 对应 frontend fetch/types/mocks/e2e expectations
- `page_business_audit.py` 的 2400 行 registry + orchestration + SQL monolith
- `audit_workbench_relation_display.py` 内迁移到统一 Workbench proof 后的重复 SQL/runtime 入口

### 删除前必须先证明调用情况

- specialized HTTP routes 的生产访问日志和外部调用方。
- legacy `GET /api/workbench` full-payload compatibility route。
- `no_oa_bank_batch` legacy API/read-model 命名和实际页面归属。
- Workbench materialized-all repair-only path。

### 必须保留的正式边界

- `ReadModelRefreshGateway`
- PostgreSQL durable queue
- read model manifest/scope policy/worker registry
- canonical `app.workbench_pair_relations`
- shared `workbench_relation` read models
- Workbench active-generation atomic publish
- `audit_report.py` 中有效 snapshot/evaluation 能力
- 经调用证明仍承担正式运维职责的 readiness backfill/queue repair 工具

## 7. 目标 I/O 边界

| Owner | 输入 | 输出 | 禁止 |
|---|---|---|---|
| Audit contract registry | page key、proof owner、scope/event/version metadata | 不可变 contract | SQL、HTTP、refresh |
| Audit snapshot | DB connection | 单一 read-only repeatable-read context | 业务判断、写入 |
| Domain proof | snapshot + contract | expected/actual/field issues | refresh、HTTP response |
| Relation proof | snapshot + consumer contract | canonical/shared/consumer edge diff | 修改 relation |
| Freshness proof | snapshot + manifest policy | current-effective dirty/outbox/readiness/generation | direct mark-fresh |
| External proof | 已登记 external evidence | pass/fail/unknown | 把缺失证据当 pass |
| OperationsAuditService | 上述 proof ports | 结构化 page/system report | SQL、HTTP cookie/header |
| Route | auth + request | HTTP DTO | 业务 SQL/证明逻辑 |
| Frontend control | structured report + current version | 明确文案和失效状态 | 自行推导完整性 |

## 8. Grill Gate 结论

| 问题 | 当前答案 |
|---|---|
| 目标是否明确 | 是：证明所有注册页面内部数据、字段、关系、版本与运行收敛；外部证据单列 |
| 页面范围是否明确 | 是：当前 registry 17 页；必须由 architecture test 保持同步 |
| canonical fact owner 是否全部明确 | 部分；Phase 19 第一执行计划必须完成逐页 owner/field/consumer matrix |
| 旧链路是否明确 | runtime 主体已定位；外部调用/repair-only 使用仍需日志和调用证明 |
| I/O 是否清晰 | 目标边界已冻结；现有 monolith/specialized route 不满足 |
| 是否存在可绿色遗漏反例 | 是：shared relation 有 I-B edge，而 input page 漏 B summary |
| 是否可直接实现 | 否；先完成逐页 contract/field/consumer matrix 和测试责任冻结 |
| 是否需要用户业务决策 | 当前不需要；外部证据可用性和生产写授权到对应 gate 再单问 |

## 9. 当前阶段出口

进入 runtime 实现前必须补齐：

1. 17 页逐页 canonical owner、expected-set、关键字段、relation consumer、scope/event、external evidence 矩阵。
2. 当前 9 个 Audit 的 SQL/check-to-claim 映射。
3. 所有 fan-out manifest entry 的 parent/shard current-effective 真值表。
4. 旧 route/module/symbol 调用图和删除 gate。
5. 七类测试责任与精确回归 fixtures。

## 10. 19-02 实施后增量状态（2026-07-11）

- 新增 `PAGE_AUDIT_REGISTRY`，与 frontend 17 个 page key 机械严格相等。
- 9 个现有页面 proof 登记为 `ready`；8 个未实现 proof 页面登记为 `unavailable` 并在 service/HTTP fail closed，登记不再等于可通过。
- 9 个页面 Audit 控件统一调用 `page-audit?page=<page_key>`；进项、销项页面不再调用 specialized HTTP route。
- 进项/销项 invoice core 已在同一 audit snapshot 内查询 `job.outbox_events`，`queue=drained` 不再由“没有生成 queue issue”伪推导。
- 页面 success gate 新增 `proof_availability=ready` 和非空 `contract_revision`；在 consumer relation proof 完成前，文案只声明“已登记证明一致”。
- specialized routes/service/repository/tools 尚未删除：App Health 运维面板仍调用进项 specialized route，且外部 caller 证据尚未完成；它们继续列在 legacy removal ledger。
- 仍未完成：8 页业务 proof、所有 consumer relation edge equality、evidence/source/generation version binding、system snapshot、external evidence、正式旧链路删除和生产闭环。

## 11. 19-03 实施后增量状态（2026-07-11）

- 进项/销项 invoice proof 新增 shared linked relation → page consumer summaries 的 typed edge 双向 equality；identity 为 `relationCaseId + row_id + row_type`，缺失和多余 edge 都阻断 integrity。
- 该 proof 与现有 canonical → shared groups/rows equality 在同一 repeatable-read snapshot 组合，直接覆盖“共享关系存在、invoice 页面漏关系”的反例。
- proof revision 升级为 `page-audit-contract.v2`。
- App Health 面板已迁移到统一 `page-audit?page=input-invoice-usage`；两个 specialized HTTP route、handler、frontend client 和 service/repository public method 已删除。
- invoice core 与两个 CLI thin adapters 保留：统一 repository executor 和正式只读 CLI 仍实际调用它们，因此不是 dead runtime fallback。
- 仍未完成：其余 7 个 ready 页 consumer equality、8 个 unavailable 页业务 proof、version/system snapshot/external evidence，以及其它 legacy paths。

## 12. 19-04 实施后增量状态（2026-07-11）

- `oa-pending-payments` 登记 completed/admitted OA anchor 的 consumer contract；shared linked relation 中的 OA、bank、input-invoice edge 与页面持久化 summaries 双向比较。
- `pending-invoices` 登记 active bank anchor 的 consumer contract；shared linked relation 中的 OA、bank、input/output-invoice edge 与页面持久化 summaries 双向比较，invoice 类型由 expense/income 页面方向确定。
- 两页 proof 使用 `(case_id, row_id, row_type)` 跨 scope 逻辑 union；任一 shared→consumer 缺失或 consumer→shared 多余都阻断 integrity。
- consumer SQL 已移入单独的只读 repository proof module；registry/route/service/worker/read model 写路径未增加新职责。
- proof revision 升级为 `page-audit-contract.v3`。
- 仍未完成：bank-details 标签 consumer、cost/turnover/bank-flow/batch-accounting 各自语义 proof、8 个 unavailable 页、version/system snapshot/external evidence、剩余 legacy 删除和生产闭环。

## 13. 19-05 实施后增量状态（2026-07-11）

- `bank-details` consumer contract 已按页面真实表达能力登记：linked OA/发票存在性标签、linked case id、linked status，而不是虚构页面未持久化的完整成员 DTO。
- expected tag/case/status 从 active bank facts 与 linked shared relation groups 重算；页面 consumer 从 `bank_detail_rows` structured columns 与 payload 读取。
- shared bank member 同时属于多个 linked cases、漏 linked 标签/case/status、case 不一致或页面伪造 linked 标签都会阻断 integrity；candidate 不作为正式已配对 edge。
- proof revision 升级为 `page-audit-contract.v4`。
- 仍未完成：cost/turnover/bank-flow/batch-accounting 各自 projection proof、8 个 unavailable 页、version/system snapshot/external evidence、剩余 legacy 删除和生产闭环。

## 14. 19-06 实施后增量状态（2026-07-11）

- `bank-flow-rule-batches` 新增 canonical batch → page payload → active batch relation 三方 member-set equality。
- submitted 批次缺 active relation、非 submitted 批次残留 relation、active relation 无 canonical batch，以及任一 bank member 缺失/多余均阻断 integrity。
- page payload 的 `bank_transaction_ids` / `row_ids` 被解析为排序去重集合；`row_count` 相同不再足以通过。
- proof revision 升级为 `page-audit-contract.v5`。
- 仍未完成：batch-accounting direct shared consumer、turnover/cost projection proof、8 个 unavailable 页、version/system snapshot/external evidence、剩余 legacy 删除和生产闭环。

## 15. 19-07 实施后增量状态（2026-07-11）

- `batch-accounting` 明确登记为 direct shared-relation consumer，没有新增第二 read model。
- active canonical batch-accounting case set 与 linked shared group logical case set 双向比较；canonical relation mode、payload mode/source/special metadata 必须一致。
- canonical wrong mode、missing group、group orphan 或 metadata drift 均阻断 integrity；完整 member edges 复用全局 canonical/shared equality。
- proof revision 升级为 `page-audit-contract.v6`。
- 仍未完成：turnover/cost projection proof、8 个 unavailable 页、version/system snapshot/external evidence、剩余 legacy 删除和生产闭环。

## 16. 19-08 实施后增量状态（2026-07-11）

- turnover ledger/flow payload 新增 `workbench_relations` 结构化 summaries，保留 case↔typed-member 映射；未增加表或事实源。
- Audit 对 ledger aggregate row 与每条 flow row 分别形成 anchor，比较 relevant linked shared relation edges 双向相等。
- `TURNOVER_LEDGER_SCHEMA_VERSION` 升至 `2026-07-turnover-ledger-v5`；旧 payload 必须由 gateway 重建后才可通过新 proof。
- proof revision 升级为 `page-audit-contract.v7`。
- 仍未完成：cost lineage/active-generation proof、8 个 unavailable 页、version/system snapshot/external evidence、剩余 legacy 删除和生产闭环。

## 17. 19-09 实施后增量状态（2026-07-11）

- `reconciliation-workbench` 已从 unavailable 变为 ready，管理员页面 Audit 控件、统一 page API 与正式运维 CLI 均调用唯一的 `workbench_page_audit` repository proof owner。
- 同一只读 repeatable-read snapshot 组合 canonical/shared typed-edge equality、active generation relation display、同组/唯一 owner、case/mode/alignment、visible automatic-decision 排除、all/member generation 时序，以及 `workbench`/`workbench_relation` dirty scope 与 outbox。
- 原 `audit_workbench_relation_display` tool 已降为 parser/connection/JSON/exit-code 薄适配器；SQL、归一化、issue/evaluation 只保留在 repository owner，并由 source guard 防止旧逻辑回流。
- proof revision 升级为 `page-audit-contract.v8`；ready/unavailable 页面变为 10/7。
- 仍未完成：cost lineage/active-generation 输入版本绑定、7 个 unavailable 页、system snapshot/external evidence、其余 legacy 删除和生产闭环。

## 18. 19-10 实施后增量状态（2026-07-11）

- Workbench Audit expected-set 已从“active relation members”扩展为 eligible canonical OA、银行、普通/附件发票和 ETC summary/detail；普通 relation-free row 遗漏不再可能因 relation equality 正常而通过。
- 每个 active month generation 与 canonical inventory 双向比较；`all` generation 必须等于 active month rows 的逻辑 union。OA pending claim 排除、active relation supplement、ETC hidden/folded summary 均纳入正式 SQL contract。
- 关键 OA/银行/发票字段、ETC detail/count/amount、generation row/group/summary counts、页面 summary counts和 builder/parser/rules/dependency versions独立重算；任一 mismatch blocking。
- proof revision 升级为 `page-audit-contract.v9`。
- 本地 disposable PostgreSQL 应用 0001..0096 全量 migrations 后真实执行全部新 proof SQL 成功，并以 canonical bank 缺失 fixture 证明返回 `workbench_canonical_object_set_mismatch`；临时数据库已删除。
- 仍未完成：成本统计 lineage/version proof、7 个 unavailable 页面、system snapshot/external evidence、其余 legacy、完整 backend baseline 与授权生产闭环。

## 19. 19-11 实施后增量状态（2026-07-11）

- 成本统计在同一个 repeatable-read read-only snapshot 内复用完整 Workbench integrity collector 与 bank-detail canonical/field/version proof；没有嵌套 Audit transaction 或第二运行时。
- full bank-flow identity/month/amount expected-set 直接来自 active canonical `app.bank_transactions` outflow facts；WorkBench 与 cost、bank-detail 与 cost 同时漏同一银行对象时不再可能一起通过。
- OA-bank cost rows 的 group/context/time/counterparty/amount/tag fields、全银行支出 fields、project/expense/bank-flow summaries、settings bank accounts 均双向重算。
- month model 精确绑定当前 Workbench/bank-detail source_versions；parent source_shards 精确绑定当前 materialized month models。
- proof revision 升级为 `page-audit-contract.v10`。
- disposable PostgreSQL 全迁移 clean fixture 可 pass；canonical outflow omission fixture 被多层独立 proof 阻断；临时库已删除。
- 完整 backend baseline 仍有 14 个本计划外失败；完整 frontend 71/828 与 build 通过。
- 仍未完成：7 个 unavailable 页面、system snapshot/version set/external evidence、剩余 legacy、14 个 baseline failures 与授权生产闭环。

## 20. 19-12 实施后增量状态（2026-07-11）

- `tax-offset` 已从 unavailable 变为 ready；同一只读一致性快照独立证明 canonical invoices/certified records 到五类 tax item、匹配、字段、控制、summary、version 和 queue。
- `relation_proof_required=false` 是精确非消费者合同：成功文案显示“本页面不消费配对关系”，不再虚构 relation proof。
- 修复 certified source version `created_at`、parent entry_count、空 seller identity 误配，并增加 canonical total/ambiguous match 反证。
- tax schema 升至 `2026-07-tax-offset-audit-proof-v2`；proof revision 升至 `page-audit-contract.v11`。
- Workbench/红蓝票 relation → tax dirty/outbox、SLO、动态造数 mock 和旧 Browser spec 已删除；canonical invoice/ETC/certified 合法刷新保留。
- disposable PostgreSQL 0001..0096 clean pass，wrong match/stale version/bad total 全部 fail closed；临时库已删除。
- 完整 backend baseline 为 4300 tests / 13 failures / 25 skipped；完整 frontend 71/830 与 build 通过。
- 仍未完成：6 个 unavailable 页面、system snapshot/version set/external evidence、剩余 legacy、13 个 baseline failures 与授权生产闭环。

## 21. 19-13 实施后增量状态（2026-07-11）

- `etc-tickets` 已从 unavailable 变为 ready，并明确登记为 `read_model_keys=()` 的 direct-canonical 页面；proof revision 升至 `page-audit-contract.v12`，ready/unavailable 为 12/5。
- 同一只读 repeatable-read snapshot 证明 business batch/task/file/ETC invoice/import/submission/canonical invoice bridge 的完整集合、关键字段、重复表示 equality 与单一正式边的引用/owner 闭包。
- ETC import durable job backlog/terminal failure 分别进入 freshness+queue/integrity gate；UI 不再要求不存在的 page read model，也不会为有 read model 的页面放宽 fresh gate。
- Workbench/tax/cost/invoice-lifecycle 只作为写后 downstream targets；page matrix 和 write impact matrix 不再把它们冒充 ETC page consumers。
- runtime whole-repo scan 未发现仍存活的 legacy ETC route/detector/revoke/snapshot fallback；历史 repair/migration/backfill 工具按正式运维 owner 与删除条件保留。
- disposable PostgreSQL 0001..0096 clean pass；task/batch omission、wrong total、orphan card edge 和 active import queue 均 fail closed；临时库已删除。
- 完整 frontend 148/831 与 build 通过；完整 backend baseline 为 4307 tests / 13 failures / 25 skipped，无 ETC 新增失败。
- 仍未完成：5 个 unavailable 页面、system snapshot/version set/external evidence、13 个 baseline failures 与授权生产闭环。

## 22. 19-14 实施后增量状态（2026-07-11）

- `settings` 已从 unavailable 变为 ready，并明确登记为 `read_model_keys=()`、`relation_proof_required=false` 的 direct-canonical control-plane 页面；proof revision 升至 `page-audit-contract.v13`，ready/unavailable 为 13/4。
- 同一只读 repeatable-read snapshot 证明唯一 app settings singleton、formal/raw/fixed-point normalization、全部注册配置 families、非敏感 credential summaries 与 settings reset durable job 状态。
- credential SQL 只读取 identity/status/version/time 和 `has_credential` 布尔值；不选择/解密/返回 secret、ciphertext、token 或可逆 fingerprint。
- active reset job 阻断 freshness/queue，未确认 terminal failure 阻断 integrity；Audit 不执行 provider/OA/reset I/O。
- whole-repo runtime scan 发现并移除了 Turnover local tag-selection 对 `AppSettingsService._snapshot` 和 settings store 的跨模块 save/refresh bypass；本地 UoW 改走领域化 state/commit/restore 端口，回滚只恢复该 setting family，server helper 删除并由 guard 防回流。
- disposable PostgreSQL 0001..0096 clean pass；non-normalized payload、secret leakage guard 和 active reset queue 均 fail closed；临时库已删除。
- 完整 frontend 71/831 与 build 通过；完整 backend baseline为 4355 passed / 13 failed / 37 skipped，失败类别未扩大。
- 仍未完成：4 个 unavailable 页面、system snapshot/version set/external evidence、13 个 baseline failures 与授权生产闭环。

## 23. 19-15 实施后增量状态（2026-07-11）

- `imports.bank-transactions` 已从 unavailable 变为 ready，并明确登记为 `read_model_keys=()`、`relation_proof_required=false` 的 direct-canonical workflow；proof revision 升至 `page-audit-contract.v14`，ready/unavailable 为 14/3。
- 同一只读 repeatable-read snapshot 证明 file object hash registration、session/file、batch/row、preview/session audit counts、confirm 后 canonical bank transaction ownership/identity/critical fields，以及当前 `file_import.confirm` job/outbox gate。
- bank detail/account balance/Workbench/relation/pending/OA pending/cost/search 只作为写后 impact targets；不冒充银行导入页面 consumer 或配对关系 proof。App 文件 hash/size 不替代银行外部 statement control evidence。
- whole-repo scan 后删除无正式 caller 的 `/imports/preview`、`/imports/confirm` JSON route/handler/entrypoint、`general_import.confirm` producer/processor/check registry 和 preview-only orchestration dependencies；保留仍有正式 owner 的 normalization service ports 与 file/session worker restore。
- disposable PostgreSQL 0001..0096 clean pass；amount drift、hash missing、canonical transaction omission、active/terminal job/outbox 均 fail closed；时区 instant 和 decimal 表示按 canonical 语义归一；临时数据库已删除。
- 完整 frontend 71/831 与 build 通过；完整 backend baseline 为 4353 passed / 13 failed / 38 skipped，失败类别未扩大。
- 仍未完成：3 个 unavailable 页面、system snapshot/version set/external evidence、13 个 baseline failures 与授权生产闭环。

## 24. 19-16 实施后增量状态（2026-07-11）

- `imports.invoices` 已从 unavailable 变为 ready，并明确登记为 `read_model_keys=()`、`relation_proof_required=false` 的 direct-canonical workflow；proof revision 升至 `page-audit-contract.v15`，ready/unavailable 为 15/2。
- 同一只读 repeatable-read snapshot 证明 input/output file/session/batch/row、preview/session counts、canonical invoice 关键字段、manual source-link 双向 edge equality，以及精确归属的 `file_import.confirm` job/outbox。
- Workbench/relation/lifecycle/pending/input/output/OA pending/tax/cost/search 仅为写后 impacts；不冒充本页 consumer。App file hash/size 不替代税务平台导出完整性和 control total 对账。
- file confirm 生产写链收口到 PostgreSQL durable job/outbox，RabbitMQ 仅 wakeup；queue 缺失 fail closed，pending job retry 更新 background reference。删除 incomplete batch revert 和 `app.import_files.import_batch_id` runtime/schema fallback。
- disposable PostgreSQL 0001–0097 clean pass；amount/source-link/hash/job/outbox 破坏性反证 fail closed；临时数据库已删除。
- 完整 frontend 71/832 与 build 通过；完整 backend 修正 migration pin 后仅剩进入计划前同样的 13 个 baseline failures，无本计划新增失败。
- 仍未完成：2 个 unavailable 页面、system snapshot/version set/external evidence、13 个 baseline failures 与授权生产闭环。

## 25. 19-17 实施后增量状态（2026-07-11）

- `imports.etc-invoices` 已从 unavailable 变为 ready，并登记为 `read_model_keys=()` 的 direct-canonical workflow；proof revision 升至 `page-audit-contract.v16`，ready/unavailable 为 16/1。
- ETC preview/confirm 不再依赖 Web 进程内 dict：task id/version、confirmed item-set hash、ZIP preview generation、原始 ZIP file-object identity/hash/size、preview requirement/match edges、counts 与 fingerprint 均持久化为 durable session/file metadata；独立 PostgreSQL worker 从 session id 重载并复验。
- confirm 只有 durable job/outbox 单链；task `begin_import` 在 worker 内对同 session 幂等执行，enqueue 失败不提前污染 task，failed job 可安全重试同一 session。旧 `POST /api/etc/import`、inline callback/server executor、`_etc_reconciliation_import_previews` 和 `EtcService._import_sessions` 生产 ownership 已删除，source guard 防止回流。
- 同一只读 repeatable-read snapshot 复用 ETC tickets canonical collector，并追加 session/file/file-object、task/requirement/match、business/import batch、ETC invoice/canonical bridge、job/outbox 的双向集合与关键字段证明；下游 Workbench/tax/cost/invoice 页面仍由各自 Audit 负责。
- disposable PostgreSQL 应用 0001–0098 后 clean pass，archive hash 与 preview edge 破坏性反证 fail closed；测试库已删除。阶段目标回归为 480 passed / 6 skipped / 26 subtests，唯一失败是进入计划前已存在的 OA 浏览器证据 marker；矩阵其余测试、lint、docs 与 diff check 通过。
- 完整 frontend 71/833 与 production build 通过；完整 backend failure set 仍为同样 13 项，无 ETC 新增失败。
- 仍未完成：唯一 unavailable 的 `app-health-operations`、跨全部页面的同一 system snapshot/version set、外部银行/OA/发票/ETC control evidence、13 个 baseline failures 与授权生产只读闭环。

## 26. 19-18 实施后增量状态（2026-07-11）

- `app-health-operations` 已成为 system Audit owner；registry 升级为 `page-audit-contract.v17`，17/17 页面全部 `ready`。App Health 无 own read model、无业务 relation consumer，不再用虚构 projection 表达系统证明。
- 一次 System Audit 只打开一个 outer `REPEATABLE READ READ ONLY` transaction，并把同一 caller-owned `AuditSnapshot`、PostgreSQL snapshot identity 和 contract/version set 传给其余 16 个正式 proof owner。缺页、重复/乱序、revision/snapshot mismatch 或任一子页 integrity/freshness/queue failure 都 fail closed。
- App Health inventory 在同一 snapshot 生成页面 actual projection，并由独立 SQL 重算 bank/invoice/OA/import expected-set；read model manifest/status registry、required worker/current-effective heartbeat 和 durable outbox 进入系统 gate。outbox metrics `unknown/null` 不再被错误解释为 0/drained。
- 报告明确分成 `database_system_snapshot`、`runtime_observation` 和 `external_evidence`。HTTP/RabbitMQ 等观测不冒充数据库事实；外部银行/OA/发票/ETC control evidence 未登记时保持 `external=unknown`、`end_to_end_source_truth=unproven`，即使内部 snapshot pass 也不宣称端到端来源完整。
- App Health 旧 `InputInvoiceUsageAuditPanel`、专项 state/callback/client/mock URL 已删除；页面只调用统一 `page-audit?page=app-health-operations`。普通 dashboard refresh 会清除历史 Audit 绿色，防止旧 snapshot 被继续解释为当前状态；guard 禁止旧符号与 specialized Audit URL 回流。
- disposable PostgreSQL 应用 0001–0098 后，17 页 clean system snapshot pass；dashboard inventory drift、canonical bank omission、active queue/required worker failure和 unavailable outbox metrics 均阻断。真实 PostgreSQL 同时暴露并修复 turnover consumer Audit 的 duplicate `scope_key` 和 jsonb ordinality cast 两个 SQL 缺陷；临时数据库已删除。
- 目标后端为 366 passed / 4 skipped / 14 subtests；完整 frontend 为 71 files / 833 tests，production build 和 Chromium AppHealth smoke 通过；lint/docs/diff check 通过。完整 backend `--lf` 保持进入计划前同样的 13 failures，无 19-18 新增失败。
- 仍未完成：13 个 backend baseline failures；外部 control evidence 的版本化登记与授权生产只读执行；在这些 gate 完成前不得把 Phase 19 或 `/goal` 标记 complete。

## 27. 19-19 实施后增量状态（2026-07-11）

- 完整 backend baseline 已从 13 failures 收敛为 **0 failures**：最终 **4389 passed / 42 skipped / 589 subtests passed**。没有新增 skip/xfail、删除测试、放宽 assertion 或扩大 architecture allowlist。
- Workbench `month=all` 测试改为正式 composed active shards version；input-invoice direct-fresh owner 精确迁移到 `InputInvoiceUsageReadModelFreshGateService.filter_options/rows_by_invoice_ids`；OA 页面证据与 Browser fixture 删除旧 `支付少了` 状态，只保留 `未支付/已支付`。
- 成本统计 API fixture 通过正式 confirm-link 建立 active relation，candidate-only 继续排除；`bank_flow_time_rows` 从 canonical bank outflow 独立 projection，未配对 OA 流水保持 `未配对OA/未分类`，没有恢复 candidate/live fallback。
- 成本统计 tag-rules PUT、`保存并同步` 控件和 dynamic Browser opener 已进入 permissions inventory；read-export Chromium 证明查看可用、保存 disabled、mutation 零调用。
- OA reset 回归证明 OA attachment cache 重建与普通 canonical output invoice 共同保留；按稳定 id 断言且不重跑 OCR。
- legacy bank exception 相同 identity/row-set/month/code 复用既有 scenario 并走统一 idempotency owner；异码/异行/月份/非 legacy case 继续 active-case conflict，未新增第二 case owner或 fallback。
- 全量顺序测试额外发现并修复真实 background-job owner 竞态：OA reset runtime reload 不再替换当前进程的 `BackgroundJobService`，避免旧/新实例双写 job store、查询瞬时 404 和把运行中任务误判为进程重启中断；首次启动/真正重启恢复语义不变。
- 完整 frontend **71 files / 833 tests**、production build、权限 Chromium **7/7**、candidate semantics Chromium **2/2**、lint/docs/diff check 全部通过。build 仅保留既有 HeroUI CSS/chunk warning。
- 仍未完成：版本化 external bank/OA/invoice/ETC control evidence 的登记/采集/验证，以及明确授权后的生产只读 System Audit。外部 evidence unknown 时，端到端来源完整性继续为 unproven；未触碰生产。

## 28. 19-20 实施后增量状态（2026-07-11）

- 新增 `external-control-evidence.v1` 唯一合同：四域只接受 `complete_snapshot/all`，manifest 必须绑定可信来源系统/snapshot、observed/valid time、原始 artifact sha256/size、collector version、exact items 和 controls；App 当前 canonical rows 不得反向生成 manifest 后自证。
- `audit.external_control_evidence` / `audit.external_control_evidence_items` 采用 immutable append；重复 fingerprint 幂等，latest revoked 不回退旧版本。register/revoke 只有 service/repository/CLI owner，要求 actor/reason、原子写 `audit.events`，无 HTTP/UI 写入口。API/worker/readonly DB role 只有 select，apply 使用受控 migrator/operator role。
- 唯一 external comparer 在 caller-owned System Audit snapshot 内独立重算 bank transaction、OA application/item/attachment、ordinary invoice/tax-certified、ETC invoice/archive canonical items，逐项比较 identity、关键字段 fingerprint、missing/extra/duplicate 和 count/amount/tax controls。
- 缺 manifest 为 unknown；latest revoked/expired/contract/coverage/field/set/control mismatch 为 fail；四域全部精确通过才返回 `proven_as_of_external_evidence`，并绑定外部 observed/source snapshot 与当前 immutable system snapshot。
- 17 页 registry 已显式登记 external domain dependencies，合同升级为 `page-audit-contract.v18`。旧 `_external_evidence(registrations)` free-text classifier 已删除，静态 guard 防回流；System Audit 仍严格只读，不采集、不登记、不 refresh、不 repair。
- disposable PostgreSQL 应用 0001–0099 后，四域 exact pass、field drift、canonical omission、latest revoke 和 System Audit external integration 全部按预期；临时数据库已删除。
- 目标 backend **124 passed / 3 skipped / 17 subtests**；完整 backend **4407 passed / 44 skipped / 589 subtests**。完整 frontend 第二轮 **71 files / 834 tests**，Chromium AppHealth **4/4**，production build、lint/docs/diff check 通过。首次 frontend 全量有一个既有 Workbench 时序断言失败，精确重跑和第二轮全量均通过，未修改该链路。
- 本地功能已闭环但生产内部事实尚未形成：必须发布精确 release 并运行只读 System Audit。四域 manifest/artifact 只用于可选的外部来源无遗漏证明；缺失时 external 保持 unknown/unproven，但不阻塞 canonical facts/relation facts 与页面 read model/consumer 的直接内部对账。
- `19-GOAL-PROMPT.md` 固化一次一个 GSD plan、每轮 Grill、按完成/错误状态生成下一 prompt、七类测试和生产显式授权边界；当前恢复点为 gated 的 `19-21-PLAN.md`。
- 2026-07-12 生产只读 gate：`/health/ready` 显示 active release `main-2a9c5a6a-20260711144425`，与本地 HEAD 相同但不包含 233 个 dirty worktree entry；`page-audit?page=app-health-operations` 返回旧合同 `page_audit_domain_required`。因此当前生产不能运行 v18/0099，下一步必须先形成 reviewed release commit，不能直接部署 dirty tree。

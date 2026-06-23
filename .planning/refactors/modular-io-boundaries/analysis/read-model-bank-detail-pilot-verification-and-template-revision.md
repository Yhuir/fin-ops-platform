# Bank Detail Pilot Verification And Template Revision

**日期:** 2026-06-24
**Boundary:** `read-models:bank-detail-pilot-verification-and-template-revision`
**状态:** `analysis-closed`
**模块闭环:** `implementation-gap-open`
**范围:** 对 `bank_detail` read model 试点做语义验收、剩余旧链路分类和 Queue 状态纠偏；不修改业务代码、不启动 Go/Fiber/Go Worker、不声明模块全闭环。

## 结论

`bank_detail` 试点不能标记为完整模块闭环。

已完成的是几个窄实现 slice：

- `read-models:bank-detail-repository-port-extraction`
- `read-models:bank-detail-refresh-freshness-operation-barrier`
- `read-models:bank-detail-legacy-contamination-removal`

这些 slice 证明了查询 repository port、写后/强制刷新响应 contract、operation barrier target 和两个旧 SQL read helper 删除。但 `server.py` 仍保留 bank detail scope/freshness/cache/refresh/callback 类 helper，并通过 `Application._bank_details_application_service(...)` 注入到 `BankDetailsApplicationService`。因此当前应进入一个新的窄边界，先分类并隔离这些 helper，再决定哪些可迁移或删除。

本轮没有修改 `02-MODULE-IO-CONTRACT-TEMPLATE.md`、`08-AUTONOMOUS-RUNBOOK.md` 或 `10-AUTONOMOUS-STOP-GATES.md` 的模板语义。已有模板已经要求 legacy removal/quarantine、read model freshness proof、operation barrier、状态机更新闸门和 production evidence/defer status。本轮需要修正的是当前 Queue/Prompt 的下一步指向，避免把未闭环试点推进成 Go admission 或第二批推广。

## Previous State

- `autonomous/STATE.md` 指向 `read-models:bank-detail-pilot-verification-and-template-revision`。
- `autonomous/MODULE-QUEUE.md` 第 22 项为 pending。
- 主控 prompt 要求先执行 pilot verification/template revision，并且如发现 remaining legacy paths，要先 split queue。
- `00-REQUIREMENTS.md` 和 `03-REFACTOR-STATE-MACHINE.md` 明确：模块完成必须包含 IO contract、public/internal boundary、canonical facts、read model freshness、force refresh、operation barrier、legacy removal/quarantine、permissions、audit、tests、docs 和 environment evidence/defer status。

## Selected Boundary

本轮只执行验证和状态对账：

- 核对已完成 bank_detail implementation slices。
- 盘点仍在 `server.py` 中的 bank detail helper。
- 判断是否可以把 pilot 标记为 Verified/Closed。
- 更新 Queue，使下一步仍是具体 read model/bank_detail 实现边界，而不是 Go admission。

## Transition Guard

- 当前分支是 `dev`，且与 `origin/dev` 无本地 ahead/behind。
- 不存在当前 slice 的业务代码改动。
- CodeGraph 和 targeted `rg` 已用于定位 bank_detail 相关 helper、service、route、repository 和测试入口。
- 不连接真实 PostgreSQL、Redis、RabbitMQ，不执行生产写入。

## Pilot Evidence Audit

| 模块完成条件 | 当前证据 | 结论 |
| --- | --- | --- |
| 完整 IO 合同 | read model manifest、bank detail docs、analysis slices 已覆盖主要 query/refresh/operation barrier 语义 | 部分满足；仍缺剩余 helper owner/deletion condition |
| public/internal boundary | `BankDetailsApiRoutes -> BankDetailsApplicationService` 已成为 accounts/transactions 公共读入口 | 部分满足；Application 仍注入多个内部 helper/callback |
| canonical facts 单一 | category 写入仍在 category service/settings/import facts 路径 | 本轮未发现新事实源漂移 |
| read model freshness proof | scope summary、rule version mismatch、refreshing/stale/missing API 行为已有测试 | 部分满足；真实 worker/readiness 证据缺失 |
| force refresh contract | reapply 返回 `read_model_scope_keys` 和 `freshness_targets`，refresh 走 gateway | 本地 contract 满足 |
| operation barrier | exact month target 和 other-month pending isolation 已测试 | 本地 contract 满足 |
| legacy removal/quarantine | 两个 `_get_bank_detail_*_from_sql_read_model` helper 已删除 | 未满足；剩余 scope/cache/refresh/callback helper 尚未完整分类 |
| permissions | routes 层 mutation/export/read 权限已有覆盖 | 本轮未改变 |
| audit | category/export/auto-tag reapply 审计路径已有测试覆盖 | 本轮未改变 |
| 七类测试 | API/service/read model/operation barrier/regression 已有 targeted tests | 部分满足；无真实 DB/worker/e2e 本轮证据 |
| docs impact | read-models/bank-details implementation notes 已记录 prior slices | 需补本轮 verification 记录 |
| production evidence/defer | 无 local `PGSQL_URL`、无 staging DB；未执行 production DB/worker proof | 必须继续作为 deferred，不能声明生产闭环 |

## Remaining Server Helper Classification

| Path | 当前 owner/caller | 当前状态 | 风险 | 下一步 |
| --- | --- | --- | --- | --- |
| `Application._bank_detail_scope_keys_for_range(...)` | `BankDetailsApplicationService` fallback provider pattern | unclassified compat helper | scope 计算仍由 Application/repository fallback 混合，owner 不够清晰 | 分类为 compat-only 或迁移进 service/port |
| `Application._bank_detail_scope_summary(...)` | `BankDetailsApplicationService` freshness helper pattern | unclassified compat helper | freshness summary 与 auto-tag rule freshness 混在 Application | 迁移/隔离 freshness provider |
| `Application._with_bank_detail_auto_tag_rule_freshness(...)` | Application helper | unclassified compat helper | service freshness contract 仍依赖 Application 内部 source version helper | 迁移到 service 或专用 freshness collaborator |
| `Application._bank_detail_accounts_refreshing_payload(...)` | compatibility payload helper | unclassified compat helper | response fallback payload shape 仍可被 Application 私有函数影响 | 迁移到 application service 或登记 compat-only |
| `Application._bank_detail_transactions_refreshing_payload(...)` | compatibility payload helper | unclassified compat helper | 同上 | 迁移到 application service 或登记 compat-only |
| `Application._with_bank_detail_tag_dictionary(...)` | compatibility payload helper | unclassified compat helper | 仍读取 `_bank_details_service` 私有 payload 方法 | 明确是否保留只读 compat adapter |
| `Application._enqueue_bank_detail_read_model_refreshes_unless_refreshing(...)` | refresh wrapper | gateway-backed wrapper | 走 `ReadModelRefreshGateway`，但仍位于 Application | 分类 owner/deletion condition；必要时迁移至 service/collaborator |
| `Application._enqueue_bank_detail_read_model_refreshes(...)` | refresh wrapper | gateway-backed wrapper | 删除 Redis wakeup/cache 仍混在 Application | 保留前必须记录 forbidden writes 和 tests |
| `Application._bank_detail_redis_cache_key(...)` | cache helper | unclassified compat helper | Redis cache contract 位于 Application | 迁移或登记 fresh-gated cache adapter |
| `Application._get_bank_detail_cached_payload(...)` | cache helper | unclassified compat helper | cache miss/error swallow 必须继续只在 fresh gate 后使用 | 分类并加 guard |
| `Application._set_bank_detail_cached_payload(...)` | cache helper | unclassified compat helper | 同上 | 分类并加 guard |
| `Application._delete_bank_detail_redis_cache(...)` | wakeup/cache helper | gateway-adjacent wrapper | 实际只 publish wakeup，不删除 key；命名和语义不清 | 下一步必须重命名/迁移/登记 |
| `Application._latest_bank_detail_auto_category_suggestion(...)` | service callback | unclassified callback | Application 仍直接摸 import service 和 `_bank_details_service._auto_category_input_row` | 迁移到 application service collaborator 或登记短期 callback |
| `Application._after_bank_category_confirmation_mutation(...)` | service callback | unclassified callback | mutation side effects 跨 bank_detail/turnover/workbench/audit，仍在 Application | 需要边界化为 side-effect port |
| `Application._bank_details_application_service(...)` | dependency factory | allowed wiring with risks | 允许作为 wiring，但注入过多 Application-owned callbacks | 下一步收敛依赖注入清单 |
| `Application._derived_lifecycle_bank_detail_executor(...)` | derived lifecycle executor | registered producer | 走 gateway wrapper，但仍在 Application | 先保持，后续 lifecycle boundary 处理 |
| `Application._bank_detail_available_month_scope_keys(...)` | lifecycle/all fan-out helper | registered producer support | 读取 import service 推导月份，可能属于 shared scope calculator | 后续可抽出 shared scope calculator |

## Impact Analysis

| 层 | 是否影响 | 文件/符号 | 风险 | 处理 |
| --- | --- | --- | --- | --- |
| route / HTTP mapping | 否 | `routes_bank_details.py` | 本轮不改 route | 无代码改动 |
| application service | 是，分析 | `BankDetailsApplicationService` | 依赖注入仍包含多项 Application callback/helper | 新增下一边界 |
| repository / SQL | 否 | `BankDetailReadModelRepositoryPort` | port 已窄化但 accounts 仍临时读 balance port | 保持后续风险 |
| read model freshness | 是，分析 | scope summary/cache/refresh helpers | freshness/cache/gateway wrapper owner 未闭合 | 新增下一边界 |
| worker/queue | 否 | durable queue/gateway | 本轮不写 queue | 保持 PostgreSQL dual queue 事实源 |
| frontend | 否 | BankDetails page/API | 本轮无前端变化 | 不适用 |
| permission/audit | 否 | routes/service audit | 本轮无语义变化 | 不适用 |
| docs/state | 是 | planning state/docs implementation notes | 需要纠正第 22 项状态和 next prompt | 本轮更新 |

## 七类测试映射

| 类别 | 是否适用 | 本轮处理 |
| --- | --- | --- |
| 1. Business core unit tests | 不适用 | 本轮不改业务规则、金额、分类状态或权限决策。 |
| 2. Service-layer tests | 适用，回归 | 复跑 bank_detail service/API/read model targeted tests，确认状态对账未破坏现有闭环。 |
| 3. API contract tests | 适用，回归 | 复跑 accounts/transactions/auto-tag/category 相关 API tests。 |
| 4. Read model/cache/background job tests | 适用，回归 | 复跑 SQL runtime、operation barrier 和 freshness tests；真实 DB/worker 仍 deferred。 |
| 5. Frontend component and interaction tests | 不适用 | 本轮无前端/API shape 改动。 |
| 6. End-to-end business-flow integration tests | 不适用 | 无 local `PGSQL_URL`/staging；不执行生产写入。 |
| 7. Existing feature regression tests | 适用，回归 | 复跑 bank detail targeted regression set。 |

## State Machine Impact

- Global workflow definition: unchanged。
  - 已审阅 `03-REFACTOR-STATE-MACHINE.md`；本轮不新增状态、transition、guard 或 status label。
- Module state definition: unchanged。
  - 已审阅 `docs/modules/read-models/state-machine.md`、`docs/modules/bank-details/state-machine.md`、`docs/modules/runtime-workers/state-machine.md`；本轮只更新 progress/accounting，不改变业务/read model/worker 状态语义。
- Progress/accounting changed:
  - `read-models:bank-detail-pilot-verification-and-template-revision` -> `analysis-closed`
  - `bank_detail` module remains `implementation-gap-open`
  - 插入下一边界 `read-models:bank-detail-server-helper-quarantine`
- Go state:
  - unchanged，仍 `blocked-by-prerequisite`

## Template / Runbook Decision

不修改模板。原因：

- `00-REQUIREMENTS.md` 已明确模块完成定义。
- `05-IMPACT-AND-TEST-GATES.md` 已要求 legacy removal/quarantine、read model force refresh、partitioned scoped incremental projection 和 environment verification。
- `08-AUTONOMOUS-RUNBOOK.md` 已要求每个 slice 后更新 Queue/State/Journal/Next Prompt。
- `10-AUTONOMOUS-STOP-GATES.md` 已区分 hard stop 与 production-evidence-deferred。
- 当前缺口不是模板缺失，而是 Queue 下一步需要拆出更窄的 remaining helper quarantine boundary。

## Next Boundary

`read-models:bank-detail-server-helper-quarantine`

目标：

- 对剩余 `server.py` bank_detail helper/callback 做 owner、caller、allowed/forbidden writes、deletion condition 分类。
- 删除或迁移最小且有测试证明的 unsafe helper。
- 对必须短期保留的 helper 登记为 `compat-only` 或 `gateway-backed wrapper`，并补防污染测试。
- 保持 API response shape、read model freshness 语义和 operation barrier contract 不变。
- 不启动 Go/Fiber/Go Worker。

## 未测风险

- 未连接真实 PostgreSQL、Redis、RabbitMQ。
- 未执行生产 read-only SSH/HTTP SLO。
- 未证明真实 `bank_detail` worker drain 的 enqueue-to-fresh SLO。
- 仍未完成对所有 `server.py` bank_detail helper 的迁移/删除/compat-only 防污染测试。

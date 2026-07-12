# 税金抵扣状态机

> 修改 `税金抵扣` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。税金抵扣的认证状态事实源是后端 policy/read model，不是页面本地勾选状态。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 发票生命周期 | `uncertified` / `certified` / `locked_certified` | `InvoiceLifecyclePolicy`、`invoice_lifecycle` read boundary、tax certified records | 发票导入或认证导入后由 lifecycle/read model 刷新得出；页面只展示 `certified_status` / `is_locked_certified`。 |
| 销项税额 | `selected` / `unselected` | `TaxOffsetService.calculate`、页面勾选请求 | 用户在试算中选择本月销项票；保存计划时带 selected ids 和 read model versions。 |
| 进项计划 | `planned_uncertified` | `TaxOffsetService`、SQL projection、OA 附件发票 cache | 真实导入进项票或 OA 附件发票按月份进入计划，允许用户参与试算。 |
| 已认证进项 | `certified_matched` | `TaxCertifiedImportService`、`TaxOffsetService._match_certified_to_plan` | 已认证记录匹配计划进项后锁定对应 input id，不允许再次作为未认证计划行抵扣。 |
| 已认证进项 | `certified_outside_plan` | certified import records | 已认证记录未匹配计划时进入已认证结果侧栏，不反向创建计划行。 |
| 认证导入 session | `previewed` | `tax_certified_import_sessions` / application service | preview 只生成可确认 session，不写最终认证事实。 |
| 认证导入 confirm | `queued` / `running` / `completed` / `failed` | import job repository、confirm job polling API | confirm 可同步完成或排队；页面 modal 轮询 job，完成后刷新当前月份。 |
| 税金计划 | `draft` / `saved` / `conflict` | `TaxOffsetPlanService` | 保存时校验 idempotency key、read model scope key 和 source versions；旧版本返回 conflict。 |
| 税额结果 | `payable` / `carry_forward` | `TaxOffsetService.calculate` | `output_tax > input_tax` 为本月应纳税额，否则为本月留抵税额。 |

关键规则：

- 税金抵扣页面不私有定义发票认证生命周期；认证字段来自统一 lifecycle/read model。
- 没有真实导入、OA 附件或认证记录时，不允许返回硬编码计划行或硬编码已认证结果。
- 已认证进项税额始终计入 input tax；匹配到计划的已认证进项必须从可选未认证计划行中锁定。
- 计划保存必须携带并校验 `read_model_scope_key`、`source_versions` 和 `idempotency_key`。
- `tax_offset` read model scope 只允许月份 `YYYY-MM`；`all` 只用于 worker fan-out 到月份 shard。
- Redis 只能缓存 fresh gate 后的 month/summary payload，不能作为 freshness 事实源。

禁止流转：

- 禁止页面根据本地勾选把认证状态改成 certified。
- 禁止认证导入 preview 直接写最终认证记录。
- 禁止重复导入相同认证记录导致重复抵扣。
- 禁止保存基于 stale/source mismatch read model 的计划。
- 禁止 API 请求线程在生产 PostgreSQL read model miss 时同步 rebuild 并伪装 fresh。
- 禁止银行流水导入或 Workbench relation 写入直接刷新税金抵扣；税金抵扣只受发票、认证、ETC canonical promotion 和确实改变 projection source 的规则/生命周期事件影响。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面首次请求 `/api/tax-offset?month=...` | 展示加载态；请求 abort 后必须清理 loading，不保留假数据。 |
| refreshing | API 返回 `read_model_status=refreshing` 或 202 | 展示刷新/同步语义，可保留可用旧 payload，但不能把空 accepted payload 当最终空结果。 |
| stale | API 返回 stale/source/schema mismatch 或 App Status 暴露 stale scope | 显示陈旧提示或阻止保存，等待 worker 收敛。 |
| empty | fresh payload 且 output/input/certified 全为空 | 表示当前月份真实没有税金抵扣数据。 |
| error | month/calculate/save/import/job 请求失败 | 展示可理解错误；不暴露底层 SQL、worker 或文件解析 internals。 |
| import preview modal | 用户选择或拖拽 Excel 后 | 展示文件、行级识别状态、计划内/计划外统计；非 Excel 立即拒绝。 |
| import processing modal | confirm 已提交，job queued/running | modal 保持 processing 并轮询 job，不提前关闭或伪造完成。 |
| certified drawer | 用户展开已认证结果 | 展示 matched/outside-plan，点击 matched 行高亮对应计划行。 |
| save pending | 用户保存计划 | 禁用重复提交，成功 toast；version conflict 显示 stale/conflict 反馈。 |
| permission disabled/hidden | session permissions | 只读用户可查看数据，但不显示认证导入和保存类写操作。 |

前端事件：

- `invoiceFactUpdated`、`etcBusinessBatchUpdated` 等事件只能触发页面 refetch 或刷新提示。
- 前端事件不是事实源；后端 dirty scope/outbox/worker/readiness 才证明税金抵扣已收敛。
- 离开页面后 React tree 卸载，inactive 页面不 replay 事件；返回页面重新通过 API/read boundary 加载。

## Read Model / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| `fresh` | scope schema/source/readiness 与当前事实一致，且没有 active dirty scope | 页面可展示，Redis month/summary 可缓存该 scope payload。 |
| `missing` | 没有对应月份 read model 或 readiness | 入队 `tax_offset.read_model.refresh`；API 返回 refreshing 或 accepted payload。 |
| `refreshing` | dirty scope pending/processing，或 `all` fan-out 正在入队月份 shard | worker 继续处理；页面展示同步中。 |
| `stale` / `source_mismatch` / `schema_mismatch` | 发票、认证记录、OA 附件或 schema source version 落后 | 入队重建；保存计划应被 version guard 拦截。 |
| `failed` | worker refresh、认证导入 job 或 projection 失败 | App Status busy/blocked，页面显示错误并允许重试或等待运维处理。 |
| `unavailable` | repository、queue、Redis、worker dependency 不可用 | API 返回 unavailable/refreshing 或 App Status blocked；不得返回 fake fresh。 |

Refresh 触发来源：

- 发票导入确认。
- 已认证导入 confirm/job completion。
- ETC 发票导入或 ETC 业务批次影响 invoice facts。
- Workbench relation 确认/撤回、人工发票关系变化。
- 待找发票规则变化、invoice lifecycle refresh。
- OA rebuild 或 OA 附件发票 cache 更新。
- readiness backfill、App Health 运维任务。
- `startup_stale_scan` 默认关闭，且不直接刷新税金 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响。

`all` refresh 流程：

1. 收到 `tax_offset.read_model.refresh` 且 scope 为 `all`。
2. `TaxOffsetReadModelRefreshService` 询问 projection builder 列出月份 shard。
3. 通过 `ReadModelRefreshGateway` 入队每个 `YYYY-MM` shard。
4. 完成 `all` dirty scope；`all` 不写普通 tax offset payload。
5. 月份 shard worker 成功后发布对应 month read model/readiness。

失败恢复：

1. 先看 `/api/app-health.app_status` 中 `tax_offset` domain、readiness scope、dirty scope、outbox 和 `tax-offset` worker；旧 `cost-tax` 只是兼容消费者。
2. 对 `missing/refreshing`，确认 durable queue 是否已有 `tax_offset.read_model.refresh`；不要手工写 fresh。
3. 对 `failed/unavailable`，检查 `tax-offset` worker 日志、SQL projection、tax certified import job 和 Redis 错误。
4. 对计划保存 conflict，让页面重新拉取月份 payload，再基于新 `source_versions` 保存。
5. 对认证导入失败，优先保留 session/job payload，重新 preview/confirm 或按 import job runbook 重试。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-23 | 补 read model manifest 合同守卫 | 不改变税金抵扣业务/UI/read model/worker 状态；锁定 `tax_offset` 为 `partitioned_scoped_incremental`、`all` 为 fan-out command，并保持 `tax-offset` primary worker 与 `cost-tax` 兼容 worker 的 owner 区分 | `tests/test_read_model_manifest.py::ReadModelManifestTests::test_cost_tax_and_turnover_manifest_preserve_summary_contracts` |
| 2026-06-11 | 补齐测试闭环状态机 | 认证状态、计划保存、read model freshness、认证导入 job、UI 和 worker 状态边界 | `tests.test_tax_offset_service`、`tests.test_tax_certified_import_service`、`tests.test_tax_offset_read_model_service`、`tests.test_tax_offset_api`、`tests.test_import_job_queue`、`tests.test_tax_offset_sql_runtime`、`tests.test_read_model_refresh_gateway`、`tests.test_runtime_worker_read_model_refresh_scopes`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_postgres_state_store`、`tests.test_postgres_migrations`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx` |

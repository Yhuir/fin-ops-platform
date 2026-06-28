# 税金抵扣状态机

> 修改 `税金抵扣` 相关业务状态、UI 状态、direct API 数据流或 worker/cache legacy 链路前必须读取本文件。税金抵扣的认证状态事实源是后端 policy/direct read boundary，不是页面本地勾选状态。

## 业务状态

| 状态域 | 状态 | 事实源 | 允许流转 |
| --- | --- | --- | --- |
| 发票生命周期 | `uncertified` / `certified` / `locked_certified` | `InvoiceLifecyclePolicy`、direct read boundary、tax certified records | 发票导入或认证导入后由 lifecycle facts 和 direct query/service 得出；页面只展示 `certified_status` / `is_locked_certified`。 |
| 销项税额 | `selected` / `unselected` | `TaxOffsetService.calculate`、页面勾选请求 | 用户在试算中选择本月销项票；保存计划时带 selected ids 和后端 source versions。 |
| 进项计划 | `planned_uncertified` | `TaxOffsetService`、Invoice repository、OA 附件发票 cache | 真实导入进项票或 OA 附件发票按月份进入计划，允许用户参与试算。 |
| 已认证进项 | `certified_matched` | `TaxCertifiedImportService`、`TaxOffsetService._match_certified_to_plan` | 已认证记录匹配计划进项后锁定对应 input id，不允许再次作为未认证计划行抵扣。 |
| 已认证进项 | `certified_outside_plan` | certified import records | 已认证记录未匹配计划时进入已认证结果侧栏，不反向创建计划行。 |
| 认证导入 session | `previewed` | `tax_certified_import_sessions` / application service | preview 只生成可确认 session，不写最终认证事实。 |
| 认证导入 confirm | `queued` / `running` / `completed` / `failed` | import job repository、confirm job polling API | confirm 可同步完成或排队；页面 modal 轮询 job，完成后刷新当前月份。 |
| 税金计划 | `draft` / `saved` / `conflict` | `TaxOffsetPlanService` | 保存时校验 idempotency key 和 direct source versions；旧版本返回 conflict。 |
| 税额结果 | `payable` / `carry_forward` | `TaxOffsetService.calculate` | `output_tax > input_tax` 为本月应纳税额，否则为本月留抵税额。 |

关键规则：

- 税金抵扣页面不私有定义发票认证生命周期；认证字段来自统一 lifecycle/direct read boundary。
- 没有真实导入、OA 附件或认证记录时，不允许返回硬编码计划行或硬编码已认证结果。
- 已认证进项税额始终计入 input tax；匹配到计划的已认证进项必须从可选未认证计划行中锁定。
- 计划保存必须携带并校验 `source_versions` 和 `idempotency_key`；页面 GET 不再暴露 read model scope key。
- Redis 只属于 legacy/runtime cache，不能作为页面 freshness 事实源。

禁止流转：

- 禁止页面根据本地勾选把认证状态改成 certified。
- 禁止认证导入 preview 直接写最终认证记录。
- 禁止重复导入相同认证记录导致重复抵扣。
- 禁止保存基于过期 direct source versions 的计划。
- 禁止页面 API 请求线程读取 PostgreSQL legacy read model miss/stale 并伪装 fresh；页面 GET 直接从业务 service 组装当前 payload。
- 禁止银行流水导入直接刷新税金抵扣；税金抵扣只受发票、认证、ETC、关系和规则类事件影响。

## UI 状态

| UI 状态 | 来源 | 语义 |
| --- | --- | --- |
| loading | 页面首次请求 `/api/tax-offset?month=...` | 展示加载态；请求 abort 后必须清理 loading，不保留假数据。 |
| refreshing | 用户触发重新读取 `/api/tax-offset?month=...` 且请求未完成 | 保持加载/刷新语义；不读取旧 `read_model_status` 字段。 |
| legacy stale | 后端保存计划返回 source/version conflict | 显示 conflict 反馈，用户重新拉取 direct payload 后再保存。 |
| empty | direct payload 中 output/input/certified 全为空 | 表示当前月份真实没有税金抵扣数据。 |
| error | month/calculate/save/import/job 请求失败 | 展示可理解错误；不暴露底层 SQL、worker 或文件解析 internals。 |
| import preview modal | 用户选择或拖拽 Excel 后 | 展示文件、行级识别状态、计划内/计划外统计；非 Excel 立即拒绝。 |
| import processing modal | confirm 已提交，job queued/running | modal 保持 processing 并轮询 job，不提前关闭或伪造完成。 |
| certified drawer | 用户展开已认证结果 | 展示 matched/outside-plan，点击 matched 行高亮对应计划行。 |
| save pending | 用户保存计划 | 禁用重复提交，成功 toast；version conflict 显示 stale/conflict 反馈。 |
| permission disabled/hidden | session permissions | 只读用户可查看数据，但不显示认证导入和保存类写操作。 |

前端事件：

- `invoiceFactUpdated`、`etcBusinessBatchUpdated` 等事件只能触发页面 refetch 或刷新提示。
- 前端事件不是事实源；页面重新读取 direct API payload 后展示后端结果。
- 离开页面后 React tree 卸载，inactive 页面不 replay 事件；返回页面重新通过 API/read boundary 加载。

## Direct Payload / Worker 状态

| 状态 | 判定 | 后续动作 |
| --- | --- | --- |
| direct payload ready | 当前月份 direct GET 成功返回 rows/summary/source versions | 页面展示业务数据；保存计划使用 direct source versions 和 idempotency key。 |
| direct payload empty | 当前月份 direct GET 成功且 output/input/certified 全为空 | 页面展示真实空态，不入队页面 read-model refresh。 |
| direct payload error | direct query、repository、权限或外部依赖失败 | 页面展示业务错误；不返回旧 `read_model_status` 或伪造 fresh。 |
| import job running | 认证导入 confirm 已排队或运行中 | modal 轮询 job；完成后直接重读当前月份 direct API。 |
| legacy runtime/cache diagnostics | 历史 SQL snapshot、cache warmup 或 Redis 兼容状态 | 只用于运维/回滚诊断，不作为页面 fresh gate。 |

Direct refetch / downstream diagnostics 触发来源：

- 发票导入确认。
- 已认证导入 confirm/job completion。
- ETC 发票导入或 ETC 业务批次影响 invoice facts。
- Workbench relation 确认/撤回、人工发票关系变化。
- 待找发票规则变化、invoice lifecycle facts 更新。
- OA rebuild 或 OA 附件发票 cache 更新。
- App Health 运维任务；readiness backfill 已删除。
- `startup_stale_scan` 默认关闭，且不直接刷新税金 read model；只有后续 matching 结果真实变化并触发业务 lifecycle 时才间接影响。

`tax_offset.read_model.refresh` worker lane 已删除。`all` 只保留为历史 SQL/清理语义，不再通过 durable queue fan-out 月份 shard。

失败恢复：

1. 先看 direct API、认证导入 job、invoice lifecycle 和 cache warmup 状态；不要用 read-model readiness 判断页面 fresh。
2. 对历史 `missing/refreshing` 记录，不要手工写 fresh，也不要恢复 `tax_offset.read_model.refresh` worker。
3. 对 `failed/unavailable`，检查 direct query、legacy compatibility storage、tax certified import job 和 Redis 错误。
4. 对计划保存 conflict，让页面重新拉取月份 payload，再基于新 `source_versions` 保存。
5. 对认证导入失败，优先保留 session/job payload，重新 preview/confirm 或按 import job runbook 重试。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-06-28 | 删除 tax offset read-model worker lane 和旧 cost/tax SQL projection | 不再注册 `tax-offset` / `cost-tax` worker，不再投递 `tax_offset.read_model.refresh`；旧 SQL runtime 测试已删除；页面继续 direct API 读取 | `tests/test_runtime_worker_registry.py`、`tests/test_read_model_manifest.py`、`tests/test_tax_offset_api.py`、`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-11 | 补齐测试闭环状态机 | 认证状态、计划保存、direct API、认证导入 job、UI 和 runtime/cache 状态边界 | `tests.test_tax_offset_service`、`tests.test_tax_certified_import_service`、`tests.test_tax_offset_api`、`tests.test_import_job_queue`、`tests.test_tax_offset_worker_rebuild_executor`、`tests.test_tax_offset_cache_warmup_executor`、`tests.test_derived_data_lifecycle_service`、`tests.test_app_status_overview_service`、`tests.test_postgres_state_store`、`tests.test_postgres_migrations`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx` |

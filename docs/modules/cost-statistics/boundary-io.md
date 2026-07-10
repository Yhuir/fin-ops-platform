# 成本统计模块边界与 I/O

日期：2026-07-10

## 模块化状态

- 状态：closed
- 当前边界可信度：high
- 目标边界：成本统计页面读取 `cost_statistics` SQL read model，经 query gateway 暴露 parent rollup fresh 状态。
- 当前结论：local/non-SQL explorer fallback、route-owner live service fallback、live export workbook helper 和旧 `ProjectDetailExportService` 已删除。成本统计页不再暴露项目范围切换按钮，页面查询固定使用 `project_scope=active`；`project_scope=all` 仍是后端 API/export/read model 合同。按银行统计的银行全集来自 settings owner 输出的银行账户映射，由成本统计 read model payload 暴露给页面；成本统计标签规则来自 app settings owner，只在 query/export 层过滤 fresh explorer payload，不进入 read model source_versions，也不触发全量重建。`按项目`、`按银行`、`按OA费用类型` 只统计被规则选中的 OA 配对流水；`按标签`、`按时间` 统计被规则选中的全部银行支出流水。
- 旧代码删除状态：route owner 不接收旧 `CostStatisticsService` 依赖；project/detail/export/export-preview 只调用 `CostStatisticsQueryService`；`CostStatisticsService` 的旧 live project/detail public methods 已删除；query miss/stale 只返回 refreshing 并入队 durable refresh，不同步扫描 live service；历史 `cost_statistics_cache_warmup` job 入口仅作为兼容桥接，关闭或转入 `cost_statistics.read_model.refresh`，不再构造 payload、写 read model 或写 Redis fresh cache。

## 职责边界

### 负责

- 成本统计页面汇总、筛选、父聚合和明细读取。
- 成本统计页面按时间、项目、银行、OA 费用类型、流水标签五种统计口径的表头总金额展示；总金额只从当前 fresh explorer payload 经标签规则过滤后的可见行汇总，页面不得回读源表。
- 成本统计页面的按银行统计；银行账户全集来自 `app.app_settings.bank_account_mappings` 经后端 owner read port 注入 explorer payload，页面只做零金额账户补位和筛选，不直接调用设置页 API。
- 成本统计页面的 `按标签` 三栏视图；该视图只从 `cost_statistics` explorer read model 的 `bank_flow_time_rows.bank_tag_*` 字段派生主标签、子标签和流水，不直接读取银行明细页 read model。
- 成本统计标签规则抽屉；抽屉读取 app settings owner 归一后的银行主/子标签与虚拟 `__uncategorized__` 未分类标签，保存后等待当前成本统计 scope fresh 再关闭。
- `cost_statistics` read model 的 parent rollup 投影。
- 与税金抵扣共享 cost/tax 投影 worker 时保持明确 event/scope。

### 不负责

- 不拥有税金抵扣业务状态。
- 不直接处理发票导入和 ETC 源事实。
- 不把 `all` 当成无界重建入口；`all` 是 queryable parent aggregate 合同。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面筛选/月份/父级聚合查询 | `CostStatisticsPage.tsx`、`features/cost-statistics/api.ts` | 进入成本统计 API/query service；页面主时间范围只暴露单一按钮选择 `all` / `year` / `month`，不再暴露主页面自定义日期范围；精确日期范围只属于导出中心 |
| 页面只读 Audit | `PageBusinessAuditIcon` / AppHealth operations API | admin-only 调用 `page-audit?domain=cost_statistics`；canonical paired-cost expected-set 必须从 Workbench active generation 的结构化 group/member payload 独立形成，并与 projection builder 使用同一 candidate/linked-open 优先级、完整 OA context tuple（项目名、项目 ID、费用类型、费用内容、申请人）以及 bank payload 方向/金额语义；fresh bank-detail expense rows 独立形成 full bank-flow expected-set。transaction identity、数量、金额、项目/费用类型和 summary 必须重算一致，并要求共享 relation 双向 edge equality 与只读一致性快照；审计只读，不能触发成本统计 rebuild/export 或读取旧 live service |
| 银行账户全集 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_account_mappings` | 仅后端投影层读取 settings owner 输出，写入 explorer payload 的 `bank_accounts`；页面不得直接读取 settings API 或设置页面状态 |
| 银行自动标签规则版本 | `AppSettingsService.get_cost_statistics_source_settings_payload()` / `app.app_settings.bank_transaction_tags` | 进入 `source_versions.bank_auto_tag_rules_version`；规则更新由 `bank_auto_tag_rules_changed` lifecycle 入队 `cost_statistics.read_model.refresh` |
| 银行明细有效标签 | `BankTransactionTagReadFacade` / fresh `bank_detail` read model | 成本统计 worker 按月份批量读取银行流水 `effective_category_*`，写入 `time_rows.bank_tag_*`；`bank_detail_source_versions` 纳入成本统计 source_versions，非 fresh 时 worker fail-closed 并等待依赖刷新 |
| 成本统计标签规则 | `AppSettingsService.get_cost_statistics_tag_selection_payload()` / `app.app_settings.cost_statistics_tag_selection` | route 只暴露归一后的主/子标签、`__uncategorized__` 未分类标签和已选 leaf codes；默认未配置时等价于全选当前有效支出标签 + 未分类，显式空数组表示全部不进入成本统计。保存规则不写 read model、不写 dirty scope，只返回当前 `cost_statistics` operation barrier target 供页面等待 fresh |
| 全流水标签统计输入 | `CostStatisticsSqlProjectionBuilder` + `BankDetailsApplicationService` | 月度投影在 read model 边界内批量读取 fresh `bank_detail` 支出流水，写入 `bank_flow_time_rows` 与 `bank_flow_summary`；父 scope 只从已物化月份 shard payload 汇总这些字段，禁止页面直接读银行明细 API |
| 流水标签三栏统计 | `CostStatisticsPage.tsx` | 输入是 fresh explorer `bank_flow_time_rows` 中的 `bank_tag_code`、`bank_tag_label`、`bank_tag_primary_label`、`bank_tag_sub_label`、`bank_tag_label_path`；缺失旧 payload 在 query/API mapper 层可回退到 `time_rows`，正常生产链路通过 fresh `bank_detail` 标签重新投影 |
| 项目明细/流水详情/导出请求 | `routes_cost_statistics.py` | 只调用 `CostStatisticsQueryService`；read model 不 fresh 时返回 `409 cost_statistics_read_model_not_fresh`，不得同步扫描旧 live service 伪装成功；成本统计页面默认透传 `project_scope=active` |
| Refresh scope | `cost_statistics` manifest | active/all month + parent aggregate |
| Workbench 月度输入 | `read_model.workbench_generations` active generation + `read_model.workbench_groups` | 先定位 active generation，再按 `generation_id + scope_key` 读取 groups；禁止按裸 `scope_key` 扫描历史 generation |
| 关系变更 | workbench relation/downstream lifecycle | 转换为受影响 cost_statistics scopes |
| 导入确认 | import processing service/job result | 返回规范化后的 cost_statistics operation barrier targets，月份输入经 scope policy 展开为 active/all shards 与 parent aggregate |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 成本统计 rows/summary | 前端页面 | query gateway 后返回 freshness；`time_rows` 输出 OA 配对成本流水字段和流水标签 `bank_tag_*` 字段，供 `按项目`、`按银行`、`按OA费用类型` 使用；`bank_flow_time_rows` 输出全部银行支出流水标签字段，供 `按标签`、`按时间` 使用 |
| 页面 Audit 状态 | 标题附件 | 只有 audit status 与 explorer read model 均明确 fresh/pass 才显示成功；问题数量是有上限 sample |
| Explorer bank accounts | 前端页面 | `bank_accounts` 输出设置中的银行账户全集，字段为 `bank_name`、`account_last4`、`payment_account_label`、`source`；按银行统计必须展示这些账户，即使当前范围金额为 0 |
| Source versions | read model/query gateway | `source_versions` 必须包含 workbench/input 版本、`bank_auto_tag_rules_version` 和 `bank_account_mappings_fingerprint`；任一变化都使旧 payload 失配并刷新 |
| Project/detail/export payload | 前端页面 / 下载 | 由 fresh `cost_statistics` explorer read model 组装；导出保留 filename/workbook/row-limit contract；live `CostStatisticsService` 不再拥有 export-preview/export 输出 |
| Parent rollup | read model repository | scoped parent aggregate |
| Dirty scope | runtime queue | fan-out 到必要 parent/month scopes |
| Write target visibility | 导入/关系写 API | 上游写操作必须显式透出 `cost_statistics` targets，成本统计页面自身保持纯读面 |

## 持久化与投影

- Read model：`cost_statistics`
- Projection：`partitioned_scoped_parent_rollup`
- `all` 语义：`queryable_parent_aggregate`
- Worker：`cost-statistics`；旧 `cost-tax` 成本统计消费链路已移除
- Query owner：`CostStatisticsQueryService`；项目明细、流水详情、export-preview、export 都归属该 owner。
- Miss/stale owner：`ReadModelQueryGateway`；SQL view 缺失、stale、source mismatch 或 payload invalid 时返回 `refreshing` envelope 并入队 `cost_statistics.read_model.refresh`，禁止同步 rebuild。
- `time_rows.bank_tag_*` 的来源是 `BankTransactionTagReadFacade` 暴露的 fresh `bank_detail` scoped read model 有效分类字段，经 `cost_statistics_bank_tags.bank_tag_context_from_row(...)` 归一化后写入成本统计 read model payload。父 scope 从已物化月份 rows 的 payload 回读这些字段，不能回头读 Workbench `all`、Workbench 行内旧标签字段或银行明细页面 API。
- `bank_flow_time_rows.bank_tag_*` 的来源是成本统计投影层通过银行明细 read facade 批量读取的 fresh 支出流水；它是 `按标签`、`按时间` 的全流水统计输入。`time_rows` 继续是 OA 配对成本输入；两类 rowset 的总金额口径允许不同。
- 成本统计标签规则由 `AppSettingsService` 持久化，`CostStatisticsQueryService` 读取归一后的 selected leaf codes 并在 query/export 层过滤。该规则不是投影 source version，保存时不触发 read model rebuild；页面只等待当前 scope freshness，避免全量刷新放大耗时。
- `bank_accounts` 的来源是 settings owner 的银行账户映射，投影层通过 `cost_statistics_bank_accounts.py` 归一为页面只读 payload，并以 `bank_account_mappings_fingerprint` 纳入 source version。页面银行统计以 `bank_accounts + time_rows` 合并生成，禁止恢复只从当前流水推断银行全集的旧逻辑。
- Upstream read model 输入：月份 shard 只消费 Workbench active generation；父 scope 从已物化 `read_model.cost_statistics_rows` 聚合，不读 Workbench `all` 或历史 generation。
- Explorer payload schema version：`2026-07-cost-statistics-audit-proof-v6`。生产 v6 投影必须输出 `bank_accounts`、`bank_flow_summary` 和 `bank_flow_time_rows`，并将带千分位的展示金额无损写入结构化 `cost_statistics_rows.amount`，供 Audit 独立重算 expected-set 和 summary；旧 schema payload 或仍使用 Workbench 行内旧标签字段时必须通过 schema gate fail-closed 并重新投影。query/API mapper 可兼容历史本地 fixture 缺少 `bank_flow_time_rows` 的形态，但生产链路不能依赖该兼容形态提供全流水统计。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` |
| Frontend components | `web/src/components/cost-statistics/*`、`web/src/features/cost-statistics/*` |
| Backend route | `backend/src/fin_ops_platform/app/routes_cost_statistics.py` |
| Backend service | `cost_statistics_query_service.py`、`cost_statistics_runtime_service.py`、`cost_statistics_service.py`、`cost_statistics_read_model_service.py`、`cost_statistics_bank_tags.py`、`cost_statistics_bank_accounts.py`、`app_settings_service.py` |
| Repository / SQL | `cost_statistics_read_model_repository.py`、`cost_tax_sql_projection.py` |
| Worker/read model | `cost_statistics_read_model_refresh.py`、`cost_statistics_derived_lifecycle_executor.py`、`runtime_worker_registry.py` |
| Tests | `tests/test_cost_statistics*.py`、`web/src/test/CostStatistics*.test.*`、`web/e2e/cost-statistics-*.spec.ts` |

## 依赖方向

- 允许依赖：workbench active generation read model、workbench relation read model、settings owner read port、`BankTransactionTagReadFacade`、银行明细 fresh read facade、cost/tax projection、query gateway。
- 必须通过：CostStatisticsQueryService 和 read model query gateway。
- 禁止绕过：页面/API 直接扫描源表伪装 fresh；页面直接调用 settings API 读取银行账户；页面直接调用银行明细 API/read model 读取标签规则或全流水 rows；成本统计投影继续信任 Workbench 行内旧标签字段；route owner 调用旧 `CostStatisticsService.get_project_statistics/get_transaction_detail/get_export_preview/export_view`；query service 持有 live `CostStatisticsService`、local read model service 或 `_cached_month_entries` fallback；runtime service 持有 `explorer_loader`、`_upsert_read_model` 或 `worker_cost_statistics_read_model_refresh` 写入路径；成本统计投影按裸 `scope_key` 扫描 Workbench 历史 generation；把税金抵扣状态写入成本统计模块。

## 测试与验证

- `tests/test_cost_statistics_sql_runtime.py`
- `tests/test_cost_statistics_api.py`
- `tests/test_app_settings_service.py`
- `tests/test_cost_statistics_runtime_service.py`
- `tests/test_import_processing_service.py`
- `tests/test_derived_data_lifecycle_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `web/src/test/CostStatisticsPage.test.tsx`
- `web/src/test/CostStatisticsApi.test.ts`
- `web/e2e/cost-statistics-flow.spec.ts`
- `web/e2e/cost-statistics-relation-fanout.spec.ts`

## 当前缺口和删除条件

- 模块边界已 closed；后续若恢复 local fallback、live export helper、旧 warmup writer 或页面项目范围切换，必须重新打开本模块状态并补全 UAT。
- 成本统计页面旧 UI 已删除：标题下解释文案、三张顶部 summary card、项目范围切换按钮、主页面自定义日期范围和旧范围 tab 不再作为页面 I/O；导出中心仍保留精确日期范围。
- 按时间统计旧 ISO/T 字符串直出已关闭；页面展示统一格式化为 `YYYY-MM-DD HH:mm:ss`，过滤仍使用原始 `trade_time`。
- 按银行统计旧“只从当前流水分组得出银行列表”的逻辑已删除；银行全集由 read model payload 的 `bank_accounts` 输入决定。
- 成本统计标签规则是本模块唯一写入口；route 仍保持 thin owner，只委托 `AppSettingsService` 持久化并返回当前 `cost_statistics` scope 的 operation barrier target。页面保存时必须等待该 target fresh 后再关闭抽屉；等待范围只能是当前 scope，禁止保存规则后触发全量 read model rebuild。
- 性能边界：首屏 API/read model 只能走 SQL read model + Redis fresh cache；API miss 不同步扫描 Workbench/live service。`source_versions` 读取 settings 时使用一次 owner payload snapshot 同时计算标签规则版本和银行账户指纹，标签选择过滤在 query/export 层完成并参与 Redis cache key；禁止为页面补全银行/标签额外发起 settings 或 bank-detail API 请求。当前生产 HTTP SLO 目标继续按 page shell、explorer、summary p95 <= 1000ms 验收，worker direct refresh 保持父 scope 有界聚合。

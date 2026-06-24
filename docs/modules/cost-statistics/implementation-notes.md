# 成本统计 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 成本统计 read model refresh scope 只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`；旧裸月份/裸 `all` 必须在统一 read model refresh gateway 中归一化，不能直接进入 durable queue。
- 生产库中已有的成本统计 legacy/invalid runtime scope 通过 `scripts/check-read-model-scope-contracts.py` 检查；`--apply` 删除旧状态，并补投可归一化的规范 replacement scope。
- 成本税务 projection 中的发票输入必须来自 canonical invoice facts；OA 附件正式发票先 promotion 到 Invoice repository / `app.invoices`，不能从 `app.oa_attachment_invoice_cache` 直接拼计划或成本税务输入项。
- 成本统计 export-preview/export 是同步生成路径；time、month、project、expense_type 导出超过 20,000 行时必须返回 `cost_statistics_export_row_limit_exceeded`，不能继续生成大预览或 XLSX。
- 2026-06-11 测试闭环审计确认：现有 P0/P1 覆盖成本归因、API/导出、SQL read model、parent/shard readiness、scope gateway、App Status 和前端交互；本轮不新增重复代码测试，主要补齐模块测试矩阵和状态机文档。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-06-24 - Modular IO repository port extraction

- 目标：执行 `read-models:cost-statistics-repository-port-extraction`，把成本统计 read model load/get/save surface 收窄到显式 repository port。
- 影响范围：`CostStatisticsReadModelRepositoryPort`、`CostStatisticsSqlProjectionBuilder`、`PostgresStateStore.cost_statistics_sql_read_repository`、成本统计 SQL runtime/state-store tests；不改变成本归因、项目范围、导出、parent aggregate、API shape、worker event、queue schema、Redis key/envelope 或前端行为。
- 关键决策：新增 `CostStatisticsReadModelRepositoryPort`，只暴露 `load_cost_statistics_read_models`、`get_cost_statistics_view`、`save_cost_statistics_read_models`。`CostStatisticsSqlProjectionBuilder` 和 PostgreSQL SQL read wiring 使用该 port；SQL/table owner 仍是 `PostgresReadModelRepository`。
- 文档影响：新增 modular IO repository port extraction analysis，更新 autonomous queue/state/journal/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵。
- 测试覆盖：新增 `CostStatisticsReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`，扩展 `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection`，复跑成本统计 SQL projection parent/month 目标测试。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实大数据性能、真实浏览器生产样本和生产 scope cleanup evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`；Go summary-rollup admission 继续 blocked。

## 2026-06-24 - Modular IO pilot selected after tax offset

- 目标：执行 `read-models:next-pilot-selection-after-tax-offset`，确认 `cost_statistics` 是否应作为 tax offset 之后的下一非 Go read model 模块化试点。
- 影响范围：modular IO analysis/state/queue/next prompt、主控 prompt、read-models/cost-statistics 实施记录和测试矩阵；不改成本归因、API、UI、worker、queue 或 Redis 合同。
- 关键决策：选择 `cost_statistics`。本模块同时消费 Workbench relation、银行明细标签、导入事实、ETC/no-OA/turnover/settings fan-out；还拥有 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all` 特殊 scope、queryable parent aggregate 和旧 `cost-tax` compatibility worker lane。首切为 `CostStatisticsReadModelRepositoryPort` 抽取。
- 文档影响：新增 modular IO next-pilot selection analysis，更新 autonomous queue/state/journal/next prompt 和主控 prompt。
- 测试覆盖：本轮为 analysis/accounting only；下一实现切片必须新增/更新 repository port guard，并保持 SQL runtime/freshness/parent aggregate 测试通过。
- 验证命令：见 `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker drain、真实大数据性能、真实浏览器生产样本和生产 scope cleanup evidence 仍 deferred。
- 后续事项：执行 `read-models:cost-statistics-repository-port-extraction`；Go summary-rollup admission 继续 blocked。

## 2026-06-20 - 成本统计 explorer 加载失败刷新恢复

- 目标：补齐 `cost-statistics` 的本地 `NETWORK-RECOVERY` Browser 负面链路，避免 explorer 首屏暂时 503 时页面显示正常空态、允许导出中心伪成功，或没有显式恢复路径。
- 影响范围：`web/src/pages/CostStatisticsPage.tsx`、`web/e2e/fixtures/apiMocks.ts`、`web/src/test/apiMock.ts`、`web/e2e/cost-statistics-flow.spec.ts`、`web/src/test/CostStatisticsPage.test.tsx`、成本统计和全局测试闭环文档；不改后端业务逻辑、成本归因、read model scope contract 或 API shape。
- 关键决策：页面新增显式 `刷新` 入口，手动刷新时清理 explorer cache 并触发重新请求；根 explorer 加载失败且没有可用 explorer 数据时禁用导出中心，但流水详情加载失败不禁用导出中心；deterministic mock 的 transient failure 只作用于当前可见月份 explorer，避免隐藏的 `month=all` 导出参考数据请求消耗失败次数。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::recovers explorer after a transient load failure when refreshed`；新增 `web/src/test/CostStatisticsPage.test.tsx::refreshes explorer data after a transient loading failure`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium` 通过 9 tests；`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx` 通过 20 tests。
- 未测风险：本地 deterministic 503 不等于真实网络中断、真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 或生产大数据恢复；这些仍需 infra-smoke/staging/production smoke。
- 后续事项：继续按全局 `NETWORK-RECOVERY` 队列补其他页面或 mutation 级失败恢复。

## 2026-06-19 - 生产 authenticated 成本统计 500 与 schema_version 查询修复

- 目标：修复生产 authenticated HTTP probe 暴露的成本统计 API 500，避免成本统计页面在真实登录态下无法作为 Spec-first runtime gate 的一部分闭环。
- 影响范围：`PostgresReadModelRepository.get_cost_statistics_view(...)`、`tests/test_cost_statistics_sql_runtime.py`、生产 release `main-bf02acc5-coststats-schema-20260619172500`；不改变成本归因、scope contract、payload shape、read model refresh 或前端展示。
- 生产证据：使用现有目标 OA 申请人凭据临时登录后，`/api/session/me` authenticated 通过，SSE first-event smoke 通过；full authenticated HTTP probe 发现 `/api/cost-statistics/explorer?month=2026-03&project_scope=active` 和 `/api/cost-statistics?month=2026-03&project_scope=active` 返回 `500 internal_server_error`。后端日志显示 `column "schema_version" does not exist`，位置在 `get_cost_statistics_view(...)` 查询 `read_model.cost_statistics_read_models`。
- 根因：`read_model.cost_statistics_read_models` 由 `0006_read_models.sql` 创建，表上没有顶层 `schema_version` 列；版本事实在 `payload` / `raw_payload` 内。旧测试模拟 row 带有 `schema_version` 字段，未约束 SQL 不选择不存在列。
- 修复与发布：新增 RED 测试 `test_repository_reads_cost_statistics_schema_version_from_payload_not_table_column`，确认 repository 从 payload 读取 schema version 且父表 SQL 不包含 `schema_version`；随后移除父表 select 中的 `schema_version`。在隔离 clean worktree 基于生产 commit `3d88ce99` 提交 `bf02acc5 Fix cost statistics read model schema query` 并发布激活。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_cost_statistics_sql_runtime.py tests/test_postgres_repositories_boundaries.py -q` 通过 `38 passed`；`PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`；`git diff --check`；`VITE_APP_BASE_PATH=/fin-ops/ npm run build`。
- 发布后复验：`health_ready_payload_probe` 通过；`read_model_slo_smoke --apply --read-model-key output_invoice_collection --read-model-key cost_statistics --target-ms 5000` 通过，`cost_statistics:active:2026-04` 约 `2843.542ms`；两个成本统计 authenticated endpoint 从 `500` 变为 `200`。
- 未测风险：full authenticated HTTP gate 仍未闭合，因为生产缺 admin 登录态导致 admin-only dashboard 403，且 `output-invoice-collections` 默认 `all` 读路径仍返回 `read_model_status=refreshing`。

## 2026-06-19 - 生产 direct refresh SLO 失败与 rows 批量保存发布复验

- 目标：处理生产 critical read model apply gate 中 `cost_statistics:active:2026-04` 超过 5 秒 direct refresh SLO 的问题，避免成本统计真实 worker drain 成为 Spec-first E2E 总闭环尾部风险。
- 影响范围：`PostgresReadModelRepository._replace_cost_statistics_rows(...)`、成本统计 read model rows 写入性能、本模块实施记录；不改变成本归因、项目范围、scope contract、API shape、前端展示或导出行为。
- 生产证据：在 release `main-33a150e7-write-e2e-approval-gate-20260619151922` 执行 `read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120`，15 个 critical scope 全部达到 dirty/outbox `done` 和 readiness `fresh`/`dirty_done`，但 `cost_statistics:active:2026-04` enqueue-to-fresh 约 6459.019ms。只重跑失败 scope 后，`invoice_lifecycle` 已通过，`cost_statistics:active:2026-04` 仍约 7003.227ms，说明成本统计不是一次性并发抖动。
- 根因调查：成本统计 month scope rebuild 最终调用 `_replace_cost_statistics_rows(...)`；该方法删除 scope rows 后对 `time_rows` 每行执行一次 `connection.execute(...)` insert/upsert。生产失败样本 handler duration 接近 enqueue-to-fresh duration，慢点集中在 handler 本身，逐行写入是当前最直接根因。
- 修复与发布：新增 `tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch`，先 RED 证明 `executed_many` 为 0；随后将 rows 保存改为收集 params 并调用 `_execute_many(...)`，保持 delete、字段映射、`on conflict (scope_key, row_key)` 和同一事务不变。为避免混入主工作区未提交变更，基于生产 commit `33a150e7` 创建隔离 clean worktree，提交 `3d88ce99 Optimize cost statistics read model row saves`，通过 release `main-3d88ce99-coststats-batch-20260619170500` 发布激活。
- 发布后复验：新 release 上 `health_ready_payload_probe` 通过，`runtime_release.consistent=true`、`runtime_blocker_count=0`；`read_model_slo_smoke --critical-only --apply --target-ms 5000 --timeout-seconds 120` 15/15 pass，summary p50 约 490.393ms、p95/max 约 3176.5ms，`cost_statistics:active:2026-04` 降至约 3176.5ms。
- 文档影响：同步 `docs/modules/read-models/implementation-notes.md` 与全局 `docs/dev/testing-closure-state.md`。
- 测试覆盖：新增 repository boundary 性能合同测试；既有成本统计 SQL runtime 测试继续覆盖 read model payload、freshness、cache 和 API 行为。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py::test_cost_statistics_rows_are_saved_in_batch -q` 先 RED 后 PASS；`PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_repositories_boundaries.py tests/test_cost_statistics_sql_runtime.py -q` 通过 37 tests；`PYTHONPATH=backend/src python3 -m compileall backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 通过。
- 未测风险：生产 direct refresh SLO 已复验通过；真实业务写操作 SLO、认证态 HTTP SLO 和受控 mutating write scenario 仍未闭环。

## 2026-06-19 - 成本统计 Spec-first covered 校准

- 目标：完成 `cost-statistics` 本地 Spec-first E2E Audit 校准，把剩余 `COST-E2E-007`、`COST-E2E-009` 和 `COST-E2E-010` 从 partial 收敛为 covered。
- 影响范围：成本统计 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：成本页当前无写入口，页面权限风险集中在 read/export，`read_export_only` 当前筛选下载、forbidden/expired/API auth 与全局 role matrix/API contract 足以覆盖 `COST-E2E-007`；导出 Browser download event、文件名、请求筛选和内容字段已覆盖，真实 workbook 打开归 staging/manual 风险，不阻塞 `COST-E2E-009`；银行/发票/ETC 导入、no-OA、turnover、settings 和 Workbench relation 已有成本统计 fresh read model 或下游影响行 Browser 证据，search 目前无独立前端 route，由 API/runtime 证据覆盖，因此 `COST-E2E-010` 本地闭环。
- 文档影响：`docs/modules/cost-statistics/e2e-coverage.md` 将 `COST-E2E-007/009/010` 标记为 `covered`；`docs/dev/spec-first-e2e-inventory.md` 将 `cost-statistics` 页面状态更新为 `covered`。
- 测试覆盖：未新增测试；本轮是基于现有 `cost-statistics-flow`、`cost-statistics-relation-fanout`、导入/no-OA/turnover/settings Browser specs 和后端 read model/API 证据做覆盖校准。
- 验证命令：待本轮运行 `bash scripts/verify.sh docs`、成本统计相关 Playwright specs 和 `git diff --check`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 打开、真实大文件/历史模板、生产 scope cleanup `--apply`、未来独立 search Browser UI 和新增成本页写入口仍需 staging 或后续功能轮次。
- 后续事项：按全局队列继续推进其他 `spec-first-partial` 页面，优先 import、pending invoices、no-OA/turnover/batch-accounting 或真实 infra smoke。

## 2026-06-19 - 成本统计 detail/export non-fresh Browser 防伪成功

- 目标：补齐 `COST-E2E-006` 在 fresh explorer 下的 detail/export non-fresh Browser 负面路径，避免只证明主 explorer 非 fresh 防 false-empty。
- 影响范围：`web/e2e/fixtures/apiMocks.ts`、`web/e2e/cost-statistics-flow.spec.ts`、成本统计 Spec-first 覆盖矩阵、测试矩阵和全局 testing closure 文档；不改产品代码。
- 关键决策：扩展 deterministic mock 的 `costStatisticsTransactionDetailReadModelStatus` 和 `costStatisticsExportReadModelStatus`，让 transaction detail、export-preview 和 export 能返回 `cost_statistics_*_not_fresh` 409。Browser 用例在 fresh explorer 下触发详情和导出，断言不打开旧详情、不显示旧预览表、不触发 download，并展示“成本统计数据正在刷新，请稍后重试导出。”。预期 409 会产生浏览器资源日志，测试只允许该预期日志，不允许其他 console/page/request/dialog 错误。
- 文档影响：`COST-E2E-006` 从 `partial` 更新为 `covered`；当时成本统计整体仍保持 `spec-first-partial`，现已由本文件上方 “成本统计 Spec-first covered 校准” 记录取代。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::does not treat non-fresh transaction detail or export responses as successful results`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium -g "does not treat non-fresh transaction detail"`；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：真实 RabbitMQ/Redis/systemd worker drain、真实 XLSX workbook 打开、生产大数据和 search 外层 UI 仍需后续轮次或 staging smoke。
- 后续事项：已完成 `COST-E2E-010` 本地闭环校准；真实 worker drain、真实 XLSX 和未来 search Browser UI 继续作为 staging/后续功能风险。

## 2026-06-19 - 成本统计按银行/费用类型 Browser baseline

- 目标：补齐 `COST-E2E-001` 的真实浏览器 bank/expense baseline，避免成本统计只用 Vitest/API 证明按银行和按费用类型视图。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、成本统计 Spec-first 覆盖矩阵、测试矩阵和全局 testing closure 文档；不改产品代码或 API mock shape。
- 关键决策：复用现有 deterministic 成本 explorer 数据，在同一 Chromium 用例中从成本统计页切到按银行，选择 `工商银行 账户 0001` 和 `云南溯源科技`，断言银行对应流水表展示 `PLC 模块采购` 与供应商并打开流水详情；再切到按费用类型，选择 `设备货款及材料费`，断言费用类型流水表和详情可用。用例收集 console/pageerror/requestfailed/dialog，防止“页面显示了但浏览器报错”被误判为通过。
- 文档影响：`COST-E2E-001` 从 `partial` 更新为 `covered`；当时成本统计整体仍保持 `spec-first-partial`，现已由本文件上方 “成本统计 Spec-first covered 校准” 记录取代。
- 测试覆盖：新增 `web/e2e/cost-statistics-flow.spec.ts::shows bank and expense-type baselines with drilldown details`。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium -g "shows bank and expense-type baselines"`；`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：真实生产超大数据、真实 worker drain、真实 XLSX workbook 打开和 search 外层 UI 仍需后续轮次或 staging smoke。
- 后续事项：继续审计 `COST-E2E-006` detail/export non-fresh 和 `COST-E2E-010` 真实基础设施 fan-out。

## 2026-06-19 - 成本统计大数据窄屏宽表 Browser 覆盖

- 目标：补齐 `COST-E2E-008`，用真实 Chromium 证明成本统计在大数据、长字段、390px 窄屏下不是只返回 fresh payload，而是表格和下钻交互仍可用。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计测试矩阵、Spec-first 覆盖矩阵和全局 testing closure 文档。
- 关键决策：
  - 新增 opt-in deterministic mock `costStatisticsLargeDataset`，默认成本统计数据不变；启用时向 `2026-03` active/all explorer 增加 120 条长项目名、长对方户名、长费用内容和多费用类型成本行。
  - Browser 流先等待 `/api/cost-statistics/explorer?month=2026-03&project_scope=active` 返回 `read_model_status=fresh` 和 120+ rows，再断言按时间表存在大数据行、表格可横向/纵向滚动、右侧列在 viewport 内、导出入口未被遮挡且无浏览器错误。
  - 切到按项目后继续等待 `active:all` fresh explorer，选择长项目和费用类型，断言项目对应流水表展示长字段并可横向/纵向滚动。
  - 首次运行失败属于测试断言问题：按时间表本来不展示对方户名，已把对方户名断言放到项目下钻表；第二轮失败属于 HeroUI 表头包装层导致的 `elementFromPoint` 假阳性，表头改为 viewport 可见性，按钮/选择器仍保留未遮挡检查。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 新增 `web/e2e/cost-statistics-flow.spec.ts::keeps large cost tables fresh, scrollable, and usable on narrow screens`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的成本统计 large dataset mock。
- 验证命令：`cd web && npx playwright test e2e/cost-statistics-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker；真实 enqueue-to-fresh drain、生产超大数据查询/下载耗时、真实 XLSX 打开和生产视觉性能仍需 staging/production smoke。
- 后续事项：继续推进真实基础设施 worker drain、其他页面 relation 字段导出或更多撤销链路。

## 2026-06-19 - settings project scope 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明设置页项目状态变化后，成本统计通过自己的 active/all project scope read model 展示一致结果。
- 影响范围：`web/e2e/settings-data-reset-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和 settings 测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `settingsProjectScopeFanout`，让 settings GET/POST 保留 `completed_project_ids`，并把保存后的完成项目集传给成本统计 explorer。
  - Browser 流保持 settings 主链路：设置页项目状态管理 -> 把 `昆明卷烟厂动力设备控制系统升级改造项目` 标记完成 -> 保存设置并断言 POST `completed_project_ids` -> 进入成本统计 -> 默认 active scope 不显示该项目 -> 切到 all scope 后显示该项目和金额 `4,800.00`。
  - 测试捕获 `pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog，避免 settings 保存成功但成本页浏览器报错被误判为通过。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、settings 测试矩阵/实施记录、全局 Spec-first inventory / testing closure state。
- 测试覆盖：
  - 更新 `web/e2e/settings-data-reset-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 settings -> cost statistics project scope fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/settings-data-reset-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd settings lifecycle 与 cost-statistics worker；真实 enqueue-to-fresh drain、历史 settings payload 和 search 联动仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - turnover manual closure 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明外部往来手动闭环确认后，成本统计不是只依赖周转页成功 toast，而是重新读取自己的 fresh read model 并展示闭环成本行。
- 影响范围：`web/e2e/turnover-ledger-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和外部往来测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `turnoverCostFanout`，仅在外部往来闭环已确认且测试显式启用时，把 `turnover-bank-expense-1000` 作为 `2026-05` 的外部往来闭环成本行暴露给成本统计；默认成本统计 mock 不变。
  - Browser 流保持外部往来主链路：选择同组两条流水 -> confirm closure -> operation barrier -> 成本统计 fresh explorer -> 按项目/费用类型/流水表展示 `外部往来闭环成本项目`、`外部往来款付款`、`浏览器 e2e 归还借款` 和 `建设银行` -> 回外部往来完成撤回并验证闭环 chip 移除。
  - 测试捕获 `pageerror`、`console.error`、非 abort `requestfailed` 和未预期 dialog，避免“关系已建立但浏览器报错”被误判为通过。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/modules/turnover-ledger/tests.md`、`docs/modules/turnover-ledger/implementation-notes.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 更新 `web/e2e/turnover-ledger-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 turnover -> cost statistics fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/turnover-ledger-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `turnover-ledger` 与 `cost-statistics` worker；真实 enqueue-to-fresh drain、生产历史周转关系和大数据页面性能仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - no-OA submit 到成本统计 Browser fan-out

- 目标：继续推进 `COST-E2E-010`，用真实 Chromium 证明 no-OA 手续费批次提交后，成本统计不是依赖本页状态或静态数据，而是重新读取自己的 fresh read model 并展示 no-OA 成本行。
- 影响范围：`web/e2e/no-oa-bank-batches-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计和 no-OA 测试矩阵、Spec-first 覆盖矩阵和全局 testing closure state。
- 关键决策：
  - 新增 opt-in deterministic mock `noOaCostFanout`，仅在 no-OA 批次已提交且测试显式启用时，把 `no-oa-bank-e2e-001` 作为 `2026-05` 的免 OA 手续费成本行暴露给成本统计；默认成本统计 mock 不变。
  - Browser 流保持 no-OA 主链路：选择未提交流水 -> submit-selection -> operation barrier -> 成本统计 fresh explorer -> 按项目/费用类型/流水表展示 `免OA手续费成本项目`、`手续费`、`网银手续费` 和 `建设银行` -> 回 no-OA 完成撤回和历史只读断言。
  - 首次运行失败属于测试 selector bug：`/手续费/` 同时匹配项目按钮和费用类型按钮；已收窄为 `/手续费 1 条流水/`，未发现产品逻辑问题。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/modules/no-oa-bank-batches/tests.md`、`docs/modules/no-oa-bank-batches/implementation-notes.md`、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：
  - 更新 `web/e2e/no-oa-bank-batches-flow.spec.ts`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的 no-OA -> cost statistics fan-out mock。
- 验证命令：`cd web && npx playwright test e2e/no-oa-bank-batches-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `no-oa-bank-batch` 与 `cost-statistics` worker；真实 enqueue-to-fresh drain、生产历史 no-OA 批次和大数据页面性能仍需 staging/production smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - ETC 导入到成本统计 Browser fan-out 文档校准

- 目标：推进 `COST-E2E-010` 的导入类 fan-out 闭环，确认 ETC 导入确认后不是只在导入页显示 job success，而是进入成本统计页读取 fresh read model 并展示导入成本行。
- 影响范围：成本统计 Spec-first E2E 覆盖矩阵、测试矩阵、实施记录和全局 testing closure state；本轮不改业务代码。
- 关键决策：
  - 复用 `web/e2e/imports-etc-invoices-flow.spec.ts::confirms ETC import and observes downstream read models as fresh` 作为成本统计下游导入 fan-out 的 Browser 证据，避免重复造一条只覆盖同一 mock 状态的成本页测试。
  - 该测试在 ETC confirm 后依次进入 ETC 票据、税金抵扣和成本统计；成本统计阶段等待 `/api/cost-statistics/explorer`，断言 `read_model_status=fresh`，再切到按项目并展示 `ETC导入通行成本项目`、金额 `32.26`、`ETC高速通行费` 和 `ETC导入通行服务商`。
  - 当时 `COST-E2E-010` 仍为 `partial`：ETC 导入已有 Browser 证据；后续银行/发票导入、no-OA、turnover、settings 和权限/导出证据补齐后，已由本文件上方 covered 校准记录收敛。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md`、`docs/dev/testing.md`、`docs/dev/testing-closure-state.md` 和 `docs/dev/testing-closure-dependency-map.md`。
- 测试覆盖：未新增测试；校准并验证既有 `web/e2e/imports-etc-invoices-flow.spec.ts` 中 ETC import downstream fan-out。
- 验证命令：`cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium`。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd import/cost-statistics worker；真实 ETC zip、对象存储、OA 草稿、enqueue-to-fresh drain、真实 search/historical repair 仍需 staging 或生产只读 smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - 成本统计导出 Browser download event

- 目标：补齐 `COST-E2E-009` 的本地 Browser 证据，避免成本统计只覆盖导出预览和 row-limit 错误，而没有真实 download event、文件名、筛选参数和导出字段保护。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、成本统计 Spec-first E2E 覆盖矩阵、测试矩阵和全局 testing closure state。
- 关键决策：
  - 成本统计 deterministic mock 默认仍返回 row-limit 400，保留既有错误反馈测试；只有 `costStatisticsExportDownloadSuccess` opt-in 时返回成功下载。
  - Browser 测试使用 `read_export_only` session，先跑 export-preview，再触发真实 download event，断言 `view=time`、`month=2026-03`、`project_scope=active`，且不带 `page` / `page_size`。
  - 本地下载体使用可读文本模拟 xlsx payload，锁定流水 ID、项目、费用类型、费用内容、对方户名、支付账户和筛选字段；真实生产 XLSX workbook 打开和完整解析仍留给 staging/manual smoke。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：
  - 新增 `web/e2e/cost-statistics-flow.spec.ts::downloads the current time-view cost rows with request filters and cost fields`。
  - 更新 `web/e2e/fixtures/apiMocks.ts` 的成本统计导出成功 mock。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实生产/staging 后端生成真实 XLSX；真实 workbook 打开、格式、公式、超大数据耗时和代理下载头仍需真实环境 smoke。
- 后续事项：继续补真实基础设施 worker drain、更多导入变体或 `COST-E2E-008` 大数据宽表/视觉稳定性。

## 2026-06-19 - 成本统计 read model 非 fresh Browser 防护

- 目标：补齐 `COST-E2E-006` 的真实浏览器负面场景，避免 explorer 返回 `refreshing` / `stale` / `failed` 空 payload 时，页面把它当作最终空态、0 条 summary 或允许导出非 fresh 成本数据。
- 影响范围：`CostStatisticsPage` 的 read model status gate、成本统计 deterministic Playwright mock、成本统计 Browser 主流程 spec、页面 Vitest 和模块 Spec-first E2E 文档。
- 关键决策：
  - `refreshing`、`stale`、`failed`、`missing`、`schema_mismatch`、`unavailable` 均视为非 fresh；非 fresh 时显示刷新或不可用语义，不渲染成本表格，不显示最终空态或 0 条 summary，不允许打开导出中心。
  - Playwright mock 新增 `costStatisticsReadModelStatus` 选项，专门构造非 fresh 空 payload；测试断言无 console error、无 pageerror，且没有非 abort 请求失败。
  - 不改变成本归因 service、API shape、SQL read model、scope policy 或 worker 入队逻辑；真实 worker drain 仍由 `infra-smoke` / staging gate 验证。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、本实施记录和全局 Spec-first inventory / testing closure state。
- 测试覆盖：
  - 更新 `web/src/pages/CostStatisticsPage.tsx`。
  - 更新 `web/src/test/CostStatisticsPage.test.tsx::hides read model refresh details without treating empty accepted payload as final empty data`。
  - 更新 `web/e2e/fixtures/apiMocks.ts`。
  - 新增 `web/e2e/cost-statistics-flow.spec.ts` 中 `refreshing` / `stale` / `failed` Browser 场景。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实 PostgreSQL/RabbitMQ/Redis/systemd `cost-statistics` worker；真实 enqueue-to-fresh、真实大数据下载和真实文件打开仍需 staging/production smoke。
- 后续事项：`COST-E2E-009` 已由后续 download event 覆盖；继续补真实基础设施 worker drain、更多导入变体或大数据视觉稳定性。

## 2026-06-18 - 成本统计 explorer payload contract 修复

- 目标：修复 App Health 显示 `成本统计 已同步`，但进入成本统计页仍出现“成本统计数据加载失败”的问题，避免旧 read model/cache payload 被当作当前 explorer API 的 fresh 数据。
- 影响范围：`CostStatisticsQueryService.get_explorer_from_sql_read_model(...)`、`ReadModelQueryGateway`、成本统计 SQL runtime 测试、read-models 共享测试与文档。
- 关键决策：
  - 成本统计 explorer 的 fresh payload 必须包含 `summary`、`time_rows`、`project_rows`、`expense_type_rows`；只看 schema/source/readiness 不足以证明页面 mapper 可消费。
  - 业务 shape 校验放在后端 read boundary：旧 Redis payload 校验失败时 miss 并改读 SQL view；旧 SQL payload 校验失败时返回 canonical empty refreshing payload，入队 `api_payload_shape_invalid`，不写 fresh cache。
  - 前端不新增旧 shape 兼容分支，避免让页面继续承接过期 API contract。
- 文档影响：更新成本统计状态机、测试矩阵、实施记录，并同步 read-models 状态机/测试矩阵/实施记录。
- 测试覆盖：
  - 新增 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues`。
  - 新增 `tests/test_read_model_query_gateway.py::ReadModelQueryGatewayTests::test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view`、`test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache`。
  - 更新 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_api_reads_sql_and_populates_short_redis_cache` 的 valid explorer fixture，锁定当前 shape。
- 验证命令：见本轮交付说明。
- 未测风险：未连接真实 OA iframe、真实生产 Redis/PostgreSQL 或 worker drain；发布后若生产已有旧缓存，需等待 TTL 或按运维流程清理，但新后端不再把 invalid cache 当 fresh 返回。
- 后续事项：后续 explorer API shape 改动必须同步 payload validator、schema/source version、SQL projection 和前端 API mapper 测试。

## 2026-06-18 - 成本统计 explorer 认证错误呈现修复

- 目标：修复进入成本统计页时后端返回 `401 invalid_oa_session` 却被页面统一显示为“成本统计数据加载失败”的问题，避免把 OA 登录态缺失误判为成本统计/read model 故障。
- 影响范围：`web/src/pages/CostStatisticsPage.tsx`、`web/src/test/CostStatisticsPage.test.tsx`、成本统计测试矩阵。
- 关键决策：
  - 保持后端 API、read model、worker、scope contract 和成本归因架构不变；直接请求应用接口已确认无 OA 登录态时后端返回结构化 `401` 和业务 `message`。
  - 页面加载 explorer 失败时仅对 `401`、`403` 和 `invalid_oa_session` 暴露后端业务文案；普通 500/网络异常继续使用泛化成本统计失败文案，避免暴露底层异常。
  - `202 refreshing`、empty accepted payload、SQL read model miss/stale 仍走既有刷新状态，不当作本次错误。
- 文档影响：更新本实施记录和 `tests.md`；产品规格、API 契约、状态机、read model/worker 长期事实源不变。
- 测试覆盖：
  - 新增 `web/src/test/CostStatisticsPage.test.tsx::surfaces OA session errors from explorer loading`。
  - 保留既有泛化 500 加载失败测试，避免所有后端错误都直接透出。
- 七类测试覆盖：
  - Business core unit tests：不适用；未改变成本归因、状态流转、金额计算或项目范围。
  - Service-layer tests：不适用；未改 service/repository/read model/worker。
  - API contract tests：后端契约未改；用直接应用请求确认 `401 invalid_oa_session` shape。
  - Read model/cache/background job tests：不适用；未改变 read model freshness、queue、cache 或 worker。
  - Frontend component and interaction tests：适用，新增页面级认证错误呈现回归。
  - End-to-end business-flow integration tests：不适用；未跨模块改变业务流。
  - Existing feature regression tests：适用，保留成本统计 500 泛化失败、refreshing empty payload 和既有交互回归。
- 验证命令：`PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`；直接应用请求 `/api/cost-statistics/explorer?month=2026-03&project_scope=active`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_sql_runtime -v`。
- 未测风险：未跑真实 OA iframe 登录链路、真实浏览器手工进入、生产 PostgreSQL scope cleanup 或 RabbitMQ/Redis worker drain；本轮修复只覆盖错误呈现层。

## 2026-06-18 - Workbench 成本关系 Browser fan-out

- 目标：补齐 Spec-first Browser E2E 中的成本统计下游 fan-out，防止关联台 open candidate 被误算进成本，或 confirmed 成本关系写入后成本页没有重新读取并展示。
- 影响范围：`web/e2e/cost-statistics-relation-fanout.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、成本统计 Spec-first E2E 文档、测试矩阵、状态机和全局测试闭环文档。
- 关键决策：
  - 使用 opt-in deterministic mock `costStatisticsRelationFanout` 构造成本关系链路；默认成本统计 mock 数据保持不变。
  - Browser 规格先断言候选阶段看不到 `智能工厂项目` 和 `智能工厂设备尾款`，再通过关联台确认关系，返回成本页验证项目金额 `58,000.00`、对应流水和详情 modal。
  - 本轮不改成本归因 service、SQL projection 或 read model worker；candidate 排除和 confirmed inclusion 的后端规则继续由既有 service/SQL tests 保护。
- 文档影响：新增 `e2e-spec.md` / `e2e-coverage.md`，更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing*.md` 和 workbench-relations 覆盖矩阵。
- 测试覆盖：
  - `web/e2e/cost-statistics-relation-fanout.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改业务规则；candidate 排除由既有成本 service/SQL 测试继续保护。
  - Service-layer tests：本轮未改 service/read model 写边界；真实 worker drain 仍为 staging/production 风险。
  - API contract tests：适用；e2e 断言成本 explorer/detail 在 Workbench confirm 后重新读取并展示 confirmed 成本关系。
  - Read model/cache/background job tests：本轮未改 worker/readiness；真实 enqueue-to-fresh 仍需 staging smoke。
  - Frontend component and interaction tests：适用并新增真实 Chromium 跨页确认、返回成本页、项目/费用/流水/详情展示。
  - End-to-end business-flow integration tests：适用并新增 Workbench confirm -> 成本统计重新读取 -> confirmed 成本关系出现的浏览器闭环。
  - Existing feature regression tests：适用，防止 candidate/linked relation 成本语义和既有成本页下钻断链。
- 未测风险：真实 RabbitMQ/Redis/cost-statistics worker drain、生产旧 scope cleanup、真实大数据下载/视觉性能、settings/project scope 和其他导入变体到成本页的更多 fan-out 仍需后续轮次或 staging smoke。

## 2026-06-17 - Browser e2e 项目下钻与导出错误反馈

- 目标：补齐成本统计真实浏览器主路径，防止后续页面维护时破坏 project scope、项目/费用类型/流水详情下钻、导出 preview 和结构化导出错误反馈。
- 影响范围：`web/e2e/cost-statistics-flow.spec.ts`、`web/e2e/fixtures/apiMocks.ts`、`web/package.json`、成本统计测试矩阵与全局测试闭环文档。
- 关键决策：
  - 使用 deterministic API mocks 构造 active/all 项目范围差异，浏览器必须请求 `project_scope=all` 后才能看到已完成项目。
  - e2e 断言真实 Chromium 中的可见 UI、transaction detail query、export-preview query 和 export row-limit JSON 错误展示；不新增后端业务代码或 read model 逻辑。
  - 导出接口在 e2e 中返回 `cost_statistics_export_row_limit_exceeded`，用于保护前端对结构化错误的真实浏览器闭环。
- 文档影响：更新本实施记录、`tests.md`、`state-machine.md`、`docs/dev/testing*.md` 和 testing closure dependency/state。
- 测试覆盖：
  - `web/e2e/cost-statistics-flow.spec.ts`
  - `cd web && npm run e2e:smoke`
- 七类测试覆盖：
  - Business core unit tests：本轮未改成本归因规则，由既有 service tests 保护。
  - Service-layer tests：本轮未改 service/read model 写边界，由既有 cost read model/runtime tests 保护。
  - API contract tests：适用，e2e 额外断言 explorer project scope、transaction detail、export-preview 和 export row-limit response。
  - Read model/cache/background job tests：本轮未改 worker/readiness；真实 worker drain 仍属未测风险。
  - Frontend component and interaction tests：适用并新增真实 Chromium tab、scope、三段下钻、modal、preview 和导出错误反馈。
  - End-to-end business-flow integration tests：适用并新增 explorer -> project scope -> drilldown -> export preview/error browser flow。
  - Existing feature regression tests：适用并防止 project scope、detail modal 和 export center 在真实浏览器中断链。
- 未测风险：真实 PostgreSQL scope cleanup `--apply`、真实 RabbitMQ/Redis/cost-statistics worker drain、真实文件下载/打开、大数据下载耗时和视觉性能仍需 staging/manual smoke。

## 2026-06-17 - 成本统计项目费用类型下钻重复流水行修复

- 目标：修复成本统计项目视图中选中项目后再切换费用类型，真实数据含同一流水多条成本行时页面卡死/白屏的问题。
- 影响范围：`CostStatisticsPage` 的成本流水表行身份、`CostStatisticsTable` 行 key contract、成本统计前端 mock 和页面交互测试。
- 关键决策：`transaction_id` 是银行流水身份，不是成本统计行身份；前端表格行 key 改为由流水 id、交易时间、项目、费用类型、费用内容、金额和行序号组成的渲染键，避免同一流水拆成多条成本行时 HeroUI Table collection 冲突或丢行。不改变 API shape，后端 `row_key` 是否外露另行评估。
- 文档影响：更新本实施记录和 `tests.md` 历史 bug/前端交互覆盖；产品、API、read model 和 worker 长期事实源不变。
- 测试覆盖：新增 `web/src/test/CostStatisticsPage.test.tsx::project view keeps split cost rows with the same transaction id renderable`，mock API 可返回重复 `transaction_id` 的成本行。
- 验证命令：`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx -t "project view keeps split cost rows" --reporter=verbose`；`cd web && npm test -- --run src/test/CostStatisticsPage.test.tsx --reporter=verbose`；`cd web && npm run build`。
- 未测风险：本地没有连接真实生产后端复现用户截图中的 123 条明细；真实生产数据量、浏览器白屏堆栈和后端是否应外露 canonical cost row key 仍需 staging/production smoke 进一步确认。
- 后续事项：如后端 API 后续补充 `row_key`，前端可优先使用后端 canonical cost row identity，保留当前合成键作为兼容 fallback。

## 2026-06-16 - 成本统计导出错误反馈闭环

- 目标：确保成本统计同步导出被后端行数上限拒绝时，前端下载路径解析结构化错误并在导出中心展示具体原因。
- 影响范围：`web/src/features/cost-statistics/api.ts`、`web/src/pages/CostStatisticsPage.tsx`、成本统计前端 API/page 测试和 P2/P3 闭环台账。
- 关键决策：非 2xx 下载响应先读取 `message` / nested `error.message` / `error`，HTML fallback 仍按代理配置错误处理；页面导出和预览 catch 保留后端消息，不再统一覆盖成泛化失败。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；长期产品/API 文档不变。
- 测试覆盖：新增 `web/src/test/CostStatisticsApi.test.ts::surfaces backend row-limit messages from failed export downloads`；新增 `web/src/test/CostStatisticsPage.test.tsx::shows backend export failure messages inside the export center`。
- 验证命令：`npm run test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx src/test/TurnoverLedgerApi.test.ts src/test/PendingInvoicesApi.test.ts`。
- 未测风险：真实浏览器下载、代理错误页面、生产网络中断和大文件打开仍需 staging/manual smoke。
- 后续事项：如业务需要超过 20,000 行导出，应改异步导出任务并补任务进度/下载链接闭环。

## 2026-06-16 - P2/P3 成本统计同步导出上限

- 目标：收敛成本统计 time/project/expense_type 大数据 export-preview/export 的同步生成风险，避免大匹配集继续构造预览 rows 或 XLSX。
- 影响范围：`CostStatisticsService`、`CostStatisticsApiRoutes`、成本统计 service/API 测试、模块测试矩阵和 P2/P3 闭环台账。
- 关键决策：导出上限为 20,000 行；超过上限返回 `cost_statistics_export_row_limit_exceeded`，details 包含 `view`、`total` 和 `limit`。transaction 单笔详情不使用该上限。
- 文档影响：更新 `tests.md`、本实施记录和 `.planning/P2P3-CLOSURE-PLAN.md`；产品/API 长期文档未扩展，因为这是性能保护边界。
- 测试覆盖：新增 `tests/test_cost_statistics_service.py::CostStatisticsServiceTests::test_export_preview_and_download_reject_large_time_export_before_workbook_generation`；新增 `tests/test_cost_statistics_api.py::CostStatisticsApiTests::test_cost_statistics_export_limit_returns_structured_error`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service.CostStatisticsServiceTests.test_export_preview_and_download_reject_large_time_export_before_workbook_generation tests.test_cost_statistics_api.CostStatisticsApiTests.test_cost_statistics_export_limit_returns_structured_error -v`。
- 未测风险：真实 PostgreSQL EXPLAIN、生产数据分布、浏览器下载/打开文件和视觉性能仍需 staging/manual smoke；本地只证明超大匹配集不会继续同步生成预览或 XLSX。
- 后续事项：继续执行 authenticated HTTP/SSE/read model final gate；若真实用户需要超过 20,000 行导出，应另设异步导出任务而不是放宽同步路径。

## 2026-06-16 - P2/P3 首屏 SLO 与父 scope 有界聚合证据

- 目标：复核成本统计在 P2/P3 一秒级推进中的真实性能护栏，避免把该页误按普通 rows 分页列表处理。
- 影响范围：`tests/test_http_slo_probe.py`、成本统计测试矩阵和 P2/P3 闭环台账；未改变成本统计业务代码、API contract 或页面行为。
- 关键决策：成本统计页面首屏事实源是 explorer/summary 聚合 read model，不是可追加 `page_size` 的 rows 列表；本地证据应锁定认证态 SLO 探针覆盖 `/api/cost-statistics/explorer` 与 `/api/cost-statistics`，并复用 SQL runtime 中父 scope 从已物化月份 shard 聚合、不读 Workbench 全量 payload 的测试。
- 文档影响：更新 `tests.md` 和本实施记录；长期产品/API 文档不变。
- 测试覆盖：更新 `tests/test_http_slo_probe.py::HttpSloProbeTests::test_default_probes_cover_page_domains_and_known_slow_endpoints`，显式断言成本统计 explorer/summary 默认探针；沿用 `tests/test_cost_statistics_sql_runtime.py::CostStatisticsSqlRuntimeTests::test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_http_slo_probe.HttpSloProbeTests.test_default_probes_cover_page_domains_and_known_slow_endpoints -v`。
- 未测风险：未连接真实 PostgreSQL 执行 EXPLAIN、pg_stat 或生产旧 scope `--apply`；真实登录态 p95/p99、worker drain、导出耗时和浏览器下载仍需 staging/生产 smoke。
- 后续事项：生产 scope contract repair 获批后，复跑认证态 HTTP SLO 和 cost-statistics App Status。

## 2026-06-16 - 外部往来 Postgres 写路径补齐成本统计 scope contract

- 目标：补齐 `turnover_relation_changed` 下游对成本统计的事务内入队 contract，避免再次产生裸月份/裸 `all` 的 `cost_statistics.read_model.refresh`。
- 影响范围：外部往来确认/撤回后的成本统计 dirty scope、outbox、readiness，以及生产 scope contract repair。
- 关键决策：成本统计 canonical scope 仍只允许 `active:YYYY-MM`、`all:YYYY-MM`、`active:all`、`all:all`；事务入队路径在写入 durable queue 前归一化，不改变 worker projection contract。
- 文档影响：更新成本统计、read-models、turnover-ledger 和 P2/P3 closure ledger。
- 测试覆盖：新增 turnover Postgres dirty outbox writer 回归；保留 `tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py` 的成本统计 scope policy/repair 覆盖。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_postgres_dirty_outbox_writer_normalizes_cost_statistics_scopes_in_transaction tests.test_turnover_ledger_api.TurnoverLedgerApiTests.test_target_postgres_withdraw_relation_uses_facade_without_direct_read_model_clear -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`。
- 未测风险：生产现存 legacy rows 只完成 dry-run 取证，未执行 `--apply`；一秒级 worker drain 需在发布和 cleanup 后复测。
- 后续事项：批准后执行 production scope contract repair，再复查 cost-statistics App Status 和 write-operation SLO。

## 2026-06-13 - 成本税务发票输入收敛到 canonical invoice facts

- 目标：删除成本税务 SQL projection 直接读取 `app.oa_attachment_invoice_cache` 拼进项计划项的旁路，跟随统一 Invoice repository 事实源。
- 影响范围：`CostTaxSqlProjectionBuilder._build_tax_payload`、税金抵扣服务共享发票读取链路、Workbench OA 附件发票 promotion。
- 关键决策：`app.oa_attachment_invoice_cache` 继续作为 OA 附件 parser cache 和运维审计对象，但不作为成本税务 read model 的正式发票输入。OA 附件正式发票进入 `app.invoices` 后由 `_invoice_items(..., output=False)` 统一读取。
- 文档影响：更新本模块记录，并同步 Workbench/Tax Offset 记录。
- 测试覆盖：通过 `tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py` 和 Workbench canonical projection tests 间接覆盖；本模块未新增重复成本统计专测。
- 验证命令：见本轮最终执行记录。
- 未测风险：未跑完整成本统计 API/SQL 回归；若后续修改成本归因或 projection scope，应按本模块测试矩阵补跑最小闭环。

## 2026-06-11 - 成本统计测试闭环矩阵与状态机补齐

- 目标：执行 testing closure master goal 的 `cost-statistics` 模块轮次，确认新功能改动不会绕过成本归因、read model freshness、App Status 或页面交互回归保护。
- 影响范围：`docs/modules/cost-statistics/tests.md`、`docs/modules/cost-statistics/state-machine.md`、`docs/modules/cost-statistics/implementation-notes.md`；未改变业务代码或测试代码。
- 关键决策：现有 P0/P1 自动化测试已覆盖成本归因规则、项目范围、API 契约、导出 shape、SQL read model、`active/all` parent 与 month shard readiness、scope gateway、worker/App Status 语义和前端 loading/empty/error/refreshing/stale 交互；本轮不新增重复测试。
- 文档影响：补齐七类测试矩阵、影响面清单、关键 smoke flows、历史 bug 回归库、状态机和 remaining risk。
- 测试覆盖：沿用 `tests/test_cost_statistics_service.py`、`tests/test_project_costing_service.py`、`tests/test_project_costing_api.py`、`tests/test_cost_statistics_api.py`、`tests/test_cost_statistics_read_model_service.py`、`tests/test_cost_statistics_runtime_service.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_read_model_scope_contract.py`、`tests/test_app_status_overview_service.py`、`tests/test_runtime_monitoring.py`、`web/src/test/CostStatisticsApi.test.ts`、`web/src/test/CostStatisticsPage.test.tsx`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_service tests.test_project_costing_service tests.test_project_costing_api -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_api tests.test_cost_statistics_read_model_service tests.test_cost_statistics_runtime_service -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_app_status_overview_service tests.test_runtime_monitoring -v`；`cd web && npm test -- --run src/test/CostStatisticsApi.test.ts src/test/CostStatisticsPage.test.tsx`。
- 未测风险：未在真实生产数据库执行 `scripts/check-read-model-scope-contracts.py --apply`；未跑真实 RabbitMQ/Redis/cost-statistics worker drain；未做大数据量导出和真实浏览器下载 smoke。
- 后续事项：下一轮处理 `tax-offset`，重点审计税金认证导入、ETC、invoice lifecycle 与成本税务共享链路。

## 2026-06-10 - 成本统计生产旧 scope 检查与清理

- 目标：清理历史 `2026-03`、`2026-04`、裸 `all` 或未知 project scope 造成的成本统计 App Status readiness、dirty scope 和 dead-letter/outbox 污染。
- 影响范围：`read_model.app_status_readiness`、`job.read_model_dirty_scopes`、`job.outbox_events` 中 `cost_statistics` 相关旧状态。
- 关键决策：只删除当前 scope policy registry 不认为是 canonical 的成本统计状态；legacy scope 会通过 gateway 补投 `active/all` replacement scope，invalid scope 不猜测含义。
- 文档影响：更新成本统计测试矩阵和 runtime worker 运维 runbook。
- 测试覆盖：`tests/test_read_model_scope_contract.py` 覆盖检查、删除和 replacement enqueue 去重。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_scope_contract -v`；`PYTHONPATH=backend/src scripts/check-read-model-scope-contracts.py --help`。
- 未测风险：未在真实生产数据库执行 `--apply`。
- 后续事项：无。

## 2026-06-10 - 成本统计 read model refresh scope contract

- 目标：阻止裸月份/裸 `all` 作为 `cost_statistics.read_model.refresh` scope 进入 durable queue，避免 SQL projection 报 `scope_key must use project_scope:month` 并污染 App Status readiness。
- 影响范围：成本统计 read model refresh 入队 contract、worker lifecycle 触发链路。
- 关键决策：合法成本统计 scope 统一为 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 和 `all:all`。旧裸月份/裸 `all` 只允许在统一 gateway 中归一化；未知 project scope 直接拒绝。
- 文档影响：更新成本统计、read-models、runtime-workers 模块入口和测试矩阵。
- 测试覆盖：`tests/test_read_model_refresh_gateway.py` 覆盖成本统计 policy，`tests/test_runtime_worker_read_model_refresh_scopes.py` 覆盖 worker lifecycle。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v`；`PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_generic_cost_statistics_enqueue_expands_month_scopes -v`。
- 未测风险：阶段 1 未执行真实生产库清理。
- 后续事项：已由后续 scope contract 检查/清理入口补齐。
